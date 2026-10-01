"""Evaluate and plot the primary held-out v4 Farkas trajectory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
    parser.add_argument("--plot", type=Path, required=True)
    parser.add_argument("--holdout-id", default="20260928_203310")
    parser.add_argument("--release-filter-frame", type=int, default=180)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    training = json.loads(args.training.read_text(encoding="utf-8"))
    mu = training["fit"]["parameters"]["mu_bottom"]
    folder = args.runs_root / args.holdout_id
    project = json.loads((folder / "audit_result.json").read_text(encoding="utf-8"))["result"]["project"]
    experiment = project["experiments"][0]
    run = folder / experiment["last_run"]
    config = json.loads((run / "effective_settings.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run / "export" / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows = [row for row in rows if row["frame_index"] >= args.release_filter_frame]
    trials = free_trials(config, experiment, rows, [], False)
    results = []

    for trial in trials:
        body = Body(**trial["body"])
        state, initialization = initialize_fixed(trial, body, mu)
        times = np.asarray(trial["times"])
        observed = np.asarray(trial["position_angle"])
        predicted = propagate(state, body, mu, times - times[0])[:, [0, 1, 4]]
        delta = predicted[1:] - observed[1:]
        distance = np.linalg.norm(delta[:, :2], axis=1)
        result = {
            "video": f"{args.holdout_id}.mp4",
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
            "scope": "different video; same session; measured initial 12-frame prefix excluded from score; no held-out friction refit",
        }
        results.append(result)

        figure, axes = plt.subplots(1, 3, figsize=(13, 3.8), layout="constrained")
        axes[0].plot(observed[:, 0] * 1000, observed[:, 1] * 1000, ".", ms=3, label="Video observation")
        axes[0].plot(predicted[:, 0] * 1000, predicted[:, 1] * 1000, label="Frozen-mu prediction")
        axes[0].set(xlabel="x (mm)", ylabel="y (mm)", title="Held-out trajectory")
        axes[0].axis("equal")
        axes[0].legend(fontsize=8)
        axes[1].plot(times[1:] - times[0], distance * 1000)
        axes[1].set(
            xlabel="Prediction time (s)",
            ylabel="Position error (mm)",
            title=f"RMSE {result['position_rmse_mm']:.2f} mm",
        )
        axes[2].plot(times - times[0], np.degrees(observed[:, 2] - observed[0, 2]), ".", ms=3)
        axes[2].plot(times - times[0], np.degrees(predicted[:, 2] - observed[0, 2]))
        axes[2].set(
            xlabel="Prediction time (s)",
            ylabel="Rotation (degrees)",
            title=f"Angle RMSE {result['angle_rmse_deg']:.1f} deg",
        )
        for axis in axes:
            axis.grid(alpha=0.25)
        figure.suptitle(
            f"Train: {training['training_video']} | Hold-out: {args.holdout_id} | "
            "nominal geometry/time | not absolute accuracy",
            fontsize=10,
        )
        args.plot.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.plot, dpi=160)
        plt.close(figure)
        print(
            {
                key: result[key]
                for key in ("video", "mu_fixed", "position_rmse_mm", "position_max_mm", "angle_rmse_deg", "scored_duration_s")
            },
            flush=True,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(clean(results), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
