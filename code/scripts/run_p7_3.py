from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import pearsonr, spearmanr


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "p7_3"
FIGURES = RESULTS / "figures"
REPORT = ROOT / "reports" / "P7_3_ROOT_CAUSE_AUDIT.md"
AUDIT = ROOT / "audits" / "P7_3_READ_ONLY_AUDIT.json"
P6_FREEZE = ROOT / "audits" / "P6_ESTIMATOR_FREEZE.json"
P7_FREEZE = ROOT / "audits" / "P7_CALIBRATION_FREEZE.json"
P7_1_REPORT = ROOT / "reports" / "P7_1_GATE_UTILITY_FORENSIC.md"
P7_2_GATE_FREEZE = ROOT / "audits" / "P7_2_GATE_FREEZE.json"
P7_2_FINAL_FREEZE = ROOT / "audits" / "P7_2_FINAL_CALIBRATION_FREEZE.json"
P7_2_POOLS = ROOT / "configs" / "p7_2_fresh_center_pools.json"
P7_2_SELECTED_GATE = ROOT / "configs" / "p7_2_selected_gate.json"
P7_2_SELECTED_ACTION = ROOT / "configs" / "p7_2_selected_action_params.json"
P7_GRID = ROOT / "configs" / "p7_delta_grid.json"

