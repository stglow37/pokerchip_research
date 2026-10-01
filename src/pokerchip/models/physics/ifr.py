"""Signed impulses on body 2; model reconstruction is explicit, not an erratum."""
import numpy as np

MODELS = ("contact_consistent_reconstruction", "percussion_paper_scope")


def invariants(states, bodies, origin=(0., 0.)):
    momentum = np.zeros(2)
    angular = energy = 0.
    for s, b in zip(states, bodies):
        x, v = np.asarray(s[:2])-origin, np.asarray(s[2:4])
        momentum += b.mass*v
        angular += b.mass*(x[0]*v[1]-x[1]*v[0]) + b.inertia*s[5]
        energy += .5*b.mass*np.dot(v, v) + .5*b.inertia*s[5]**2
    return {"momentum": momentum, "angular_momentum": float(angular), "energy": float(energy)}


def contact_velocity(states, bodies, normal):
    n = np.asarray(normal, float)
    if n.shape != (2,) or not np.isfinite(n).all() or np.linalg.norm(n) == 0:
        raise ValueError("유효한 접촉 법선 필요")
    n = n/np.linalg.norm(n)
    t = np.array([-n[1], n[0]])
    relative = states[0, 2:4] - states[1, 2:4]
    return float(relative@n), float(relative@t + bodies[0].radius*states[0, 5] + bodies[1].radius*states[1, 5]), n, t


def impact(states, bodies, e_n, e_t, mu_c, model=MODELS[0], normal=None, require_contact=True):
    s = np.asarray(states, float)
    if s.shape != (2, 6) or not np.isfinite(s).all():
        raise ValueError("2 x 6 유한 충돌 상태 필요")
    if not (0 <= e_n <= 1 and -1 <= e_t <= 1 and mu_c >= 0) or not np.isfinite([e_n, e_t, mu_c]).all():
        return {"status": "invalid", "reason": "계수 경계 위반", "post": None}
    if model not in MODELS:
        raise ValueError("알 수 없는 IFR 모델")
    b1, b2 = bodies
    separation = s[1, :2] - s[0, :2]
    distance = np.linalg.norm(separation)
    if distance == 0:
        return {"status": "invalid", "reason": "중심 중첩", "post": None}
    if require_contact and abs(distance-b1.radius-b2.radius) > 1e-7:
        return {"status": "invalid", "reason": "접촉 기하 아님", "post": None}
    a, c, n, t = contact_velocity(s, bodies, separation if normal is None else normal)
    if a <= 1e-12:
        return {"status": "separating", "reason": "새 접근 충돌 아님", "post": s.copy(), "J_n": 0., "J_t": 0.}
    if model == MODELS[1] and (max(abs(s[:, 5])) > 1e-10 or any(not np.isclose(b.inertia, .5*b.mass*b.radius**2, rtol=1e-8, atol=1e-15) for b in bodies)):
        return {"status": "unsupported", "reason": "percussion은 무초기회전·균질 원판 범위만 지원", "post": None}
    An = 1/b1.mass + 1/b2.mass
    At = An + b1.radius**2/b1.inertia + b2.radius**2/b2.inertia
    As = At if model == MODELS[0] else 2*An
    Jn = (1+e_n)*a/An
    Jte = (1+e_t)*c/At
    Jf = np.sign(c)*min(mu_c*Jn, abs(c)/As)
    Jt = Jte+Jf
    impulse = Jn*n + Jt*t
    post = s.copy()
    post[0, 2:4] -= impulse/b1.mass
    post[1, 2:4] += impulse/b2.mass
    post[0, 5] -= b1.radius*Jt/b1.inertia
    post[1, 5] -= b2.radius*Jt/b2.inertia
    before, after = invariants(s, bodies), invariants(post, bodies)
    dK = -a*Jn+.5*An*Jn*Jn-c*Jt+.5*At*Jt*Jt
    admissible = dK <= 1e-12 + 1e-10*before["energy"]
    return {"status": "ok" if admissible else "invalid", "reason": None if admissible else "수동 충돌 total energy 증가",
            "post": post if admissible else None, "candidate_post": post if not admissible else None,
            "J_n": Jn, "J_t": Jt, "J_te": Jte, "J_f": Jf, "a": a, "c": c,
            "c_after": c-At*Jt, "e_t": e_t, "e_t_obs": -(c-At*Jt)/c if abs(c) > 1e-10 else None,
            "branch": "sliding" if mu_c*Jn < abs(c)/As else "sticking",
            "friction_saturation_margin_Ns": mu_c*Jn-abs(c)/As,
            "branch_definition": "friction_component_saturation_not_total_contact_sticking",
            "contact_slip_after_m_s": c-At*Jt,
            "normal": n, "tangent": t, "model": model, "arbitrary_spin_scope": "mathematical_extension_unvalidated" if model == MODELS[0] else "paper_no_spin",
            "delta_energy_formula": dK, "energy_before": before["energy"], "energy_after": after["energy"],
            "momentum_residual": after["momentum"]-before["momentum"],
            "angular_momentum_residual": after["angular_momentum"]-before["angular_momentum"]}
