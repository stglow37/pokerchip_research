import os, json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from pokerchip.jobs import Control
from pokerchip.pipeline import Cancelled

def test_cancel_unblocks_pause():
    c=Control();c.pause();c.cancel()
    assert c.cancelled.is_set() and not c.paused.is_set()
    with pytest.raises(Cancelled):c.check()

def test_telemetry_failure_does_not_break_processing(monkeypatch):
    import pokerchip.pipeline as p
    def unavailable():raise p.psutil.NoSuchProcess(1)
    monkeypatch.setattr(p.psutil,'Process',unavailable)
    assert p.sample_rss()==0

def test_review_sheet_uses_actual_nonzero_frame_indices(tmp_path,monkeypatch):
    from pokerchip.storage import Records
    import pokerchip.review_sheet as module
    run=tmp_path/'run';(run/'export').mkdir(parents=True)
    with Records(run/'records.sqlite') as db:
        for f in range(100,110):db.put('frames',f,'',dict(frame_index=f))
    requested=[]
    def frames(source,start=0,end=None):
        requested.append((start,end))
        for f in range(start,end+1):yield dict(frame_index=f),np.zeros((60,80,3),np.uint8)
    monkeypatch.setattr(module,'frames',frames)
    module.save_sheet('source',run)
    assert requested==[(100,109)]
    assert (run/'export/검출_확인.jpg').is_file()

def test_marker_count_union_across_occlusions(monkeypatch):
    import pokerchip.automatic as a
    import pokerchip.markers_v3 as m
    from pokerchip.config import default_project
    # Never three simultaneous silhouettes; all three stable color identities occur.
    seq=[['chip_1','chip_2'],['chip_1','chip_2'],['chip_2','chip_3'],['chip_2','chip_3']]
    images=[np.full((240,320,3),i,np.uint8) for i in range(4)]
    monkeypatch.setattr(a,'sample_video',lambda *args,**kwargs:((dict(frame_index=i),im) for i,im in enumerate(images)))
    monkeypatch.setattr(a,'candidates',lambda *args,**kwargs:[(np.array([60.,80.]),30.),(np.array([180.,80.]),30.)])
    monkeypatch.setattr(a,'measure',lambda im,c,*args,**kwargs:dict(raw_center_px=c[0].tolist(),radius_px=30.,visible_arc_fraction=1.,edge_residual_px=.1))
    def marks(im,d,*args,**kwargs):
        key=seq[int(im[0,0,0])][0 if d['raw_center_px'][0]<100 else 1]
        return {key:dict(rim=True,inner=True,rim_ambiguous=False,inner_ambiguous=False)}
    monkeypatch.setattr(m,'painted_markers',marks)
    import pokerchip.video as v
    monkeypatch.setattr(v,'frame_at',lambda *args:(dict(frame_index=0),images[0].copy()))
    report,_=a.detect_count('unused',default_project())
    assert report['count']==3
    assert report['confirmed_marker_ids']==['chip_1','chip_2','chip_3']
    assert report['status']=='review_required'

def test_cached_gray_preserves_measurement():
    import cv2
    from pokerchip.demo import render_disks
    from pokerchip.vision import measure
    from pokerchip.config import default_project
    im=render_disks([[180,200]],[.2]);candidate=(np.array([180,200]),32.)
    settings=default_project()['analysis']
    a=measure(im,candidate,{},settings)
    b=measure(im,candidate,{},settings,gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY).astype(np.float32))
    assert a==b


def test_sqlite_backup_captures_wal_and_cache_rejects_corruption(tmp_path):
    import sqlite3
    from pokerchip.storage import backup_database,database_ok
    src=tmp_path/'source.sqlite';dest=tmp_path/'copy.sqlite'
    db=sqlite3.connect(src);db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA wal_autocheckpoint=0');db.execute('CREATE TABLE payload(value TEXT)')
    db.execute("INSERT INTO payload VALUES('committed in WAL')");db.commit()
    assert src.with_name(src.name+'-wal').stat().st_size>0
    backup_database(src,dest)
    with sqlite3.connect(dest) as copied:assert copied.execute('select value from payload').fetchone()[0]=='committed in WAL'
    assert database_ok(dest)
    db.close();dest.write_bytes(b'not a database');assert not database_ok(dest)


