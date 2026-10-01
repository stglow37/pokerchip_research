"""Full-contact uniform-pressure Farkas model, signed CCW spin."""
import math
import numpy as np
from scipy.special import ellipk, ellipe
from scipy.integrate import solve_ivp
from ...core.config import Body

G = 9.80665
MODEL = "farkas_uniform_pressure_disk_v1"


def functions(epsilon):
    """Dimensionless force/torque. Elliptic modulus k is squared for SciPy."""
    e = float(epsilon)
    if e < 0 or math.isnan(e):
        raise ValueError("epsilon은 음수가 아니어야 합니다.")
    if e == 0:
        return 0., 2 / 3
    if math.isinf(e):
        return 1., 0.
    if e < 1e-3:
        # Taylor series obtained by expanding the area integrals.
        return e - e**3 / 8 - e**5 / 64, 2 / 3 - e*e / 2 + 3*e**4 / 32 + e**6 / 96
    if e > 30:
        q = 1 / e
        return 1 - q*q / 8 - q**4 / 64 - 5*q**6 / 1024, q / 4 + q**3 / 48 + 3*q**5 / 512
    if e == 1:
        return 8 / (3 * np.pi), 8 / (9 * np.pi)
    k = min(e, 1/e)
    K, E = ellipk(k*k), ellipe(k*k)
    if e < 1:
        F = 4 * ((e*e+1)*E + (e*e-1)*K) / (3*np.pi*e)
        T = 4 * ((4-2*e*e)*E + (e*e-1)*K) / (9*np.pi)
    else:
        F = 4 * ((e*e+1)*E - (e*e-1)*K) / (3*np.pi)
        # The supplied 2002 PDF prints division by e here. Independent area
        # integration and Q(e)-e Q'(e) require MULTIPLICATION by e. See decisions.
        T = 4 * e * ((4-2*e*e)*E + (2*e*e-5+3/(e*e))*K) / (9*np.pi)
    return float(F), float(T)


def force_torque(velocity, omega, body: Body, mu, g=G):
    if mu < 0 or not math.isfinite(mu):
        raise ValueError("바닥 마찰계수는 0 이상의 유한값")
    v = np.asarray(velocity, float)
    speed = np.linalg.norm(v)
    if speed == 0 and omega == 0:
        return np.zeros(2), 0.
    F, T = functions(speed/(body.radius*abs(omega)) if omega else np.inf)
    force = -mu*body.mass*g*F*v/speed if speed else np.zeros(2)
    torque = -mu*body.mass*g*body.radius*T*np.sign(omega)
    return force, float(torque)


class FreeSolution:
    """Dense free flight. Pure modes exact; mixed magnitudes integrate to a stop event."""
    def __init__(self, state, body, mu, duration, rtol=1e-8, stop_speed=1e-8):
        self.initial = np.asarray(state, float).copy()
        self.body, self.mu, self.duration = body, float(mu), float(duration)
        if self.initial.shape != (6,) or not np.all(np.isfinite(self.initial)) or not np.isfinite([duration,mu,rtol,stop_speed]).all() or duration < 0 or mu < 0 or rtol <= 0 or stop_speed <= 0:
            raise ValueError("자유운동 상태/시간/계수 오류")
        self.speed = float(np.linalg.norm(self.initial[2:4]))
        self.direction = self.initial[2:4] / self.speed if self.speed else np.zeros(2)
        self.spin = abs(self.initial[5])
        self.sign = np.sign(self.initial[5])
        self.stop_time = None
        self.sol = None
        if self.speed and self.spin and mu and duration:
            def rhs(t, y):
                speed, spin = max(0., y[0]), max(0., y[1])
                F, T = functions(speed/(body.radius*spin) if spin else np.inf)
                return [-mu*G*F if y[0] > 0 else 0.,
                        -mu*body.mass*G*body.radius*T/body.inertia if y[1] > 0 else 0., speed, spin]
            def stop(t, y):
                return max(y[0], body.radius*y[1]) - stop_speed
            stop.terminal, stop.direction = True, -1
            self.sol = solve_ivp(rhs, (0, duration), [self.speed, self.spin, 0., 0.],
                                 dense_output=True, events=stop, rtol=rtol, atol=rtol*1e-3,
                                 max_step=max(duration/20, 1e-6))
            if not self.sol.success:
                raise ArithmeticError(self.sol.message)
            if len(self.sol.t_events[0]):
                self.stop_time = float(self.sol.t_events[0][0])

    def __call__(self, t):
        t = float(t)
        if t < -1e-12 or t > self.duration + 1e-8:
            raise ValueError("자유운동 보간 범위 밖")
        out = self.initial.copy()
        if not self.mu:
            out[:2] += t*out[2:4]
            out[4] += t*out[5]
            return out
        if self.sol is not None:
            q = self.sol.sol(min(t, self.stop_time) if self.stop_time is not None else t)
            speed, spin, distance, angle = q
            if self.stop_time is not None and t >= self.stop_time:
                speed = spin = 0.
        else:
            a, b = self.mu*G, 2*self.mu*self.body.mass*G*self.body.radius/(3*self.body.inertia)
            tv, tw = min(t, self.speed/a), min(t, self.spin/b)
            speed, spin = max(0., self.speed-a*t), max(0., self.spin-b*t)
            distance, angle = self.speed*tv-.5*a*tv*tv, self.spin*tw-.5*b*tw*tw
        out[:2] += distance*self.direction
        out[2:4] = max(0., speed)*self.direction
        out[4] += self.sign*angle
        out[5] = self.sign*max(0., spin)
        return out


def propagate(state, body, mu, times, **kwargs):
    times = np.asarray(times, float)
    if times.ndim != 1 or len(times) == 0 or not np.isfinite(times).all() or np.any(np.diff(times) < 0) or times[0] < 0:
        raise ValueError("증가하는 상대 시간 배열 필요")
    solution = FreeSolution(state, body, mu, float(times[-1]), **kwargs)
    return np.array([solution(t) for t in times])
