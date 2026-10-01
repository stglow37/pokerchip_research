"""Candidates are separate from original-image subpixel edges and geometric fits."""
import cv2
import numpy as np
from scipy.optimize import least_squares
from .calibration import to_world, to_pixel
from ..core.config import COLORS


def wrap(angle):
    return (np.asarray(angle)+np.pi)%(2*np.pi)-np.pi


def circle_fit(points, radius_prior=None, sigma_prior=None, noise_floor=.1):
    p = np.asarray(points,float)
    if len(p)<8:
        raise ValueError("원 경계점 부족")
    A = np.column_stack([2*p[:,0],2*p[:,1],np.ones(len(p))])
    sol = np.linalg.lstsq(A, np.sum(p*p,axis=1),rcond=None)[0]
    r = np.sqrt(max(0,sol[2]+sum(sol[:2]**2)))
    initial = np.r_[sol[:2],r]
    scale = max(noise_floor, r*.006)
    def residual(q):
        values = np.linalg.norm(p-q[:2],axis=1)-q[2]
        if radius_prior is not None and sigma_prior is not None:
            values = np.r_[values,(q[2]-radius_prior)*scale/sigma_prior]
        return values
    fit = least_squares(residual,initial,loss="soft_l1",f_scale=scale,max_nfev=120)
    err = np.linalg.norm(p-fit.x[:2],axis=1)-fit.x[2]
    mad = max(noise_floor,1.4826*np.median(abs(err-np.median(err))))
    good = abs(err)<3*mad
    if good.sum()<8 or fit.x[2]<=0:
        raise ValueError("유효 원 경계점 부족")
    v = p[good]-fit.x[:2]
    radii = np.linalg.norm(v,axis=1)
    J = np.column_stack([-v/radii[:,None],-np.ones(len(v))])
    covariance = np.linalg.pinv(J.T@J)*max(noise_floor**2,np.sum(err[good]**2)/max(1,len(v)-3))
    angles = np.sort(np.arctan2(v[:,1],v[:,0]))
    maxgap = np.max(np.diff(np.r_[angles,angles[0]+2*np.pi]))
    coverage = float((2*np.pi-maxgap)/(2*np.pi))
    condition = float(np.linalg.cond(J.T@J))
    return {"center": fit.x[:2], "radius": float(fit.x[2]), "residual_rms": float(np.sqrt(np.mean(err[good]**2))),
            "covariance": covariance, "visible_arc_fraction": coverage, "condition": condition,
            "inlier_fraction": float(good.mean()), "points": p[good],
            "status": "low_confidence" if coverage < .55 or condition > 300 else "partially_observed" if coverage < .85 else "observed",
            "uncertainty_kind": "conditional_linearized_edge_fit_excludes_shared_camera_bias"}


def edge_points(image, center, radius, rays=144, blockers=(), allowed_arc=None, gray=None):
    if gray is None:gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
    angles = np.linspace(0,2*np.pi,rays,endpoint=False)
    radial = np.linspace(.82*radius,1.18*radius,49)
    directions = np.column_stack([np.cos(angles),np.sin(angles)])
    xy = np.asarray(center)[None,None,:]+directions[:,None,:]*radial[None,:,None]
    profiles = cv2.remap(gray,xy[:,:,0].astype(np.float32),xy[:,:,1].astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT101)
    grad = np.abs(np.gradient(profiles,radial,axis=1))
    # Prefer the expected outer silhouette while retaining both light/dark rim sectors.
    score = grad*np.exp(-.5*((radial-radius)/(.095*radius))**2)
    k = np.argmax(score[:,2:-2],axis=1)+2
    points, strengths = [], []
    for i,j in enumerate(k):
        if allowed_arc is not None:
            deg = np.degrees(angles[i])%360
            a,b = allowed_arc
            if not (a<=deg<=b if a<=b else deg>=a or deg<=b):
                continue
        if grad[i,j]<8:
            continue
        left, mid, right = grad[i,j-1:j+2]
        denom = left-2*mid+right
        shift = np.clip(.5*(left-right)/denom,-.5,.5) if abs(denom)>1e-10 else 0.
        point = np.asarray(center)+directions[i]*(radial[j]+shift*(radial[1]-radial[0]))
        if not (2<=point[0]<image.shape[1]-2 and 2<=point[1]<image.shape[0]-2):
            continue
        if any(np.linalg.norm(point-np.asarray(c))<r*.99 for c,r in blockers):
            continue
        points.append(point)
        strengths.append(float(mid))
    return np.asarray(points).reshape(-1,2), strengths


