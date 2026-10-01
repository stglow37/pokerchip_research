"""Non-destructive in-memory upgrade; save_project backs up a v1 file first."""
import copy

def migrate(project):
    p=copy.deepcopy(project)
    if p.get("schema_version")=="2.0":
        p.setdefault("review_schema_version",1)
        return p
    if p.get("schema_version")!="1.0":raise ValueError("알 수 없는 프로젝트 버전")
    p["schema_version"]="2.0"
    p["analysis"].setdefault("detector_profile","dark_chip")
    p["time_profile"].setdefault("preset","migrated_preserved")
    c=p["calibration"]
    if c.get("status")=="verified":
        from ..analysis.quality import calibration_gate
        c["validation"]=calibration_gate(c)
        if not c["validation"]["passed"]:c["status"]="pending"
    p["migration"]={"from":"1.0","to":"2.0","original_time_preserved":True,
                    "note":"v1 실행 결과 보존. v2 결과는 재분석 시 새 run으로 저장."}
    return p
