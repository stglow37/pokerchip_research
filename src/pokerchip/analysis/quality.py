"""Measurable quality, not an invented overall accuracy percentage."""
import math
from pathlib import Path
from ..core.storage import read_json

DEFAULT_LIMITS={"holdout_rmse_m":.0005,"length_relative_error":.002,"intrinsic_holdout_px":.75}

def calibration_gate(profile):
    limits={**DEFAULT_LIMITS,**profile.get("validation_limits",{})};checks=[]
    if any(not isinstance(x,(float,int)) or not math.isfinite(x) or x<=0 for x in limits.values()):
        raise ValueError("보정 허용오차는 유한한 양수여야 합니다.")
    def add(name,value,limit):
        checks.append({"name":name,"value":value,"limit":limit,"passed":value is not None and math.isfinite(value) and 0<=value<=limit})
    if profile.get("holdout_rmse_m") is not None:add("독립 좌표 RMSE (m)",profile["holdout_rmse_m"],limits["holdout_rmse_m"])
    for i,length in enumerate(profile.get("independent_lengths",[])):
        known=length.get("known_m",0)
        add(f"독립 길이 {i+1} 상대오차",abs(length["error_m"])/known if known>0 else None,limits["length_relative_error"])
    geometric=bool(checks)
    independent=bool(profile.get("independent_lengths")) or profile.get("holdout_reference_independent") is True
    if profile.get("K") is not None:add("렌즈 holdout RMSE (px)",profile.get("holdout_rms_px"),limits["intrinsic_holdout_px"])
    evidence=bool(profile.get("evidence","").strip())
    return {"passed":geometric and evidence and all(c["passed"] for c in checks),"checks":checks,
            "limits":limits,"has_independent_geometry":independent,"absolute_accuracy_passed":independent and evidence and all(c["passed"] for c in checks),"has_evidence":evidence,
            "scope":"supplied_holdout_only; lens_unknown_if_K_missing"}

def enrich_quality(db,quality,config,experiment):
    from collections import deque
    q=dict(quality);ambiguous=partial=review_count=issue_count=0;residual=deque(maxlen=4096);issues=[]
    previous={};max_speed_px_s=0.
    import numpy as np
    from ..core.review import scope
    eligible_total=eligible_observed=0
    for frame in db.rows("frames"):
        f=frame["frame_index"]
        expected=sum(scope(experiment,k,f)["observable"] for k in experiment["participating_chip_ids"])
        eligible_total+=expected
        rows=list(db.rows("manual",start=f,end=f));frame_issues=[]
        for row in rows:
            if row.get('status')=='outside_interval':
                previous.pop(row['chip_id'],None);continue
            old=previous.get(row["chip_id"])
            if old and row.get("physical_time_s") is not None and old.get("physical_time_s") is not None:
                dt=row["physical_time_s"]-old["physical_time_s"]
                if dt>0 and not row.get("assignment_ambiguous") and not old.get("assignment_ambiguous"):
                    max_speed_px_s=max(max_speed_px_s,float(np.linalg.norm(np.array(row["raw_center_px"])-old["raw_center_px"])/dt))
            previous[row["chip_id"]]=row
            ambiguous+=bool(row.get("assignment_ambiguous"));partial+=row.get("status")=="partially_observed"
            if row.get("edge_residual_px") is not None:residual.append(row["edge_residual_px"])
            if row.get("assignment_ambiguous") or row.get("status") in ("low_confidence","partially_observed"):
                frame_issues.append({"frame":f,"chip_id":row["chip_id"],"reason":"ID 모호" if row.get("assignment_ambiguous") else "윤곽 품질 검토"})
            if row.get('theta_wrapped_rad') is None:
                frame_issues.append({'frame':f,'chip_id':row['chip_id'],'channel':'orientation','reason':'회전 표식 미검출 또는 방향 모호: 위치와 별도로 확인'})
            if str(row['chip_id']).startswith('unknown'):
                frame_issues.append({'frame':f,'chip_id':row['chip_id'],'reason':'가림 후 칩 번호를 다시 확인하세요'})
            if row.get('measurement_warning'):frame_issues.append({'frame':f,'chip_id':row['chip_id'],'reason':'경계 적합 오차 큼: 그림자·가림·중심 확인'})
            if row.get('surface_status')=='floor_boundary':frame_issues.append({'frame':f,'chip_id':row['chip_id'],'reason':'바닥 경계: 바깥면 운동과 구분'})
        count=sum(row.get("status") not in ("missing","outside_interval") for row in rows)
        eligible_observed+=count
        if count<expected:frame_issues.append({"frame":f,"reason":f"관측 부족 {count}/{expected}"})
        if expected and frame.get('chip_count_proposal',0)>len(experiment['participating_chip_ids']):frame_issues.append({'frame':f,'reason':'설정한 개수보다 많은 원이 보입니다. 칩 수를 확인하세요'})
        if frame.get('missing_frame_suspected'):frame_issues.append({'frame':f,'reason':'영상 시간 간격이 불규칙합니다'})
        if frame.get("drift",{}).get("status")=="drift_suspected":frame_issues.append({"frame":f,"reason":"카메라 이동 의심"})
        review_count+=bool(frame_issues);issue_count+=len(frame_issues)
        if len(issues)<10000:issues.extend(frame_issues[:10000-len(issues)])
    from ..core.timebase import cadence_report
    readout=config["time_profile"].get("rolling_readout_s");omega=config["analysis"].get("omega_bound_rad_s")
    q.update(expected_visible_chip_frames=eligible_total,observed_visible_chip_frames=eligible_observed,observed_fraction_selected_intervals=eligible_observed/eligible_total if eligible_total else None,ambiguous_id_rows=ambiguous,partially_observed_rows=partial,
             edge_residual_median_px=float(np.median(residual)) if residual else None,edge_residual_is_accuracy=False,
             review_frame_count=review_count,review_issues=issues,review_issues_truncated=issue_count>len(issues),
             edge_residual_summary_scope="last_4096_observations_not_accuracy",
             time_status=config["time_profile"]["status"],geometry_status=config["calibration"]["status"],
             cadence=cadence_report(db.rows("frames"),config["time_profile"].get("capture_fps",240.)),
             detector_profile=config["analysis"].get("detector_profile","dark_chip"),
             rolling_shutter={"status":"bound_only_not_corrected" if readout is not None else "unmeasured",
                 "readout_s":readout,"observed_max_speed_px_s":max_speed_px_s,
                 "position_bias_bound_px":max_speed_px_s*readout if readout is not None else None,
                 "angle_bias_bound_rad":omega*readout if omega is not None and readout is not None else None,
                 "scope":"conservative full-frame bound; apparent velocity can contain tracking errors"},
             interval_selection=experiment.get('start_selection',{}),
             release_verification='human_confirmed' if experiment.get('start_selection',{}).get('method')=='human_release_frame' else 'automatic_not_independently_verified',
             accuracy_explanation="관측 비율은 검출 정답률이 아닙니다. 독립 라벨로 중심·각도 오차와 recall을 측정하세요.")
    return q

