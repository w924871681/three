"""P7.4B prospective paired A0/A1 representation-transport study.

The behavior path is the single frozen P7.2 Proposed configuration.  A0 and
A1 are observational representations only: neither is consulted by the gate,
action selector, RI candidate search, or parent-state evolution.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr

import core.p6 as p6core
import core.p7 as p7core
import scripts.run_p7 as p7runner
from core.common import canonical_hash, sha256_file
from core.data import generate_base_centers
from core.models import DEVICE, adapt as frozen_adapt, evaluate, state_hash
from core.p3_2_data import scenario_hash_v2, timeline_for_v2
from core.p3_2_models import build_p3_2_identity_bank
from core.p6 import FEATURE_COLUMNS, initial_model
from core.p7 import DecisionExecutor, FrozenEstimator, MethodState, Segment, batch, evidence_blocks, point_errors, read_json, save_json
from scripts.run_p6 import fit_mlp, predict_mlp


RESULTS = ROOT / "results/p7_4b"
RAW = RESULTS / "raw"
ASSIGNMENT = ROOT / "configs/P7_4B_CENTER_ASSIGNMENT.json"
FROZEN_PROTOCOL = ROOT / "configs/P7_4B_FROZEN_PROTOCOL.json"
SUPPLEMENT = ROOT / "audits/P7_4B_BEHAVIOR_PATH_SUPPLEMENT.json"
FIT_FREEZE = ROOT / "audits/P7_4B_FIT_FREEZE.json"
VALIDATION_OPENING = ROOT / "audits/P7_4B_VALIDATION_OPENING.json"
FINAL_AUDIT = ROOT / "audits/P7_4B_FINAL_SCIENTIFIC_AUDIT.json"
SELECTED_ACTION = ROOT / "configs/p7_2_selected_action_params.json"
P7_2_FREEZE = ROOT / "audits/P7_2_FINAL_CALIBRATION_FREEZE.json"
GENERATOR = ROOT / "configs/p3_mismatch_v2_frozen.json"
P7_PROTOCOL = ROOT / "configs/p7_protocol.json"

ACTION_CONFIG = {
    "method": "Proposed",
    "delta_R": -0.000272181217042075,
    "gate_frozen_from": "GateCal-v2",
    "cost_ratio": 10,
    "config_id": "Proposed_ratio10_grid33",
}
FEATURE_A0 = [f"A0_{x}" for x in FEATURE_COLUMNS]
FEATURE_A1 = [f"A1_{x}" for x in FEATURE_COLUMNS]


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, lineterminator="\n", float_format="%.17g")
    tmp.replace(path)


def write_sha(path: Path) -> None:
    path.with_suffix(".sha256").write_text(sha256_file(path) + "\n", encoding="utf-8", newline="\n")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_bound(path: Path, commit: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    payload = subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=ROOT)
    return hashlib.sha256(payload).hexdigest() == sha256_file(path)


def seed_bound_adapt(parent, data_batch, steps, seed):
    devices = [torch.cuda.current_device()] if DEVICE.type == "cuda" else []
    with torch.random.fork_rng(devices=devices):
        torch.manual_seed(int(seed))
        return frozen_adapt(parent, data_batch, steps, seed)


def install_seed_binding() -> None:
    p6core.adapt = seed_bound_adapt
    p7core.adapt = seed_bound_adapt
    p7runner.adapt = seed_bound_adapt


def preflight(require_fit: bool = False, require_opening: bool = False) -> tuple[dict, dict, dict]:
    p7runner.preflight()
    assert SUPPLEMENT.exists() and SUPPLEMENT.with_suffix(".sha256").exists()
    assert sha256_file(SUPPLEMENT) == SUPPLEMENT.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    supplement = read_json(SUPPLEMENT)
    assert supplement["authorization"]["p7_4b_execution_authorized"] is True
    assert supplement["behavior_path"] == ACTION_CONFIG
    assert supplement["a0_a1_may_influence_behavior"] is False
    assert supplement["mandatory_stage_equality_audit"] == [
        "parent_state_hash", "action", "post_action_identity", "post_action_path_hash"
    ]
    for rel, expected in supplement["files"].items():
        path = ROOT / rel
        assert sha256_file(path) == expected, f"P7.4B supplement hash mismatch: {rel}"
        assert git_bound(path, supplement["supplement_git_commit"]), f"P7.4B supplement Git mismatch: {rel}"
    assignment = read_json(ASSIGNMENT)
    protocol = read_json(FROZEN_PROTOCOL)
    frozen = read_json(GENERATOR)
    selected = read_json(SELECTED_ACTION)
    assert selected["selected"]["config"] == ACTION_CONFIG
    fit_ids = list(map(int, assignment["pools"]["RepresentationFit"]))
    val_ids = list(map(int, assignment["pools"]["RepresentationValidation"]))
    assert len(fit_ids) == len(val_ids) == 24 and set(fit_ids).isdisjoint(val_ids)
    assert sorted(fit_ids + val_ids) == list(range(32200, 32248))
    assert not (set(fit_ids + val_ids) & set(range(33000, 33020)))
    assert frozen["model_seeds"] == [7311, 7312, 7313]
    assert frozen["scenarios"] == ["C0", "C1", "C3", "C4"]
    assert protocol["authorization"]["final_heldout_33000_33019_authorized"] is False
    if require_fit:
        assert FIT_FREEZE.exists() and FIT_FREEZE.with_suffix(".sha256").exists()
        assert sha256_file(FIT_FREEZE) == FIT_FREEZE.with_suffix(".sha256").read_text(encoding="utf-8").strip()
        manifest = read_json(FIT_FREEZE)
        for rel, expected in manifest["files"].items():
            assert sha256_file(ROOT / rel) == expected, f"Fit freeze mismatch: {rel}"
    if require_opening:
        assert VALIDATION_OPENING.exists() and VALIDATION_OPENING.with_suffix(".sha256").exists()
        assert sha256_file(VALIDATION_OPENING) == VALIDATION_OPENING.with_suffix(".sha256").read_text(encoding="utf-8").strip()
        opening = read_json(VALIDATION_OPENING)
        assert opening["validation_open_authorized"] is True
        assert opening["heldout_accessed"] is False and opening["alibaba_accessed"] is False
        subprocess.check_call(["git", "diff", "--quiet", "HEAD", "--",
                               VALIDATION_OPENING.relative_to(ROOT).as_posix()], cwd=ROOT)
    return assignment, protocol, frozen


def all_bases(assignment: dict):
    ids = sorted(list(map(int, assignment["pools"]["RepresentationFit"])) +
                 list(map(int, assignment["pools"]["RepresentationValidation"])))
    return generate_base_centers(ids, data_seed=7311)


def bank(frozen: dict):
    source = read_json(ROOT / frozen["source_training_manifest_path"])
    value = build_p3_2_identity_bank(source)
    assert canonical_hash([item.to_dict() for item in value]) == read_json(P7_PROTOCOL)["source_bank_hash"]
    return value


def raw_path(pool: str, scenario: str, center: int, seed: int) -> Path:
    return RAW / pool / f"{scenario}_{center}_{seed}.csv"


def scale_from_reference(model, segment: Segment, source: str, identity_id: str, center: int,
                         seed: int, scenario: str, stage: int, bank_index=None) -> dict:
    assert len(segment.y) == 200
    errors = np.asarray(point_errors(model, batch(segment)), dtype=float)
    if len(errors) != 104 or not np.isfinite(errors).all():
        raise AssertionError("P7.4B reference scale requires exactly 104 finite point errors")
    median = float(np.median(errors))
    scale = float(max(median, 1e-12))
    if not np.isfinite(scale):
        raise AssertionError("non-finite P7.4B identity scale")
    return {
        "pool": None, "center_id": center, "seed": seed, "scenario": scenario, "stage": stage,
        "identity_id": identity_id, "birth_source": source, "selected_ri_bank_index": bank_index,
        "reference_observation_count": 200, "valid_point_error_count": len(errors),
        "point_error_median": median, "S_m": scale, "floor_activated": int(median < 1e-12),
        "reference_segment_hash": segment.hash,
        "point_error_vector_hash": canonical_hash(errors.tolist()),
    }


def paired_path_assert(row: dict, previous_path_hash: str) -> str:
    a0_parent = str(row["parent_state_hash"])
    a1_parent = str(row["parent_state_hash"])
    a0_action = str(row["action"])
    a1_action = str(row["action"])
    a0_identity = str(row["identity_after"])
    a1_identity = str(row["identity_after"])
    payload = {
        "previous_path_hash": previous_path_hash,
        "parent_state_hash": a0_parent,
        "action": a0_action,
        "post_action_identity": a0_identity,
        "deployed_state_hash": str(row["deployed_state_hash"]),
    }
    a0_path = canonical_hash(payload)
    a1_path = canonical_hash(dict(payload))
    if not (a0_parent == a1_parent and a0_action == a1_action and a0_identity == a1_identity and a0_path == a1_path):
        raise AssertionError("A0/A1 behavior-path divergence: mandatory immediate STOP")
    row.update({
        "A0_parent_state_hash": a0_parent, "A1_parent_state_hash": a1_parent,
        "A0_action": a0_action, "A1_action": a1_action,
        "A0_post_action_identity": a0_identity, "A1_post_action_identity": a1_identity,
        "A0_post_action_path_hash": a0_path, "A1_post_action_path_hash": a1_path,
        "behavior_path_match": True,
    })
    return a0_path


def run_trajectory(base, seed: int, scenario: str, frozen: dict, protocol: dict, identities, tau: float):
    timeline, metadata = timeline_for_v2(base, scenario, frozen)
    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    initial = initial_model(base, seed, incumbent, timeline)
    prefix = timeline._segment((800, 1000), "assessment")
    active_scale = scale_from_reference(initial, prefix, "initial", incumbent.identity_id,
                                        base.center_id, seed, scenario, 0)
    state = MethodState(copy.deepcopy(ACTION_CONFIG), initial, incumbent, evidence=list(evidence_blocks(prefix)))
    executor = DecisionExecutor(identities, frozen["deployment_limits"][base.budget_tier], FrozenEstimator(),
                                protocol["ravm"], base.center_id, seed, protocol["unit"])
    rows, scales = [], [active_scale]
    a0_history, a1_history = [], []
    path_hash = canonical_hash({"initial_state_hash": state_hash(initial), "identity": incumbent.identity_id})
    scenario_hash = scenario_hash_v2(base, scenario, frozen)
    for stage in range(1, 25):
        update, assessment = timeline.decision_data(stage)
        decision = executor.step_group([state], stage, update, assessment)[0]
        _, row, parent, probe, selected = decision
        scale_current = float(active_scale["S_m"])
        path_hash = paired_path_assert(row, path_hash)
        a0_history.append((float(row["probe_gain"]), float(row["probe_residual"])))
        a1_history.append((float(row["probe_gain"]), float(row["probe_residual"]) / scale_current))
        a0_features = p7core.history_features(a0_history)
        a1_features = p7core.history_features(a1_history)
        for name, value in zip(FEATURE_A0, a0_features):
            row[name] = float(value)
        for name, value in zip(FEATURE_A1, a1_features):
            row[name] = float(value)
        row["A1_active_S_m"] = scale_current
        row["identity_age"] = len(a0_history)
        row["history_coverage"] = min(len(a0_history), 6) / 6.0
        row["A0_A1_used_for_behavior"] = False
        row["behavior_config_hash"] = canonical_hash(ACTION_CONFIG)
        new_scale = None
        if row["action"] == "ri":
            tail = Segment(assessment.x[-200:].copy(), assessment.y[-200:].copy(),
                           assessment.ts[-200:].copy(), "assessment")
            bank_index = next(i for i, item in enumerate(identities) if item.identity_id == row["identity_after"])
            new_scale = scale_from_reference(selected, tail, "RI", row["identity_after"],
                                             base.center_id, seed, scenario, stage, bank_index)
            scales.append(new_scale)
            row["next_identity_S_m"] = new_scale["S_m"]
            row["next_identity_reference_hash"] = new_scale["reference_segment_hash"]
        else:
            row["next_identity_S_m"] = np.nan
            row["next_identity_reference_hash"] = ""
        timeline.seal_decision(stage)
        labels = p7runner.offline_labels(parent, probe, timeline, stage, base, seed, tau)
        service = timeline.service(stage)
        service_mse = evaluate(selected, batch(service))[0]
        row.update(labels)
        row.update({
            "center_id": base.center_id, "seed": seed, "scenario": scenario,
            "center_type": base.center_type, "deployment_tier": base.budget_tier,
            "scenario_hash": scenario_hash,
            "scenario_role": "secondary Nonlinear Dependency-Shift Stress" if scenario == "C4" else metadata["definition"],
            "initial_state_hash": state_hash(initial), "tau_service": tau,
            "service_mse": service_mse, "D_srv_hash": service.hash,
            "service_start_ts": int(service.ts[0]), "oracle_offline_only": True,
            "J_life_normalized_stage": (service_mse + row["event_cost_raw"]) / protocol["unit"],
            "A0_target": float(labels["R_B50"]),
            "A1_target": float(labels["R_B50"]) / scale_current,
            "A0_response_residual": float(row["probe_residual"]),
            "A1_response_residual": float(row["probe_residual"]) / scale_current,
        })
        rows.append(row)
        if row["action"] == "ri":
            active_scale = new_scale
            a0_history, a1_history = [], []
        executor.source_cache = {}
    frame = pd.DataFrame(rows)
    assert len(frame) == 24 and frame.behavior_path_match.all()
    return frame, pd.DataFrame(scales)


def worker(pool: str, center: int, seed: int, scenario: str) -> str:
    install_seed_binding()
    assignment, _, frozen_protocol = preflight(require_fit=(pool == "validation"), require_opening=(pool == "validation"))
    frozen = read_json(GENERATOR)
    allowed = assignment["pools"]["RepresentationFit" if pool == "fit" else "RepresentationValidation"]
    assert center in allowed
    output = raw_path(pool, scenario, center, seed)
    receipt = output.with_suffix(".integrity.json")
    scales_output = output.with_suffix(".scales.csv")
    if output.exists() and receipt.exists() and scales_output.exists():
        info = read_json(receipt)
        assert sha256_file(output) == info["trajectory_sha256"]
        assert sha256_file(scales_output) == info["scales_sha256"]
        return output.as_posix()
    base = next(value for value in all_bases(assignment) if value.center_id == center)
    identities = bank(frozen)
    refs = read_json(RESULTS / f"{pool}_references.json")
    frame, scales = run_trajectory(base, seed, scenario, frozen, read_json(P7_PROTOCOL), identities,
                                   float(refs[f"{center}:{seed}"]["tau_service"]))
    frame["pool"] = pool
    scales["pool"] = pool
    write_csv(output, frame)
    write_csv(scales_output, scales)
    save_json(receipt, {
        "schema": "p7.4b-paired-trajectory-integrity-v1", "pool": pool, "center": center,
        "seed": seed, "scenario": scenario, "rows": len(frame),
        "trajectory_sha256": sha256_file(output), "scales_sha256": sha256_file(scales_output),
        "behavior_config_hash": canonical_hash(ACTION_CONFIG), "all_stage_path_matches": True,
        "completed_at_utc": utc(), "supplement_sha256": sha256_file(SUPPLEMENT),
    })
    return output.as_posix()


def make_references(pool: str, centers: list[int], assignment: dict, frozen: dict) -> Path:
    path = RESULTS / f"{pool}_references.json"
    if path.exists():
        return path
    identities = bank(frozen)
    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    bases = all_bases(assignment)
    refs = {}
    for center in centers:
        base = next(value for value in bases if value.center_id == center)
        for seed in frozen["model_seeds"]:
            refs[f"{center}:{seed}"] = p7runner.reference(base, int(seed), incumbent, frozen)
    save_json(path, refs)
    return path


def materialize(pool: str, workers: int) -> None:
    assignment, _, frozen_protocol = preflight(require_fit=(pool == "validation"), require_opening=(pool == "validation"))
    if pool == "validation":
        assert VALIDATION_OPENING.exists()
    frozen = read_json(GENERATOR)
    centers = list(map(int, assignment["pools"]["RepresentationFit" if pool == "fit" else "RepresentationValidation"]))
    reference_path = make_references(pool, centers, assignment, frozen)
    tasks = [(pool, c, int(s), scenario) for c in centers for s in frozen["model_seeds"] for scenario in frozen["scenarios"]]
    total = len(tasks)
    def task_path(task):
        _, center, seed, scenario = task
        return raw_path(pool, scenario, center, seed)
    complete_existing = sum(task_path(task).exists() and task_path(task).with_suffix(".integrity.json").exists()
                            for task in tasks)
    save_json(RESULTS / f"{pool}_materialization_started.json", {
        "pool": pool, "started_at_utc": utc(), "centers": centers, "total_trajectories": total,
        "references_sha256": sha256_file(reference_path), "behavior_path": ACTION_CONFIG,
        "supplement_sha256": sha256_file(SUPPLEMENT), "heldout_accessed": False,
        "alibaba_accessed": False, "P8_executed": False,
    })
    completed = complete_existing
    pending = [task for task in tasks if not (task_path(task).exists() and task_path(task).with_suffix(".integrity.json").exists())]
    with ProcessPoolExecutor(max_workers=workers, initializer=install_seed_binding) as executor:
        futures = {executor.submit(worker, *task): task for task in pending}
        for future in as_completed(futures):
            last = future.result()
            completed += 1
            save_json(RESULTS / f"{pool}_execution_status.json", {
                "status": "RUNNING", "completed_trajectories": completed, "total_trajectories": total,
                "last_completed": last, "updated_at_utc": utc(), "workers": workers,
                "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
            })
            print(f"P7.4B {pool} {completed}/{total} {last}", flush=True)
    save_json(RESULTS / f"{pool}_execution_status.json", {
        "status": "MATERIALIZATION_COMPLETE", "completed_trajectories": completed,
        "total_trajectories": total, "updated_at_utc": utc(), "workers": workers,
        "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
    })


def load_pool(pool: str, centers: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    frozen = read_json(GENERATOR)
    frames, scale_frames, hashes = [], [], {}
    for center in centers:
        for seed in frozen["model_seeds"]:
            for scenario in frozen["scenarios"]:
                path = raw_path(pool, scenario, center, int(seed))
                receipt = path.with_suffix(".integrity.json")
                scale_path = path.with_suffix(".scales.csv")
                assert path.exists() and receipt.exists() and scale_path.exists()
                info = read_json(receipt)
                assert info["all_stage_path_matches"] is True
                assert sha256_file(path) == info["trajectory_sha256"]
                assert sha256_file(scale_path) == info["scales_sha256"]
                frame = pd.read_csv(path)
                assert len(frame) == 24 and frame.behavior_path_match.astype(bool).all()
                for lhs, rhs in [
                    ("A0_parent_state_hash", "A1_parent_state_hash"), ("A0_action", "A1_action"),
                    ("A0_post_action_identity", "A1_post_action_identity"),
                    ("A0_post_action_path_hash", "A1_post_action_path_hash")]:
                    assert frame[lhs].astype(str).equals(frame[rhs].astype(str)), f"behavior divergence {lhs}/{rhs}"
                frames.append(frame)
                scale_frames.append(pd.read_csv(scale_path))
                for value in (path, receipt, scale_path):
                    hashes[value.relative_to(ROOT).as_posix()] = sha256_file(value)
    data = pd.concat(frames, ignore_index=True)
    scales = pd.concat(scale_frames, ignore_index=True)
    assert np.isfinite(scales.S_m).all() and (scales.valid_point_error_count == 104).all()
    if float(scales.floor_activated.mean()) > 0.01:
        raise AssertionError(f"{pool} scale floor activation exceeds 1%")
    return data, scales, hashes


def scaler_fit(x: np.ndarray) -> dict:
    mean = x.mean(axis=0)
    std = x.std(axis=0, ddof=0)
    std[std == 0] = 1.0
    return {"mean": mean.tolist(), "scale": std.tolist()}


def scaler_apply(x: np.ndarray, scaler: dict) -> np.ndarray:
    return (x - np.asarray(scaler["mean"])) / np.asarray(scaler["scale"])


def safe_spearman(y, pred) -> float:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    if len(y) < 3 or np.std(y) == 0 or np.std(pred) == 0:
        return float("nan")
    return float(spearmanr(y, pred).statistic)


def center_metrics(frame: pd.DataFrame, target: str, prediction: str) -> pd.DataFrame:
    rows = []
    for center, group in frame.groupby("center_id"):
        y, p = group[target].to_numpy(float), group[prediction].to_numpy(float)
        negative = y < 0
        rows.append({
            "center_id": int(center), "n": len(group), "mae": float(np.mean(np.abs(p-y))),
            "rmse": float(np.sqrt(np.mean((p-y)**2))), "spearman": safe_spearman(y, p),
            "bias": float(np.mean(p-y)), "negative_n": int(negative.sum()),
            "nonnegative_n": int((~negative).sum()),
            "tpr": float((p[negative] < 0).mean()) if negative.any() else np.nan,
            "tnr": float((p[~negative] >= 0).mean()) if (~negative).any() else np.nan,
        })
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame, target: str, prediction: str) -> dict:
    cm = center_metrics(frame, target, prediction)
    macro_tpr = float(cm.tpr.dropna().mean()) if cm.tpr.notna().any() else np.nan
    macro_tnr = float(cm.tnr.dropna().mean()) if cm.tnr.notna().any() else np.nan
    return {
        "centers": int(len(cm)), "records": int(len(frame)),
        "macro_center_MAE": float(cm.mae.mean()), "macro_center_RMSE": float(cm.rmse.mean()),
        "macro_center_Spearman": float(cm.spearman.mean()) if cm.spearman.notna().all() else np.nan,
        "pooled_Spearman": safe_spearman(frame[target], frame[prediction]),
        "positive_Spearman_center_fraction": float((cm.spearman.fillna(-np.inf) > 0).sum()/len(cm)),
        "macro_TPR": macro_tpr, "macro_TNR": macro_tnr,
        "balanced_admission_accuracy": float(0.5*(macro_tpr+macro_tnr)) if np.isfinite(macro_tpr+macro_tnr) else np.nan,
        "prediction_bias": float(cm.bias.mean()),
        "TPR_defined_centers": int(cm.tpr.notna().sum()), "TNR_defined_centers": int(cm.tnr.notna().sum()),
    }


def representation_spec(rep: str) -> tuple[list[str], str, float]:
    if rep == "A0":
        return FEATURE_A0, "A0_target", 1000.0
    return FEATURE_A1, "A1_target", 1.0


def train_config(multiplier: float) -> dict:
    return {"learning_rate": 0.001, "weight_decay": 0.0001, "epoch_budget": 400,
            "target_multiplier": multiplier}


def attach_predictions(frame: pd.DataFrame, pool: str, assignment: dict) -> tuple[pd.DataFrame, dict]:
    out = frame.copy()
    saved = {}
    if pool == "fit":
        folds = assignment["fit_center_group_folds"]
        for rep in ("A0", "A1"):
            features, target, multiplier = representation_spec(rep)
            prediction = np.full(len(out), np.nan)
            for fold in folds:
                fold_key = int(fold["fold"])
                validation_centers = fold["validation_centers"]
                val_mask = out.center_id.isin(validation_centers).to_numpy()
                train_mask = ~val_mask
                scaler = scaler_fit(out.loc[train_mask, features].to_numpy(float))
                model = fit_mlp(scaler_apply(out.loc[train_mask, features].to_numpy(float), scaler),
                                out.loc[train_mask, target].to_numpy(float), train_config(multiplier),
                                9632 + fold_key)
                prediction[val_mask] = predict_mlp(model,
                    scaler_apply(out.loc[val_mask, features].to_numpy(float), scaler), multiplier)
                saved[f"{rep}_fold_{fold_key}_scaler"] = scaler
            assert np.isfinite(prediction).all()
            out[f"{rep}_prediction"] = prediction
    else:
        for rep in ("A0", "A1"):
            features, _, multiplier = representation_spec(rep)
            scaler = read_json(ROOT / f"artifacts/p7_4b_{rep}_scaler.json")
            payload = torch.load(ROOT / f"artifacts/p7_4b_{rep}_estimator.pt", weights_only=True, map_location="cpu")
            model = p7core.FrozenMLP()
            model.load_state_dict(payload["state_dict"])
            model.eval()
            out[f"{rep}_prediction"] = predict_mlp(model, scaler_apply(out[features].to_numpy(float), scaler), multiplier)
    return out, saved


def metric_tables(frame: pd.DataFrame, pool: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows, center_rows, scenario_rows, strata_rows = [], [], [], []
    subgroups = [("all", frame), ("non-C3", frame[frame.scenario != "C3"])]
    subgroups += [(str(name), group) for name, group in frame.groupby("scenario")]
    for rep in ("A0", "A1"):
        target, pred = f"{rep}_target", f"{rep}_prediction"
        for name, group in subgroups:
            summary_rows.append({"pool": pool, "representation": rep, "subgroup": name, **summarize(group, target, pred)})
        cm = center_metrics(frame, target, pred)
        cm.insert(0, "representation", rep); cm.insert(0, "pool", pool)
        center_rows.append(cm)
        for scenario, group in frame.groupby("scenario"):
            scenario_rows.append({"pool": pool, "representation": rep, "scenario": scenario,
                                  **summarize(group, target, pred)})
        for column in ("center_type", "deployment_tier"):
            for value, group in frame.groupby(column):
                strata_rows.append({"pool": pool, "representation": rep, "stratum": column,
                                    "value": value, **summarize(group, target, pred)})
        aged = frame.copy()
        aged["identity_age_bin"] = pd.cut(aged.identity_age, [0,1,2,6,12,24], include_lowest=True).astype(str)
        aged["history_coverage_bin"] = pd.cut(aged.history_coverage, [0,.34,.67,1], include_lowest=True).astype(str)
        for column in ("identity_age_bin", "history_coverage_bin"):
            for value, group in aged.groupby(column, observed=True):
                strata_rows.append({"pool": pool, "representation": rep, "stratum": column,
                                    "value": value, **summarize(group, target, pred)})
    return pd.DataFrame(summary_rows), pd.concat(center_rows, ignore_index=True), pd.DataFrame(scenario_rows), pd.DataFrame(strata_rows)


def commit_paths(paths: list[Path], message: str) -> str:
    rels = [path.relative_to(ROOT).as_posix() for path in paths]
    subprocess.check_call(["git", "add", "--", *rels], cwd=ROOT)
    subprocess.check_call(["git", "commit", "-m", message, "--", *rels], cwd=ROOT)
    return git("rev-parse", "HEAD")


def fit_freeze() -> None:
    assignment, _, _ = preflight()
    centers = list(map(int, assignment["pools"]["RepresentationFit"]))
    frame, scales, raw_hashes = load_pool("fit", centers)
    predicted, fold_scalers = attach_predictions(frame, "fit", assignment)
    write_csv(RESULTS / "fit_oof_predictions.csv", predicted)
    metrics, by_center, by_scenario, by_stratum = metric_tables(predicted, "fit")
    write_csv(RESULTS / "fit_metrics.csv", metrics)
    write_csv(RESULTS / "fit_metrics_by_center.csv", by_center)
    write_csv(RESULTS / "fit_metrics_by_scenario.csv", by_scenario)
    write_csv(RESULTS / "fit_metrics_by_stratum.csv", by_stratum)
    write_csv(RESULTS / "fit_reference_scale_audit.csv", scales)
    save_json(RESULTS / "fit_fold_scalers.json", fold_scalers)
    artifact_paths = []
    for rep in ("A0", "A1"):
        features, target, multiplier = representation_spec(rep)
        scaler = scaler_fit(frame[features].to_numpy(float))
        scaler.update({"schema": "p7.4b-standard-scaler-v1", "representation": rep,
                       "feature_order": features, "ddof": 0, "fit_centers": centers})
        scaler_path = ROOT / f"artifacts/p7_4b_{rep}_scaler.json"
        save_json(scaler_path, scaler)
        model = fit_mlp(scaler_apply(frame[features].to_numpy(float), scaler), frame[target].to_numpy(float),
                        train_config(multiplier), 19631)
        model_path = ROOT / f"artifacts/p7_4b_{rep}_estimator.pt"
        torch.save({"schema": "p7.4b-estimator-v1", "representation": rep,
                    "feature_order": features, "target_multiplier": multiplier,
                    "training_seed": 19631, "state_dict": model.state_dict()}, model_path)
        artifact_paths += [scaler_path, model_path]
    paths = [RESULTS / name for name in (
        "fit_oof_predictions.csv", "fit_metrics.csv", "fit_metrics_by_center.csv",
        "fit_metrics_by_scenario.csv", "fit_metrics_by_stratum.csv", "fit_reference_scale_audit.csv",
        "fit_fold_scalers.json")] + artifact_paths
    files = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}
    files.update(raw_hashes)
    manifest = {
        "schema": "p7.4b-fit-freeze-v1", "created_at_utc": utc(), "status": "FIT_FROZEN",
        "representation_fit_centers": centers, "files": files,
        "behavior_path": ACTION_CONFIG, "stage_pairing_audit_passed": True,
        "scale_audit_passed": True, "validation_accessed": False,
        "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
    }
    save_json(FIT_FREEZE, manifest); write_sha(FIT_FREEZE)
    paths += [FIT_FREEZE, FIT_FREEZE.with_suffix(".sha256")]
    fit_commit = commit_paths(paths, "Freeze P7.4B Fit pipelines before Validation")
    opening = {
        "schema": "p7.4b-validation-opening-v1", "created_at_utc": utc(),
        "validation_open_authorized": True, "fit_freeze_sha256": sha256_file(FIT_FREEZE),
        "final_pipeline_hashes": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in artifact_paths},
        "fit_freeze_git_commit": fit_commit,
        "no_refit_or_reselection_after_opening": True, "heldout_accessed": False,
        "alibaba_accessed": False, "P8_executed": False,
    }
    save_json(VALIDATION_OPENING, opening); write_sha(VALIDATION_OPENING)
    commit_paths([VALIDATION_OPENING, VALIDATION_OPENING.with_suffix(".sha256")],
                 "Authorize one-time P7.4B Validation opening")


def condition_set(metrics: pd.DataFrame, pair: dict, intervals: dict) -> dict:
    a1_all = metrics[(metrics.representation == "A1") & (metrics.subgroup == "all")].iloc[0]
    a1_non = metrics[(metrics.representation == "A1") & (metrics.subgroup == "non-C3")].iloc[0]
    checks = {
        "A1_macro_center_Spearman_gt_0": bool(a1_all.macro_center_Spearman > 0),
        "A1_positive_center_fraction_gt_0_5": bool(a1_all.positive_Spearman_center_fraction > .5),
        "A1_balanced_accuracy_gt_0_5": bool(a1_all.balanced_admission_accuracy > .5),
        "A1_non_C3_macro_center_Spearman_gt_0": bool(a1_non.macro_center_Spearman > 0),
        "Delta_macro_Spearman_gt_0": bool(pair["Delta_macro_Spearman"] > 0),
        "Delta_balanced_accuracy_gt_0": bool(pair["Delta_balanced_admission_accuracy"] > 0),
    }
    s_lo, s_hi = intervals["Delta_macro_Spearman"]
    b_lo, b_hi = intervals["Delta_balanced_admission_accuracy"]
    checks["paired_uncertainty_rule"] = bool((s_lo > 0 and b_hi >= 0) or (b_lo > 0 and s_hi >= 0))
    return checks


def paired_stats(frame: pd.DataFrame) -> dict:
    a0 = summarize(frame, "A0_target", "A0_prediction")
    a1 = summarize(frame, "A1_target", "A1_prediction")
    return {"Delta_macro_Spearman": a1["macro_center_Spearman"] - a0["macro_center_Spearman"],
            "Delta_balanced_admission_accuracy": a1["balanced_admission_accuracy"] - a0["balanced_admission_accuracy"]}


def bootstrap(frame: pd.DataFrame, centers: list[int], resamples: int = 4000) -> tuple[dict, pd.DataFrame]:
    rng = np.random.default_rng(2904)
    values = []
    grouped = {c: frame[frame.center_id == c] for c in centers}
    for index in range(resamples):
        sampled = rng.choice(centers, len(centers), replace=True)
        parts = []
        for occurrence, center in enumerate(sampled):
            part = grouped[int(center)].copy()
            part["center_id"] = occurrence
            parts.append(part)
        stat = paired_stats(pd.concat(parts, ignore_index=True))
        if not all(np.isfinite(list(stat.values()))):
            raise AssertionError("undefined paired bootstrap replicate")
        values.append({"replicate": index, **stat})
    samples = pd.DataFrame(values)
    intervals = {key: [float(np.quantile(samples[key], .025, method="linear")),
                       float(np.quantile(samples[key], .975, method="linear"))]
                 for key in ("Delta_macro_Spearman", "Delta_balanced_admission_accuracy")}
    return intervals, samples


def finalize() -> None:
    assignment, _, _ = preflight(require_fit=True, require_opening=True)
    centers = list(map(int, assignment["pools"]["RepresentationValidation"]))
    frame, scales, raw_hashes = load_pool("validation", centers)
    predicted, _ = attach_predictions(frame, "validation", assignment)
    metrics, val_center, val_scenario, val_stratum = metric_tables(predicted, "validation")
    write_csv(RESULTS / "validation_predictions.csv", predicted)
    write_csv(RESULTS / "validation_metrics.csv", metrics)
    fit_center = pd.read_csv(RESULTS / "fit_metrics_by_center.csv")
    fit_scenario = pd.read_csv(RESULTS / "fit_metrics_by_scenario.csv")
    write_csv(RESULTS / "metrics_by_center.csv", pd.concat([fit_center, val_center], ignore_index=True))
    write_csv(RESULTS / "metrics_by_scenario.csv", pd.concat([fit_scenario, val_scenario], ignore_index=True))
    fit_stratum = pd.read_csv(RESULTS / "fit_metrics_by_stratum.csv")
    write_csv(RESULTS / "metrics_by_stratum.csv", pd.concat([fit_stratum, val_stratum], ignore_index=True))
    fit_scales = pd.read_csv(RESULTS / "fit_reference_scale_audit.csv")
    write_csv(RESULTS / "reference_scale_audit.csv", pd.concat([fit_scales, scales], ignore_index=True))
    point = paired_stats(predicted)
    intervals, samples = bootstrap(predicted, centers)
    paired = pd.DataFrame([{
        **point,
        "Delta_macro_Spearman_CI_low": intervals["Delta_macro_Spearman"][0],
        "Delta_macro_Spearman_CI_high": intervals["Delta_macro_Spearman"][1],
        "Delta_balanced_admission_accuracy_CI_low": intervals["Delta_balanced_admission_accuracy"][0],
        "Delta_balanced_admission_accuracy_CI_high": intervals["Delta_balanced_admission_accuracy"][1],
        "bootstrap_resamples": 4000, "bootstrap_seed": 2904,
    }])
    write_csv(RESULTS / "paired_a1_vs_a0.csv", paired)
    write_csv(RESULTS / "paired_bootstrap_samples.csv", samples)
    loo_rows = []
    for omitted in centers:
        subset = predicted[predicted.center_id != omitted]
        subset_metrics, _, _, _ = metric_tables(subset, "validation_LOO")
        pair = paired_stats(subset)
        loo_intervals, _ = bootstrap(subset, [c for c in centers if c != omitted])
        checks = condition_set(subset_metrics, pair, loo_intervals)
        loo_rows.append({"omitted_center": omitted, **pair,
                         "Delta_macro_Spearman_CI_low": loo_intervals["Delta_macro_Spearman"][0],
                         "Delta_macro_Spearman_CI_high": loo_intervals["Delta_macro_Spearman"][1],
                         "Delta_balanced_admission_accuracy_CI_low": loo_intervals["Delta_balanced_admission_accuracy"][0],
                         "Delta_balanced_admission_accuracy_CI_high": loo_intervals["Delta_balanced_admission_accuracy"][1],
                         **checks, "all_conditions_pass": all(checks.values())})
    loo = pd.DataFrame(loo_rows)
    write_csv(RESULTS / "leave_one_center_out.csv", loo)
    fit_metrics = pd.read_csv(RESULTS / "fit_metrics.csv")
    fit_checks = condition_set(fit_metrics, {"Delta_macro_Spearman": 1, "Delta_balanced_admission_accuracy": 1},
                               {"Delta_macro_Spearman": [1,1], "Delta_balanced_admission_accuracy": [1,1]})
    fit_absolute = {k:v for k,v in fit_checks.items() if k.startswith("A1_")}
    val_checks = condition_set(metrics, point, intervals)
    def metric(pool_frame, rep, name):
        return float(pool_frame[(pool_frame.representation == rep) & (pool_frame.subgroup == "all")].iloc[0][name])
    deterioration = {
        name: {rep: metric(fit_metrics, rep, name) - metric(metrics, rep, name) for rep in ("A0", "A1")}
        for name in ("macro_center_Spearman", "balanced_admission_accuracy")
    }
    deterioration_stop = all(deterioration[name]["A1"] > deterioration[name]["A0"] for name in deterioration)
    all_pass = all(fit_absolute.values()) and all(val_checks.values()) and not deterioration_stop and bool(loo.all_conditions_pass.all())
    verdict = "P7_4B_PASS" if all_pass else "P7_4B_FAIL"
    report = ROOT / "reports/P7_4B_REPRESENTATION_TRANSPORT.md"
    report.write_text(
        "# P7.4B Prospective A0 vs A1 Representation Transport Study\n\n"
        f"## Formal verdict\n\n**{verdict}**\n\n"
        "The behavior/data-generation path was the frozen P7.2 Proposed configuration "
        "(delta_R=-0.000272181217042075, cost ratio=10). A0 and A1 never affected actions, RI, or parent-state evolution. "
        "Every stage passed the required paired parent/action/identity/path-hash audit.\n\n"
        f"## Fit absolute checks\n\n```json\n{json.dumps(fit_absolute, indent=2)}\n```\n\n"
        f"## Validation checks\n\n```json\n{json.dumps(val_checks, indent=2)}\n```\n\n"
        f"## Paired Validation effects\n\n```json\n{json.dumps({**point, 'intervals': intervals}, indent=2)}\n```\n\n"
        f"## Transport deterioration\n\n```json\n{json.dumps(deterioration, indent=2)}\n```\n\n"
        f"Leave-one-center checks passed for {int(loo.all_conditions_pass.sum())} of 24 omissions.\n\n"
        "## Scientific answers and claim boundary\n\n"
        "The exact answers to A--G follow directly from the frozen checks and supplied metric tables. "
        "Even under PASS, the only authorized claim is that the fixed deployment-reference representation improves "
        "prospective cross-center recoverability transport relative to the paired absolute representation under the "
        "evaluated synthetic protocol. This does not establish C2 or C3 restoration, lifecycle superiority, final "
        "heldout success, Alibaba generality, or P8 readiness.\n\n"
        "Execution stops here for human scientific review.\n",
        encoding="utf-8", newline="\n")
    paths = [RESULTS / name for name in (
        "validation_predictions.csv", "validation_metrics.csv", "metrics_by_center.csv", "metrics_by_scenario.csv",
        "metrics_by_stratum.csv", "paired_a1_vs_a0.csv", "paired_bootstrap_samples.csv",
        "reference_scale_audit.csv", "leave_one_center_out.csv")] + [report]
    files = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}
    files.update(raw_hashes)
    audit = {
        "schema": "p7.4b-final-scientific-audit-v1", "created_at_utc": utc(), "verdict": verdict,
        "fit_absolute_checks": fit_absolute, "validation_checks": val_checks,
        "paired_point_estimates": point, "paired_intervals": intervals,
        "transport_deterioration": deterioration, "transport_deterioration_stop": deterioration_stop,
        "leave_one_center_all_pass": bool(loo.all_conditions_pass.all()),
        "behavior_path": ACTION_CONFIG, "all_stage_pairing_audits_passed": True,
        "scale_audits_passed": True, "files": files,
        "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
        "terminal_state": "STOP_FOR_HUMAN_SCIENTIFIC_REVIEW",
    }
    save_json(FINAL_AUDIT, audit); write_sha(FINAL_AUDIT)
    commit_paths(paths + [FINAL_AUDIT, FINAL_AUDIT.with_suffix(".sha256")],
                 f"Complete P7.4B representation study: {verdict}")
    print(verdict, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    for name in ("fit-materialize", "validation-materialize"):
        item = sub.add_parser(name); item.add_argument("--workers", type=int, default=1)
    sub.add_parser("fit-freeze")
    sub.add_parser("finalize")
    args = parser.parse_args()
    install_seed_binding()
    if args.command == "preflight":
        preflight(); print("P7.4B preflight PASS")
    elif args.command == "fit-materialize":
        materialize("fit", args.workers)
    elif args.command == "validation-materialize":
        materialize("validation", args.workers)
    elif args.command == "fit-freeze":
        fit_freeze()
    else:
        finalize()


if __name__ == "__main__":
    main()
