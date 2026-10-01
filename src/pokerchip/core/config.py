"""Validated project schema. Missing measurements are never silently imputed."""
from __future__ import annotations
import copy
from dataclasses import dataclass
from pathlib import Path
import math
from .storage import atomic_json, read_json, new_id, file_hash

COLORS = {"chip_1": ("red", "blue"), "chip_2": ("blue", "yellow"), "chip_3": ("green", "red")}

def ensure_chips(project, count):
    if not 1 <= count <= 32:raise ValueError("칩 수는 1~32개로 설정하세요.")
    present={c['id'] for c in project['chips']}
    for i in range(1,count+1):
        key=f'chip_{i}'
        if key not in present:
            c=copy.deepcopy(project['chips'][0]);c.update(id=key,rim_color='auto',inner_color='auto')
            project['chips'].append(c)
    return [f'chip_{i}' for i in range(1,count+1)]


@dataclass(frozen=True)
class Body:
    mass: float
    radius: float
    inertia: float
    id: str = "chip"

    def __post_init__(self):
        if any(not math.isfinite(x) or x <= 0 for x in (self.mass, self.radius, self.inertia)):
            raise ValueError("질량·반지름·관성모멘트는 양수 SI 값이어야 합니다.")

    @classmethod
    def from_chip(cls, chip):
        m, r, inertia = chip.get("mass_kg"), chip.get("radius_m"), chip.get("inertia_kg_m2")
        if m is None or r is None:
            raise ValueError(f"{chip['id']}: 질량/반지름 측정 대기")
        if inertia is None and chip.get("inertia_model") == "uniform_disk":
            inertia = .5 * m * r * r
        if inertia is None:
            raise ValueError(f"{chip['id']}: 관성 측정 또는 명시적 uniform_disk 선택 필요")
        return cls(m, r, inertia, chip["id"])


def default_project(name="새 연구"):
    return {"schema_version": "2.0", "review_schema_version": 1, "id": new_id("project"), "name": name,
            "session_id": "session_1", "mode": "experiment", "seed": 20260927,
            "chips": [{"id": k, "rim_color": v[0], "inner_color": v[1],
                       "radius_m": .020, "radius_status": "nominal_pending", "radius_sigma_m": None,
                       "mass_kg": .012, "thickness_m": None, "inertia_kg_m2": None,
                       "inertia_model": "uniform_disk", "inner_diameter_m": .003,
                       "contact_model": "uniform_pressure_full_disk_assumed"} for k, v in COLORS.items()],
            "time_profile": {"id": "time_pending", "status": "declared", "evidence": "사용자 촬영 조건: 삼성 FHD 240fps, 전체 1/8배속",
                             "capture_fps": 240., "preset": "samsung_fhd240_8x",
                             "segments": [{"p_start": 0., "p_end": None, "t_start": 0., "slow_factor": 8.}],
                             "frame_types": {}, "exposure_s": None, "exposure_reference": "unknown"},
            "calibration": {"id": "geometry_pending", "status": "pending", "H": None,
                            "K": None, "distortion": None, "pose_R": None, "pose_t": None,
                            "capture_mode": "pending", "image_size": None, "valid_polygon_px": None},
            "quick_setup": {"calibration_video": None, "floor_confirmed": False, "rolling_shutter_correction": False,
                            "floor_grid_spacing_m": .430/18, "floor_grid_pitches_m":[.405/18,.430/18],
                            "floor_grid_source":"user: 40.5/18 cm and 43/18 cm; longer image direction automatic"},
            "templates": {}, "experiments": [], "corrections": [], "correction_cursor": 0,
            "analysis": {"detector_profile": "dark_chip", "radius_px": [20, 110], "roi_px": None, "max_candidates": 12,
                         "max_gap_frames": 12, "assignment_gate_px": 90., "redetect_every": 5,
                         "edge_rays": 144, "window_s": .08, "min_samples": 5,
                         "max_window_samples": 161, "omega_bound_rad_s": None,
                         "chunk_frames": 32, "max_frame_bytes": 64 * 1024 * 1024,
                         "max_buffer_bytes": 160 * 1024 * 1024},
            "physics": {"mu_bottom": None, "e_normal": None, "e_tangential": None,
                        "mu_collision": None, "model": "contact_consistent_reconstruction"},
            "plot": {"color": "#2166ac"}, "fit_split": {"train": [], "holdout": [], "unit": "session"}}