def test_blurred_neighbor_is_used_and_labelled_v6():
    from pokerchip.analysis import kinematic_at
    from pokerchip.config import default_project
    cfg=default_project()['analysis'];cfg.update(window_s=.1,min_samples=3)
    rows=[dict(frame_index=f,chip_id='chip_1',raw_center_px=[f,0],world_center_m=[f*.01,0],physical_time_s=f*.01,status='observed',source='observation') for f in range(9)]
    rows[4].update(measurement_warning='blurred_edge_review',status='low_confidence')
    target=kinematic_at(rows[2],rows,cfg,[])
    assert target['vx_m_s']==pytest.approx(1.)
    assert kinematic_at(rows[4],rows,cfg,[])['vx_m_s']==pytest.approx(1.)
    assert target['uses_warned_observations']
    assert any(r['frame_index']==4 for r in target['warning_observation_refs'])


def test_zero_count_retries_temporal_sampling_without_assuming_a_chip(monkeypatch):
    import pokerchip.automatic as a
    from pokerchip.config import default_project
    seen=[]
    def samples(path,maximum=24,**kwargs):
        seen.append(maximum)
        for i in range(2):yield dict(frame_index=i),np.zeros((80,100,3),np.uint8)
    monkeypatch.setattr(a,'sample_video',samples)
    monkeypatch.setattr(a,'candidates',lambda *args,**kwargs:[])
    report,_=a.detect_count('unused',default_project())
    assert seen==[24,192]
    assert report['count']==0
    assert report['sampling_retry']['initial_count']==0
    assert report['status']=='review_required'


def test_readonly_records_do_not_create_or_modify_tables(tmp_path):
    import sqlite3
    from pokerchip.storage import Records
    path=tmp_path/'read.sqlite'
    with Records(path) as db:db.put('trajectories',1,'chip_1',{'frame_index':1})
    with Records(path,readonly=True) as db:
        assert list(db.rows('trajectories'))==[{'frame_index':1}]
        with pytest.raises(sqlite3.OperationalError):db.put('trajectories',2,'chip_1',{})


def test_publication_reads_completed_export_without_reopening_database(tmp_path):
    from pokerchip.delivery import human_rows
    run=tmp_path/'run';(run/'export').mkdir(parents=True)
    row={'frame_index':7,'chip_id':'chip_1','raw_center_px':[12,34],'world_center_m':[.1,.2],'physical_time_s':.03}
    (run/'export/trajectories.jsonl').write_text(json.dumps(row)+'\n')
    (run/'records.sqlite').write_bytes(b'unreadable database')
    values=list(human_rows(run,'test.mp4'))
    assert len(values)==1 and values[0][:8]==['test.mp4','chip_1',7,.03,12,34,.1,.2]


def test_backup_closes_connections_explicitly(tmp_path,monkeypatch):
    import sqlite3
    import pokerchip.storage as s
    original=sqlite3.connect;closed=[]
    class Tracked(sqlite3.Connection):
        def close(self):closed.append(self);super().close()
    src=tmp_path/'source.sqlite'
    with original(src) as db:db.execute('create table a(x)');db.commit()
    monkeypatch.setattr(s.sqlite3,'connect',lambda *args,**kwargs:original(*args,**kwargs,factory=Tracked))
    s.backup_database(src,tmp_path/'copy.sqlite')
    assert len(closed)==2


def test_blurred_unmarked_false_circle_cannot_keep_a_lost_track_alive():
    import copy
    from pokerchip.tracking import Tracker
    from pokerchip.config import default_project
    settings=default_project()['analysis'];settings['identity_mode']='painted_tracks'
    marker={'rim':{'angle':0.,'angle_sigma_rad':.02},'inner':{'angle':3.14159265,'angle_sigma_rad':.02},'rim_ambiguous':False,'inner_ambiguous':False}
    good=dict(raw_center_px=[100.,100.],radius_px=50.,visible_arc_fraction=1.,edge_residual_px=.2,surface_status='inside_floor',markers={'chip_1':marker})
    tr=Tracker(settings,['chip_1'],{});observed,_=tr.update(0,[good]);assert observed[0]['chip_id']=='chip_1'
    false=copy.deepcopy(good);false['measurement_warning']='blurred_edge_review';false['markers']['chip_1'].update(rim=None,inner=None)
    for frame in range(1,21):tr.update(frame,[false])
    assert 'chip_1' not in tr.tracks
    moved=dict(good,raw_center_px=[600.,100.]);observed,_=tr.update(21,[moved])
    assert observed[0]['chip_id']=='chip_1' and observed[0]['identity_status']=='two_marker_confirmed'
