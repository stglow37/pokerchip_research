import copy
import time
import numpy as np
import pytest
from pokerchip.core.config import default_project
from pokerchip.measurement.vision import circle_fit
from pokerchip.analysis.kinematics import kinematic_at,classify_graph


def test_four_short_arcs_are_not_a_complete_silhouette():
    angles=np.concatenate([np.linspace(a,a+.08,20) for a in (0,np.pi/2,np.pi,1.5*np.pi)])
    result=circle_fit(50*np.column_stack([np.cos(angles),np.sin(angles)]))
    assert result['angular_span_fraction']>.7
    assert result['visible_arc_fraction']<.3
    assert result['status']=='low_confidence'


def test_circle_consensus_rejects_grid_outliers():
    a=np.linspace(0,2*np.pi,144,endpoint=False);rng=np.random.default_rng(5)
    points=[150,120]+50*np.column_stack([np.cos(a),np.sin(a)])+rng.normal(0,.08,(144,2))
    points[::6]+=[9,5]
    fit=circle_fit(points)
    assert np.linalg.norm(fit['center']-[150,120])<.2
    assert abs(fit['radius']-50)<.2


def test_position_and_rotation_windows_are_independent():
    s=default_project()['analysis'];s['omega_bound_rad_s']=100
    rows=[dict(frame_index=i,chip_id='chip_1',physical_time_s=i/240,
        raw_center_px=[i,0],world_center_m=[i/1000,0],status='observed',
        theta_wrapped_rad=i*.01 if i!=4 else None,theta_sigma_rad=.01) for i in range(18)]
    r=kinematic_at(rows[10],rows,s,[])
    assert r['vx_m_s']==pytest.approx(.24)
    assert r['omega_rad_s']==pytest.approx(2.4)
    assert r['angle_fit_frame_interval'][0]==5
    missing=kinematic_at(rows[4],rows,s,[])
    assert missing['vx_m_s'] is not None and missing['omega_rad_s'] is None


def test_final_boundaries_separate_overlapping_candidates():
    a=dict(pair=['a','b'],frame_start=10,frame_end=16,closest_frame=12,kind='isolated_binary',contact_frame_interval=[11,12],fit_eligible=True)
    b=dict(pair=['b','c'],frame_start=15,frame_end=21,closest_frame=18,kind='isolated_binary',contact_frame_interval=[18,19],fit_eligible=True)
    classify_graph([a,b]);assert a['kind']==b['kind']=='isolated_binary'
    b['contact_frame_interval']=[11,12];classify_graph([a,b]);assert not a['fit_eligible']


def test_noncontact_does_not_block_graph():
    events=[dict(pair=['a','b'],frame_start=1,frame_end=8,closest_frame=4,kind='noncontact_pass'),
            dict(pair=['b','c'],frame_start=2,frame_end=9,closest_frame=4,kind='isolated_binary')]
    classify_graph(events);assert events[1]['kind']=='isolated_binary'


def test_automatic_interval_does_not_forge_human_consent(tmp_path):
    from pokerchip.application.interval_proposal import apply_automatic
    from pokerchip.measurement.selection import require_start,confirm_start
    from pokerchip.core.storage import file_hash
    source=tmp_path/'video';source.write_bytes(b'original')
    proposal={'id':'p','source_hash':file_hash(source),'global':{'start':10,'end':50,'confidence':'medium'}}
    e={'interval':[0,None]};p=default_project();apply_automatic(e,proposal)
    require_start(p,e,file_hash(source));assert not e['start_selection']['confirmed']
    with pytest.raises(ValueError):require_start(p,e,'changed_source')
    confirm_start(e,source,12,48);before=copy.deepcopy(e);apply_automatic(e,proposal);assert e==before


def test_manual_interval_change_preserves_trimmed_chip_segments(tmp_path):
    from pokerchip.measurement.selection import confirm_start
    from pokerchip.core.review import validate_intervals
    p=tmp_path/'v';p.write_bytes(b'a');e={'participating_chip_ids':['a'],'interval':[0,100],
        'chip_intervals':{'a':[{'start':0,'end':20},{'start':50,'end':90}]}}
    confirm_start(e,p,10,75);validate_intervals(e)
    assert e['chip_intervals']['a']==[{'start':10,'end':20},{'start':50,'end':75}]
    assert e['review_history']


