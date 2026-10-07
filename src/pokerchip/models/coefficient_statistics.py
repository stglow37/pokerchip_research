"""Video/session-balanced estimates and reproducible cluster uncertainty."""
import copy
import numpy as np
from ..core.task import checkpoint, least_squares


def mean(values):
    return float(np.mean(values)) if values else None


def grouped(rows, key):
    result = {}
    for r in rows:
        result.setdefault(r.get(key) or 'unrecorded', []).append(r)
    return result


def hierarchy(rows):
    videos = []
    for key, rr in grouped(rows, 'video_id').items():
        videos.append({'video_id': key, 'session_id': rr[0]['session_id'],
                       'value': mean([r['value'] for r in rr]), 'segments': len(rr)})
    sessions = [{'session_id': key, 'value': mean([v['value'] for v in rr]), 'videos': len(rr)}
                for key, rr in grouped(videos, 'session_id').items()]
    values = [r['value'] for r in rows]
    weighted = [r for r in rows if r.get('variance') is not None and r['variance'] > 0]
    return {'value': mean([s['value'] for s in sessions]), 'videos': videos, 'sessions': sessions,
            'segment_mean': mean(values), 'segment_median': float(np.median(values)) if values else None,
            'segment_std': float(np.std(values, ddof=1)) if len(values)>1 else None,
            'video_std': float(np.std([v['value'] for v in videos],ddof=1)) if len(videos)>1 else None,
            'session_std': float(np.std([s['value'] for s in sessions],ddof=1)) if len(sessions)>1 else None,
            'conditional_inverse_variance_mean': float(np.average([r['value'] for r in weighted], weights=[1/r['variance'] for r in weighted])) if weighted else None,
            'method': 'segment_mean_then_video_mean_then_session_mean',
            'independent_videos': len(videos), 'sessions_count': len(sessions)}


def normal_fit(rows):
    a = np.array([r['a_m_s'] for r in rows]); b = np.array([r['b_m_s'] for r in rows])
    sa = np.array([r['a_sigma_m_s'] for r in rows]); sb = np.array([r['b_sigma_m_s'] for r in rows])
    fit = least_squares(lambda x: np.r_[(b+x[0]*x[1:])/sb, (x[1:]-a)/sa], np.r_[.7,a],
        bounds=(np.r_[0.,np.zeros(len(a))], np.r_[1.,np.full(len(a),np.inf)]), loss='soft_l1')
    from ..analysis.validation import diagnostics
    return {'value': float(fit.x[0]), 'optimizer_success': bool(fit.success),
            'active_bound': bool(np.any(fit.active_mask)),
            'diagnostics': diagnostics(fit, ['e_normal']+[f'approach_{i}' for i in range(len(a))]),
            'event_count': len(rows), 'errors_in_variables': True,
            'observed_mean': mean([-r['b_m_s']/r['a_m_s'] for r in rows]),
            'observed_median': float(np.median([-r['b_m_s']/r['a_m_s'] for r in rows])),
            'method': 'robust_pre_post_errors_in_variables'}


def reliability(rows, estimator, count=200, seed=0):
    unit = 'session_id' if len(grouped(rows, 'session_id'))>1 else 'video_id'
    groups = grouped(rows, unit); names = sorted(groups)
    scope = 'between_sessions' if unit=='session_id' else 'within_single_session_between_videos'
    distributions={key:{name:estimator(rr) for name,rr in grouped(rows,key).items()} for key in ('video_id','session_id')}
    repeatability={'group_estimates':distributions,'group_std':{key:float(np.std(list(values.values()),ddof=1)) if len(values)>1 else None for key,values in distributions.items()}}
    exclusions = {key: estimator([r for r in rows if r.get('video_id')!=key])
                  for key in grouped(rows, 'video_id') if any(r.get('video_id')!=key for r in rows)}
    if len(names)<2 or count<2:
        return {**repeatability,'status': 'insufficient_independent_groups' if len(names)<2 else 'disabled',
                'unit': unit, 'scope': scope, 'interval95': None, 'leave_one_video_out': exclusions,
                'requested': count, 'count': 0, 'samples': []}
    rng = np.random.default_rng(seed); values = []; failures = []
    for i in range(count):
        checkpoint(f'계수 재표본 {i+1}/{count}', phase='bootstrap')
        sample = []
        for j, name in enumerate(rng.choice(names, len(names), replace=True)):
            for original in groups[name]:
                r = copy.deepcopy(original)
                r['video_id'] = f'{j}:{r["video_id"]}'
                if unit=='session_id':r['session_id'] = f'{j}:{r["session_id"]}'
                sample.append(r)
        try:
            value = estimator(sample)
            if value is None or not np.isfinite(value):raise ValueError('유한한 대표계수 없음')
            values.append(float(value))
        except (ValueError, ArithmeticError) as exc:failures.append({'iteration': i, 'reason': str(exc)})
    return {**repeatability,'status': 'computed' if len(values)>1 else 'insufficient_successes', 'unit': unit,
            'scope': scope, 'seed': seed, 'requested': count, 'count': len(values),
            'interval95': np.quantile(values,[.025,.975]).tolist() if len(values)>1 else None,
            'samples': values, 'failures': failures, 'leave_one_video_out': exclusions,
            'uncertainty_scope': 'cluster_sampling_only; shared calibration/model bias excluded'}


