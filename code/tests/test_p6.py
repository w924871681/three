from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.common import ROOT, sha256_file
from core.p6 import FEATURE_COLUMNS, causal_history_features


P4 = ROOT / "audits" / "P4_EXPERIMENT_SCOPE_FREEZE.json"
CANDIDATES = ROOT / "configs" / "p6_estimator_candidates.json"
FOLDS = ROOT / "configs" / "p6_group_cv_folds.json"
STAGES = ROOT / "results" / "p6" / "stage_records.csv"
FEATURES = ROOT / "results" / "p6" / "selected_feature_matrix.csv"
PREDICTIONS = ROOT / "results" / "p6" / "cv_predictions.csv"
SCALERS = ROOT / "results" / "p6" / "fold_scalers.json"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _events(identity=("A", "A", "A", "A", "B", "B", "B")):
    return pd.DataFrame(
        {
            "center_id": [1] * len(identity),
            "seed": [7] * len(identity),
            "scenario": ["C0"] * len(identity),
            "stage": list(range(1, len(identity) + 1)),
            "identity_id": list(identity),
            "probe_gain": np.arange(len(identity), dtype=float),
            "probe_residual": np.arange(len(identity), dtype=float) / 10 + 1,
            "R_B50": np.arange(len(identity), dtype=float) / 100,
        }
    )


def test_p6_fit_pool_matches_p4_freeze():
    p4 = _json(P4)
    folds = _json(FOLDS)
    pool = p4["center_pools"]["prospective_estimator_fitting"]
    expected = list(range(pool["id_start"], pool["id_end_inclusive"] + 1))
    assert folds["fitting_centers"] == expected
    if STAGES.exists():
        assert sorted(pd.read_csv(STAGES, usecols=["center_id"]).center_id.unique()) == expected


def test_p6_no_calibration_or_heldout_access():
    p4 = _json(P4)
    forbidden = set(range(32000, 32020)) | set(range(33000, 33020))
    forbidden |= set(p4["center_pools"]["generator_design_development"]["ids"])
    forbidden |= set(p4["center_pools"]["fresh_phenomenon_development"]["ids"])
    if STAGES.exists():
        assert not (set(pd.read_csv(STAGES, usecols=["center_id"]).center_id) & forbidden)


def test_p6_group_split_by_center():
    folds = _json(FOLDS)
    all_centers = set(folds["fitting_centers"])
    for fold in folds["folds"]:
        valid = set(fold["validation_centers"])
        assert len(valid) == 6
        assert len(all_centers - valid) == 24


def test_p6_no_center_overlap_between_folds():
    folds = _json(FOLDS)
    groups = [set(item["validation_centers"]) for item in folds["folds"]]
    assert not any(left & right for i, left in enumerate(groups) for right in groups[i + 1 :])
    assert set().union(*groups) == set(folds["fitting_centers"])


def test_p6_fold_local_scaler():
    if not (FEATURES.exists() and SCALERS.exists()):
        pytest.skip("P6 selected feature artifacts not materialized yet")
    frame = pd.read_csv(FEATURES)
    recorded = _json(SCALERS)
    for item in recorded["folds"]:
        train = frame[frame.fold != item["fold"]]
        assert sorted(train.center_id.unique()) == item["training_centers"]
        mean = train[FEATURE_COLUMNS].to_numpy().mean(axis=0)
        scale = train[FEATURE_COLUMNS].to_numpy().std(axis=0, ddof=0)
        scale[scale == 0] = 1.0
        assert np.allclose(mean, item["scaler"]["mean"], rtol=0, atol=1e-12)
        assert np.allclose(scale, item["scaler"]["scale"], rtol=0, atol=1e-12)


def test_p6_feature_exactly_six_dimensions():
    config = _json(CANDIDATES)
    assert config["feature_order"] == FEATURE_COLUMNS
    assert config["feature_dimension"] == 6
    made = causal_history_features(_events(), 2, 6)
    assert made[FEATURE_COLUMNS].shape == (7, 6)


def test_p6_no_scenario_or_center_metadata_feature():
    config = _json(CANDIDATES)
    forbidden = {"scenario_id", "center_id", "center_type", "deployment_tier", "architecture_id"}
    assert not (set(config["feature_order"]) & forbidden)
    assert config["feature_order"] == FEATURE_COLUMNS


def test_p6_no_future_service_input():
    config = _json(CANDIDATES)
    assert "future_information" in config["forbidden_features"]
    assert not any("service" in value.lower() or value.startswith("R_") for value in config["feature_order"])


def test_p6_current_probe_is_causal():
    events = _events()
    made = causal_history_features(events, 2, 6)
    first = made.iloc[0]
    assert first.mean_gain_short == events.iloc[0].probe_gain
    assert first.mean_residual_short == events.iloc[0].probe_residual
    assert first.history_size == 1


def test_p6_history_reset_on_identity_change():
    made = causal_history_features(_events(), 2, 6)
    first_b = made[made.identity_id == "B"].iloc[0]
    assert first_b.stage == 5
    assert first_b.history_size == 1
    assert first_b.coverage_short == 0.5
    assert first_b.coverage_long == 1 / 6


def test_p6_window_never_crosses_identity_boundary():
    events = _events()
    made = causal_history_features(events, 2, 6)
    first_b = made[made.identity_id == "B"].iloc[0]
    assert first_b.mean_gain_short == events.iloc[4].probe_gain
    assert first_b.mean_gain_long == events.iloc[4].probe_gain


def test_p6_window_never_uses_future_response():
    events = _events(("A",) * 7)
    baseline = causal_history_features(events, 2, 6)
    changed = events.copy()
    changed.loc[changed.stage > 3, ["probe_gain", "probe_residual"]] = 999
    perturbed = causal_history_features(changed, 2, 6)
    assert np.array_equal(
        baseline.loc[baseline.stage <= 3, FEATURE_COLUMNS].to_numpy(),
        perturbed.loc[perturbed.stage <= 3, FEATURE_COLUMNS].to_numpy(),
    )


def test_p6_oracle_target_offline_only():
    if not STAGES.exists():
        pytest.skip("P6 targets not materialized yet")
    frame = pd.read_csv(STAGES)
    assert frame.oracle_future_data_offline_only.eq(True).all()
    assert frame.R_B50.notna().all()
    assert not any(column in FEATURE_COLUMNS for column in ["R_B50", "best_loss_B50", "tau_service"])


def test_p6_cv_predictions_complete():
    if not PREDICTIONS.exists():
        pytest.skip("P6 CV predictions not materialized yet")
    frame = pd.read_csv(PREDICTIONS)
    assert len(frame) == 30 * 3 * 4 * 24
    assert frame.predicted_R_B50.notna().all()
    assert frame.R_B50.notna().all()
    assert frame.duplicated(["center_id", "seed", "scenario", "stage"]).sum() == 0


def test_p6_model_selection_rule_predeclared():
    config = _json(CANDIDATES)
    assert config["declared_before_fitting_outcome_materialization"] is True
    assert "one_standard_error_rule" in config["selection"]
    assert config["selection"]["deterministic_tie_break"]
    assert sha256_file(CANDIDATES) == (ROOT / "configs" / "p6_estimator_candidates.sha256").read_text().split()[0]
    assert sha256_file(FOLDS) == (ROOT / "configs" / "p6_group_cv_folds.sha256").read_text().split()[0]
