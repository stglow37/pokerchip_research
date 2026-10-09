import numpy as np
import pytest
from pokerchip.models.contact_field import acceleration,acceleration_basis,disk_quadrature,simulate

def test_disk_moments():
    xy,w=disk_quadrature(16,64)
    assert np.isclose(w.sum(),1)
    assert np.allclose(w@xy,0,atol=1e-14)
    assert np.allclose(w@(xy*xy),[.25,.25],atol=1e-14)

def test_pure_translation_and_rotation_limits():
    mu=.2;r=.02;g=9.80665
    assert np.allclose(acceleration([0,0,1,0,0,0],[mu,0,0]),[-mu*g,0,0],atol=1e-9)
    # polar quadrature of r converges to 2/3
    a=acceleration([0,0,0,0,0,10],[mu,0,0],nr=32,nt=96)
    assert abs(a[2]+mu*g*4/(3*r))<.002

def test_nonnegative_local_friction_required():
    with pytest.raises(ValueError):acceleration([0,0,1,0,0,1],[.1,.2,0])

def test_uniform_quadrature_matches_independent_elliptic_formula():
    from pokerchip.models.physics.farkas import functions
    for epsilon in [.05,.2,.7,1.,1.2,2.,10.]:
        a=acceleration([0,0,epsilon*.02,0,0,1],[1,0,0],nr=40,nt=160)
        F,T=functions(epsilon)
        assert abs(-a[0]/9.80665-F)<8e-4
        assert abs(-a[2]*.01/9.80665-T)<8e-4

def test_local_work_identity_and_passivity():
    rng=np.random.default_rng(42);xy,w=disk_quadrature()
    for _ in range(40):
        s=np.r_[0.,0.,rng.normal(size=2),rng.normal(),rng.normal()*10]
        c=np.r_[.2,rng.normal(size=2)*.02];a=acceleration(s,c)
        power=s[2:4]@a[:2]+.5*.02**2*s[5]*a[2]
        assert power<=1e-12
        co,si=np.cos(s[4]),np.sin(s[4]);world=xy@np.array([[co,si],[-si,co]])
        u=np.column_stack([s[2]-s[5]*.02*world[:,1],s[3]+s[5]*.02*world[:,0]])
        u2=np.sum(u*u,axis=1);field=c[0]+xy@c[1:]
        expected=-9.80665*np.sum(w*field*u2/np.sqrt(u2+1e-12))
        assert np.isclose(power,expected,rtol=1e-12,atol=1e-12)

def test_spin_up_can_coexist_with_energy_loss():
    # Synthetic mechanism example, never evidence of the experimental cause.
    s=[0,0,1,0,0,1];a=acceleration(s,[.2,0,.12])
    assert a[0]<0 and a[2]>0
    assert a[0]+.5*.02**2*a[2]<0

def test_simulation_convergence_and_energy():
    t=np.linspace(0,.2,49);s=[0,0,.8,.1,.3,2];c=[.2,.03,.07]
    a=simulate(s,t,c);b=simulate(s,t,c,max_step=1/960)
    assert np.max(np.abs(a-b))<1e-4
    energy=.5*(a[:,2]**2+a[:,3]**2)+.25*.02**2*a[:,5]**2
    assert np.max(np.diff(energy))<1e-9