def fit_segments(trials, fit_function):
    from time import perf_counter
    from .physics.farkas import propagate
    from ..core.config import Body
    records = []
    for i, tr in enumerate(trials):
        checkpoint(f'구간별 마찰 {i+1}/{len(trials)}', phase='free_segments')
        start = perf_counter()
        record = {k: tr.get(k) for k in ('id','video_id','video','session_id','chip_id','segment_frames',
                  'calculation_warnings','warning_observation_refs','warning_observation_count','used_observation_count','used_observation_refs','warning_observation_fraction')}
        record['calculation_warnings']=list(record.get('calculation_warnings') or [])
        try:
            fit = fit_function([tr], starts=(.15,.35), max_nfev=100, exploratory=True)
            record.update(fit=fit, optimizer_success=fit['optimizer_success'])
            diag=fit['diagnostics']
            singular=diag.get('rank',len(diag.get('parameter_names',[])))<len(diag.get('parameter_names',[]))
            if fit['optimizer_success'] and singular:
                record.update(status='not_computed',reason='rank_deficient_fit',candidate_value=fit['parameters']['mu_bottom'])
            elif fit['optimizer_success']:
                record['value'] = fit['parameters']['mu_bottom']
                cov = diag.get('covariance_conditional')
                record['variance'] = cov[0][0] if cov else None
                if diag.get('identifiability')!='identified_locally':record['calculation_warnings'].append('weak_identifiability')
                if any(diag.get('active_bounds',[])):record['calculation_warnings'].append('active_fit_bound')
                obs = np.asarray(tr['position_angle']);ts=np.asarray(tr['times'])
                pred = propagate(fit['initial_states'][tr['id']],Body(**tr['body']),record['value'],ts-ts[0])
                record['position_fit_rmse_m'] = float(np.sqrt(np.mean(np.sum((pred[:,:2]-obs[:,:2])**2,axis=1))))
                record['angle_fit_rmse_rad'] = float(np.sqrt(np.mean((pred[:,4]-obs[:,2])**2)))
                record['status'] = 'computed_with_warnings' if record['calculation_warnings'] else 'computed'
            else:record.update(status='not_computed', reason='최적화 미수렴', candidate_value=fit['parameters']['mu_bottom'])
        except (ValueError, ArithmeticError) as exc:record.update(status='not_computed',reason=str(exc))
        record['elapsed_s'] = perf_counter()-start;records.append(record)
    return records


def collision_diagnostics(trials, parameters, model, candidate_parameters=None):
    """Observed impulse consistency; not separate per-event estimates of et/muc."""
    from ..core.config import Body
    from .physics.ifr import impact
    records=[]
    for tr in trials:
        p=np.asarray(tr['pre']);q=np.asarray(tr['post']);n=np.asarray(tr['normal'],float)
        n=n/np.linalg.norm(n);t=np.array([-n[1],n[0]])
        bodies=[Body(**b) for b in tr['bodies']]
        c=float((p[0,2:4]-p[1,2:4])@t+sum(b.radius*p[i,5] for i,b in enumerate(bodies)))
        cp=float((q[0,2:4]-q[1,2:4])@t+sum(b.radius*q[i,5] for i,b in enumerate(bodies)))
        tangents=[float(-bodies[0].mass*(q[0,2:4]-p[0,2:4])@t),float(bodies[1].mass*(q[1,2:4]-p[1,2:4])@t)]
        tangents += [float(-b.inertia*(q[i,5]-p[i,5])/b.radius) for i,b in enumerate(bodies)]
        record={k:tr.get(k) for k in ('id','video_id','video','session_id','calculation_warnings','warning_observation_refs')}
        record.update(c_m_s=c,c_after_m_s=cp,e_t_obs=-cp/c if abs(c)>1e-12 else None,
            omega_change_rad_s=(q[:,5]-p[:,5]).tolist(),observed_J_t_N_s=float(np.mean(tangents)),
            impulse_channel_estimates_N_s=tangents,impulse_consistency_rms_N_s=float(np.std(tangents)),
            scope='observed_impulse_consistency; et and muc are jointly estimated across events')
        available=all(k in parameters for k in ('e_normal','e_tangential','mu_collision'))
        chosen=parameters if available else candidate_parameters or {}
        record['model_parameter_scope']='representative' if available else 'withheld_optimizer_candidate'
        if all(k in chosen for k in ('e_normal','e_tangential','mu_collision')):
            prediction=impact(p,bodies,chosen['e_normal'],chosen['e_tangential'],chosen['mu_collision'],model,normal=n,require_contact=False)
            record.update(model_status=prediction['status'],model_reason=prediction.get('reason'))
            post=prediction.get('post') if prediction.get('post') is not None else prediction.get('candidate_post')
            if post is not None:
                record.update(model_J_t_N_s=float(prediction['J_t']),model_J_n_N_s=float(prediction['J_n']),
                    velocity_residual_m_s=(q[:,2:4]-post[:,2:4]).tolist(),
                    omega_residual_rad_s=(q[:,5]-post[:,5]).tolist())
        else:record['model_reason']='접선 대표계수 미산출: 관측 진단만 제공'
        records.append(record)
    return records