def candidates(image, radius_range, roi=None, limit=12, profile="dark_chip"):
    if profile!="dark_chip":raise ValueError("검정 칩 전용 검출기입니다.")
    x0,y0,x1,y1 = roi or [0,0,image.shape[1],image.shape[0]]
    crop = image[y0:y1,x0:x1]
    scale = min(1.,960/max(crop.shape[:2]))
    gray = cv2.cvtColor(cv2.resize(crop,None,fx=scale,fy=scale),cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray,(5,5),1)
    circles = cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1.25,
                              max(8,radius_range[0]*scale*1.6),param1=100,param2=24,
                              minRadius=max(3,int(radius_range[0]*scale)),maxRadius=int(radius_range[1]*scale))
    result=[]
    # Dark-face components complement Hough when white rim sectors and motion
    # blur interrupt the circular edge. All candidates still undergo the same
    # original-image subpixel fit and dark-face/edge-quality checks below.
    threshold,_=cv2.threshold(gray,0,255,cv2.THRESH_BINARY|cv2.THRESH_OTSU)
    mask=(gray<np.clip(threshold,65,130)).astype(np.uint8)*255
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    mask=cv2.morphologyEx(cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel),cv2.MORPH_CLOSE,kernel)
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area=cv2.contourArea(contour)
        if len(contour)<12 or not .45*np.pi*(radius_range[0]*scale)**2<area<1.4*np.pi*(radius_range[1]*scale)**2:continue
        (x,y),(a,b),_=cv2.fitEllipse(contour);r=(a*b)**.5/2
        if min(a,b)/max(a,b)<.72 or area/(np.pi*a*b/4)<.65:continue
        if not radius_range[0]*scale*.85<r<radius_range[1]*scale:continue
        result.append((np.array([x/scale+x0,y/scale+y0]),float(r/scale)))
    if circles is not None:
        for x,y,r in circles[0]:
            patch=gray[max(0,int(y-r*.65)):int(y+r*.65)+1,max(0,int(x-r*.65)):int(x+r*.65)+1]
            a=np.linspace(0,2*np.pi,80,endpoint=False)
            outer=np.round(np.column_stack([x+1.3*r*np.cos(a),y+1.3*r*np.sin(a)])).astype(int)
            ok=(outer[:,0]>=0)&(outer[:,0]<gray.shape[1])&(outer[:,1]>=0)&(outer[:,1]<gray.shape[0])
            contrast=float(np.median(gray[outer[ok,1],outer[ok,0]])-np.median(patch)) if patch.size and ok.sum()>30 else 0
            if patch.size and contrast>12:
                c=np.array([x/scale+x0,y/scale+y0]);radius=float(r/scale)
                if not any(np.linalg.norm(c-q[0])<.8*min(radius,q[1]) for q in result):result.append((c,radius))
    return result[:limit]


