"""Model-conditioned contact states, separate from the measurement export."""
import copy
import numpy as np
from ..core.task import least_squares
from ..core.config import Body
from .physics.farkas import propagate


def reconstruct(event, rows, cfg, mu):
    result=copy.deepcopy(event);tc=event.get('time_s')
    if tc is None:raise ValueError('충돌 시각이 없습니다.')
    states={'pre':[],'post':[]};audit=[]
    for i,key in enumerate(event['pair']):
        body=Body.from_chip(next(c for c in cfg['chips'] if c['id']==key))
        for side in ('pre','post'):
            old=event[side][i];needed=old.get('angle_fit_frames') or old.get('fit_frames',[])
            rr=sorted([r for r in rows if r['chip_id']==key and r['frame_index'] in needed],key=lambda r:r['frame_index'])
            if len(rr)<5 or any(r.get('theta_wrapped_rad') is None or r.get('world_center_m') is None
                    or r.get('physical_time_s') is None or r.get('assignment_ambiguous') or r.get('measurement_warning') for r in rr):
                raise ValueError('충돌 양쪽의 선명한 위치·각도 표본이 부족합니다.')
            ts=np.array([r['physical_time_s'] for r in rr]);ff=np.array([r['frame_index'] for r in rr])
            if np.any(np.diff(ff)!=1) or np.any(np.diff(ts)<=0):raise ValueError('충돌 전후 표본이 연속되지 않습니다.')
            bound=cfg['analysis'].get('omega_bound_rad_s')
            if not bound or max(np.diff(ts))*bound>=np.pi:raise ValueError('충돌 회전각 펼침의 회전 상한이 불충분합니다.')
            obs=np.array([r['world_center_m']+[r['theta_wrapped_rad']] for r in rr]);obs[:,2]=np.unwrap(obs[:,2])
            if np.any(abs(np.diff(obs[:,2]))>bound*np.diff(ts)+.05):raise ValueError('충돌 표식 회전각이 불연속입니다.')
            origin=ts[0] if side=='pre' else tc
            if (side=='pre' and ts[-1]>=tc) or (side=='post' and ts[0]<=tc):raise ValueError('충돌 전후 시간 구간이 겹칩니다.')
            guess=np.r_[obs[0,:2],old['velocity'],obs[0,2],old['omega']]
            if side=='post':guess[:2]=old['position'];guess[4]-=guess[5]*(ts[0]-tc)
            weights=np.array([[max(.0001,np.sqrt(max(0,(r.get('covariance_world') or np.eye(3)*2.5e-7)[j][j]))) for j in (0,1)]+[max(.01,r.get('theta_sigma_rad') or .035)] for r in rr])
            def residual(s):return ((propagate(s,body,mu,ts-origin)[:,[0,1,4]]-obs)/weights).ravel()
            fit=least_squares(residual,guess,max_nfev=100,x_scale='jac',loss='soft_l1')
            if not fit.success:raise ValueError('충돌 시각 상태 추정이 수렴하지 않았습니다.')
            state=propagate(fit.x,body,mu,[tc-origin])[0] if side=='pre' else fit.x
            if np.linalg.matrix_rank(fit.jac)<6:raise ValueError('접촉 상태의 6개 성분을 식별할 수 없습니다.')
            covariance=np.linalg.pinv(fit.jac.T@fit.jac)*max(1.,2*fit.cost/max(1,len(fit.fun)-6))
            if side=='pre':
                eps=1e-6
                J=np.column_stack([(propagate(fit.x+np.eye(6)[j]*eps,body,mu,[tc-origin])[0]-propagate(fit.x-np.eye(6)[j]*eps,body,mu,[tc-origin])[0])/(2*eps) for j in range(6)])
                covariance=J@covariance@J.T
            sig=np.sqrt(np.maximum(0,np.diag(covariance)))
            new=copy.deepcopy(old);new.update(position_sigma=sig[:2].tolist(),velocity_sigma=sig[2:4].tolist(),omega_sigma=float(sig[5]),state_covariance_conditional=covariance.tolist())
            new.update(position=state[:2].tolist(),velocity=state[2:4].tolist(),theta=float(state[4]),omega=float(state[5]))
            states[side].append(new)
            audit.append(dict(chip_id=key,side=side,frames=ff.tolist(),optimizer_success=bool(fit.success),
                              residual_scaled_rms=float(np.sqrt(np.mean(residual(fit.x)**2)))))
    pre,post=states['pre'],states['post']
    d=np.array(pre[1]['position'])-pre[0]['position'];distance=np.linalg.norm(d)
    if distance<1e-8:raise ValueError('충돌 법선을 결정할 수 없습니다.')
    radius=sum(c['radius_m'] for c in cfg['chips'] if c['id'] in event['pair'])
    if abs(distance-radius)>.004:raise ValueError('환산한 접촉 거리 잔차가 4 mm를 초과합니다.')
    n=d/distance;a=(np.array(pre[0]['velocity'])-pre[1]['velocity'])@n;b=(np.array(post[0]['velocity'])-post[1]['velocity'])@n
    if a<=.01 or b>0:raise ValueError('접근 후 분리하는 충돌 상태가 아닙니다.')
    result.update(**states,normal=n.tolist(),a_m_s=float(a),e_n_obs=float(-b/a),
        measurement_e_n_obs=event.get('e_n_obs'),velocity_scope='farkas_fixed_mu_contact_reconstruction',
        reconstruction=dict(mu_fixed=float(mu),time_fixed_s=tc,contact_distance_m=float(distance),fits=audit,
            uncertainty='conditional Jacobian covariance propagated to contact time; fixed-mu/model/clock/geometry systematics excluded'))
    return result