def test_stationary_disk_is_not_a_release():
    from pokerchip.application.interval_proposal import propose_from_tracks
    r=[{'frame':i,'center':[10,10],'radius':40,'coverage':1,'residual':.1} for i in range(0,100,4)]
    p=propose_from_tracks({'a':r},1,100)
    assert p['global']['confidence']=='low'


def test_missing_span_is_not_motion():
    from pokerchip.application.interval_proposal import propose_from_tracks
    r=[{'frame':i,'center':[i,10],'radius':40,'coverage':1,'residual':.1} for i in range(0,1000,50)]
    assert propose_from_tracks({'a':r},1,1000)['global']['confidence']=='low'


def test_first_moving_frame_not_future_confirmation_window():
    from pokerchip.application.interval_proposal import propose_from_tracks
    r=[{'frame':i,'center':[max(0,i-20)*2,10],'radius':40,'coverage':1,'residual':.1} for i in range(0,100,4)]
    p=propose_from_tracks({'a':r},1,100)
    assert p['global']['start']==20
    assert p['release_verified'] is False


def test_same_grid_check_does_not_claim_absolute_accuracy():
    from pokerchip.analysis.quality import calibration_gate
    r=calibration_gate({'holdout_rmse_m':.0001,'evidence':'same grid'})
    assert not r['has_independent_geometry'] and not r['absolute_accuracy_passed']


def test_stop_retains_position_but_excludes_later_fit():
    from pokerchip.core.review import scope
    e={'interval':[0,100],'stop_annotations':[{'chip_id':'a','kind':'stopped','frame':50}]}
    assert scope(e,'a',51)['observable'] and not scope(e,'a',51)['fit_enabled']
    assert scope(e,'b',51)['fit_enabled']


def test_exact_seek_matches_sequential_and_memory_bound(tmp_path):
    from pokerchip.application.demo import make_video
    from pokerchip.measurement.video import frames
    from pokerchip.measurement.frame_access import IndexedFrameReader
    path=make_video(tmp_path/'long.mp4',count=42,kind='single')
    truth={t['frame_index']:(t,im) for t,im in frames(path)}
    reader=IndexedFrameReader(max_bytes=640*480*3,cache_dir=tmp_path/'index')
    for f in (0,38,37,2,41,0):
        t,im=reader.get(path,f)
        assert t==truth[f][0] and np.array_equal(im,truth[f][1])
        assert reader.bytes<=reader.limit
    assert reader.fast
    reader.close()


def test_cancelled_decode_does_not_return_a_frame(tmp_path):
    from pokerchip.application.demo import make_video
    from pokerchip.measurement.frame_access import IndexedFrameReader,Superseded
    path=make_video(tmp_path/'v.mp4',count=10,kind='single')
    reader=IndexedFrameReader(cache_dir=tmp_path/'index')
    with pytest.raises(Superseded):reader.get(path,8,cancelled=lambda:True)
    assert not list((tmp_path/'index').glob('*.json'))


@pytest.mark.parametrize('start_first',[True,False])
def test_start_end_pin_order_and_cursor_independence(tmp_path,start_first):
    from pokerchip.application.demo import make_video
    from pokerchip.ui.viewer import StartFrameDialog
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    path=make_video(tmp_path/'v.mp4',count=24,kind='single')
    d=StartFrameDialog(path,{'name':'test','interval':[0,None]});d.show()
    def show(f):
        d.slider.setValue(f);until=time.monotonic()+15
        while d.loaded!=f and time.monotonic()<until:app.processEvents();time.sleep(.005)
        assert d.loaded==f
    for f,action in ([(3,d.pin_start),(18,d.pin_end)] if start_first else [(18,d.pin_end),(3,d.pin_start)]):show(f);action()
    show(10);d.commit();assert (d.selected_frame,d.selected_end)==(3,18)
    d.close();app.processEvents()


