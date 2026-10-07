import copy
import numpy as np
import pytest
from pokerchip.core.config import default_project
from pokerchip.core.observation_policy import usable, warning_audit
from pokerchip.analysis.kinematics import kinematic_at, automatic_impact_gate
from pokerchip.models.coefficient_statistics import hierarchy, reliability, normal_fit
from pokerchip.models.study import free_trials, normal_trials


def observations(count=160):
    return [dict(frame_index=i,chip_id='chip_1',raw_center_px=[i,0.],world_center_m=[i/1000,0.],
        physical_time_s=i/240.,status='observed',theta_wrapped_rad=i*.005,omega_rad_s=1.2,
        speed_m_s=.24,theta_sigma_rad=.01) for i in range(count)]


def test_warning_only_changes_audit_not_numeric_kinematics():
    cfg=default_project()['analysis'];cfg['omega_bound_rad_s']=100.;rows=observations(30)
    before=kinematic_at(rows[15],rows,cfg,[])
    rows[14].update(status='low_confidence',measurement_warning='blurred_edge_review')
    after=kinematic_at(rows[15],rows,cfg,[])
    for k in ('vx_m_s','vy_m_s','ax_m_s2','ay_m_s2','omega_rad_s','alpha_rad_s2'):assert after[k]==pytest.approx(before[k])
    assert after['calculation_status']=='computed_with_warnings'
    assert after['warning_observation_refs'][0]['frame_index']==14
    assert after['angle_warning_audit']['uses_warned_observations']


@pytest.mark.parametrize('change',[{'status':'missing'},{'assignment_ambiguous':True},{'identity_status':'ambiguous'},{'observable':False},{'surface_status':'floor_boundary'},{'world_center_m':None},{'world_center_m':[None,0.]},{'physical_time_s':None}])
def test_hard_inputs_still_block(change):
    row=observations(1)[0];row.update(change);assert not usable(row)


def test_segments_cover_all_eligible_time_and_report_tail():
    cfg=default_project();cfg['analysis']['omega_bound_rad_s']=100.
    e=dict(id='v',name='video',session_id='s',participating_chip_ids=['chip_1'])
    rows=observations(265);rows[59].update(status='low_confidence',measurement_warning='blurred_edge_review')
    skipped=[];trials=free_trials(cfg,e,rows,[],True,skipped)
    frames=[f for tr in trials for f in tr['segment_frames']]
    assert len(trials)==5 and len(frames)==265 and len(set(frames))==265
    assert trials[0]['warning_observation_count']==1
    assert all(tr['segment_frames'][-1]-tr['segment_frames'][0]<60 for tr in trials)
    skipped=[];trials=free_trials(cfg,e,observations(250),[],True,skipped)
    assert len(trials)==4 and skipped[0]['frames']==[240,249]


def test_hierarchy_balances_videos_then_sessions():
    rows=[dict(video_id='long',session_id='s1',value=.1,variance=.01)]*10
    rows += [dict(video_id='short',session_id='s1',value=.3,variance=.01),dict(video_id='other',session_id='s2',value=.6,variance=.01)]
    result=hierarchy(rows);assert result['value']==pytest.approx(.4)
    a=reliability(rows,lambda rr:hierarchy(rr)['value'],200,7)
    b=reliability(rows,lambda rr:hierarchy(rr)['value'],200,7)
    assert a==b and a['unit']=='session_id' and a['count']==200
    one=reliability(rows[:10],lambda rr:hierarchy(rr)['value'],200,7)
    assert one['interval95'] is None


def test_uncertain_unreviewed_collision_is_included_with_warning():
    sides=[dict(position=[0.,0.],velocity=[.02,0.],velocity_sigma=[.1,.1]),dict(position=[.04,0.],velocity=[0.,0.],velocity_sigma=[.1,.1])]
    event=dict(id='ev',kind='isolated_binary',status='review_required',normal=[1.,0.],pre=sides,
        post=[dict(s,velocity=[-.03,0.]) if i==0 else s for i,s in enumerate(sides)],a_m_s=.02,
        normal_sigma_rad_approx=.5,approach_sigma_m_s=.2,boundary_frame_interval=[10,20])
    event['automatic_fit_gate']=automatic_impact_gate(event)
    assert event['automatic_fit_gate']['eligible'] and event['automatic_fit_gate']['warnings']
    e=dict(id='video',name='video',session_id='s')
    trials,skipped=normal_trials(e,[event]);assert len(trials)==1 and not skipped
    assert trials[0]['e_n_obs']==pytest.approx(1.5)
    assert 'observed_restitution_outside_model_range' in trials[0]['calculation_warnings']
    fit=normal_fit(trials);assert fit['active_bound'] and fit['value']==pytest.approx(1.,abs=1e-6)


def test_missing_angle_allows_velocity_without_rotation():
    rows=observations(30);rows[15]['theta_wrapped_rad']=None
    cfg=default_project()['analysis'];cfg['omega_bound_rad_s']=100.
    r=kinematic_at(rows[15],rows,cfg,[])
    assert r['vx_m_s'] is not None and r['omega_rad_s'] is None


def test_nonfinite_angle_blocks_rotation_not_position():
    rows=observations(30);rows[15]['theta_wrapped_rad']=float('nan')
    cfg=default_project()['analysis'];cfg['omega_bound_rad_s']=100.
    r=kinematic_at(rows[15],rows,cfg,[])
    assert r['vx_m_s'] is not None and r['omega_rad_s'] is None


