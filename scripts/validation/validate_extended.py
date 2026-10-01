"""Independent image stress measurements and a bounded-memory streaming run."""
import argparse
from pathlib import Path
import time
import platform
import av
import cv2
import numpy as np
import psutil
from fractions import Fraction
from pokerchip.config import default_project,create_project,register,save_project
from pokerchip.demo import render_disks
from pokerchip.vision import measure
from pokerchip.calibration import transform
from pokerchip.storage import atomic_json
from pokerchip.jobs import Batch


def image_checks(out):
    settings=default_project()['analysis'];settings['radius_px']=[25,40]
    H=np.array([[.9,.08,25],[.025,.86,20],[.0002,.0001,1.]])
    scale=np.diag([.001,-.001,1.])
    cal={'status':'synthetic','H':(scale@np.linalg.inv(H)).tolist()}
    rng=np.random.default_rng(42);results=[]
    for name in ('clean','blur','noise','shadow','occlusion'):
        for center in ([110.3,100.7],[330.1,180.2],[490.4,310.1]):
            image=render_disks([center],[.7])
            if name=='blur':image=cv2.GaussianBlur(image,(9,9),1.8)
            if name=='noise':image=np.clip(image.astype(float)+rng.normal(0,8,image.shape),0,255).astype('uint8')
            if name=='shadow':image[:,:int(center[0])]=(image[:,:int(center[0])].astype(float)*.65).astype('uint8')
            if name=='occlusion':cv2.rectangle(image,(int(center[0]+5),int(center[1]-40)),(int(center[0]+40),int(center[1]+40)),(180,180,180),-1)
            warped=cv2.warpPerspective(image,H,(640,400))
            c=transform([center],H)[0]
            radial=transform([np.array(center)+[32,0],np.array(center)+[0,32]],H)
            radius=float(np.mean(np.linalg.norm(radial-c,axis=1)))
            truth=np.array(center)*[.001,-.001]
            try:
                r=measure(warped,(c,radius),cal,settings)
                error=float(np.linalg.norm(np.array(r['world_center_m'])-truth))
                results.append({'case':name,'center':center,'center_error_m':error,'equivalent_original_px':error/.001,'status':r['status'],'visible_arc':r['visible_arc_fraction']})
            except ValueError as exc:results.append({'case':name,'center':center,'status':'rejected','reason':str(exc)})
    atomic_json(out/'image_stress.json',{'seed':42,'assumption':'known candidate; candidate recall is NOT measured','cases':results})
    assert all(r.get('equivalent_original_px',100)<1 for r in results if r['case']=='clean')


def soak(out,count):
    folder=out/'streaming';folder.mkdir(exist_ok=True)
    project=create_project(folder,'합성 메모리 검증');project['analysis'].update(radius_px=[28,37],redetect_every=10)
    path=folder/'stream.mp4'
    with av.open(str(path),'w') as container:
        s=container.add_stream('libx264',rate=240);s.width=640;s.height=400;s.pix_fmt='yuv420p';s.options={'crf':'20','preset':'fast'}
        for i in range(count):
            image=render_disks([[200+80*np.sin(i/400),200]],[i/150])
            f=av.VideoFrame.from_ndarray(image,format='bgr24');f.pts=i;f.time_base=Fraction(1,240)
            for packet in s.encode(f):container.mux(packet)
        for packet in s.encode():container.mux(packet)
    register(folder,project,[path],['chip_1']);save_project(folder,project)
    samples=[];process=psutil.Process();start=time.perf_counter()
    def callback(event):
        samples.append({'elapsed_s':time.perf_counter()-start,'frame':event.get('frame'),'stage':event.get('stage'),'rss_bytes':process.memory_info().rss})
    result=Batch(folder,project,callback).run()
    atomic_json(out/'streaming_memory.json',{'host':platform.platform(),'logical_cpu':psutil.cpu_count(),'ram_bytes':psutil.virtual_memory().total,'fixture':{'frames':count,'width':640,'height':400,'rate':240,'codec':'H264 synthetic'},'elapsed_s':time.perf_counter()-start,'rss_sampled_peak_bytes':max(r['rss_bytes'] for r in samples),'samples':samples,'statuses':[r['status'] for r in result],'scope':'synthetic frame-count scaling check; not hours-long soak or real FHD240 throughput'})
    assert all(r['status']=='complete' for r in result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--frames',type=int,default=2000);args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    image_checks(out)
    if args.frames:soak(out,args.frames)
