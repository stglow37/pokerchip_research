"""Staged shared-parameter fitting; trial initial conditions and EIV are explicit."""
import copy
from pathlib import Path
import numpy as np
from ..core.task import least_squares
from ..core.config import Body
from .physics.farkas import propagate
from .physics.ifr import impact
from ..analysis.validation import diagnostics,metrics,split_trials
from ..core.storage import atomic_json,new_id,stamp


def whiten(delta,sigma,covariance=None):
    """Within-observation covariance; missing coordinates use principal submatrices.
    Temporal correlation is handled separately by resampling whole sessions.
    """
    delta=np.asarray(delta,float)
    if delta.ndim!=2:raise ValueError("잔차는 관측 수 × 성분 수 배열")
    valid=np.isfinite(delta)
    if covariance is None:
        s=np.broadcast_to(np.asarray(sigma,float),delta.shape)
        if not np.isfinite(s).all() or np.any(s<=0):raise ValueError("sigma는 유한한 양수")
        return (delta/s)[valid]
    n,d=delta.shape;cov=np.broadcast_to(np.asarray(covariance,float),(n,d,d));values=[]
    for r,c,mask in zip(delta,cov,valid):
        if not mask.any():continue
        c=c[np.ix_(mask,mask)]
        if not np.isfinite(c).all() or not np.allclose(c,c.T,rtol=1e-7,atol=1e-14):raise ValueError("공분산은 유한한 대칭행렬")
        try:L=np.linalg.cholesky(c)
        except np.linalg.LinAlgError as exc:raise ValueError("공분산은 양의 정부호여야 합니다.") from exc
        values.extend(np.linalg.solve(L,r[mask]))
    return np.asarray(values)


def gate(trials):
    if not trials:
        raise ValueError("피팅 실험이 없습니다.")
    for tr in trials:
        if tr.get("time_status") not in ("verified","synthetic_known_clock") or tr.get("geometry_status") not in ("verified","synthetic"):
            raise ValueError(f"{tr.get('id')}: 시간축/기하 검증 전 피팅 금지")
        if tr.get("source") in ("physics_prediction","tracking_prediction"):
            raise ValueError("모델 예측을 독립 관측으로 피팅할 수 없습니다.")
        for key in ("sigma","pre_sigma","post_sigma","normal_sigma","initial_sigma"):
            if key in tr:
                s=np.asarray(tr[key],float)
                if not np.isfinite(s).all() or np.any(s<=0):raise ValueError(f"{key}: 유한한 양수 불확실성 필요")


def body_from_dict(value):
    return Body(value["mass"],value["radius"],value["inertia"],value.get("id","chip"))


def fit_free(trials, starts=(.08,.2), max_nfev=150, exploratory=False):
    if exploratory:
        if not trials or any(tr.get('time_status') not in ('declared','verified','synthetic_known_clock') or tr.get('geometry_status') not in ('provisional','verified','synthetic') or tr.get('source') not in ('reviewed_observations','direct_observations') for tr in trials):
            raise ValueError('탐색 피팅에도 직접 관측과 유효한 잠정 시간·거리 설정이 필요합니다.')
    else:gate(trials)
    for tr in trials:
        if len(tr["times"])>5000:
            raise ValueError("trial당 5000점 이하의 명시적 표본을 선택하세요.")
    bodies=[body_from_dict(tr["body"]) for tr in trials]
    initial=np.concatenate([np.asarray(tr["initial_guess"],float) for tr in trials])
    def residual(params):
        result=[]
        for i,(tr,body) in enumerate(zip(trials,bodies)):
            times=np.asarray(tr["times"],float)
            state=params[1+i*6:7+i*6]
            prediction=propagate(state,body,params[0],times-times[0])
            observed=np.asarray(tr["position_angle"],float)
            delta=prediction[:,[0,1,4]]-observed
            # Trusted unwrapped angles are preferred; a caller can request circular residuals.
            if tr.get("angle_mode")=="wrapped":
                delta[:,2]=(delta[:,2]+np.pi)%(2*np.pi)-np.pi
            sigma=np.broadcast_to(np.asarray(tr.get("sigma",[.0002,.0002,.03])),delta.shape)
            result.extend(whiten(delta,sigma,tr.get("position_angle_covariance")))
            if tr.get("initial_sigma") is not None:
                result.extend((state-np.asarray(tr["initial_guess"]))/np.asarray(tr["initial_sigma"]))
        return np.asarray(result)
    results=[]
    for start in starts:
        params=np.r_[start,initial]
        results.append(least_squares(residual,params,bounds=(np.r_[0.,np.full(len(initial),-np.inf)],np.r_[2.,np.full(len(initial),np.inf)]),
                                     loss="soft_l1",max_nfev=max_nfev,x_scale="jac",ftol=1e-8,xtol=1e-8))
    best=min(results,key=lambda x:x.cost)
    names=["mu_bottom"]+[f"{tr['id']}:{key}" for tr in trials for key in ("x0","y0","vx0","vy0","theta0","omega0")]
    return {"stage":"free_motion","validation_status":"exploratory_not_validated" if exploratory else "reviewed_input_fit",
            "optimizer_success":bool(best.success),"parameters":{"mu_bottom":float(best.x[0])},
            "initial_states":{tr["id"]:best.x[1+i*6:7+i*6].tolist() for i,tr in enumerate(trials)},
            "diagnostics":diagnostics(best,names),"trial_ids":[tr["id"] for tr in trials],
            "physical_status":"admissible" if 0<=best.x[0]<=2 else "invalid",
            "multistart_costs":[float(r.cost) for r in results],"objective":"direct_position_angle_whitened_robust",
            "assumptions":"shared uniform-pressure mu; fixed independently measured inertia/time/scale"}


