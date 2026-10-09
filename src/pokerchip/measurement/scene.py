"""Per-video rectangular floor lattice. Never infer metric scale from chip size."""
import copy
import cv2
import numpy as np
from .calibration import undistort, transform

PITCHES=(.405/18,.430/18)


def video_floor_scene(path, calibration, pitches=PITCHES, start=0, control=None, progress=None):
    """Check several frames and require agreement of local metric bases.

    Lattice origins may differ by whole cells. Compare derivatives, not origin.
    A small residual alone is insufficient to choose a plane.
    """
    from .video import frames, metadata
    total = metadata(path).get('estimated_frames') or start + 151
    # Early frames can be occluded by the launcher or hands. Later image-only
    # samples are allowed for geometry, while the same consensus/error gates
    # remain in force. No measured motion or fitted coefficient chooses a map.
    later = tuple(int((total-1)*q) for q in (.20,.35,.50,.65,.80,.95))
    indices = sorted({f for f in (0, 12, 30, 60, 90, 150, start, start+12,*later)
                      if 0 <= f < total})
    accepted, attempts = [], []
    for timing, image in frames(path, end=max(indices, default=0)):
        if control: control.check()
        f = timing['frame_index']
        if f not in indices: continue
        if progress: progress({'stage': 'geometry', 'frame': f})
        scene = floor_scene(image, calibration, pitches)
        attempts.append(dict(frame=f, status=scene['status'], reason=scene.get('reason'),
                             holdout_rmse_m=scene.get('holdout_rmse_m')))
        if scene['status'] != 'provisional': continue
        h,w = image.shape[:2]
        pts = undistort([[w/2,h/2],[w/2+100,h/2],[w/2,h/2+100]], scene['calibration'])
        metric = transform(pts, np.asarray(scene['calibration']['H']))
        basis = (metric[1:]-metric[0]).ravel()
        accepted.append((scene, f, basis))
        clusters = [[b for b in accepted if a[0]['long_direction']==b[0]['long_direction']
                     and np.linalg.norm(a[2]-b[2])/max(np.linalg.norm(a[2]),1e-9)<.03] for a in accepted]
        group = max(clusters, key=len)
        if len(group) >= 3: break
    if not accepted:
        return dict(status='unmeasurable', reason='여러 프레임에서 격자를 확인하지 못했습니다.', attempts=attempts)
    clusters = [[b for b in accepted if a[0]['long_direction']==b[0]['long_direction']
                 and np.linalg.norm(a[2]-b[2])/max(np.linalg.norm(a[2]),1e-9)<.03] for a in accepted]
    group = max(clusters, key=len)
    if len(group)<2:
        return dict(status='unmeasurable', reason='격자 변환이 두 프레임 이상에서 일치하지 않습니다.', attempts=attempts)
    median = np.median([s[2] for s in group], axis=0)
    selected = min(group, key=lambda s: np.linalg.norm(s[2]-median))
    result = copy.deepcopy(selected[0])
    result.update(selected_frame=selected[1], consensus_frames=[s[1] for s in group], attempts=attempts,
                  method='multi_frame_metric_basis_consensus')
    result['calibration']['selection_evidence'] = dict(frame=selected[1], consensus_frames=result['consensus_frames'])
    return result

