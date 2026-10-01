"""Reproducible FHD 240 capture / 30 playback fixture and GUI evidence.
Synthetic metrics do not establish smartphone accuracy.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
import argparse
from fractions import Fraction
import av
import numpy as np
from pokerchip.demo import make_demo,render_disks
from pokerchip.config import create_project,save_project,register
from pokerchip.pipeline import analyze
from pokerchip.storage import atomic_json,file_hash,read_json,Records
from pokerchip.benchmark import save_label,evaluate_labels


def validate(out,count=120):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);folder=out/"samsung_synthetic"
    p=create_project(folder,"FHD 240→30fps 합성 시간·계측 검증")
    p["mode"]="synthetic_demo"
    p["time_profile"].update(status="synthetic_known_clock",evidence="generator physical i/240; PTS i/30")
    p["analysis"].update(radius_px=[59,69],omega_bound_rad_s=30,redetect_every=5)
    p["calibration"].update(status="synthetic",H=[[.02/64,0,0],[0,-.02/64,.3375],[0,0,1]],image_size=[1920,1080],capture_mode="synthetic")
    for i,c in enumerate(p["chips"]):
        c.update(mass_kg=.01,inertia_model="uniform_disk",radius_status="synthetic",radius_sigma_m=.00001)
        p["templates"][c["id"]]={"delta_inner_minus_rim_rad":[1.1,-1.5,2.2][i],"inner_radius_ratio":[.42,.58,.49][i],"rim_radius_ratio":.87}
    path=folder/"FHD240_slow8.mp4";truth=[]
    with av.open(str(path),"w") as container:
        stream=container.add_stream("libx264",rate=30);stream.width=1920;stream.height=1080;stream.pix_fmt="yuv420p";stream.options={"crf":"16","preset":"fast"}
        for i in range(count):
            t=i/240;centers=[[300+500*t,240+50*t],[980-240*t,550],[1500-350*t,850-120*t]];angles=[4*t,-7*t,11*t]
            image=render_disks(centers,angles,radius=64,size=(1920,1080))
            frame=av.VideoFrame.from_ndarray(image,format="bgr24");frame.pts=i;frame.time_base=Fraction(1,30)
            for packet in stream.encode(frame):container.mux(packet)
            truth.append({"frame_index":i,"centers":centers,"angles":angles})
        for packet in stream.encode():container.mux(packet)
    exp=register(folder,p,[path])[0];save_project(folder,p)
    result=analyze(folder,p,exp);exp.update(status="complete",last_run=str(Path(result["run"]).relative_to(folder)),source_hash=result["source_hash"]);save_project(folder,p)
    labels=folder/"labels"/(exp["id"]+".json")
    for row in truth:
        save_label(labels,row["frame_index"],[{"chip_id":f"chip_{j+1}","center_px":c,"radius_px":64,"angle_rad":row["angles"][j]} for j,c in enumerate(row["centers"])],result["source_hash"],source="synthetic_generator")
    metrics=evaluate_labels(result["run"],labels)
    with Records(Path(result["run"])/"records.sqlite") as db:
        last=list(db.rows("frames"))[-1]
    summary={"fixture":"synthetic FHD 240 capture; PTS 30fps; factor8", "frames":count,
             "physical_last_s":last["physical_time_s"],"expected_physical_last_s":(count-1)/240,
             "metrics":metrics,"quality":read_json(Path(result["run"])/"export/quality.json"),
             "runtime":read_json(Path(result["run"])/"manifest.json")["runtime"]}
    atomic_json(out/"fhd240_validation.json",summary)
    from PySide6.QtWidgets import QApplication
    from pokerchip.gui import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(folder);w.show();app.processEvents()
    w.tabs.setCurrentIndex(5);app.processEvents();w.grab().save(str(out/"dashboard.png"))
    w.tabs.setCurrentIndex(1);app.processEvents();w.grab().save(str(out/"setup.png"));w.close();app.processEvents()
    print(f"Saved {out}; {count} frames; center RMSE={metrics['center_rmse_px']}; recall={metrics['recall']}")
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("output");parser.add_argument("--frames",type=int,default=120)
    args=parser.parse_args();validate(args.output,args.frames)