def fit_impacts(trials, model="contact_consistent_reconstruction", eiv=True, max_nfev=150, exploratory=False,
                fixed_e_normal=None):
    if exploratory:
        if not trials or any(tr.get('time_status') not in ('declared','verified','synthetic_known_clock') or tr.get('geometry_status') not in ('provisional','verified','synthetic') or tr.get('source') not in ('reviewed_observations','direct_observations') for tr in trials):
            raise ValueError('탐색 충돌 피팅에도 직접 관측과 유효한 잠정 시간·거리 설정이 필요합니다.')
    else:gate(trials)
    for tr in trials:
        if tr.get("kind")!="isolated_binary" or not tr.get("approved",False):
            raise ValueError("승인한 고립 2체 충돌만 피팅 가능")
    bodies=[[body_from_dict(b) for b in tr["bodies"]] for tr in trials]
    pre=[np.asarray(tr["pre"],float) for tr in trials]
    post=[np.asarray(tr["post"],float) for tr in trials]
    # First stage: normal coefficient with noisy pre approach speeds as latent values.
    a=[];b=[];sig=[]
    for tr,p,q in zip(trials,pre,post):
        n=np.asarray(tr["normal"],float)
        if n.shape!=(2,) or not np.isfinite(n).all() or np.linalg.norm(n)<1e-12:raise ValueError("유효한 법선 필요")
        n=n/np.linalg.norm(n)
        a.append((p[0,2:4]-p[1,2:4])@n)
        b.append((q[0,2:4]-q[1,2:4])@n)
        # Legacy normal_sigma is the normal RELATIVE VELOCITY sigma (m/s),
        # not the angular uncertainty of the unit normal vector.
        sig.append(tr.get("normal_sigma",.01))
    a,b,sig=np.asarray(a),np.asarray(b),np.asarray(sig)
    if np.any(a<=0):raise ValueError("접근 법선속도 양수 필요")
    if fixed_e_normal is None:
        def normal_res(x):
            actual=x[1:] if eiv else a
            return np.r_[(b+x[0]*actual)/sig,(actual-a)/sig] if eiv else (b+x[0]*actual)/sig
        nfit=least_squares(normal_res,np.r_[.7,a] if eiv else [.7],bounds=(np.r_[0.,np.zeros(len(a))] if eiv else [0.],np.r_[1.,np.full(len(a),np.inf)] if eiv else [1.]),loss="soft_l1")
        en=float(nfit.x[0]);normal_diagnostics=diagnostics(nfit,["e_normal"]+[f"a_{i}" for i in range(len(nfit.x)-1)])
        normal_scope="estimated_inside_impact_fit"
    else:
        en=float(fixed_e_normal)
        if not np.isfinite(en) or not 0<=en<=1:raise ValueError("고정 법선 반발계수는 0..1 범위의 유한값이어야 합니다.")
        normal_diagnostics={"optimizer_success":True,"identifiability":"fixed_from_separate_normal_stage",
                            "active_bounds":[],"uncertainty_status":"inherited_from_separate_normal_stage"}
        normal_scope="fixed_from_separate_position_based_normal_stage"
    # Next stage: et/muc plus optional latent noisy incoming velocity/spin.
    latent=np.concatenate([p[:,[2,3,5]].ravel() for p in pre])
    def tangent_res(x):
        values=[]
        for i,(tr,p,q,bs) in enumerate(zip(trials,pre,post,bodies)):
            actual=p.copy()
            if eiv:
                actual[:,[2,3,5]]=x[2+i*6:8+i*6].reshape(2,3)
            outcome=impact(actual,bs,en,x[0],x[1],model,normal=tr["normal"],require_contact=False)
            candidate=outcome.get("post")
            if candidate is None:candidate=outcome.get("candidate_post")
            if candidate is None:
                raise ValueError(outcome.get("reason","지원되지 않는 충돌"))
            sigma=np.broadcast_to(tr.get("post_sigma",[.01,.01,1.]),(2,3))
            values.extend(whiten(candidate[:,[2,3,5]]-q[:,[2,3,5]],sigma,tr.get("post_covariance")))
            # Continuous penalty, never rescale a non-passive prediction.
            values.append(max(0.,outcome.get("delta_energy_formula",0))/max(1e-8,outcome.get("energy_before",1.))*100)
            if eiv:
                values.extend(whiten(actual[:,[2,3,5]]-p[:,[2,3,5]],tr.get("pre_sigma",[.01,.01,1.]),tr.get("pre_covariance")))
        return np.array(values)
    fits=[]
    for start in ((-.9,.05),(-.5,.2),(-1.,.5)):
        x=np.r_[start,latent] if eiv else np.array(start)
        lower=np.r_[-1.,0.,np.full(len(x)-2,-np.inf)];upper=np.r_[1.,2.,np.full(len(x)-2,np.inf)]
        fits.append(least_squares(tangent_res,x,bounds=(lower,upper),loss="soft_l1",max_nfev=max_nfev,x_scale="jac"))
    best=min(fits,key=lambda x:x.cost)
    fitted_pre=[p.copy() for p in pre]
    if eiv:
        for i,p in enumerate(fitted_pre): p[:,[2,3,5]]=best.x[2+i*6:8+i*6].reshape(2,3)
    outcomes=[impact(p,bs,en,best.x[0],best.x[1],model,normal=tr["normal"],require_contact=False) for tr,p,bs in zip(trials,fitted_pre,bodies)]
    diag=diagnostics(best,["e_tangential","mu_collision"]+[f"latent_pre_{i}" for i in range(len(best.x)-2)])
    branches=[x.get("branch") for x in outcomes]
    if branches and all(b=="sticking" for b in branches):
        diag["identifiability"]="sticking_only_mu_lower_bound"
    return {"stage":"normal_then_tangential","validation_status":"exploratory_not_validated" if exploratory else "reviewed_input_fit","parameters":{"e_normal":en,"e_tangential":float(best.x[0]),"mu_collision":float(best.x[1])},
            "normal_diagnostics":normal_diagnostics,"normal_scope":normal_scope,
            "diagnostics":diag,"physical_status":"admissible" if all(x["status"]=="ok" for x in outcomes) else "invalid",
            "fitted_pre_states":[p.tolist() for p in fitted_pre],
            "outcome_diagnostics":[{k:v for k,v in x.items() if k not in ("post","candidate_post")} for x in outcomes],
            "model":model,"branches":branches,"e_t_obs":[x.get("e_t_obs") for x in outcomes],
            "trial_ids":[tr["id"] for tr in trials],"errors_in_variables":eiv,"multistart_costs":[float(r.cost) for r in fits]}


