"""Small independent rendered fixtures. All physical properties are synthetic only."""
from fractions import Fraction
from pathlib import Path
import av
import cv2
import numpy as np
from ..core.config import create_project,save_project,register
from ..core.storage import atomic_json,dumps
from ..models.physics.farkas import G

BGR={"red":(25,25,240),"blue":(230,60,20),"green":(25,180,25),"yellow":(20,220,235)}


def render_disks(centers,angles,radius=32,size=(640,400),occluded=None,grid=True,grid_spacing=50):
    scale=3;w,h=size
    image=np.full((h*scale,w*scale,3),224,np.uint8)
    if grid:
        for x in np.arange(0,w,grid_spacing):cv2.line(image,(round(x*scale),0),(round(x*scale),h*scale),(175,175,175),scale)
        for y in np.arange(0,h,grid_spacing):cv2.line(image,(0,round(y*scale)),(w*scale,round(y*scale)),(175,175,175),scale)
    ratios=[.42,.58,.49];deltas=[1.1,-1.5,2.2]
    for i,(center,theta) in enumerate(zip(centers,angles)):
        # OpenCV resize maps pixel centers via (x+.5)*scale-.5. Omitting this
        # causes an artificial ~0.47 px 2D ground-truth bias at scale=3.
        c=np.round((np.asarray(center)+.5)*scale-.5).astype(int);r=round(radius*scale)
        cv2.circle(image,tuple(c),r,(45,45,45),-1,cv2.LINE_AA)
        cv2.circle(image,tuple(c),r,(15,15,15),2*scale,cv2.LINE_AA)
        for k in range(6):
            a=np.degrees(-theta)+k*60
            cv2.ellipse(image,tuple(c),(round(.86*r),round(.86*r)),0,a,a+18,(245,245,245),round(.16*r),cv2.LINE_AA)
        colors=[("red","blue"),("blue","yellow"),("green","red")][i%3]
        for role,color,rr,angle in [("rim",colors[0],.87,theta),("inner",colors[1],ratios[i%3],theta+deltas[i%3])]:
            if occluded and (i,role) in occluded:continue
            point=c+np.array([np.cos(angle),-np.sin(angle)])*r*rr
            cv2.circle(image,tuple(np.round(point).astype(int)),round(r*(.12 if role=="rim" else .075)),BGR[color],-1,cv2.LINE_AA)
    return cv2.resize(image,(w,h),interpolation=cv2.INTER_AREA)


def make_video(path,count=60,rate=60,kind="three",size=(640,400),seed=7):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    truth=[]
    with av.open(str(path),"w") as container:
        stream=container.add_stream("libx264",rate=rate);stream.width=size[0];stream.height=size[1];stream.pix_fmt="yuv420p"
        stream.options={"crf":"16","preset":"fast"}
        for i in range(count):
            t=i/rate
            if kind=="three":
                centers=[[95+45*t,90+7*t],[305-20*t,205],[490-35*t,310-8*t]];angles=[1.5*t,-2*t,2.7*t]
            elif kind=="collision":
                tc=.8;speed=100.;x1=150+speed*min(t,tc)+15*max(0,t-tc);x2=294+85*max(0,t-tc)
                centers=[[x1,200],[x2,200]];angles=[0.,0.]
            else:
                centers=[[100+40*t,200]];angles=[2*t]
            image=render_disks(centers,angles,size=size)
            cv2.putText(image,f"SYNTHETIC {seed}",(8,size[1]-8),cv2.FONT_HERSHEY_SIMPLEX,.35,(80,80,80),1)
            frame=av.VideoFrame.from_ndarray(image,format="bgr24");frame.pts=i;frame.time_base=Fraction(1,rate)
            for packet in stream.encode(frame):container.mux(packet)
            truth.append({"frame_index":i,"time_s":t,"centers_px":centers,"angles_rad":angles})
        for packet in stream.encode():container.mux(packet)
    with path.with_suffix(".truth.jsonl").open("w",encoding="utf-8") as f:
        for row in truth:f.write(dumps(row)+"\n")
    return path