def validate(project):
    if project.get("schema_version") != "2.0":
        raise ValueError("지원하지 않는 설정 schema_version")
    if project.get("mode") not in ("experiment", "synthetic_demo"):
        raise ValueError("mode는 experiment 또는 synthetic_demo")
    ids = [x["id"] for x in project["chips"]]
    if not ids or len(ids)>32 or len(ids) != len(set(ids)):
        raise ValueError("서로 다른 칩 ID가 1~32개 필요합니다.")
    for c in project["chips"]:
        if any(c.get(k) not in ('red','blue','yellow','green','auto') for k in ('rim_color','inner_color')):
            raise ValueError("표식 색 설정을 확인하세요.")
        for key in ("mass_kg", "radius_m", "inertia_kg_m2", "thickness_m"):
            x = c.get(key)
            if x is not None and (not isinstance(x, (float, int)) or not math.isfinite(x) or x <= 0):
                raise ValueError(f"{key}: 양수 또는 null 필요")
    exp_ids = [e["id"] for e in project["experiments"]]
    if len(exp_ids) != len(set(exp_ids)):
        raise ValueError("experiment id 중복")
    for e in project["experiments"]:
        if any(k not in ids for k in e["participating_chip_ids"]):
            raise ValueError("참여 칩 ID 오류")
        if len(e["participating_chip_ids"]) != len(set(e["participating_chip_ids"])):
            raise ValueError("참여 칩 ID 중복")
        a, b = e.get("interval", [0, None])
        if a < 0 or (b is not None and b < a):
            raise ValueError("분석 frame 구간 오류")
    from .review import validate_intervals
    for experiment in project["experiments"]:validate_intervals(experiment)
    from .timebase import TimeProfile
    TimeProfile(project["time_profile"], project["mode"])
    a = project["analysis"]
    if a.get("detector_profile","dark_chip")!="dark_chip":
        raise ValueError("이 연구는 검정 칩 + 가장자리 색칠 + 내부 스티커만 지원합니다.")
    radii=a["radius_px"]
    if len(radii)!=2 or not all(math.isfinite(x) for x in radii) or not 0<radii[0]<radii[1]:
        raise ValueError("반지름 탐색 범위를 확인하세요.")
    for key in ("shared_scale_sigma_fraction","shared_clock_sigma_fraction"):
        value=a.get(key,0)
        if not math.isfinite(value) or value<0:raise ValueError("공통 상대 불확실성은 0 이상")
    if a.get("omega_bound_rad_s") is not None and (not math.isfinite(a["omega_bound_rad_s"]) or a["omega_bound_rad_s"]<=0):
        raise ValueError("각속도 안전 상한은 양수 또는 null")
    if not 3 <= a["min_samples"] <= a["max_window_samples"] <= 1001:
        raise ValueError("운동학 샘플 수는 3..1001 범위")
    if a["window_s"] <= 0 or a["max_buffer_bytes"] < 2 * a["max_frame_bytes"]:
        raise ValueError("창 길이 또는 메모리 상한 오류")
    return project


def create_project(folder, name="새 연구"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "project.json").exists():
        raise FileExistsError("기존 프로젝트를 덮어쓸 수 없습니다.")
    p = default_project(name)
    atomic_json(folder / "project.json", p)
    return p


def load_project(folder):
    from .migration import migrate
    return validate(migrate(read_json(Path(folder) / "project.json")))


def save_project(folder, project):
    path = Path(folder) / "project.json"
    if path.exists() and read_json(path).get("schema_version") == "1.0":
        from shutil import copy2
        backup = path.with_name("project.v1.backup.json")
        if not backup.exists(): copy2(path, backup)
    atomic_json(path, validate(project))


def source_path(folder, experiment):
    path = Path(experiment["video_uri"])
    return path if path.is_absolute() else Path(folder) / path


def register(folder, project, paths, chips=None, session=None):
    added = []
    for path in paths:
        path = Path(path).resolve()
        try:
            uri = str(path.relative_to(Path(folder).resolve()))
        except ValueError:
            uri = str(path)
        exp = {"id": new_id("exp"), "session_id": session or project["session_id"],
               "name": path.name, "video_uri": uri, "source_hash": None,
               "participating_chip_ids": list(chips or COLORS), "interval": [0, None],
               "conditions": "", "kind": "experiment", "status": "pending"}
        project["experiments"].append(exp)
        added.append(exp)
    save_project(folder, project)
    return added


def relink(folder, project, experiment_id, path):
    exp = next(e for e in project["experiments"] if e["id"] == experiment_id)
    actual = file_hash(path)
    if exp.get("source_hash") and actual != exp["source_hash"]:
        raise ValueError("원본 SHA-256 불일치: 재연결할 수 없습니다.")
    exp["video_uri"] = str(Path(path).resolve())
    exp["source_hash"] = actual
    save_project(folder, project)


def effective(project, experiment):
    result = copy.deepcopy(project)
    for key in ("time_profile", "calibration", "analysis", "templates"):
        if key in experiment:
            result[key] = copy.deepcopy(experiment[key])
    return validate(result)