def bootstrap(trials, fit_function, count=100, seed=0, unit="session"):
    if count<2:raise ValueError("bootstrap은 2회 이상")
    key="session_id" if unit=="session" else "id"
    groups=sorted({tr[key] for tr in trials})
    if len(groups)<2:
        return {"status":"insufficient_independent_groups","count":0,"interval95":None}
    rng=np.random.default_rng(seed);values=[];draws=[];failures=[]
    for iteration in range(count):
        from ..core.task import checkpoint
        checkpoint(f'불확실성 재표본 {iteration+1}/{count}',overall_percent=100*iteration/max(count,1),phase='bootstrap')
        draw=rng.choice(groups,len(groups),replace=True).tolist()
        sample=[]
        # Shared calibration scale drawn once per selected session, not per frame.
        for group_index,group in enumerate(draw):
            rows=copy.deepcopy([tr for tr in trials if tr[key]==group])
            scale=float(np.exp(rng.normal(0,rows[0].get("shared_scale_sigma_fraction",0))))
            clock=float(np.exp(rng.normal(0,rows[0].get("shared_clock_sigma_fraction",0))))
            for tr in rows:
                tr["id"]=tr["id"]+f"_boot{group_index}"
                if "position_angle" in tr:
                    z=np.asarray(tr["position_angle"],float);z[:,:2]*=scale;tr["position_angle"]=z.tolist()
                    times=np.asarray(tr["times"],float);tr["times"]=(times[0]+(times-times[0])*clock).tolist()
                    state=np.asarray(tr["initial_guess"],float);state[:2]*=scale;state[2:4]*=scale/clock;state[5]/=clock
                    tr["initial_guess"]=state.tolist()
                    s=np.asarray(tr.get("sigma",[.0002,.0002,.03]),float).copy();s[..., :2]*=scale;tr["sigma"]=s.tolist()
                    if tr.get("position_angle_covariance") is not None:
                        d=np.array([scale,scale,1.]);cov=np.asarray(tr["position_angle_covariance"],float)
                        tr["position_angle_covariance"]=(cov*d[:,None]*d[None,:]).tolist()
                    if tr.get("initial_sigma") is not None:
                        s=np.asarray(tr["initial_sigma"],float);s[:2]*=scale;s[2:4]*=scale/clock;s[5]/=clock;tr["initial_sigma"]=s.tolist()
                if "pre" in tr:
                    for side in ("pre","post"):
                        s=np.asarray(tr[side],float);s[:,:2]*=scale;s[:,2:4]*=scale/clock;s[:,5]/=clock;tr[side]=s.tolist()
                        sigkey=side+"_sigma";sigma=np.asarray(tr.get(sigkey,[.01,.01,1.]),float).copy()
                        sigma[...,:2]*=scale/clock;sigma[...,2]/=clock;tr[sigkey]=sigma.tolist()
                        covkey=side+"_covariance"
                        if tr.get(covkey) is not None:
                            d=np.array([scale/clock,scale/clock,1/clock]);cov=np.asarray(tr[covkey],float)
                            tr[covkey]=(cov*d[:,None]*d[None,:]).tolist()
                    if 'normal_sigma' in tr:tr['normal_sigma']*=scale/clock
            sample.extend(rows)
        try:
            fit=fit_function(sample)
            if not fit["diagnostics"]["optimizer_success"] or fit["physical_status"]!="admissible" or fit['diagnostics'].get('identifiability')!='identified_locally' or any(fit['diagnostics'].get('active_bounds',[])):
                failures.append({"iteration":iteration,"reason":"optimizer_or_physics"});continue
            values.append(fit["parameters"]);draws.append(draw)
        except (ValueError,ArithmeticError) as exc:
            failures.append({"iteration":iteration,"reason":str(exc)})
    names=list(values[0]) if values else []
    return {"status":"computed" if len(values)>1 else "insufficient_successes","unit":unit,"seed":seed,
            "requested":count,"count":len(values),"draws":draws,"failures":failures,
            "interval95":{n:np.quantile([v[n] for v in values],[.025,.975]).tolist() for n in names} if len(values)>1 else None,
            "samples":values,"scope":"cluster_CI_plus_supplied_shared_scale_and_clock_uncertainty",
            "stability_warning":"적은 bootstrap 표본: 연구용 CI에는 반복수 수렴을 확인하세요." if count<200 else None}


