"""Measured 52-file synthetic queue and process RSS, not a real FHD240 claim."""
import argparse
import platform
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
import psutil
from pokerchip.config import create_project,register
from pokerchip.demo import make_video
from pokerchip.jobs import Batch
from pokerchip.storage import atomic_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument("output");ap.add_argument("--jobs",type=int,default=52);args=ap.parse_args()
    folder=Path(args.output);p=create_project(folder,"52개 합성 파일 처리 검사")
    p["analysis"].update(radius_px=[28,36],chunk_frames=2)
    paths=[]
    for i in range(args.jobs):paths.append(make_video(folder/"inputs"/str(i)/"동일 파일명.mp4",count=4,kind="single",seed=i))
    corrupt=folder/"inputs"/"손상.mp4";corrupt.write_bytes(b"unsupported corrupt container")
    paths.insert(12,corrupt);register(folder,p,paths,["chip_1"])
    samples=[];start=time.perf_counter();process=psutil.Process()
    def callback(event):
        samples.append({"elapsed_s":time.perf_counter()-start,"rss_bytes":process.memory_info().rss,"stage":event.get("stage"),"status":event.get("status")})
        if event.get("status"):print(event["status"],event.get("experiment_id"),flush=True)
    result=Batch(folder,p,callback).run()
    report={"host":platform.platform(),"processor":platform.processor(),"logical_cpu":psutil.cpu_count(),"system_ram_bytes":psutil.virtual_memory().total,
            "fixture":{"width":640,"height":400,"fps":60,"frames_per_file":4,"unique_valid_files":args.jobs,"corrupt_files":1},
            "elapsed_s":time.perf_counter()-start,"peak_rss_sampled_bytes":max(x["rss_bytes"] for x in samples),"rss_samples":samples,
            "completed":sum(x["status"]=="complete" for x in result),"failed":sum(x["status"]=="failed" for x in result),
            "worker_count":1,"limitation":"Short synthetic batch only; real FHD240 throughput and long-duration soak pending."}
    atomic_json(folder/"benchmark.json",report)
    assert report["completed"]==args.jobs and report["failed"]==1
    assert result[-1]["status"]=="complete"


if __name__=="__main__":main()
