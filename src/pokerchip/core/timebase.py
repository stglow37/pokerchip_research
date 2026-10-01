"""PTS / slow factor; Samsung 240 capture fps becomes 30 playback fps at x8.
Declared timing permits provisional measurements, not independently verified fits.
"""
import math
import numpy as np


class TimeProfile:
    def __init__(self, profile, mode="experiment"):
        self.profile, self.mode = profile, mode
        self.segments = profile.get("segments", [])
        if not self.segments: raise ValueError("시간 구간이 필요합니다.")
        if profile.get("exposure_reference", "unknown") not in ("start","midpoint","end","unknown"):
            raise ValueError("노출 기준은 start/midpoint/end/unknown 중 하나입니다.")
        exp=profile.get("exposure_s")
        if exp is not None and (not math.isfinite(exp) or exp <= 0): raise ValueError("노출시간은 실제 초 단위의 양수입니다.")
        readout=profile.get("rolling_readout_s")
        if readout is not None and (not math.isfinite(readout) or readout<0):raise ValueError("행 읽기 시간은 0 이상의 실제 초 단위입니다.")
        previous = None
        for i,s in enumerate(self.segments):
            if not all(math.isfinite(s[k]) for k in ("p_start","t_start","slow_factor")) or s["slow_factor"] <= 0:
                raise ValueError("시간 배율은 유한한 양수입니다.")
            end=s.get("p_end")
            if end is None and i != len(self.segments)-1: raise ValueError("마지막 구간만 열린 끝을 허용합니다.")
            if end is not None and (not math.isfinite(end) or end <= s["p_start"]): raise ValueError("시간 구간 끝은 시작보다 커야 합니다.")
            if previous:
                expected=previous["t_start"]+(previous["p_end"]-previous["p_start"])/previous["slow_factor"]
                if abs(previous["p_end"]-s["p_start"])>1e-9 or abs(expected-s["t_start"])>1e-9:
                    raise ValueError("시간 변환 구간이 비연속적입니다.")
            previous=s
        if profile.get("status") in ("declared","verified") and not profile.get("evidence","").strip():
            raise ValueError("촬영 조건 또는 독립 시간 검증 근거를 입력하세요.")

    @property
    def verified(self):
        return self.profile.get("status")=="verified" or (self.mode=="synthetic_demo" and self.profile.get("status")=="synthetic_known_clock")

    @property
    def usable(self): return self.verified or self.profile.get("status")=="declared"

    def map(self, presentation_s):
        if presentation_s is None or not math.isfinite(presentation_s) or not self.usable: return None
        for s in self.segments:
            if presentation_s>=s["p_start"] and (s.get("p_end") is None or presentation_s<=s["p_end"]):
                return s["t_start"]+(presentation_s-s["p_start"])/s["slow_factor"]
        return None

    def timing(self, frame, previous_p=None):
        p=frame["presentation_time_s"]
        good=p is not None and (previous_p is None or p>previous_p)
        source_type=self.profile.get("frame_types",{}).get(str(frame["frame_index"]),"native_unconfirmed")
        independent=source_type not in ("duplicate","interpolated","missing")
        physical=self.map(p) if good and independent else None
        exp=self.profile.get("exposure_s");midpoint=None
        if physical is not None and exp is not None:
            shift={"start":.5,"midpoint":0.,"end":-.5}.get(self.profile.get("exposure_reference"))
            if shift is not None: midpoint=physical+shift*exp
        status=("verified" if self.verified else "declared_provisional") if physical is not None else "timebase_unverified"
        return {**frame,"physical_time_s":physical,"exposure_midpoint_s":midpoint,
                "exposure_s":exp,"source_frame_type":source_type,"independent_observation":independent,
                "time_status":status,"time_reason":None if status=="verified" else
                "사용자 촬영 조건으로 계산한 잠정 시간; 독립 시계 검증 전" if physical is not None else
                "시간 근거/PTS/구간/원본 프레임 여부 확인 필요"}


def verify_clock(profile, presentation_times, reference_times, tolerance_s=.001):
    p=np.asarray(presentation_times,float);t=np.asarray(reference_times,float)
    if p.shape!=t.shape or p.ndim!=1 or len(p)<3 or not np.isfinite([p,t]).all() or np.any(np.diff(p)<=0) or np.any(np.diff(t)<=0):
        raise ValueError("서로 증가하는 독립 시계 대응점 3개 이상이 필요합니다.")
    provisional={**profile,"status":"declared","evidence":profile.get("evidence") or "clock comparison"}
    mapped=[TimeProfile(provisional).map(x) for x in p]
    if any(x is None for x in mapped):raise ValueError("시간 구간 밖의 시계 대응점입니다.")
    error=(np.asarray(mapped)-mapped[0])-(t-t[0])
    maximum=float(np.max(abs(error)))
    if not math.isfinite(tolerance_s) or tolerance_s<=0:raise ValueError("시간 허용오차는 양수")
    return {"passed":maximum<=tolerance_s,"max_error_s":maximum,"rmse_s":float(np.sqrt(np.mean(error**2))),
            "tolerance_s":tolerance_s,"presentation_times_s":p.tolist(),"reference_times_s":t.tolist(),
            "scope":"elapsed_time_mapping_only_not_frame_interpolation_or_rolling_shutter"}


def cadence_report(times, capture_fps=240.):
    if not math.isfinite(capture_fps) or capture_fps<=0:raise ValueError("촬영 fps는 유한한 양수")
    previous=None;sample=[];n=bad=gaps=0;rng=np.random.default_rng(240)
    for row in times:
        value=row.get("physical_time_s")
        if value is None:continue
        if previous is not None:
            dt=value-previous
            if dt<=0:bad+=1
            else:
                n+=1;gaps+=dt>1.5/capture_fps
                if len(sample)<4096:sample.append(dt)
                else:
                    j=int(rng.integers(n))
                    if j<4096:sample[j]=dt
        previous=value
    if not sample:return {"status":"unavailable"}
    median=float(np.median(sample));effective=1/median
    return {"status":"consistent" if abs(effective/capture_fps-1)<.03 else "review_required",
            "effective_unique_fps":effective,"expected_capture_fps":capture_fps,"median_dt_s":median,
            "nonpositive_intervals":bad,"gap_intervals":int(gaps),"interval_count":n,"median_sample_count":len(sample),
            "note":"PTS 간격 검사이며 native 프레임 증명은 아닙니다."}
