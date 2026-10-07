"""Replay frozen ZIP raw observations, without retracking or changing the ZIP."""
import argparse
import copy
import json
import time
import zipfile
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pokerchip.core.config import default_project, effective, save_project
from pokerchip.core.storage import Records, atomic_json, read_json
from pokerchip.application.pipeline import derive, stage_keys, code_digest
from pokerchip.application.exporting import export_run
from pokerchip.models.study import train_constants, evaluate_fixed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('zip');parser.add_argument('destination')
    args=parser.parse_args();dest=Path(args.destination).resolve()
    if dest.exists():raise ValueError('기존 결과를 덮어쓰지 않습니다. 새 폴더 필요')
    dest.mkdir(parents=True);start=time.perf_counter();comparisons=[]
    with zipfile.ZipFile(args.zip) as archive:
        project_name=next(n for n in archive.namelist() if n.endswith('/project.json') and '/runs/' not in n)
        base=project_name[:-len('project.json')]
        project=json.loads(archive.read(project_name));project=copy.deepcopy(project)
        defaults=default_project()['analysis']
        project['analysis'].update({k:defaults[k] for k in ('free_segment_duration_s','coefficient_bootstrap_count','compare_joint_fit','tangential_bootstrap_count')})
        project.pop('constant_bank',None)
        for e in project['experiments']:
            old_run=e['last_run'].replace('\\','/');prefix=base+old_run+'/'
            cfg=json.loads(archive.read(prefix+'effective_settings.json'))
            manifest=json.loads(archive.read(prefix+'manifest.json'))
            old_events=[json.loads(line) for line in archive.read(prefix+'export/events.jsonl').decode('utf8').splitlines() if line]
            old_rows=[json.loads(line) for line in archive.read(prefix+'export/trajectories.jsonl').decode('utf8').splitlines() if line]
            target=dest/'runs'/('v6_'+Path(old_run).name);target.mkdir(parents=True)
            atomic_json(target/'frozen_v5_manifest.json',manifest)
            frozen=target/'frozen_v5.sqlite';frozen.write_bytes(archive.read(prefix+'records.sqlite'))
            for k in ('analysis','time_profile','calibration','templates'):e[k]=copy.deepcopy(cfg[k])
            e['analysis'].update({k:defaults[k] for k in ('free_segment_duration_s','coefficient_bootstrap_count','compare_joint_fit','tangential_bootstrap_count')})
            e['last_run']=str(target.relative_to(dest));cfg=effective(project,e)
            with Records(frozen,readonly=True) as old,Records(target/'records.sqlite') as new:
                for table in ('frames','observations','predictions'):
                    for row in old.rows(table):new.put(table,row['frame_index'],row.get('chip_id',''),row)
                new.db.commit()
            started=time.perf_counter()
            derive(target/'records.sqlite',cfg,e,lambda:None,lambda *a:None)
            manifest.update(id=target.name,status='complete',stage_keys=stage_keys(cfg,e,manifest['source_hash']),code_hash=code_digest(),replay_scope='raw frozen observations, no retracking',prior_run=old_run)
            manifest.setdefault('code_hashes',{}).update({k:code_digest(k) for k in ('analysis','physics','export')})
            atomic_json(target/'manifest.json',manifest);atomic_json(target/'effective_settings.json',cfg);atomic_json(target/'experiment.json',e)
            export_run(target)
            with Records(target/'records.sqlite',readonly=True) as db:
                rows=list(db.rows('trajectories'));events=list(db.rows('events'))
            select=lambda rr:[{k:r.get(k) for k in ('chip_id','frame_index','status','measurement_warning','vx_m_s','vy_m_s','omega_rad_s','reason','calculation_status','warning_observation_refs')} for r in rr if (r['chip_id'],r['frame_index']) in [('chip_1',212),('chip_2',221)]]
            comparisons.append({'video':e['name'],'elapsed_s':time.perf_counter()-started,'v5_events':old_events,'v6_events':events,'v5_selected_frames':select(old_rows),'v6_selected_frames':select(rows)})
            print(json.dumps({'video':e['name'],'events':[(ev['kind'],ev.get('e_n_obs')) for ev in events]},ensure_ascii=True),flush=True)
        old_constants=next(n for n in archive.namelist() if n.endswith('/constants.json'))
        prior=json.loads(archive.read(old_constants))
    save_project(dest,project)
    fit_start=time.perf_counter();bank=train_constants(dest,project)
    project['constant_bank']=str(Path(bank['path']).relative_to(dest));save_project(dest,project)
    report={'scope':'Same frozen v5 raw observations; no source video measurement re-run. Development replay, not independent physical validation.',
        'zip':str(Path(args.zip).resolve()),'comparisons':comparisons,'v5_parameters':prior['parameters'],
        'v6_constants':bank,'coefficient_elapsed_s':time.perf_counter()-fit_start,'total_elapsed_s':time.perf_counter()-start}
    if any(e.get('fit_role')=='test' for e in project['experiments']):report['validation']=evaluate_fixed(dest,project,bank['path'])
    atomic_json(dest/'v6_zip_comparison.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
