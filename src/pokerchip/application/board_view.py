"""Auditable trajectory context on the actual board; no invented star positions."""
from pathlib import Path
import cv2
import numpy as np
from ..core.storage import Records,read_json,atomic_json
from ..measurement.video import frame_at
from ..measurement.calibration import to_world,to_pixel


def save_board_view(source,run):
    run=Path(run);exp=read_json(run/'experiment.json');cfg=read_json(run/'effective_settings.json')
    timing,image=frame_at(source,exp['interval'][0]);cal=cfg['calibration']
    with Records(run/'records.sqlite',readonly=True) as db:
        rows=[r for r in db.rows('manual') if r.get('status') not in ('missing','outside_interval')]
    colors=[(60,80,245),(240,170,30),(70,205,60),(200,60,200)]
    original=image.copy()
    for i,key in enumerate(sorted({r['chip_id'] for r in rows})):
        for row in rows:
            if row['chip_id']==key:cv2.circle(original,tuple(np.round(row['raw_center_px']).astype(int)),2,colors[i%len(colors)],-1)
    cv2.putText(original,f"Source frame {timing['frame_index']} | observed centers | pixel coordinates",(18,30),0,.6,(20,20,235),2)
    cv2.imencode('.jpg',original)[1].tofile(str(run/'export/board_trajectory.jpg'))
    details={'source_frame':timing['frame_index'],'background':'single_original_frame_not_composite',
        'grid_and_stars':'visible_original_image_only','coordinate_origin':'per_video_calibration',
        'geometry_status':cal.get('status'),'absolute_accuracy':'not_established_by_overlay'}
    if cal.get('H') is not None and cal.get('status') in ('provisional','verified','synthetic'):
        polygon=cfg['analysis'].get('floor_polygon_px') or [[0,0],[image.shape[1]-1,0],[image.shape[1]-1,image.shape[0]-1],[0,image.shape[0]-1]]
        world=to_world(polygon,cal);lo=world.min(0);hi=world.max(0);extent=hi-lo
        if np.isfinite(extent).all() and np.all(extent>0) and np.max(extent)<5:
            scale=min(2400.,1400/float(np.max(extent)));size=np.maximum(2,np.ceil(extent*scale).astype(int))
            yy,xx=np.mgrid[:size[1],:size[0]]
            coords=np.column_stack([lo[0]+xx.ravel()/scale,hi[1]-yy.ravel()/scale])
            px=to_pixel(coords,cal).reshape(size[1],size[0],2)
            bird=cv2.remap(image,px[:,:,0].astype('float32'),px[:,:,1].astype('float32'),cv2.INTER_LINEAR)
            for i,key in enumerate(sorted({r['chip_id'] for r in rows})):
                for row in rows:
                    if row['chip_id']!=key or row.get('world_center_m') is None:continue
                    x,y=row['world_center_m'];point=(round((x-lo[0])*scale),round((hi[1]-y)*scale))
                    cv2.circle(bird,point,2,colors[i%len(colors)],-1)
            bar=round(.05*scale);cv2.line(bird,(20,30),(20+bar,30),(0,0,240),3)
            cv2.putText(bird,'50 mm (calibration scale)',(20,55),0,.5,(0,0,240),1)
            cv2.imencode('.jpg',bird)[1].tofile(str(run/'export/board_metric_trajectory.jpg'))
            details.update(meters_per_pixel=1/scale,world_bounds=[lo.tolist(),hi.tolist()])
    atomic_json(run/'export/board_view.json',details)
