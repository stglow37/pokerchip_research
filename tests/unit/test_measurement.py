import numpy as np
import pytest
import cv2
from pokerchip.config import default_project,validate
from pokerchip.timebase import TimeProfile
from pokerchip.calibration import fit_plane,to_world,to_pixel,calibrate_views,transform
from pokerchip.vision import circle_fit,measure,marker_features,orientation,learn_template,wrap,candidates
from pokerchip.demo import render_disks
from pokerchip.tracking import Tracker
from pokerchip.analysis import local_polynomial,kinematic_at,classify_graph,monte_carlo


def test_time_maps_and_gate():
    cfg=default_project();p=cfg["time_profile"]
    p["status"]="pending"  # v2 defaults to the user's declared Samsung x8 clock.
    assert TimeProfile(p).map(1) is None
    p.update(status="verified",evidence="independent clock fixture")
    p["segments"]=[{"p_start":0.,"p_end":1.,"t_start":0.,"slow_factor":1.},{"p_start":1.,"p_end":None,"t_start":1.,"slow_factor":8.}]
    t=TimeProfile(p)
    assert t.map(1)==1
    assert t.map(9)==2
    for i in range(10):assert TimeProfile({**p,"segments":[{"p_start":0,"p_end":None,"t_start":0,"slow_factor":8}]}).map(i/30)==pytest.approx(i/240)
    assert t.timing({"frame_index":1,"presentation_time_s":.1},.1)["physical_time_s"] is None
    p["frame_types"]={"1":"interpolated"}
    assert t.timing({"frame_index":1,"presentation_time_s":.2},.1)["independent_observation"] is False
    p["segments"][1]["t_start"]=2
    with pytest.raises(ValueError):TimeProfile(p)
    cfg=default_project();cfg["chips"][0]["mass_kg"]=-1
    with pytest.raises(ValueError):validate(cfg)


def test_plane_and_height_ray():
    K=np.array([[800.,0,320],[0,800,240],[0,0,1]])
    R=np.diag([1.,-1.,-1.]);t=np.array([0.,0.,.5])
    profile={"status":"verified","K":K.tolist(),"distortion":[0,0,0,0,0],"pose_R":R.tolist(),"pose_t":t.tolist(),"H":[[1/1600,0,-.2],[0,-1/1600,.15],[0,0,1]]}
    world=np.array([[.1,.05],[-.1,-.05],[0,0]])
    pixels=to_pixel(world,profile,.003)
    np.testing.assert_allclose(to_world(pixels,profile,.003),world,atol=1e-12)
    assert np.max(abs(to_world(pixels,profile,0)-world))>.0005
    p=np.array([[0,0],[600,0],[600,400],[0,400],[300,200]],float)
    H=np.array([[.001,.0001,-.1],[0,-.001,.2],[.0001,0,1.]])
    fit=fit_plane(p,transform(p,H),holdout={"pixel_points":[[200,100],[400,300]],"world_points":transform([[200,100],[400,300]],H).tolist()},evidence="independent synthetic coordinates")
    assert fit["status"]=="verified"
    assert fit["holdout_rmse_m"]<1e-7


def test_camera_holdout_recovery():
    obj=np.array([[x*.025,y*.025,0] for y in range(7) for x in range(9)],np.float32)
    K=np.array([[850.,0,320],[0,870.,240],[0,0,1.]])
    images=[];objects=[]
    for i in range(12):
        rv=np.array([-.25+.05*i,.2*np.sin(i),.1*np.cos(i)])
        tv=np.array([-.10+.012*(i%3),-.07+.01*(i%4),.6+.03*(i%5)])
        images.append(cv2.projectPoints(obj,rv,tv,K,np.zeros(5))[0].reshape(-1,2));objects.append(obj)
    result=calibrate_views(objects,images,(640,480),[2,6,10])
    np.testing.assert_allclose(np.array(result["K"]),K,atol=.15)
    assert result["holdout_rms_px"]<.001


def test_circle_geometry_and_short_arc_uncertainty():
    rng=np.random.default_rng(1)
    a=np.linspace(0,2*np.pi,160,endpoint=False)
    full=np.array([42.3,91.7])+30*np.column_stack([np.cos(a),np.sin(a)])+rng.normal(0,.15,(160,2))
    fit=circle_fit(full)
    np.testing.assert_allclose(fit["center"],[42.3,91.7],atol=.06)
    short=circle_fit(full[:30])
    assert short["status"]=="low_confidence"
    assert np.trace(short["covariance"][:2,:2])>np.trace(fit["covariance"][:2,:2])*10