def test_weak_free_motion_is_not_silently_trimmed():
    cfg=default_project();cfg['analysis']['omega_bound_rad_s']=100.
    rows=observations(60)
    for r in rows:r.update(speed_m_s=.005,omega_rad_s=.5)
    trial=free_trials(cfg,dict(id='v',name='v',participating_chip_ids=['chip_1']),rows,[],True)[0]
    assert trial['segment_frames']==list(range(60))
    assert 'weak_free_motion_signal' in trial['calculation_warnings']


def test_single_session_video_bootstrap_labelled():
    rows=[dict(video_id='a',session_id='s',value=.1),dict(video_id='b',session_id='s',value=.3)]
    r=reliability(rows,lambda rr:hierarchy(rr)['value'],200,1)
    assert r['unit']=='video_id' and r['scope']=='within_single_session_between_videos'


def test_warning_dependencies_are_preserved_without_relabeling_target_frame():
    raw=observations(3);raw[0].update(status='low_confidence',measurement_warning='blur')
    derived=dict(raw[2],**warning_audit(raw))
    audit=warning_audit([derived,derived])
    assert audit['used_observation_count']==3
    assert audit['warning_observation_count']==1
    assert audit['warning_observation_fraction']==pytest.approx(1/3)
    assert audit['warning_observation_refs'][0]['frame_index']==0


def test_singular_segment_keeps_candidate_but_not_representative_value():
    from pokerchip.models.coefficient_statistics import fit_segments
    trial=dict(id='t',video_id='v',session_id='s')
    fit=lambda *args,**kwargs:dict(optimizer_success=True,parameters={'mu_bottom':.9},diagnostics={'rank':6,'parameter_names':list(range(7))})
    result=fit_segments([trial],fit)[0]
    assert result['candidate_value']==.9 and result['reason']=='rank_deficient_fit'
    assert result.get('value') is None and result['status']=='not_computed'


def test_stale_whole_video_review_does_not_approve_new_event():
    from pokerchip.models.study import human_reviewed
    assert not human_reviewed({'impacts_reviewed':True},{'status':'review_required'})
    assert human_reviewed({},dict(status='approved'))


def test_automatic_tangential_input_is_never_saved_as_human_approved():
    from pokerchip.models.study import impact_trials
    from pokerchip.models.fitting import fit_impacts
    cfg=default_project();cfg['time_profile']['status']='synthetic_known_clock';cfg['calibration']['status']='synthetic'
    sides=[dict(position=[0.,0.],velocity=[1.,0.],theta=0.,omega=1.,velocity_sigma=[.01,.01]),dict(position=[.04,0.],velocity=[0.,0.],theta=0.,omega=0.,velocity_sigma=[.01,.01])]
    ev=dict(id='ev',pair=['chip_1','chip_2'],kind='isolated_binary',status='review_required',normal=[1.,0.],pre=sides,post=sides)
    trials,_=impact_trials(cfg,dict(id='v',name='v'),[ev])
    assert trials[0]['calculation_eligible'] and not trials[0]['approved']
    fitted=fit_impacts(trials,exploratory=True,fixed_e_normal=.7,max_nfev=1)
    assert fitted['validation_status']=='exploratory_not_validated'
    assert not trials[0]['approved']


def test_uncalibrated_pixel_derivatives_keep_warning_audit(tmp_path):
    from pokerchip.core.storage import Records
    from pokerchip.application.pipeline import derive
    cfg=default_project();cfg['mode']='synthetic_demo';cfg['time_profile']['status']='synthetic_known_clock';cfg['analysis']['omega_bound_rad_s']=100.
    e=dict(id='video',interval=[0,29],participating_chip_ids=['chip_1'])
    path=tmp_path/'records.sqlite'
    with Records(path) as db:
        for row in observations(30):
            row['world_center_m']=None;row['radius_px']=5.
            if row['frame_index']==14:row.update(status='low_confidence',measurement_warning='blur')
            db.put('observations',row['frame_index'],'chip_1',row)
            db.put('frames',row['frame_index'],'',dict(frame_index=row['frame_index'],presentation_time_s=row['frame_index']/240.))
        db.db.commit()
    derive(path,cfg,e,lambda:None,lambda *a:None)
    with Records(path,readonly=True) as db:r=next(db.rows('trajectories','chip_1',15,15))
    assert r['vx_m_s'] is None and r['vx_px_s'] is not None
    assert r['metric_calculation_status']=='not_computed'
    assert r['pixel_calculation_status']=='computed_with_warnings'
    assert r['calculation_status']=='partially_computed_with_warnings'
    assert r['warning_observation_refs'][0]['frame_index']==14


@pytest.mark.parametrize('change',[{'theta_wrapped_rad':float('nan')},{'fit_enabled':False}])
def test_legacy_free_dataset_does_not_bridge_invalid_orientation_or_exclusion(tmp_path,change):
    from pokerchip.core.storage import Records,atomic_json
    from pokerchip.models.research import free_trial
    cfg=default_project();cfg['analysis']['omega_bound_rad_s']=100.
    atomic_json(tmp_path/'effective_settings.json',cfg)
    atomic_json(tmp_path/'experiment.json',dict(id='video',session_id='session'))
    with Records(tmp_path/'records.sqlite') as db:
        for row in observations(30):
            row.update(vx_m_s=.24,vy_m_s=0.)
            db.put('trajectories',row['frame_index'],'chip_1',row)
            if row['frame_index']==14:row.update(change)
            db.put('manual',row['frame_index'],'chip_1',row)
    with pytest.raises(ValueError,match='연속 구간'):
        free_trial(tmp_path,'chip_1',0,29)
