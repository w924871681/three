from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .common import array_digest, write_json
from .p3_2_data import ONSET_RAW_INDEX, make_scenario_v2, target_structure


def _longest_true_run(stages: np.ndarray, values: np.ndarray) -> int:
    longest = 0
    current = 0
    previous = None
    for stage, value in zip(stages, values):
        if bool(value) and (previous is None or int(stage) == int(previous) + 1):
            current += 1
        elif bool(value):
            current = 1
        else:
            current = 0
        longest = max(longest, current)
        previous = int(stage)
    return longest


def generator_structural_audit(bases, config: dict, output_dir: Path, phase: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for base in bases:
        for scenario in ("C0", "C3", "C4"):
            x, y, metadata = make_scenario_v2(base, scenario, config)
            values = {
                "phase": phase,
                "generator_revision": config["generator_revision"],
                "center_id": base.center_id,
                "center_type": base.center_type,
                "scenario": scenario,
                "target_sha256": array_digest(y),
                "joint_scenario_sha256": array_digest(x, y, base.ts),
                "postshift_observation_mean_abs_change_vs_native": float(
                    np.mean(np.abs(x[ONSET_RAW_INDEX:, :12] - base.x[ONSET_RAW_INDEX:, :12]))
                ),
                "definition": metadata["definition"],
                **target_structure(y),
            }
            rows.append(values)
    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "target_structural_statistics.csv", index=False)

    metrics = ("std", "range", "adjacent_rmse")
    ratios = []
    for center_id, group in frame.groupby("center_id"):
        reference = group[group.scenario == "C0"].iloc[0]
        for scenario in ("C3", "C4"):
            row = group[group.scenario == scenario].iloc[0]
            ratios.append(
                {
                    "center_id": int(center_id),
                    "scenario": scenario,
                    **{f"{metric}_ratio_vs_C0": float(row[metric] / reference[metric]) for metric in metrics},
                }
            )
    ratio_frame = pd.DataFrame(ratios)
    ratio_frame.to_csv(output_dir / "target_structural_ratios.csv", index=False)
    aggregate = {
        scenario: {
            f"mean_{metric}_ratio_vs_C0": float(
                ratio_frame[ratio_frame.scenario == scenario][f"{metric}_ratio_vs_C0"].mean()
            )
            for metric in metrics
        }
        for scenario in ("C3", "C4")
    }
    rules = config["generator_only_stop_rules"]
    checks = {
        f"{scenario}_{metric}_not_compressed": (
            aggregate[scenario][f"mean_{metric}_ratio_vs_C0"]
            >= float(rules[f"min_postshift_{metric}_ratio_vs_C0"])
        )
        for scenario in ("C3", "C4")
        for metric in metrics
    }
    for scenario in ("C3", "C4"):
        for metric in metrics:
            key = f"max_postshift_{metric}_ratio_vs_C0"
            if key in rules:
                checks[f"{scenario}_{metric}_not_inflated"] = bool(
                    aggregate[scenario][f"mean_{metric}_ratio_vs_C0"] <= float(rules[key])
                )
    c3 = frame[frame.scenario == "C3"].sort_values("center_id")
    c0 = frame[frame.scenario == "C0"].sort_values("center_id")
    target_unchanged = not any(
        key in config["c3_regime_b"]
        for key in ("load_feedback", "response_orientation")
    )
    target_hashes_equal = bool((c3.target_sha256.to_numpy() == c0.target_sha256.to_numpy()).all())
    checks["C3_target_matches_definition"] = (
        target_hashes_equal if target_unchanged else not target_hashes_equal
    )
    checks["C3_observation_mechanism_changed"] = bool(
        (c3.postshift_observation_mean_abs_change_vs_native > 0).all()
    )
    result = {
        "schema": "dt-lifecycle-escalation-p3.2-structural-audit-v1",
        "phase": phase,
        "generator_revision": config["generator_revision"],
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "aggregate_ratios": aggregate,
        "centers": sorted(int(value) for value in frame.center_id.unique()),
        "oracle_or_model_outcomes_used": False,
        "heldout_used": False,
    }
    write_json(output_dir / "generator_structural_audit.json", result)
    return result


def _center_bootstrap_difference(primary: pd.DataFrame, config: dict) -> dict:
    center_values = []
    for _, group in primary.groupby("center_id"):
        mismatch = (group[group.scenario.isin(["C3", "C4"])].R_B50 < 0).mean()
        maintainable = (group[group.scenario.isin(["C0", "C1"])].R_B50 < 0).mean()
        center_values.append(float(mismatch - maintainable))
    values = np.asarray(center_values, dtype=float)
    rng = np.random.default_rng(int(config["bootstrap_seed"]))
    indices = rng.integers(0, len(values), size=(int(config["bootstrap_repetitions"]), len(values)))
    boot = values[indices].mean(axis=1)
    return {
        "definition": "center-level mismatch minus maintainable negative-R rate; seeds/stages retained within center",
        "n_centers": int(len(values)),
        "mean_difference": float(values.mean()),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "center_differences": [float(value) for value in values],
    }


