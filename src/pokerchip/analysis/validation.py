"""Whole-video/session splits and explicit prediction categories."""
import numpy as np


def split_trials(trials, train_ids, holdout_ids, unit="session"):
    if unit not in ("session","trial"):raise ValueError("split 단위는 session 또는 trial")
    if set(train_ids)&set(holdout_ids):
        raise ValueError("train/holdout ID 중복")
    key="session_id" if unit=="session" else "id"
    train=[x for x in trials if x[key] in train_ids]
    held=[x for x in trials if x[key] in holdout_ids]
    if not train or not held:
        raise ValueError("학습 및 보류 실험을 각각 지정하세요.")
    if {x["id"] for x in train}&{x["id"] for x in held}:
        raise ValueError("검증 누수")
    return train,held


def metrics(observed, predicted, sigma=None, kind="full_forward"):
    if kind not in ("free_motion","impact_conditional","full_forward"):
        raise ValueError("예측 평가 종류 오류")
    a,b=np.asarray(observed,float),np.asarray(predicted,float)
    if a.shape!=b.shape:
        raise ValueError("평가 배열 shape 불일치")
    valid=np.isfinite(a)&np.isfinite(b)
    error=(a-b)[valid]
    vector_rmse=None
    if a.ndim>=2 and a.shape[-1]==2:
        v=np.all(valid,axis=-1)
        if v.any():vector_rmse=float(np.sqrt(np.mean(np.sum((a-b)**2,axis=-1)[v])))
    return {"prediction_kind":kind,"vector_rmse":vector_rmse,"rmse":float(np.sqrt(np.mean(error**2))) if error.size else None,
            "mae":float(np.mean(abs(error))) if error.size else None,"valid_values":int(valid.sum()),
            "total_values":a.size,"valid_fraction":float(valid.mean()) if valid.size else 0,
            "rmse_definition":"component-wise; vector_rmse is Euclidean 2D RMS when available",
            "coverage95":float(np.mean(abs(a-b)[valid]<=1.96*np.broadcast_to(sigma,a.shape)[valid])) if sigma is not None and error.size else None}


def diagnostics(result, parameter_names):
    J=np.asarray(result.jac)
    singular=np.linalg.svd(J,compute_uv=False)
    rank=int(np.linalg.matrix_rank(J,tol=max(singular[0]*1e-7,1e-10))) if len(singular) else 0
    covariance=np.linalg.pinv(J.T@J)*max(1.,2*result.cost/max(1,J.shape[0]-J.shape[1]))
    sd=np.sqrt(np.maximum(0,np.diag(covariance)))
    denom=np.outer(sd,sd)
    correlation=np.divide(covariance,denom,out=np.zeros_like(covariance),where=denom>0)
    return {"optimizer_success":bool(result.success),"message":str(result.message),"cost":float(result.cost),
            "parameter_names":parameter_names,"jacobian_singular_values":singular.tolist(),"rank":rank,
            "identifiability":"identified_locally" if rank==J.shape[1] and singular[-1]/singular[0]>1e-6 else "weak_or_nonidentifiable",
            "covariance_conditional":covariance.tolist() if rank==J.shape[1] else None,
            "correlation":correlation.tolist() if rank==J.shape[1] else None,
            "uncertainty_status":"local_conditional_only" if rank==J.shape[1] else "unavailable_nonidentifiable",
            "covariance_warning":"국소 선형/robust Jacobian 근사; 공통 계통오차·모델오차 및 비식별 방향의 CI 보증 없음",
            "sensitivity_column_norm":np.linalg.norm(J,axis=0).tolist(),"active_bounds":result.active_mask.tolist()}
