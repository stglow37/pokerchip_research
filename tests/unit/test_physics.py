import numpy as np
import pytest
from numpy.polynomial.legendre import leggauss
from pokerchip.config import Body
from pokerchip.physics.farkas import functions,propagate,force_torque,G
from pokerchip.physics.ifr import impact,invariants
from pokerchip.physics.simulator import simulate


def quadrature(e):
    q,w=leggauss(150);r=(q+1)/2;wr=w/2
    a=(np.arange(1200)+.5)*2*np.pi/1200
    x=r[:,None]*np.cos(a);y=r[:,None]*np.sin(a)
    ux=e-y;uy=x;norm=np.sqrt(ux*ux+uy*uy)
    weight=wr[:,None]*r[:,None]*(2/1200)
    return np.sum(weight*ux/norm),np.sum(weight*(x*uy-y*ux)/norm)


@pytest.mark.parametrize("e",[0,1e-6,.001,.05,.3,.653,1-1e-8,1,1+1e-8,2,10,31,100,1e6])
def test_farkas_independent_area(e):
    np.testing.assert_allclose(functions(e),quadrature(e),atol=2e-5,rtol=3e-4)


def test_farkas_limits_pure_modes_and_stop():
    b=Body(.01,.02,2e-6)
    assert functions(0)==(0,2/3)
    np.testing.assert_allclose(functions(1),[8/(3*np.pi),8/(9*np.pi)])
    assert functions(np.inf)==(1,0)
    mu=.2;tstop=1/(mu*G)
    s=propagate([0,0,1,0,0,0],b,mu,[0,tstop/2,tstop,tstop+1])
    np.testing.assert_allclose(s[-1],[1/(2*mu*G),0,0,0,0,0],atol=1e-12)
    s=propagate([0,0,0,0,0,-10],b,mu,[0,.001])
    assert (s[1,5]-s[0,5])/.001==pytest.approx(4*mu*G/(3*b.radius))


def test_mixed_energy_straight_sign_and_convergence():
    b=Body(.01,.02,2e-6);t=np.linspace(0,1,100)
    a=propagate([0,0,.3,.4,.2,-25],b,.13,t,rtol=1e-7)
    c=propagate([0,0,.3,.4,.2,-25],b,.13,t,rtol=1e-10,stop_speed=1e-10)
    np.testing.assert_allclose(a,c,atol=3e-5)
    E=.5*b.mass*np.sum(a[:,2:4]**2,axis=1)+.5*b.inertia*a[:,5]**2
    assert np.max(np.diff(E))<1e-12
    assert np.all(a[:,5]<=0)
    np.testing.assert_allclose(a[:,0]*4,a[:,1]*3,atol=1e-12)


@pytest.mark.parametrize("ratio",[.5,1,2])
@pytest.mark.parametrize("spins",[(0,0),(12,4),(-12,4),(4,-20)])
def test_ifr_conservation_independent(ratio,spins):
    b=[Body(.01,.02,2e-6),Body(.01/ratio,.025,.4*(.01/ratio)*.025**2)]
    s=np.array([[0,0,1,.5,0,spins[0]],[.045,0,.1,-.2,0,spins[1]]])
    result=impact(s,b,.7,-.9,.08)
    assert result["status"]=="ok"
    q=result["post"];before=invariants(s,b,origin=(.13,-.7));after=invariants(q,b,origin=(.13,-.7))
    np.testing.assert_allclose(before["momentum"],after["momentum"],atol=1e-14)
    assert before["angular_momentum"]==pytest.approx(after["angular_momentum"],abs=1e-14)
    assert q[0,2]-q[1,2]==pytest.approx(-.7*.9)
    assert after["energy"]-before["energy"]==pytest.approx(result["delta_energy_formula"],abs=1e-14)
    assert after["energy"]<=before["energy"]+1e-14
    np.testing.assert_array_equal(s[:,[0,1,4]],q[:,[0,1,4]])


def test_ifr_symmetries_and_branch():
    b=[Body(.01,.02,2e-6)]*2
    s=np.array([[0,0,1,.4,0,3],[.04,0,0,0,0,-2]],float)
    result=impact(s,b,.8,-.9,.1);q=result["post"]
    swap=impact(s[::-1],b,.8,-.9,.1)["post"]
    np.testing.assert_allclose(swap,q[::-1],atol=1e-14)
    mirror=s.copy();mirror[:,[1,3,4,5]]*=-1
    mq=impact(mirror,b,.8,-.9,.1)["post"];mq[:,[1,3,4,5]]*=-1
    np.testing.assert_allclose(mq,q,atol=1e-14)
    a=.73;R=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
    rot=s.copy();rot[:,:2]=s[:,:2]@R.T;rot[:,2:4]=s[:,2:4]@R.T
    rq=impact(rot,b,.8,-.9,.1)["post"];rq[:,:2]=rq[:,:2]@R;rq[:,2:4]=rq[:,2:4]@R
    np.testing.assert_allclose(rq,q,atol=1e-14)
    assert impact(q,b,.8,-.9,.1)["status"]=="separating"
    assert impact(s,b,.8,-.9,.1,model="percussion_paper_scope")["status"]=="unsupported"
    assert impact(s,b,1,1,2)["status"]=="invalid"


def test_fast_swept_and_multi_contact():
    b=[Body(.01,.02,2e-6)]*3
    s=[[0,0,100,0,0,0],[.2,0,0,0,0,0],[.6,0,0,0,0,0]]
    result=simulate(s,b,[0,.01],0,1,-1,0)
    assert result["status"]=="complete"
    assert len(result["events"])==2
    assert result["events"][0]["time_s"]==pytest.approx(.0016,abs=1e-10)
    for e in result["events"]:np.testing.assert_allclose(e["pre"][:,[0,1,4]],e["post"][:,[0,1,4]])
    simultaneous=simulate([[-.1,0,1,0,0,0],[0,0,0,0,0,0],[.1,0,-1,0,0,0]],b,[0,.1],0,.8,-1,0)
    assert simultaneous["status"]=="unsupported"
    assert simultaneous["reason"]=="simultaneous_multi_contact"
