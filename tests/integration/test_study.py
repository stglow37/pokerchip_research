import copy
import numpy as np
import pytest
from pokerchip import study
from pokerchip.config import default_project,Body
from pokerchip.physics.farkas import propagate
from pokerchip.physics.ifr import impact
from pokerchip.storage import read_json,atomic_json


def setup(monkeypatch):
    p=default_project();p['calibration']['status']='synthetic';p['time_profile']['status']='synthetic_known_clock';p['analysis']['omega_bound_rad_s']=500.
    p['experiments']=[dict(id=k,name=k,fit_role=role,participating_chip_ids=['chip_1'],session_id=k) for k,role in [('learn','train'),('unseen','test')]]
    b=Body.from_chip(p['chips'][0]);times=np.arange(110)/240.;states=propagate([0,0,.8,.1,0,15],b,.22,times)
    rows=[dict(chip_id='chip_1',frame_index=i,physical_time_s=float(t),world_center_m=s[:2].tolist(),theta_wrapped_rad=float((s[4]+np.pi)%(2*np.pi)-np.pi),omega_rad_s=float(s[5]),speed_m_s=float(np.linalg.norm(s[2:4])),status='observed') for i,(t,s) in enumerate(zip(times,states))]
    loaded=[]
    def load(folder,project,e):
        loaded.append(e['id'])
        return p,copy.deepcopy(rows),[],dict(experiment_id=e['id'],source_hash=e['id'],session_id=e['session_id'])
    monkeypatch.setattr(study,'load_video',load)
    return p,loaded,load


def test_train_never_reads_test_and_fixed_validation_never_refits(tmp_path,monkeypatch):
    p,loaded,_=setup(monkeypatch);f=study.train_constants(tmp_path,p)
    assert loaded==['learn']
    assert f['parameters']['mu_bottom']==pytest.approx(.22,abs=.003)
    original=open(f['path'],'rb').read();loaded.clear()
    monkeypatch.setattr(study,'fit_free',lambda *a,**k:pytest.fail('validation refitted constants'))
    r=study.evaluate_fixed(tmp_path,p,f['path']);v=read_json(r['path'])
    assert loaded==['unseen'];assert open(f['path'],'rb').read()==original
    assert not v['parameters_refitted'] and v['parameter_hash']==v['parameter_hash_after']
    for item in v['free_motion']:assert min(item['score_frames'])>max(item['initialization_frames'])


def test_same_original_cannot_leak_through_renamed_test_file(tmp_path,monkeypatch):
    p,_,load=setup(monkeypatch);f=study.train_constants(tmp_path,p)
    def duplicate(*args):
        cfg,rows,events,prov=load(*args);prov['source_hash']='learn';return cfg,rows,events,prov
    monkeypatch.setattr(study,'load_video',duplicate)
    with pytest.raises(ValueError,match='원본이 같은'):study.evaluate_fixed(tmp_path,p,f['path'])


def test_modified_frozen_constants_are_rejected(tmp_path,monkeypatch):
    p,_,_=setup(monkeypatch);f=study.train_constants(tmp_path,p);bank=read_json(f['path']);bank['parameters']['mu_bottom']+=.1;atomic_json(f['path'],bank)
    with pytest.raises(ValueError,match='변경'):study.evaluate_fixed(tmp_path,p,f['path'])

def test_held_out_suffix_cannot_change_initial_state(monkeypatch):
    p,_,load=setup(monkeypatch);e=p['experiments'][1];cfg,rows,events,_=load(None,p,e)
    tr=study.free_trials(cfg,e,rows,events,False)[0];body=Body(**tr['body'])
    a,report=study.initialize_fixed(tr,body,.22)
    tr['position_angle'][1:]=[[100.,100.,100.]]*(len(tr['position_angle'])-1)
    b,_=study.initialize_fixed(tr,body,.22)
    assert np.allclose(a,b) and report['mu_fixed']==.22


def test_one_reviewed_collision_fits_normal_without_rotation_or_inventing_tangent(tmp_path,monkeypatch):
    p=default_project();p['calibration']['status']='synthetic';p['time_profile']['status']='synthetic_known_clock'
    e=dict(id='impact1',name='impact1',fit_role='train',impacts_reviewed=True,participating_chip_ids=['chip_1','chip_2'],session_id='one');p['experiments']=[e]
    bodies=[Body.from_chip(c) for c in p['chips'][:2]];pre=np.array([[0,0,1,.2,0,0],[.04,0,0,0,0,0.]])
    post=impact(pre,bodies,.72,-.8,.03)['post'];assert post is not None
    sides=lambda ss:[dict(position=s[:2].tolist(),velocity=s[2:4].tolist(),theta=None,omega=None,velocity_sigma=[.01,.01],omega_sigma=None) for s in ss]
    ev=dict(id='ev1',kind='isolated_binary',normal=[1.,0.],pair=['chip_1','chip_2'],pre=sides(pre),post=sides(post))
    monkeypatch.setattr(study,'load_video',lambda *args:(p,[],[ev],dict(experiment_id='impact1',source_hash='hash')))
    f=study.train_constants(tmp_path,p);assert f['parameters']['e_normal']==pytest.approx(.72,abs=1e-6)
    assert 'mu_collision' not in f['parameters'] and 'e_tangential' not in f['parameters']
