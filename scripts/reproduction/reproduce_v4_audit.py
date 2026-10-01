"""Reproduce this full-recording diagnostic; NOT release-approved physics data.

Run from any directory:
  python reproduce_v4_audit.py --videos /path/to/videos --output /path/to/new_audit
The production GUI keeps its normal human start-frame confirmation gate.
"""
import argparse,os,sys,json,subprocess,concurrent.futures
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[2]

def one(name,videos,destination):
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    sys.path.insert(0,str(PACKAGE/'src'))
    import cv2
    cv2.setNumThreads(1)
    from pokerchip.config import create_project,register,load_project
    from pokerchip.jobs import Control
    from pokerchip.automatic import run_automatic
    from pokerchip.storage import file_hash,atomic_json
    import pokerchip.selection as selection
    def boundary(project,e,source_hash=None):
        if e.get('audit_full_recording') is not True or e['interval'] != [0,None]:raise ValueError('Not the declared full-recording diagnostic')
        if source_hash and source_hash!=e['source_hash']:raise ValueError('Source changed')
    selection.require_start=boundary
    folder=destination/Path(name).stem;source=videos/name
    expected={r['video']:r for r in json.loads((PACKAGE/'results/v4/summaries/video_inventory.json').read_text())}
    item=expected[name]
    if source.stat().st_size!=item['bytes'] or file_hash(source)!=item['source_sha256']:raise ValueError('The source does not match the audited video: '+name)
    p=load_project(folder) if (folder/'project.json').exists() else create_project(folder,name)
    e=p['experiments'][0] if p['experiments'] else register(folder,p,[source],['chip_1'])[0]
    e.update(count_mode='auto',quick_workflow=True,audit_full_recording=True,source_hash=item['source_sha256'],impacts_reviewed=False,interval=[0,None])
    cal='20260928_200058' if name[9:15]<'203000' else '20260928_203026'
    p['calibration']=json.loads((PACKAGE/'results/v4/evidence'/(cal+'_calibration.json')).read_text())
    result=run_automatic(folder,p,Control())
    atomic_json(folder/'audit_result.json',{'video':name,'result':result,'scope':'full recording diagnostic; no human release or impact approval'})
    return result['project']['experiments'][0]['status']

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--videos',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--workers',type=int,default=2);ap.add_argument('--one',help=argparse.SUPPRESS)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.one:
        status=one(a.one,a.videos.resolve(),a.output.resolve());print(a.one,status)
        if status!='complete':raise SystemExit(1)
        return
    files=json.loads((PACKAGE/'results/v4/summaries/video_inventory.json').read_text())
    def worker(item):
        name=item['video'];log=a.output/(name+'.log')
        with log.open('w') as f:
            result=subprocess.run([sys.executable,__file__,'--videos',str(a.videos.resolve()),'--output',str(a.output.resolve()),'--one',name],stdout=f,stderr=f)
        print(name,result.returncode,flush=True);return result.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,a.workers)) as pool:
        results=list(pool.map(worker,[x for x in files if x['kind']=='experiment']))
    if any(results):raise SystemExit('Some videos failed; inspect their logs.')
if __name__=='__main__':main()
