"""Farkas -> earliest dense swept root -> IFR -> Farkas, with contact-graph gates."""
from itertools import combinations
import numpy as np
from scipy.optimize import brentq, minimize_scalar
from .farkas import FreeSolution
from .ifr import impact


def simulate(initial, bodies, times, mu_bottom, e_normal, e_tangential, mu_collision,
             model="contact_consistent_reconstruction", rtol=1e-8,
             event_uncertainty_s=1e-7, max_events=1000):
    times = np.asarray(times, float)
    state = np.asarray(initial, float).copy()
    if times.ndim!=1 or len(times) == 0 or not bodies or not np.isfinite(times).all() or not np.isfinite(state).all() or times[0] < 0 or np.any(np.diff(times) <= 0) or state.shape != (len(bodies), 6):
        raise ValueError("시뮬레이션 상태/시간 배열 오류")
    if not np.isfinite([mu_bottom,e_normal,e_tangential,mu_collision,rtol,event_uncertainty_s]).all() or mu_bottom<0 or not 0<=e_normal<=1 or not -1<=e_tangential<=1 or mu_collision<0 or rtol<=0 or event_uncertainty_s<0:
        raise ValueError("물리계수 또는 허용오차 범위 오류")
    if len(times) > 200000:
        raise ValueError("한 요청은 200000 표본 이하로 나누세요.")
    pairs = list(combinations(range(len(bodies)), 2))
    output, events, now, index = [], [], 0., 0
    status, reason = "complete", None
    while now < times[-1] + 1e-12 and index < len(times):
        contacts = []
        for i, j in pairs:
            d = state[j, :2]-state[i, :2]
            gap = np.linalg.norm(d)-bodies[i].radius-bodies[j].radius
            if gap < -1e-7:
                return {"status": "unsupported", "reason": "initial_overlap", "times": times[:index], "states": np.array(output), "events": events}
            if gap <= 1e-8:
                a = (state[i, 2:4]-state[j, 2:4])@d/np.linalg.norm(d)
                if abs(a) < 1e-10:
                    return {"status": "unsupported", "reason": "persistent_contact", "times": times[:index], "states": np.array(output), "events": events}
                if a > 0:
                    contacts.append((now, i, j))
        remaining = float(times[-1]-now)
        free = [FreeSolution(s, b, mu_bottom, max(0., remaining), rtol=rtol) for s, b in zip(state, bodies)]
        # Each interval bounds relative travel; a minimizer catches grazing/enter-exit within it.
        speed = max(np.linalg.norm(s[2:4]) for s in state)
        step = min(.02, .4*min(b.radius for b in bodies)/max(2*speed, 1e-12))
        roots = contacts[:]
        if not roots and remaining > 0:
            left = 0.
            while left < remaining:
                right = min(remaining, left+step)
                for i, j in pairs:
                    radius = bodies[i].radius+bodies[j].radius
                    def gap(t):
                        return np.linalg.norm(free[j](t)[:2]-free[i](t)[:2])-radius
                    gl, gr = gap(left), gap(right)
                    if left == 0 and gl <= 1e-8:
                        probe = min(right, max(1e-8, right*1e-5))
                        l = probe
                        gl = gap(l)
                    else:
                        l = left
                    if l >= right:
                        continue
                    if min(gl, gr) > 2*speed*(right-l)+1e-8:
                        continue
                    minimum = minimize_scalar(gap, bounds=(l, right), method="bounded", options={"xatol": 1e-12})
                    tmin = minimum.x if minimum.fun < gr else right
                    if gl > 0 and gap(tmin) <= 0:
                        root = brentq(gap, l, tmin, xtol=1e-12)
                        roots.append((now+root, i, j))
                if roots:
                    break
                left = right
        tc = min(r[0] for r in roots) if roots else float(times[-1])
        while index < len(times) and times[index] < tc-1e-11:
            output.append(np.array([f(times[index]-now) for f in free]))
            index += 1
        pre = np.array([f(max(0., tc-now)) for f in free])
        if not roots:
            while index < len(times):
                output.append(np.array([f(times[index]-now) for f in free]))
                index += 1
            break
        active = [(i,j) for tr,i,j in roots if abs(tr-tc) <= event_uncertainty_s]
        # Include a third disk already touching a member at the event, even if static.
        for i,j in pairs:
            if (i,j) not in active and np.linalg.norm(pre[j,:2]-pre[i,:2]) <= bodies[i].radius+bodies[j].radius+1e-8:
                active.append((i,j))
        if len(active) > 1:
            reason = "simultaneous_multi_contact" if all(abs(tr-tc) < 1e-9 for tr,_,_ in roots) else "near_simultaneous"
            events.append({"time_s": tc, "pairs": active, "kind": reason, "pre": pre, "post": None})
            status = "unsupported"
            break
        i,j = active[0]
        jump = impact(pre[[i,j]], [bodies[i], bodies[j]], e_normal, e_tangential, mu_collision, model)
        if jump["status"] != "ok":
            status, reason = jump["status"], jump["reason"]
            events.append({"time_s": tc, "pair": [i,j], "pre": pre, "jump": jump})
            break
        state = pre.copy()
        state[[i,j]] = jump["post"]
        events.append({"time_s": tc, "pair": [i,j], "kind": "isolated_binary", "pre": pre, "post": state.copy(), "jump": jump})
        now = tc
        while index < len(times) and abs(times[index]-now) < 1e-11:
            output.append(state.copy())
            index += 1
        if len(events) >= max_events:
            status, reason = "unsupported", "event_limit_or_inelastic_collapse"
            break
    return {"status": status, "reason": reason, "times": times[:len(output)],
            "states": np.array(output), "events": events, "prediction_kind": "full_forward",
            "model": model, "rtol": rtol, "contact_time_uncertainty_s": event_uncertainty_s}
