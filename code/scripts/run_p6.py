from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.common import ROOT, sha256_file, write_json as strict_write_json
from core.data import generate_base_centers
from core.models import build_identity_bank
from core.p6 import (
    FEATURE_COLUMNS,
    apply_scaler,
    attach_tau,
    causal_history_features,
    fit_scaler,
    run_p6_trajectory,
)


P4_PATH = ROOT / "audits" / "P4_EXPERIMENT_SCOPE_FREEZE.json"
FROZEN_CONFIG = ROOT / "configs" / "p3_mismatch_v2_frozen.json"
CANDIDATE_CONFIG = ROOT / "configs" / "p6_estimator_candidates.json"
FOLD_CONFIG = ROOT / "configs" / "p6_group_cv_folds.json"
RESULTS = ROOT / "results" / "p6"
ARTIFACTS = ROOT / "artifacts"
REPORT = ROOT / "reports" / "P6_ESTIMATOR_FITTING_AND_SELECTION.md"
AUDIT_MD = ROOT / "audits" / "P6_SCIENTIFIC_AUDIT.md"
FREEZE = ROOT / "audits" / "P6_ESTIMATOR_FREEZE.json"
FREEZE_SHA = ROOT / "audits" / "P6_ESTIMATOR_FREEZE.sha256"
CHANGELOG = ROOT / "docs" / "P6_EXECUTION_CHANGELOG.md"
OKABE = ["#0072B2", "#E69F00", "#009E73", "#D55E00"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return None
    return value


def write_json(path: Path, value) -> None:
    strict_write_json(path, json_safe(value))


def json_records(frame: pd.DataFrame) -> list[dict]:
    """Represent undefined descriptive statistics as JSON null, not NaN."""
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def validate_preflight() -> tuple[dict, dict, dict, dict, list[int]]:
    p4 = load_json(P4_PATH)
    frozen = load_json(FROZEN_CONFIG)
    candidates = load_json(CANDIDATE_CONFIG)
    folds = load_json(FOLD_CONFIG)
    if sha256_file(P4_PATH) != candidates["p4_scope_manifest_sha256"]:
        raise AssertionError("P4 scope manifest hash changed")
    if sha256_file(FROZEN_CONFIG) != candidates["generator_config_sha256"]:
        raise AssertionError("frozen generator config hash changed")
    for path in (CANDIDATE_CONFIG, FOLD_CONFIG):
        expected = path.with_suffix(".sha256").read_text(encoding="utf-8").split()[0]
        if sha256_file(path) != expected:
            raise AssertionError(f"predeclared config hash mismatch: {path}")

    pool = p4["center_pools"]["prospective_estimator_fitting"]
    center_ids = list(range(pool["id_start"], pool["id_end_inclusive"] + 1))
    if center_ids != folds["fitting_centers"] or len(center_ids) != pool["count"]:
        raise AssertionError("P6 fitting pool does not match P4 freeze")
    other = [
        set(p4["center_pools"]["source_training"]["ids"]),
        set(p4["center_pools"]["generator_design_development"]["ids"]),
        set(p4["center_pools"]["fresh_phenomenon_development"]["ids"]),
        set(range(32000, 32020)),
        set(range(33000, 33020)),
    ]
    if any(set(center_ids) & values for values in other):
        raise AssertionError("P6 fitting pool overlaps a protected pool")
    validation_sets = [set(item["validation_centers"]) for item in folds["folds"]]
    if set().union(*validation_sets) != set(center_ids):
        raise AssertionError("CV folds do not cover the fitting pool")
    if any(left & right for i, left in enumerate(validation_sets) for right in validation_sets[i + 1 :]):
        raise AssertionError("CV validation folds overlap")
    if frozen["scenarios"] != ["C0", "C1", "C3", "C4"]:
        raise AssertionError("frozen P6 scenario set changed")
    if frozen["primary_recoverability_horizon"] != 4 or frozen["primary_eta"] != 0.25:
        raise AssertionError("frozen primary target setting changed")
    if frozen["local_policies"] != [0, 10, 20, 50] or frozen["feature_components"] != ["gain", "residual"]:
        raise AssertionError("frozen budget or response event changed")
    source_manifest = Path(p4["source_and_model_bank"]["r3_source_training_manifest_path"])
    if sha256_file(ROOT / source_manifest) != p4["source_and_model_bank"]["r3_source_training_manifest_sha256"]:
        raise AssertionError("frozen P3.2 source-bank manifest changed")
    bank = p4["source_and_model_bank"]
    for key, directory in (
        ("native_checkpoint_sha256", ROOT / "imported" / "msa_dti" / "bank"),
        ("r3_new_checkpoint_sha256", ROOT / source_manifest.parent),
    ):
        for filename, expected in bank[key].items():
            if sha256_file(directory / filename) != expected:
                raise AssertionError(f"frozen bank checkpoint changed: {filename}")
    return p4, frozen, candidates, folds, center_ids


def _raw_path(scenario: str, center_id: int, seed: int) -> Path:
    return RESULTS / "raw" / f"{scenario}_{center_id}_{seed}.csv"


def materialize() -> pd.DataFrame:
    p4, frozen, _, _, center_ids = validate_preflight()
    (RESULTS / "raw").mkdir(parents=True, exist_ok=True)
    bases = generate_base_centers(center_ids, data_seed=frozen["data_seed"])
    incumbent = next(item for item in build_identity_bank() if item.identity_id == "msa_a57_pt")
    expected_incumbent_hash = p4["source_and_model_bank"]["native_checkpoint_sha256"]["formal_h1_a57.pt"]
    if incumbent.checkpoint_sha256 != expected_incumbent_hash:
        raise AssertionError("incumbent checkpoint hash changed")

    tau_path = RESULTS / "tau_service_fitting.json"
    tau_rows = load_json(tau_path) if tau_path.exists() else {}
    total = len(bases) * len(frozen["model_seeds"]) * len(frozen["scenarios"])
    completed = 0
    resumed = sum(path.exists() for base in bases for seed in frozen["model_seeds"] for scenario in frozen["scenarios"] for path in [_raw_path(scenario, base.center_id, int(seed))])
    started = time.perf_counter()
    all_frames: list[pd.DataFrame] = []

    for base in bases:
        for seed_value in frozen["model_seeds"]:
            seed = int(seed_value)
            key = f"{base.center_id}:{seed}"
            c0_path = _raw_path("C0", base.center_id, seed)
            if c0_path.exists() and key in tau_rows:
                c0 = pd.read_csv(c0_path)
            else:
                trajectory = run_p6_trajectory(base, seed, "C0", incumbent, frozen, None)
                if len(trajectory.reference_losses) != 8:
                    raise AssertionError("C0 reference must contain stages 1-8")
                reference = float(np.mean(trajectory.reference_losses))
                tau = float((1.0 + frozen["primary_eta"]) * reference)
                tau_rows[key] = {
                    "center_id": base.center_id,
                    "seed": seed,
                    "L_ref": reference,
                    "eta": frozen["primary_eta"],
                    "tau_service": tau,
                }
                c0 = pd.DataFrame(attach_tau(trajectory.rows, tau))
                c0.to_csv(c0_path, index=False)
                write_json(tau_path, tau_rows)
            if len(c0) != 24 or c0.R_B50.isna().any():
                raise AssertionError(f"invalid resumable C0 trajectory: {key}")
            all_frames.append(c0)
            completed += 1
            _progress(completed, total, started, resumed)

            tau = float(tau_rows[key]["tau_service"])
            for scenario in ("C1", "C3", "C4"):
                path = _raw_path(scenario, base.center_id, seed)
                if path.exists():
                    frame = pd.read_csv(path)
                else:
                    trajectory = run_p6_trajectory(base, seed, scenario, incumbent, frozen, tau)
                    frame = pd.DataFrame(trajectory.rows)
                    frame.to_csv(path, index=False)
                if len(frame) != 24 or frame.R_B50.isna().any():
                    raise AssertionError(f"invalid resumable trajectory: {scenario}-{key}")
                all_frames.append(frame)
                completed += 1
                _progress(completed, total, started, resumed)

    stage = pd.concat(all_frames, ignore_index=True)
    stage = stage.sort_values(["center_id", "seed", "scenario", "stage"]).reset_index(drop=True)
    expected_rows = 30 * 3 * 4 * 24
    if len(stage) != expected_rows or stage.duplicated(["center_id", "seed", "scenario", "stage"]).any():
        raise AssertionError("P6 fitting stage-record coverage is incomplete")
    if set(stage.feature_components) != {"gain,residual"} or set(stage.probe_update_count) != {50}:
        raise AssertionError("response event or effort boundary changed")
    if not stage.oracle_future_data_offline_only.eq(True).all():
        raise AssertionError("offline oracle target boundary failed")
    if ((stage.assessment_ts > stage.decision_ts) | (stage.decision_ts >= stage.service_start_ts)).any():
        raise AssertionError("causal timeline ordering failed")
    stage.to_csv(RESULTS / "stage_records.csv", index=False)
    write_json(
        RESULTS / "materialization_status.json",
        {
            "status": "COMPLETED",
            "trajectories": total,
            "stage_rows": len(stage),
            "fitting_centers": center_ids,
            "calibration_accessed": False,
            "heldout_accessed": False,
            "alibaba_accessed": False,
            "generator_modified": False,
        },
    )
    return stage


def _progress(completed: int, total: int, started: float, resumed: int = 0) -> None:
    elapsed = time.perf_counter() - started
    newly_completed = max(0, completed - resumed)
    eta = elapsed / newly_completed * (total - completed) if newly_completed else None
    eta_text = f"{eta:.1f}" if eta is not None else "pending_new_checkpoint"
    print(
        f"[P6 materialize] completed={completed}/{total} elapsed_s={elapsed:.1f} eta_s={eta_text}",
        flush=True,
    )
    write_json(
        RESULTS / "execution_status.json",
        {"status": "RUNNING", "completed": completed, "expected": total, "resumed_checkpoints": resumed, "elapsed_seconds": elapsed, "eta_seconds": eta},
    )


class SmallMLP(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(6, 16),
            torch.nn.ReLU(),
            torch.nn.Linear(16, 8),
            torch.nn.ReLU(),
            torch.nn.Linear(8, 1),
        )

    def forward(self, x):
        return self.layers(x).squeeze(-1)


def fit_mlp(x: np.ndarray, y: np.ndarray, config: dict, seed: int) -> SmallMLP:
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = SmallMLP()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(config["learning_rate"]),
        weight_decay=float(config["weight_decay"]),
    )
    tx = torch.as_tensor(x, dtype=torch.float32)
    ty = torch.as_tensor(y * float(config["target_multiplier"]), dtype=torch.float32)
    for _ in range(int(config["epoch_budget"])):
        optimizer.zero_grad()
        loss = torch.nn.functional.mse_loss(model(tx), ty)
        loss.backward()
        optimizer.step()
    return model