K_S = 2
K_L = 6
EPS = 1e-12
PALETTE = {"P6-OOF": "#0072B2", "GateCal-v2": "#E69F00", "ActionCal-v2": "#009E73"}
MARKERS = {"P6-OOF": "o", "GateCal-v2": "s", "ActionCal-v2": "^"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.15g")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_spearman(x: pd.Series, y: pd.Series) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 3 or x[mask].nunique() < 2 or y[mask].nunique() < 2:
        return math.nan
    return float(spearmanr(x[mask].to_numpy(), y[mask].to_numpy()).statistic)


def safe_pearson(x: pd.Series, y: pd.Series) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 3 or x[mask].nunique() < 2 or y[mask].nunique() < 2:
        return math.nan
    return float(pearsonr(x[mask].to_numpy(), y[mask].to_numpy()).statistic)


def confusion(frame: pd.DataFrame, threshold: float) -> dict[str, float]:
    truth = frame["R_B50"].to_numpy() < 0.0
    pred = frame["R_hat"].to_numpy() < threshold
    tp = int(np.sum(truth & pred))
    fn = int(np.sum(truth & ~pred))
    tn = int(np.sum(~truth & ~pred))
    fp = int(np.sum(~truth & pred))
    tpr = tp / (tp + fn) if tp + fn else math.nan
    tnr = tn / (tn + fp) if tn + fp else math.nan
    ba = np.nanmean([tpr, tnr]) if not (math.isnan(tpr) and math.isnan(tnr)) else math.nan
    return {
        "TP": tp,
        "FN": fn,
        "TN": tn,
        "FP": fp,
        "TPR": tpr,
        "TNR": tnr,
        "balanced_sign_accuracy": float(ba),
        "sign_accuracy": float(np.mean(truth == pred)),
        "false_admission_rate": fp / (fp + tn) if fp + tn else math.nan,
        "missed_admission_rate": fn / (fn + tp) if fn + tp else math.nan,
        "gate_open_rate": float(np.mean(pred)),
        "negative_prevalence": float(np.mean(truth)),
    }


def metric_row(frame: pd.DataFrame, threshold: float = 0.0) -> dict[str, float]:
    error = frame["R_hat"] - frame["R_B50"]
    row = {
        "n": int(len(frame)),
        "MAE": float(error.abs().mean()),
        "RMSE": float(np.sqrt(np.mean(np.square(error)))),
        "Spearman": safe_spearman(frame["R_hat"], frame["R_B50"]),
        "Pearson_descriptive": safe_pearson(frame["R_hat"], frame["R_B50"]),
        "mean_prediction_error": float(error.mean()),
        "median_prediction_error": float(error.median()),
        "oracle_SD": float(frame["R_B50"].std(ddof=1)),
        "prediction_SD": float(frame["R_hat"].std(ddof=1)),
    }
    row["spread_ratio_prediction_to_oracle"] = (
        row["prediction_SD"] / row["oracle_SD"] if row["oracle_SD"] > EPS else math.nan
    )
    row.update(confusion(frame, threshold))
    return row


def bootstrap_center_mean(center_metrics: pd.DataFrame, column: str, seed: int) -> tuple[float, float]:
    values = center_metrics[column].dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(5000, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def rolling_features(frame: pd.DataFrame, use_recorded_history: bool) -> pd.DataFrame:
    rows: list[dict] = []
    keys = ["center_id", "seed", "scenario"]
    for _, group in frame.sort_values(keys + ["stage"]).groupby(keys, sort=False):
        history: list[tuple[float, float]] = []
        prior_identity: str | None = None
        for record in group.to_dict("records"):
            identity = str(record["model_identity"])
            recorded = int(record["identity_age"]) if use_recorded_history else None
            if use_recorded_history:
                if recorded == 1:
                    history = []
            elif prior_identity is None or identity != prior_identity:
                history = []
            history.append((float(record["probe_gain"]), float(record["probe_residual"])))
            if use_recorded_history and len(history) != recorded:
                raise AssertionError("recorded history size is inconsistent with saved action path")
            short = np.asarray(history[-K_S:], dtype=float)
            long = np.asarray(history[-K_L:], dtype=float)
            record.update(
                {
                    "identity_age": len(history),
                    "mean_gain_short": float(short[:, 0].mean()),
                    "mean_residual_short": float(short[:, 1].mean()),
                    "mean_gain_long": float(long[:, 0].mean()),
                    "mean_residual_long": float(long[:, 1].mean()),
                    "coverage_short": float(len(short) / K_S),
                    "coverage_long": float(len(long) / K_L),
                }
            )
            rows.append(record)
            prior_identity = identity
    return pd.DataFrame(rows)


def load_p6() -> pd.DataFrame:
    features = pd.read_csv(ROOT / "results" / "p6" / "selected_feature_matrix.csv")
    predictions = pd.read_csv(ROOT / "results" / "p6" / "cv_predictions.csv")
    keys = ["center_id", "seed", "scenario", "stage"]
    pred = predictions[keys + ["predicted_R_B50", "fold"]].copy()
    merged = features.merge(pred, on=keys, how="inner", validate="one_to_one", suffixes=("", "_pred"))
    if len(merged) != len(features) or len(merged) != len(predictions):
        raise AssertionError("P6 OOF merge is incomplete")
    out = pd.DataFrame(
        {
            "pool": "P6-OOF",
            "center_id": merged.center_id.astype(int),
            "seed": merged.seed.astype(int),
            "scenario": merged.scenario,
            "stage": merged.stage.astype(int),
            "model_identity": merged.identity_id,
            "identity_age": merged.history_size.astype(int),
            "center_type": merged.center_type,
            "deployment_tier": merged.deployment_tier,
            "R_hat": merged.predicted_R_B50.astype(float),
            "R_B50": merged.R_B50.astype(float),
            "tau_service": merged.tau_service.astype(float),
            "pre_assessment_loss": merged.probe_pre_assess_loss.astype(float),
            "probe_gain": merged.probe_gain.astype(float),
            "probe_residual": merged.probe_residual.astype(float),
            "mean_gain_short": merged.mean_gain_short.astype(float),
            "mean_residual_short": merged.mean_residual_short.astype(float),
            "mean_gain_long": merged.mean_gain_long.astype(float),
            "mean_residual_long": merged.mean_residual_long.astype(float),
            "coverage_short": merged.coverage_short.astype(float),
            "coverage_long": merged.coverage_long.astype(float),
            "fold": merged.fold_pred.astype(int) if "fold_pred" in merged else merged.fold.astype(int),
            "source_path_class": "results/p6 selected_feature_matrix + cv_predictions",
        }
    )
    return out


def load_gatecal() -> pd.DataFrame:
    paths = sorted((ROOT / "results" / "p7_2" / "raw" / "gatecal").glob("*.csv"))
    if len(paths) != 144:
        raise AssertionError(f"GateCal-v2 raw count mismatch: {len(paths)}")
    raw = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    if len(raw) != 3456 or raw.duplicated(["center_id", "seed", "scenario", "stage"]).any():
        raise AssertionError("GateCal-v2 stage table is not exactly 3456 unique stages")
    base = pd.DataFrame(
        {
            "pool": "GateCal-v2",
            "center_id": raw.center_id.astype(int),
            "seed": raw.seed.astype(int),
            "scenario": raw.scenario,
            "stage": raw.stage.astype(int),
            "model_identity": raw.identity_id,
            "identity_age": 0,
            "center_type": raw.center_type,
            "deployment_tier": raw.deployment_tier,
            "R_hat": raw.predicted_R.astype(float),
            "R_B50": raw.R_B50.astype(float),
            "tau_service": raw.tau_service.astype(float),
            "pre_assessment_loss": raw.probe_pre_assess_loss.astype(float),
            "probe_gain": raw.probe_gain.astype(float),
            "probe_residual": raw.probe_residual.astype(float),
            "fold": np.nan,
            "source_path_class": "results/p7_2/raw/gatecal",
        }
    )
    return rolling_features(base, use_recorded_history=False)


def load_actioncal(config_id: str) -> pd.DataFrame:
    paths = sorted((ROOT / "results" / "p7_2" / "raw" / "actioncal").glob("*.csv"))
    if len(paths) != 144:
        raise AssertionError(f"ActionCal-v2 raw count mismatch: {len(paths)}")
    usecols = [
        "config_id", "center_id", "seed", "scenario", "stage", "identity_before", "center_type",
        "deployment_tier", "predicted_R", "R_B50", "tau_service", "pre_assessment_mse",
        "probe_gain", "probe_residual", "history_size",
    ]
    parts = []
    for path in paths:
        frame = pd.read_csv(path, usecols=usecols)
        parts.append(frame[frame.config_id == config_id])
    raw = pd.concat(parts, ignore_index=True)
    if len(raw) != 3456 or raw.duplicated(["center_id", "seed", "scenario", "stage"]).any():
        raise AssertionError("selected ActionCal-v2 path is not exactly 3456 unique stages")
    base = pd.DataFrame(
        {
            "pool": "ActionCal-v2",
            "center_id": raw.center_id.astype(int),
            "seed": raw.seed.astype(int),
            "scenario": raw.scenario,
            "stage": raw.stage.astype(int),
            "model_identity": raw.identity_before,
            "identity_age": raw.history_size.astype(int),
            "center_type": raw.center_type,
            "deployment_tier": raw.deployment_tier,
            "R_hat": raw.predicted_R.astype(float),
            "R_B50": raw.R_B50.astype(float),
            "tau_service": raw.tau_service.astype(float),
            "pre_assessment_loss": raw.pre_assessment_mse.astype(float),
            "probe_gain": raw.probe_gain.astype(float),
            "probe_residual": raw.probe_residual.astype(float),
            "fold": np.nan,
            "source_path_class": f"results/p7_2/raw/actioncal::{config_id}",
        }
    )
    return rolling_features(base, use_recorded_history=True)


def attach_diagnostics(frame: pd.DataFrame, delta: float) -> pd.DataFrame:
    out = frame.copy()
    out["oracle_sign"] = np.where(out.R_B50 < 0, "R_B50<0", "R_B50>=0")
    out["prediction_error"] = out.R_hat - out.R_B50
    out["absolute_error"] = out.prediction_error.abs()
    out["zero_sign_prediction"] = np.where(out.R_hat < 0, "negative", "nonnegative")
    out["frozen_gate_open"] = (out.R_hat < delta).astype(int)
    out["frozen_gate_error"] = np.select(
        [
            (out.R_B50 < 0) & (out.frozen_gate_open == 1),
            (out.R_B50 < 0) & (out.frozen_gate_open == 0),
            (out.R_B50 >= 0) & (out.frozen_gate_open == 0),
        ],
        ["true_admission", "missed_admission", "true_rejection"],
        default="false_admission",
    )
    out["history_coverage_bin"] = pd.cut(
        out.coverage_long,
        bins=[-np.inf, 0.5, 1.0, np.inf],
        right=False,
        labels=["coverage<0.5", "0.5<=coverage<1", "full_coverage"],
    ).astype(str)
    out["identity_age_bin"] = pd.cut(
        out.identity_age,
        bins=[0, 2, 5, np.inf],
        right=True,
        labels=["events_1_2", "events_3_5", "events_6_plus"],
    ).astype(str)
    out["R_rel_tau"] = out.R_B50 / (out.tau_service.abs() + EPS)
    out["R_hat_rel_tau"] = out.R_hat / (out.tau_service.abs() + EPS)
    for pool, pool_idx in out.groupby("pool").groups.items():
        pool_frame = out.loc[pool_idx]
        for _, idx in pool_frame.groupby("center_id").groups.items():
            oracle = out.loc[idx, "R_B50"]
            pred = out.loc[idx, "R_hat"]
            oracle_scale = float(oracle.quantile(0.75) - oracle.quantile(0.25))
            pred_scale = float(pred.quantile(0.75) - pred.quantile(0.25))
            if oracle_scale <= EPS:
                oracle_scale = max(float(oracle.std(ddof=0)), EPS)
            if pred_scale <= EPS:
                pred_scale = max(float(pred.std(ddof=0)), EPS)
            out.loc[idx, "R_center_z"] = (oracle - float(oracle.median())) / oracle_scale
            out.loc[idx, "R_hat_center_z"] = (pred - float(pred.median())) / pred_scale
    return out


def verify_frozen_inputs() -> tuple[dict, dict]:
    p6 = read_json(P6_FREEZE)
    gate = read_json(P7_2_GATE_FREEZE)
    final = read_json(P7_2_FINAL_FREEZE)
    if final["status"] != "FAIL":
        raise AssertionError("P7.2 FAIL is not preserved")
    if sha256_file(ROOT / "artifacts" / "p6_recoverability_estimator.pt") != p6["estimator_sha256"]:
        raise AssertionError("P6 estimator hash mismatch")
    if sha256_file(ROOT / "artifacts" / "p6_recoverability_scaler.json") != p6["scaler_sha256"]:
        raise AssertionError("P6 scaler hash mismatch")
    if (p6["K_S"], p6["K_L"]) != (K_S, K_L):
        raise AssertionError("K_S/K_L changed")
    expected_features = [
        "mean_gain_short", "mean_residual_short", "mean_gain_long", "mean_residual_long",
        "coverage_short", "coverage_long",
    ]
    if p6["feature_order"] != expected_features:
        raise AssertionError("feature specification changed")
    for rel, expected in gate["raw_gatecal_hashes"].items():
        if sha256_file(ROOT / rel) != expected:
            raise AssertionError(f"GateCal raw hash mismatch: {rel}")
    for rel, expected in final["raw_actioncal_hashes"].items():
        if sha256_file(ROOT / rel) != expected:
            raise AssertionError(f"ActionCal raw hash mismatch: {rel}")
    tracked = {
        "P6_estimator": sha256_file(ROOT / "artifacts" / "p6_recoverability_estimator.pt"),
        "P6_scaler": sha256_file(ROOT / "artifacts" / "p6_recoverability_scaler.json"),
        "P6_freeze": sha256_file(P6_FREEZE),
        "P7_freeze": sha256_file(P7_FREEZE),
        "P7_1_report": sha256_file(P7_1_REPORT),
        "P7_2_gate_freeze": sha256_file(P7_2_GATE_FREEZE),
        "P7_2_final_freeze": sha256_file(P7_2_FINAL_FREEZE),
    }
    raw = {**gate["raw_gatecal_hashes"], **final["raw_actioncal_hashes"]}
    return tracked, raw


def center_metrics(common: pd.DataFrame, delta: float) -> pd.DataFrame:
    rows = []
    for (pool, center), group in common.groupby(["pool", "center_id"], sort=True):
        zero = metric_row(group, 0.0)
        frozen = confusion(group, delta)
        row = {
            "pool": pool,
            "center_id": int(center),
            "center_type": group.center_type.iloc[0],
            "deployment_tier": group.deployment_tier.iloc[0],
            **{f"zero_{key}": value for key, value in zero.items()},
            **{f"frozen_{key}": value for key, value in frozen.items()},
        }
        rows.append(row)
    result = pd.DataFrame(rows)
    for pool, idx in result.groupby("pool").groups.items():
        pool_common = common[common.pool == pool]
        base = confusion(pool_common, delta)["balanced_sign_accuracy"]
        for i in idx:
            center = result.loc[i, "center_id"]
            without = pool_common[pool_common.center_id != center]
            result.loc[i, "frozen_pooled_BA_without_center"] = confusion(without, delta)["balanced_sign_accuracy"]
            result.loc[i, "frozen_pooled_BA_change_when_removed"] = (
                result.loc[i, "frozen_pooled_BA_without_center"] - base
            )
    return result


def transport_summary(common: pd.DataFrame, centers: pd.DataFrame, delta: float) -> pd.DataFrame:
    rows = []
    for pool, group in common.groupby("pool", sort=False):
        pooled = metric_row(group, 0.0)
        c = centers[centers.pool == pool]
        frozen = confusion(group, delta)
        loo_spearman = []
        loo_mae = []
        for center in sorted(group.center_id.unique()):
            without = group[group.center_id != center]
            loo_spearman.append(safe_spearman(without.R_hat, without.R_B50))
            loo_mae.append(float((without.R_hat - without.R_B50).abs().mean()))
        ci_s = bootstrap_center_mean(c, "zero_Spearman", seed=7311 + len(rows))
        ci_ba = bootstrap_center_mean(c, "zero_balanced_sign_accuracy", seed=7411 + len(rows))
        row = {
            "pool": pool,
            **pooled,
            "macro_center_MAE": float(c.zero_MAE.mean()),
            "macro_center_RMSE": float(c.zero_RMSE.mean()),
            "mean_center_Spearman": float(c.zero_Spearman.mean()),
            "median_center_Spearman": float(c.zero_Spearman.median()),
            "positive_Spearman_centers": int((c.zero_Spearman > 0).sum()),
            "Spearman_defined_centers": int(c.zero_Spearman.notna().sum()),
            "positive_Spearman_fraction": float((c.zero_Spearman > 0).sum() / c.zero_Spearman.notna().sum()),
            "mean_center_Spearman_bootstrap_CI_low": ci_s[0],
            "mean_center_Spearman_bootstrap_CI_high": ci_s[1],
            "mean_center_zero_BA": float(c.zero_balanced_sign_accuracy.mean()),
            "mean_center_zero_BA_bootstrap_CI_low": ci_ba[0],
            "mean_center_zero_BA_bootstrap_CI_high": ci_ba[1],
            "leave_one_center_pooled_Spearman_min": float(np.nanmin(loo_spearman)),
            "leave_one_center_pooled_Spearman_max": float(np.nanmax(loo_spearman)),
            "leave_one_center_pooled_MAE_min": float(np.nanmin(loo_mae)),
            "leave_one_center_pooled_MAE_max": float(np.nanmax(loo_mae)),
            "frozen_delta_R": delta,
            "frozen_macro_TPR": float(c.frozen_TPR.mean()),
            "frozen_macro_TNR": float(c.frozen_TNR.mean()),
            "frozen_macro_balanced_sign_accuracy": float(c.frozen_balanced_sign_accuracy.mean()),
            "frozen_macro_false_admission_rate": float(c.frozen_false_admission_rate.mean()),
            "frozen_macro_missed_admission_rate": float(c.frozen_missed_admission_rate.mean()),
            **{f"frozen_{key}": value for key, value in frozen.items()},
            "POSTHOC_R_rel_tau_Spearman": safe_spearman(group.R_hat_rel_tau, group.R_rel_tau),
            "POSTHOC_R_rel_tau_MAE": float((group.R_hat_rel_tau - group.R_rel_tau).abs().mean()),
            "POSTHOC_center_z_Spearman": safe_spearman(group.R_hat_center_z, group.R_center_z),
            "POSTHOC_center_z_zero_BA": confusion(
                group.rename(columns={"R_center_z": "_oracle", "R_hat_center_z": "_pred"})
                .assign(R_B50=lambda x: x._oracle, R_hat=lambda x: x._pred),
                0.0,
            )["balanced_sign_accuracy"],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def select_diagnosis(transport: pd.DataFrame) -> tuple[str, str | None]:
    indexed = transport.set_index("pool")
    fresh = indexed.loc[["GateCal-v2", "ActionCal-v2"]]
    pooled_collapsed = fresh.Spearman.le(0.05).all()
    center_transport_consistent = (
        fresh.mean_center_Spearman.gt(0).all()
        and fresh.positive_Spearman_fraction.ge(0.5).all()
    )
    if pooled_collapsed:
        return "D1_CONTINUOUS_ESTIMATOR_TRANSPORT_FAILURE", None
    if center_transport_consistent:
        return "D2_ABSOLUTE_THRESHOLD_TRANSPORT_FAILURE", "D4_CENTER_SCALE_HETEROGENEITY_DOMINATES"
    return "D6_MIXED_OR_INCONCLUSIVE", None


def scenario_metrics(common: pd.DataFrame, delta: float) -> pd.DataFrame:
    rows = []
    for pool, pool_frame in common.groupby("pool", sort=False):
        groups: list[tuple[str, pd.DataFrame]] = [(s, g) for s, g in pool_frame.groupby("scenario", sort=True)]
        groups.append(("non-C3", pool_frame[pool_frame.scenario != "C3"]))
        for label, group in groups:
            zero = metric_row(group, 0.0)
            frozen = confusion(group, delta)
            rows.append(
                {
                    "pool": pool,
                    "scenario_group": label,
                    **{f"zero_{key}": value for key, value in zero.items()},
                    **{f"frozen_{key}": value for key, value in frozen.items()},
                }
            )
    return pd.DataFrame(rows)


def distribution_summary(common: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dimensions = [
        ("overall", []),
        ("center", ["center_id"]),
        ("scenario", ["scenario"]),
        ("center_type", ["center_type"]),
        ("deployment_tier", ["deployment_tier"]),
    ]
    variables = ["R_B50", "R_hat", "prediction_error"]
    for pool, pool_frame in common.groupby("pool", sort=False):
        for level, keys in dimensions:
            grouped: Iterable[tuple[object, pd.DataFrame]]
            if keys:
                grouped = pool_frame.groupby(keys[0], sort=True)
            else:
                grouped = [("all", pool_frame)]
            for value, group in grouped:
                for variable in variables:
                    x = group[variable]
                    rows.append(
                        {
                            "pool": pool,
                            "group_level": level,
                            "group_value": value,
                            "variable": variable,
                            "n": len(x),
                            "mean": float(x.mean()),
                            "median": float(x.median()),
                            "SD": float(x.std(ddof=1)),
                            "IQR": float(x.quantile(0.75) - x.quantile(0.25)),
                            "p05": float(x.quantile(0.05)),
                            "p25": float(x.quantile(0.25)),
                            "p50": float(x.quantile(0.50)),
                            "p75": float(x.quantile(0.75)),
                            "p95": float(x.quantile(0.95)),
                            "negative_prevalence": float((group.R_B50 < 0).mean()),
                        }
                    )
    return pd.DataFrame(rows)


def center_scale_summary(common: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pool, center), group in common.groupby(["pool", "center_id"], sort=True):
        oracle_iqr = float(group.R_B50.quantile(0.75) - group.R_B50.quantile(0.25))
        rows.append(
            {
                "row_type": "center",
                "pool": pool,
                "center_id": int(center),
                "center_type": group.center_type.iloc[0],
                "deployment_tier": group.deployment_tier.iloc[0],
                "n": len(group),
                "median_abs_R_B50": float(group.R_B50.abs().median()),
                "IQR_R_B50": oracle_iqr,
                "SD_R_B50": float(group.R_B50.std(ddof=1)),
                "median_residual_feature": float(group.mean_residual_long.median()),
                "median_pre_action_assessment_loss": float(group.pre_assessment_loss.median()),
                "median_tau_service": float(group.tau_service.median()),
                "median_prediction_error": float(group.prediction_error.median()),
                "POSTHOC_tau_relative_oracle_IQR": float(
                    group.R_rel_tau.quantile(0.75) - group.R_rel_tau.quantile(0.25)
                ),
                "POSTHOC_center_z_oracle_IQR": float(
                    group.R_center_z.quantile(0.75) - group.R_center_z.quantile(0.25)
                ),
            }
        )
    result = pd.DataFrame(rows)
    summaries = []
    for pool, group in result.groupby("pool", sort=False):
        summary = {"row_type": "pool_cross_center_variation", "pool": pool, "center_id": "ALL"}
        for column in [
            "median_abs_R_B50", "IQR_R_B50", "SD_R_B50", "median_residual_feature",
            "median_pre_action_assessment_loss", "median_tau_service",
        ]:
            positive = group.loc[group[column] > EPS, column]
            summary[f"{column}_min_positive"] = float(positive.min()) if len(positive) else math.nan
            summary[f"{column}_max"] = float(group[column].max())
            summary[f"{column}_max_min_ratio"] = (
                float(group[column].max() / positive.min()) if len(positive) else math.nan
            )
            q25 = float(group[column].quantile(0.25))
            q75 = float(group[column].quantile(0.75))
            summary[f"{column}_robust_high_low_ratio"] = q75 / q25 if abs(q25) > EPS else math.nan
        summaries.append(summary)
    return pd.concat([result, pd.DataFrame(summaries)], ignore_index=True, sort=False)


def rank_sign_summary(centers: pd.DataFrame) -> pd.DataFrame:
    result = centers[
        [
            "pool", "center_id", "center_type", "deployment_tier", "zero_n", "zero_Spearman",
            "zero_balanced_sign_accuracy", "frozen_balanced_sign_accuracy", "zero_median_prediction_error",
            "zero_spread_ratio_prediction_to_oracle", "frozen_TP", "frozen_FN", "frozen_TN", "frozen_FP",
        ]
    ].copy()
    conditions = [
        result.zero_Spearman.isna()
        | result.zero_balanced_sign_accuracy.isna()
        | ((result.frozen_TP + result.frozen_FN) == 0)
        | ((result.frozen_TN + result.frozen_FP) == 0),
        (result.zero_Spearman > 0) & (result.zero_balanced_sign_accuracy > 0.5),
        (result.zero_Spearman > 0) & (result.zero_balanced_sign_accuracy <= 0.5),
    ]
    result["directional_taxonomy"] = np.select(
        conditions,
        ["undefined / insufficient class support", "good rank / good sign", "good rank / poor sign"],
        default="poor rank / poor sign",
    )
    result["taxonomy_note"] = "descriptive directional anchors only: Spearman>0 and BA>0.5; not a PASS rule"
    return result


def history_summary(common: pd.DataFrame, delta: float) -> pd.DataFrame:
    rows = []
    for pool, pool_frame in common.groupby("pool", sort=False):
        for kind, column, order in [
            ("coverage", "history_coverage_bin", ["coverage<0.5", "0.5<=coverage<1", "full_coverage"]),
            ("identity_age", "identity_age_bin", ["events_1_2", "events_3_5", "events_6_plus"]),
        ]:
            for label in order:
                group = pool_frame[pool_frame[column] == label]
                if group.empty:
                    continue
                frozen = confusion(group, delta)
                rows.append(
                    {
                        "pool": pool,
                        "stratification": kind,
                        "bin": label,
                        "n": len(group),
                        "Spearman": safe_spearman(group.R_hat, group.R_B50),
                        "zero_balanced_sign_accuracy": confusion(group, 0.0)["balanced_sign_accuracy"],
                        "frozen_balanced_sign_accuracy": frozen["balanced_sign_accuracy"],
                        "frozen_false_admission_rate": frozen["false_admission_rate"],
                        "frozen_missed_admission_rate": frozen["missed_admission_rate"],
                        "negative_prevalence": frozen["negative_prevalence"],
                    }
                )
    return pd.DataFrame(rows)


def near_zero_summary(common: pd.DataFrame, scale: float) -> pd.DataFrame:
    rows = []
    for (pool, center), group in common.groupby(["pool", "center_id"], sort=True):
        for multiplier in [0.25, 0.5, 1.0]:
            rows.append(
                {
                    "aggregation": "center",
                    "pool": pool,
                    "center_id": int(center),
                    "scale_s": scale,
                    "multiplier": multiplier,
                    "absolute_margin_bound": multiplier * scale,
                    "n": len(group),
                    "fraction_near_zero": float((group.R_B50.abs() <= multiplier * scale).mean()),
                }
            )
    for pool, group in common.groupby("pool", sort=False):
        for multiplier in [0.25, 0.5, 1.0]:
            rows.append(
                {
                    "aggregation": "pool",
                    "pool": pool,
                    "center_id": "ALL",
                    "scale_s": scale,
                    "multiplier": multiplier,
                    "absolute_margin_bound": multiplier * scale,
                    "n": len(group),
                    "fraction_near_zero": float((group.R_B50.abs() <= multiplier * scale).mean()),
                }
            )
    return pd.DataFrame(rows)


def grouped_admission(common: pd.DataFrame, delta: float, column: str) -> pd.DataFrame:
    rows = []
    for (pool, value), group in common.groupby(["pool", column], sort=True):
        rows.append({"pool": pool, "group": column, "value": value, "n": len(group), **confusion(group, delta)})
    return pd.DataFrame(rows)


def make_figures(common: pd.DataFrame, centers: pd.DataFrame, delta: float) -> list[Path]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.95)
    plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 300, "axes.unicode_minus": False})
    outputs: list[Path] = []

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.65), constrained_layout=True)
    lim = float(np.quantile(np.abs(common[["R_B50", "R_hat"]].to_numpy()), 0.995))
    for ax, (pool, group) in zip(axes, common.groupby("pool", sort=False)):
        hb = ax.hexbin(group.R_B50, group.R_hat, gridsize=38, mincnt=1, cmap="viridis", bins="log")
        ax.plot([-lim, lim], [-lim, lim], linestyle="--", color="0.25", linewidth=0.8, label="identity")
        ax.axhline(0, color="0.55", linewidth=0.6)
        ax.axvline(0, color="0.55", linewidth=0.6)
        if pool != "P6-OOF":
            ax.axhline(delta, color="#D55E00", linestyle=":", linewidth=1.0, label="frozen gate")
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_title(pool)
        ax.set_xlabel(r"Oracle $R_{B50}$")
        if ax is axes[0]:
            ax.set_ylabel(r"Predicted $\hat{R}$")
        ax.legend(frameon=False, fontsize=6, loc="upper left")
        fig.colorbar(hb, ax=ax, label="log count", fraction=0.046, pad=0.03)
    path = FIGURES / "rhat_vs_oracle_by_pool.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    outputs.append(path)

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), constrained_layout=True)
    for pool, group in common.groupby("pool", sort=False):
        for ax, column, label in [
            (axes[0], "R_B50", r"Oracle $R_{B50}$"),
            (axes[1], "R_hat", r"Predicted $\hat{R}$"),
        ]:
            x = np.sort(group[column].to_numpy())
            y = np.arange(1, len(x) + 1) / len(x)
            ax.plot(x, y, color=PALETTE[pool], linewidth=1.25, label=pool)
            ax.set_xlabel(label)
            ax.set_ylabel("Empirical cumulative fraction")
            ax.axvline(0, color="0.5", linewidth=0.7)
    axes[1].axvline(delta, color="#D55E00", linestyle=":", linewidth=1.0, label="P7.2 frozen gate")
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    axes[1].legend(frameon=False, fontsize=7, loc="upper left")
    path = FIGURES / "pool_margin_distributions.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    outputs.append(path)

    scale_centers = center_scale_summary(common)
    scale_centers = scale_centers[scale_centers.row_type == "center"].copy()
    fig, ax = plt.subplots(figsize=(5.2, 4.0), constrained_layout=True)
    for pool, group in scale_centers.groupby("pool", sort=False):
        ax.scatter(
            group.IQR_R_B50,
            group.median_prediction_error,
            s=30,
            alpha=0.8,
            color=PALETTE[pool],
            marker=MARKERS[pool],
            edgecolor="white",
            linewidth=0.35,
            label=pool,
        )
    ax.axhline(0, color="0.35", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xlabel(r"Center oracle spread, IQR($R_{B50}$)")
    ax.set_ylabel(r"Center median error, $\hat{R}-R_{B50}$")
    ax.legend(frameon=False, fontsize=7)
    path = FIGURES / "center_bias_and_scale.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    outputs.append(path)

    fig, ax = plt.subplots(figsize=(5.4, 4.2), constrained_layout=True)
    for pool, group in centers.groupby("pool", sort=False):
        ax.scatter(
            group.zero_Spearman,
            group.frozen_balanced_sign_accuracy,
            s=34,
            alpha=0.82,
            color=PALETTE[pool],
            marker=MARKERS[pool],
            edgecolor="white",
            linewidth=0.35,
            label=pool,
        )
    ax.axvline(0, color="0.4", linestyle="--", linewidth=0.8)
    ax.axhline(0.5, color="0.4", linestyle="--", linewidth=0.8)
    ax.set_xlabel(r"Within-center Spearman($\hat{R}$, $R_{B50}$)")
    ax.set_ylabel("Balanced admission accuracy\n(P7.2 frozen threshold)")
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, fontsize=7)
    path = FIGURES / "rank_vs_sign_by_center.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    outputs.append(path)
    return outputs


