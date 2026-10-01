"""Evaluate the frozen v4 friction fit against the two additional holdout runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pokerchip.config import Body
from pokerchip.physics.farkas import propagate
from pokerchip.storage import clean
from pokerchip.study import free_trials, initialize_fixed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mu = json.loads(args.training.read_text(encoding="utf-8"))["fit"]["parameters"]["mu_bottom"]
    output = []
    for run_id, first_frame in (("20260928_203408", 385), ("20260928_203122", 180)):
        folder = args.runs_root / run_id
        project = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        experiment = project["experiments"][0]
        run = folder / experiment["last_run"]
        config = json.loads((run / "effective_settings.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in (run / "export" / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        rows = [row for row in rows if row["frame_index"] >= first_frame]
        trials = free_trials(config, experiment, rows, [], False)
        for trial in trials:
            body = Body(**trial["body"])
            state, initialization = initialize_fixed(trial, body, mu)
            times = np.asarray(trial["times"])
            observed = np.asarray(trial["position_angle"])
            predicted = propagate(state, body, mu, times - times[0])[:, [0, 1, 4]]
            delta = predicted[1:] - observed[1:]
            distance = np.linalg.norm(delta[:, :2], axis=1)
            result = {
                "video": f"{run_id}.mp4",
                "release_filter": first_frame,
                "mu_fixed": mu,
                "initialization": initialization,
                "scored_frames": trial["frames"][1:],
                "scored_duration_s": float(times[-1] - times[1]),
                "position_rmse_mm": float(np.sqrt(np.mean(distance**2)) * 1000),
                "position_max_mm": float(distance.max() * 1000),
                "angle_rmse_deg": float(np.sqrt(np.mean(delta[:, 2] ** 2)) * 180 / np.pi),
                "times_s": times.tolist(),
                "observed_position_angle": observed.tolist(),
                "predicted_position_angle": predicted.tolist(),
                "scope": "different video; same session; initial 12-frame prefix excluded; frozen friction",
            }
            output.append(result)
            print(
                {key: result[key] for key in ("video", "scored_duration_s", "position_rmse_mm", "angle_rmse_deg")},
                flush=True,
            )
        if not trials:
            output.append({"video": f"{run_id}.mp4", "status": "insufficient_contiguous_segment"})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(clean(output), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
