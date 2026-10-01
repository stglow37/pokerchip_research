"""Coarse check of user-measured floor pitch; never invent a plane from line spacing."""
import cv2
import numpy as np
from .calibration import to_world


def floor_grid_check(image,profile,pitch_m=.429/18):
    result={'expected_pitch_m':pitch_m,'status':'unmeasurable','scope':'coarse_floor_scale_check_not_calibration_accuracy'}
    if profile.get('H') is None or profile.get('status') not in ('verified','synthetic','provisional'):return result
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    lines=cv2.HoughLinesP(cv2.Canny(gray,60,150),1,np.pi/720,70,minLineLength=max(60,image.shape[1]//12),maxLineGap=15)
    if lines is None or len(lines)<12:return result
    ends=to_world(lines.reshape(-1,2),profile)
    if ends is None:return result
    ends=ends.reshape(-1,2,2);delta=ends[:,1]-ends[:,0];length=np.linalg.norm(delta,axis=1)
    angle=np.arctan2(delta[:,1],delta[:,0])%np.pi
    hist,bins=np.histogram(angle,bins=90,range=(0,np.pi),weights=length)
    axis=(bins[np.argmax(hist)]+bins[np.argmax(hist)+1])/2
    estimates=[]
    for a in (axis,(axis+np.pi/2)%np.pi):
        distance=abs((angle-a+np.pi/2)%np.pi-np.pi/2)
        good=distance<np.deg2rad(4)
        offsets=np.sort(ends[good].mean(axis=1)@np.array([-np.sin(a),np.cos(a)]))
        clusters=[]
        for offset in offsets:
            if clusters and abs(offset-np.mean(clusters[-1]))<pitch_m*.12:clusters[-1].append(offset)
            else:clusters.append([offset])
        if len(clusters)<6:continue
        gap=np.diff([np.mean(c) for c in clusters]);close=gap[(gap>.6*pitch_m)&(gap<1.4*pitch_m)]
        if len(close)<5:continue
        med=float(np.median(close));mad=float(np.median(abs(close-med)))
        if mad/med>.07:continue
        estimates.append({'pitch_m':med,'intervals':len(close),'relative_error':abs(med/pitch_m-1)})
    result['directions']=estimates
    if len(estimates)==2:
        err=max(x['relative_error'] for x in estimates);result['max_relative_error']=err
        result['status']='consistent' if err<=.08 else 'scale_mismatch'
    return result