def test_original_edges_markers_and_three_ids():
    settings=default_project()["analysis"];settings.update(radius_px=[28,36])
    centers=[[95.3,90.7],[305.1,205.2],[490.4,310.1]];angles=[3.12,-1.2,.7]
    image=render_disks(centers,angles)
    observations=[];templates={}
    for i in range(3):
        chip=f"chip_{i+1}";templates[chip]={"delta_inner_minus_rim_rad":[1.1,-1.5,2.2][i]}
        obs=measure(image,(centers[i],32),{},settings)
        np.testing.assert_allclose(obs["raw_center_px"],centers[i],atol=.5)
        obs["markers"]=marker_features(image,obs,templates,{})
        theta,sigma,status,used=orientation(obs["markers"][chip],templates[chip])
        assert theta is not None
        assert abs(float(wrap(theta-angles[i])))<.05
        observations.append(obs)
    tracker=Tracker(settings,list(templates),templates)
    obs,pred=tracker.update(0,observations)
    assert {r["chip_id"] for r in obs}==set(templates)
    assert not pred
    obs,pred=tracker.update(1,[])
    assert len(pred)==3 and all(p["status"]=="predicted_only" for p in pred)


def test_template_learns_non_half_radius_and_circular_fusion():
    features={"rim":{"angle":np.deg2rad(179),"angle_sigma_rad":.02,"radius_ratio":.85},"inner":{"angle":np.deg2rad(-179),"angle_sigma_rad":.02,"radius_ratio":.42}}
    template=learn_template([features],"s")
    assert template["inner_radius_ratio"]==.42
    assert template["delta_inner_minus_rim_rad"]==pytest.approx(np.deg2rad(2))
    theta,*_=orientation(features,{"delta_inner_minus_rim_rad":0})
    assert abs(theta)>3.1
    theta,*_=orientation({"rim":None,"inner":features["inner"]},template)
    assert abs(float(wrap(theta-np.deg2rad(179))))<1e-10


def test_irregular_polynomial_and_event_segmentation():
    t=np.array([0,.009,.023,.030,.047,.071,.1])
    y=2+3*t+4*t*t
    b,se=local_polynomial(t,y,np.full(len(t),.01),.03)
    np.testing.assert_allclose(b,[2+3*.03+4*.03**2,3+8*.03,8],atol=1e-10)
    rows=[{"frame_index":i,"chip_id":"chip_1","physical_time_s":x,"world_center_m":[2+3*x+4*x*x,0],"raw_center_px":[0,0],"status":"observed","theta_wrapped_rad":0,"theta_sigma_rad":.01} for i,x in enumerate(t)]
    settings=default_project()["analysis"];settings.update(window_s=.3,omega_bound_rad_s=10)
    r=kinematic_at(rows[3],rows,settings,[(3,3)])
    assert r["vx_m_s"] is None and r["reason"]=="event_or_launch_boundary"
    settings["omega_bound_rad_s"]=None
    r=kinematic_at(rows[3],rows,settings,[])
    assert r["vx_m_s"]==pytest.approx(3.24)
    assert r["omega_rad_s"] is None
    events=[{"pair":["a","b"],"frame_start":10,"frame_end":12,"closest_frame":11},{"pair":["b","c"],"frame_start":10,"frame_end":12,"closest_frame":11}]
    classify_graph(events)
    assert all(e["kind"]=="simultaneous_multi_contact" for e in events)


def test_shared_uncertainty_does_not_average_away():
    mean=np.zeros((100,1));ind=np.array([[1.]]);shared=np.array([[4.]])
    result=monte_carlo(lambda x:x.mean(0),mean,ind,shared,count=2000,seed=4)
    assert 3.5<float(result["covariance"])<4.5


def test_continuous_unwrap_and_manual_covariance():
    from pokerchip.analysis import continuous_angle,apply_corrections
    state={};result=[]
    for i,a in enumerate(np.linspace(2.9,10,100)):
        r={"chip_id":"chip_1","frame_index":i,"segment":0,"theta_wrapped_rad":float(wrap(a)),"theta_unwrapped_rad":float(wrap(a))}
        result.append(continuous_angle(r,state)["theta_unwrapped_rad"])
    np.testing.assert_allclose(result,np.linspace(2.9,10,100),atol=1e-12)
    row={"chip_id":"chip_1","frame_index":0}
    edit={"id":"a","target":{"chip_id":"chip_1"},"action":"center","after":{"point_px":[2,4],"sigma_px":2}}
    cal={"status":"verified","H":[[.001,0,0],[0,-.001,0],[0,0,1]]}
    r=apply_corrections(row,[edit],cal,[])
    np.testing.assert_allclose(np.diag(r["covariance_world"])[:2],[4e-6,4e-6])


def test_tracker_promotion_and_participant_cap():
    from copy import deepcopy
    settings=default_project()["analysis"]
    tracker=Tracker(settings,["chip_1"],{})
    d={"raw_center_px":[100.,100.],"radius_px":30.,"status":"observed","markers":{}}
    rows,_=tracker.update(0,[deepcopy(d),deepcopy(d)])
    assert len(rows)==1 and rows[0]["chip_id"].startswith("unknown")
    d["markers"]={"chip_1":{"rim":{"angle":0,"angle_sigma_rad":.02},"inner":{"angle":1,"angle_sigma_rad":.02},"rim_ambiguous":False,"inner_ambiguous":False}}
    rows,pred=tracker.update(1,[d])
    assert len(rows)==1 and rows[0]["chip_id"]=="chip_1" and not pred


def test_empty_grid_is_not_a_measured_disk():
    image=render_disks([],[])
    with pytest.raises(ValueError,match="대비"):
        measure(image,([200,200],50),{},default_project()['analysis'])
