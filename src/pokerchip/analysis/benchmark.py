"""Independent complete-frame labels, immutable source association and metrics."""
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from ..core.storage import read_json,atomic_json,Records,digest


def save_label(path, frame_index, objects, source_hash, complete=True, split="validation", source="manual_independent"):
    path=Path(path)
    data=read_json(path) if path.exists() else {"schema":"labels-2.0","source_hash":source_hash,"source":source,"split":split,"frames":[]}
    if data.get("locked_hash"):raise ValueError("잠긴 정답 세트는 수정할 수 없습니다. 별도 개발용 사본을 만드세요.")
    if data["source_hash"]!=source_hash:raise ValueError("정답과 영상 원본 hash 불일치")
    if len({o["chip_id"] for o in objects})!=len(objects):raise ValueError("프레임 내 정답 ID 중복")
    for obj in objects:
        if not np.isfinite(obj["center_px"]).all() or obj["radius_px"]<=0:raise ValueError("유효한 정답 중심/반지름 필요")
    item={"frame_index":int(frame_index),"complete":bool(complete),"objects":objects}
    data["frames"]=[f for f in data["frames"] if f["frame_index"]!=frame_index]+[item]
    data["frames"].sort(key=lambda f:f["frame_index"])
    atomic_json(path,data)
    return data


def lock_labels(path):
    data=read_json(path)
    if not any(f["complete"] for f in data["frames"]):raise ValueError("완전 라벨 프레임이 없습니다.")
    data["split"]="locked_test";data.pop("locked_hash",None);data["locked_hash"]=digest(data)
    atomic_json(path,data);return data


def evaluate_labels(run, labels_path):
    run=Path(run);labels=read_json(labels_path);manifest=read_json(run/"manifest.json")
    if labels["source_hash"]!=manifest["source_hash"]:raise ValueError("정답과 분석 원본 hash 불일치")
    if labels.get("locked_hash"):
        check={k:v for k,v in labels.items() if k!="locked_hash"}
        if digest(check)!=labels["locked_hash"]:raise ValueError("locked 정답이 변경되었습니다.")
    tp=fp=fn=identity=matches=switches=0;center=[];angles=[];previous={};evaluated=[]
    with Records(run/"records.sqlite") as db:
        for frame in labels["frames"]:
            if not frame.get("complete"):continue
            f=frame["frame_index"];truth=frame["objects"];pred=list(db.rows("observations",start=f,end=f))
            pairs=[]
            if truth and pred:
                distance=np.array([[np.linalg.norm(np.array(t["center_px"])-p["raw_center_px"]) for p in pred] for t in truth])
                cost=distance.copy()
                for i,t in enumerate(truth):cost[i,distance[i]>.5*t["radius_px"]]=1e9
                rr,cc=linear_sum_assignment(cost)
                pairs=[(i,j) for i,j in zip(rr,cc) if cost[i,j]<1e9]
            tp+=len(pairs);fp+=len(pred)-len(pairs);fn+=len(truth)-len(pairs)
            for i,j in pairs:
                t,p=truth[i],pred[j];center.append(float(np.linalg.norm(np.array(t["center_px"])-p["raw_center_px"])))
                matches+=1;identity+=p["chip_id"]==t["chip_id"]
                if t["chip_id"] in previous and previous[t["chip_id"]]!=p["chip_id"]:switches+=1
                previous[t["chip_id"]]=p["chip_id"]
                if t.get("angle_rad") is not None and p.get("theta_wrapped_rad") is not None:
                    angles.append(float(abs((p["theta_wrapped_rad"]-t["angle_rad"]+np.pi)%(2*np.pi)-np.pi)))
            evaluated.append(f)
    result={"source_hash":labels["source_hash"],"labels_hash":digest(labels),"code_hash":manifest["code_hash"],
        "run_id":manifest["id"],"split":labels.get("split"),"labelled_frames":evaluated,"complete_frames":len(evaluated),
        "tp":tp,"fp":fp,"fn":fn,"recall":tp/(tp+fn) if tp+fn else None,"precision":tp/(tp+fp) if tp+fp else None,
        "false_positives_per_frame":fp/len(evaluated) if evaluated else None,"matched_id_accuracy":identity/matches if matches else None,
        "id_switches_between_labelled_frames":switches,"center_median_px":float(np.median(center)) if center else None,
        "center_rmse_px":float(np.sqrt(np.mean(np.square(center)))) if center else None,
        "angle_mae_deg":float(np.degrees(np.mean(angles))) if angles else None,"angle_matched_samples":len(angles),
        "label_source":labels.get("source","manual_independent"),
        "scope":"raw automatic observations on labelled subset; synthetic results do not validate smartphone accuracy"}
    atomic_json(run/"export/label_validation.json",result)
    return result
