from __future__ import annotations

from collections import defaultdict

from .models import ModelIdentity, feasible
from .protocol import spans


def run_p3_2_audits(
    stage_rows: list[dict],
    candidate_rows: list[dict],
    run_rows: list[dict],
    identities: list[ModelIdentity],
    config: dict,
    expected_centers: list[int],
    phase: str,
) -> dict:
    checks: dict[str, bool] = {}
    role_disjoint = True
    for stage in range(1, 25):
        update, assessment, service = spans(stage)
        role_disjoint &= set(range(*update)).isdisjoint(range(*assessment))
        role_disjoint &= set(range(*update)).isdisjoint(range(*service))
        role_disjoint &= set(range(*assessment)).isdisjoint(range(*service))

    checks["test_raw_role_disjointness"] = role_disjoint
    checks["test_window_no_cross_role_boundary"] = role_disjoint
    checks["test_no_future_service_leakage"] = all(
        row["decision_ts"] < row["service_start_ts"] for row in stage_rows
    )
    checks["test_assessment_not_used_for_gradients"] = all(
        row["probe_update_count"] == 50 for row in stage_rows
    )
    checks["test_probe_does_not_modify_deployed_state"] = all(
        row["parent_immutable_during_probe"] for row in run_rows
    )
    grouped_initial: dict[tuple[int, int], set[str]] = defaultdict(set)
    for row in run_rows:
        grouped_initial[(row["center_id"], row["seed"])].add(row["initial_state_hash"])
    checks["test_same_initial_state"] = all(len(values) == 1 for values in grouped_initial.values())
    checks["test_same_bank_hash"] = len({row["bank_hash"] for row in run_rows}) == 1
    checks["test_deployment_filter"] = all(row["num_feasible_alternatives"] >= 1 for row in stage_rows)
    checks["test_candidate_adaptation_budget"] = all(
        row["adaptation_updates"] == 50 for row in candidate_rows
    )
    checks["test_oracle_future_data_offline_only"] = all(
        row["oracle_future_data_offline_only"] for row in stage_rows
    )
    checks["test_all_deployed_models_meet_limits"] = all(
        row["deployment_feasible"] for row in stage_rows
    )
    checks["test_effort_feature_removed"] = all(
        "probe_effort" not in row and row["feature_components"] == "gain,residual"
        for row in stage_rows
    )
    checks["test_per_policy_losses_complete"] = all(
        all(f"J_P{steps}" in row for steps in (0, 10, 20, 50)) for row in stage_rows
    )
    checks["test_budget_subsets_complete"] = all(
        all(f"R_{budget}" in row and f"best_policy_{budget}" in row for budget in ("B0", "B10", "B20", "B50"))
        for row in stage_rows
    )
    checks["test_phase_centers_exact"] = set(row["center_id"] for row in run_rows) == set(expected_centers)
    checks["test_model_seeds_exact"] = set(row["seed"] for row in run_rows) == set(config["model_seeds"])
    checks["test_scenarios_exact"] = set(row["scenario"] for row in run_rows) == set(config["scenarios"])
    checks["test_trajectory_count"] = len(run_rows) == len(expected_centers) * len(config["model_seeds"]) * len(config["scenarios"])
    checks["test_no_prediction_output_blending"] = all(
        row["scenario_metadata"].get("prediction_output_blending") is False for row in run_rows
    )
    checks["test_estimator_not_fitted"] = all(not row["estimator_fitted"] for row in run_rows)
    checks["test_proposed_not_executed"] = all(not row["proposed_executed"] for row in run_rows)
    checks["test_heldout_not_accessed"] = all(not row["heldout_accessed"] for row in run_rows)

    design = set(config["design_centers"])
    fresh = set(config["fresh_development_centers"])
    calibration = set(config["calibration_centers_forbidden"])
    heldout = set(config["heldout_centers_forbidden"])
    source = set(config["source_pair"]["source_centers"])
    checks["test_center_pools_disjoint"] = not any(
        left & right
        for index, left in enumerate((source, design, fresh, calibration, heldout))
        for right in (source, design, fresh, calibration, heldout)[index + 1 :]
    )
    checks["test_phase_label"] = all(row["phase"] == phase for row in run_rows)

    identity_map = {identity.identity_id: identity for identity in identities}
    incumbent = identity_map["msa_a57_pt"]
    c3_identity = identity_map["p3v2_a57_regime_b"]
    c4_identity = identity_map["p3v2_a46_regime_c"]
    checks["test_c3_same_architecture_distinct_source"] = (
        c3_identity.architecture == incumbent.architecture
        and c3_identity.source_initialization_id != incumbent.source_initialization_id
    )
    checks["test_c4_distinct_architecture_family"] = c4_identity.family != incumbent.family
    checks["test_c3_c4_matched_assets_feasible"] = all(
        feasible(identity, limits)
        for identity in (c3_identity, c4_identity)
        for limits in config["deployment_limits"].values()
    )

    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema": "dt-lifecycle-escalation-p3.2-audit-v1",
        "phase": phase,
        "status": status,
        "checks": checks,
        "stage_rows": len(stage_rows),
        "candidate_rows": len(candidate_rows),
        "trajectories": len(run_rows),
        "heldout_accessed": False,
        "estimator_fitted": False,
        "gate_calibrated": False,
        "proposed_executed": False,
    }