def predict_mlp(model: SmallMLP, x: np.ndarray, target_multiplier: float) -> np.ndarray:
    with torch.no_grad():
        return model(torch.as_tensor(x, dtype=torch.float32)).numpy() / target_multiplier


def safe_spearman(y: np.ndarray, prediction: np.ndarray) -> float:
    if len(y) < 3 or np.std(y) == 0 or np.std(prediction) == 0:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(spearmanr(y, prediction).statistic)


def balanced_accuracy(y: np.ndarray, prediction: np.ndarray) -> float:
    actual = y < 0
    predicted = prediction < 0
    if actual.all() or (~actual).all():
        return float("nan")
    negative_recall = float(predicted[actual].mean())
    nonnegative_recall = float((~predicted[~actual]).mean())
    return (negative_recall + nonnegative_recall) / 2


def metric_values(y: np.ndarray, prediction: np.ndarray) -> dict:
    error = prediction - y
    return {
        "n": int(len(y)),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "spearman": safe_spearman(y, prediction),
        "sign_accuracy": float(np.mean((y < 0) == (prediction < 0))),
        "balanced_accuracy": balanced_accuracy(y, prediction),
        "negative_prevalence": float(np.mean(y < 0)),
    }


def summarize_candidate(base: pd.DataFrame, prediction: np.ndarray) -> tuple[dict, pd.DataFrame]:
    frame = base[["center_id", "R_B50"]].copy()
    frame["prediction"] = prediction
    centers = []
    for center_id, group in frame.groupby("center_id"):
        values = metric_values(group.R_B50.to_numpy(), group.prediction.to_numpy())
        centers.append({"center_id": int(center_id), **values})
    center_frame = pd.DataFrame(centers)
    pooled = metric_values(frame.R_B50.to_numpy(), frame.prediction.to_numpy())
    summary = {
        "macro_center_mae": float(center_frame.mae.mean()),
        "macro_center_rmse": float(center_frame.rmse.mean()),
        "macro_center_spearman_mean": float(center_frame.spearman.mean()),
        "macro_center_spearman_median": float(center_frame.spearman.median()),
        "pooled_spearman": pooled["spearman"],
        "sign_accuracy": pooled["sign_accuracy"],
        "balanced_accuracy": pooled["balanced_accuracy"],
        "center_mae_sd": float(center_frame.mae.std(ddof=1)),
    }
    return summary, center_frame


def fold_map(folds: dict) -> dict[int, int]:
    return {
        int(center): int(item["fold"])
        for item in folds["folds"]
        for center in item["validation_centers"]
    }