def project_status(project,folder=None):
    if not project:return {"next":"새 프로젝트 또는 합성 예제를 여세요.","checks":[],"experiments":[],"ready_for_analysis":False}
    t=project["time_profile"];c=project["calibration"];checks=[]
    checks.append({"label":"시간축","state":"완료" if t["status"] in ("verified","synthetic_known_clock") else "잠정" if t["status"]=="declared" else "필요",
                   "detail":"실제 시간 = 재생 시간 ÷ 배율. 독립 시계로 확인하면 피팅에 사용합니다.","page":1})
    checks.append({"label":"거리 보정","state":"완료" if c["status"] in ("verified","synthetic") else "필요",
                   "detail":"별도 검증점/길이의 오차가 기준을 통과해야 m 단위 결과를 얻습니다.","page":1})
    participants={k for e in project["experiments"] for k in e["participating_chip_ids"]}
    from ..core.config import Body
    bad=[]
    for chip in project["chips"]:
        if chip["id"] not in participants:continue
        try:Body.from_chip(chip)
        except ValueError:bad.append(chip["id"])
    checks.append({"label":"칩 물성","state":"필요" if bad else "완료","detail":"질량·반지름·관성: "+(", ".join(bad) if bad else "입력됨"),"page":1})
    exps=[]
    for exp in project["experiments"]:
        q={};stale=False
        if folder and exp.get("last_run"):
            path=Path(folder)/exp["last_run"]/"export/quality.json"
            if path.exists():
                q=read_json(path)
                from ..application.pipeline import stage_keys
                from ..core.config import effective
                manifest=read_json(path.parent.parent/"manifest.json")
                expected=stage_keys(effective(project,exp),exp,manifest["source_hash"])
                stale=manifest.get("stage_keys",{}).get("export")!=expected["export"]
        exps.append({"id":exp["id"],"name":exp["name"],"status":exp.get("status"),"quality":q,"stale":stale})
    next_action="영상 등록 후 분석을 시작하세요."
    if any(x["quality"].get("review_frame_count",0) for x in exps):next_action="관측 누락·ID·충돌 후보가 있는 프레임을 먼저 검토하세요."
    elif exps and all(x["status"]=="complete" for x in exps):next_action="관측 검토 후 학습/보류 세션을 나누어 피팅하세요."
    if c["status"] not in ("verified","synthetic"):next_action="원 검출을 시험할 수 있습니다. 물리량 계산에는 거리 보정이 필요합니다."
    if any(e["stale"] for e in exps):next_action="설정·보정·코드가 바뀐 이전 결과가 있습니다. 새 분석을 실행해 갱신하세요."
    return {"checks":checks,"experiments":exps,"next":next_action,"ready_for_analysis":bool(exps),"accuracy":"독립 정답 평가 전"}