def evaluate_holdout(trials, fit, kind):
    results=[]
    for tr in trials:
        if kind=="free_motion":
            prediction=propagate(tr["initial_guess"],body_from_dict(tr["body"]),fit["parameters"]["mu_bottom"],np.asarray(tr["times"])-tr["times"][0])
            observed=np.asarray(tr["position_angle"]);sigma=np.broadcast_to(tr.get("sigma",[.001,.001,.05]),observed.shape)
            score={"prediction_kind":kind,"position_m":metrics(observed[:,:2],prediction[:,:2],sigma[:,:2],kind),
                   "angle_rad":metrics(observed[:,2],prediction[:,4],sigma[:,2],kind),
                   "stop_in_window":bool(np.linalg.norm(prediction[-1,2:4])<1e-7 and abs(prediction[-1,5])<1e-7)}
        else:
            p=fit["parameters"]
            result=impact(np.asarray(tr["pre"]),[body_from_dict(b) for b in tr["bodies"]],p["e_normal"],p["e_tangential"],p["mu_collision"],fit["model"],normal=tr["normal"],require_contact=False)
            if result["status"]=="ok":
                observed=np.asarray(tr["post"]);sigma=np.broadcast_to(tr.get("post_sigma",[.01,.01,1.]),(2,3))
                score={"prediction_kind":kind,"velocity_m_s":metrics(observed[:,2:4],result["post"][:,2:4],sigma[:,:2],kind),
                       "omega_rad_s":metrics(observed[:,5],result["post"][:,5],sigma[:,2],kind),
                       "J_n":result["J_n"],"J_t":result["J_t"],"momentum_residual":result["momentum_residual"],
                       "angular_momentum_residual":result["angular_momentum_residual"],"energy_change":result["delta_energy_formula"],
                       "pre":tr["pre"],"observed_post":tr["post"],"predicted_post":result["post"]}
            else:score={"status":result["status"],"reason":result["reason"]}
        results.append({"trial_id":tr["id"],**score})
    return results


