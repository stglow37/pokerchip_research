"""Image-only automatic intervals. No force law or fitted coefficient input.

Automatic application permits exploratory measurement, not a claim that release
was independently verified. Ambiguities remain in the saved evidence and GUI.
"""
import copy
from pathlib import Path
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from ..core.storage import digest, file_hash, atomic_json, read_json, stamp
from ..measurement.video import frames, metadata
from ..measurement.vision import candidates, measure

ALGORITHM='image_motion_circle_recovery_v5_4'


def refine_start(path,proposal,settings,control=None):
    """Full-resolution adjacent frames refine the coarse search, never model fit."""
    if not proposal.get('tracks'):return
    target=min(proposal['tracks'],key=lambda r:r['first_motion'])
    coarse=proposal['global']['start'];track=proposal['evidence_tracks'][target['track']]
    anchor=min(track,key=lambda r:abs(r['frame']-coarse));center=np.array(anchor['center']);radius=anchor['radius']
    evidence=[]
    for timing,image in frames(path,start=max(0,coarse-16),end=coarse+16):
        if control:control.check()
        f=timing['frame_index'];det=[]
        for c in candidates(image,[max(5,radius*.78),radius*1.25],settings.get('roi_px'),16):
            if np.linalg.norm(c[0]-center)>radius*6:continue
            try:
                d=measure(image,c,{},settings)
                if d['status']=='observed' and d['visible_arc_fraction']>=.85:det.append(d)
            except (ValueError,cv2.error,np.linalg.LinAlgError):pass
        d=min(det,key=lambda d:np.linalg.norm(np.array(d['raw_center_px'])-center)) if det else None
        evidence.append({'frame':f,'good':d is not None,'center':d['raw_center_px'] if d else None,
            'residual_px':d['edge_residual_px'] if d else None})
    for i,row in enumerate(evidence):
        window=evidence[i:i+10];good=[r for r in window if r['good']]
        if not row['good'] or len(window)<10 or len(good)<8:continue
        if np.linalg.norm(np.array(good[-1]['center'])-good[0]['center'])<radius*.2:continue
        # Do not accept a separate static object as a release boundary.
        displacement=np.diff([r['center'] for r in good],axis=0)
        lengths=np.linalg.norm(displacement,axis=1)
        direction=np.linalg.norm(np.sum(displacement,axis=0))/max(sum(lengths),1e-9)
        if direction<.85:continue
        proposal['global']['start']=row['frame'];break
    proposal['fine_start_evidence']=evidence
    proposal['global']['coarse_start']=coarse


def propose_from_tracks(tracks, count, total, stride=4, fps=240.):
    """Return intervals from persistent observed motion, with explicit evidence.

    Motion is measured in radius units and physical time. Missing observations
    split tracks; stationary target disks do not delay the launched disk.
    """
    summaries=[]
    for key,rows in tracks.items():
        rows=sorted(rows,key=lambda r:r['frame'])
        if len(rows)<5:continue
        xy=np.array([r['center'] for r in rows]);rad=float(np.median([r['radius'] for r in rows]))
        ff=np.array([r['frame'] for r in rows]);dt=np.diff([r.get('physical_time_s',r['frame']/fps) for r in rows])
        step=np.linalg.norm(np.diff(xy,axis=0),axis=1)/max(rad,1.)
        speed=step/np.maximum(dt,1e-9)
        valid=(np.diff(ff)<=stride*2)
        moving=(speed>1.2)&(step>.035)&valid
        starts=[i for i in range(len(moving)-2) if moving[i:i+3].all()]
        if not starts:continue
        i=starts[0];first=rows[i]['frame']
        # Require a stable full silhouette and at least three movement samples.
        # A round disk can still touch a launcher: this is supporting evidence.
        window=rows[i:i+max(3,int(np.ceil(.05*fps/stride)))];good=sum(r['coverage']>=.85 and r['residual']/r['radius']<.04 for r in window)/len(window)
        speeds=speed[i:i+max(3,int(np.ceil(.05*fps/stride)))]
        rising=len(speeds)>2 and speeds[-1]>speeds[0]*1.5+1.
        motion_ids=np.flatnonzero(moving)
        last=rows[int(motion_ids[-1])+1]['frame']
        # Keep a post-motion tail for rotation and stop verification, never
        # assume unobserved rotation is zero. Analysis end is last visibility.
        end=rows[-1]['frame']
        summaries.append({'track':key,'first_motion':first,'last_motion':last,'last_visible':end,
            'start':first,'end':end,'circle_good_fraction':good,'continued_acceleration_suspected':bool(rising),
            'recovery_observed':bool(i==0 or rows[max(0,i-1)]['coverage']<.85),
            'visible_frames':[r['frame'] for r in rows],
            'speed_radius_s':speeds.tolist(),'reason':'persistent_observed_motion'})
    if not summaries:
        return {'status':'review_required','global':{'start':0,'end':max(0,total-1),'confidence':'low'},
                'tracks':[],'warnings':['지속 이동을 확인하지 못했습니다. 전체 영상 계측 후 시작 장면을 확인하세요.']}
    launch=min(summaries,key=lambda s:s['first_motion'])
    start=max(0,launch['start']);end=min(total-1,max(s['end'] for s in summaries)+stride)
    warnings=['자동 구간은 영상 관측에 의한 제안이며 외력 해제의 독립 정답이 아닙니다.']
    confidence='medium'
    if launch['continued_acceleration_suspected']:
        warnings.append('시작 후보 뒤에도 속도 증가가 보입니다. 발사 종료 장면 확인이 필요합니다.');confidence='low'
    if launch['circle_good_fraction']<.8:
        warnings.append('시작 후보의 원 윤곽이 불안정합니다.');confidence='low'
    return {'status':'proposed','global':{'start':start,'end':max(start,end),'confidence':confidence,
            'alternative_starts':[max(0,start-stride),start+stride],'terminal_reason':'last_observed_disk'},
            'tracks':summaries,'warnings':warnings,'count':count,
            'release_verified':False,'coefficient_scope':'exploratory_until_release_review'}


