"""P7.6B staged Fit freeze, Validation opening, and frozen verdict.

This module is never called by P7.6B-0 preflight or benchmark. It adapts the
unchanged P7.4B numerical helpers to new artifact paths and bootstrap seed.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from core.common import sha256_file
from scripts import run_p7_4b as p7b
from scripts import run_p7_6b as runner
from scripts.run_p6 import fit_mlp, predict_mlp

ROOT = runner.ROOT
RESULTS = runner.RESULTS


def _csv(path: Path, frame: pd.DataFrame) -> None:
    runner.atomic_bytes(path, frame.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode())


def _sha(path: Path) -> None:
    runner.atomic_bytes(path.with_suffix(".sha256"), (sha256_file(path) + "\n").encode())


def _commit(paths: list[Path], message: str) -> str:
    rels = [p.relative_to(ROOT).as_posix() for p in paths]
    subprocess.check_call(["git", "add", "--", *rels], cwd=ROOT)
    subprocess.check_call(["git", "commit", "-m", message, "--", *rels], cwd=ROOT)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _pool(phase: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    assignment, _ = runner.preflight(phase=phase, require_opening=(phase == "validation"))
    tasks = runner.canonical_tasks(assignment, phase)
    runtime_sha = sha256_file(runner.EXECUTION_CONFIG)
    frames, scale_frames, hashes = [], [], {}
    for task in tasks:
        if not runner.validate_receipt(phase, task, runtime_sha):
            raise RuntimeError(f"incomplete {phase} trajectory: {task.key}")
        csv, scales, receipt, _ = runner.output_paths(phase, task)
        frame = pd.read_csv(csv)
        scale = pd.read_csv(scales)
        if len(frame) != 24 or not frame.behavior_path_match.astype(str).str.lower().eq("true").all():
            raise RuntimeError(f"behavior-path failure: {task.key}")
        for lhs, rhs in (("A0_parent_identity", "A1_parent_identity"),
                         ("A0_parent_state_hash", "A1_parent_state_hash"),
                         ("A0_action", "A1_action"),
                         ("A0_RI", "A1_RI"),
                         ("A0_post_action_identity", "A1_post_action_identity"),
                         ("A0_post_action_path_hash", "A1_post_action_path_hash")):
            if not frame[lhs].astype(str).equals(frame[rhs].astype(str)):
                raise RuntimeError(f"stagewise A0/A1 mismatch: {task.key} {lhs}")
        frames.append(frame)
        scale_frames.append(scale)
        for path in (csv, scales, receipt):
            hashes[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    data, scales = pd.concat(frames, ignore_index=True), pd.concat(scale_frames, ignore_index=True)
    if not np.isfinite(scales.S_m.to_numpy(float)).all() or not (scales.valid_point_error_count == 104).all():
        raise RuntimeError("reference scale nonfinite or incorrect point count")
    if float(scales.floor_activated.mean()) > 0.01:
        raise RuntimeError(f"{phase} scale floor rate >1%")
    assert len(data) == 432 * 24
    assert data.center_id.nunique() == 36
    return data, scales, hashes


def _fit_absolute(metrics: pd.DataFrame) -> dict:
    dummy_pair = {"Delta_macro_Spearman": 1.0, "Delta_balanced_admission_accuracy": 1.0}
    dummy_ci = {"Delta_macro_Spearman": [1.0, 1.0],
                "Delta_balanced_admission_accuracy": [1.0, 1.0]}
    return {k: v for k, v in p7b.condition_set(metrics, dummy_pair, dummy_ci).items() if k.startswith("A1_")}


def fit_freeze() -> None:
    assignment, protocol = runner.preflight(phase="fit")
    data, scales, raw_hashes = _pool("fit")
    predicted, fold_scalers = p7b.attach_predictions(data, "fit", assignment)
    metrics, by_center, by_scenario, by_stratum = p7b.metric_tables(predicted, "fit")
    paths = []
    for name, frame in (("fit_oof_predictions.csv", predicted), ("fit_metrics.csv", metrics),
                        ("fit_metrics_by_center.csv", by_center),
                        ("fit_metrics_by_scenario.csv", by_scenario),
                        ("fit_metrics_by_stratum.csv", by_stratum),
                        ("fit_reference_scale_audit.csv", scales)):
        path = RESULTS / name
        _csv(path, frame); paths.append(path)
    fold_path = RESULTS / "fit_fold_scalers.json"
    runner.atomic_json(fold_path, fold_scalers); paths.append(fold_path)
    checks = _fit_absolute(metrics)
    if not all(checks.values()):
        stop = ROOT / "audits/P7_6B_FIT_SCIENTIFIC_STOP.json"
        runner.atomic_json(stop, {"status": "P7_6B_FIT_ABSOLUTE_FAIL_STOP", "checks": checks,
                                  "validation_accessed": False,
                                  "files": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths}})
        _sha(stop)
        _commit(paths + [stop, stop.with_suffix(".sha256")], "Record P7.6B Fit scientific stop before Validation")
        raise RuntimeError("Fit absolute condition failed; Validation must remain closed")
    centers = list(map(int, assignment["pools"]["ReplicationFit"]))
    for rep in ("A0", "A1"):
        features, target, multiplier = p7b.representation_spec(rep)
        scaler = p7b.scaler_fit(data[features].to_numpy(float))
        scaler.update({"schema": "p7.6b-standard-scaler-v1", "representation": rep,
                       "feature_order": features, "ddof": 0, "fit_centers": centers})
        scaler_path = ROOT / f"artifacts/p7_6b_{rep}_scaler.json"
        runner.atomic_json(scaler_path, scaler); paths.append(scaler_path)
        model = fit_mlp(p7b.scaler_apply(data[features].to_numpy(float), scaler),
                        data[target].to_numpy(float), p7b.train_config(multiplier), 19631)
        blob = io.BytesIO()
        torch.save({"schema": "p7.6b-estimator-v1", "representation": rep,
                    "feature_order": features, "target_multiplier": multiplier,
                    "training_seed": 19631, "state_dict": model.state_dict()}, blob)
        model_path = ROOT / f"artifacts/p7_6b_{rep}_estimator.pt"
        runner.atomic_bytes(model_path, blob.getvalue()); paths.append(model_path)
    bound = [runner.ASSIGNMENT, runner.PROTOCOL, runner.EXECUTION_CONFIG,
             ROOT / "scripts/run_p7_6b.py", ROOT / "scripts/p7_6b_science.py",
             ROOT / "core/p7_6b_selected_data.py", ROOT / "scripts/run_p7_4b.py",
             ROOT / "scripts/run_p6.py"]
    files = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths + bound}
    files.update(raw_hashes)
    manifest = {"schema": "p7.6b-fit-freeze-v1", "status": "FIT_FROZEN",
                "fit_centers": centers, "fit_absolute_checks": checks,
                "stage_pairing_audit_passed": True, "scale_audit_passed": True,
                "validation_accessed": False, "heldout_accessed": False,
                "alibaba_accessed": False, "P8_executed": False, "files": files}
    runner.atomic_json(runner.FIT_FREEZE, manifest); _sha(runner.FIT_FREEZE)
    paths += [runner.FIT_FREEZE, runner.FIT_FREEZE.with_suffix(".sha256")]
    _commit(paths, "Freeze P7.6B ReplicationFit before Validation")


def open_validation() -> None:
    if not runner.FIT_FREEZE.exists() or not runner.git_bound(runner.FIT_FREEZE):
        raise RuntimeError("Fit freeze not committed")
    freeze = runner.read_json(runner.FIT_FREEZE)
    if freeze.get("status") != "FIT_FROZEN" or not all(freeze.get("fit_absolute_checks", {}).values()):
        raise RuntimeError("Fit scientific gate did not pass")
    for rel, expected in freeze["files"].items():
        runner.assert_digest(ROOT / rel, expected, bound=not rel.startswith("results/p7_6b/raw/"))
    if runner.VALIDATION_OPENING.exists():
        raise RuntimeError("Validation opening is one-time and already exists")
    required = ("artifacts/p7_6b_A0_scaler.json", "artifacts/p7_6b_A1_scaler.json",
                "artifacts/p7_6b_A0_estimator.pt", "artifacts/p7_6b_A1_estimator.pt",
                "results/p7_6b/fit_oof_predictions.csv", "results/p7_6b/fit_metrics.csv",
                "scripts/run_p7_6b.py", "configs/P7_6B_FROZEN_PROTOCOL.json",
                "configs/P7_6B_EXECUTION_CONFIG.json")
    opening = {"schema": "p7.6b-validation-opening-v1", "validation_open_authorized": True,
               "fit_freeze_sha256": sha256_file(runner.FIT_FREEZE),
               "files": {rel: freeze["files"][rel] for rel in required},
               "no_refit_or_reselection_after_opening": True,
               "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False}
    runner.atomic_json(runner.VALIDATION_OPENING, opening); _sha(runner.VALIDATION_OPENING)
    _commit([runner.VALIDATION_OPENING, runner.VALIDATION_OPENING.with_suffix(".sha256")],
            "Commit one-time P7.6B ReplicationValidation opening")


def _predict_validation(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for rep in ("A0", "A1"):
        features, _, multiplier = p7b.representation_spec(rep)
        scaler = runner.read_json(ROOT / f"artifacts/p7_6b_{rep}_scaler.json")
        payload = torch.load(ROOT / f"artifacts/p7_6b_{rep}_estimator.pt",
                             weights_only=True, map_location="cpu")
        model = p7b.p7core.FrozenMLP()
        model.load_state_dict(payload["state_dict"])
        model.eval()
        out[f"{rep}_prediction"] = predict_mlp(model,
            p7b.scaler_apply(out[features].to_numpy(float), scaler), multiplier)
    return out


def _bootstrap(frame: pd.DataFrame, centers: list[int], resamples: int = 4000):
    rng = np.random.default_rng(7601)
    grouped = {c: frame[frame.center_id == c] for c in centers}
    values = []
    for index in range(resamples):
        sampled = rng.choice(centers, len(centers), replace=True)
        parts = []
        for occurrence, center in enumerate(sampled):
            part = grouped[int(center)].copy()
            part["center_id"] = occurrence
            parts.append(part)
        stat = p7b.paired_stats(pd.concat(parts, ignore_index=True))
        if not all(np.isfinite(list(stat.values()))):
            raise RuntimeError("undefined paired bootstrap replicate")
        values.append({"replicate": index, **stat})
    samples = pd.DataFrame(values)
    intervals = {key: [float(np.quantile(samples[key], .025, method="linear")),
                       float(np.quantile(samples[key], .975, method="linear"))]
                 for key in ("Delta_macro_Spearman", "Delta_balanced_admission_accuracy")}
    return intervals, samples


def finalize() -> None:
    runner.preflight(phase="validation", require_opening=True)
    assignment = runner.read_json(runner.ASSIGNMENT)
    centers = list(map(int, assignment["pools"]["ReplicationValidation"]))
    data, scales, raw_hashes = _pool("validation")
    predicted = _predict_validation(data)
    metrics, by_center, by_scenario, by_stratum = p7b.metric_tables(predicted, "validation")
    point = p7b.paired_stats(predicted)
    intervals, samples = _bootstrap(predicted, centers)
    val_checks = p7b.condition_set(metrics, point, intervals)
    fit_metrics = pd.read_csv(RESULTS / "fit_metrics.csv")
    fit_checks = _fit_absolute(fit_metrics)
    def metric(table, rep, name):
        return float(table[(table.representation == rep) & (table.subgroup == "all")].iloc[0][name])
    deterioration = {name: {rep: metric(fit_metrics, rep, name) - metric(metrics, rep, name)
                            for rep in ("A0", "A1")}
                     for name in ("macro_center_Spearman", "balanced_admission_accuracy")}
    deterioration_stop = all(deterioration[k]["A1"] > deterioration[k]["A0"] for k in deterioration)
    loo_rows = []
    for omitted in centers:
        subset = predicted[predicted.center_id != omitted]
        subset_metrics, _, _, _ = p7b.metric_tables(subset, "validation_LOO")
        pair = p7b.paired_stats(subset)
        ci, _ = _bootstrap(subset, [c for c in centers if c != omitted])
        checks = p7b.condition_set(subset_metrics, pair, ci)
        loo_rows.append({"omitted_center": omitted, **pair,
                         "Delta_macro_Spearman_CI_low": ci["Delta_macro_Spearman"][0],
                         "Delta_macro_Spearman_CI_high": ci["Delta_macro_Spearman"][1],
                         "Delta_balanced_admission_accuracy_CI_low": ci["Delta_balanced_admission_accuracy"][0],
                         "Delta_balanced_admission_accuracy_CI_high": ci["Delta_balanced_admission_accuracy"][1],
                         **checks, "all_conditions_pass": all(checks.values())})
    loo = pd.DataFrame(loo_rows)
    passed = (all(fit_checks.values()) and all(val_checks.values()) and not deterioration_stop
              and bool(loo.all_conditions_pass.all()))
    verdict = "P7_6B_REPLICATION_PASS" if passed else "P7_6B_REPLICATION_FAIL"
    paths = []
    for name, frame in (("validation_predictions.csv", predicted), ("validation_metrics.csv", metrics),
                        ("validation_metrics_by_center.csv", by_center),
                        ("validation_metrics_by_scenario.csv", by_scenario),
                        ("validation_metrics_by_stratum.csv", by_stratum),
                        ("validation_reference_scale_audit.csv", scales),
                        ("paired_bootstrap_samples.csv", samples),
                        ("leave_one_center_out.csv", loo)):
        path = RESULTS / name; _csv(path, frame); paths.append(path)
    paired_path = RESULTS / "paired_a1_vs_a0.csv"
    _csv(paired_path, pd.DataFrame([{**point,
        "Delta_macro_Spearman_CI_low": intervals["Delta_macro_Spearman"][0],
        "Delta_macro_Spearman_CI_high": intervals["Delta_macro_Spearman"][1],
        "Delta_balanced_admission_accuracy_CI_low": intervals["Delta_balanced_admission_accuracy"][0],
        "Delta_balanced_admission_accuracy_CI_high": intervals["Delta_balanced_admission_accuracy"][1],
        "bootstrap_resamples": 4000, "bootstrap_seed": 7601}]))
    paths.append(paired_path)
    report = ROOT / "reports/P7_6B_DESIGN_BASED_REPLICATION.md"
    runner.atomic_bytes(report, ("# P7.6B design-based replication\n\n"
        f"Formal verdict: **{verdict}**\n\n"
        f"Fit checks: `{json.dumps(fit_checks, sort_keys=True)}`\n\n"
        f"Validation checks: `{json.dumps(val_checks, sort_keys=True)}`\n\n"
        f"Paired effects: `{json.dumps(point, sort_keys=True)}`\n\n"
        f"Paired intervals: `{json.dumps(intervals, sort_keys=True)}`\n\n"
        f"LOO passes: {int(loo.all_conditions_pass.sum())}/36. "
        f"Transport deterioration stop: {deterioration_stop}.\n\n"
        "No final heldout, Alibaba, or P8 access. Stops for human scientific review.\n").encode())
    paths.append(report)
    audit = ROOT / "audits/P7_6B_FINAL_SCIENTIFIC_AUDIT.json"
    files = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths}
    files.update(raw_hashes)
    runner.atomic_json(audit, {"schema": "p7.6b-final-scientific-audit-v1", "verdict": verdict,
        "fit_absolute_checks": fit_checks, "validation_checks": val_checks,
        "paired_point_estimates": point, "paired_intervals": intervals,
        "transport_deterioration": deterioration, "transport_deterioration_stop": deterioration_stop,
        "leave_one_center_all_pass": bool(loo.all_conditions_pass.all()),
        "stage_pairing_audits_passed": True, "scale_audits_passed": True,
        "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
        "terminal_state": "STOP_FOR_HUMAN_SCIENTIFIC_REVIEW", "files": files})
    _sha(audit)
    _commit(paths + [audit, audit.with_suffix(".sha256")], f"Complete P7.6B replication: {verdict}")
    print(verdict, flush=True)
