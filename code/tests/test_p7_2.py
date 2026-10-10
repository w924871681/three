"""P7.2 prospective scientific/leakage/fairness guards."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from core.common import ROOT, sha256_file
from core.p6 import FEATURE_COLUMNS
from core.p7 import read_json


POOLS = ROOT / "configs/p7_2_fresh_center_pools.json"
GRID = ROOT / "configs/p7_2_gate_grid.json"
AMENDMENT = ROOT / "docs/P7_2_GATE_CALIBRATION_AMENDMENT.md"
PRE = ROOT / "audits/P7_2_PRE_OUTCOME_PROTOCOL_FREEZE.json"
GATE = ROOT / "audits/P7_2_GATE_FREEZE.json"
RESULTS = ROOT / "results/p7_2"


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _action_frame():
    files = sorted((RESULTS / "raw/actioncal").glob("*.csv"))
    if len(files) != 144:
        return None
    return pd.concat([pd.read_csv(path) for path in files], ignore_index=True)


def test_p7_2_amendment_committed_before_outcomes():
    pre = read_json(PRE)
    amendment_commit = pre["amendment_git_commit"]
    protocol_commit = pre["protocol_git_commit"]
    assert subprocess.run(["git", "merge-base", "--is-ancestor", amendment_commit, protocol_commit], cwd=ROOT).returncode == 0
    assert sha256_file(AMENDMENT) == AMENDMENT.with_suffix(".sha256").read_text().strip()
    started = RESULTS / "gatecal_materialization_started.json"
    if started.exists():
        marker = read_json(started)
        assert marker["pre_outcome_git_commit"] == protocol_commit
        assert marker["pre_outcome_manifest_sha256"] == sha256_file(PRE)


def test_p7_2_fresh_centers_unused():
    pools = read_json(POOLS)
    ids = set(pools["gatecal_v2"]) | set(pools["actioncal_v2"])
    assert ids == set(range(32100, 32124))
    forbidden = set(range(31200, 31230)) | set(range(32000, 32020)) | set(range(33000, 33020))
    assert ids.isdisjoint(forbidden)
    assert not any(path.name for path in ROOT.rglob("*") if path.is_file() and path.name.startswith(tuple(str(i) for i in ids)))


def test_p7_2_gatecal_actioncal_disjoint():
    pools = read_json(POOLS)
    assert len(pools["gatecal_v2"]) == len(pools["actioncal_v2"]) == 12
    assert set(pools["gatecal_v2"]).isdisjoint(pools["actioncal_v2"])


def test_p7_2_no_final_heldout_access():
    for marker in RESULTS.glob("*.json"):
        payload = read_json(marker)
        if "heldout_accessed" in payload:
            assert payload["heldout_accessed"] is False
    assert not list((RESULTS / "raw").rglob("*330*.csv")) if (RESULTS / "raw").exists() else True


def test_p7_2_no_alibaba_access():
    for marker in RESULTS.glob("*.json"):
        payload = read_json(marker)
        if "alibaba_accessed" in payload:
            assert payload["alibaba_accessed"] is False


def test_p7_2_p6_estimator_hash_unchanged():
    freeze = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
    assert sha256_file(ROOT / "artifacts/p6_recoverability_estimator.pt") == freeze["estimator_sha256"]


def test_p7_2_scaler_hash_unchanged():
    freeze = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
    assert sha256_file(ROOT / "artifacts/p6_recoverability_scaler.json") == freeze["scaler_sha256"]


def test_p7_2_feature_spec_unchanged():
    assert FEATURE_COLUMNS == ["mean_gain_short", "mean_residual_short", "mean_gain_long", "mean_residual_long",
                               "coverage_short", "coverage_long"]
    p6 = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
    assert p6["feature_order"] == FEATURE_COLUMNS
    assert "scenario" not in FEATURE_COLUMNS and "center_id" not in FEATURE_COLUMNS


def test_p7_2_window_pair_unchanged():
    p6 = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
    assert (p6["K_S"], p6["K_L"]) == (2, 6)


def test_p7_2_delta_grid_identical_to_p7():
    new = read_json(GRID)
    old = read_json(ROOT / "configs/p7_delta_grid.json")
    assert new["multipliers"] == old["multipliers"]
    assert new["delta_R"] == old["delta_R"]
    assert new["s"] == old["s"]
    assert new["p7_grid_sha256"] == sha256_file(ROOT / "configs/p7_delta_grid.json")


def test_p7_2_gate_selection_uses_only_gatecal():
    selected = read_json(ROOT / "configs/p7_2_selected_gate.json")
    assert selected["selection_pool"] == "GateCal-v2"
    assert selected["selection_metric"] == "macro_center_balanced_admission_accuracy"
    assert selected["heldout_access_allowed"] is False


def test_p7_2_actioncal_never_changes_delta():
    action = ROOT / "configs/p7_2_selected_action_params.json"
    if not action.exists():
        return
    gate = read_json(ROOT / "configs/p7_2_selected_gate.json")
    chosen = read_json(action)
    assert chosen["delta_R_frozen_from_gatecal"] == gate["delta_R"]
    assert all(value["config"]["delta_R"] == gate["delta_R"] for value in chosen["by_ratio"].values())


def test_p7_2_scenario_not_used_as_gate_feature():
    assert "scenario" not in FEATURE_COLUMNS and "scenario_id" not in FEATURE_COLUMNS


def test_p7_2_no_future_service_in_online_decision():
    frame = _action_frame()
    if frame is None:
        return
    assert not frame.future_service_used_in_decision.any()
    assert frame.decision_ts.lt(frame.service_start_ts).all()


def test_p7_2_assessment_not_used_for_gradients():
    frame = _action_frame()
    if frame is None:
        return
    assert frame.assessment_gradient_updates.eq(0).all()


def test_p7_2_same_bank_budget_across_methods():
    frame = _action_frame()
    if frame is None:
        return
    assert frame.bank_hash.nunique() == 1
    assert frame.ri_updates_per_candidate.eq(50).all()
    assert frame.probe_updates.eq(50).all()
    assert (frame.ri_search_updates_charged == 50 * frame.feasible_candidate_count).all()


def test_p7_2_history_reset_on_identity_change():
    frame = _action_frame()
    if frame is None:
        return
    for _, group in frame.groupby(["config_id", "center_id", "seed", "scenario"]):
        ordered = group.sort_values("stage")
        for previous, current in zip(ordered.iloc[:-1].itertuples(), ordered.iloc[1:].itertuples()):
            assert current.history_size == (1 if previous.ri else previous.history_size + 1)


def test_p7_2_baseline_grids_not_expanded():
    old = read_json(ROOT / "configs/p7_baseline_grids.json")
    assert old["cost_ratios"] == [2, 5, 10]
    selected = ROOT / "configs/p7_2_selected_baseline_params.json"
    if not selected.exists():
        return
    payload = read_json(selected)
    for ratio, methods in payload["by_ratio"].items():
        assert int(ratio) in old["cost_ratios"]
        for method, value in methods.items():
            cfg = value["config"]
            if method == "B3": assert cfg["K"] in old["B3"]["K"]
            if method == "B4":
                assert cfg["quantile"] in old["B4"]["quantile"] and cfg["persistence"] in old["B4"]["persistence"]
            if method == "B5": assert cfg["delta"] in old["B5"]["delta"]
            if method == "B6": assert cfg["K"] in old["B6"]["K"]
            if method == "B7":
                assert cfg["window"] in old["B7"]["window"] and cfg["margin"] in old["B7"]["normalized_margin"]


def test_p7_2_b8_always_open_exact():
    frame = _action_frame()
    if frame is None:
        return
    b8 = frame[frame.method == "B8"]
    assert len(b8) == 3 * 3456 and b8.gate_open.eq(1).all()


def test_p7_2_all_selected_params_frozen_before_heldout():
    for path in [ROOT / "configs/p7_2_selected_gate.json", ROOT / "configs/p7_2_selected_action_params.json",
                 ROOT / "configs/p7_2_selected_baseline_params.json"]:
        if path.exists():
            assert read_json(path).get("heldout_access_allowed", False) is False
    assert read_json(PRE)["heldout_accessed"] is False
    if GATE.exists():
        assert read_json(GATE)["heldout_accessed"] is False

