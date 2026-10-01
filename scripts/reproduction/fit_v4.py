"""Reproduce the exploratory v4 Farkas fit from an extracted run directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pokerchip.config import Body
from pokerchip.fitting import fit_free
from pokerchip.physics.farkas import propagate
from pokerchip.study import free_trials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--training-id", default="20260928_203246")
    parser.add_argument("--release-filter-frame", type=int, default=184)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    folder = args.runs_root / args.training_id
    project = json.loads((folder / "audit_result.json").read_text(encoding="utf-8"))["result"]["project"]
    experiment = project["experiments"][0]
    run = folder / experiment["last_run"]
    config = json.loads((run / "effective_settings.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run / "export" / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows = [row for row in rows if row["frame_index"] >= args.release_filter_frame]
    trials = free_trials(config, experiment, rows, [], True)
    print("trials", len(trials), flush=True)

    fit = fit_free(trials, starts=(0.15, 0.35), max_nfev=100, exploratory=True)
    metrics = []
    for trial in trials:
        times = np.asarray(trial["times"])
        prediction = propagate(
            fit["initial_states"][trial["id"]],
            Body(**trial["body"]),
            fit["parameters"]["mu_bottom"],
            times - times[0],
        )[:, [0, 1, 4]]
        delta = prediction - np.asarray(trial["position_angle"])
        metrics.append(
            {
                "first_frame": trial["frames"][0],
                "last_frame": trial["frames"][-1],
                "samples": len(times),
                "position_rmse_mm": float(np.sqrt(np.mean(np.sum(delta[:, :2] ** 2, axis=1))) * 1000),
                "angle_rmse_deg": float(np.sqrt(np.mean(delta[:, 2] ** 2)) * 180 / np.pi),
            }
        )

    result = {
        "training_metrics": metrics,
        "actual_audit_assumptions": "nominal scale, time and uniform-disk inertia; not independently measured",
        "training_video": f"{args.training_id}.mp4",
        "training_release_filter_frame": args.release_filter_frame,
        "calibration": "20260928_203026.mp4",
        "training_trials": trials,
        "fit": fit,
        "scope": "exploratory model fit against video-derived observations; not independent absolute truth",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(fit["parameters"], fit["optimizer_success"], flush=True)


if __name__ == "__main__":
    main()