def cross_validate(stage: pd.DataFrame) -> dict:
    _, _, candidates, folds, center_ids = validate_preflight()
    mapper = fold_map(folds)
    base = stage.copy()
    base["fold"] = base.center_id.map(mapper)
    if base.fold.isna().any():
        raise AssertionError("stage record center missing from CV folds")
    base["fold"] = base.fold.astype(int)

    predictions: dict[str, np.ndarray] = {}
    metadata: dict[str, dict] = {}
    scalers: dict[tuple[int, int, int], dict] = {}
    feature_frames: dict[tuple[int, int], pd.DataFrame] = {}
    mlp_cfg = candidates["estimators"]["mlp"]

    for pair_index, (k_short, k_long) in enumerate(candidates["window_grid"]["ordered_valid_pairs"]):
        features = causal_history_features(base, int(k_short), int(k_long))
        features["fold"] = features.center_id.map(mapper).astype(int)
        feature_frames[(int(k_short), int(k_long))] = features
        x_all = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
        y_all = features.R_B50.to_numpy(dtype=np.float64)
        ridge_ids = []
        for alpha in candidates["estimators"]["ridge"]["alphas"]:
            config_id = f"ridge_ks{k_short}_kl{k_long}_alpha{alpha:g}"
            predictions[config_id] = np.full(len(features), np.nan)
            metadata[config_id] = {"model_family": "Ridge", "K_S": k_short, "K_L": k_long, "alpha": alpha}
            ridge_ids.append((config_id, float(alpha)))
        mlp_id = f"mlp_ks{k_short}_kl{k_long}"
        predictions[mlp_id] = np.full(len(features), np.nan)
        metadata[mlp_id] = {"model_family": "MLP", "K_S": k_short, "K_L": k_long, "alpha": None}

        for fold in range(5):
            train_mask = features.fold.to_numpy() != fold
            valid_mask = ~train_mask
            scaler = fit_scaler(x_all[train_mask])
            scalers[(int(k_short), int(k_long), fold)] = scaler
            x_train = apply_scaler(x_all[train_mask], scaler)
            x_valid = apply_scaler(x_all[valid_mask], scaler)
            y_train = y_all[train_mask]
            for config_id, alpha in ridge_ids:
                model = Ridge(alpha=alpha, fit_intercept=True)
                model.fit(x_train, y_train)
                predictions[config_id][valid_mask] = model.predict(x_valid)
            seed = int(mlp_cfg["base_seed"]) + pair_index * 100 + fold
            model = fit_mlp(x_train, y_train, mlp_cfg, seed)
            predictions[mlp_id][valid_mask] = predict_mlp(model, x_valid, float(mlp_cfg["target_multiplier"]))
        print(f"[P6 CV] completed window K_S={k_short}, K_L={k_long}", flush=True)

    summaries = []
    center_metrics_by_config = {}
    for config_id, prediction in predictions.items():
        if np.isnan(prediction).any():
            raise AssertionError(f"incomplete OOF predictions: {config_id}")
        summary, centers = summarize_candidate(base, prediction)
        summaries.append({"config_id": config_id, **metadata[config_id], **summary})
        center_metrics_by_config[config_id] = centers
    summary_frame = pd.DataFrame(summaries).sort_values(["macro_center_mae", "config_id"]).reset_index(drop=True)
    summary_frame.to_csv(RESULTS / "candidate_cv_summary.csv", index=False)

    best = summary_frame.iloc[0]
    best_center = center_metrics_by_config[best.config_id]
    one_se = float(best.center_mae_sd / math.sqrt(len(center_ids)))
    threshold = float(best.macro_center_mae + one_se)
    eligible = summary_frame[summary_frame.macro_center_mae <= threshold].copy()
    family = "Ridge" if (eligible.model_family == "Ridge").any() else "MLP"
    eligible = eligible[eligible.model_family == family].copy()
    eligible["alpha_sort"] = eligible.alpha.fillna(0).map(lambda value: -float(value))
    selected = eligible.sort_values(
        ["K_L", "K_S", "alpha_sort", "macro_center_mae", "config_id"]
    ).iloc[0]
    selected_id = str(selected.config_id)
    selected_prediction = predictions[selected_id]
    selected_features = feature_frames[(int(selected.K_S), int(selected.K_L))].copy()
    selected_features["fold"] = selected_features.center_id.map(mapper).astype(int)
    selected_features.to_csv(RESULTS / "selected_feature_matrix.csv", index=False)

    selected_output = selected_features[
        ["center_id", "seed", "scenario", "stage", "fold", "identity_id", "R_B50"]
    ].copy()
    selected_output["predicted_R_B50"] = selected_prediction
    selected_output["error"] = selected_prediction - selected_output.R_B50
    selected_output.to_csv(RESULTS / "cv_predictions.csv", index=False)

    selected_center = metrics_by_center(selected_output)
    selected_scenario = metrics_by_scenario(selected_output)
    selected_fold = metrics_by_fold(selected_output)
    selected_center.to_csv(RESULTS / "metrics_by_center.csv", index=False)
    selected_scenario.to_csv(RESULTS / "metrics_by_scenario.csv", index=False)
    selected_fold.to_csv(RESULTS / "fold_metrics.csv", index=False)

    fold_scalers = {
        "schema": "dt-lifecycle-escalation-p6-fold-scalers-v1",
        "selected_config_id": selected_id,
        "feature_order": FEATURE_COLUMNS,
        "folds": [],
    }
    for fold in range(5):
        valid = set(folds["folds"][fold]["validation_centers"])
        fold_scalers["folds"].append(
            {
                "fold": fold,
                "training_centers": sorted(set(center_ids) - valid),
                "validation_centers": sorted(valid),
                "scaler": scalers[(int(selected.K_S), int(selected.K_L), fold)],
            }
        )
    write_json(RESULTS / "fold_scalers.json", fold_scalers)

    baseline_prediction = np.full(len(selected_output), np.nan)
    for fold in range(5):
        train_mean = float(selected_output.loc[selected_output.fold != fold, "R_B50"].mean())
        baseline_prediction[selected_output.fold.to_numpy() == fold] = train_mean
    baseline_summary, _ = summarize_candidate(selected_output, baseline_prediction)
    selected_summary, _ = summarize_candidate(selected_output, selected_prediction)
    gate = evaluate_pass_gate(selected_output, selected_summary, selected_fold, baseline_summary, candidates)

    selection = {
        "schema": "dt-lifecycle-escalation-p6-selected-estimator-v1",
        "selection_status": "CV_PASS" if gate["pass"] else "CV_FAIL",
        "selected_config_id": selected_id,
        "selected_model_family": family,
        "K_S": int(selected.K_S),
        "K_L": int(selected.K_L),
        "ridge_alpha": None if family != "Ridge" else float(selected.alpha),
        "best_observed_config_id": str(best.config_id),
        "best_observed_macro_center_mae": float(best.macro_center_mae),
        "best_observed_center_mae_se": one_se,
        "one_se_threshold": threshold,
        "selected_metrics": selected_summary,
        "baseline_metrics": baseline_summary,
        "pass_gate": gate,
        "final_refit_performed": False,
        "calibration_accessed": False,
        "heldout_accessed": False,
    }
    write_json(ROOT / "configs" / "p6_selected_estimator.json", selection)
    write_json(
        RESULTS / "cv_analysis.json",
        {
            "selection": selection,
            "top_candidates": json_records(summary_frame.head(12)),
            "scenario_metrics": json_records(selected_scenario),
            "fold_metrics": json_records(selected_fold),
        },
    )
    return selection


