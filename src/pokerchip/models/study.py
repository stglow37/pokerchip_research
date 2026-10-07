"""Fit on selected whole videos; immutable constants, separate held-out predictions."""
import copy
from pathlib import Path
from dataclasses import asdict
import csv
from time import perf_counter
import numpy as np
from ..core.task import least_squares
from ..core.config import Body,effective
from ..core.storage import Records,read_json,atomic_json,new_id,stamp,digest
from ..application.pipeline import code_digest,stage_keys
from .fitting import fit_free,fit_impacts
from .physics.farkas import propagate
from .physics.ifr import impact
from ..analysis.validation import metrics
from ..analysis.kinematics import event_barriers
from ..core.task import checkpoint,task_scope
from ..core.observation_policy import usable, warning_audit


def split(project):
    train=[e for e in project['experiments'] if e.get('fit_role')=='train']
    test=[e for e in project['experiments'] if e.get('fit_role')=='test']
    if {e['id'] for e in train}&{e['id'] for e in test}:raise ValueError('같은 영상은 계수 측정과 검증에 동시에 쓸 수 없습니다.')
    return train,test


def impact_included(e,event):
    return (event.get('status')!='excluded' and event.get('fit_scope_allowed',True)
            and event.get('kind')=='isolated_binary' and bool(event.get('pre') and event.get('post')))


def human_reviewed(e,event):
    # A v6 review-required event must not inherit approval from an older
    # whole-video checkbox after the observation/review basis changed.
    return bool(event.get('fit_eligible') or event.get('status')=='approved' or
        (event.get('status') is None and e.get('impacts_reviewed')))


def load_video(folder,project,e):
    if e.get('status')!='complete' or not e.get('last_run'):raise ValueError(e['name']+': 먼저 영상 분석을 완료하세요.')
    run=Path(folder)/e['last_run'];measurement_cfg=read_json(run/'effective_settings.json');m=read_json(run/'manifest.json')
    current_cfg=effective(project,e)
    if stage_keys(current_cfg,e,m['source_hash'])['analysis']!=m['stage_keys']['analysis']:
        raise ValueError(e['name']+': 소스 또는 측정 설정이 바뀌었습니다. 영상을 다시 분석하세요.')
    if measurement_cfg['calibration'].get('status') not in ('verified','provisional','synthetic'):raise ValueError(e['name']+': 거리 보정 필요')
    # Measurements stay tied to the immutable run settings. Physical fitting
    # deliberately uses the current, explicitly selected body/model settings.
    cfg=copy.deepcopy(measurement_cfg)
    for key in ('chips','physics','fit_split','seed'):
        cfg[key]=copy.deepcopy(current_cfg[key])
    with Records(run/'records.sqlite',readonly=True) as db:rows=list(db.rows('trajectories'));events=list(db.rows('events'))
    provenance=dict(experiment_id=e['id'],name=e['name'],run=e['last_run'],source_hash=m['source_hash'],analysis_hash=m['stage_keys']['analysis'],
        measurement_settings_hash=m.get('settings_hash'),physics_settings_hash=digest({'chips':cfg['chips'],'physics':cfg['physics']}),
        physical_settings_source='current_project_snapshot',session_id=e.get('session_id'),
        time_status=cfg['time_profile']['status'],geometry_status=cfg['calibration']['status'],
        release_selection=e.get('start_selection'),parent_source_id=e.get('parent_source_id'),
        physical_properties=[{k:c.get(k) for k in ('id','mass_kg','radius_m','inertia_model','inertia_kg_m2')} for c in cfg['chips']])
    return cfg,rows,events,provenance


