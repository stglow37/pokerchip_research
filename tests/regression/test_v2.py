import copy
import numpy as np
import pytest
from pokerchip.config import default_project,load_project,save_project
from pokerchip.timebase import TimeProfile,verify_clock,cadence_report
from pokerchip.calibration import fit_plane
from pokerchip.quality import calibration_gate
from pokerchip.storage import atomic_json,read_json,Records


def test_samsung_eightfold_and_not_double_divided():
    profile=default_project()["time_profile"];clock=TimeProfile(profile)
    assert clock.map(8)==1
    assert clock.map(1/30)==pytest.approx(1/240)
    assert not clock.verified
    frames=[clock.timing({"frame_index":i,"presentation_time_s":i/30}) for i in range(241)]
    assert frames[-1]["physical_time_s"]==1
    assert frames[-1]["time_status"]=="declared_provisional"
    assert cadence_report(frames)["effective_unique_fps"]==pytest.approx(240)


def test_exposure_end_and_clock_validation():
    p=default_project()["time_profile"];p.update(exposure_s=.001,exposure_reference="end")
    assert TimeProfile(p).timing({"frame_index":3,"presentation_time_s":8})["exposure_midpoint_s"]==.9995
    assert verify_clock(p,[0,4,8],[10,10.5,11])["passed"]
    assert not verify_clock(p,[0,4,8],[10,11,12])["passed"]
    with pytest.raises(ValueError):TimeProfile({**p,"exposure_reference":"typo"})


def test_bad_calibration_cannot_be_verified_by_evidence_string():
    px=[[0,0],[100,0],[100,100],[0,100]];world=np.asarray(px)*.001
    result=fit_plane(px,world,holdout={"pixel_points":[[50,50]],"world_points":[[.09,.09]]},evidence="entered")
    assert result["status"]=="pending" and not result["validation"]["passed"]
    with pytest.raises(ValueError):calibration_gate({"validation_limits":{"holdout_rmse_m":-1}})


def test_v1_migration_preserves_clock_and_backup(tmp_path):
    p=default_project();p["schema_version"]="1.0";p["time_profile"].update(status="pending",segments=[{"p_start":0,"p_end":None,"t_start":0,"slow_factor":1}])
    atomic_json(tmp_path/"project.json",p);new=load_project(tmp_path)
    assert new["schema_version"]=="2.0" and new["time_profile"]["segments"][0]["slow_factor"]==1
    save_project(tmp_path,new)
    assert read_json(tmp_path/"project.v1.backup.json")==p


def test_normal_vectors_are_normalized_and_eiv_diagnostics_match():
    from pokerchip.demo import fit_fixture
    from pokerchip.fitting import fit_impacts,body_from_dict
    from pokerchip.physics.ifr import impact
    trials=fit_fixture()["impact_trials"][:6]
    for tr in trials:tr["normal"]=[7,0]
    fit=fit_impacts(trials,max_nfev=40)
    assert abs(fit["parameters"]["e_normal"]-.72)<.02
    for tr,p,observed_et in zip(trials,fit["fitted_pre_states"],fit["e_t_obs"]):
        params=fit["parameters"]
        result=impact(p,[body_from_dict(b) for b in tr["bodies"]],params["e_normal"],params["e_tangential"],params["mu_collision"],normal=tr["normal"],require_contact=False)
        assert result["e_t_obs"]==pytest.approx(observed_et)


def test_black_chip_markers_and_empty_grid():
    import cv2
    from pokerchip.vision import candidates,measure
    from pokerchip.demo import render_disks
    img=render_disks([[220,170]],[.5])
    settings=default_project()["analysis"];settings.update(radius_px=[28,36])
    found=candidates(img,[28,36])
    assert any(np.linalg.norm(c-[220,170])<3 for c,r in found)
    m=measure(img,([220,170],32),{},settings)
    assert np.linalg.norm(np.array(m["raw_center_px"])-[220,170])<1
    with pytest.raises(ValueError):measure(render_disks([],[]),([200,200],50),{},settings)
    wood=render_disks([],[])
    wood[:]=[130,185,210]
    for x in range(0,640,50):cv2.line(wood,(x,0),(x,400),(45,55,60),2)
    for y in range(0,400,50):cv2.line(wood,(0,y),(640,y),(45,55,60),2)
    with pytest.raises(ValueError):measure(wood,([200,200],50),{},settings)
    with pytest.raises(ValueError):candidates(img,[28,36],profile="color_chip")


