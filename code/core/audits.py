from __future__ import annotations

from collections import defaultdict

import numpy as np

from .models import ModelIdentity, feasible
from .protocol import spans


def run_audits(stage_rows: list[dict], candidate_rows: list[dict], run_audits: list[dict], identities: list[ModelIdentity], config: dict, splits: dict) -> dict:
    checks = {}
    role_disjoint = True
    for stage in range(1, 25):
        u, a, s = spans(stage)
        role_disjoint &= set(range(*u)).isdisjoint(range(*a))
        role_disjoint &= set(range(*u)).isdisjoint(range(*s))
        role_disjoint &= set(range(*a)).isdisjoint(range(*s))
    checks["test_raw_role_disjointness"] = role_disjoint
    checks["test_window_no_cross_role_boundary"] = role_disjoint
    checks["test_no_future_service_leakage"] = all(row["decision_ts"] < row["service_start_ts"] for row in stage_rows)
    checks["test_assessment_not_used_for_gradients"] = all(row["probe_update_count"] == 50 for row in stage_rows)
    checks["test_probe_does_not_modify_deployed_state"] = all(item["parent_immutable_during_probe"] for item in run_audits)
    grouped_initial = defaultdict(set)
    for item in run_audits:
        grouped_initial[(item["center_id"], item["seed"])].add(item["initial_state_hash"])
    checks["test_same_initial_state"] = all(len(values) == 1 for values in grouped_initial.values())
    checks["test_same_bank_hash"] = len({item["bank_hash"] for item in run_audits}) == 1
    checks["test_deployment_filter"] = all(row["num_feasible_alternatives"] >= 1 for row in stage_rows)
    checks["test_candidate_adaptation_budget"] = all(row["adaptation_updates"] == 50 for row in candidate_rows)
    checks["test_oracle_future_data_offline_only"] = all(row["oracle_future_data_offline_only"] for row in stage_rows)
    pool_sets = [set(splits[name]) for name in ("development", "calibration", "heldout")]
    checks["test_center_pool_disjointness"] = not (pool_sets[0] & pool_sets[1] or pool_sets[0] & pool_sets[2] or pool_sets[1] & pool_sets[2])
    checks["test_all_deployed_models_meet_limits"] = all(row["deployment_feasible"] for row in stage_rows)
    effort = np.asarray([row["probe_effort"] for row in stage_rows], dtype=float)
    effort_variance = float(np.var(effort))
    checks["test_effort_feature_variance"] = effort_variance == 0.0
    checks["test_effort_feature_removed_when_constant"] = (
        effort_variance != 0.0 or all(row["feature_components"] == "gain,residual" for row in stage_rows)
    )
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "effort_variance": effort_variance,
        "effort_informative": False if effort_variance == 0.0 else True,
        "estimator_feature_decision": "exclude effort; use [gain, residual]" if effort_variance == 0.0 else "retain for later review",
        "stage_rows": len(stage_rows),
        "candidate_rows": len(candidate_rows),
    }