def free_trials(cfg,e,rows,events,training,skipped=None):
    trials=[]
    for key in e['participating_chip_ids']:
        barriers=event_barriers(events,key)
        valid=[r for r in rows if r['chip_id']==key and usable(r,orientation=True) and r.get('omega_rad_s') is not None and np.isfinite(r['omega_rad_s'])
            and r.get('fit_enabled',True)
            and not any(a<=r['frame_index']<=b for a,b in barriers)]
        segments=[]
        for r in valid:
            if not segments or r['frame_index']!=segments[-1][-1]['frame_index']+1 or r.get('scope_segment')!=segments[-1][-1].get('scope_segment') or any(segments[-1][-1]['frame_index']<a<=r['frame_index'] for a,b in barriers):segments.append([])
            segments[-1].append(r)
        duration=cfg['analysis'].get('free_segment_duration_s',.25)
        if not np.isfinite(duration) or duration<=0:raise ValueError('마찰 구간 길이는 양의 실제 시간이어야 합니다.')
        chunks=[]
        for seg in segments:
            chunk=[]
            for r in seg:
                if chunk and r['physical_time_s']-chunk[0]['physical_time_s']>=duration-1e-10:
                    chunks.append(chunk);chunk=[]
                chunk.append(r)
            if chunk:chunks.append(chunk)
        for seg in chunks:
            if len(seg)<24:
                if skipped is not None:skipped.append(dict(video=e['name'],chip_id=key,coefficient='mu_bottom',frames=[seg[0]['frame_index'],seg[-1]['frame_index']],reason='자유운동 구간 연속 관측 24개 미만'))
                continue
            if not seg:continue
            ts=np.array([r['physical_time_s'] for r in seg]);bound=cfg['analysis'].get('omega_bound_rad_s')
            reason=None
            if np.any(np.diff(ts)<=0):reason='실제 시간 중복 또는 역행'
            elif not bound or max(np.diff(ts))*bound>=np.pi:reason='회전 상한 미입력 또는 회전 alias'
            if reason:
                if skipped is not None:skipped.append(dict(video=e.get('name',e['id']),chip_id=key,coefficient='mu_bottom',frames=[seg[0]['frame_index'],seg[-1]['frame_index']],reason=reason))
                continue
            obs=np.array([r['world_center_m']+[r['theta_wrapped_rad']] for r in seg]);obs[:,2]=np.unwrap(obs[:,2])
            # Initial state uses only the first 12 observed positions/angles, never
            # the smoothed velocity that could have used future evaluation frames.
            prefix=12;origin=ts[prefix-1];A=np.column_stack([np.ones(prefix),ts[:prefix]-origin])
            beta=np.linalg.lstsq(A,obs[:prefix],rcond=None)[0]
            state=[*beta[0,:2],*beta[1,:2],beta[0,2],beta[1,2]]
            begin=prefix-1;body=Body.from_chip(next(c for c in cfg['chips'] if c['id']==key))
            trials.append(dict(**warning_audit(seg),video_id=e['id'],video=e.get('name',e['id']),segment_frames=[r['frame_index'] for r in seg],id=e['id']+'_'+key+'_f'+str(seg[0]['frame_index']),chip_id=key,session_id=e.get('session_id') or e['id'],body=asdict(body),source='direct_observations',
                time_status=cfg['time_profile']['status'],geometry_status=cfg['calibration']['status'],
                times=ts[begin:].tolist(),position_angle=obs[begin:].tolist(),initial_guess=state,sigma=[[max(.0001,float(np.sqrt(max(0,(r.get('covariance_world') or np.eye(3)*2.5e-7)[j][j])))) for j in (0,1)]+[max(.01,r.get('theta_sigma_rad') or .035)] for r in seg[begin:]],
                uncertainty_scope='conditional_edge_and_marker_sigma_with_floor_shared_bias_excluded',
                initialization_times=ts[:prefix].tolist(),initialization_position_angle=obs[:prefix].tolist(),
                frames=[r['frame_index'] for r in seg[begin:]],initialization_frames=[r['frame_index'] for r in seg[:prefix]],score_from_index=1))
            if max((r.get('speed_m_s') or 0) for r in seg)<=.015 and max(abs(r.get('omega_rad_s') or 0) for r in seg)<=1.:
                trials[-1]['calculation_warnings'].append('weak_free_motion_signal')
    return trials


def initialize_fixed(tr,body,mu):
    """Estimate six initial-state components on the prefix; mu is never optimized."""
    times=np.array(tr['initialization_times']);obs=np.array(tr['initialization_position_angle'])
    guess=np.array(tr['initial_guess']);guess[:2]=obs[0,:2];guess[4]=obs[0,2]
    fit=least_squares(lambda s:((propagate(s,body,mu,times-times[0])[:,[0,1,4]]-obs)/[.0005,.0005,.035]).ravel(),
        guess,max_nfev=80,loss='soft_l1',x_scale='jac')
    if not fit.success:raise ValueError('검증 영상 처음 12프레임의 초기 상태 계산이 수렴하지 않았습니다.')
    state=propagate(fit.x,body,mu,[times[-1]-times[0]])[0]
    return state,{'method':'six_state_prefix_fit_with_frozen_mu','frames':tr['initialization_frames'],'mu_fixed':mu,'optimizer_success':bool(fit.success)}