def make_demo(folder,count=90):
    folder=Path(folder);project=create_project(folder,"합성 검증 데모 - 실험값 아님")
    project["mode"]="synthetic_demo"
    for c in project["chips"]:
        c.update(mass_kg=.01,thickness_m=.003,radius_status="synthetic",radius_sigma_m=.00005,inertia_model="uniform_disk")
    project["analysis"].update(radius_px=[29,36],omega_bound_rad_s=30.,window_s=.16,assignment_gate_px=45.)
    project["time_profile"].update(status="synthetic_known_clock",evidence="generator exact frame clock",
        segments=[{"p_start":0.,"p_end":None,"t_start":0.,"slow_factor":1.}],capture_fps=60.,preset="synthetic")
    project["calibration"].update(status="synthetic",H=[[.02/32,0,0],[0,-.02/32,.25],[0,0,1]],image_size=[640,400],capture_mode="synthetic",id="synthetic_exact_plane")
    for i,c in enumerate(project["chips"]):
        project["templates"][c["id"]]={"delta_inner_minus_rim_rad":[1.1,-1.5,2.2][i],"inner_radius_ratio":[.42,.58,.49][i],"rim_radius_ratio":.87,"geometry_status":"synthetic_known","session_id":"synthetic","colors":{}}
    save_project(folder,project)
    path=make_video(folder/"videos"/"합성 3칩.mp4",count)
    register(folder,project,[path]);save_project(folder,project)
    atomic_json(folder/"fit_dataset.synthetic.json",fit_fixture())
    atomic_json(folder/"simulation.synthetic.json",{"mode":"synthetic_demo","bodies":[{"mass":.01,"radius":.02,"inertia":.000002,"id":f"chip_{i+1}"} for i in range(3)],
                "initial":[[0,0,1,0,0,0],[.15,0,0,0,0,0],[.32,0,0,0,0,0]],"times":np.linspace(0,.7,141).tolist(),
                "mu_bottom":.05,"e_normal":.8,"e_tangential":-1.,"mu_collision":0.})
    return project


def fit_fixture(seed=11):
    """Analytic constant-deceleration and independently assembled impulse fixtures."""
    rng=np.random.default_rng(seed);free=[];impacts=[]
    mu=.12;en=.72;et=-.83;muc=.08
    for j in range(6):
        t=np.linspace(0,.35,36);v=.8+.1*j;angle=.2*j
        distance=v*t-.5*mu*G*t*t
        z=np.column_stack([distance*np.cos(angle),distance*np.sin(angle),np.full(len(t),angle)])
        z+=rng.normal(0,[.00008,.00008,.003],z.shape)
        free.append({"id":f"free{j}","session_id":f"session_{j//2}","time_status":"synthetic_known_clock","geometry_status":"synthetic","source":"synthetic_observation",
                     "body":{"mass":.01,"radius":.02,"inertia":.000002},"times":t.tolist(),"position_angle":z.tolist(),
                     "sigma":[.00008,.00008,.003],"initial_guess":[0,0,v*np.cos(angle),v*np.sin(angle),angle,0],
                     "initial_sigma":[.001,.001,.05,.05,.02,.05]})
    for j in range(18):
        m1=.01;m2=.015 if j%2 else .01;r1=r2=.02;I1=.5*m1*r1*r1;I2=.5*m2*r2*r2
        a=.7+.03*j;c=.05+.10*j
        An=1/m1+1/m2;At=3*An
        jn=(1+en)*a/An;jt=(1+et)*c/At+min(muc*jn,c/At)
        pre=np.array([[0,0,a,c,0,0],[r1+r2,0,0,0,0,0]],float)
        post=pre.copy();post[0,2:4]-=[jn/m1,jt/m1];post[1,2:4]+=[jn/m2,jt/m2];post[0,5]-=r1*jt/I1;post[1,5]-=r2*jt/I2
        pre[:,2:4]+=rng.normal(0,.001,(2,2));post[:,2:4]+=rng.normal(0,.001,(2,2));post[:,5]+=rng.normal(0,.04,2)
        impacts.append({"id":f"impact{j}","session_id":f"session_{j//6}","time_status":"synthetic_known_clock","geometry_status":"synthetic","source":"synthetic_observation",
                        "kind":"isolated_binary","approved":True,"normal":[1,0],"pre":pre.tolist(),"post":post.tolist(),
                        "bodies":[{"mass":m1,"radius":r1,"inertia":I1},{"mass":m2,"radius":r2,"inertia":I2}],"normal_sigma":.003,"pre_sigma":[.002,.002,.05],"post_sigma":[.002,.002,.05]})
    return {"mode":"synthetic_demo","seed":seed,"truth":{"mu_bottom":mu,"e_normal":en,"e_tangential":et,"mu_collision":muc},
            "split":{"unit":"session","train":["session_0","session_1"],"holdout":["session_2"]},"free_trials":free,"impact_trials":impacts}