def propose_interval(path,project,experiment,folder,control=None,progress=None):
    source=file_hash(path);settings=copy.deepcopy(project['analysis']);settings.update(experiment.get('analysis',{}))
    from ..measurement.scene import video_floor_scene,PITCHES
    scene=video_floor_scene(path,project['calibration'],project.get('quick_setup',{}).get('floor_grid_pitches_m',PITCHES),0,control,progress)
    if scene.get('status')=='provisional':
        settings.update({k:scene[k] for k in ('roi_px','floor_polygon_px') if k in scene})
        from ..measurement.calibration import to_world,to_pixel
        roi=settings['roi_px'];center=np.array([(roi[0]+roi[2])/2,(roi[1]+roi[3])/2])
        wc=to_world([center],scene['calibration'])[0];r=project['chips'][0]['radius_m']
        points=to_pixel(wc+np.array([[r,0],[0,r],[-r,0],[0,-r]]),scene['calibration'])
        rp=np.median(np.linalg.norm(points-center,axis=1));settings['radius_px']=[max(5,float(rp*.7)),float(rp*1.35)]
    key=digest({'source':source,'algorithm':ALGORITHM,'settings':settings,
        'code':{str(p.name):file_hash(p) for p in [Path(__file__),Path(__file__).parents[1]/'measurement/vision.py',Path(__file__).parents[1]/'measurement/scene.py']},
        'time':project['time_profile'],'calibration':experiment.get('calibration',project['calibration'])})
    cache=Path(folder)/'cache'/'intervals'/(key+'.json')
    if cache.exists():
        p=read_json(cache)
        if p.get('source_hash')==source and p.get('algorithm')==ALGORITHM:return p
    meta=metadata(path);total=meta.get('estimated_frames') or 0;stride=4;tracks={};serial=0;last_frame=-1
    radii=settings['radius_px'];samples=[]
    from ..core.timebase import TimeProfile
    clock=TimeProfile(project['time_profile'],project['mode'])
    for timing,image in frames(path):
        if control:control.check()
        f=timing['frame_index'];last_frame=f
        if f%stride:continue
        if progress:progress({'stage':'interval','frame':f,'detail':'자동 시작·끝 탐색'})
        cs=candidates(image,radii,settings.get('roi_px'),max(12,settings.get('max_candidates',12)))
        ds=[]
        for c in cs:
            try:
                d=measure(image,c,{},settings)
                if d['status']=='low_confidence' or d['visible_arc_fraction']<.65:continue
                if any(np.linalg.norm(np.array(d['raw_center_px'])-q['raw_center_px'])<.7*(d['radius_px']+q['radius_px']) for q in ds):continue
                ds.append(d)
            except (ValueError,cv2.error,np.linalg.LinAlgError):continue
        samples.append(len(ds))
        keys=[k for k,r in tracks.items() if f-r[-1]['frame']<=stride*3]
        assignments={}
        if keys and ds:
            cost=np.array([[np.linalg.norm(np.asarray(tracks[k][-1]['center'])-d['raw_center_px'])/max(d['radius_px'],1) for d in ds] for k in keys])
            aa,bb=linear_sum_assignment(cost)
            assignments={int(b):keys[a] for a,b in zip(aa,bb) if cost[a,b]<3.0}
        for j,d in enumerate(ds):
            k=assignments.get(j)
            if k is None:serial+=1;k=str(serial);tracks[k]=[]
            tracks[k].append({'frame':f,'center':d['raw_center_px'],'radius':d['radius_px'],
                'coverage':d['visible_arc_fraction'],'residual':d['edge_residual_px'],
                'physical_time_s':clock.map(timing['presentation_time_s']) if clock.map(timing['presentation_time_s']) is not None else f/float(project['time_profile'].get('capture_fps') or 240.)})
    total=last_frame+1
    from collections import Counter
    hist=Counter(samples);supported=[n for n,v in hist.items() if n and v>=max(2,len(samples)*.1)]
    count=max(supported,default=0)
    fps=float(project['time_profile'].get('capture_fps') or 240.)
    proposal=propose_from_tracks(tracks,count,total,stride,fps)
    proposal['evidence_tracks']=tracks
    refine_start(path,proposal,settings,control)
    proposal['scene_summary']={k:v for k,v in scene.items() if k!='calibration'}
    proposal['detector_settings']=settings
    proposal.update(id='interval_'+key[:20],algorithm=ALGORITHM,source_hash=source,settings_hash=key,
        created_at=stamp(),proposal_schema_version=1,decoded_count=total,stride=stride,
        evidence_tracks=tracks,automatic_application='exploratory_measurement_only')
    atomic_json(cache,proposal)
    return proposal


def apply_automatic(experiment,proposal):
    """Never overwrite an explicit human choice or user chip intervals."""
    if experiment.get('start_selection',{}).get('method')=='human_release_frame':return
    g=proposal['global'];experiment['interval_proposal']=copy.deepcopy(proposal)
    experiment['interval']=[g['start'],g['end']]
    experiment['start_selection']={'method':'automatic_image_interval','frame':g['start'],'end':g['end'],
        'confirmed':False,'source_hash':proposal['source_hash'],'proposal_id':proposal['id'],
        'confidence':g['confidence'],'release_verified':False,'selected_at':stamp()}
    experiment['status']='pending';experiment['impacts_reviewed']=False