def normal_trials(e,events):
    """Build position/velocity-only normal restitution observations.

    Rotation is deliberately not an eligibility condition here. Tangential IFR
    trials are built separately by ``impact_trials``.
    """
    result=[];skipped=[]
    for ev in events:
        base={'event':ev.get('id'),'coefficient':'e_normal'}
        if ev.get('status')=='excluded' or not ev.get('fit_scope_allowed',True) or ev.get('kind')!='isolated_binary' or not ev.get('pre') or not ev.get('post'):
            skipped.append({**base,'reason':'검토된 고립 2체 충돌의 위치 전후 상태 부족'});continue
        if not impact_included(e,ev):
            skipped.append({**base,'reason':'충돌 영상 검토 확인 필요'});continue
        try:
            n=np.asarray(ev['normal'],float);pre=ev['pre'];post=ev['post']
            if n.shape!=(2,) or not np.isfinite(n).all() or np.linalg.norm(n)<1e-12:raise ValueError
            n=n/np.linalg.norm(n)
            a=float((np.asarray(pre[0]['velocity'])-pre[1]['velocity'])@n)
            b=float((np.asarray(post[0]['velocity'])-post[1]['velocity'])@n)
            sigmas=[np.asarray(s.get('velocity_sigma') or [.03,.03],float) for side in (pre,post) for s in side]
            sigma=float(max(.003,np.sqrt(sum(float((x*n)@(x*n)) for x in sigmas))))
            sigma_pre=float(max(.003,np.sqrt(sum(float((x*n)@(x*n)) for x in sigmas[:2]))))
            sigma_post=float(max(.003,np.sqrt(sum(float((x*n)@(x*n)) for x in sigmas[2:]))))
        except (KeyError,TypeError,ValueError,IndexError):
            skipped.append({**base,'reason':'법선 또는 충돌 전후 중심 속도 자료 오류'});continue
        if not np.isfinite([a,b,sigma]).all() or a<=1e-12:
            skipped.append({**base,'reason':'유한한 전후 속도와 양의 접근 속도 필요'});continue
        warning=list(ev.get('calculation_warnings',[]))+list(ev.get('automatic_fit_gate',{}).get('warnings',[]))
        if a<=3*sigma:warning.append('weak_approach_signal')
        if b>3*sigma:warning.append('post_state_not_separating')
        if not 0<=-b/a<=1:warning.append('observed_restitution_outside_model_range')
        if not human_reviewed(e,ev):warning.append('human_review_incomplete')
        result.append({'id':e['id']+'_'+ev['id'],'video_id':e['id'],'video':e['name'],'event_id':ev['id'],'session_id':e.get('session_id') or e['id'],
                       'e_n_obs':float(-b/a),'calculation_warnings':sorted(set(warning)),
                       'warning_observation_refs':ev.get('warning_observation_refs',[]),
                       'used_observation_refs':ev.get('used_observation_refs',[]),
                       'warning_observation_count':ev.get('warning_observation_count',0),
                       'used_observation_count':ev.get('used_observation_count',0),
                       'warning_observation_fraction':ev.get('warning_observation_fraction',0.),
                       'a_m_s':a,'b_m_s':b,'sigma_m_s':sigma,
                       'a_sigma_m_s':sigma_pre,'b_sigma_m_s':sigma_post,
                       'scope':'position_based_one_sided_observed_states','rotation_required':False,
                       'review_scope':'human_reviewed' if human_reviewed(e,ev) else 'automatic_exploratory'})
    return result,skipped


def impact_trials(cfg,e,events):
    result=[];skipped=[]
    for ev in events:
        if ev.get('status')=='excluded' or not ev.get('fit_scope_allowed',True) or ev.get('kind')!='isolated_binary' or not ev.get('pre') or not ev.get('post'):
            skipped.append({'event':ev['id'],'coefficient':'ifr','reason':'고립 2체 충돌의 연속 전후 측정 부족'});continue
        if not impact_included(e,ev):
            skipped.append({'event':ev['id'],'coefficient':'ifr','reason':'충돌 영상 검토 확인 필요'});continue
        if any(s.get('omega') is None or not np.isfinite(s['omega']) for side in ('pre','post') for s in ev[side]):
            skipped.append({'event':ev['id'],'coefficient':'ifr','reason':'충돌 전후 각속도 누락'});continue
        states={side:[s['position']+s['velocity']+[s.get('theta') or 0.,s['omega']] for s in ev[side]] for side in ('pre','post')}
        sig={side+'_sigma':[list(np.maximum(.01,s['velocity_sigma']))+[max(1.,s.get('omega_sigma') or 1.)] for s in ev[side]] for side in ('pre','post')}
        bodies=[asdict(Body.from_chip(next(c for c in cfg['chips'] if c['id']==k))) for k in ev['pair']]
        reviewed=human_reviewed(e,ev)
        result.append(dict(video_id=e['id'],video=e['name'],calculation_warnings=ev.get('calculation_warnings',[]),warning_observation_refs=ev.get('warning_observation_refs',[]),id=e['id']+'_'+ev['id'],session_id=e.get('session_id') or e['id'],source='reviewed_observations' if reviewed else 'direct_observations',review_scope='human_reviewed' if reviewed else 'automatic_exploratory',state_estimation=ev.get('velocity_scope','measurement'),reconstruction=ev.get('reconstruction'),kind='isolated_binary',approved=reviewed,calculation_eligible=True,
            time_status=cfg['time_profile']['status'],geometry_status=cfg['calibration']['status'],bodies=bodies,normal=ev['normal'],normal_sigma=.03,**states,**sig))
        result[-1].update({k:ev.get(k) for k in ('used_observation_refs','used_observation_count','warning_observation_count','warning_observation_fraction','uses_warned_observations')})
        result[-1]['calculation_warnings']=list(result[-1].get('calculation_warnings') or [])
        if not reviewed:result[-1]['calculation_warnings'].append('human_review_incomplete')
    return result,skipped


