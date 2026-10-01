"""Small automatic visual receipt using actual detections, never predictions."""
import cv2
import numpy as np
from ..core.storage import Records
from ..measurement.video import frames

def save_sheet(source,run):
    with Records(run/'records.sqlite',readonly=True) as db:
        indices=[r['frame_index'] for r in db.rows('frames')];n=len(indices);events=list(db.rows('events'));byframe={}
        if not indices:return
        first,last=indices[0],indices[-1]
        target=set(indices[i] for i in sorted({0,min(1,n-1),min(4,n-1),min(12,n-1),n//3,n//2,n-1}))
        for e in events[:2]:target.update([max(first,e['closest_frame']-3),e['closest_frame'],min(last,e['closest_frame']+3)])
        target=sorted(target)[:12]
        for r in db.rows('observations'):
            if r['frame_index'] in target:byframe.setdefault(r['frame_index'],[]).append(r)
    tiles=[]
    for timing,im in frames(source,start=first,end=max(target)):
        f=timing['frame_index']
        if f not in target:continue
        for r in byframe.get(f,[]):
            xy=tuple(np.rint(r['raw_center_px']).astype(int));radius=round(r['radius_px']);color=(20,190,20) if not r.get('measurement_warning') else (0,170,255)
            cv2.circle(im,xy,radius,color,2);cv2.putText(im,r['chip_id'],(xy[0]-radius,xy[1]-radius-8),cv2.FONT_HERSHEY_SIMPLEX,.65,color,2)
        h,w=im.shape[:2];scale=min(270/w,430/h);im=cv2.resize(im,None,fx=scale,fy=scale)
        tile=np.full((460,270,3),245,np.uint8);tile[25:25+im.shape[0],:im.shape[1]]=im
        cv2.putText(tile,f'Frame {f}: {len(byframe.get(f,[]))} observed',(5,18),cv2.FONT_HERSHEY_SIMPLEX,.46,(20,30,40),1);tiles.append(tile)
    while len(tiles)%4:tiles.append(np.full((460,270,3),245,np.uint8))
    sheet=np.concatenate([np.concatenate(tiles[i:i+4],axis=1) for i in range(0,len(tiles),4)],axis=0)
    cv2.imencode('.jpg',sheet)[1].tofile(str(run/'export/검출_확인.jpg'))
