"""Robust objective profiles and prospective experiment coverage diagnostics."""
import numpy as np
from scipy.optimize import least_squares
from .fitting import gate,body_from_dict,whiten
from .physics.ifr import impact,contact_velocity


def experiment_design(trials):
    rows=[]
    for tr in trials:
        bs=[body_from_dict(b) for b in tr["bodies"]]
        a,c,_,_=contact_velocity(np.asarray(tr["pre"]),bs,tr["normal"])
        rows.append({"id":tr["id"],"a":a,"c":c,"c_over_a":c/a if a>1e-9 else None,"session_id":tr["session_id"]})
    suggestions=[]
    if len({r["session_id"] for r in rows})<3:suggestions.append("서로 다른 촬영 세션을 추가해 계수 반복성과 보류 예측을 검사하세요.")
    if rows and not (any(r["c"]>0 for r in rows) and any(r["c"]<0 for r in rows)):suggestions.append("접선 미끄럼 양/음 조건을 모두 촬영하세요.")
    if len(rows)<10:suggestions.append("현재 충돌 수가 적습니다. 접근속도·impact parameter·초기 spin을 바꾸어 반복하세요.")
    return {"trials":rows,"suggestions":suggestions}


def profile_impacts(trials,fit,points=9,max_nfev=80):
    """Reoptimize the other tangential coefficient and EIV pre-states at each grid.
    e_n remains fixed at its staged estimate. Robust costs are NOT chi-square CIs.
    """
    gate(trials)
    if points<3:raise ValueError("profile grid는 3점 이상")
    bs=[[body_from_dict(b) for b in tr["bodies"]] for tr in trials]
    pre=[np.asarray(tr["pre"],float) for tr in trials];post=[np.asarray(tr["post"],float) for tr in trials]
    params=fit["parameters"];model=fit["model"];use_eiv=fit.get("errors_in_variables",True)
    latent=np.concatenate([np.asarray(p)[:,[2,3,5]].ravel() for p in fit.get("fitted_pre_states",pre)])
    grids={"e_tangential":np.unique(np.r_[np.linspace(-1,1,points),params["e_tangential"]]),
           "mu_collision":np.unique(np.r_[np.linspace(0,min(2,max(.3,params["mu_collision"]*3)),points),params["mu_collision"]])}
    profiles={}
    for fixed,grid in grids.items():
        other="mu_collision" if fixed=="e_tangential" else "e_tangential";results=[]
        for value in grid:
            def residual(x):
                et=value if fixed=="e_tangential" else x[0];mu=value if fixed=="mu_collision" else x[0]
                values=[]
                for i,(tr,p,q,bodies) in enumerate(zip(trials,pre,post,bs)):
                    actual=p.copy()
                    if use_eiv:actual[:,[2,3,5]]=x[1+6*i:7+6*i].reshape(2,3)
                    out=impact(actual,bodies,params["e_normal"],et,mu,model,normal=tr["normal"],require_contact=False)
                    pred=out.get("post")
                    if pred is None:pred=out.get("candidate_post")
                    if pred is None:raise ValueError("해당 profile에서 지원하지 않는 충돌 상태")
                    values.extend(whiten(pred[:,[2,3,5]]-q[:,[2,3,5]],tr.get("post_sigma",[.01,.01,1]),tr.get("post_covariance")))
                    values.append(max(0.,out.get("delta_energy_formula",0))/max(1e-8,out.get("energy_before",1))*100)
                    if use_eiv:values.extend(whiten(actual[:,[2,3,5]]-p[:,[2,3,5]],tr.get("pre_sigma",[.01,.01,1]),tr.get("pre_covariance")))
                return np.asarray(values)
            start=np.r_[params[other],latent] if use_eiv else np.array([params[other]])
            lower=np.r_[0 if other=="mu_collision" else -1,np.full(len(start)-1,-np.inf)]
            upper=np.r_[2 if other=="mu_collision" else 1,np.full(len(start)-1,np.inf)]
            result=least_squares(residual,start,bounds=(lower,upper),loss="soft_l1",max_nfev=max_nfev,x_scale="jac")
            results.append({"value":float(value),"cost":float(result.cost),"optimizer_success":bool(result.success),"other_estimate":float(result.x[0])})
        minimum=min(r["cost"] for r in results)
        for r in results:r["delta_cost"]=r["cost"]-minimum
        profiles[fixed]=results
    return {"profiles":profiles,"method":"conditional_robust_objective_profile_with_EIV_nuisance_optimization",
            "fixed_e_normal":params["e_normal"],"confidence_interval":None,
            "limitations":"robust loss/branch boundaries: delta cost is not a calibrated likelihood CI; staged normal uncertainty excluded",
            "experiment_design":experiment_design(trials)}