def _train_constants(folder,project,progress=None):
    train,_=split(project)
    if not train:raise ValueError('계수 구하기용 영상을 하나 이상 지정하세요.')
    free=[];normal=[];collisions=[];sources=[];skipped=[];loaded=[]
    emit=progress or (lambda v:None)
    # Test video records are deliberately never loaded by this function.
    for index,e in enumerate(train,1):
        checkpoint(f"계수용 영상 준비 {index}/{len(train)} · {e['name']}",video_index=index,video_total=len(train),overall_percent=5*index/len(train))
        try:cfg,rows,events,prov=load_video(folder,project,e)
        except (ValueError,FileNotFoundError) as exc:
            skipped.append(dict(video=e['name'],reason=str(exc)));continue
        sources.append(prov);loaded.append((cfg,e,rows,events))
        free.extend(free_trials(cfg,e,rows,events,True,skipped))
        trials,why=normal_trials(e,events);normal.extend(trials)
        skipped.extend([dict(video=e['name'],**x) for x in why])
    if len({s['source_hash'] for s in sources})!=len(sources):raise ValueError('계수 영상에 동일 원본이 중복 등록되어 있습니다.')
    bank=dict(id=new_id('constants'),created=stamp(),status='exploratory_not_independently_validated',code_hash=code_digest(),
        code_hashes={'physics':code_digest('physics')},
        parameters={},stages={},training_sources=sources,skipped_impacts=skipped,
        model=project['physics']['model'],model_version='farkas_v1_ifr_reconstruction_v2',
        model_scope='Farkas free-motion model; position-based normal restitution; rotation-dependent tangential IFR extension',
        uncertainty='Conditional measurement weights; shared camera/time uncertainty not calibrated.',
        split_unit='whole_video',data=dict(free_trials=free,normal_trials=normal,impact_trials=collisions))
    if free:
        checkpoint('1/4 바닥 마찰 공통 피팅',overall_percent=10,phase_end_percent=48)
        emit({'stage':'study','message':'1/4 구간별 바닥 마찰 피팅 · 반복 최적화 중'})
        from .coefficient_statistics import fit_segments,hierarchy,reliability
        segments=fit_segments(free,fit_free);bank['segment_estimates']=segments
        accepted=[r for r in segments if r.get('value') is not None]
        summary=hierarchy(accepted)
        bank['stages']['free_motion']={'optimizer_success':bool(accepted),'parameters':{'mu_bottom':summary['value']},'aggregation':summary,'segment_fit_elapsed_s':sum(r['elapsed_s'] for r in segments)}
        if accepted:
            bank['parameters']['mu_bottom']=summary['value']
            bank.setdefault('reliability',{})['mu_bottom']=reliability(accepted,lambda rr:hierarchy(rr)['value'],project['analysis'].get('coefficient_bootstrap_count',200),project.get('seed',0))
        if project['analysis'].get('compare_joint_fit',False):
            started=perf_counter();comparison=fit_free(free,starts=(.15,.35),max_nfev=100,exploratory=True)
            comparison['elapsed_s']=perf_counter()-started
            bank['stages']['free_motion']['joint_comparison']=comparison
    checkpoint('2/4 법선 반발계수',overall_percent=50,phase_end_percent=60)
    emit({'stage':'study','message':'2/4 위치 기반 법선 반발계수 검사 중'})
    if normal:
        from .coefficient_statistics import normal_fit,reliability
        fit=normal_fit(normal);bank['stages']['normal']=fit
        if fit['optimizer_success']:
            bank['parameters']['e_normal']=fit['value']
            if fit['active_bound']:fit['calculation_warnings']=['active_fit_bound']
            bank.setdefault('reliability',{})['e_normal']=reliability(normal,lambda rr:normal_fit(rr)['value'],project['analysis'].get('coefficient_bootstrap_count',200),project.get('seed',0))
        else:fit['release_status']='법선 반발 최적화 실패'
    else:
        bank['stages']['normal']={'event_count':0,'release_status':'검토된 위치 기반 법선 충돌 자료 없음'}
    from .contact_states import reconstruct
    checkpoint('3/4 충돌 상태 환산',overall_percent=62,phase_end_percent=78)
    emit({'stage':'study','message':'3/4 IFR용 회전 포함 상태를 같은 충돌 시각으로 환산 중'})
    for cfg,e,rows,events in loaded:
        corrected=[]
        for ev in events:
            if ev.get('kind')!='isolated_binary' or ev.get('status')=='excluded':
                skipped.append(dict(video=e['name'],event=ev.get('id'),coefficient='ifr',reason='검토된 고립 2체 충돌 아님'));continue
            if not impact_included(e,ev):
                skipped.append(dict(video=e['name'],event=ev.get('id'),coefficient='ifr',reason='충돌 영상 검토 확인 필요'));continue
            try:
                if cfg['time_profile']['status']=='synthetic_known_clock':updated=ev
                else:
                    if 'mu_bottom' not in bank['parameters']:raise ValueError('먼저 자유운동 자료에서 바닥 마찰계수를 구해야 합니다.')
                    updated=reconstruct(ev,rows,cfg,bank['parameters']['mu_bottom'])
                corrected.append(updated)
            except ValueError as exc:skipped.append(dict(video=e['name'],event=ev['id'],coefficient='ifr',reason=str(exc)))
        tr,why=impact_trials(cfg,e,corrected);collisions.extend(tr)
        skipped.extend([dict(video=e['name'],**x) for x in why])
    bank['data']['impact_trials']=collisions
    checkpoint('4/4 접선 IFR 피팅',overall_percent=80,phase_end_percent=96)
    emit({'stage':'study','message':'4/4 회전 포함 IFR 식별성 검사 중'})
    if collisions:
        if len(collisions)>=3 and 'e_normal' in bank['parameters']:
            fit=fit_impacts(collisions,bank['model'],eiv=True,max_nfev=150,exploratory=True,
                            fixed_e_normal=bank['parameters']['e_normal']);bank['stages']['impact']=fit
            d=fit['diagnostics'];bounds=d['active_bounds'][:2]
            if d['optimizer_success'] and d['identifiability']=='identified_locally' and not any(bounds) and fit['physical_status']=='admissible':
                bank['parameters'].update({k:v for k,v in fit['parameters'].items() if k in ('e_tangential','mu_collision')})
            else:bank['stages']['impact']['release_status']='접선 계수 식별성/경계/물리 조건 불충족: 고정 적용 보류'
        elif len(collisions)<3:bank['stages']['impact']={'release_status':'접선 반발·충돌 마찰 분리에는 서로 다른 조건의 검토된 충돌 3개 이상 필요. 개수 충족만으로 식별 보장 안 됨.'}
        else:bank['stages']['impact']={'release_status':'승인된 위치 기반 법선 반발계수가 없어 IFR 피팅 보류'}
    from .coefficient_statistics import full_tangential_bootstrap
    bank['tangential_bootstrap']=full_tangential_bootstrap(loaded,project,fit_free)
    if not bank['parameters']:bank['status']='no_estimable_coefficients'
    checkpoint('계수 및 미산출 사유 저장 중',overall_percent=98)
    bank['coefficient_status']={key:dict(status='provisional' if key in bank['parameters'] else 'withheld',reason='잠정 계수: 독립 정확도 미검증' if key in bank['parameters'] else bank['stages'].get(stage,{}).get('release_status','입력 자료 또는 식별성 부족'),used_trials=len(bank['data'].get(data_key,[]))) for key,stage,data_key in [('mu_bottom','free_motion','free_trials'),('e_normal','normal','normal_trials'),('e_tangential','impact','impact_trials'),('mu_collision','impact','impact_trials')]}
    bank['parameter_hash']=digest(bank['parameters']);out=Path(folder)/'results'/'계수_측정'/bank['id'];out.mkdir(parents=True)
    bank['calculation_warnings']=sorted({w for tr in free+normal+collisions+bank.get('segment_estimates',[]) for w in tr.get('calculation_warnings',[])})
    bank['warning_observation_refs']=list({(r['chip_id'],r['frame_index'],tr.get('video_id')):dict(r,video_id=tr.get('video_id')) for tr in free+normal+collisions for r in tr.get('warning_observation_refs',[])}.values())
    for key,status in bank['coefficient_status'].items():
        inputs=([s for s in bank.get('segment_estimates',[]) if s.get('value') is not None] if key=='mu_bottom' else normal if key=='e_normal' else collisions)
        refs={(tr.get('video_id'),r['chip_id'],r['frame_index']) for tr in inputs for r in tr.get('warning_observation_refs',[])}
        used={(tr.get('video_id'),r['chip_id'],r['frame_index']) for tr in inputs for r in tr.get('used_observation_refs',[])}
        status.update(used_trials=len(inputs),independent_videos=len({tr['video_id'] for tr in inputs}),sessions=len({tr['session_id'] for tr in inputs}),warning_observations=len(refs),used_observations=len(used),warning_observation_fraction=len(refs)/len(used) if used else None,
            calculation_warnings=sorted({w for tr in inputs for w in tr.get('calculation_warnings',[])}))
    from .coefficient_statistics import collision_diagnostics
    bank['collision_estimates']=collision_diagnostics(collisions,bank['parameters'],bank['model'],bank['stages'].get('impact',{}).get('parameters'))
    from ..application.exporting import table_csv,summary_workbook
    segment_fields=['video','chip_id','segment_frames','value','candidate_value','variance','status','reason','calculation_warnings','warning_observation_refs','warning_observation_count','used_observation_count','warning_observation_fraction','position_fit_rmse_m','angle_fit_rmse_rad','elapsed_s']
    table_csv(out/'구간별_마찰계수.csv',segment_fields,bank.get('segment_estimates',[]))
    tangent_by_id={r['id']:r for r in bank['collision_estimates']}
    event_records=[dict(tr,**{k:v for k,v in tangent_by_id.get(tr['id'],{}).items() if k not in tr}) for tr in normal]
    event_fields=['video','event_id','a_m_s','b_m_s','e_n_obs','a_sigma_m_s','b_sigma_m_s','c_m_s','c_after_m_s','e_t_obs','omega_change_rad_s','observed_J_t_N_s','impulse_consistency_rms_N_s','model_J_t_N_s','velocity_residual_m_s','omega_residual_rad_s','model_parameter_scope','model_reason','calculation_warnings','warning_observation_refs','warning_observation_count','used_observation_count','warning_observation_fraction']
    reliability_fields=['coefficient','status','unit','scope','interval95','count','group_estimates','group_std','leave_one_video_out']
    reliability_records=[dict(coefficient=k,**v) for k,v in bank.get('reliability',{}).items()]
    table_csv(out/'충돌별_계수.csv',event_fields,event_records)
    table_csv(out/'계수_신뢰도.csv',reliability_fields,reliability_records)
    summary_workbook(out/'계수_요약.xlsx',{
        'coefficients':(['coefficient','value','status','reason','used_trials','independent_videos','sessions','warning_observations','warning_observation_fraction','calculation_warnings'],[dict(coefficient=k,value=bank['parameters'].get(k),**v) for k,v in bank['coefficient_status'].items()]),
        'segments':(segment_fields,bank.get('segment_estimates',[])),
        'collisions':(event_fields,event_records),'reliability':(reliability_fields,reliability_records)})
    atomic_json(out/'constants.json',bank)
    names={'mu_bottom':'바닥 마찰계수','e_normal':'법선 반발계수','e_tangential':'IFR 접선 반발계수','mu_collision':'원판 충돌 마찰계수'}
    with (out/'측정한_계수.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.writer(stream);w.writerow(['물리량','피팅값','상태','피팅에 사용한 영상 수','사용 구간 또는 사건 수','세션 수','재표본 95% 구간','경고 관측 수','경고 관측 비율','경고 사유','미산출 또는 적용 사유'])
        for key,name in names.items():
            status=bank['coefficient_status'][key]
            w.writerow([name,bank['parameters'].get(key),status['status'],status['independent_videos'],status['used_trials'],status['sessions'],bank.get('reliability',{}).get(key,{}).get('interval95'),status['warning_observations'],status['warning_observation_fraction'],status['calculation_warnings'],status['reason']])
    (out/'읽어주세요.txt').write_text('계수 구하기용 영상만 사용했습니다. 검증 영상은 피팅에서 읽지 않습니다.\n'+str(bank['parameters'])+'\n잠정 결과이며 확정된 계수 정확도나 신뢰구간이 아닙니다. constants.json의 근거 영상·구간·식별성 기록을 확인하세요.\n',encoding='utf8')
    return {'path':str(out/'constants.json'),'parameters':bank['parameters'],'id':bank['id'],'status':bank['status'],'coefficient_status':bank['coefficient_status']}


def _evaluate_fixed(folder,project,bank_path,progress=None):
    _,test=split(project)
    if not test:raise ValueError('고정 계수 검증용 영상을 하나 이상 지정하세요.')
    bank=read_json(bank_path);params=bank['parameters']
    if digest(params)!=bank['parameter_hash']:raise ValueError('저장된 계수 파일이 변경되었습니다. 원본 계수 파일을 사용하세요.')
    trained={s['source_hash'] for s in bank['training_sources']};trained_ids={s['experiment_id'] for s in bank['training_sources']}
    if trained_ids&{e['id'] for e in test}:raise ValueError('이 계수를 구하는 데 사용한 영상은 독립 검증 영상으로 재사용할 수 없습니다.')
    out=Path(folder)/'results'/'고정계수_검증'/new_id('validation');out.mkdir(parents=True)
    result=dict(created=stamp(),constant_bank_id=bank['id'],parameter_hash=bank['parameter_hash'],parameters=dict(params),
        parameters_refitted=False,code_hash=code_digest(),code_hashes={'physics':code_digest('physics')},model=bank.get('model'),
        model_version=bank.get('model_version','legacy_unversioned'),sources=[],free_motion=[],impacts=[],skipped=[],
        model_scope=bank.get('model_scope','legacy_unrecorded_scope'),
        evaluation_scope='free-motion conditional on first 12 observed frames; impact conditional on observed pre-state. Not end-to-end full-forward validation.',
        scope_warning='Video split may share session calibration errors. Repeated tuning against these videos makes them development data.')
    csvrows=[];emit=progress or (lambda v:None)
    for index,e in enumerate(test,1):
        checkpoint(f'고정 검증 {index}/{len(test)}번째 영상 · '+e['name'],video_index=index,video_total=len(test),overall_percent=95*(index-1)/len(test))
        try:cfg,rows,events,prov=load_video(folder,project,e)
        except (ValueError,FileNotFoundError) as exc:
            result['skipped'].append(dict(video=e['name'],reason=str(exc)));continue
        if prov.get('parent_source_id') and prov['parent_source_id'] in {s.get('parent_source_id') for s in bank['training_sources']}:raise ValueError('같은 원본에서 잘라낸 영상은 독립 검증이 아닙니다.')
        if prov.get('session_id') in {s.get('session_id') for s in bank['training_sources']}:
            result['skipped'].append({'video':e['name'],'warning':'학습과 같은 촬영 세션: 영상 분리 검증이며 독립 세션 검증은 아님'})
        material=next((s.get('physical_properties') for s in bank['training_sources'] if s.get('physical_properties')),None)
        if material and material!=prov.get('physical_properties'):raise ValueError('계수 측정 때의 질량·반지름·관성 설정과 다릅니다. 계수를 다시 구하거나 동일 물성을 사용하세요.')
        if prov['source_hash'] in trained:raise ValueError('파일명이 달라도 원본이 같은 영상은 검증에 사용할 수 없습니다.')
        result['sources'].append(prov)
        if 'mu_bottom' in params:
            for tr in free_trials(cfg,e,rows,events,False):
                body=Body(**tr['body']);times=np.array(tr['times']);obs=np.array(tr['position_angle'])
                initial,init_report=initialize_fixed(tr,body,params['mu_bottom'])
                pred=propagate(initial,body,params['mu_bottom'],times-times[0]);i=tr['score_from_index']
                score=dict(calculation_warnings=tr.get('calculation_warnings',[]),warning_observation_refs=tr.get('warning_observation_refs',[]),video=e['name'],chip_id=tr['chip_id'],initialization_frames=tr['initialization_frames'],
                    initialization=init_report,initial_state=initial.tolist(),
                    score_frames=tr['frames'][i:],position_m=metrics(obs[i:,:2],pred[i:,:2],kind='free_motion'),
                    angle_rad=metrics(obs[i:,2],pred[i:,4],kind='free_motion'),constants_frozen=True)
                result['free_motion'].append(score)
                for j in range(i,len(times)):csvrows.append([e['name'],tr['chip_id'],tr['frames'][j],times[j],*obs[j],*pred[j,[0,1,4]],params['mu_bottom'],tr.get('calculation_warnings',[]),tr.get('warning_observation_refs',[])])
                import matplotlib
                matplotlib.use('Agg')
                from matplotlib import pyplot as plt
                fig,ax=plt.subplots(1,2,figsize=(10,4));ax[0].plot(obs[i:,0],obs[i:,1],'.',label='Held-out observation');ax[0].plot(pred[i:,0],pred[i:,1],label='Frozen mu prediction');ax[0].legend();ax[0].set(xlabel='x (m)',ylabel='y (m)')
                ax[1].plot(times[i:]-times[0],obs[i:,2],'.');ax[1].plot(times[i:]-times[0],pred[i:,4]);ax[1].set(xlabel='Time (s)',ylabel='Angle (rad)');fig.tight_layout();fig.savefig(out/(tr['id']+'.png'),dpi=120);plt.close(fig)
        impact_scores={}
        normal_data,normal_why=normal_trials(e,events)
        result['skipped'].extend([dict(video=e['name'],**x) for x in normal_why])
        for tr in normal_data:
            score=dict(calculation_warnings=tr.get('calculation_warnings',[]),warning_observation_refs=tr.get('warning_observation_refs',[]),video=e['name'],event=tr['id'],constants_frozen=True,state_estimation=tr['scope'])
            if 'e_normal' in params:
                predicted=-params['e_normal']*tr['a_m_s'];actual=tr['b_m_s']
                score.update(normal_relative_prediction_m_s=float(predicted),normal_relative_observed_m_s=float(actual),
                             normal_relative_error_m_s=float(predicted-actual),normal_validation_scope=tr['scope'])
            else:score['normal_status']='고정된 법선 반발계수 없음'
            impact_scores[tr['id']]=score
        corrected=[]
        from .contact_states import reconstruct
        for ev in events:
            if ev.get('kind')!='isolated_binary' or ev.get('status')=='excluded' or not impact_included(e,ev):continue
            try:
                if cfg['time_profile']['status']=='synthetic_known_clock':corrected.append(ev)
                elif 'mu_bottom' in params:corrected.append(reconstruct(ev,rows,cfg,params['mu_bottom']))
                else:raise ValueError('고정된 바닥 마찰계수가 없어 충돌 시각 환산을 보류합니다.')
            except ValueError as exc:result['skipped'].append(dict(video=e['name'],reason=str(exc)))
        trs,why=impact_trials(cfg,e,corrected);result['skipped'].extend([dict(video=e['name'],**x) for x in why])
        for tr in trs:
            p=np.array(tr['pre']);q=np.array(tr['post']);n=np.array(tr['normal']);a=(p[0,2:4]-p[1,2:4])@n
            score=impact_scores.setdefault(tr['id'],dict(video=e['name'],event=tr['id'],constants_frozen=True))
            score.update(ifr_state_estimation=tr.get('state_estimation'),reconstruction=tr.get('reconstruction'))
            if all(k in params for k in ('e_normal','e_tangential','mu_collision')):
                r=impact(p,[Body(**b) for b in tr['bodies']],params['e_normal'],params['e_tangential'],params['mu_collision'],bank['model'],normal=n,require_contact=False)
                score.update(status=r['status'],reason=r.get('reason'))
                if r['status']=='ok':score.update(velocity_m_s=metrics(q[:,2:4],r['post'][:,2:4],kind='impact_conditional'),omega_rad_s=metrics(q[:,5],r['post'][:,5],kind='impact_conditional'))
            else:score['ifr_full_status']='접선 계수 미확정: 법선 상대속도만 검증 가능'
        result['impacts'].extend(impact_scores.values())
    scored_free=sum(r.get('position_m',{}).get('valid_values',0)>0 for r in result['free_motion'])
    scored_impacts=sum(r.get('normal_relative_error_m_s') is not None or r.get('velocity_m_s',{}).get('valid_values',0)>0 for r in result['impacts'])
    result['evaluated_counts']={'free_segments':scored_free,'impacts':scored_impacts}
    result['status']='conditional_holdout_evaluated' if scored_free+scored_impacts else 'no_eligible_validation_data'
    checkpoint('검증 파일 저장 중',overall_percent=98)
    result['parameter_hash_after']=digest(params)
    atomic_json(out/'validation.json',result)
    with (out/'고정계수_검증요약.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.writer(stream);w.writerow(['영상','칩 또는 충돌','평가 종류','위치 2D RMSE(m)','각도 RMSE(rad)','충돌 속도 2D RMSE(m/s)','충돌 각속도 RMSE(rad/s)','법선 상대속도 오차(m/s)','계수 다시 피팅함','경고 사유','원인 관측'])
        for r in result['free_motion']:w.writerow([r['video'],r['chip_id'],'초기12프레임 제외 자유운동',r['position_m']['vector_rmse'],r['angle_rad']['rmse'],None,None,None,'아니오',r.get('calculation_warnings',[]),r.get('warning_observation_refs',[])])
        for r in result['impacts']:w.writerow([r['video'],r['event'],'관측 충돌 직전 상태에서 예측',None,None,r.get('velocity_m_s',{}).get('vector_rmse'),r.get('omega_rad_s',{}).get('rmse'),r.get('normal_relative_error_m_s'),'아니오',r.get('calculation_warnings',[]),r.get('warning_observation_refs',[])])
    with (out/'고정계수_예측비교.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.writer(stream);w.writerow(['영상','칩','프레임','실제시간_s','관측x_m','관측y_m','관측각_rad','예측x_m','예측y_m','예측각_rad','고정_바닥마찰계수','경고 사유','원인 관측']);w.writerows(csvrows)
    (out/'읽어주세요.txt').write_text('고정 계수를 다시 피팅하지 않았습니다.\n초기 12프레임은 초기 상태 측정용이며 평가 오차에서 제외합니다.\n자유운동과 충돌 직후 예측을 분리합니다. 전체 연속 운동의 무조건적 검증은 아닙니다.\n'+result['status'],encoding='utf8')
    return {'path':str(out/'validation.json'),'parameters':params,'status':result['status']}


def preflight(folder,project,role='train'):
    rows=[]
    for e in project['experiments']:
        if e.get('fit_role')!=role:continue
        try:
            cfg,data,events,_=load_video(folder,project,e)
            free=free_trials(cfg,e,data,events,role=='train');n=len(free)
            impacts=sum(ev.get('kind')=='isolated_binary' and ev.get('status')!='excluded' for ev in events)
            normal_count=len(normal_trials(e,events)[0]);ifr_count=len(impact_trials(cfg,e,events)[0])
            reviewed=bool(e.get('impacts_reviewed'))
            rows.append(dict(video=e['name'],usable=bool(n or normal_count or ifr_count),free_segments=n,collision_candidates=impacts,
                normal_eligible=normal_count,ifr_preliminary=ifr_count,ifr_eligible=None,
                selected_free_intervals=[{'chip_id':tr['chip_id'],'initialization':tr['initialization_frames'],'frames':tr['frames']} for tr in free],
                reason=f'자유운동 {n}구간 · 충돌 후보 {impacts}개 · 법선 가능 {normal_count}개 · IFR 1차 후보 {ifr_count}개 (접촉 시각 환산 후 확정)\n'+', '.join(f"{tr['chip_id']} {tr['initialization_frames'][0]}–{tr['frames'][-1]}프레임" for tr in free)+'\n위치·회전 연속 24표본 이상, 기본 실제시간 0.25초 비중첩 구간. 경고 포함, 충돌·누락·바닥 이탈에서 분리.'))
        except (ValueError,FileNotFoundError) as exc:rows.append(dict(video=e['name'],usable=False,reason=str(exc)))
    return rows


def _run_task(fn,folder,project,args,progress,control):
    journal=Path(folder)/'results'/'작업기록'/(new_id('study')+'.json')
    record={'status':'running','started':stamp(),'kind':fn.__name__,'project_id':project.get('id')}
    atomic_json(journal,record)
    with task_scope(progress,control):
        def relay(value):
            import re
            message=value.get('message','계산 중');match=re.match(r'(\d+)/(\d+)',message)
            extra={'overall_percent':5+90*(int(match[1])-1)/int(match[2])} if match else {}
            checkpoint(message,**extra)
        try:
            result=fn(folder,project,*args,progress=relay)
            record.update(status='complete',finished=stamp(),result=result);atomic_json(journal,record)
            checkpoint('계산·파일 저장 완료',overall_percent=100,phase='complete')
            return result
        except Exception as exc:
            record.update(status='cancelled' if control and control.cancelled.is_set() else 'failed',finished=stamp(),reason=str(exc))
            atomic_json(journal,record)
            raise


def train_constants(folder,project,progress=None,control=None):
    return _run_task(_train_constants,folder,project,(),progress,control)


def evaluate_fixed(folder,project,bank_path,progress=None,control=None):
    return _run_task(_evaluate_fixed,folder,project,(bank_path,),progress,control)
