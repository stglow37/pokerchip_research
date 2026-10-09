"""Exploratory passive circular-contact model; not a validated replacement.

The body is a uniform thin cylinder. Uniform normal pressure and a nonnegative
body-fixed first-harmonic friction coefficient are assumed. Circular footprint
does not imply homogeneous friction. mu(r)=mu0+mux*x_body/R+muy*y_body/R.
This describes an effective friction-strength field, not an inferred pressure
distribution. The original Farkas/IFR API and configured default are unchanged.
"""
from functools import lru_cache
import numpy as np
from scipy.integrate import solve_ivp

G=9.80665

@lru_cache(maxsize=8)
def disk_quadrature(nr=12,nt=48):
    z,w=np.polynomial.legendre.leggauss(nr)
    radius=np.sqrt((z+1)/2)
    a=2*np.pi*(np.arange(nt)+.5)/nt
    xy=np.stack([(radius[:,None]*np.cos(a)).ravel(),
                 (radius[:,None]*np.sin(a)).ravel()],axis=1)
    weights=np.repeat(w/2/nt,nt)
    return xy,weights

def validate_coefficients(coeff):
    c=np.asarray(coeff,dtype=float)
    if c.shape!=(3,) or not np.isfinite(c).all():
        raise ValueError('Expected three finite friction coefficients')
    if c[0]<0 or np.hypot(c[1],c[2])>c[0]+1e-12:
        raise ValueError('Local friction must be nonnegative everywhere')
    return c

def acceleration_basis(vx,vy,omega,theta,radius=.02,kappa=.5,nr=12,nt=48,epsilon=1e-6):
    """Return 3x3 map [ax,ay,alpha] = basis @ [mu0,mux,muy]."""
    xy,w=disk_quadrature(nr,nt)
    co,si=np.cos(theta),np.sin(theta)
    world=xy@np.array([[co,si],[-si,co]])
    slip=np.column_stack([vx-omega*radius*world[:,1],vy+omega*radius*world[:,0]])
    unit=slip/np.sqrt(np.sum(slip*slip,axis=1)+epsilon**2)[:,None]
    field=np.column_stack([np.ones(len(xy)),xy])
    force=-G*(unit*w[:,None]).T@field
    torque=-G/(kappa*radius)*((world[:,0]*unit[:,1]-world[:,1]*unit[:,0])*w)@field
    return np.vstack([force,torque])

def acceleration(state,coeff,radius=.02,kappa=.5,**kwargs):
    c=validate_coefficients(coeff)
    return acceleration_basis(state[2],state[3],state[5],state[4],radius,kappa,**kwargs)@c

def simulate(initial,times,coeff,radius=.02,kappa=.5,stop_speed=.003,max_step=1/480):
    """Free-motion prediction only, with a declared numerical stopping threshold.

    No measured state after initialization is injected. Impact trajectories need
    a separate impulse law and explicit event integration.
    """
    c=validate_coefficients(coeff);times=np.asarray(times,dtype=float)
    if len(times)==0 or np.any(np.diff(times)<=0):raise ValueError('Increasing times required')
    z=np.asarray(initial,dtype=float)
    if z.shape!=(6,) or not np.isfinite(z).all():raise ValueError('Finite 6-state required')
    def rhs(t,s):
        a=acceleration(s,c,radius,kappa)
        return [s[2],s[3],a[0],a[1],s[5],a[2]]
    def stopped(t,s):return np.sqrt(s[2]**2+s[3]**2+kappa*(radius*s[5])**2)-stop_speed
    stopped.terminal=True;stopped.direction=-1
    if stopped(0,z)<=0:
        out=np.repeat(z[None,:],len(times),axis=0);out[:,[2,3,5]]=0;return out
    if len(times)==1:return z[None,:]
    sol=solve_ivp(rhs,[times[0],times[-1]],z,rtol=2e-6,atol=1e-9,max_step=max_step,events=stopped,dense_output=True)
    if not sol.success:raise RuntimeError(sol.message)
    end=sol.t[-1];out=sol.sol(np.minimum(times,end)).T
    out[times>end,2:4]=0;out[times>end,5]=0
    return out
