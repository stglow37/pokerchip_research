"""Reproducible real-video intake smoke. Does not declare scientific accuracy."""
import sys,json,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pokerchip.core.config import create_project,register,save_project,load_project
from pokerchip.application.automatic import run_automatic
from pokerchip.application.jobs import Control
from pokerchip.core.storage import read_json,atomic_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('videos_json');parser.add_argument('output');parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();folder=Path(args.output).resolve()
    if (folder/'project.json').exists():project=load_project(folder)
    else:
        project=create_project(folder,'v5 real-video development verification')
        paths=read_json(args.videos_json)
        for path in paths:
            e=register(folder,project,[path])[0];e.update(count_mode='auto',quick_workflow=True)
        save_project(folder,project)
    start=time.monotonic()
    def progress(v):
        if v.get('frame') is None or v['frame']%100==0:print(json.dumps(v,ensure_ascii=False),flush=True)
    if args.resume:
        from pokerchip.application.pipeline import analyze
        # Finished videos retain their exact proposed interval. Canonical stage
        # fingerprints reuse only raw measurements when analysis code changed.
        for e in project['experiments']:
            if e.get('status')!='complete':continue
            r=analyze(folder,project,e,Control(),progress)
            e['last_run']=str(Path(r['run']).relative_to(folder));save_project(folder,project)
        pending=[e['id'] for e in project['experiments'] if e.get('status')!='complete']
        result=run_automatic(folder,project,Control(),progress,pending)
    else:result=run_automatic(folder,project,Control(),progress)
    summary=[]
    for e in result['project']['experiments']:
        row={k:e.get(k) for k in ('name','status','source_hash','interval','participating_chip_ids','failure_reason')}
        if e.get('last_run'):
            q=read_json(folder/e['last_run']/'export/quality.json')
            row['quality']={k:q.get(k) for k in ('frames','observation_rows','physical_velocity_rows','angular_velocity_rows','initial_30_observations','geometry_status','event_candidates','fit_eligible_events')}
        summary.append(row)
    atomic_json(folder/'verification_summary.json',{'elapsed_s':time.monotonic()-start,'scope':'development_smoke_not_independent_accuracy','videos':summary})
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
