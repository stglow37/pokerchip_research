"""Verify advanced bootstrap re-runs stages and never resurrects exclusions."""
import copy
from pokerchip.core.config import default_project
from pokerchip.models.coefficient_statistics import full_tangential_bootstrap


def test_full_bootstrap_rebuilds_upstream_stages_and_preserves_exclusions(monkeypatch):
    cfg=default_project();cfg['analysis']['tangential_bootstrap_count']=2
    calls={'segments':0,'normal':0,'contact':[],'tangent':0,'rebuilt':[]}
    sides=[dict(position=[0.,0.],velocity=[1.,0.],theta=0.,omega=1.,velocity_sigma=[.01,.01]),
           dict(position=[.04,0.],velocity=[0.,0.],theta=0.,omega=0.,velocity_sigma=[.01,.01])]
    event=dict(id='ev',pair=['chip_1','chip_2'],kind='isolated_binary',status='review_required',normal=[1.,0.],pre=sides,
        post=[dict(sides[0],velocity=[.1,0.]),dict(sides[1],velocity=[.9,0.])])
    events=[dict(event,id=str(i)) for i in range(3)]+[dict(event,id='excluded',status='excluded')]
    loaded=[(copy.deepcopy(cfg),dict(id=k,name=k,session_id=k),[],copy.deepcopy(events)) for k in ('a','b')]
    def rebuild(ev,*args):
        calls['rebuilt'].append(ev['id']);assert ev['status']!='excluded';return copy.deepcopy(ev)
    def segments(trials,fn):
        calls['segments']+=1
        return [dict(video_id='v',session_id='s',value=.23)]
    def normals(trials):
        calls['normal']+=1;assert len(trials)==6
        return dict(value=.8,optimizer_success=True)
    def contact(ev,rows,c,mu):
        calls['contact'].append(mu);assert ev['status']!='excluded';return ev
    def fit(trials,model,**kwargs):
        calls['tangent']+=1;assert kwargs['fixed_e_normal']==.8
        assert len(trials)==6
        return dict(parameters=dict(e_normal=.8,e_tangential=-.5,mu_collision=.1),physical_status='admissible',
            diagnostics=dict(optimizer_success=True,identifiability='identified_locally',active_bounds=[False,False]))
    monkeypatch.setattr('pokerchip.analysis.kinematics.refine_event',rebuild)
    monkeypatch.setattr('pokerchip.models.study.free_trials',lambda *args:[])
    monkeypatch.setattr('pokerchip.models.coefficient_statistics.fit_segments',segments)
    monkeypatch.setattr('pokerchip.models.coefficient_statistics.normal_fit',normals)
    monkeypatch.setattr('pokerchip.models.contact_states.reconstruct',contact)
    monkeypatch.setattr('pokerchip.models.fitting.fit_impacts',fit)
    result=full_tangential_bootstrap(loaded,cfg,lambda:None)
    assert result['status']=='computed' and result['count']==2 and not result['failures']
    assert calls['segments']==calls['normal']==calls['tangent']==2
    assert calls['contact']==[.23]*12 and len(calls['rebuilt'])==12
    assert 'unknown systematics excluded' in result['shared_uncertainty']