def test_global_assignment_ambiguity_preserves_tracks():
    from pokerchip.tracking import Tracker
    s=default_project()["analysis"];t=Tracker(s,["chip_1","chip_2"],{})
    t.tracks={"chip_1":{"position":[95.,100.],"velocity_px_frame":[0,0],"radius":30,"last_frame":0},
              "chip_2":{"position":[105.,100.],"velocity_px_frame":[0,0],"radius":30,"last_frame":0}}
    d={"raw_center_px":[100.,100.],"radius_px":30,"markers":{},"status":"observed"}
    rows,pred=t.update(1,[d])
    assert rows[0]["assignment_ambiguous"] and rows[0]["chip_id"].startswith("unknown")
    assert len(pred)==2 and t.tracks["chip_1"]["last_frame"]==0


def test_independent_labels_count_false_negatives_and_lock(tmp_path):
    from pokerchip.benchmark import save_label,evaluate_labels,lock_labels
    run=tmp_path/"run";run.mkdir();atomic_json(run/"manifest.json",{"id":"run","source_hash":"abc","code_hash":"code"})
    with Records(run/"records.sqlite") as db:
        db.put("observations",0,"chip_1",{"raw_center_px":[11,10],"chip_id":"chip_1","theta_wrapped_rad":0})
    labels=tmp_path/"labels.json"
    save_label(labels,0,[{"chip_id":"chip_1","center_px":[10,10],"radius_px":10,"angle_rad":0},
                         {"chip_id":"chip_2","center_px":[50,50],"radius_px":10}],"abc")
    result=evaluate_labels(run,labels)
    assert result["recall"]==.5 and result["center_rmse_px"]==1
    lock_labels(labels)
    with pytest.raises(ValueError):save_label(labels,1,[],"abc")


def test_locked_test_cannot_leak(tmp_path):
    from pokerchip.fitting import fit_dataset
    with pytest.raises(ValueError,match="locked"):
        fit_dataset({"split":{"train":["s"],"holdout":["h"],"locked_test":["s"]}},tmp_path)


def test_nonfinite_farkas_rejected():
    from pokerchip.physics.farkas import propagate
    from pokerchip.config import Body
    with pytest.raises(ValueError):propagate([0]*6,Body(.01,.02,2e-6),.1,[0,np.nan])


def test_correlated_observation_whitening_and_missing_angle():
    from pokerchip.fitting import whiten
    c=np.array([[4,1,0],[1,2,0],[0,0,.1]])
    r=np.array([[1.,2.,np.nan]])
    z=whiten(r,[1,1,1],c)
    assert z@z==pytest.approx(r[0,:2]@np.linalg.inv(c[:2,:2])@r[0,:2])
    with pytest.raises(ValueError):whiten(np.ones((1,3)),[1,1,1],-np.eye(3))


def test_profile_reoptimizes_nuisance_and_reports_limits():
    from pokerchip.demo import fit_fixture
    from pokerchip.fitting import fit_impacts
    from pokerchip.inference import profile_impacts
    trials=fit_fixture()["impact_trials"][::4]
    fit=fit_impacts(trials,eiv=False,max_nfev=60)
    result=profile_impacts(trials,fit,points=3,max_nfev=40)
    assert result["confidence_interval"] is None
    for rows in result["profiles"].values():
        assert min(row["delta_cost"] for row in rows)==0
        assert all(np.isfinite(row["cost"]) for row in rows)