def measure(image, candidate, calibration, settings, blockers=(), height=None, gray=None):
    center,radius = candidate
    # The supplied chips have a dark face. Reject grid intersections even if their
    # radial line crossings happen to support a numerically excellent circle.
    if gray is None:gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
    angles=np.linspace(0,2*np.pi,80,endpoint=False)
    directions=np.column_stack([np.cos(angles),np.sin(angles)])
    samples=[]
    for rr in (.35,.55,1.2,1.35):
        p=np.round(np.asarray(center)+radius*rr*directions).astype(int)
        valid=(p[:,0]>=0)&(p[:,0]<image.shape[1])&(p[:,1]>=0)&(p[:,1]<image.shape[0])
        if valid.sum()<30:raise ValueError("화면 밖 칩 경계")
        samples.append(float(np.median(gray[p[valid,1],p[valid,0]])))
    contrast=float(np.mean(samples[2:])-np.mean(samples[:2]))
    profile=settings.get("detector_profile","dark_chip")
    if profile!="dark_chip":raise ValueError("검정 칩 전용 검출기입니다.")
    if profile=="dark_chip" and contrast<settings.get("dark_face_contrast_min",12):raise ValueError("검은 칩 내부/주변 대비 부족: 격자 또는 가림 의심")
    p=np.round(np.asarray(center)+radius*.45*directions).astype(int)
    p[:,0]=np.clip(p[:,0],0,image.shape[1]-1);p[:,1]=np.clip(p[:,1],0,image.shape[0]-1)
    hsv=cv2.cvtColor(image[p[:,1],p[:,0]][None,:,:],cv2.COLOR_BGR2HSV)[0]
    if profile=="dark_chip" and np.median(hsv[:,2])>settings.get("dark_face_value_max",170):
        raise ValueError("검은 칩 내부 밝기 범위 밖: 배경/발사기 의심")
    bgr=np.median(image[p[:,1],p[:,0]].astype(float),axis=0)
    if bgr[2]>1.4*max(bgr[0],1) and bgr[2]-bgr[1]>12:
        raise ValueError('검정 몸체가 아닌 붉은 물체: 발사 장치 제외')
    polygon=settings.get('floor_polygon_px')
    if polygon and cv2.pointPolygonTest(np.asarray(polygon,np.float32),tuple(map(float,center)),False)<0:
        raise ValueError('바둑판 밖: 같은 바닥의 운동 분석에서 제외')
    points,strengths=edge_points(image,center,radius,settings.get("edge_rays",144),blockers,gray=gray)
    fit=circle_fit(points)
    # One refinement samples fresh ORIGINAL grayscale, never a threshold contour.
    points,strengths=edge_points(image,fit["center"],fit["radius"],settings.get("edge_rays",144),blockers,gray=gray)
    fit=circle_fit(points)
    if abs(fit["radius"]-radius)>radius*.25:
        raise ValueError("후보 대비 반경 불일치")
    if fit['residual_rms']>max(1.5,fit['radius']*settings.get('edge_relative_limit',.04)):
        raise ValueError('원 경계 오차가 큽니다: 그림자·격자·다른 물체 의심')
    world_points=to_world(fit["points"],calibration,height)
    wf=circle_fit(world_points,noise_floor=1e-6) if world_points is not None else None
    if wf is not None:
        # Resample the ORIGINAL image along projected concentric world circles.
        # This corrects the initial approximate pixel-circle sampling under perspective.
        for _ in range(2):
            a=np.linspace(0,2*np.pi,settings.get("edge_rays",144),endpoint=False)
            radial=np.linspace(.88,1.12,41)*wf["radius"]
            world=wf["center"][None,None,:]+np.column_stack([np.cos(a),np.sin(a)])[:,None,:]*radial[None,:,None]
            pixels=to_pixel(world.reshape(-1,2),calibration,height or 0).reshape(len(a),len(radial),2)
            values=cv2.remap(gray,pixels[:,:,0].astype(np.float32),pixels[:,:,1].astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT101)
            grad=abs(np.gradient(values,axis=1));indices=np.argmax(grad[:,2:-2]*np.exp(-.5*((radial[2:-2]/wf["radius"]-1)/.07)**2),axis=1)+2
            refined=[]
            for i,j in enumerate(indices):
                point=pixels[i,j]
                if grad[i,j]<2 or not (2<point[0]<image.shape[1]-2 and 2<point[1]<image.shape[0]-2):continue
                if any(np.linalg.norm(point-np.asarray(c))<r*.99 for c,r in blockers):continue
                left,mid,right=grad[i,j-1:j+2];denom=left-2*mid+right
                shift=np.clip(.5*(left-right)/denom,-.5,.5) if abs(denom)>1e-10 else 0.
                refined.append(world[i,j]+(world[i,j+1]-world[i,j])*shift)
            if len(refined)>=12:wf=circle_fit(refined,noise_floor=1e-6)
        center=to_pixel([wf["center"]],calibration,height or 0)[0]
    else:
        center=fit["center"]
    clearance=cv2.pointPolygonTest(np.asarray(polygon,np.float32),tuple(map(float,center)),True) if polygon else None
    status=(wf or fit)['status']
    if clearance is not None and clearance<fit['radius']*.9:status='low_confidence'
    return {"raw_center_px": np.asarray(center).tolist(), "radius_px": fit["radius"],
            "world_center_m": wf["center"].tolist() if wf else None,
            "radius_m": wf["radius"] if wf else None, "edge_points_px": fit["points"].tolist(),
            "covariance_px": fit["covariance"].tolist(), "covariance_world": wf["covariance"].tolist() if wf else None,
            "edge_residual_px": fit["residual_rms"], "visible_arc_fraction": fit["visible_arc_fraction"],
            "condition": (wf or fit)["condition"], "status": status,
            "surface_status":'floor_boundary' if clearance is not None and clearance<fit['radius']*.9 else 'inside_floor' if polygon else 'not_checked',
            "measurement_warning":'blurred_edge_review' if fit['residual_rms']>max(1.5,fit['radius']*.04) else None,
            "edge_strength": float(np.median(strengths)), "quality_score_kind": "heuristic_not_probability",
            "dark_face_contrast":contrast,"detector_profile":profile,
            "geometry_status": "calibration_unverified" if wf is None else "height_corrected" if height is not None and calibration.get("pose_R") is not None else "height_unverified",
            "uncertainty_kind": fit["uncertainty_kind"]}


