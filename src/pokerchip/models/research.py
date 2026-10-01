"""Bridge reviewed observations to fitting and independent model comparison."""
from pathlib import Path
import numpy as np
from ..core.config import Body
from ..core.storage import Records,read_json,atomic_json
from .physics.simulator import simulate
from ..analysis.validation import metrics


def properties(chip):
    b=Body.from_chip(chip)
    return {"mass":b.mass,"radius":b.radius,"inertia":b.inertia,"id":b.id}


def free_trial(run,chip_id,start,end):
    run=Path(run);cfg=read_json(run/"effective_settings.json");exp=read_json(run/"experiment.json")
    chip=next(c for c in cfg["chips"] if c["id"]==chip_id)
    with Records(run/"records.sqlite") as db:
        if any(chip_id in e["pair"] and not (e["frame_end"]<start or e["frame_start"]>end) for e in db.rows("events")):
            raise ValueError("선택 자유운동 구간에 충돌 후보가 있습니다.")
        rows=list(db.rows("trajectories",chip_id,start,end))
        observations=list(db.rows("manual",chip_id,start,end))
    if len(rows)<6 or len(rows)>5000:raise ValueError("자유운동 구간은 6..5000 관측 표본")
    first=next((r for r in rows if r.get("vx_m_s") is not None and r.get("omega_rad_s") is not None),None)
    if first is None:raise ValueError("검증된 위치·속도·회전·시간 및 alias 상한이 필요합니다.")
    observations=[r for r in observations if r["frame_index"]>=first["frame_index"] and r.get("physical_time_s") is not None and r.get("world_center_m") is not None and r.get("theta_wrapped_rad") is not None and r["status"] not in ("missing","low_confidence") and not r.get("assignment_ambiguous") and not r.get("measurement_warning")]
    if len(observations)<6:raise ValueError("직접 위치/각도 관측 부족")
    if any(b["frame_index"]!=a["frame_index"]+1 for a,b in zip(observations,observations[1:])):raise ValueError("결측을 가로지르는 회전 피팅 금지: 연속 구간을 선택하세요.")
    angles=np.unwrap([r["theta_wrapped_rad"] for r in observations])
    bound=cfg["analysis"].get("omega_bound_rad_s")
    dt=np.diff([r["physical_time_s"] for r in observations])
    if bound is None or np.any(dt<=0) or np.any(dt*bound>=np.pi) or np.any(abs(np.diff(angles))>dt*bound+.05):
        raise ValueError("선택 자유운동 구간의 회전 alias 상한 검증 실패")
    sigma=np.array([[max(1e-6,np.sqrt(np.array(r.get("covariance_world") or np.eye(3)*1e-8)[j,j])) for j in (0,1)]+[max(.005,r.get("theta_sigma_rad") or .05)] for r in observations])
    return {"id":exp["id"]+f"_{chip_id}_{start}_{end}","session_id":exp["session_id"],"source":"reviewed_observations",
            "source_run":run.name,"time_status":cfg["time_profile"]["status"],"geometry_status":cfg["calibration"]["status"],
            "body":properties(chip),"times":[r["physical_time_s"] for r in observations],
            "position_angle":[r["world_center_m"]+[float(a)] for r,a in zip(observations,angles)],
            "sigma":sigma.tolist(),"uncertainty_note":"프레임별 경계/각도 조건부 sigma; 공통 시간·보정 오차는 별도 전달",
            "shared_scale_sigma_fraction":cfg["analysis"].get("shared_scale_sigma_fraction",0.),
            "shared_clock_sigma_fraction":cfg["analysis"].get("shared_clock_sigma_fraction",0.),
            "initial_guess":first["world_center_m"]+[first["vx_m_s"],first["vy_m_s"],float(angles[0]),first["omega_rad_s"]]}