def full_tangential_bootstrap(loaded, project, fit_function):
    """Refit the staged model for each session/video cluster draw, without I/O."""
    from .study import free_trials, normal_trials, impact_trials
    from .contact_states import reconstruct
    from .fitting import fit_impacts
    from ..analysis.kinematics import refine_event
    count=project['analysis'].get('tangential_bootstrap_count',0)
    if not count:return {'status':'disabled','interval95':None,'requested':0}
    groups={}
    sessions={e.get('session_id') or e['id'] for cfg,e,rows,events in loaded}
    unit='session' if len(sessions)>1 else 'video'
    for item in loaded:
        e=item[1];key=e.get('session_id') or e['id'] if unit=='session' else e['id']
        groups.setdefault(key,[]).append(item)
    if len(groups)<2:return {'status':'insufficient_independent_groups','interval95':None,'unit':unit,'requested':count}
    rng=np.random.default_rng(project.get('seed',0));names=sorted(groups);samples=[];failures=[]
    for iteration in range(count):
        checkpoint(f'접선 전체 재피팅 {iteration+1}/{count}',phase='tangential_bootstrap')
        selected=[];free=[];normal=[];impacts=[]
        for j,key in enumerate(rng.choice(names,len(names),replace=True)):
            first=groups[key][0][0]['analysis']
            scale=float(np.exp(rng.normal(0,first.get('shared_scale_sigma_fraction',0))))
            clock=float(np.exp(rng.normal(0,first.get('shared_clock_sigma_fraction',0))))
            for cfg,e,rows,events in copy.deepcopy(groups[key]):
                e['id']=f'boot{j}_'+e['id'];e['session_id']=f'boot{j}_'+(e.get('session_id') or key)
                for row in rows:
                    if row.get('world_center_m') is not None:row['world_center_m']=(np.array(row['world_center_m'])*scale).tolist()
                    if row.get('physical_time_s') is not None:row['physical_time_s']*=clock
                    for k in ('vx_m_s','vy_m_s','speed_m_s'):
                        if row.get(k) is not None:row[k]*=scale/clock
                    if row.get('omega_rad_s') is not None:row['omega_rad_s']/=clock
                    if row.get('covariance_world') is not None:row['covariance_world']=(np.array(row['covariance_world'])*scale**2).tolist()
                def get_rows(chip,a,b):return [r for r in rows if r['chip_id']==chip and a<=r['frame_index']<=b]
                rebuilt=[ev if ev.get('status')=='excluded' else refine_event(ev,get_rows,cfg['analysis'],cfg['chips']) for ev in events]
                free.extend(free_trials(cfg,e,rows,rebuilt,True));nr,_=normal_trials(e,rebuilt);normal.extend(nr)
                selected.append((cfg,e,rows,rebuilt))
        try:
            accepted=[r for r in fit_segments(free,fit_function) if r.get('value') is not None]
            mu=hierarchy(accepted)['value']
            if mu is None or not normal:raise ValueError('재표본 마찰/법선 입력 부족')
            en=normal_fit(normal)
            if not en['optimizer_success']:raise ValueError('재표본 법선 미수렴')
            for cfg,e,rows,events in selected:
                corrected=[]
                for ev in events:
                    if ev.get('kind')!='isolated_binary' or ev.get('status')=='excluded':continue
                    try:corrected.append(reconstruct(ev,rows,cfg,mu))
                    except ValueError:continue
                tr,_=impact_trials(cfg,e,corrected);impacts.extend(tr)
            if len(impacts)<3:raise ValueError('재표본 유효 접선 충돌 3개 미만')
            fit=fit_impacts(impacts,project['physics']['model'],eiv=True,max_nfev=150,exploratory=True,fixed_e_normal=en['value'])
            diag=fit['diagnostics']
            if not diag['optimizer_success'] or diag['identifiability']!='identified_locally' or fit['physical_status']!='admissible' or any(diag['active_bounds'][:2]):raise ValueError('재표본 접선 식별성/물리 조건 실패')
            samples.append(dict(mu_bottom=mu,**fit['parameters']))
        except (ValueError,ArithmeticError) as exc:failures.append({'iteration':iteration,'reason':str(exc)})
    return {'status':'computed' if len(samples)>1 else 'insufficient_successes','unit':unit,
            'scope':'between_sessions' if unit=='session' else 'within_single_session_between_videos',
            'requested':count,'count':len(samples),'samples':samples,'failures':failures,
            'interval95':{k:np.quantile([s[k] for s in samples],[.025,.975]).tolist() for k in samples[0]} if len(samples)>1 else None,
            'method':'refit_segments_normal_contact_reconstruction_then_tangential',
            'shared_uncertainty':'only supplied scale/clock sigma; unknown systematics excluded'}
