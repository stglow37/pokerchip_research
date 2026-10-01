"""One observation renderer shared by review, exports and validation images."""
import cv2
import numpy as np


def draw_observation(image,row,markers=True):
    if row.get('status') in ('outside_interval','missing'):return
    c=tuple(np.round(row['raw_center_px']).astype(int));r=round(row['radius_px'])
    color=(50,200,70) if row.get('status')=='observed' else (30,175,255)
    boundary=row.get('projected_boundary_px')
    if boundary is not None:
        cv2.polylines(image,[np.round(boundary).astype(np.int32)],True,color,2,cv2.LINE_AA)
    else:cv2.circle(image,c,r,color,2,cv2.LINE_AA)
    cv2.drawMarker(image,c,color,cv2.MARKER_CROSS,8,1)
    cv2.putText(image,row.get('chip_id','chip'),(c[0]-r,c[1]-r-5),0,.55,color,2)
    entry=row.get('markers',{}).get(row.get('chip_id'),{})
    if markers:
        for role,mark_color in [('rim',(30,220,255)),('inner',(255,170,60))]:
            mark=entry.get(role)
            if not mark or not mark.get('point_px'):continue
            point=tuple(np.round(mark['point_px']).astype(int))
            cv2.drawMarker(image,point,mark_color,cv2.MARKER_TILTED_CROSS if entry.get(role+'_ambiguous') else cv2.MARKER_CROSS,14,2)
            cv2.line(image,c,point,mark_color,1,cv2.LINE_AA)
    status='angle OK' if row.get('theta_wrapped_rad') is not None else 'angle missing'
    cv2.putText(image,status,(c[0]-r,c[1]+r+18),0,.4,(220,220,220),1)