def impact_trials(run):
    run=Path(run);cfg=read_json(run/"effective_settings.json");exp=read_json(run/"experiment.json")
    with Records(run/"records.sqlite") as db:events=list(db.rows("events"))
    result=[]
    for event in events:
        if not event.get("fit_eligible"):continue
        if any(s.get("omega") is None for side in ("pre","post") for s in event[side]):continue
        bodies=[properties(next(c for c in cfg["chips"] if c["id"]==key)) for key in event["pair"]]
        states={side:[s["position"]+s["velocity"]+[s["theta"],s["omega"]] for s in event[side]] for side in ("pre","post")}
        result.append({"id":exp["id"]+"_"+event["id"],"session_id":exp["session_id"],"source":"reviewed_observations","source_run":run.name,
                       "time_status":cfg["time_profile"]["status"],"geometry_status":cfg["calibration"]["status"],"kind":"isolated_binary",
                       "approved":True,"normal":event["normal"],"bodies":bodies,**states,
                       "pre_sigma":[s["velocity_sigma"]+[max(1e-6,s.get("omega_sigma") or 1.)] for s in event["pre"]],
                       "post_sigma":[s["velocity_sigma"]+[max(1e-6,s.get("omega_sigma") or 1.)] for s in event["post"]],
                       "normal_sigma":max(1e-6,float(np.sqrt(sum(np.sum(np.square(s["velocity_sigma"])) for s in event["pre"])))),
                       "shared_scale_sigma_fraction":cfg["analysis"].get("shared_scale_sigma_fraction",0.),
                       "shared_clock_sigma_fraction":cfg["analysis"].get("shared_clock_sigma_fraction",0.)})
    return result


def compare_forward(run,parameters,start_frame=None,end_frame=None):
    run=Path(run);cfg=read_json(run/"effective_settings.json");exp=read_json(run/"experiment.json")
    ids=exp["participating_chip_ids"]
    if any(parameters.get(k) is None for k in ("mu_bottom","e_normal","e_tangential","mu_collision")):
        raise ValueError("검증할 고정 물리계수를 모두 입력하세요.")
    bodies=[Body.from_chip(next(c for c in cfg["chips"] if c["id"]==key)) for key in ids]
    byframe={}
    with Records(run/"records.sqlite") as db:
        for row in db.rows("trajectories",start=start_frame,end=end_frame):
            if row["chip_id"] in ids and all(row.get(k) is not None for k in ("physical_time_s","world_center_m","vx_m_s","vy_m_s","omega_rad_s","theta_wrapped_rad")):
                byframe.setdefault(row["frame_index"],{})[row["chip_id"]]=row
            if len(byframe)>20000:raise ValueError("비교 구간을 20000프레임 이하로 나누세요.")
    complete=[(f,r) for f,r in sorted(byframe.items()) if len(r)==len(ids)]
    if len(complete)<2:raise ValueError("모든 참여 칩의 공통 초기 상태/시간이 부족합니다.")
    first=complete[0][1];t0=first[ids[0]]["physical_time_s"]
    initial=[first[k]["world_center_m"]+[first[k]["vx_m_s"],first[k]["vy_m_s"],first[k]["theta_wrapped_rad"],first[k]["omega_rad_s"]] for k in ids]
    times=np.array([r[ids[0]]["physical_time_s"]-t0 for _,r in complete])
    simulation=simulate(initial,bodies,times,parameters["mu_bottom"],parameters["e_normal"],parameters["e_tangential"],parameters["mu_collision"],parameters.get("model","contact_consistent_reconstruction"))
    observed=np.array([[r[k]["world_center_m"]+[r[k]["vx_m_s"],r[k]["vy_m_s"],r[k]["theta_wrapped_rad"],r[k]["omega_rad_s"]] for k in ids] for _,r in complete])
    n=len(simulation["states"]);pred=simulation["states"]
    scores={key:metrics(observed[:n,:,columns],pred[:,:,columns],kind="full_forward") for key,columns in (("position_m",[0,1]),("velocity_m_s",[2,3]),("omega_rad_s",[5]))} if n else {}
    result={"prediction_kind":"full_forward","initial_source":"first_common_observed_state","source_run":run.name,
            "initial_frame":complete[0][0],"parameters":parameters,"simulation":simulation,"metrics":scores}
    atomic_json(run/"export/forward_comparison.json",result)
    if n:
        from matplotlib import pyplot as plt
        fig,ax=plt.subplots(figsize=(8,6))
        for i,k in enumerate(ids):
            ax.plot(observed[:n,i,0],observed[:n,i,1],".",ms=3,label=k+" observation")
            ax.plot(pred[:,i,0],pred[:,i,1],"-",label=k+" physics prediction")
        ax.set(xlabel="x (m)",ylabel="y (m)",title="Full forward comparison");ax.legend();ax.grid(alpha=.25)
        fig.savefig(run/"export/forward_comparison.png",dpi=140);plt.close(fig)
    return result
