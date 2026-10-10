"""Audited, execution-only recovery from the P7.4B CUDA driver crash.

Reuses only complete hash-valid GPU checkpoints. Remaining frozen bootstrap
draws are aggregated with NumPy; no scientific input or decision rule changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_p7_4b as frozen  # noqa: E402
from scripts import run_p7_4b_gpu_finalize as gpu  # noqa: E402

CHECKPOINTS = ROOT / "results/p7_4b/cpu_recovery_checkpoints"
COLUMNS = ["Delta_macro_Spearman", "Delta_balanced_admission_accuracy"]


def cpu_samples(frame: pd.DataFrame, centers: list[int], resamples: int) -> pd.DataFrame:
    positions = np.asarray(gpu._draw_positions(centers, resamples), dtype=np.intp)
    stats = gpu._center_stats(frame, centers)
    summaries = {}
    for rep in ("A0", "A1"):
        values = stats[rep]
        spearman = np.asarray(values["spearman"], dtype=np.float64)
        tpr = np.asarray(values["tpr"], dtype=np.float64)
        tnr = np.asarray(values["tnr"], dtype=np.float64)
        summaries[rep] = (
            np.mean(spearman[positions], axis=1),
            0.5 * (np.nanmean(tpr[positions], axis=1) + np.nanmean(tnr[positions], axis=1)),
        )
    samples = pd.DataFrame({
        "replicate": np.arange(resamples),
        COLUMNS[0]: summaries["A1"][0] - summaries["A0"][0],
        COLUMNS[1]: summaries["A1"][1] - summaries["A0"][1],
    })
    if len(samples) != resamples or not np.isfinite(samples[COLUMNS].to_numpy()).all():
        raise AssertionError("undefined or incomplete vectorized bootstrap replicate")
    return samples


def _read_checkpoint(path: Path, receipt: Path, expected_schema: str,
                     frame: pd.DataFrame, centers: list[int], resamples: int) -> pd.DataFrame:
    if not path.is_file() or not receipt.is_file():
        raise AssertionError(f"incomplete checkpoint: {path.name}")
    if gpu._file_hash(path) != receipt.read_text(encoding="ascii").strip():
        raise AssertionError(f"checkpoint SHA-256 mismatch: {path.name}")
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (saved["schema"] != expected_schema or saved["input_sha256"] != gpu._input_hash(frame, centers)
            or saved["centers"] != centers or saved["seed"] != gpu.SEED
            or saved["resamples"] != resamples):
        raise AssertionError(f"checkpoint provenance mismatch: {path.name}")
    samples = pd.DataFrame(saved["samples"])
    if (list(samples.columns) != ["replicate", *COLUMNS] or len(samples) != resamples
            or not np.array_equal(samples.replicate.to_numpy(), np.arange(resamples))
            or not np.isfinite(samples[COLUMNS].to_numpy()).all()):
        raise AssertionError(f"invalid checkpoint samples: {path.name}")
    return samples


def _checkpointed(frame: pd.DataFrame, centers: list[int], all_centers: list[int],
                  resamples: int) -> tuple[dict, pd.DataFrame]:
    if resamples != gpu.RESAMPLES:
        raise AssertionError("frozen bootstrap draw count changed")
    name = gpu._checkpoint_name(centers, all_centers)
    old = gpu.CHECKPOINTS / f"{name}.json"
    old_receipt = gpu.CHECKPOINTS / f"{name}.sha256"
    new = CHECKPOINTS / f"{name}.json"
    new_receipt = CHECKPOINTS / f"{name}.sha256"
    if old.exists() or old_receipt.exists():
        if new.exists() or new_receipt.exists():
            raise AssertionError(f"duplicate checkpoint provenance: {name}")
        samples = _read_checkpoint(old, old_receipt, "p7.4b-gpu-bootstrap-checkpoint-v1",
                                   frame, centers, resamples)
    elif new.exists() or new_receipt.exists():
        samples = _read_checkpoint(new, new_receipt,
                                   "p7.4b-cpu-vector-bootstrap-checkpoint-v1",
                                   frame, centers, resamples)
    else:
        samples = cpu_samples(frame, centers, resamples)
        payload = {
            "schema": "p7.4b-cpu-vector-bootstrap-checkpoint-v1",
            "input_sha256": gpu._input_hash(frame, centers),
            "centers": centers, "seed": gpu.SEED, "resamples": resamples,
            "samples": samples.to_dict(orient="list"),
        }
        CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        temporary = new.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(new)
        new_receipt.write_text(gpu._file_hash(new) + "\n", encoding="ascii")
        print(f"CPU_RECOVERY_CHECKPOINT {name}", flush=True)
    return gpu._intervals(samples), samples


def verify() -> list[int]:
    assignment, _, _ = frozen.preflight(require_fit=True, require_opening=True)
    centers = list(map(int, assignment["pools"]["RepresentationValidation"]))
    if len(centers) != 24:
        raise AssertionError("frozen Validation center count changed")
    for name, expected in gpu.PAUSED_OUTPUT_HASHES.items():
        if name in ("paired_a1_vs_a0.csv", "paired_bootstrap_samples.csv"):
            continue  # The failed GPU finalizer rewrote these from its valid main checkpoint.
        if gpu._file_hash(frozen.RESULTS / name) != expected:
            raise AssertionError(f"paused intermediate hash mismatch: {name}")
    frame, _, _ = frozen.load_pool("validation", centers)
    predicted, _ = frozen.attach_predictions(frame, "validation", assignment)
    persisted_predicted = pd.read_csv(frozen.RESULTS / "validation_predictions.csv")
    if (len(predicted) != len(persisted_predicted)
            or not np.array_equal(predicted.center_id.to_numpy(), persisted_predicted.center_id.to_numpy())
            or np.max(np.abs(predicted[gpu.PREDICTION_COLUMNS[1:]].to_numpy(float)
                              - persisted_predicted[gpu.PREDICTION_COLUMNS[1:]].to_numpy(float))) > 1e-12):
        raise AssertionError("fresh Validation predictions differ from frozen persisted predictions")
    main = cpu_samples(predicted, centers, gpu.RESAMPLES)
    main_saved = _read_checkpoint(gpu.CHECKPOINTS / "main.json",
                                  gpu.CHECKPOINTS / "main.sha256",
                                  "p7.4b-gpu-bootstrap-checkpoint-v1",
                                  predicted, centers, gpu.RESAMPLES)
    persisted = pd.read_csv(frozen.RESULTS / "paired_bootstrap_samples.csv")
    if list(persisted.columns) != list(main_saved.columns) or len(persisted) != gpu.RESAMPLES:
        raise AssertionError("post-GPU paired sample CSV schema mismatch")
    persisted_error = float(np.max(np.abs(persisted[COLUMNS].to_numpy() - main_saved[COLUMNS].to_numpy())))
    if not np.array_equal(persisted.replicate.to_numpy(), np.arange(gpu.RESAMPLES)) or persisted_error > 1e-12:
        raise AssertionError("post-GPU paired sample CSV differs from main checkpoint")
    pair = pd.read_csv(frozen.RESULTS / "paired_a1_vs_a0.csv")
    point = frozen.paired_stats(predicted)
    intervals = gpu._intervals(main_saved)
    if len(pair) != 1 or int(pair.iloc[0].bootstrap_resamples) != gpu.RESAMPLES or int(pair.iloc[0].bootstrap_seed) != gpu.SEED:
        raise AssertionError("post-GPU paired summary metadata mismatch")
    expected_pair = {
        **point,
        "Delta_macro_Spearman_CI_low": intervals[COLUMNS[0]][0],
        "Delta_macro_Spearman_CI_high": intervals[COLUMNS[0]][1],
        "Delta_balanced_admission_accuracy_CI_low": intervals[COLUMNS[1]][0],
        "Delta_balanced_admission_accuracy_CI_high": intervals[COLUMNS[1]][1],
    }
    for name, expected in expected_pair.items():
        if not np.isfinite(pair.iloc[0][name]) or abs(float(pair.iloc[0][name]) - expected) > 1e-12:
            raise AssertionError(f"post-GPU paired summary mismatch: {name}")
    maximum = float(np.max(np.abs(main[COLUMNS].to_numpy() - main_saved[COLUMNS].to_numpy())))
    if not np.isfinite(maximum) or maximum > 1e-12:
        raise AssertionError(f"vectorized CPU/GPU main mismatch: {maximum}")
    completed = 0
    missing = []
    for omitted in centers:
        remaining = [c for c in centers if c != omitted]
        subset = predicted[predicted.center_id != omitted]
        name = gpu._checkpoint_name(remaining, centers)
        old = gpu.CHECKPOINTS / f"{name}.json"
        old_receipt = gpu.CHECKPOINTS / f"{name}.sha256"
        if old.exists() or old_receipt.exists():
            saved = _read_checkpoint(old, old_receipt, "p7.4b-gpu-bootstrap-checkpoint-v1",
                                     subset, remaining, gpu.RESAMPLES)
            candidate = cpu_samples(subset, remaining, gpu.RESAMPLES)
            error = float(np.max(np.abs(saved[COLUMNS].to_numpy() - candidate[COLUMNS].to_numpy())))
            if not np.isfinite(error) or error > 1e-12:
                raise AssertionError(f"CPU/GPU completed checkpoint mismatch: {name}: {error}")
            completed += 1
        else:
            missing.append(omitted)
    if completed != 17 or len(missing) != 7:
        raise AssertionError(f"unexpected recovery boundary: {completed} complete, {len(missing)} missing")
    for omitted in missing:
        remaining = [c for c in centers if c != omitted]
        subset = predicted[predicted.center_id != omitted]
        _, serial = frozen.bootstrap(subset, remaining, resamples=8)
        fast = cpu_samples(subset, remaining, resamples=8)
        error = float(np.max(np.abs(serial[COLUMNS].to_numpy() - fast[COLUMNS].to_numpy())))
        if not np.isfinite(error) or error > 1e-12:
            raise AssertionError(f"original CPU / vectorized LOO mismatch: {omitted}: {error}")
    print(f"CPU_RECOVERY_EQUIVALENCE_PASS main_max_abs_error={maximum:.3g} "
          f"reused_gpu_loo={completed} missing_cpu_loo={len(missing)}", flush=True)
    return centers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "run"))
    args = parser.parse_args()
    process = psutil.Process()
    process.cpu_affinity([0])
    process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    print("CPU_RECOVERY_LIMIT affinity=logical_cpu_0 priority=BELOW_NORMAL", flush=True)
    centers = verify()
    if args.command == "verify":
        return
    if frozen.FINAL_AUDIT.exists() or (frozen.RESULTS / "leave_one_center_out.csv").exists():
        raise AssertionError("final output already exists; refusing to overwrite")
    frozen.bootstrap = lambda frame, selected, resamples=gpu.RESAMPLES: _checkpointed(
        frame, list(map(int, selected)), centers, resamples)
    frozen.finalize()


if __name__ == "__main__":
    main()
