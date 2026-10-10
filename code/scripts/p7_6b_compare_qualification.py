"""Compare two complete test-only P7.6B qualification trajectories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "results/p7_6b_qualification"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args()
    dirs = [ROOT / args.left, ROOT / args.right]
    summaries = [json.loads((p / "summary.json").read_text()) for p in dirs]
    assert all(x["test_only"] and 90000 <= x["center_id"] <= 90005 for x in summaries)
    assert summaries[0]["center_id"] == summaries[1]["center_id"]
    assert summaries[0]["seed"] == summaries[1]["seed"]
    assert summaries[0]["scenario"] == summaries[1]["scenario"]
    frames = [pd.read_csv(p / "trajectory.csv") for p in dirs]
    assert all(len(x) == 24 for x in frames)
    a, b = frames
    exact_equal, mismatched = [], []
    numeric = {}
    for column in a.columns:
        if column not in b.columns:
            mismatched.append(column)
            continue
        if pd.api.types.is_numeric_dtype(a[column]) and pd.api.types.is_numeric_dtype(b[column]):
            av, bv = a[column].to_numpy(dtype=float), b[column].to_numpy(dtype=float)
            if np.array_equal(av, bv, equal_nan=True):
                exact_equal.append(column)
            else:
                delta = np.abs(av - bv)
                finite = np.isfinite(delta)
                rel = delta[finite] / np.maximum(np.maximum(np.abs(av[finite]), np.abs(bv[finite])), 1e-12)
                numeric[column] = {"max_abs": float(np.max(delta[finite])) if finite.any() else None,
                                   "max_rel": float(np.max(rel)) if len(rel) else None,
                                   "different_stages": int(np.count_nonzero(delta[finite]))}
        elif a[column].fillna("<NA>").equals(b[column].fillna("<NA>")):
            exact_equal.append(column)
        else:
            mismatched.append(column)
    discrete = ("stage", "identity_before", "identity_after", "D_upd_hash", "D_assess_hash",
                "D_srv_hash", "action", "ri", "local", "gate_open", "best_local_policy",
                "feasible_candidate_count", "A0_action", "A1_action", "A0_post_action_identity",
                "A1_post_action_identity", "behavior_path_match", "identity_age",
                "history_size", "history_coverage", "A0_A1_used_for_behavior", "scenario_hash")
    discrete_equal = {k: k in exact_equal for k in discrete}
    internal_path_equal = all(bool((frame.A0_post_action_path_hash == frame.A1_post_action_path_hash).all())
                              for frame in frames)
    internal_parent_equal = all(bool((frame.A0_parent_state_hash == frame.A1_parent_state_hash).all())
                                for frame in frames)
    internal_action_equal = all(bool((frame.A0_action == frame.A1_action).all()) for frame in frames)
    scales = [pd.read_csv(p / "scales.csv") for p in dirs]
    assert len(scales[0]) == len(scales[1])
    scale_rows = []
    for i in range(len(scales[0])):
        row_a, row_b = scales[0].iloc[i], scales[1].iloc[i]
        scale_rows.append({"stage": int(row_a.stage), "identity_equal": row_a.identity_id == row_b.identity_id,
                           "birth_equal": row_a.birth_source == row_b.birth_source,
                           "reference_segment_equal": row_a.reference_segment_hash == row_b.reference_segment_hash,
                           "S_m_abs_diff": abs(float(row_a.S_m) - float(row_b.S_m)),
                           "point_error_median_abs_diff": abs(float(row_a.point_error_median) - float(row_b.point_error_median))})
    diag = [json.loads((p / "candidate_diagnostics.json").read_text())["stages"] for p in dirs]
    candidate_loss_max = 0.0
    candidate_identity_match = True
    candidate_hash_mismatch_count = 0
    for x, y in zip(diag[0], diag[1]):
        xx, yy = x["candidate_identities_and_hashes"], y["candidate_identities_and_hashes"]
        candidate_identity_match &= [z["identity_id"] for z in xx] == [z["identity_id"] for z in yy]
        for z, w in zip(xx, yy):
            candidate_hash_mismatch_count += z["state_hash"] != w["state_hash"]
            candidate_loss_max = max(candidate_loss_max, abs(z["assessment_loss"] - w["assessment_loss"]))
    vectors = [np.load(p / "state_vectors.npz") for p in dirs]
    assert set(vectors[0].files) == set(vectors[1].files)
    categories = {}
    for key in vectors[0].files:
        x, y = vectors[0][key], vectors[1][key]
        assert x.shape == y.shape
        category = key.split("_")[2]
        d = np.abs(x.astype(np.float64) - y.astype(np.float64))
        max_abs = float(d.max(initial=0))
        max_rel = float((d / np.maximum(np.maximum(np.abs(x), np.abs(y)), 1e-12)).max(initial=0))
        group = categories.setdefault(category, {"count": 0, "max_abs": 0.0, "max_rel": 0.0,
                                                  "exact_equal": 0})
        group["count"] += 1
        group["max_abs"] = max(group["max_abs"], max_abs)
        group["max_rel"] = max(group["max_rel"], max_rel)
        group["exact_equal"] += bool(np.array_equal(x, y))
    report = {"left": args.left, "right": args.right,
              "same_generated_observations": summaries[0]["base_hashes"] == summaries[1]["base_hashes"],
              "discrete_equal": discrete_equal, "paired_within_each_path": {
                  "parent_hash": internal_parent_equal, "action": internal_action_equal,
                  "post_action_path_hash": internal_path_equal},
              "numeric_differences": numeric, "non_numeric_mismatches": mismatched,
              "scales": scale_rows, "candidate_identity_match": candidate_identity_match,
              "candidate_hash_mismatch_count": candidate_hash_mismatch_count,
              "candidate_loss_max_abs_diff": candidate_loss_max, "vector_categories": categories,
              "action_sequence_equal": summaries[0]["action_sequence"] == summaries[1]["action_sequence"]}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