HUES={"red":0.,"blue":115.,"yellow":28.,"green":60.}


def color_mask(hsv, color, model=None):
    model = model or {"hue":HUES[color],"hue_tolerance":14.,"min_saturation":80.,"min_value":40.}
    delta = abs((hsv[:,:,0].astype(float)-model["hue"]+90)%180-90)
    return ((delta<model["hue_tolerance"]) & (hsv[:,:,1]>=model["min_saturation"]) & (hsv[:,:,2]>=model["min_value"])).astype(np.uint8)


def learn_color(image, point, radius=3):
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    x,y=np.round(point).astype(int)
    patch=hsv[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1].reshape(-1,3)
    patch=patch[patch[:,1]>40]
    if not len(patch):
        raise ValueError("선택한 표식에 유효한 채도 픽셀이 없습니다.")
    hue=np.angle(np.mean(np.exp(2j*np.pi*patch[:,0]/180)))%(2*np.pi)*180/(2*np.pi)
    delta=abs((patch[:,0]-hue+90)%180-90)
    return {"hue":float(hue),"hue_tolerance":float(np.clip(np.quantile(delta,.95)+4,5,25)),
            "min_saturation":float(max(30,np.quantile(patch[:,1],.1)*.7)),"min_value":float(max(15,np.quantile(patch[:,2],.1)*.6))}


def marker_features(image, observation, templates, calibration, height=None):
    center=np.asarray(observation["raw_center_px"])
    radius=observation["radius_px"]
    x0,y0=np.maximum(0,np.floor(center-radius*1.2)).astype(int)
    x1,y1=np.minimum([image.shape[1],image.shape[0]],np.ceil(center+radius*1.2)).astype(int)
    hsv=cv2.cvtColor(image[y0:y1,x0:x1],cv2.COLOR_BGR2HSV)
    features={}
    for chip,(rim,inner) in COLORS.items():
        template=templates.get(chip,{})
        entry={}
        for role,color,band in [("rim",rim,(.73,1.12)),("inner",inner,(.23,.73))]:
            learned=template.get(role+"_radius_ratio")
            if learned is not None:
                band=(max(band[0],learned-.18),min(band[1],learned+.18))
            mask=color_mask(hsv,color,template.get("colors",{}).get(role))
            n,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
            blobs=[]
            for k in range(1,n):
                area=stats[k,cv2.CC_STAT_AREA]
                point=centroids[k]+[x0,y0]
                ratio=np.linalg.norm(point-center)/radius
                wp=to_world([point],calibration,height)
                delta=wp[0]-observation["world_center_m"] if wp is not None else (point-center)*[1,-1]
                if wp is not None and observation.get("radius_m"):
                    ratio=np.linalg.norm(delta)/observation["radius_m"]
                if 3<=area<=radius*radius*(.9 if role=="rim" else .2) and band[0]<ratio<band[1]:
                    blobs.append({"point_px":point.tolist(),"radius_ratio":float(ratio),"angle":float(np.arctan2(delta[1],delta[0])),
                                  "area_px":int(area),"angle_sigma_rad":float(max(.01,.6/np.linalg.norm(point-center)))})
            blobs.sort(key=lambda x:x["area_px"],reverse=True)
            entry[role]=blobs[0] if blobs else None
            entry[role+"_ambiguous"]=len(blobs)>1 and blobs[1]["area_px"]>blobs[0]["area_px"]*.6
        features[chip]=entry
    return features


