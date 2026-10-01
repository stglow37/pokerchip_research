"""Simple intake orchestration. Provisional measurements never become validated fits."""
from pathlib import Path
from collections import Counter
import copy
import numpy as np
import cv2
from ..measurement.video import frames,metadata
from ..core.storage import atomic_json,file_hash,read_json
from ..core.config import ensure_chips,source_path,save_project
from ..measurement.calibration import fit_plane,calibrate_views,to_pixel
from ..measurement.vision import candidates,measure
from .pipeline import analyze,Cancelled

BOARD={'squares':[11,8],'square_m':.015,'marker_m':.011,'dictionary':'DICT_4X4_50',
       'legacy_pattern':False,'paper_mm':[200,150],
       'source':'calib.io_CHARUCO_200x150_8x11_15_11_DICT_4X4.pdf'}


def board_detector():
    b=cv2.aruco.CharucoBoard(tuple(BOARD['squares']),BOARD['square_m'],BOARD['marker_m'],
                            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    b.setLegacyPattern(False)
    return b,cv2.aruco.CharucoDetector(b)


def plane_from_board(corners,ids,base=None,image_size=None):
    board,_=board_detector();ids=np.asarray(ids).ravel();px=np.asarray(corners).reshape(-1,2)
    if len(ids)<20:raise ValueError('보정판 교차점이 20개 이상 선명하게 보여야 합니다.')
    world=board.getChessboardCorners()[ids,:2].astype(float);world[:,1]*=-1
    held=ids%4==0
    if held.sum()<4 or (~held).sum()<8:raise ValueError('보정판이 너무 많이 가려져 있습니다.')
    c=fit_plane(px[~held],world[~held],base,
        {'pixel_points':px[held].tolist(),'world_points':world[held].tolist()},
        evidence='첨부 PDF의 15 mm 격자 가정. 변환에 쓰지 않은 같은 판의 교차점으로 내부 오차 검사')
    passed=c['validation']['passed']
    c.update(status='provisional' if passed else 'pending',board=copy.deepcopy(BOARD),image_size=image_size,
        calibration_kind='automatic_same_board_holdout',absolute_scale_status='nominal_print_size_not_independently_measured',
        lens_status='estimated' if c.get('K') is not None else 'not_corrected',
        validation_scope='same_board_corner_consistency_not_independent_absolute_accuracy',
        corners_detected=len(ids),capture_mode='Samsung FHD240 slow8')
    return c


def calibrate_automatic(path,floor_confirmed=False,control=None,progress=None):
    """Final stable board segment supplies a plane ONLY with operator floor confirmation."""
    board,detector=board_detector();samples=[];views=[];features=[];last_frame=0
    anchor_image=None
    for timing,image in frames(path):
        if control:control.check()
        last_frame=timing['frame_index']
        if last_frame%6:continue
        if progress:progress({'stage':'calibrating','frame':last_frame})
        corners,ids,_,_=detector.detectBoard(image)
        if ids is None or len(ids)<20:continue
        p=corners.reshape(-1,2);size=[image.shape[1],image.shape[0]]
        entry={'frame':last_frame,'points':p.copy(),'ids':ids.ravel().copy(),'size':size}
        samples.append(entry);samples=samples[-8:];anchor_image=image.copy()
        feature=np.r_[p.mean(0)/size,p.std(0)/size]
        if len(views)<60 and (not features or min(np.linalg.norm(feature-f) for f in features)>.035):
            features.append(feature);views.append((board.getChessboardCorners()[ids.ravel()],p))
    if not samples:raise ValueError('보정판을 찾지 못했습니다. 첨부한 판 전체를 선명하게 촬영하세요.')
    anchor=samples[-1];base={};lens_reason='여러 기울기의 판 영상이 부족해 렌즈 왜곡은 보정하지 않았습니다.'
    if len(views)>=9 and np.std([f[2]/max(f[3],1e-9) for f in features])>.04:
        try:
            c=calibrate_views([v[0] for v in views],[v[1] for v in views],anchor['size'],list(range(3,len(views),4)))
            K=np.array(c['K']);w,h=anchor['size']
            if c['holdout_rms_px']<=.75 and .2*w<K[0,0]<10*w and .2*h<K[1,1]<15*h and np.isfinite(K).all():
                base=c;lens_reason='별도 영상 구간의 재투영 오차 기준 통과'
            else:lens_reason='렌즈 추정이 불안정해 적용하지 않았습니다. 평면 보정만 사용합니다.'
        except (ValueError,cv2.error):pass
    stable=[]
    for previous in reversed(samples[:-1]):
        shared,ai,bi=np.intersect1d(anchor['ids'],previous['ids'],return_indices=True)
        if len(shared)<20 or np.median(np.linalg.norm(anchor['points'][ai]-previous['points'][bi],axis=1))>1.0:break
        stable.append(previous)
    stable_ok=len(stable)>=2 and anchor['frame']-stable[-1]['frame']>=12 and last_frame-anchor['frame']<=30
    report={'source_hash':file_hash(path),'floor_confirmed':bool(floor_confirmed),'stable_end':stable_ok,
            'anchor_frame':anchor['frame'],'distinct_lens_views':len(views),'lens_note':lens_reason}
    if floor_confirmed and stable_ok:
        c=plane_from_board(anchor['points'],anchor['ids'],base,anchor['size'])
    else:
        c={**base,'H':None,'status':'pending','image_size':anchor['size'],'board':copy.deepcopy(BOARD),
           'capture_mode':'Samsung FHD240 slow8','lens_status':'estimated' if base else 'not_corrected'}
        report['action']='보정 영상 끝에 판을 실험 바닥에 평평하게 놓고 2초 이상 멈춰 촬영한 뒤 바닥 확인을 체크하세요.'
    c['automatic_report']=report
    c['reference_gray_shape']=[int(x) for x in anchor_image.shape[:2]]
    # Saved separately by caller; the source frame remains an auditable visual reference.
    return c,anchor_image


def sample_video(path,maximum=24,control=None,start=0,end=None):
    total=metadata(path).get('estimated_frames') or 0
    last=min(total-1,end) if end is not None else total-1
    indices=set(np.linspace(start,max(start,last),min(maximum,max(1,last-start+1)),dtype=int)) if total else None
    taken=0
    for timing,image in frames(path,start=start,end=end):
        if control:control.check()
        f=timing['frame_index']
        if (indices is not None and f not in indices) or (indices is None and f%15):continue
        yield timing,image
        taken+=1
        if taken>=maximum:break


def detect_count(path,project,control=None,progress=None,start=0,end=None,maximum=24):
    settings=copy.deepcopy(project['analysis']);cal=project['calibration'];samples=[];radii=[];preview=None
    # Estimate the circle search scale from the nominal 40 mm chip and board map.
    if cal.get('status') in ('verified','provisional','synthetic') and cal.get('H') is not None:
        try:
            radius=project['chips'][0].get('radius_m') or .02
            p=to_pixel([[.08,-.06],[.08+radius,-.06],[.08,-.06+radius]],cal)
            r=float(np.mean(np.linalg.norm(p[1:]-p[0],axis=1)))
            settings['radius_px']=[max(5,r*.60),min(700,r*1.55)]
        except (ValueError,cv2.error,np.linalg.LinAlgError):pass
    settings['max_candidates']=64
    for timing,image in sample_video(path,maximum=maximum,control=control,start=start,end=end):
        if progress:progress({'stage':'counting','frame':timing['frame_index']})
        proposed=candidates(image,settings['radius_px'],settings.get('roi_px'),64)
        # Nested Hough proposals of the same physical disk are NOT occluders.
        # Match the duplicate suppression already used by the frame tracker.
        found=[]
        for c in proposed:
            if not any(np.linalg.norm(c[0]-q[0])<.8*min(c[1],q[1]) for q in found):found.append(c)
        good=[]
        for i,candidate in enumerate(found):
            if control:control.check()
            try:
                # Counting uses unobstructed high-quality silhouettes. Unverified
                # proposals must not erase one another's edges as fake blockers.
                d=measure(image,candidate,{},settings)
                if d['visible_arc_fraction']>=.75 and d['edge_residual_px']<max(1.5,d['radius_px']*.035):good.append(d)
            except (ValueError,cv2.error,np.linalg.LinAlgError):pass
        unique=[]
        for d in sorted(good,key=lambda q:q['edge_residual_px']):
            if not any(np.linalg.norm(np.array(d['raw_center_px'])-q['raw_center_px'])<.7*(d['radius_px']+q['radius_px']) for q in unique):unique.append(d)
        good=unique
        from ..measurement.markers_v3 import painted_markers
        identities=[]
        for d in good:
            marks=painted_markers(image,d,[c['id'] for c in project['chips']],cal,chips=project['chips'],templates=project.get('templates'))
            unique=[k for k,m in marks.items() if m.get('identity_eligible',True) and m.get('rim') and m.get('inner') and not m.get('rim_ambiguous') and not m.get('inner_ambiguous')]
            identities.append(unique[0] if len(unique)==1 else None)
        samples.append({'frame':timing['frame_index'],'count':len(good),'marker_ids':identities,'radii_px':[d['radius_px'] for d in good],
                        'centers_px':[d['raw_center_px'] for d in good]})
        radii.extend(d['radius_px'] for d in good)
        if preview is None or len(good)>preview[0]:
            annotated=image.copy()
            for i,d in enumerate(sorted(good,key=lambda x:x['raw_center_px'][0])):
                xy=tuple(np.round(d['raw_center_px']).astype(int));r=round(d['radius_px'])
                cv2.circle(annotated,xy,r,(50,200,50),2);cv2.putText(annotated,str(i+1),(xy[0]-r,xy[1]-r),cv2.FONT_HERSHEY_SIMPLEX,.8,(20,70,240),2)
            preview=(len(good),annotated,timing['frame_index'])
    # All nominal chips have the same diameter. A small circular mark on the
    # launcher cannot set the disk scale when a repeatable larger cluster exists.
    if radii:
        seed=max(radii,key=lambda r:sum(any(.72*r<v<1.38*r for v in s['radii_px']) for s in samples))
        for s in samples:
            ids=[i for i,r in enumerate(s['radii_px']) if .72*seed<r<1.38*seed]
            s['marker_ids']=[s['marker_ids'][i] for i in ids]
            s['radii_px']=[s['radii_px'][i] for i in ids];s['centers_px']=[s['centers_px'][i] for i in ids];s['count']=len(ids)
    hist=Counter(x['count'] for x in samples);needed=max(2,int(np.ceil(len(samples)*.1)))
    supported=[n for n,k in hist.items() if n>0 and k>=needed]
    count=max(supported) if supported else max(hist,default=0)
    # Repeated DISTINCT two-color identities remain participants even when an
    # occluded launch and an early exit prevent a simultaneous maximum count.
    votes=Counter(k for sample in samples for k in set(sample['marker_ids']) if k)
    confirmed=sorted(k for k,v in votes.items() if v>=2)
    count=max(count,len(confirmed))
    if count>32:raise ValueError('32개보다 많은 원 후보가 보입니다. 분석 영역과 영상을 확인하세요.')
    support=hist.get(count,0)/max(1,len(samples))
    report={'count':count,'method':'largest_count_repeated_in_sampled_frames','samples':samples,
            'marker_identity_votes':dict(votes),'confirmed_marker_ids':confirmed,
            'identity_count_evidence':'at_least_two_sampled_frames_per_two_color_identity',
            'support_fraction':support,'status':'stable_proposal' if count>0 and support>=.75 else 'review_required',
            'note':'표본 프레임에서 보이는 칩 개수의 제안입니다. 가려지거나 화면 밖에 있는 칩 수는 알 수 없습니다.',
            'radius_range_px':settings['radius_px'],'preview_frame':preview[2] if preview else None}
    radii=[r for sample in samples if sample['count']==count for r in sample['radii_px']]
    if radii:
        lo,hi=np.quantile(radii,[.1,.9]);report['radius_range_px']=[max(5,float(lo*.78)),float(hi*1.25)]
    selected=next((s for s in samples if s['count']==count),None) if count else None
    if selected:
        from ..measurement.video import frame_at
        _,annotated=frame_at(path,selected['frame']);report['preview_frame']=selected['frame']
        for i,(xy,r) in enumerate(zip(selected['centers_px'],selected['radii_px'])):
            xy=tuple(np.round(xy).astype(int));cv2.circle(annotated,xy,round(r),(50,200,50),2)
            cv2.putText(annotated,str(i+1),(xy[0]-round(r),xy[1]-round(r)),cv2.FONT_HERSHEY_SIMPLEX,.8,(20,70,240),2)
        preview=(count,annotated,selected['frame'])
    report['sampling_maximum']=maximum
    # A short free-flight interval can fall between the initial 24 samples.
    # Retry the same measurement gates with denser temporal coverage; never
    # turn a missing disk into an assumed participant or relax edge quality.
    if count==0 and maximum==24:
        dense,dense_preview=detect_count(path,project,control,progress,start,end,maximum=192)
        dense['sampling_retry']={'reason':'zero_count_in_initial_samples','initial_samples':len(samples),'initial_count':0}
        return dense,dense_preview
    return report,preview[1] if preview else None


def run_automatic(folder,project,control,progress=None,ids=None):
    """One immutable worker snapshot, failure-isolated videos, automatic public export."""
    from .delivery import publish_results
    folder=Path(folder);p=copy.deepcopy(project);setup=p.setdefault('quick_setup',{})
    emit=progress or (lambda value:None);results=[];issues=[]
    from ..measurement.selection import require_start
    from .batch_progress import BatchProgress
    selected=[e for e in p['experiments'] if ids is None or e['id'] in ids]
    for e in selected: require_start(p,e)
    reporter=BatchProgress(emit,len(selected))
    if setup.get('calibration_video'):
        source=Path(setup['calibration_video'])
        if not source.is_absolute():source=folder/source
        try:
            control.check();digest=file_hash(source)
            cache=p['calibration'].get('automatic_report',{})
            if cache.get('source_hash')!=digest or cache.get('floor_confirmed')!=setup.get('floor_confirmed',False):
                cal,img=calibrate_automatic(source,setup.get('floor_confirmed',False),control,emit)
                p['calibration']=cal
                dest=folder/'calibration';dest.mkdir(exist_ok=True)
                atomic_json(dest/'calibration.json',cal)
                cv2.imencode('.png',img)[1].tofile(str(dest/'reference.png'))
        except Cancelled:
            save_project(folder,p)
            return {'project':p,'results':[],'output':str(publish_results(folder,p,['보정 중 사용자가 중단했습니다.'])),
                    'issues':['보정 중단'],'cancelled':True}
        except Exception as exc:
            p['calibration']={'status':'pending','H':None,'K':None,'distortion':None,'error_message':str(exc)}
            issues.append('보정 실패: '+str(exc))
    for video_index,e in enumerate(selected,1):
        reporter.begin(video_index,e,0)
        try:
            control.check()
            source=source_path(folder,e)
            require_start(p,e,file_hash(source))
            reporter.begin(video_index,e,metadata(source).get('estimated_frames') or 0)
            video_emit=reporter.emit
            working=copy.deepcopy(p)
            from ..measurement.gridcheck import floor_grid_check
            from ..measurement.video import frame_at
            from ..measurement.scene import video_floor_scene,PITCHES
            scene=video_floor_scene(source,p['calibration'],setup.get('floor_grid_pitches_m',PITCHES),
                e['interval'][0],control,video_emit)
            if e.get('manual_plane_locked') and e.get('calibration',{}).get('H') is not None:
                # Explicit user plane survives an automatic reanalysis. Lens/scene
                # findings remain evidence; they must not silently replace clicks.
                scene={**scene,'status':'provisional','calibration':copy.deepcopy(e['calibration']),
                       'scope':'user_locked_manual_plane','pitch_xy_m':None}
            e['floor_scene']={k:v for k,v in scene.items() if k!='calibration'}
            scene_settings={}
            if scene['status']=='provisional':
                e['calibration']=scene['calibration'];working['calibration']=scene['calibration']
                scene_settings={k:scene[k] for k in ('roi_px','floor_polygon_px') if k in scene}
                working['analysis'].update(scene_settings)
            elif p['calibration'].get('status')!='synthetic':
                local=copy.deepcopy(p['calibration']);local.update(H=None,status='pending',plane_reason=scene.get('reason'))
                e['calibration']=local;working['calibration']=local
            grid={'status':scene['status'],'scope':scene.get('scope'),'pitch_xy_m':scene.get('pitch_xy_m')}
            e['floor_grid_check']=grid
            if grid['status']=='scale_mismatch':
                local=copy.deepcopy(p['calibration']);local.update(status='pending',scale_mismatch=grid)
                e['calibration']=local;working['calibration']=local
            elif e.get('calibration',{}).get('scale_mismatch'):
                e.pop('calibration')
            e['input_metadata']=metadata(source)
            if e.get('count_mode','manual')=='auto':
                proposal,img=detect_count(source,working,control,video_emit,*e['interval']);e['count_proposal']=proposal
                dest=folder/'intake'/e['id'];dest.mkdir(parents=True,exist_ok=True)
                atomic_json(dest/'count.json',proposal)
                if img is not None:cv2.imencode('.jpg',img)[1].tofile(str(dest/'count_preview.jpg'))
                if proposal['count']<1:raise ValueError('칩을 찾지 못했습니다. 칩 개수를 직접 지정하거나 밝기·반지름 범위를 확인하세요.')
                available=ensure_chips(p,proposal['count'])
                confirmed=proposal.get('confirmed_marker_ids',[])
                e['participating_chip_ids']=confirmed+[k for k in available if k not in confirmed][:proposal['count']-len(confirmed)]
                e['identity_selection']='repeated_marker_ids_then_unresolved_slots'
                e['analysis']={**copy.deepcopy(p['analysis']),**scene_settings,'radius_px':proposal['radius_range_px']}
            # spatial IDs mean track numbers in this video, never physical labels across trials.
            e.setdefault('analysis',copy.deepcopy(p['analysis']))
            e['analysis'].update(scene_settings)
            if e.get('quick_workflow',True):
                e['analysis'].update(identity_mode='painted_tracks',redetect_every=1,edge_relative_limit=.065,collision_fit_degree=1,max_candidates=max(12,len(e['participating_chip_ids'])*2),
                    omega_bound_rad_s=setup.get('omega_bound_rad_s',500.))
            result=analyze(folder,p,e,control,video_emit)
            e.update(status='complete',last_run=str(Path(result['run']).relative_to(folder)),source_hash=result['source_hash'])
            if read_json(Path(result['run'])/'export/quality.json')['observation_rows']==0:
                raise ValueError('위치를 한 번도 찾지 못했습니다. 개수·영상 반지름 범위·조명을 확인하세요. 빈 데이터를 성공으로 처리하지 않습니다.')
            e.pop('failure_reason',None);result['experiment_id']=e['id'];results.append(result);video_emit(result)
        except Cancelled:
            e['status']='cancelled';results.append({'experiment_id':e['id'],'status':'cancelled'});break
        except Exception as exc:
            e.update(status='failed',failure_reason=str(exc));r={'experiment_id':e['id'],'status':'failed','reason':str(exc)}
            results.append(r);reporter.emit(r)
        save_project(folder,p)
    save_project(folder,p)
    out=publish_results(folder,p,issues)
    return {'project':p,'results':results,'output':str(out),'issues':issues,'cancelled':control.cancelled.is_set()}
