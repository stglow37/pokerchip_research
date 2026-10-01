import os,time,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from pokerchip.config import default_project
from pokerchip.selection import require_start,confirm_start
from pokerchip.batch_progress import BatchProgress
from pokerchip.viewer import ImageView,ExactFrameReader,StartFrameDialog
from pokerchip.analysis import refine_event


def test_required_selection_rejects_old_interval_and_changed_source(tmp_path):
    p=default_project();e=dict(name='test',interval=[12,None]);source=tmp_path/'source';source.write_bytes(b'original')
    with pytest.raises(ValueError,match='사람이'):require_start(p,e)
    confirm_start(e,source,12);require_start(p,e,e['start_selection']['source_hash'])
    with pytest.raises(ValueError,match='원본'):require_start(p,e,'different')
    e['interval'][0]=13
    with pytest.raises(ValueError):require_start(p,e)


def test_progress_monotonic_and_names():
    updates=[];p=BatchProgress(updates.append,2);p.begin(1,dict(id='a',name='a.mp4',interval=[10,None]),100)
    for f in (10,40,20,99):p.emit(dict(stage='detect',frame=f))
    p.emit(dict(stage='analysis'));p.emit(dict(stage='export'));p.emit(dict(stage='complete'))
    p.begin(2,dict(id='b',name='b.mp4',interval=[0,None]),100);p.emit(dict(stage='complete'))
    assert [u['overall_percent'] for u in updates]==sorted(u['overall_percent'] for u in updates)
    assert updates[-1]['overall_percent']==100 and updates[-1]['video_index']==2


def test_noncontact_does_not_produce_material_coefficients():
    event=dict(pair=['chip_1','chip_2'],gap_unit='m',min_gap=.00769,frame_start=12,frame_end=15)
    def rows(key,a,b):return [dict(frame_index=f,world_center_m=[0.,0.],status='observed') for f in range(a,b+1)]
    result=refine_event(event,rows,{},default_project()['chips'])
    assert result['kind']=='noncontact_pass' and result['e_n_obs'] is None


def test_right_drag_never_places_measurement_point_and_zoom_preserves_coordinates():
    app=QApplication.instance() or QApplication([]);view=ImageView();view.resize(700,500)
    view.set_image(np.zeros((480,640,3),np.uint8));view.show();app.processEvents();clicks=[];view.clicked.connect(lambda x,y:clicks.append((x,y)))
    QTest.mousePress(view,Qt.MouseButton.RightButton,pos=QPoint(300,250));QTest.mouseMove(view,QPoint(330,270));QTest.mouseRelease(view,Qt.MouseButton.RightButton,pos=QPoint(330,270))
    assert not clicks
    view.zoom_at(2);app.processEvents();target=view.target
    x,y=250.,180.;screen=QPoint(round(target.x()+x*target.width()/640),round(target.y()+y*target.height()/480))
    QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=screen)
    assert np.allclose(clicks[-1],[x,y],atol=.5)
    view.close()


def test_start_dialog_loaded_frame_required_and_reader_exact(tmp_path):
    from pokerchip.demo import make_video
    path=make_video(tmp_path/'test.mp4',count=14,kind='single')
    reader=ExactFrameReader(max_bytes=6*640*480*3)
    from pokerchip.video import frame_at
    for i in (0,4,3,12,1):
        t,img=reader.get(path,i);ref,raw=frame_at(path,i)
        assert t['frame_index']==i and np.array_equal(img,raw)
    assert reader.bytes<=reader.limit;reader.close()
    app=QApplication.instance() or QApplication([]);d=StartFrameDialog(path,dict(name='test',interval=[0,None]));d.show()
    until=time.monotonic()+10
    while d.loaded!=0 and time.monotonic()<until:app.processEvents();time.sleep(.01)
    assert not d.accept_button.isEnabled()
    d.check.setChecked(True);assert d.accept_button.isEnabled()
    d.slider.setValue(3);assert not d.accept_button.isEnabled() and not d.check.isChecked()
    until=time.monotonic()+10
    while d.loaded!=3 and time.monotonic()<until:app.processEvents();time.sleep(.01)
    d.check.setChecked(True);d.commit();assert d.selected_frame==3
    app.processEvents()


def test_nonidentifiable_covariance_is_not_zero_certainty():
    from types import SimpleNamespace
    from pokerchip.validation import diagnostics
    result=SimpleNamespace(jac=np.array([[1.,0.],[2.,0.],[3.,0.]]),cost=1.,success=True,message='ok',active_mask=np.zeros(2))
    d=diagnostics(result,['a','b']);assert d['covariance_conditional'] is None
    assert d['uncertainty_status']=='unavailable_nonidentifiable'


def test_measurement_exclusion_survives_kinematics_for_fit_filtering():
    from pokerchip.analysis import kinematic_at
    row=dict(frame_index=3,chip_id='chip_1',raw_center_px=[10,10],status='observed',
             measurement_warning='blurred_edge_review',assignment_ambiguous=True)
    r=kinematic_at(row,[],default_project()['analysis'],[])
    assert r['measurement_warning']=='blurred_edge_review' and r['assignment_ambiguous']


def test_friction_conditioned_contact_recovers_synthetic_restitution_without_editing_observations():
    from pokerchip.physics.farkas import propagate
    from pokerchip.physics.ifr import impact
    from pokerchip.config import Body
    from pokerchip.contact_states import reconstruct
    cfg=default_project();cfg['analysis']['omega_bound_rad_s']=500.
    bodies=[Body.from_chip(c) for c in cfg['chips'][:2]];mu=.25;tc=13/240
    starts=np.array([[0.,0.,1.,.1,0.,15.],[.04,0.,0.,0.,0.,-10.]])
    pre=np.array([propagate(s,b,mu,[tc])[0] for s,b in zip(starts,bodies)])
    offset=pre[0,:2]+[.04,0]-pre[1,:2];starts[1,:2]+=offset;pre[1,:2]+=offset
    post=impact(pre,bodies,.72,-.6,.08)['post'];assert post is not None
    ev=dict(time_s=tc,pair=['chip_1','chip_2'],pre=[],post=[],e_n_obs=.5);rows=[]
    for i,b in enumerate(bodies):
        for side,ff in [('pre',list(range(12))),('post',list(range(15,27)))]:
            ts=np.array(ff)/240
            z=propagate(starts[i] if side=='pre' else post[i],b,mu,ts if side=='pre' else ts-tc)
            A=np.column_stack([np.ones(len(ts)),ts-tc]);beta=np.linalg.lstsq(A,z[:,[0,1,4]],rcond=None)[0]
            ev[side].append(dict(position=beta[0,:2].tolist(),velocity=beta[1,:2].tolist(),omega=float(beta[1,2]),fit_frames=ff))
            for f,t,s in zip(ff,ts,z):rows.append(dict(chip_id=b.id,frame_index=f,physical_time_s=float(t),world_center_m=s[:2].tolist(),theta_wrapped_rad=float(s[4])))
    original=copy.deepcopy((ev,rows));result=reconstruct(ev,rows,cfg,mu)
    assert result['e_n_obs']==pytest.approx(.72,abs=.003)
    assert (ev,rows)==original and result['measurement_e_n_obs']==.5
