"""Painted rim + inner spot; color identity is evidence, never a forced label."""
import cv2
import numpy as np
from .vision import color_mask
from .calibration import to_world
from ..core.config import COLORS

def painted_markers(image,observation,participating,calibration,height=None,chips=None,templates=None):
    center=np.asarray(observation['raw_center_px']);r=observation['radius_px']
    lo=np.maximum(0,np.floor(center-r*1.2)).astype(int);hi=np.minimum(image.shape[1::-1],np.ceil(center+r*1.2)).astype(int)
    hsv=cv2.cvtColor(image[lo[1]:hi[1],lo[0]:hi[0]],cv2.COLOR_BGR2HSV)
    yy,xx=np.mgrid[lo[1]:hi[1],lo[0]:hi[0]];rad=np.hypot(xx-center[0],yy-center[1])/r
    result={}
    definitions={c['id']:c for c in chips or []}
    templates=templates or {}
    for key in participating:
        c=definitions.get(key)
        colors=(c.get('rim_color','auto'),c.get('inner_color','auto')) if c else COLORS.get(key)
        if colors is None or 'auto' in colors:
            from .vision import generic_markers
            f=generic_markers(image,observation,[key],calibration,height)[key]
            f['identity_eligible']=False
            result[key]=f
            continue
        entry={}
        for role,color,limits in [('rim',colors[0],(.68,1.12)),('inner',colors[1],(0.,.65))]:
            hue={'red':0.,'blue':115.,'yellow':28.,'green':60.}[color]
            model=dict(hue=hue,hue_tolerance=16.,min_saturation=125.,min_value=95. if color=='blue' else 65.)
            model.update(templates.get(key,{}).get('colors',{}).get(role,{}) or {})
            mask=color_mask(hsv,color,model)*((rad>=limits[0])&(rad<limits[1])).astype('uint8')
            n,labels,stats,cent=cv2.connectedComponentsWithStats(mask);blobs=[]
            for k in range(1,n):
                area=int(stats[k,cv2.CC_STAT_AREA])
                if not max(5,r*r*.002)<area<r*r*.4:continue
                point=cent[k]+lo;delta=(point-center)*[1,-1];wp=to_world([center,point],calibration,height)
                if wp is not None:delta=wp[1]-wp[0]
                blobs.append(dict(point_px=point.tolist(),area_px=area,radius_ratio=float(np.linalg.norm(point-center)/r),
                    angle=float(np.arctan2(delta[1],delta[0])),angle_sigma_rad=float(max(.01,.7/max(1,np.linalg.norm(point-center))))))
            blobs.sort(key=lambda b:-b['area_px']);entry[role]=blobs[0] if blobs else None
            entry[role+'_ambiguous']=len(blobs)>1 and blobs[1]['area_px']>.5*blobs[0]['area_px']
        result[key]=entry
    return result