def orientation(features, template):
    angles,weights,used=[],[],[]
    rim,inner=features.get("rim"),features.get("inner")
    delta=template.get("delta_inner_minus_rim_rad")
    if rim and not features.get("rim_ambiguous"):
        angles.append(rim["angle"]); weights.append(1/rim["angle_sigma_rad"]**2); used.append("rim")
    if inner and delta is not None and not features.get("inner_ambiguous"):
        angles.append(float(wrap(inner["angle"]-delta))); weights.append(1/inner["angle_sigma_rad"]**2); used.append("inner")
    if len(angles)==2 and abs(float(wrap(angles[0]-angles[1])))>max(.18,4*np.sqrt(sum(1/np.array(weights)))):
        return None,None,"relative_angle_inconsistent",[]
    if not angles:
        return None,None,"missing",[]
    z=np.sum(np.asarray(weights)*np.exp(1j*np.asarray(angles)))
    return float(np.angle(z)),float(1/np.sqrt(sum(weights))),"observed" if len(angles)==2 else "partially_observed",used


def generic_markers(image, observation, participating, calibration, height=None):
    """A colored rim patch gives an axis, not a permanent cross-video identity.

    A center sticker is recorded but never used as an angular lever arm.
    Multiple comparable rim patches are ambiguous, not silently fused.
    """
    center=np.asarray(observation['raw_center_px']);radius=observation['radius_px']
    lo=np.maximum(0,np.floor(center-radius*1.2)).astype(int)
    hi=np.minimum([image.shape[1],image.shape[0]],np.ceil(center+radius*1.2)).astype(int)
    hsv=cv2.cvtColor(image[lo[1]:hi[1],lo[0]:hi[0]],cv2.COLOR_BGR2HSV)
    # Keep hue families separate: otherwise a red painted rim touching a
    # saturated wooden floor becomes one giant "colored" component.
    blobs=[]
    for hue in range(0,180,15):
        distance=abs((hsv[:,:,0].astype(float)-hue+90)%180-90)
        mask=((distance<10)&(hsv[:,:,1]>85)&(hsv[:,:,2]>45)).astype(np.uint8)
        n,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
        for k in range(1,n):
            area=int(stats[k,cv2.CC_STAT_AREA]);point=centroids[k]+lo
            if area<3 or area>radius*radius*.4:continue
            blobs.append((area,point))
    unique=[]
    for area,point in sorted(blobs,key=lambda b:-b[0]):
        if not any(np.linalg.norm(point-q[1])<max(2,radius*.12) for q in unique):unique.append((area,point))
    roles={'rim':[],'inner':[]}
    for area,point in unique:
        delta=(point-center)*[1,-1];wp=to_world([point],calibration,height)
        ratio=np.linalg.norm(delta)/radius
        if wp is not None and observation.get('world_center_m') is not None:
            delta=wp[0]-observation['world_center_m']
            if observation.get('radius_m'):ratio=np.linalg.norm(delta)/observation['radius_m']
        if area<3:continue
        role='rim' if .70<ratio<1.15 else 'inner' if ratio<.68 else None
        if role and area<radius*radius*(.9 if role=='rim' else .5):
            roles[role].append({'point_px':point.tolist(),'radius_ratio':float(ratio),
                'area_px':area,'angle':float(np.arctan2(delta[1],delta[0])),
                'angle_sigma_rad':float(max(.01,.6/max(1,np.linalg.norm(point-center))))})
    entry={}
    for role,blobs in roles.items():
        blobs.sort(key=lambda x:x['area_px'],reverse=True)
        entry[role]=blobs[0] if blobs else None
        entry[role+'_ambiguous']=len(blobs)>1 and blobs[1]['area_px']>blobs[0]['area_px']*.6
    return {key:dict(entry) for key in participating}


def learn_template(samples, session_id, colors=None):
    valid=[s for s in samples if s.get("rim") and s.get("inner")]
    if not valid:
        raise ValueError("두 표식이 확인된 기준 관측이 필요합니다.")
    delta=np.array([float(wrap(s["inner"]["angle"]-s["rim"]["angle"])) for s in valid])
    z=np.mean(np.exp(1j*delta))
    return {"version":1,"session_id":session_id,"geometry_status":"learned_initial" if len(valid)<3 else "learned",
            "delta_inner_minus_rim_rad":float(np.angle(z)),"delta_circular_sd":float(np.sqrt(max(0.,-2*np.log(max(abs(z),1e-12))))),
            "rim_radius_ratio":float(np.median([s["rim"]["radius_ratio"] for s in valid])),
            "inner_radius_ratio":float(np.median([s["inner"]["radius_ratio"] for s in valid])),
            "sample_count":len(valid),"body_axis":"rim_direction", "colors":colors or {},
            "sticker_diameter_m":.003,"status":"user_confirmed_geometry_not_dynamic_validation"}