def fit_dataset(dataset, outdir, bootstrap_count=0):
    from ..application.pipeline import code_digest
    from ..core.storage import digest
    from .. import __version__
    model=dataset.get("model","contact_consistent_reconstruction")
    results={"id":new_id("fit"),"created":stamp(),"split":dataset["split"],"source":"observations","stages":{},
             "code_version":__version__,"code_hash":code_digest(),"code_hashes":{"physics":code_digest("physics")},"dataset_hash":digest(dataset),
             "seed":dataset.get("seed",0),"bootstrap_requested":bootstrap_count,
             "model":model,"model_version":"farkas_v1_ifr_reconstruction_v2",
             "model_scope":"Farkas free-motion model; position-based normal restitution; rotation-dependent tangential IFR extension"}
    atomic_json(Path(outdir)/"dataset.json",dataset)
    split=dataset["split"]
    locked=set(split.get("locked_test",[]))
    if locked & (set(split["train"])|set(split["holdout"])):
        raise ValueError("locked test를 학습/모델선택 보류 세션에 섞을 수 없습니다.")
    for section,func,kind in [("free_trials",fit_free,"free_motion"),("impact_trials",lambda tr:fit_impacts(tr,model),"impact_conditional")]:
        if not dataset.get(section):continue
        train,held=split_trials(dataset[section],split["train"],split["holdout"],split.get("unit","session"))
        result=func(train)
        result["holdout"]=evaluate_holdout(held,result,kind)
        result["research_readiness"]={"optimizer_success":result["diagnostics"]["optimizer_success"],
            "physical_admissible":result["physical_status"]=="admissible",
            "identified_locally":result["diagnostics"]["identifiability"]=="identified_locally",
            "holdout_evaluated":bool(held),"holdout_passed":None,
            "note":"보류 오차 합격은 연구 허용오차와 비교해야 합니다. optimizer 성공만으로 정확도를 보증하지 않습니다."}
        if bootstrap_count:
            result["bootstrap"]=bootstrap(train,func,bootstrap_count,dataset.get("seed",0),split.get("unit","session"))
        results["stages"][kind]=result
    if not results["stages"]:raise ValueError("피팅 데이터가 없습니다.")
    atomic_json(Path(outdir)/"fit.json",results)
    return results