def fmt(value: float, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{value:.{digits}f}"


def markdown_table(frame: pd.DataFrame, columns: list[str], percent: set[str] | None = None) -> str:
    percent = percent or set()
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    lines = [header, divider]
    for row in frame[columns].to_dict("records"):
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, (float, np.floating)):
                values.append(f"{100 * value:.2f}%" if column in percent else f"{value:.5g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    common: pd.DataFrame,
    transport: pd.DataFrame,
    centers: pd.DataFrame,
    scenarios: pd.DataFrame,
    distributions: pd.DataFrame,
    scales: pd.DataFrame,
    ranks: pd.DataFrame,
    history: pd.DataFrame,
    near_zero: pd.DataFrame,
    delta: float,
    scale_s: float,
) -> None:
    t = transport.set_index("pool")
    overall_dist = distributions[(distributions.group_level == "overall") & (distributions.variable == "R_B50")]
    scale_pool = scales[scales.row_type == "pool_cross_center_variation"].set_index("pool")
    taxonomy = ranks.groupby(["pool", "directional_taxonomy"]).size().unstack(fill_value=0)
    grouped_type = grouped_admission(common, delta, "center_type")
    grouped_tier = grouped_admission(common, delta, "deployment_tier")
    grouped_seed = grouped_admission(common, delta, "seed")
    pool_near = near_zero[near_zero.aggregation == "pool"]

    action_ba = t.loc["ActionCal-v2", "frozen_macro_balanced_sign_accuracy"]
    gate_ba = t.loc["GateCal-v2", "frozen_macro_balanced_sign_accuracy"]
    p6_spearman = t.loc["P6-OOF", "Spearman"]
    action_non_c3 = scenarios[(scenarios.pool == "ActionCal-v2") & (scenarios.scenario_group == "non-C3")].iloc[0]
    gate_non_c3 = scenarios[(scenarios.pool == "GateCal-v2") & (scenarios.scenario_group == "non-C3")].iloc[0]
    action_c3 = scenarios[(scenarios.pool == "ActionCal-v2") & (scenarios.scenario_group == "C3")].iloc[0]

    primary, secondary = select_diagnosis(transport)

    transport_view = transport[
        [
            "pool", "n", "MAE", "RMSE", "Spearman", "Pearson_descriptive", "sign_accuracy",
            "balanced_sign_accuracy", "macro_center_MAE", "macro_center_RMSE", "mean_center_Spearman",
            "median_center_Spearman", "positive_Spearman_centers", "Spearman_defined_centers",
        ]
    ]
    gate_action = transport[
        [
            "pool", "frozen_gate_open_rate", "frozen_macro_TPR", "frozen_macro_TNR",
            "frozen_macro_balanced_sign_accuracy", "frozen_false_admission_rate", "frozen_missed_admission_rate",
            "frozen_negative_prevalence", "mean_prediction_error",
        ]
    ]
    scenario_view = scenarios[
        [
            "pool", "scenario_group", "zero_n", "zero_Spearman", "zero_MAE",
            "zero_balanced_sign_accuracy", "zero_mean_prediction_error", "frozen_balanced_sign_accuracy",
        ]
    ]
    history_view = history[
        [
            "pool", "stratification", "bin", "n", "Spearman", "zero_balanced_sign_accuracy",
            "frozen_balanced_sign_accuracy", "frozen_false_admission_rate", "frozen_missed_admission_rate",
        ]
    ]
    near_view = pool_near[["pool", "multiplier", "absolute_margin_bound", "fraction_near_zero"]]

    lines = [
        "# P7.3 Read-Only Root-Cause Audit of Recoverability-to-Admission Failure",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent; scipilot-figure-skill",
        "- Origin Mode: validate (read-only forensic analysis)",
        f"- Origin Date: {datetime.now(timezone.utc).date().isoformat()}",
        "- Verification Status: ANALYZED",
        "- Overall Confidence: MODERATE (synthetic fresh-pool diagnosis; no heldout access)",
        "",
        "## 1. Executive diagnosis",
        "",
        f"**Primary diagnosis: `{primary}`.**",
        "",
        f"**Secondary diagnosis: `{secondary}`.**" if secondary else "**Secondary diagnosis: none assigned.**",
        "",
        (
            "GateCal retains useful continuous association (pooled Spearman "
            f"{t.loc['GateCal-v2','Spearman']:.3f}; mean center Spearman "
            f"{t.loc['GateCal-v2','mean_center_Spearman']:.3f}; 12/12 centers positive). ActionCal is different: "
            f"its pooled Spearman is {t.loc['ActionCal-v2','Spearman']:.3f}, but mean center Spearman is "
            f"{t.loc['ActionCal-v2','mean_center_Spearman']:.3f} and only "
            f"{int(t.loc['ActionCal-v2','positive_Spearman_centers'])}/12 centers are positive. Because center is the "
            "primary unit, the pooled ActionCal association cannot be treated as stable continuous transport. "
            f"At the same time, macro balanced admission accuracy falls from {gate_ba:.3f} on GateCal to "
            f"{action_ba:.3f} on ActionCal, with large center-scale and location shifts. The evidence therefore mixes "
            "ActionCal continuous-transport degradation with absolute-boundary transport failure; no single mechanism "
            "dominates both fresh pools."
        ),
        "",
        "## 2. Scope and preserved verdicts",
        "",
        "This audit used only saved P6 OOF and P7.2 GateCal/ActionCal artifacts. It generated no trajectory, "
        "reran no adaptation or RI candidate, fitted no estimator, changed no scaler or feature, and selected no "
        "threshold. All relative and center-standardized results are explicitly post-hoc diagnostics.",
        "",
        "| Phase | Preserved outcome |",
        "|---|---|",
        "| P6 | continuous estimator-development PASS |",
        "| P7 | formal calibration PASS under its original lifecycle-objective rule |",
        "| P7.1 | `GATE_IS_EFFECTIVELY_ALWAYS_OPEN_ON_CALIBRATION` |",
        "| P7.2 | FAIL under fresh prospective gate semantics |",
        "",
        f"The common table contains {len(common):,} saved stage records: "
        + ", ".join(f"{pool}={len(group):,}" for pool, group in common.groupby('pool', sort=False))
        + ". Center is the primary aggregation unit.",
        "",
        "## 3. Continuous estimator transport",
        "",
        markdown_table(transport_view, list(transport_view.columns)),
        "",
        (
            f"P6 OOF retains strong pooled association (Spearman {p6_spearman:.3f}). GateCal transports at both the "
            "pooled and center levels. ActionCal retains a weak pooled association but not a positive macro-center "
            "association, consistent with an aggregation/base-rate contribution rather than stable within-center "
            "transport. The center "
            "bootstrap intervals and leave-one-center sensitivity are recorded in "
            "`continuous_transport_by_pool.csv`; they are descriptive and do not define a new PASS boundary."
        ),
        "",
        "## 4. Pool distribution shift",
        "",
        markdown_table(
            overall_dist[["pool", "mean", "median", "SD", "IQR", "p05", "p25", "p50", "p75", "p95", "negative_prevalence"]],
            ["pool", "mean", "median", "SD", "IQR", "p05", "p25", "p50", "p75", "p95", "negative_prevalence"],
            {"negative_prevalence"},
        ),
        "",
        "The complete long-form summary also reports R-hat and prediction-error distributions by center, scenario, "
        "center type, and deployment tier. Negative prevalence is pool-specific synthetic composition, not a "
        "population prevalence estimate.",
        "",
        "## 5. Center-scale comparability",
        "",
    ]
    for pool in t.index:
        row = scale_pool.loc[pool]
        lines.append(
            f"- {pool}: cross-center oracle-IQR max/min-positive ratio "
            f"{fmt(row['IQR_R_B50_max_min_ratio'], 2)} and robust Q75/Q25 ratio "
            f"{fmt(row['IQR_R_B50_robust_high_low_ratio'], 2)}; median-|R| max/min-positive ratio "
            f"{fmt(row['median_abs_R_B50_max_min_ratio'], 2)}."
        )
    lines += [
        "",
        "These variations make one globally fixed absolute quantity scientifically fragile across heterogeneous "
        "centers. The finding is about comparability of units; it is not authorization to recalibrate per center.",
        "",
        "## 6. Offline relative-margin diagnostics",
        "",
        "**POST-HOC ROOT-CAUSE DIAGNOSTIC — NOT A METHOD RESULT.** No transformed value was used as an online "
        "feature, label, decision rule, or selection criterion.",
        "",
        markdown_table(
            transport[["pool", "POSTHOC_R_rel_tau_Spearman", "POSTHOC_R_rel_tau_MAE", "POSTHOC_center_z_Spearman", "POSTHOC_center_z_zero_BA"]],
            ["pool", "POSTHOC_R_rel_tau_Spearman", "POSTHOC_R_rel_tau_MAE", "POSTHOC_center_z_Spearman", "POSTHOC_center_z_zero_BA"],
        ),
        "",
        "Center standardization is mechanically centered within the analysis pool and therefore cannot be read as "
        "deployable prospective calibration. Its role is limited to asking whether location/scale heterogeneity can "
        "account for the observed absolute-boundary instability.",
        "",
        "## 7. Rank-versus-sign decomposition",
        "",
    ]
    for pool in taxonomy.index:
        counts = ", ".join(f"{name}: {int(value)}" for name, value in taxonomy.loc[pool].items())
        lines.append(f"- {pool}: {counts}.")
    lines += [
        "",
        "The taxonomy uses only neutral directional anchors (Spearman > 0 and balanced accuracy > 0.5), not a "
        "post-hoc validation threshold. Center-level bias, spread ratio, frozen confusion counts, and taxonomy are "
        "available in `rank_vs_sign_summary.csv`.",
        "",
        "## 8. Scenario and C3/non-C3 decomposition",
        "",
        markdown_table(scenario_view, list(scenario_view.columns)),
        "",
        (
            f"ActionCal non-C3 Spearman is {action_non_c3.zero_Spearman:.3f} versus C3 "
            f"{action_c3.zero_Spearman:.3f}; GateCal non-C3 Spearman is {gate_non_c3.zero_Spearman:.3f}. "
            "C4 remains Nonlinear Dependency-Shift Stress only. These patterns determine whether C3 dominance is "
            "secondary, but do not change scenario roles."
        ),
        "",
        "## 9. Center/type/tier/seed concentration",
        "",
    ]
    for pool in t.index:
        c = centers[centers.pool == pool]
        worst = c.loc[c.frozen_balanced_sign_accuracy.idxmin()]
        dominant = c.loc[c.frozen_pooled_BA_change_when_removed.abs().idxmax()]
        lines.append(
            f"- {pool}: lowest center BA is center {int(worst.center_id)} ({worst.frozen_balanced_sign_accuracy:.3f}); "
            f"largest absolute leave-one-center change comes from center {int(dominant.center_id)} "
            f"({dominant.frozen_pooled_BA_change_when_removed:+.3f})."
        )
    lines += [
        "",
        "No center was removed for selection or re-estimation. Type, tier, and seed summaries follow.",
        "",
        markdown_table(grouped_type[["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]], ["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]),
        "",
        markdown_table(grouped_tier[["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]], ["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]),
        "",
        markdown_table(grouped_seed[["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]], ["pool", "value", "n", "balanced_sign_accuracy", "false_admission_rate", "missed_admission_rate"]),
        "",
        "## 10. Identity age and history coverage",
        "",
        markdown_table(history_view, list(history_view.columns)),
        "",
        "These strata use saved history or a deterministic reconstruction of the saved gain/residual sequence only; "
        "no model was rerun and warm-up semantics were not changed.",
        "",
        "## 11. Oracle margins near zero",
        "",
        f"The pre-frozen P6 OOF error scale is s={scale_s:.12g}.",
        "",
        markdown_table(near_view, list(near_view.columns), {"fraction_near_zero"}),
        "",
        "A large near-zero fraction means that small location errors can reverse admission labels even when rank "
        "association remains useful. These fractions are descriptive and do not define a new tolerance label.",
        "",
        "## 12. GateCal-to-ActionCal transport at the frozen delta",
        "",
        f"Frozen delta_R = {delta:.15g}; no reselection was performed.",
        "",
        markdown_table(gate_action[gate_action.pool.isin(["GateCal-v2", "ActionCal-v2"])], list(gate_action.columns), {"frozen_gate_open_rate", "frozen_macro_TPR", "frozen_macro_TNR", "frozen_macro_balanced_sign_accuracy", "frozen_false_admission_rate", "frozen_missed_admission_rate", "frozen_negative_prevalence"}),
        "",
        "The disjoint ActionCal pool shows lower TPR and balanced admission accuracy under exactly the same frozen "
        "decision rule. This is a transport diagnostic, not a threshold-search opportunity; because ActionCal also "
        "loses within-center rank association, the contrast cannot be attributed to the boundary alone.",
        "",
        "## 13. Hypothesis adjudication",
        "",
        "- **H1 (continuous transport failed): partially supported, but only on ActionCal at the primary center level.** GateCal clearly retains transport, so D1, which requires collapse on both fresh pools, is not met.",
        "- **H2 (rank useful, absolute threshold transport fails): supported on GateCal and in the GateCal-to-ActionCal contrast, but insufficient as a sole diagnosis.** ActionCal does not retain positive macro-center rank association.",
        "- **H3 (C3-dominated estimator): not supported as the principal explanation.** ActionCal is weak in both C3 and non-C3, while GateCal retains non-C3 directionality; C4 keeps its stress-only role.",
        "- **H4 (few centers/types/tiers dominate): partially supported.** Center and subgroup ranges are large, but leave-one-center removal does not restore a stable ActionCal result.",
        "- **H5 (oracle absolute units differ by center): supported as a contributor.** Cross-center scale ratios and bias variation are large, but post-hoc tau-relative and center-z normalization do not rescue ActionCal association, so scale heterogeneity cannot be called the sole dominant cause.",
        "- **H6 (early-history instability): not supported.** On ActionCal the full-history stratum is weaker than the early strata; the failure is not concentrated before coverage accumulates.",
        "",
        "## 14. Statistical-fallacy scan",
        "",
        "| Fallacy | Audit disposition |",
        "|---|---|",
        "| Simpson / aggregation reversal | Pooled, macro-center, scenario, type, tier, seed, and history strata are reported side by side. |",
        "| Ecological inference | Center-level patterns are not attributed to individual stages or real populations. |",
        "| Base-rate effects | Negative prevalence, TPR, TNR, false admission, and missed admission are reported separately. |",
        "| Selected-pool bias | P6, GateCal, and ActionCal retain their distinct development/selection/validation roles. |",
        "| Center dominance | Leave-one-center sensitivity is reported; no center is removed from the formal result. |",
        "| Look-elsewhere | No threshold, feature, or classifier search was conducted. |",
        "| Post-hoc normalization | Every relative/z result is labeled forensic-only and excluded from method claims. |",
        "| Regression to mean | Pool shifts are described without causal attribution or claims of future correction. |",
        "| Temporal leakage | Only saved causal prediction/history fields are used; offline oracle values remain diagnostic labels. |",
        "| Causal overinterpretation | Associations and decomposition are described as root-cause evidence, not causal proof. |",
        "| Survivorship | All hash-valid P6/GateCal/selected-ActionCal stages are retained; failures are not filtered. |",
        "",
        "## 15. Scientific implications and required final decision",
        "",
        "| Claim | Conservative status |",
        "|---|---|",
        "| C1 | SUPPORTED |",
        "| C2 | WEAKENED_BY_FRESH_POOL_FAILURE |",
        "| C3 | CURRENT_HARD_ABSOLUTE_GATE_REJECTED |",
        "",
        f"1. **Primary root-cause diagnosis:** `{primary}`.",
        f"2. **Secondary diagnosis:** `{secondary}`." if secondary else "2. **Secondary diagnosis:** none assigned; center-scale heterogeneity contributes but does not dominate after post-hoc normalization.",
        "3. **C1/C2/C3 status:** C1 SUPPORTED; C2 WEAKENED_BY_FRESH_POOL_FAILURE; C3 CURRENT_HARD_ABSOLUTE_GATE_REJECTED.",
        "4. **Current hard absolute-threshold gate:** it should be abandoned in its present globally fixed form; this does not revoke the continuous-estimator development result.",
        "5. **Single most scientifically justified next research step:** pre-register a new non-heldout development study that separates within-center continuous transport from cross-center absolute-scale transport, prospectively comparing the existing absolute representation with a scientifically defined center-scale-relative recoverability target and explicit history strata. This is a redesign study, not retrospective threshold tuning, and P7.3 does not implement it.",
        "6. **No final heldout data were accessed and no method change was implemented in P7.3.**",
        "",
        "STOP. Do not implement P7.4 or run P8 before human scientific review.",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def execute() -> None:
    tracked_before, raw_expected = verify_frozen_inputs()
    p6 = read_json(P6_FREEZE)
    gate = read_json(P7_2_SELECTED_GATE)
    selected_action = read_json(P7_2_SELECTED_ACTION)
    grid = read_json(P7_GRID)
    delta = float(gate["delta_R"])
    config_id = selected_action["selected"]["config"]["config_id"]
    scale_s = float(grid["s"])

    common = pd.concat([load_p6(), load_gatecal(), load_actioncal(config_id)], ignore_index=True, sort=False)
    common = attach_diagnostics(common, delta)
    order = [
        "pool", "center_id", "seed", "scenario", "stage", "model_identity", "identity_age",
        "center_type", "deployment_tier", "R_hat", "R_B50", "oracle_sign", "prediction_error",
        "absolute_error", "tau_service", "pre_assessment_loss", "probe_gain", "probe_residual",
        "mean_gain_short", "mean_residual_short", "mean_gain_long", "mean_residual_long",
        "coverage_short", "coverage_long", "history_coverage_bin", "identity_age_bin",
        "zero_sign_prediction", "frozen_gate_open", "frozen_gate_error", "fold", "R_rel_tau",
        "R_hat_rel_tau", "R_center_z", "R_hat_center_z", "source_path_class",
    ]
    common = common[order].sort_values(["pool", "center_id", "seed", "scenario", "stage"]).reset_index(drop=True)

    centers = center_metrics(common, delta)
    transport = transport_summary(common, centers, delta)
    scenarios = scenario_metrics(common, delta)
    distributions = distribution_summary(common)
    scales = center_scale_summary(common)
    ranks = rank_sign_summary(centers)
    history = history_summary(common, delta)
    near_zero = near_zero_summary(common, scale_s)

    outputs = {
        "results/p7_3/common_diagnostic_table.csv": common,
        "results/p7_3/continuous_transport_by_pool.csv": transport,
        "results/p7_3/metrics_by_center.csv": centers,
        "results/p7_3/metrics_by_scenario.csv": scenarios,
        "results/p7_3/pool_distribution_summary.csv": distributions,
        "results/p7_3/center_scale_summary.csv": scales,
        "results/p7_3/rank_vs_sign_summary.csv": ranks,
        "results/p7_3/history_coverage_summary.csv": history,
        "results/p7_3/near_zero_margin_summary.csv": near_zero,
    }
    for rel, frame in outputs.items():
        write_csv(ROOT / rel, frame)
    figure_paths = make_figures(common, centers, delta)
    write_report(common, transport, centers, scenarios, distributions, scales, ranks, history, near_zero, delta, scale_s)

    tracked_after, raw_after = verify_frozen_inputs()
    if tracked_after != tracked_before or raw_after != raw_expected:
        raise AssertionError("immutable input changed during P7.3")
    output_paths = [ROOT / rel for rel in outputs] + figure_paths + [REPORT]
    primary, secondary = select_diagnosis(transport)
    audit = {
        "schema": "p7.3-read-only-root-cause-audit-v1",
        "status": "VALID_READ_ONLY_AUDIT",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_diagnosis": primary,
        "secondary_diagnosis": secondary,
        "preserved_verdicts": {
            "P6": "continuous estimator-development PASS",
            "P7": "formal calibration PASS under original lifecycle-objective rule",
            "P7_1": "GATE_IS_EFFECTIVELY_ALWAYS_OPEN_ON_CALIBRATION",
            "P7_2": "FAIL under fresh prospective gate semantics",
        },
        "integrity_checks": {
            "no_new_trajectory_generated": True,
            "no_adaptation_or_RI_candidate_rerun": True,
            "P6_estimator_hash_unchanged": True,
            "P6_scaler_hash_unchanged": True,
            "feature_specification_unchanged": True,
            "K_S": p6["K_S"],
            "K_L": p6["K_L"],
            "P7_2_FAIL_preserved": True,
            "GateCal_raw_artifacts_unchanged": True,
            "ActionCal_raw_artifacts_unchanged": True,
            "heldout_accessed": False,
            "alibaba_accessed": False,
            "P8_executed": False,
            "new_threshold_optimized": False,
            "posthoc_normalization_entered_online_features": False,
            "fitted_model_artifact_created": False,
            "new_calibration_or_method_freeze_created": False,
        },
        "selected_read_only_inputs": {
            "ActionCal_config_id": config_id,
            "frozen_delta_R": delta,
            "P6_error_scale_s": scale_s,
            "tracked_immutable_hashes": tracked_before,
            "GateCal_raw_file_count": len(read_json(P7_2_GATE_FREEZE)["raw_gatecal_hashes"]),
            "ActionCal_raw_file_count": len(read_json(P7_2_FINAL_FREEZE)["raw_actioncal_hashes"]),
        },
        "diagnostic_table_rows": int(len(common)),
        "pool_rows": {pool: int(len(group)) for pool, group in common.groupby("pool", sort=False)},
        "outputs": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in output_paths},
        "posthoc_notice": "Relative and center-standardized quantities are root-cause diagnostics only, not method results.",
        "final_statement": "No final heldout data were accessed and no method change was implemented in P7.3.",
    }
    write_json(AUDIT, audit)
    AUDIT.with_suffix(".sha256").write_text(sha256_file(AUDIT) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "rows": len(common), "report": str(REPORT), "audit_sha256": sha256_file(AUDIT)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="P7.3 read-only root-cause audit")
    parser.add_argument("command", choices=["audit"])
    args = parser.parse_args()
    if args.command == "audit":
        execute()


if __name__ == "__main__":
    main()
