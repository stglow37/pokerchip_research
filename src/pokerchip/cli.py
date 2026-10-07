"""CLI entry points call the same services used by the GUI."""
import argparse
from pathlib import Path
import sys
from .core.storage import read_json,atomic_json,dumps
from .core.config import create_project,load_project,save_project,register,relink


def main(argv=None):
    parser=argparse.ArgumentParser(description="포커칩 연구: 관측·물리 예측 분리, SI 단위")
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("init",help="새 연구 프로젝트");p.add_argument("folder")
    p=commands.add_parser("demo",help="합성 영상/피팅 fixture 생성");p.add_argument("folder");p.add_argument("--frames",type=int,default=90)
    p=commands.add_parser("add",help="외부 원본 등록; --chips 생략 시 개수 자동 인식");p.add_argument("folder");p.add_argument("videos",nargs="+");p.add_argument("--chips",nargs="+")
    p=commands.add_parser("analyze",help="단일 worker batch; 재실행으로 완료 캐시/중단 checkpoint 재개");p.add_argument("folder");p.add_argument("--ids",nargs="+")
    p=commands.add_parser("auto",help="GUI와 같은 자동 구간·보정·개수·계측·파일 저장");p.add_argument("folder");p.add_argument("--ids",nargs="+")
    p=commands.add_parser("inspect",help="streaming PTS·회전 메타데이터 검사");p.add_argument("video");p.add_argument("--output",required=True)
    p=commands.add_parser("calibrate",help="ChArUco 영상 calibration");p.add_argument("video");p.add_argument("board_json");p.add_argument("output");p.add_argument("--mode",required=True)
    p=commands.add_parser("fit",help="검증된 데이터셋 단계별 피팅");p.add_argument("dataset");p.add_argument("output");p.add_argument("--bootstrap",type=int,default=0)
    p=commands.add_parser("simulate",help="SI 초기 상태의 완전 전방 예측");p.add_argument("settings");p.add_argument("output")
    p=commands.add_parser("export",help="run 표/그래프 재생성");p.add_argument("run");p.add_argument("--overlay-source")
    p=commands.add_parser("relink",help="해시 검증 후 외부 원본 재연결");p.add_argument("folder");p.add_argument("experiment_id");p.add_argument("video")
    p=commands.add_parser("gui",help="한국어 GUI 실행");p.add_argument("folder",nargs="?")
    p=commands.add_parser("quality",help="프로젝트 준비 상태와 품질 요약");p.add_argument("folder")
    p=commands.add_parser("validate-labels",help="독립 정답과 자동 관측 비교");p.add_argument("run");p.add_argument("labels")
    p=commands.add_parser("profile",help="충돌 계수 robust 목적함수 profile");p.add_argument("dataset");p.add_argument("fit");p.add_argument("output");p.add_argument("--points",type=int,default=9)
    p=commands.add_parser('study-train',help='v6 구간별 계수·집계·신뢰도');p.add_argument('folder')
    p=commands.add_parser('submission',help='분담 분석 제출 manifest 생성');p.add_argument('folder');p.add_argument('--analyst',required=True)
    p=commands.add_parser('study-test',help='저장 계수 고정 검증');p.add_argument('folder');p.add_argument('constants')
    p=commands.add_parser('integration-inspect',help='분담 제출본 읽기 전용 검사');p.add_argument('folders',nargs='+');p.add_argument('--selections')
    p=commands.add_parser('integrate',help='해결된 제출본을 새 프로젝트로 통합');p.add_argument('destination');p.add_argument('folders',nargs='+');p.add_argument('--selections')
    args=parser.parse_args(argv)
    try:
        if args.command=="init":create_project(args.folder)
        elif args.command=="demo":
            from .application.demo import make_demo
            make_demo(args.folder,args.frames)
        elif args.command=="add":
            p=load_project(args.folder)
            added=register(args.folder,p,args.videos,args.chips or ['chip_1'])
            for e in added:e.update(count_mode='manual' if args.chips else 'auto',quick_workflow=True)
            save_project(args.folder,p)
        elif args.command=="analyze":
            from .application.jobs import Batch
            p=load_project(args.folder);batch=Batch(args.folder,p,lambda x:print(dumps(x),flush=True))
            try:result=batch.run(args.ids)
            except KeyboardInterrupt:batch.cancel();raise
            for r in result:
                exp=next(e for e in p["experiments"] if e["id"]==r["experiment_id"])
                exp["status"]=r["status"]
                if r.get("source_hash"):exp["source_hash"]=r["source_hash"]
                if r.get("run"):exp["last_run"]=str(Path(r["run"]).resolve().relative_to(Path(args.folder).resolve()))
            save_project(args.folder,p)
            if any(r["status"]=="failed" for r in result):return 2
        elif args.command=="auto":
            from .application.automatic import run_automatic
            from .application.jobs import Control
            result=run_automatic(args.folder,load_project(args.folder),Control(),lambda x:print(dumps(x),flush=True),args.ids)
            if any(r['status']=='failed' for r in result['results']):return 2
        elif args.command=="inspect":
            from .measurement.video import metadata,frames
            from .application.exporting import table_csv,FIELDS
            output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
            atomic_json(output/"metadata.json",metadata(args.video))
            table_csv(output/"timing.csv",FIELDS["frames"],(t for t,_ in frames(args.video)))
        elif args.command=="calibrate":
            from .measurement.calibration import charuco_video
            atomic_json(args.output,charuco_video(args.video,read_json(args.board_json),args.mode))
        elif args.command=="fit":
            from .models.fitting import fit_dataset
            fit_dataset(read_json(args.dataset),args.output,args.bootstrap)
        elif args.command=="simulate":
            from .models.fitting import body_from_dict
            from .models.physics.simulator import simulate
            cfg=read_json(args.settings)
            if cfg.get("mode")!="synthetic_demo" and (cfg.get("time_status")!="verified" or cfg.get("geometry_status")!="verified"):
                raise ValueError("실험 simulation 입력의 시간/기하 검증 필요")
            atomic_json(args.output,simulate(cfg["initial"],[body_from_dict(b) for b in cfg["bodies"]],cfg["times"],cfg["mu_bottom"],cfg["e_normal"],cfg["e_tangential"],cfg["mu_collision"],cfg.get("model","contact_consistent_reconstruction")))
        elif args.command=="export":
            from .application.exporting import export_run,overlay
            export_run(args.run)
            if args.overlay_source:overlay(args.run,args.overlay_source)
        elif args.command=="relink":
            p=load_project(args.folder);relink(args.folder,p,args.experiment_id,args.video)
        elif args.command=="gui":
            from .ui.main_window import main as gui_main
            gui_main(args.folder)
        elif args.command=="quality":
            from .analysis.quality import project_status
            print(dumps(project_status(load_project(args.folder),args.folder)))
        elif args.command=="validate-labels":
            from .analysis.benchmark import evaluate_labels
            print(dumps(evaluate_labels(args.run,args.labels)))
        elif args.command=="profile":
            from .models.inference import profile_impacts
            from .analysis.validation import split_trials
            data=read_json(args.dataset);fit=read_json(args.fit)["stages"]["impact_conditional"]
            train,_=split_trials(data["impact_trials"],data["split"]["train"],data["split"]["holdout"],data["split"].get("unit","session"))
            atomic_json(args.output,profile_impacts(train,fit,args.points))
        elif args.command=='submission':
            from .application.integration import write_submission
            print(dumps({'path':str(write_submission(args.folder,args.analyst))}))
        elif args.command=='study-train':
            from .models.study import train_constants
            p=load_project(args.folder);result=train_constants(args.folder,p)
            p['constant_bank']=str(Path(result['path']).resolve().relative_to(Path(args.folder).resolve()));save_project(args.folder,p)
            print(dumps(result))
        elif args.command=='study-test':
            from .models.study import evaluate_fixed
            print(dumps(evaluate_fixed(args.folder,load_project(args.folder),args.constants)))
        elif args.command in ('integration-inspect','integrate'):
            from .application.integration import inspect_submissions,integrate_submissions
            choices=read_json(args.selections) if args.selections else None
            if args.command=='integration-inspect':
                result=inspect_submissions(args.folders,choices);print(dumps(result))
                if result['issues']:return 2
            else:print(dumps(integrate_submissions(args.folders,args.destination,choices)))
        return 0
    except Exception as exc:
        print(f"오류: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