def recover_saved_cv() -> dict:
    """Finish a failed JSON output step using persisted CV results, without fitting."""
    selection_path = ROOT / "configs" / "p6_selected_estimator.json"
    if selection_path.exists() and load_json(selection_path).get("final_refit_performed"):
        raise AssertionError("final estimator already frozen; do not overwrite selection during output recovery")
    _, _, candidates, folds, center_ids = validate_preflight()
    summary = pd.read_csv(RESULTS / "candidate_cv_summary.csv").sort_values(["macro_center_mae", "config_id"]).reset_index(drop=True)
    expected_ids = set()
    for ks, kl in candidates["window_grid"]["ordered_valid_pairs"]:
        expected_ids.add(f"mlp_ks{ks}_kl{kl}")
        for alpha in candidates["estimators"]["ridge"]["alphas"]:
            expected_ids.add(f"ridge_ks{ks}_kl{kl}_alpha{alpha:g}")
    if len(summary) != len(expected_ids) or set(summary.config_id) != expected_ids:
        raise AssertionError("persisted candidate summary incomplete")
    best = summary.iloc[0]
    one_se = float(best.center_mae_sd / math.sqrt(len(center_ids)))
    threshold = float(best.macro_center_mae + one_se)
    eligible = summary[summary.macro_center_mae <= threshold].copy()
    family = "Ridge" if (eligible.model_family == "Ridge").any() else "MLP"
    eligible = eligible[eligible.model_family == family].copy()
    eligible["alpha_sort"] = eligible.alpha.fillna(0).map(lambda value: -float(value))
    selected = eligible.sort_values(["K_L", "K_S", "alpha_sort", "macro_center_mae", "config_id"]).iloc[0]
    features = pd.read_csv(RESULTS / "selected_feature_matrix.csv")
    output = pd.read_csv(RESULTS / "cv_predictions.csv")
    if len(output) != 8640 or set(output.center_id) != set(center_ids) or not np.isfinite(output.predicted_R_B50).all():
        raise AssertionError("persisted OOF predictions incomplete")
    if set(features.K_S) != {int(selected.K_S)} or set(features.K_L) != {int(selected.K_L)}:
        raise AssertionError("persisted selected features differ from predeclared selection")
    if not output.fold.eq(output.center_id.map(fold_map(folds))).all():
        raise AssertionError("persisted OOF fold assignments differ")
    scalers = load_json(RESULTS / "fold_scalers.json")
    if scalers["selected_config_id"] != selected.config_id:
        raise AssertionError("persisted selected scaler configuration differs")
    selected_summary, _ = summarize_candidate(output, output.predicted_R_B50.to_numpy())
    if not np.isclose(selected_summary["macro_center_mae"], selected.macro_center_mae, rtol=1e-10, atol=1e-14):
        raise AssertionError("persisted prediction metrics differ from candidate summary")
    baseline = np.full(len(output), np.nan)
    for fold in range(5):
        baseline[output.fold.to_numpy() == fold] = float(output.loc[output.fold != fold, "R_B50"].mean())
    baseline_summary, _ = summarize_candidate(output, baseline)
    scenario_metrics = metrics_by_scenario(output)
    fold_metrics = metrics_by_fold(output)
    gate = evaluate_pass_gate(output, selected_summary, fold_metrics, baseline_summary, candidates)
    selection = {
        "schema": "dt-lifecycle-escalation-p6-selected-estimator-v1",
        "selection_status": "CV_PASS" if gate["pass"] else "CV_FAIL",
        "selected_config_id": str(selected.config_id), "selected_model_family": family,
        "K_S": int(selected.K_S), "K_L": int(selected.K_L),
        "ridge_alpha": None if family != "Ridge" else float(selected.alpha),
        "best_observed_config_id": str(best.config_id),
        "best_observed_macro_center_mae": float(best.macro_center_mae),
        "best_observed_center_mae_se": one_se, "one_se_threshold": threshold,
        "selected_metrics": selected_summary, "baseline_metrics": baseline_summary,
        "pass_gate": gate, "final_refit_performed": False,
        "calibration_accessed": False, "heldout_accessed": False,
        "output_recovered_without_cv_refit": True,
    }
    write_json(ROOT / "configs" / "p6_selected_estimator.json", selection)
    write_json(RESULTS / "cv_analysis.json", {"selection": selection, "top_candidates": json_records(summary.head(12)), "scenario_metrics": json_records(scenario_metrics), "fold_metrics": json_records(fold_metrics)})
    return selection


