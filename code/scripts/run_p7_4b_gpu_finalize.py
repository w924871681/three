"""Execution-only GPU bootstrap for the frozen P7.4B finalizer.

The frozen runner still owns all data loading, metrics, decision rules, report
generation, and the final Git commit.  Only its 4,000-draw paired bootstrap is
replaced by the algebraically equivalent center-statistic GPU calculation.
This file must be frozen in a separate execution record before ``run``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_p7_4b as frozen  # noqa: E402


CHECKPOINTS = ROOT / "results/p7_4b/gpu_bootstrap_checkpoints"
SEED = 2904
RESAMPLES = 4000
PREDICTION_COLUMNS = [
    "center_id", "A0_target", "A0_prediction", "A1_target", "A1_prediction",
]
PAUSED_OUTPUT_HASHES = {
    "validation_predictions.csv": "8005857261909602aee7e928e96b514c46f907e131649944f6d5d8f5c3db9aac",
    "validation_metrics.csv": "9ec2a260d7a6e8b0fdbb8ba310fa82badd9f1d7f48989cce3005f1459dc20cdb",
    "metrics_by_center.csv": "9c5790fdba4c924e31be081e12369d748f274448964e495863ab16ea9ff3e585",
    "metrics_by_scenario.csv": "da726b35da3b5e0fb8d84e4e7f5a0d5c56523296e2c7e8ce714a5efc3428a5d5",
    "metrics_by_stratum.csv": "e445bf5def66dfde42580d6c254717430b2204d89016fbe4c1d37dda3a530044",
    "reference_scale_audit.csv": "d22deba235437c938322199b1f38a817697310902cecd6d79cdaa1437112787f",
    "paired_a1_vs_a0.csv": "fcc7df5b92fbab9f596625bab8d4c60786f39f4aa738c40a0cf02a937e2ad444",
    "paired_bootstrap_samples.csv": "ea2e8b6a91c46646c977ade35758d62bede91096598d72601703564ea2ce8c3f",
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_hash(frame: pd.DataFrame, centers: list[int]) -> str:
    # Match the input's row order and float64 values, not merely its file name.
    raw = frame[PREDICTION_COLUMNS].to_csv(
        index=False, lineterminator="\n", float_format="%.17g"
    ).encode("utf-8")
    return hashlib.sha256(
        json.dumps(centers, separators=(",", ":")).encode("ascii") + b"\n" + raw
    ).hexdigest()


def _center_stats(frame: pd.DataFrame, centers: list[int]) -> dict:
    values: dict[str, dict[str, list[float]]] = {}
    for rep in ("A0", "A1"):
        table = frozen.center_metrics(frame, f"{rep}_target", f"{rep}_prediction")
        by_center = table.set_index("center_id")
        if set(by_center.index) != set(centers):
            raise AssertionError("GPU bootstrap center set mismatch")
        values[rep] = {
            name: [float(by_center.loc[c, name]) for c in centers]
            for name in ("spearman", "tpr", "tnr")
        }
        if not np.isfinite(values[rep]["spearman"]).all():
            raise AssertionError("undefined center Spearman in bootstrap")
    return values


def _draw_positions(centers: list[int], resamples: int) -> list[list[int]]:
    rng = np.random.default_rng(SEED)
    positions = {center: index for index, center in enumerate(centers)}
    # One choice call per replicate, exactly like the frozen bootstrap.
    return [
        [positions[int(center)] for center in rng.choice(centers, len(centers), replace=True)]
        for _ in range(resamples)
    ]


def _gpu_worker() -> None:
    import torch  # imported only in the CUDA-enabled worker environment

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA PyTorch unavailable; no CPU fallback is permitted")
    request = json.load(sys.stdin)
    device = torch.device("cuda:0")
    picks = torch.tensor(request["draw_positions"], dtype=torch.int64, device=device)
    summaries: dict[str, tuple] = {}
    for rep in ("A0", "A1"):
        values = request["center_stats"][rep]
        spearman = torch.tensor(values["spearman"], dtype=torch.float64, device=device)
        tpr = torch.tensor(values["tpr"], dtype=torch.float64, device=device)
        tnr = torch.tensor(values["tnr"], dtype=torch.float64, device=device)
        summaries[rep] = (
            torch.mean(spearman[picks], dim=1),
            0.5 * (torch.nanmean(tpr[picks], dim=1) + torch.nanmean(tnr[picks], dim=1)),
        )
    delta_s = summaries["A1"][0] - summaries["A0"][0]
    delta_b = summaries["A1"][1] - summaries["A0"][1]
    output = {
        "Delta_macro_Spearman": delta_s.cpu().tolist(),
        "Delta_balanced_admission_accuracy": delta_b.cpu().tolist(),
    }
    if not np.isfinite(output["Delta_macro_Spearman"]).all() or not np.isfinite(
        output["Delta_balanced_admission_accuracy"]
    ).all():
        raise AssertionError("undefined paired GPU bootstrap replicate")
    json.dump(output, sys.stdout, allow_nan=False)


def _gpu_samples(
    frame: pd.DataFrame, centers: list[int], resamples: int, gpu_python: Path
) -> pd.DataFrame:
    request = {
        "draw_positions": _draw_positions(centers, resamples),
        "center_stats": _center_stats(frame, centers),
    }
    child = subprocess.run(
        [str(gpu_python), str(Path(__file__).resolve()), "gpu-worker"],
        input=json.dumps(request, allow_nan=True), text=True, capture_output=True,
        cwd=ROOT, timeout=120, check=False,
    )
    if child.returncode:
        raise RuntimeError(f"GPU worker failed: {child.stderr[-3000:]}")
    values = json.loads(child.stdout)
    result = pd.DataFrame({
        "replicate": range(resamples),
        "Delta_macro_Spearman": values["Delta_macro_Spearman"],
        "Delta_balanced_admission_accuracy": values["Delta_balanced_admission_accuracy"],
    })
    if len(result) != resamples or not np.isfinite(result.iloc[:, 1:].to_numpy()).all():
        raise AssertionError("GPU bootstrap returned invalid samples")
    return result


def _intervals(samples: pd.DataFrame) -> dict:
    return {
        key: [
            float(np.quantile(samples[key], 0.025, method="linear")),
            float(np.quantile(samples[key], 0.975, method="linear")),
        ]
        for key in ("Delta_macro_Spearman", "Delta_balanced_admission_accuracy")
    }


def _checkpoint_name(centers: list[int], all_centers: list[int]) -> str:
    missing = set(all_centers) - set(centers)
    if not missing and len(centers) == len(all_centers):
        return "main"
    if len(missing) == 1 and len(centers) == len(all_centers) - 1:
        return f"loo_omit_{missing.pop()}"
    raise AssertionError("unexpected P7.4B bootstrap center selection")


def _checkpointed_bootstrap(
    frame: pd.DataFrame, centers: list[int], resamples: int,
    all_centers: list[int], gpu_python: Path,
) -> tuple[dict, pd.DataFrame]:
    if resamples != RESAMPLES:
        raise AssertionError("frozen bootstrap count changed")
    key = _checkpoint_name(centers, all_centers)
    path = CHECKPOINTS / f"{key}.json"
    receipt = CHECKPOINTS / f"{key}.sha256"
    input_hash = _input_hash(frame, centers)
    if path.exists() or receipt.exists():
        if not path.exists() or not receipt.exists():
            raise AssertionError(f"incomplete bootstrap checkpoint: {key}")
        if _file_hash(path) != receipt.read_text(encoding="ascii").strip():
            raise AssertionError(f"bootstrap checkpoint hash mismatch: {key}")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["schema"] != "p7.4b-gpu-bootstrap-checkpoint-v1" or saved["input_sha256"] != input_hash:
            raise AssertionError(f"bootstrap checkpoint input mismatch: {key}")
        if saved["seed"] != SEED or saved["resamples"] != resamples or saved["centers"] != centers:
            raise AssertionError(f"bootstrap checkpoint protocol mismatch: {key}")
        samples = pd.DataFrame(saved["samples"])
    else:
        samples = _gpu_samples(frame, centers, resamples, gpu_python)
        saved = {
            "schema": "p7.4b-gpu-bootstrap-checkpoint-v1",
            "input_sha256": input_hash, "centers": centers,
            "seed": SEED, "resamples": resamples,
            "samples": samples.to_dict(orient="list"),
        }
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(saved, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
        receipt.write_text(_file_hash(path) + "\n", encoding="ascii")
        print(f"GPU_BOOTSTRAP_CHECKPOINT {key}", flush=True)
    if len(samples) != resamples or list(samples.columns) != [
        "replicate", "Delta_macro_Spearman", "Delta_balanced_admission_accuracy"
    ] or not np.array_equal(samples.replicate.to_numpy(), np.arange(resamples)):
        raise AssertionError(f"bootstrap checkpoint contents invalid: {key}")
    return _intervals(samples), samples


def _verify(gpu_python: Path) -> list[int]:
    assignment, _, _ = frozen.preflight(require_fit=True, require_opening=True)
    centers = list(map(int, assignment["pools"]["RepresentationValidation"]))
    for name, expected in PAUSED_OUTPUT_HASHES.items():
        if _file_hash(frozen.RESULTS / name) != expected:
            raise AssertionError(f"paused P7.4B output hash mismatch: {name}")
    predicted = pd.read_csv(frozen.RESULTS / "validation_predictions.csv")
    baseline = pd.read_csv(frozen.RESULTS / "paired_bootstrap_samples.csv")
    if len(baseline) != RESAMPLES:
        raise AssertionError("frozen main bootstrap receipt has wrong length")
    accelerated = _gpu_samples(predicted, centers, RESAMPLES, gpu_python)
    columns = ["Delta_macro_Spearman", "Delta_balanced_admission_accuracy"]
    maximum = float(np.max(np.abs(accelerated[columns].to_numpy() - baseline[columns].to_numpy())))
    if not np.isfinite(maximum) or maximum > 1e-12:
        raise AssertionError(f"GPU/main-CPU replicate mismatch: max absolute error {maximum}")
    for omitted in (centers[0], centers[-1]):
        subset = predicted[predicted.center_id != omitted]
        remaining = [center for center in centers if center != omitted]
        _, serial = frozen.bootstrap(subset, remaining, resamples=8)
        gpu = _gpu_samples(subset, remaining, 8, gpu_python)
        error = float(np.max(np.abs(serial[columns].to_numpy() - gpu[columns].to_numpy())))
        if not np.isfinite(error) or error > 1e-12:
            raise AssertionError(f"GPU/CPU LOO sample mismatch, omitted {omitted}: {error}")
    print(f"GPU_NUMERIC_EQUIVALENCE_PASS max_main_abs_error={maximum:.3g}", flush=True)
    return centers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("gpu-worker", "verify", "run"))
    parser.add_argument("--gpu-python", type=Path)
    args = parser.parse_args()
    if args.command == "gpu-worker":
        _gpu_worker()
        return
    if args.gpu_python is None or not args.gpu_python.is_file():
        parser.error("--gpu-python must name the verified CUDA-enabled Python runtime")
    centers = _verify(args.gpu_python)
    if args.command == "verify":
        return
    if frozen.FINAL_AUDIT.exists() or (ROOT / "results/p7_4b/leave_one_center_out.csv").exists():
        raise AssertionError("final output exists; refusing to overwrite a completed run")
    frozen.bootstrap = lambda frame, selected, resamples=RESAMPLES: _checkpointed_bootstrap(
        frame, list(map(int, selected)), resamples, centers, args.gpu_python
    )
    frozen.finalize()


if __name__ == "__main__":
    main()
