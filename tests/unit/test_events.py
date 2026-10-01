import numpy as np
import pytest
from pokerchip.analysis import refine_event
from pokerchip.config import default_project,Body
from pokerchip.physics.ifr import impact


def test_one_sided_contact_and_uncertainty():
    cfg=default_project();settings=cfg['analysis'];settings['omega_bound_rad_s']=10
    rows={k:[] for k in ('chip_1','chip_2')}
    for f in range(41):
        t=f*.01
        x1=t if t<=.2 else .2+.1*(t-.2)
        x2=.24 if t<=.2 else .24+.9*(t-.2)
        for key,x in zip(rows,(x1,x2)):
            rows[key].append(dict(frame_index=f,physical_time_s=t,world_center_m=[x,0],theta_wrapped_rad=.5*t,status='observed',covariance_world=(np.eye(3)*1e-10).tolist()))
    e=dict(id='e1',pair=list(rows),frame_start=19,frame_end=21,closest_frame=20,kind='unmeasurable')
    get=lambda c,a,b:[r for r in rows[c] if a<=r['frame_index']<=b]
    for c in cfg['chips']:c['radius_sigma_m']=1e-5
    result=refine_event(e,get,settings,cfg['chips'])
    assert result['time_s']==pytest.approx(.2,abs=1e-5)
    assert result['e_n_obs']==pytest.approx(.8,abs=1e-5)
    assert result['c_m_s']==pytest.approx(.02,abs=1e-5)
    assert max(result['pre'][0]['fit_frames'])<=20
    assert min(result['post'][0]['fit_frames'])>=20
    assert set(result['pre'][0]['fit_frames']).isdisjoint(result['post'][0]['fit_frames'])
    assert result['boundary_frame_interval'][1]-result['boundary_frame_interval'][0]==1
    wider=refine_event(e,get,{**settings,'event_clock_sigma_s':.002,'shared_scale_sigma_fraction':.01},cfg['chips'])
    assert wider['time_sigma_s']>result['time_sigma_s']


@pytest.mark.parametrize('model,As_factor',[('contact_consistent_reconstruction',3),('percussion_paper_scope',2)])
def test_ifr_branch_continuity_and_paper_scope(model,As_factor):
    b=[Body(.01,.02,2e-6),Body(.02,.02,4e-6)]
    s=np.array([[0,0,1,.3,0,0],[.04,0,0,0,0,0]],float)
    An=150;Jn=1.8/An;boundary=.3/(As_factor*An)/Jn
    below=impact(s,b,.8,-1,boundary*(1-1e-8),model)
    above=impact(s,b,.8,-1,boundary*(1+1e-8),model)
    assert below['branch']=='sliding' and above['branch']=='sticking'
    np.testing.assert_allclose(below['post'],above['post'],atol=1e-6)
    assert above['J_t']==pytest.approx(.3/(As_factor*An))
    s[0,3]=0
    zero=impact(s,b,1,-1,0,model)
    assert zero['J_t']==0 and zero['e_t_obs'] is None
    assert zero['energy_after']==pytest.approx(zero['energy_before'])