def floor_scene(image, calibration, pitches=PITCHES):
    short,long=sorted(map(float,pitches))
    if not 0<short<long:raise ValueError('바닥 격자의 짧은 변과 긴 변은 서로 다른 양수여야 합니다.')
    h,w=image.shape[:2]; hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    mask=((hsv[:,:,0]>8)&(hsv[:,:,0]<42)&(hsv[:,:,1]>25)&(hsv[:,:,1]<185)&(hsv[:,:,2]>90)).astype('uint8')*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((19,19),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return {'status':'unmeasurable','reason':'바닥 영역을 찾지 못했습니다.'}
    cnt=max(contours,key=cv2.contourArea)
    if cv2.contourArea(cnt)<h*w*.15:return {'status':'unmeasurable','reason':'바둑판이 충분히 크게 보이지 않습니다.'}
    x,y,bw,bh=cv2.boundingRect(cnt)
    boardmask=np.zeros((h,w),np.uint8);cv2.drawContours(boardmask,[cv2.convexHull(cnt)],-1,255,-1)
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    edge=cv2.Canny(gray,50,130);edge[boardmask==0]=0
    lines=cv2.HoughLinesP(edge,1,np.pi/1800,85,minLineLength=min(bw,bh)*.30,maxLineGap=30)
    if lines is None:return {'status':'unmeasurable','reason':'긴 격자 선 부족'}
    ends=undistort(lines.reshape(-1,2),calibration).reshape(-1,2,2)
    families=[]
    for vertical in (True,False):
        entries=[]
        for p,q in ends:
            d=q-p
            independent=1 if vertical else 0;dependent=1-independent
            if abs(d[independent])<4*abs(d[dependent]):continue
            slope=d[dependent]/d[independent];intercept=p[dependent]-slope*p[independent]
            # Offset at the image middle is stable under small slope variations.
            mid=(h if vertical else w)/2
            entries.append((intercept+slope*mid,slope,np.linalg.norm(d)))
        groups=[]
        for item in sorted(entries):
            if groups and abs(item[0]-np.average([z[0] for z in groups[-1]],weights=[z[2] for z in groups[-1]]))<7:groups[-1].append(item)
            else:groups.append([item])
        if len(groups)<10:return {'status':'unmeasurable','reason':'격자 방향별 최소 10개 선 필요'}
        vals=np.array([[np.average([v[k] for v in g],weights=[z[2] for z in g]) for k in (0,1)] for g in groups])
        gaps=np.diff(vals[:,0]);usable=gaps[(gaps>15)&(gaps<min(bw,bh)/8)]
        if len(usable)<8:return {'status':'unmeasurable','reason':'격자 간격을 확정할 수 없습니다.'}
        pitch=float(np.median(usable));best=None
        for seed in vals[:,0]:
            index=np.rint((vals[:,0]-seed)/pitch).astype(int);err=abs(vals[:,0]-seed-index*pitch);ok=err<pitch*.16
            if best is None or ok.sum()>best[0]:best=(ok.sum(),ok,index)
        vals=vals[best[1]];index=best[2][best[1]];index-=index.min()
        if len(vals)<10 or index.max()>20:return {'status':'unmeasurable','reason':'격자 선 배열 불일치'}
        families.append((vals,index,pitch))
    ratio=max(families[0][2],families[1][2])/min(families[0][2],families[1][2])
    # Near-overhead assignment only. Strong perspective cannot determine which
    # physical side is longer from apparent lengths without an external cue.
    if not 1.025<ratio<1.12:return {'status':'orientation_ambiguous','reason':'긴 방향 판별이 불확실합니다. 수직 촬영 또는 수동 평면 보정을 사용하세요.','apparent_ratio':ratio}
    xp,yp=(long,short) if families[0][2]>families[1][2] else (short,long)
    pixels=[];world=[];line_ids=[]
    for (offx,sx),ix in zip(families[0][0],families[0][1]):
        bx=offx-sx*h/2
        for (offy,sy),iy in zip(families[1][0],families[1][1]):
            by=offy-sy*w/2
            p=np.linalg.solve([[1,-sx],[-sy,1]],[bx,by]);pixels.append(p);world.append([ix*xp,-iy*yp]);line_ids.append([ix,iy])
    pixels=np.array(pixels);world=np.array(world);hold=np.arange(len(world))%4==0
    H,inliers=cv2.findHomography(pixels[~hold],world[~hold],cv2.RANSAC,.001)
    if H is None:return {'status':'unmeasurable','reason':'평면 변환 실패'}
    # Reject whole false lines using TRAIN intersections only; held-out points
    # remain held out. Launcher/paper borders must not become grid lines.
    ids=np.array(line_ids);error=np.linalg.norm(transform(pixels,H)-world,axis=1);valid=np.ones(len(ids),bool)
    for axis in (0,1):
        for key in np.unique(ids[:,axis]):
            train=(ids[:,axis]==key)&~hold
            if train.any() and np.median(error[train])>.00075:valid[ids[:,axis]==key]=False
    counts=[len(np.unique(ids[valid,k])) for k in (0,1)]
    if min(counts)<10:return {'status':'unmeasurable','reason':'정확한 격자 선 부족'}
    H,inliers=cv2.findHomography(pixels[valid&~hold],world[valid&~hold],cv2.RANSAC,.0007)
    hold=hold&valid
    if H is None or hold.sum()<10:return {'status':'unmeasurable','reason':'격자 검사용 교점 부족'}
    rmse=float(np.sqrt(np.mean(np.sum((transform(pixels[hold],H)-world[hold])**2,axis=1))))
    if not np.isfinite(rmse) or rmse>.001:return {'status':'unmeasurable','reason':'격자 내부 잔차가 1 mm를 넘습니다.','holdout_rmse_m':rmse}
    cal=copy.deepcopy(calibration);cal.update(H=H.tolist(),status='provisional',pose_R=None,pose_t=None,
        image_size=[w,h],calibration_kind='per_video_rectangular_grid',holdout_rmse_m=rmse,
        validation_scope='same_grid_consistency_not_independent_accuracy',
        absolute_scale_status='user_measured_rectangular_grid',floor_pitch_xy_m=[xp,yp])
    # Pose is intentionally cleared: previous camera extrinsics are not reusable.
    return {'status':'provisional','calibration':cal,'roi_px':[x,y,x+bw,y+bh],
        'floor_polygon_px':cv2.convexHull(cnt).reshape(-1,2).tolist(),'pitch_xy_m':[xp,yp],
        'long_direction':'image_horizontal' if xp>yp else 'image_vertical',
        'line_counts':counts,'holdout_rmse_m':rmse,
        'scope':'near_overhead_rectangular_lattice; no automatic accuracy certification'}
