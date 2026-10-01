"""Run provided legacy videos without approving physical time or new marker IDs."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from pokerchip.config import create_project,register,save_project
from pokerchip.jobs import Batch
from pokerchip.storage import atomic_json,read_json,file_hash
from pokerchip.exporting import overlay


def main():
    ap=argparse.ArgumentParser();ap.add_argument("source_folder");ap.add_argument("output_folder");args=ap.parse_args()
    out=Path(args.output_folder);p=create_project(out,"기존 약 60fps 입력 검토 - 시간/보정 미승인")
    p["time_profile"].update(status="pending",evidence="과거 영상의 실제 촬영시간 미확인",segments=[{"p_start":0.,"p_end":None,"t_start":0.,"slow_factor":1.}])
    p["analysis"].update(radius_px=[48,76],roi_px=[0,400,1080,1750],assignment_gate_px=130.,redetect_every=3,identity_mode="legacy_unknown")
    for name,ids in [("1개_004.mp4",["chip_1"]),("2개_001.mp4",["chip_1","chip_2"])]:
        exp=register(out,p,[Path(args.source_folder)/name],ids)[0]
        exp["conditions"]="기존 rim만 존재할 수 있음. 새 두 표식/고정 ID 검증 아님."
    save_project(out,p)
    results=Batch(out,p,lambda x:print(x,flush=True)).run()
    for r in results:
        if r["status"]!="complete":continue
        exp=next(e for e in p["experiments"] if e["id"]==r["experiment_id"])
        exp["last_run"]=str(Path(r["run"]).relative_to(out));exp["source_hash"]=r["source_hash"];exp["status"]="complete"
        overlay(r["run"],exp["video_uri"])
    save_project(out,p);atomic_json(out/"validation_summary.json",results)


if __name__=="__main__":main()
