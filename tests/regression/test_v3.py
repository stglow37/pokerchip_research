import numpy as np
import cv2
import pytest
from pokerchip.scene import floor_scene,PITCHES
from pokerchip.markers_v3 import painted_markers
from pokerchip.vision import measure
from pokerchip.tracking import Tracker
from pokerchip.config import default_project

def disk(center=(110,110),rim=(20,30,245),inner=(240,30,20)):
    im=np.full((240,240,3),(130,175,195),np.uint8)
    cv2.circle(im,center,50,(65,42,32),-1)
    cv2.circle(im,(center[0]+44,center[1]),7,rim,-1)
    cv2.circle(im,(center[0]-14,center[1]),5,inner,-1)
    return im

def detection(im,center=(110,110)):
    d=measure(im,(center,50),{},default_project()['analysis'])
    d['markers']=painted_markers(im,d,['chip_1','chip_2'],{})
    return d

def test_launcher_is_not_a_black_chip():
    image=np.full((240,240,3),(150,180,205),np.uint8)
    cv2.circle(image,(110,110),50,(25,55,145),-1)
    with pytest.raises(ValueError,match='붉은 물체'):measure(image,((110,110),50),{},default_project()['analysis'])

def test_painted_identity_recovers_after_long_gap_and_measures_angle():
    s=default_project()['analysis'];s['identity_mode']='painted_tracks'
    tracker=Tracker(s,['chip_1','chip_2'],{})
    a,_=tracker.update(0,[detection(disk())]);b,_=tracker.update(30,[detection(disk((118,110)),(118,110))])
    assert a[0]['chip_id']==b[0]['chip_id']=='chip_1'
    assert abs(b[0]['theta_wrapped_rad'])<.05

def test_blue_rim_does_not_merge_into_blue_tinted_dark_body():
    d=detection(disk(rim=(245,35,20),inner=(20,235,245)))
    f=d['markers']['chip_2']
    assert f['rim'] and f['inner'] and not f['rim_ambiguous']
    assert abs(f['rim']['angle'])<.06

def test_strong_color_does_not_authorize_an_instant_position_jump():
    s=default_project()['analysis'];s['identity_mode']='painted_tracks'
    tracker=Tracker(s,['chip_1','chip_2'],{});d=detection(disk());tracker.update(0,[d])
    bad=dict(d,raw_center_px=[600,600]);r,_=tracker.update(1,[bad])
    assert not r or (r[0]['chip_id']!='chip_1' and r[0]['assignment_ambiguous'])

def test_boundary_hand_with_one_mark_cannot_steal_chip():
    s=default_project()['analysis'];s['identity_mode']='painted_tracks'
    tr=Tracker(s,['chip_1','chip_2'],{});d=detection(disk());tr.update(0,[d])
    hand=detection(disk());hand['surface_status']='floor_boundary'
    for f in hand['markers'].values():f['inner']=None
    r,p=tr.update(1,[hand]);assert not r and p
    r,p=tr.update(30,[hand]);assert not r

def test_first_rim_only_chip_can_initialize_inside_board():
    s=default_project()['analysis'];s['identity_mode']='painted_tracks'
    tr=Tracker(s,['chip_1','chip_2'],{});d=detection(disk());d['surface_status']='inside_floor'
    d['markers']['chip_1']['inner']=None
    r,_=tr.update(0,[d]);assert r[0]['chip_id']=='chip_1'
    r,_=tr.update(1,[d]);assert r[0]['chip_id']=='chip_1'

def test_rectangular_lattice_assigns_long_axis_and_clears_old_pose():
    im=np.full((1200,1200,3),30,np.uint8);im[90:1040,70:1080]=(135,177,199)
    for i in range(19):
        cv2.line(im,(90+i*53,110),(90+i*53,1010),(35,35,35),2)
        cv2.line(im,(90,110+i*50),(1044,110+i*50),(35,35,35),2)
    for img,axis in [(im,'image_horizontal'),(cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE),'image_vertical')]:
        result=floor_scene(img,{'pose_R':np.eye(3).tolist(),'pose_t':[0,0,1]})
        assert result['status']=='provisional',result
        assert result['long_direction']==axis
        assert sorted(result['pitch_xy_m'])==list(PITCHES)
        assert result['calibration']['pose_R'] is None

def test_unknown_identity_still_gets_local_orientation():
    s=default_project()['analysis'];s['identity_mode']='spatial_tracks'
    tr=Tracker(s,['chip_1'],{});d=detection(disk());d['markers']={'chip_1':d['markers']['chip_1']}
    tr.update(0,[d]);r,_=tr.update(40,[d])
    assert r[0]['chip_id'].startswith('unknown') and r[0]['theta_wrapped_rad'] is not None