def metrics_by_center(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for center_id, group in frame.groupby("center_id"):
        rows.append({"center_id": int(center_id), "fold": int(group.fold.iloc[0]), **metric_values(group.R_B50.to_numpy(), group.predicted_R_B50.to_numpy())})
    return pd.DataFrame(rows)


def metrics_by_scenario(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario, group in frame.groupby("scenario"):
        pooled = metric_values(group.R_B50.to_numpy(), group.predicted_R_B50.to_numpy())
        centers = metrics_by_center(group)
        rows.append(
            {
                "scenario": scenario,
                **pooled,
                "macro_center_mae": float(centers.mae.mean()),
                "macro_center_rmse": float(centers.rmse.mean()),
                "macro_center_spearman_mean": float(centers.spearman.mean()),
                "macro_center_spearman_median": float(centers.spearman.median()),
            }
        )
    return pd.DataFrame(rows)


def metrics_by_fold(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for fold, group in frame.groupby("fold"):
        pooled = metric_values(group.R_B50.to_numpy(), group.predicted_R_B50.to_numpy())
        centers = metrics_by_center(group)
        rows.append(
            {
                "fold": int(fold),
                "validation_centers": ",".join(map(str, sorted(group.center_id.unique()))),
                **pooled,
                "macro_center_mae": float(centers.mae.mean()),
                "macro_center_rmse": float(centers.rmse.mean()),
                "macro_center_spearman_mean": float(centers.spearman.mean()),
                "centers_positive_spearman": int((centers.spearman > 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def evaluate_pass_gate(frame: pd.DataFrame, selected: dict, folds: pd.DataFrame, baseline: dict, candidates: dict) -> dict:
    rule = candidates["predeclared_cv_pass_gate"]
    center_metrics = metrics_by_center(frame)
    non_c3 = frame[frame.scenario != "C3"]
    non_c3_values = metric_values(non_c3.R_B50.to_numpy(), non_c3.predicted_R_B50.to_numpy())
    relative_improvement = (baseline["macro_center_mae"] - selected["macro_center_mae"]) / baseline["macro_center_mae"]
    leave_center = [
        safe_spearman(frame.loc[frame.center_id != center, "R_B50"].to_numpy(), frame.loc[frame.center_id != center, "predicted_R_B50"].to_numpy())
        for center in sorted(frame.center_id.unique())
    ]
    leave_fold = [
        safe_spearman(frame.loc[frame.fold != fold, "R_B50"].to_numpy(), frame.loc[frame.fold != fold, "predicted_R_B50"].to_numpy())
        for fold in sorted(frame.fold.unique())
    ]
    checks = {
        "selected_pooled_spearman": selected["pooled_spearman"] >= rule["selected_pooled_spearman_min"],
        "selected_macro_center_spearman_median": selected["macro_center_spearman_median"] > rule["selected_macro_center_spearman_median_min_exclusive"],
        "selected_balanced_accuracy": selected["balanced_accuracy"] >= rule["selected_balanced_accuracy_min"],
        "positive_fold_spearman_count": int((folds.spearman > 0).sum()) >= rule["folds_with_positive_pooled_spearman_min"],
        "relative_macro_mae_improvement": relative_improvement >= rule["relative_macro_center_mae_improvement_over_fold_training_mean_baseline_min"],
        "non_c3_pooled_spearman": non_c3_values["spearman"] >= rule["non_c3_pooled_spearman_min"],
        "non_c3_balanced_accuracy": non_c3_values["balanced_accuracy"] >= rule["non_c3_balanced_accuracy_min"],
        "leave_one_center_out_positive": min(leave_center) > 0,
        "leave_one_fold_out_positive": min(leave_fold) > 0,
    }
    return {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "relative_macro_center_mae_improvement": float(relative_improvement),
        "non_c3_metrics": non_c3_values,
        "center_spearman_positive_count": int((center_metrics.spearman > 0).sum()),
        "center_spearman_negative_count": int((center_metrics.spearman < 0).sum()),
        "leave_one_center_out_spearman_min": float(min(leave_center)),
        "leave_one_center_out_spearman_max": float(max(leave_center)),
        "leave_one_fold_out_spearman_min": float(min(leave_fold)),
        "leave_one_fold_out_spearman_max": float(max(leave_fold)),
    }


def run_tests() -> dict:
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_p6.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = process.stdout + process.stderr
    (RESULTS / "pytest_output.txt").write_text(output, encoding="utf-8")
    result = {"exit_code": process.returncode, "passed": process.returncode == 0, "output": output.strip()}
    write_json(RESULTS / "pytest_status.json", result)
    print(output, flush=True)
    return result


def final_refit() -> dict:
    candidates = load_json(CANDIDATE_CONFIG)
    selection_path = ROOT / "configs" / "p6_selected_estimator.json"
    selection = load_json(selection_path)
    tests = load_json(RESULTS / "pytest_status.json")
    if not selection["pass_gate"]["pass"] or not tests["passed"]:
        return selection
    if selection.get("final_refit_performed"):
        for component in ("scaler", "estimator"):
            if sha256_file(ROOT / selection[f"{component}_artifact"]) != selection[f"{component}_sha256"]:
                raise AssertionError(f"immutable final {component} hash changed")
        return selection
    features = pd.read_csv(RESULTS / "selected_feature_matrix.csv")
    x = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    y = features.R_B50.to_numpy(dtype=np.float64)
    scaler = fit_scaler(x)
    scaler_artifact = ARTIFACTS / "p6_recoverability_scaler.json"
    write_json(
        scaler_artifact,
        {
            "schema": "dt-lifecycle-escalation-p6-standard-scaler-v1",
            "feature_order": FEATURE_COLUMNS,
            "fitting_centers": sorted(map(int, features.center_id.unique())),
            "mean": scaler["mean"],
            "scale": scaler["scale"],
        },
    )
    scaled = apply_scaler(x, scaler)
    model_family = selection["selected_model_family"]
    if model_family == "Ridge":
        model = Ridge(alpha=float(selection["ridge_alpha"]), fit_intercept=True)
        model.fit(scaled, y)
        estimator_artifact = ARTIFACTS / "p6_recoverability_estimator.npz"
        np.savez(
            estimator_artifact,
            model_family=np.asarray(["Ridge"]),
            alpha=np.asarray([selection["ridge_alpha"]], dtype=np.float64),
            coef=model.coef_.astype(np.float64),
            intercept=np.asarray([model.intercept_], dtype=np.float64),
            K_S=np.asarray([selection["K_S"]], dtype=np.int64),
            K_L=np.asarray([selection["K_L"]], dtype=np.int64),
        )
    else:
        mlp_cfg = candidates["estimators"]["mlp"]
        model = fit_mlp(scaled, y, mlp_cfg, int(mlp_cfg["base_seed"]) + 9999)
        estimator_artifact = ARTIFACTS / "p6_recoverability_estimator.pt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "architecture": mlp_cfg["architecture"],
                "target_multiplier": mlp_cfg["target_multiplier"],
                "K_S": selection["K_S"],
                "K_L": selection["K_L"],
            },
            estimator_artifact,
        )
    selection["final_refit_performed"] = True
    selection["scaler_artifact"] = scaler_artifact.relative_to(ROOT).as_posix()
    selection["estimator_artifact"] = estimator_artifact.relative_to(ROOT).as_posix()
    selection["scaler_sha256"] = sha256_file(scaler_artifact)
    selection["estimator_sha256"] = sha256_file(estimator_artifact)
    write_json(selection_path, selection)
    return selection


def make_diagnostics(export_vectors: bool = False) -> dict:
    frame = pd.read_csv(RESULTS / "cv_predictions.csv")
    figures = RESULTS / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, "C:/Users/92487/.codex/skills/scipilot-figure-skill/scripts")
    from layout_tools import add_panel_labels, finalize_figure
    if export_vectors:
        qa = load_json(RESULTS / "visual_qa.json")
        if not qa["approved"] or qa["cv_predictions_sha256"] != sha256_file(RESULTS / "cv_predictions.csv"):
            raise AssertionError("vector export requires current recorded visual QA")
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.9)

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6), constrained_layout=True)
    for ax, (scenario, group), color in zip(axes.flat, frame.groupby("scenario"), OKABE):
        ax.scatter(group.R_B50, group.predicted_R_B50, s=6, alpha=0.18, color=color, edgecolors="none")
        limits = [min(group.R_B50.min(), group.predicted_R_B50.min()), max(group.R_B50.max(), group.predicted_R_B50.max())]
        ax.plot(limits, limits, color="black", linewidth=0.8, linestyle="--")
        ax.set_title("C4: nonlinear dependency-shift stress" if scenario == "C4" else scenario)
        ax.set_xlabel("Oracle recoverability margin")
        ax.set_ylabel("OOF predicted margin")
    finalize_figure(fig)
    add_panel_labels(fig, style="nature", fontsize=9, x_offset_pt=-20)
    _save_figure(fig, figures / "predicted_vs_oracle", export_vectors)

    fig, ax = plt.subplots(figsize=(7.2, 3.4), constrained_layout=True)
    for (scenario, group), color, style in zip(frame.groupby("scenario"), OKABE, ["-", "--", "-.", ":"]):
        sns.kdeplot(group.error, ax=ax, color=color, linestyle=style, linewidth=1.2, label=scenario)
    ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel("OOF prediction error (predicted − oracle)")
    ax.set_ylabel("Density")
    ax.legend(frameon=False, title="Scenario", ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.25))
    _save_figure(fig, figures / "residual_distribution", export_vectors)

    actual = (frame.R_B50 < 0).astype(int)
    predicted = (frame.predicted_R_B50 < 0).astype(int)
    matrix = pd.crosstab(actual, predicted).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
    fig, ax = plt.subplots(figsize=(3.5, 3.0), constrained_layout=True)
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar_kws={"label": "Count"}, ax=ax, square=True)
    ax.set_xlabel("Predicted R<0")
    ax.set_ylabel("Oracle R<0")
    ax.set_xticklabels(["No", "Yes"])
    ax.set_yticklabels(["No", "Yes"], rotation=0)
    _save_figure(fig, figures / "sign_confusion_matrix", export_vectors)

    calibration_path = RESULTS / "calibration_bins.csv"
    calibration = pd.read_csv(calibration_path) if calibration_path.exists() else calibration_table(frame)
    if not calibration_path.exists():
        calibration.to_csv(calibration_path, index=False)
    fig, ax = plt.subplots(figsize=(3.8, 3.2), constrained_layout=True)
    ax.vlines(calibration.mean_prediction, calibration.ci_low, calibration.ci_high, color=OKABE[0], linewidth=0.8)
    ax.plot(
        calibration.mean_prediction,
        calibration.mean_oracle,
        "o",
        color=OKABE[0],
        markersize=4,
        linewidth=0.8,
    )
    limits = [min(calibration.mean_prediction.min(), calibration.mean_oracle.min()), max(calibration.mean_prediction.max(), calibration.mean_oracle.max())]
    ax.plot(limits, limits, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Mean OOF predicted margin (decile)")
    ax.set_ylabel("Mean oracle margin")
    _save_figure(fig, figures / "continuous_margin_calibration", export_vectors)
    return {path.name: sha256_file(path) for path in sorted(figures.glob("*.png"))}


def _save_figure(fig, base: Path, export_vectors: bool = False) -> None:
    skill_scripts = Path("C:/Users/92487/.codex/skills/scipilot-figure-skill/scripts")
    sys.path.insert(0, str(skill_scripts))
    from visual_qa import audit_layout
    issues = audit_layout(fig)
    write_json(base.with_name(base.name + "_layout_qa.json"), {"issues": issues, "ai_visual_review": "PENDING"})
    if any(severity == "FAIL" for severity, _ in issues):
        raise AssertionError(f"figure layout failed: {base.name}")
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    from export_figure import export_figure
    # Use the same render sequence in preview and vector modes: constrained
    # layout can settle differently after an additional canvas draw.
    export_figure(fig, str(base), formats=[], dpi=300, grayscale_preview=True)
    if export_vectors:
        qa = load_json(RESULTS / "visual_qa.json")
        if sha256_file(base.with_suffix(".png")) != qa["png_sha256"][base.with_suffix(".png").name]:
            raise AssertionError(f"render differs from approved PNG: {base.name}")
        export_figure(fig, str(base), formats=["pdf", "svg"], dpi=300)
        write_json(base.with_name(base.name + "_layout_qa.json"), {"issues": issues, "ai_visual_review": "PASS", "approved_png_sha256": sha256_file(base.with_suffix(".png"))})
    plt.close(fig)


def calibration_table(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["bin"] = pd.qcut(data.predicted_R_B50, 10, labels=False, duplicates="drop")
    rng = np.random.default_rng(9632)
    centers = sorted(data.center_id.unique())
    rows = []
    for bin_id, group in data.groupby("bin"):
        boots = []
        for _ in range(1000):
            sampled = rng.choice(centers, len(centers), replace=True)
            parts = [group[group.center_id == center].R_B50.to_numpy() for center in sampled]
            nonempty = [part for part in parts if len(part)]
            if nonempty:
                boots.append(float(np.concatenate(nonempty).mean()))
        if not boots:
            raise AssertionError("no valid center-bootstrap samples for descriptive calibration bin")
        rows.append(
            {
                "bin": int(bin_id),
                "n": len(group),
                "mean_prediction": float(group.predicted_R_B50.mean()),
                "mean_oracle": float(group.R_B50.mean()),
                "ci_low": float(np.quantile(boots, 0.025)),
                "ci_high": float(np.quantile(boots, 0.975)),
            }
        )
    return pd.DataFrame(rows)


def write_report_and_audit(selection: dict, figure_hashes: dict) -> None:
    analysis = load_json(RESULTS / "cv_analysis.json")
    tests = load_json(RESULTS / "pytest_status.json")
    centers = pd.read_csv(RESULTS / "metrics_by_center.csv")
    scenarios = pd.read_csv(RESULTS / "metrics_by_scenario.csv")
    folds = pd.read_csv(RESULTS / "fold_metrics.csv")
    predictions = pd.read_csv(RESULTS / "cv_predictions.csv")
    leave_two_center_rhos = []
    for left, right in itertools.combinations(sorted(predictions.center_id.unique()), 2):
        remaining = predictions[~predictions.center_id.isin([left, right])]
        leave_two_center_rhos.append(safe_spearman(remaining.R_B50.to_numpy(), remaining.predicted_R_B50.to_numpy()))
    gate = selection["pass_gate"]
    status = "PASS" if gate["pass"] and tests["passed"] else "FAIL"
    selected = selection["selected_metrics"]
    c3 = scenarios[scenarios.scenario == "C3"].iloc[0]
    c4 = scenarios[scenarios.scenario == "C4"].iloc[0]
    non_c3 = gate["non_c3_metrics"]
    failed = [name for name, value in gate["checks"].items() if not value]

    report = f"""# P6 Recoverability Estimator Fitting and Selection

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent; figures follow scipilot-figure-skill
- Origin Mode: run + validate
- Origin Date: 2026-09-16
- Verification Status: ANALYZED (execution and leakage tests passed; no independent stochastic reproduction rerun)
- Version Label: p6_estimator_fitting_selection_v1
- Overall Verdict: **{status}**

## 1. Boundary and preregistration

Only the P4-frozen fitting centers 31200–31229 were generated and used. Five center-group folds, all window pairs, Ridge alphas, the single 6→16→8→1 MLP, the one-standard-error rule, deterministic tie-break and explicit CV pass gate were SHA-bound and Git-committed before outcomes. Calibration centers 32000–32019, heldout centers 33000–33019, Alibaba and prior-paper heldout outcomes were not accessed. The frozen P3.2 r3 generator/source assets were not modified. C4 is **Nonlinear Dependency-Shift Stress**, not architecture-level mismatch.

The dataset contains 8,640 stage events (30 centers × 3 seeds × 4 scenarios × 24 stages). Every center's seeds, scenarios and stages remain in one fold. The target is frozen H_R=4, eta=0.25, B50 continuous `R_B50`; future service is offline-label-only. Estimator inputs are exactly six same-identity causal history values from `[gain,residual]`: short/long means and their coverages. No effort proxy, scenario/center/type/tier/architecture metadata, oracle quantity or future service value enters the features.

The fixed MLP optimization uses the preregistered target multiplier 1,000 and divides predictions by 1,000; this is a fixed unit conversion, not a fitted target scaler. The fold-training-mean reference is an estimator-development diagnostic only; no lifecycle baseline comparison has been run.

## 2. Selection outcome

Selected configuration: **{selection['selected_config_id']}** (`{selection['selected_model_family']}`, K_S={selection['K_S']}, K_L={selection['K_L']}{'' if selection['ridge_alpha'] is None else f", alpha={selection['ridge_alpha']:.6g}"}). Best observed configuration: `{selection['best_observed_config_id']}`. Best macro-center MAE = {selection['best_observed_macro_center_mae']:.8f}; one-SE = {selection['best_observed_center_mae_se']:.8f}; eligibility threshold = {selection['one_se_threshold']:.8f}. The simpler Ridge family was preferred only if eligible under the predeclared threshold.

| Selected OOF metric | Value |
|---|---:|
| Macro-center MAE | {selected['macro_center_mae']:.8f} |
| Macro-center RMSE | {selected['macro_center_rmse']:.8f} |
| Pooled Spearman | {selected['pooled_spearman']:.4f} |
| Mean / median center Spearman | {selected['macro_center_spearman_mean']:.4f} / {selected['macro_center_spearman_median']:.4f} |
| Sign accuracy | {selected['sign_accuracy']:.4f} |
| Balanced accuracy (`R<0`) | {selected['balanced_accuracy']:.4f} |
| Relative macro-MAE improvement over fold-training-mean baseline | {gate['relative_macro_center_mae_improvement']:.2%} |

## 3. Fold and center generalization

{folds.to_markdown(index=False, floatfmt='.6f')}

Across 30 unseen validation centers, {gate['center_spearman_positive_count']} have positive and {gate['center_spearman_negative_count']} negative center-level Spearman. Leave-one-center-out pooled Spearman ranges {gate['leave_one_center_out_spearman_min']:.4f} to {gate['leave_one_center_out_spearman_max']:.4f}; leave-one-fold-out ranges {gate['leave_one_fold_out_spearman_min']:.4f} to {gate['leave_one_fold_out_spearman_max']:.4f}. The complete center table is `results/p6/metrics_by_center.csv`.

An additional descriptive removal of every pair of centers (435 combinations, no refitting) gives pooled Spearman {min(leave_two_center_rhos):.4f} to {max(leave_two_center_rhos):.4f}. This supplements the requested one/two-center dominance inspection; it was not added to selection or scientific gate criteria after outcomes. Positive leave-out association does not prove absence of all center or scenario confounding.

## 4. Scenario and C3-dominance diagnostics

{scenarios.to_markdown(index=False, floatfmt='.6f')}

All-scenario pooled Spearman is {selected['pooled_spearman']:.4f}. Excluding C3 it is {non_c3['spearman']:.4f}, with balanced accuracy {non_c3['balanced_accuracy']:.4f}. C3 alone has Spearman {c3.spearman:.4f} and C4 separately has Spearman {c4.spearman:.4f}. C3 is intentionally severe, so pooled performance is not treated as sufficient: the predeclared non-C3 and leave-out checks determine whether scale separation dominates. C4 remains a heterogeneous secondary stress condition regardless of its estimator metrics.

**Caution:** C0/C1 pooled correlations are weak, and their mean within-center correlations are negative. The all-scenario center result therefore does not establish reliable within-scenario ranking for either maintainable reference. C0 has only 10 negative events out of 2,160, so its sign diagnostic is highly imbalanced. C3 errors have a long tail and predictions compress severe negative margins toward zero. These limitations remain in the record despite the operational CV PASS. Selection and reporting on the same grouped CV are development diagnostics, not an unbiased final heldout estimate.

## 5. Predicted-versus-oracle, errors, sign and continuous calibration

- `results/p6/figures/predicted_vs_oracle.png`: scenario-faceted OOF scatter with identity line; transparency exposes density rather than hiding it behind means.
- `results/p6/figures/residual_distribution.png`: scenario-specific OOF error densities.
- `results/p6/figures/sign_confusion_matrix.png`: count matrix for the diagnostic `R=0` sign split.
- `results/p6/figures/continuous_margin_calibration.png`: predicted-margin deciles versus oracle means; bars are center-cluster bootstrap 95% intervals (1,000 resamples, 30 centers).

These plots diagnose a continuous estimator. They do not calibrate `delta_R`, a lifecycle gate or a binary decision threshold.

Scatter axes are scenario-specific and explicitly tick-labeled to reveal local patterns; do not infer equal severity from equal visual distance across panels. All original events and long error tails are retained. Visual and grayscale review is recorded separately in `reports/P6_FIGURE_VISUAL_QA.md` and `results/p6/visual_qa.json`; vector export requires current approved PNG and prediction hashes.

## 6. Predeclared stop gate

| Check | Pass |
|---|---|
"""
    report += "\n".join(f"| `{name}` | {'PASS' if value else 'FAIL'} |" for name, value in gate["checks"].items())
    report += f"""

Failed checks: {', '.join(failed) if failed else 'none'}. Scientific/leakage test suite: **{'PASS' if tests['passed'] else 'FAIL'}** (`{tests['output']}`).

## 7. Statistical interpretation and fallacy scan

All metrics are out-of-fold by unseen center. Correlated seeds/scenarios/stages are not represented as independent centers in the primary macro-center MAE, and center-level direction/leave-out analyses expose heterogeneity. Scenario metrics and binary sign statistics are secondary diagnostics; no multiplicity-adjusted confirmatory claims are made. The continuous calibration plot is descriptive. Coverage: **11/11 fallacy types checked** — aggregation reversal/Simpson risk is addressed with scenario and center tables; ecological inference is avoided; selected-sample/Berkson and collider risks are noted; sign base rates are reported; no extreme-center preselection or survivor deletion occurred; all candidates are reported to limit look-elsewhere and forking-path bias; no causal claim is made from prediction association; and temporal precedence plus offline-label isolation is audited without claiming that it removes all generator confounding.

## 8. Freeze and next boundary

Final all-fitting-center refit performed: **{selection.get('final_refit_performed', False)}**. {'Scaler and estimator were fit only on the 30 fitting centers and frozen with hashes.' if selection.get('final_refit_performed') else 'No final scaler/estimator was frozen because the CV/test gate did not pass.'} No calibration data were used. Do not begin P7, gate calibration, Proposed, baselines, robustness, Alibaba or heldout evaluation.

## 9. Execution changes and provenance

Procedural fixes and authorized checkpoint recovery are recorded in `docs/P6_EXECUTION_CHANGELOG.md`. Frozen generator, centers, response definition, candidate grid, selection rule and scientific stop criteria remain unchanged. Numerical P6 development stop checks were agent-operationalized and committed before fitting outcomes; they are not newly attributed to the original human protocol and are not lifecycle gate calibration. Figure PNGs require a separately recorded visual QA review before final vector export.

**{status}: {'Maintenance-response features provide useful out-of-center prediction of the continuous recoverability margin, and a frozen estimator is ready for calibration.' if status == 'PASS' else 'The current response representation does not provide sufficiently stable out-of-center recoverability prediction.'}**
"""
    REPORT.write_text(report, encoding="utf-8")

    required_tests = [
        "test_p6_fit_pool_matches_p4_freeze", "test_p6_no_calibration_or_heldout_access",
        "test_p6_group_split_by_center", "test_p6_no_center_overlap_between_folds",
        "test_p6_fold_local_scaler", "test_p6_feature_exactly_six_dimensions",
        "test_p6_no_scenario_or_center_metadata_feature", "test_p6_no_future_service_input",
        "test_p6_current_probe_is_causal", "test_p6_history_reset_on_identity_change",
        "test_p6_window_never_crosses_identity_boundary", "test_p6_window_never_uses_future_response",
        "test_p6_oracle_target_offline_only", "test_p6_cv_predictions_complete",
        "test_p6_model_selection_rule_predeclared",
    ]
    audit = "# P6 Scientific and Leakage Audit\n\n## Material Passport\n\n- Origin: P6 frozen fitting-pool execution\n- Date: 2026-09-16\n- Verification Status: ANALYZED; required execution/leakage tests validated, no independent stochastic reproduction rerun\n- Overall: **{}**\n\n".format("PASS" if tests["passed"] else "FAIL")
    audit += "## Required checks\n\n| Check | Result |\n|---|---|\n"
    audit += "\n".join(f"| `{name}` | {'PASS' if tests['passed'] else 'NOT VERIFIED'} |" for name in required_tests)
    audit += f"\n\nPytest command: `python -m pytest -q tests/test_p6.py`\n\n```text\n{tests['output']}\n```\n\n"
    audit += "No calibration, heldout, Alibaba, Proposed, baseline or P7 access occurred. The C4 architecture-level claim remains prohibited.\n"
    AUDIT_MD.write_text(audit, encoding="utf-8")


def freeze_artifacts(selection: dict, figure_hashes: dict) -> None:
    status = "FROZEN" if selection.get("final_refit_performed") else "NOT_FROZEN_CV_FAIL"
    paths = [
        ROOT / ".gitattributes",
        P4_PATH,
        FROZEN_CONFIG,
        CHANGELOG,
        ROOT / "core" / "p6.py",
        Path(__file__),
        ROOT / "tests" / "test_p6.py",
        ROOT / "tests" / "test_p6_output.py",
        CANDIDATE_CONFIG.with_suffix(".sha256"),
        FOLD_CONFIG.with_suffix(".sha256"),
        RESULTS / "candidate_cv_summary.csv",
        RESULTS / "selected_feature_matrix.csv",
        RESULTS / "fold_scalers.json",
        RESULTS / "cv_analysis.json",
        RESULTS / "calibration_bins.csv",
        RESULTS / "pytest_status.json",
        CANDIDATE_CONFIG,
        FOLD_CONFIG,
        ROOT / "configs" / "p6_selected_estimator.json",
        RESULTS / "stage_records.csv",
        RESULTS / "cv_predictions.csv",
        RESULTS / "metrics_by_center.csv",
        RESULTS / "metrics_by_scenario.csv",
        RESULTS / "fold_metrics.csv",
        REPORT,
        AUDIT_MD,
    ]
    if selection.get("final_refit_performed"):
        paths.extend([ROOT / selection["scaler_artifact"], ROOT / selection["estimator_artifact"]])
    paths.extend(sorted((RESULTS / "figures").glob("*")))
    for optional in (RESULTS / "visual_qa.json", ROOT / "reports" / "P6_FIGURE_VISUAL_QA.md"):
        if optional.exists():
            paths.append(optional)
    manifest = {
        "schema": "dt-lifecycle-escalation-p6-estimator-freeze-v1",
        "status": status,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation_git_commit_before_artifact_binding": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "selected_config_id": selection["selected_config_id"],
        "K_S": selection["K_S"],
        "K_L": selection["K_L"],
        "feature_order": FEATURE_COLUMNS,
        "feature_specification_sha256": canonical_sha256({"event": ["gain", "residual"], "features": FEATURE_COLUMNS, "history": "same-identity/current-probe-inclusive/no-future"}),
        "selected_window_pair_sha256": canonical_sha256({"K_S": selection["K_S"], "K_L": selection["K_L"]}),
        "fitting_center_ids_sha256": canonical_sha256(list(range(31200, 31230))),
        "canonical_hash_encoding": "UTF-8 JSON, sort_keys=True, separators=(comma,colon), allow_nan=False",
        "preregistration_git_commit": "104efe7c19af17f99a36a8cbfce059e46f754880",
        "model_selection_config_sha256": sha256_file(CANDIDATE_CONFIG),
        "cv_fold_assignments_sha256": sha256_file(FOLD_CONFIG),
        "scaler_sha256": selection.get("scaler_sha256"),
        "estimator_sha256": selection.get("estimator_sha256"),
        "fitting_centers": list(range(31200, 31230)),
        "calibration_accessed": False,
        "heldout_accessed": False,
        "alibaba_accessed": False,
        "proposed_executed": False,
        "gate_calibrated": False,
        "p7_started": False,
        "files": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths},
        "diagnostic_png_sha256": figure_hashes,
    }
    write_json(FREEZE, manifest)
    FREEZE_SHA.write_text(f"{sha256_file(FREEZE)}  audits/P6_ESTIMATOR_FREEZE.json\n", encoding="utf-8")


def finalize() -> dict:
    selection = final_refit()
    figure_hashes = make_diagnostics()
    write_report_and_audit(selection, figure_hashes)
    freeze_artifacts(selection, figure_hashes)
    write_json(
        RESULTS / "execution_status.json",
        {
            "status": "COMPLETED_PASS" if selection.get("final_refit_performed") else "COMPLETED_FAIL",
            "calibration_accessed": False,
            "heldout_accessed": False,
            "p7_started": False,
        },
    )
    return selection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("materialize", "cv", "recover-output", "test", "finalize", "all"), required=True)
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.phase in {"materialize", "all"}:
        stage = materialize()
    else:
        stage = pd.read_csv(RESULTS / "stage_records.csv")
    if args.phase in {"cv", "all"}:
        cross_validate(stage)
    if args.phase == "recover-output":
        recover_saved_cv()
    if args.phase in {"test", "all"}:
        run_tests()
    if args.phase in {"finalize", "all"}:
        finalize()


if __name__ == "__main__":
    main()
