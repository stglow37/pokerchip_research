"""Explicit exploratory free-flight fit; never overwrites research parameters."""
from pathlib import Path
import numpy as np
from ..core.config import Body
from ..core.storage import Records,atomic_json
from ..analysis.kinematics import event_barriers
from .fitting import fit_free
from .physics.farkas import propagate

def preview(run,config,experiment):
    out=Path(run)/'export';result={'status':'exploratory_not_validated','free_motion':[],
        'note':'잠정 시간·거리와 균일 압력 원판 가정의 탐색 피팅. 독립 정확도/신뢰구간/예측 검증 아님.'}
    if config['calibration'].get('status') not in ('verified','provisional','synthetic'):
        result['reason']='거리 보정 필요';atomic_json(out/'physics_preview.json',result);return result
    with Records(Path(run)/'records.sqlite') as db:
        events=list(db.rows('events'));allrows=list(db.rows('trajectories'))
    result['impacts']=[{k:e.get(k) for k in ['id','frame_start','frame_end','time_s','kind','reason','e_n_obs','e_t_obs']} for e in events]
    result['ifr_status']='충돌 전후 관측 계수만 표시; 접선 반발과 접촉 마찰 분리 피팅은 검토된 여러 충돌 필요'
    for key in experiment['participating_chip_ids']:
        barriers=event_barriers(events,key)
        selected=[r for r in allrows if r['chip_id']==key and r.get('speed_m_s',0) is not None and r.get('speed_m_s',0)>.08
            and r.get('omega_rad_s') is not None and r.get('world_center_m') is not None and r.get('status')=='observed'
            and not r.get('assignment_ambiguous') and not r.get('measurement_warning')
            and not any(a<=r['frame_index']<=b for a,b in barriers)]
        segments=[]
        for r in selected:
            if not segments or r['frame_index']!=segments[-1][-1]['frame_index']+1:segments.append([])
            segments[-1].append(r)
        seg=max(segments,key=len,default=[])[:55]
        if len(seg)<24:result['free_motion'].append({'chip_id':key,'status':'insufficient_contiguous_moving_data'});continue
        body=Body.from_chip(next(c for c in config['chips'] if c['id']==key));first=seg[0]
        times=np.array([r['physical_time_s'] for r in seg]);angles=np.unwrap([r['theta_wrapped_rad'] for r in seg])
        bound=config['analysis'].get('omega_bound_rad_s')
        if bound is None or np.max(np.diff(times))*bound>=np.pi:continue
        tr=dict(id=key,session_id=experiment['session_id'],source='direct_observations',time_status=config['time_profile']['status'],geometry_status=config['calibration']['status'],
            body={'mass':body.mass,'radius':body.radius,'inertia':body.inertia,'id':key},times=times.tolist(),
            position_angle=[r['world_center_m']+[float(a)] for r,a in zip(seg,angles)],sigma=[.0005,.0005,.035],
            initial_guess=first['world_center_m']+[first['vx_m_s'],first['vy_m_s'],float(angles[0]),first['omega_rad_s']])
        try:
            fit=fit_free([tr],starts=(.28,),max_nfev=45,exploratory=True)
            prediction=propagate(fit['initial_states'][key],body,fit['parameters']['mu_bottom'],times-times[0])
            observed=np.array(tr['position_angle']);delta=prediction[:,[0,1,4]]-observed
            record=dict(chip_id=key,status='exploratory_fit' if fit['optimizer_success'] else 'optimizer_not_converged',
                frames=[seg[0]['frame_index'],seg[-1]['frame_index']],mu_bottom=fit['parameters']['mu_bottom'],
                position_fit_rmse_m=float(np.sqrt(np.mean(np.sum(delta[:,:2]**2,axis=1)))),angle_fit_rmse_rad=float(np.sqrt(np.mean(delta[:,2]**2))),
                weighting='fixed exploratory 0.5mm / 0.035rad; not calibrated uncertainty',fit=fit)
            result['free_motion'].append(record)
            import matplotlib
            matplotlib.use('Agg')
            from matplotlib import pyplot as plt
            fig,axes=plt.subplots(1,2,figsize=(10,4))
            axes[0].plot(observed[:,0],observed[:,1],'.',label='Observed');axes[0].plot(prediction[:,0],prediction[:,1],label='Farkas fit');axes[0].set(xlabel='x (m)',ylabel='y (m)');axes[0].legend()
            axes[1].plot(times-times[0],observed[:,2],'.');axes[1].plot(times-times[0],prediction[:,4]);axes[1].set(xlabel='Time (s)',ylabel='Angle (rad)')
            fig.suptitle(f'{key}: exploratory fit, not independent validation');fig.tight_layout();fig.savefig(out/f'Farkas_preview_{key}.png',dpi=130);plt.close(fig)
        except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:result['free_motion'].append({'chip_id':key,'status':'fit_failed','reason':str(exc)})
    atomic_json(out/'physics_preview.json',result)
    return result