def test_center_sticker_does_not_supply_orientation():
    from pokerchip.measurement.vision import orientation
    r=orientation({'inner':{'angle':1.,'angle_sigma_rad':.01,'radius_ratio':.02}}, {'delta_inner_minus_rim_rad':.5})
    assert r[0] is None


def test_same_impact_survives_one_missing_frame():
    from pokerchip.analysis.kinematics import pair_candidates
    def row(f,key,x):return {'chip_id':key,'frame_index':f,'raw_center_px':[x,0.], 'radius_px':20.,'status':'observed'}
    groups=[(0,[row(0,'a',0),row(0,'b',44)]),(1,[row(1,'a',0)]),
            (2,[row(2,'a',0),row(2,'b',43)]),(3,[row(3,'a',0),row(3,'b',90)])]
    events=list(pair_candidates(groups,{}))
    assert len(events)==1 and events[0]['frame_end']==3


def test_automatic_impact_gate_preserves_review_and_does_not_filter_restitution():
    from pokerchip.analysis.kinematics import automatic_impact_gate
    event={'kind':'isolated_binary','status':'review_required','boundary_frame_interval':[30,31],
        'pre':[{'fit_frames':list(range(25,31))}]*2,'post':[{'fit_frames':list(range(31,37))}]*2,
        'normal_sigma_rad_approx':.02,'a_m_s':1.,'approach_sigma_m_s':.03,'e_n_obs':1.1}
    assert automatic_impact_gate(event)['eligible']
    assert event['status']=='review_required'
    event['boundary_frame_interval']=[30,35]
    assert not automatic_impact_gate(event)['eligible']


def test_manual_center_does_not_keep_old_projected_outline():
    from pokerchip.analysis.kinematics import apply_corrections
    r={'frame_index':1,'chip_id':'a','raw_center_px':[0.,0.],'radius_px':10.,'projected_boundary_px':[[0,0]],'status':'observed'}
    edits=[{'id':'edit1','target':{'chip_id':'a','frames':[1,1]},'action':'center','after':{'point_px':[5.,5.]}}]
    got=apply_corrections(r,edits,{},[{'id':'a'}])
    assert not got.get('projected_boundary_px') and got['raw_center_px']==[5.,5.]


def test_tracking_gate_expands_for_missing_frames_but_not_instant_jumps():
    from pokerchip.measurement.tracking import Tracker
    from pokerchip.core.config import default_project
    settings=default_project()['analysis'];settings['identity_mode']='spatial_tracks'
    tracker=Tracker(settings,['a'],{})
    def d(x):return {'raw_center_px':[x,0.],'radius_px':50.,'markers':{},'visible_arc_fraction':1,'status':'observed'}
    tracker.update(0,[d(0)])
    rows,_=tracker.update(8,[d(130)])
    assert rows[0]['chip_id']=='a'


def test_collision_boundary_uses_contiguous_suffix_after_earlier_blur():
    from pokerchip.analysis.kinematics import suggest_boundary
    rows={k:[] for k in ('a','b')}
    for f in range(20,47):
        for key in rows:
            if key=='a' and f in (25,26):continue
            x=(min(f,31.5)/240 if key=='a' else 31.5/240+.04+max(0,f-31.5)/240)
            rows[key].append({'frame_index':f,'physical_time_s':f/240,'world_center_m':[x,0.], 'status':'observed'})
    ev={'pair':['a','b'],'frame_start':28,'frame_end':36}
    assert suggest_boundary(ev,lambda key,a,b:[r for r in rows[key] if a<=r['frame_index']<=b])==[31,32]


def test_cli_add_defaults_to_automatic_count(tmp_path):
    from pokerchip.cli import main
    from pokerchip.core.config import load_project
    folder=tmp_path/'project';video=tmp_path/'input.mp4';video.write_bytes(b'registration-only')
    assert main(['init',str(folder)])==0
    assert main(['add',str(folder),str(video)])==0
    e=load_project(folder)['experiments'][0]
    assert e['count_mode']=='auto' and e['quick_workflow']