def analyze_phase(stage: pd.DataFrame, structural: pd.DataFrame, config: dict, phase: str) -> dict:
    primary_horizon = int(config["primary_recoverability_horizon"])
    primary_eta = float(config["primary_eta"])
    post = stage[(stage.stage >= 9)].copy()
    post["L_ref"] = post.tau_service / (1.0 + primary_eta)

    grid = []
    for (scenario, horizon), group in post.groupby(["scenario", "recoverability_horizon"], sort=True):
        for eta in config["eta_grid"]:
            threshold = (1.0 + float(eta)) * group.L_ref
            for budget in config["budget_subsets"]:
                negative = group[f"best_loss_{budget}"] > threshold
                grid.append(
                    {
                        "scenario": scenario,
                        "recoverability_horizon": int(horizon),
                        "eta": float(eta),
                        "budget_subset": budget,
                        "negative_R_rate": float(negative.mean()),
                        "negative_R_count": int(negative.sum()),
                        "n": int(len(group)),
                    }
                )

    primary = post[post.recoverability_horizon == primary_horizon].copy()
    scenario_summary = {}
    persistence_rows = []
    min_run = int(config["confirmatory_rules"]["persistent_interval_min_consecutive_stages"])
    for scenario, group in primary.groupby("scenario", sort=True):
        negative = group.R_B50 < 0
        conditional = group[negative]
        per_run = []
        per_run_benefit = []
        for _, run in group.groupby("run_id"):
            run = run.sort_values("stage")
            longest_negative = _longest_true_run(run.stage.to_numpy(), (run.R_B50 < 0).to_numpy())
            longest_benefit = _longest_true_run(
                run.stage.to_numpy(), ((run.R_B50 < 0) & (run.reinstantiation_gain > 0)).to_numpy()
            )
            per_run.append(longest_negative)
            per_run_benefit.append(longest_benefit)
            persistence_rows.append(
                {
                    "scenario": scenario,
                    "run_id": run.run_id.iloc[0],
                    "center_id": int(run.center_id.iloc[0]),
                    "seed": int(run.seed.iloc[0]),
                    "max_consecutive_negative_R": int(longest_negative),
                    "max_consecutive_negative_R_with_alternative_benefit": int(longest_benefit),
                }
            )
        selected = Counter(conditional.best_alternative_identity_id.astype(str))
        scenario_summary[scenario] = {
            "negative_R_rate": float(negative.mean()),
            "negative_R_count": int(negative.sum()),
            "n": int(len(group)),
            "trajectory_persistent_negative_rate": float(np.mean(np.asarray(per_run) >= min_run)),
            "median_max_consecutive_negative": float(np.median(per_run)),
            "conditional_alternative_benefit_rate": (
                float((conditional.reinstantiation_gain > 0).mean()) if len(conditional) else None
            ),
            "conditional_mean_alternative_gain": (
                float(conditional.reinstantiation_gain.mean()) if len(conditional) else None
            ),
            "negative_R_but_no_better_alternative_count": (
                int((conditional.reinstantiation_gain <= 0).sum()) if len(conditional) else 0
            ),
            "trajectory_persistent_alternative_benefit_rate": float(
                np.mean(np.asarray(per_run_benefit) >= min_run)
            ),
            "best_alternative_identity_counts_when_negative": dict(selected),
        }

    persistence = pd.DataFrame(persistence_rows)
    maintainable = primary[primary.scenario.isin(["C0", "C1"])]
    mismatch = primary[primary.scenario.isin(["C3", "C4"])]
    separation = _center_bootstrap_difference(primary, config)

    structure_index = structural.set_index(["center_id", "scenario"])
    # The generator-only structural audit deliberately covers C0/C3/C4.
    # Scale confounding is a mismatch diagnostic, so C1 must not be assigned
    # an unaudited target variance.
    mismatch_primary = primary[primary.scenario.isin(["C3", "C4"])].copy()
    normalized_negative = []
    for row in mismatch_primary.itertuples(index=False):
        scenario_variance = float(structure_index.loc[(row.center_id, row.scenario), "std"]) ** 2
        c0_variance = float(structure_index.loc[(row.center_id, "C0"), "std"]) ** 2
        normalized_loss = float(row.best_loss_B50) / scenario_variance
        normalized_tau = float(row.tau_service) / c0_variance
        normalized_negative.append(normalized_loss > normalized_tau)
    mismatch_primary["normalized_negative_R"] = normalized_negative
    normalized_summary = {
        scenario: float(group.normalized_negative_R.mean())
        for scenario, group in mismatch_primary.groupby("scenario", sort=True)
    }
    normalized_mismatch_rate = float(mismatch_primary.normalized_negative_R.mean())
    raw_mismatch_rate = float((mismatch.R_B50 < 0).mean())

    rules = config["confirmatory_rules"]
    c3_expected = "p3v2_a57_regime_b"
    c4_expected = "p3v2_a46_regime_c"
    c3_negative = primary[(primary.scenario == "C3") & (primary.R_B50 < 0)]
    c4_negative = primary[(primary.scenario == "C4") & (primary.R_B50 < 0)]
    c3_match_rate = float((c3_negative.best_alternative_identity_id == c3_expected).mean()) if len(c3_negative) else 0.0
    c4_match_rate = float((c4_negative.best_alternative_identity_id == c4_expected).mean()) if len(c4_negative) else 0.0

    verdicts = {
        "C3": (
            scenario_summary["C3"]["negative_R_rate"] >= rules["each_mismatch_negative_rate_min"]
            and scenario_summary["C3"]["trajectory_persistent_negative_rate"]
            >= rules["mismatch_persistent_interval_trajectory_rate_min"]
        ),
        "C4": (
            scenario_summary["C4"]["negative_R_rate"] >= rules["each_mismatch_negative_rate_min"]
            and scenario_summary["C4"]["trajectory_persistent_negative_rate"]
            >= rules["mismatch_persistent_interval_trajectory_rate_min"]
        ),
        "original_50_percent_gate": raw_mismatch_rate >= rules["combined_mismatch_negative_rate_min"],
        "maintainable_vs_mismatch_separation": (
            float((maintainable.R_B50 < 0).mean()) <= rules["maintainable_negative_rate_max"]
            and separation["ci_low"] > rules["separation_center_bootstrap_ci_low_min"]
        ),
        "alternative_benefit": (
            len(mismatch[mismatch.R_B50 < 0]) > 0
            and float((mismatch[mismatch.R_B50 < 0].reinstantiation_gain > 0).mean())
            >= rules["conditional_reinstantiation_benefit_rate_min"]
            and float(mismatch[mismatch.R_B50 < 0].reinstantiation_gain.mean())
            > rules["conditional_mean_reinstantiation_gain_min"]
            and np.mean(
                [
                    scenario_summary[name]["trajectory_persistent_alternative_benefit_rate"]
                    for name in ("C3", "C4")
                ]
            )
            >= rules["mismatch_persistent_alternative_benefit_trajectory_rate_min"]
        ),
        "mechanism_matched_alternatives": (
            c3_match_rate >= rules["mechanism_matched_alternative_rate_min"]
            and c4_match_rate >= rules["mechanism_matched_alternative_rate_min"]
        ),
        "scale_confounding": (
            normalized_mismatch_rate >= rules["normalized_mismatch_negative_rate_min"]
            and abs(normalized_mismatch_rate - raw_mismatch_rate)
            <= rules["max_raw_vs_normalized_mismatch_rate_gap"]
        ),
    }
    verdicts = {name: bool(passed) for name, passed in verdicts.items()}
    overall = "PASS" if all(verdicts.values()) else "FAIL"
    result = {
        "schema": "dt-lifecycle-escalation-p3.2-analysis-v1",
        "phase": phase,
        "overall_verdict": overall,
        "primary_setting": {"H_R": primary_horizon, "eta": primary_eta, "budget": "B50"},
        "scenario_summary": scenario_summary,
        "maintainable_negative_R_rate": float((maintainable.R_B50 < 0).mean()),
        "mismatch_negative_R_rate": raw_mismatch_rate,
        "mismatch_conditional_alternative_benefit_rate": (
            float((mismatch[mismatch.R_B50 < 0].reinstantiation_gain > 0).mean())
            if len(mismatch[mismatch.R_B50 < 0])
            else None
        ),
        "mismatch_conditional_mean_alternative_gain": (
            float(mismatch[mismatch.R_B50 < 0].reinstantiation_gain.mean())
            if len(mismatch[mismatch.R_B50 < 0])
            else None
        ),
        "mismatch_negative_R_but_no_better_alternative_count": int(
            ((mismatch.R_B50 < 0) & (mismatch.reinstantiation_gain <= 0)).sum()
        ),
        "separation_center_bootstrap": separation,
        "normalized_loss_diagnostic": {
            "definition": "scenario MSE divided by scenario post-shift target variance; tau divided by matched C0 variance",
            "scenario_negative_rates": normalized_summary,
            "mismatch_negative_R_rate": normalized_mismatch_rate,
            "raw_minus_normalized_mismatch_rate": raw_mismatch_rate - normalized_mismatch_rate,
            "primary_verdict_unchanged": True,
        },
        "mechanism_match_rates_when_negative": {"C3": c3_match_rate, "C4": c4_match_rate},
        "verdicts": verdicts,
        "grid": grid,
        "persistence_rows": persistence_rows,
        "estimator_fitted": False,
        "gate_calibrated": False,
        "proposed_executed": False,
        "heldout_accessed": False,
    }
    return result
