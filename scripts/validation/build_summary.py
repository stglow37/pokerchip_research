from pathlib import Path
import argparse,json,csv,collections
parser=argparse.ArgumentParser(description='v3.5/v4 감사 실행에서 요약 JSON과 CSV를 생성합니다.')
parser.add_argument('--audit-root',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();root=args.audit_root.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
inventory=json.load(open(root/'inventory_manifest.json'));rows=[]
for item in sorted(inventory,key=lambda x:x['video']):
 r=dict(item);name=Path(item['video']).stem
 if item['kind']=='calibration':
  c=json.load(open(root/'evidence'/(name+'_calibration.json')));r.update(calibration_holdout_px=c.get('holdout_rms_px'),calibration_stable_end=c['automatic_report']['stable_end']);rows.append(r);continue
 for ver,label in [('baseline','v35_default'),('v4final','v4_calibrated')]:
  folder=root/('runs_'+ver)/name;projectfile=folder/'project.json'
  if not projectfile.exists():r[label+'_status']='not_started';continue
  p=json.load(open(projectfile));e=p['experiments'][0]
  r[label+'_status']='publication_failed' if (folder/'audit_error.txt').exists() else 'running'
  if (folder/'audit_result.json').exists():r[label+'_status']=e.get('status')
  if r[label+'_status']=='publication_failed':r[label+'_error']=(folder/'audit_error.txt').read_text().splitlines()[-1]
  elif r[label+'_status']=='failed':r[label+'_error']=e.get('failure_reason')
  if e.get('count_proposal'):
   r[label+'_count']=e['count_proposal']['count'];r[label+'_participants']=','.join(e['participating_chip_ids'])
   r[label+'_count_mismatch']=e['count_proposal']['count']!=item['visual_chip_count']
  paths=list(folder.glob('runs/*/export/quality.json'))
  if not paths:continue
  run=folder/e['last_run'] if e.get('last_run') and (folder/e['last_run']/'export/quality.json').exists() else max((x.parent.parent for x in paths),key=lambda x:json.load(open(x/'manifest.json')).get('created',''))
  q=json.load(open(run/'export/quality.json'));cfg=json.load(open(run/'effective_settings.json'));m=json.load(open(run/'manifest.json'))
  for k in ['frames','observation_rows','expected_chip_frames','observed_fraction_all_target_frames','physical_velocity_rows','angular_velocity_rows','event_candidates','fit_eligible_events','review_frame_count','geometry_status','blur_review_rows','floor_boundary_rows','ambiguous_id_rows']:
   r[label+'_'+k]=q.get(k)
  r[label+'_grid_mm']=cfg['calibration'].get('holdout_rmse_m',0)*1000 if cfg['calibration'].get('holdout_rmse_m') is not None else None
  r[label+'_run']=str(run);r[label+'_source_hash']=m['source_hash'];r[label+'_code_hash']=m['code_hash']
  r[label+'_events']=[{k:v.get(k) for k in ['id','pair','frame_start','frame_end','closest_frame','kind','reason','e_n_obs','e_t_obs']} for v in json.load(open(run/'export/events.json'))]
  r[label+'_review_reasons']=dict(collections.Counter(v['reason'] for v in q.get('review_issues',[])))
 rows.append(r)
(output/'all_results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for label in ['v35_default','v4_calibrated']:
 ex=[r for r in rows if r['kind']=='experiment'];print(label,'status',dict(collections.Counter(r.get(label+'_status') for r in ex)),'wrongcount',[(r['video'],r.get(label+'_count')) for r in ex if r.get(label+'_count_mismatch')],'metric',sum(r.get(label+'_geometry_status')=='provisional' for r in ex))
fields=['video','kind','visual_chip_count','frames','calibration_holdout_px']+[p+'_'+k for p in ['v35_default','v4_calibrated'] for k in ['status','count','participants','geometry_status','observation_rows','observed_fraction_all_target_frames','physical_velocity_rows','angular_velocity_rows','event_candidates','review_frame_count','blur_review_rows','grid_mm','error']]
with (output/'video_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
