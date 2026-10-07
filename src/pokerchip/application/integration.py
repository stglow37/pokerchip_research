"""Read-only submission inspection and explicit import into a new project."""
import copy
import shutil
from pathlib import Path
from ..core.config import load_project, save_project, effective, source_path
from ..core.storage import read_json, atomic_json, digest, new_id, stamp, backup_database
from .pipeline import stage_keys, code_digest


def write_submission(folder,analyst_id):
    if not analyst_id.strip():raise ValueError('분석자 ID 필요')
    project=load_project(folder);adopted={}
    for e in project['experiments']:
        if e.get('status')!='complete' or not e.get('last_run'):raise ValueError(e['name']+': 완료된 채택 run 필요')
        if not isinstance(e.get('session_id'),str) or not e['session_id'].strip():
            raise ValueError(e['name']+': 촬영 세션 ID 필요; 분석자 ID나 영상 ID로 대체하지 마세요.')
        adopted[e['id']]=e['last_run']
    path=Path(folder)/'submission.json'
    atomic_json(path,{'schema_version':1,'analyst_id':analyst_id,'created':stamp(),'adopted_runs':adopted})
    return path


def _within(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('제출 run 경로가 제출 폴더 밖을 가리킵니다.')
    return target


def inspect_submissions(folders, selections=None):
    """SHA256 -> adopted key; optional __exclude__ lists explicitly omitted keys."""
    selections = selections or {}; entries = []; issues = []
    excluded=set(selections.get('__exclude__',[]))
    for index, folder in enumerate(folders):
        root = Path(folder).resolve(); project = load_project(root)
        submission = read_json(root/'submission.json') if (root/'submission.json').exists() else {}
        analyst = submission.get('analyst_id') or project.get('analyst_id')
        if not analyst:issues.append({'type': 'missing_analyst', 'folder': str(root), 'reason': '분석자 ID 필요'})
        for e in project['experiments']:
            key = f'{index}:{e["id"]}'
            if key in excluded:
                entries.append({'key':key,'folder':str(root),'experiment_id':e['id'],'analyst_id':analyst,'selected':False,'exclusion_reason':'explicit_integrator_exclusion'})
                continue
            if not isinstance(e.get('session_id'),str) or not e['session_id'].strip():
                issues.append({'type':'missing_session','key':key,'reason':'촬영 세션 ID 누락: 독립 표본 단위를 확인하세요.'})
            adopted = submission.get('adopted_runs',{}).get(e['id'],e.get('last_run'))
            if not adopted:
                issues.append({'type':'missing_run','key':key,'reason':'영상별 채택 run 누락'});continue
            run = _within(root,adopted)
            if not (run/'manifest.json').exists() or not (run/'records.sqlite').exists():
                issues.append({'type':'missing_run','key':key,'reason':'manifest 또는 관측 DB 누락'});continue
            m=read_json(run/'manifest.json');cfg=read_json(run/'effective_settings.json');exp=read_json(run/'experiment.json')
            if m.get('status')!='complete':issues.append({'type':'incomplete_run','key':key,'reason':'완료된 run 필요'})
            if not m.get('source_hash'):issues.append({'type':'missing_source_hash','key':key,'reason':'원본 해시 누락'})
            if stage_keys(effective(project,e),e,m.get('source_hash'))['analysis']!=m.get('stage_keys',{}).get('analysis'):
                issues.append({'type':'reanalyze_required','key':key,'reason':'현재 설정/코드와 채택 run 불일치'})
            common={k:cfg.get(k) for k in ('analysis','time_profile','chips','physics')}
            from ..core.storage import Records
            with Records(run/'records.sqlite',readonly=True) as db:events=list(db.rows('events'))
            entries.append({'key':key,'folder':str(root),'analyst_id':analyst,'experiment_id':e['id'],
                'source_hash':m.get('source_hash'),'parent_source_id':e.get('parent_source_id'),
                'parent_frame_interval':e.get('parent_frame_interval'),'session_id':e.get('session_id'),
                'fit_role':e.get('fit_role'),'run':adopted,'settings_hash':digest(common),
                'review_hash':digest({'corrections':cfg.get('corrections'),'events':events}),
                'review':{'corrections':cfg.get('corrections',[]),'events':[{k:v.get(k) for k in ('id','pair','contact_frame_interval','boundary_frame_interval','status')} for v in events]},
                'code_hash':m.get('code_hashes',{}).get('analysis'), 'selected':True})
    bysource={}
    for entry in entries:
        if 'source_hash' in entry:bysource.setdefault(entry['source_hash'],[]).append(entry)
    duplicates=[]
    for source, rr in bysource.items():
        if len(rr)<2:continue
        roles={r['fit_role'] for r in rr}
        candidates=[r['key'] for r in rr];chosen=selections.get(source)
        identical=len({(r['review_hash'],r['settings_hash'],r['code_hash']) for r in rr})==1
        if chosen is None and identical and len(roles)==1:chosen=candidates[0]
        if chosen is None and 'train' in roles and 'test' in roles:
            issues.append({'type':'split_leakage','source_hash':source,'reason':'같은 원본의 학습/검증 중복: 역할을 포함해 최종본 한 개만 선택 필요'})
        duplicates.append({'source_hash':source,'candidates':candidates,'selected':chosen,'identical':identical,
                           'review_differences':None if identical else {r['key']:r['review'] for r in rr}})
        if chosen not in candidates:issues.append({'type':'review_conflict','source_hash':source,'reason':'동일 원본의 최종 검토본 선택 필요'})
        for r in rr:r['selected']=r['key']==chosen
    adopted=[r for r in entries if r['selected']]
    if len({r['settings_hash'] for r in adopted})>1:issues.append({'type':'settings_mismatch','reason':'공통 물성·시간·분석·모델 설정 불일치: 공통 설정으로 재분석 필요'})
    for i,a in enumerate(adopted):
        for b in adopted[i+1:]:
            if not a['parent_source_id'] or a['parent_source_id']!=b['parent_source_id']:continue
            if {a['fit_role'],b['fit_role']}=={'train','test'}:
                issues.append({'type':'parent_split_leakage','keys':[a['key'],b['key']],'reason':'같은 부모 원본의 학습/검증 중복'})
            aa=a['parent_frame_interval'];bb=b['parent_frame_interval']
            if not aa or not bb or max(aa[0],bb[0])<=min(aa[1],bb[1]):
                issues.append({'type':'parent_overlap','keys':[a['key'],b['key']],'reason':'부모 프레임 중복 또는 부모 구간 미기록: 한 클립만 채택 필요'})
    return {'created':stamp(),'status':'ready' if not issues else 'resolution_required','entries':entries,
            'duplicates':duplicates,'issues':issues,'selections':selections,
            'policy':'observations merged; analyst coefficients never averaged'}


def integrate_submissions(folders, destination, selections=None):
    report=inspect_submissions(folders,selections)
    if report['issues']:raise ValueError('통합 미해결 항목: '+str(report['issues']))
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('새 통합 폴더를 지정하세요. 기존 폴더는 덮어쓰지 않습니다.')
    adopted=[r for r in report['entries'] if r['selected']]
    if not adopted:raise ValueError('채택한 관측 자료가 없습니다.')
    roots=[Path(f).resolve() for f in folders]
    if any(destination.is_relative_to(r) or r.is_relative_to(destination) for r in roots):raise ValueError('제출 폴더와 분리된 통합 폴더 필요')
    project=copy.deepcopy(load_project(adopted[0]['folder']))
    project.update(id=new_id('project'),name='v6 통합 분석',experiments=[],corrections=[],correction_cursor=0,correction_audit=[])
    project.pop('constant_bank',None);mapping=[]
    destination.mkdir(parents=True)
    for entry in adopted:
        root=Path(entry['folder']);original=load_project(root)
        e=copy.deepcopy(next(e for e in original['experiments'] if e['id']==entry['experiment_id']))
        run=_within(root,entry['run']);cfg=read_json(run/'effective_settings.json')
        old=e['id'];e['id']=new_id('exp');e['video_uri']=str(source_path(root,e).resolve())
        for key in ('analysis','templates','time_profile','calibration'):e[key]=copy.deepcopy(cfg[key])
        corrections=[c for c in cfg.get('corrections',[])[:cfg.get('correction_cursor',0)] if c.get('target',{}).get('experiment_id') in (None,old)]
        for c in corrections:
            c=copy.deepcopy(c);c['id']=new_id('correction');c.setdefault('target',{})['experiment_id']=e['id'];project['corrections'].append(c)
        target=destination/'runs'/new_id('run');shutil.copytree(run,target)
        backup_database(run/'records.sqlite',target/'records.sqlite')
        for suffix in ('-wal','-shm'):
            sidecar=target/('records.sqlite'+suffix)
            if sidecar.exists():sidecar.unlink()
        e['last_run']=str(target.relative_to(destination));e['status']='complete';e['source_hash']=entry['source_hash']
        project['experiments'].append(e);project['correction_cursor']=len(project['corrections'])
        mapping.append(dict(submission_key=entry['key'],analyst_id=entry['analyst_id'],original_experiment_id=old,experiment_id=e['id'],original_run=str(run),run=e['last_run']))
    # Write rebased snapshots only after all edits/experiments have been gathered.
    for e,entry in zip(project['experiments'],adopted):
        target=destination/e['last_run'];cfg=effective(project,e);manifest=read_json(target/'manifest.json')
        atomic_json(target/'imported_manifest.json',manifest)
        manifest.update(id=target.name,settings_hash=digest(cfg),stage_keys=stage_keys(cfg,e,entry['source_hash']),imported_submission=entry['key'])
        atomic_json(target/'manifest.json',manifest);atomic_json(target/'effective_settings.json',cfg);atomic_json(target/'experiment.json',e)
        from .exporting import export_run
        export_run(target)
    save_project(destination,project)
    report.update(mapping=mapping,destination=str(destination));atomic_json(destination/'integration_report.json',report)
    from .delivery import publish_results
    publish_results(destination,project)
    constants=None
    if any(e.get('fit_role')=='train' for e in project['experiments']):
        from ..models.study import train_constants
        constants=train_constants(destination,project)
        project['constant_bank']=str(Path(constants['path']).relative_to(destination))
        save_project(destination,project)
        report['reestimated_constants']=constants
        atomic_json(destination/'integration_report.json',report)
    return {'folder':str(destination),'report':str(destination/'integration_report.json'),'videos':len(adopted),'constants':constants}
