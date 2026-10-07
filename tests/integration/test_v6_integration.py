import copy
import pytest
from pokerchip.core.config import create_project,save_project,effective,load_project
from pokerchip.core.storage import atomic_json,Records,read_json
from pokerchip.application.pipeline import stage_keys
from pokerchip.application.integration import inspect_submissions,integrate_submissions,write_submission


def submission(root,source='hash',center=0.,role='train',parent=None):
    p=create_project(root);e=dict(id='e',name='video',session_id='s',video_uri='source.mp4',source_hash=source,
        participating_chip_ids=['chip_1'],interval=[0,20],status='complete',last_run='runs/r',fit_role=role,parent_source_id=parent)
    p['experiments']=[e];save_project(root,p);run=root/'runs/r';run.mkdir(parents=True)
    cfg=effective(p,e);atomic_json(run/'effective_settings.json',cfg);atomic_json(run/'experiment.json',e)
    atomic_json(run/'manifest.json',dict(id='r',status='complete',source_hash=source,stage_keys=stage_keys(cfg,e,source)))
    with Records(run/'records.sqlite') as db:
        db.put('events',5,'ev',dict(id='ev',pair=['chip_1','chip_2'],frame_start=4,frame_end=6,kind='isolated_binary',status='review_required',contact_frame_interval=[int(center)+4,6]))
        db.db.commit()
    write_submission(root,'analyst');return p


def test_identical_duplicate_counted_once_and_readonly(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';submission(a);submission(b)
    before=(a/'project.json').read_bytes();r=inspect_submissions([a,b])
    assert r['status']=='ready' and sum(e['selected'] for e in r['entries'])==1
    assert (a/'project.json').read_bytes()==before


def test_different_reviews_require_explicit_choice(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';submission(a);submission(b,center=1)
    report=inspect_submissions([a,b]);assert any(i['type']=='review_conflict' for i in report['issues'])
    with pytest.raises(ValueError,match='미해결'):integrate_submissions([a,b],tmp_path/'merged')
    assert not (tmp_path/'merged').exists()
    assert inspect_submissions([a,b],{'hash':'1:e'})['status']=='ready'


def test_shared_parent_train_test_rejected(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';submission(a,'a',role='train',parent='parent');submission(b,'b',role='test',parent='parent')
    report=inspect_submissions([a,b]);assert any(i['type']=='parent_split_leakage' for i in report['issues'])
    resolved=inspect_submissions([a,b],{'__exclude__':['1:e']})
    assert resolved['status']=='ready'
    assert resolved['entries'][1]['exclusion_reason']=='explicit_integrator_exclusion'


def test_duplicate_train_test_requires_explicit_role_selection(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';submission(a);submission(b,role='test')
    assert any(i['type']=='split_leakage' for i in inspect_submissions([a,b])['issues'])
    report=inspect_submissions([a,b],{'hash':'0:e'})
    assert report['status']=='ready'
    assert [r['fit_role'] for r in report['entries'] if r['selected']]==['train']


def test_missing_or_stale_run_is_explicit(tmp_path):
    a=tmp_path/'a';p=submission(a);p['analysis']['window_s']=.2;save_project(a,p)
    assert any(i['type']=='reanalyze_required' for i in inspect_submissions([a])['issues'])


def test_missing_session_blocks_submission_and_readonly_integration(tmp_path):
    a=tmp_path/'a';p=submission(a)
    p['experiments'][0].pop('session_id');save_project(a,p)
    before=(a/'submission.json').read_bytes()
    with pytest.raises(ValueError,match='세션 ID'):
        write_submission(a,'analyst')
    report=inspect_submissions([a])
    assert report['status']=='resolution_required'
    assert any(i['type']=='missing_session' for i in report['issues'])
    assert (a/'submission.json').read_bytes()==before
    with pytest.raises(ValueError,match='미해결'):
        integrate_submissions([a],tmp_path/'merged')
    assert not (tmp_path/'merged').exists()


def test_import_rebases_ids_preserves_source_and_records(tmp_path,monkeypatch):
    a=tmp_path/'a';b=tmp_path/'b';submission(a,'a');submission(b,'b')
    monkeypatch.setattr('pokerchip.application.delivery.publish_results',lambda *a:None)
    monkeypatch.setattr('pokerchip.application.exporting.export_run',lambda *a:None)
    calls=[]
    def reestimate(folder,project):
        calls.append([e['id'] for e in project['experiments']])
        return {'path':str(folder/'results/constants.json')}
    monkeypatch.setattr('pokerchip.models.study.train_constants',reestimate)
    originals=[(r/'project.json').read_bytes() for r in (a,b)]
    result=integrate_submissions([a,b],tmp_path/'merged');p=load_project(result['folder'])
    assert len(p['experiments'])==2 and len({e['id'] for e in p['experiments']})==2
    assert calls==[[e['id'] for e in p['experiments']]]
    assert [(r/'project.json').read_bytes() for r in (a,b)]==originals
    for e in p['experiments']:
        run=tmp_path/'merged'/e['last_run'];assert (run/'imported_manifest.json').exists()
        assert read_json(run/'manifest.json')['stage_keys']==stage_keys(effective(p,e),e,e['source_hash'])
        with Records(run/'records.sqlite',readonly=True) as db:assert len(list(db.rows('events')))==1
    with pytest.raises(ValueError,match='덮어쓰지'):integrate_submissions([a,b],tmp_path/'merged')
