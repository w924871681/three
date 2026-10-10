from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core.common import ROOT, canonical_hash, sha256_file, write_json
from core.data import generate_base_centers
from core.models import bank_hash, feasible
from core.p3_2_analysis import analyze_phase, generator_structural_audit
from core.p3_2_audits import run_p3_2_audits
from core.p3_2_models import build_p3_2_identity_bank, train_source_assets
from core.p3_2_oracle import reference_loss_v2, run_p3_2_trajectory


CONFIG_PATH = ROOT / "configs" / "p3_2_protocol.json"
REVISION_ROOT = ROOT / "results" / "p3_2a" / "revisions" / "p3_mismatch_v2_r1"
FRESH_ROOT = ROOT / "results" / "p3_2b"
FROZEN_CONFIG = ROOT / "configs" / "p3_mismatch_v2_frozen.json"
FROZEN_HASH = ROOT / "audits" / "p3_mismatch_v2_frozen.sha256"


def source_manifest_path(config: dict) -> Path:
    directory = ROOT / "artifacts" / "p3_2_source_bank"
    if config["generator_revision"] != "p3_mismatch_v2_r1":
        directory = directory / config["generator_revision"]
    return directory / "source_training_manifest.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_protocol(path: Path) -> dict:
    config = load_json(path)
    if "base_config" in config:
        base_path = ROOT / config.pop("base_config")
        base = load_protocol(base_path)
        for key, value in config.items():
            if key == "c3_regime_b":
                base[key] = {**base[key], **value}
            else:
                base[key] = value
        return base
    return config


def select_revision(revision: str) -> None:
    global CONFIG_PATH, REVISION_ROOT
    if revision in ("r2", "r3"):
        CONFIG_PATH = ROOT / "configs" / f"p3_2_protocol_{revision}.json"
        REVISION_ROOT = ROOT / "results" / "p3_2a" / "revisions" / f"p3_mismatch_v2_{revision}"


def _format(value) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def markdown_table(rows: list[dict], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = [
        "| " + " | ".join(_format(row.get(column)) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, rule, *body])


def validate_config(config: dict) -> None:
    forbidden_true = (
        "estimator_fitting_forbidden",
        "gate_calibration_forbidden",
        "proposed_execution_forbidden",
        "baseline_comparison_forbidden",
        "alibaba_forbidden",
        "heldout_forbidden",
    )
    if not all(config.get(key) is True for key in forbidden_true):
        raise RuntimeError("P3.2 refuses to run unless every forbidden-scope flag is true")
    if config["primary_recoverability_horizon"] != 4 or config["primary_eta"] != 0.25:
        raise RuntimeError("primary H_R/eta changed from the approved setting")
    if config["local_policies"] != [0, 10, 20, 50]:
        raise RuntimeError("approved local policy set changed")
    pools = [
        set(config["source_pair"]["source_centers"]),
        set(config["design_centers"]),
        set(config["fresh_development_centers"]),
        set(config["calibration_centers_forbidden"]),
        set(config["heldout_centers_forbidden"]),
    ]
    if any(left & right for index, left in enumerate(pools) for right in pools[index + 1 :]):
        raise RuntimeError("P3.2 center pools overlap")


def prepare_structural_only() -> dict:
    config = load_protocol(CONFIG_PATH)
    validate_config(config)
    REVISION_ROOT.mkdir(parents=True, exist_ok=True)
    config_snapshot = REVISION_ROOT / f"{config['generator_revision']}_config.json"
    if not config_snapshot.exists():
        write_json(config_snapshot, config)
    elif canonical_hash(load_json(config_snapshot)) != canonical_hash(config):
        raise RuntimeError("revision config snapshot differs from the current protocol")

    bases = generate_base_centers(config["design_centers"], data_seed=config["data_seed"])
    structural = generator_structural_audit(
        bases, config, REVISION_ROOT / "structural", phase="p3_2a"
    )
    if structural["status"] != "PASS":
        write_p3_2a_report(config, structural, None, None, None, frozen=False)
        raise RuntimeError("P3.2a generator-only structural audit failed; oracle was not run")
    return config


def prepare() -> tuple[dict, dict, list]:
    config = prepare_structural_only()
    source_manifest = train_source_assets(config)
    identities = build_p3_2_identity_bank(source_manifest)
    return config, source_manifest, identities


def _completed_trajectory(paths: dict, run_id: str) -> tuple[list[dict], list[dict], list[dict], dict] | None:
    if not all(path.exists() for path in paths.values()):
        return None
    stage = pd.read_csv(paths["stage"])
    candidates = pd.read_csv(paths["candidate"])
    policies = pd.read_csv(paths["policy"])
    audit = load_json(paths["audit"])
    if len(stage) != 72 or len(policies) != 72 or set(stage.run_id) != {run_id}:
        raise RuntimeError(f"invalid resumable trajectory artifact: {run_id}")
    return (
        stage.to_dict("records"),
        candidates.to_dict("records"),
        policies.to_dict("records"),
        audit,
    )


def run_phase(
    config: dict,
    source_manifest: dict,
    identities,
    bases,
    output_root: Path,
    phase: str,
    center_pool: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict], dict, dict]:
    raw_dir = output_root / "raw"
    candidate_dir = output_root / "candidates"
    policy_dir = output_root / "per_policy"
    run_audit_dir = output_root / "run_audits"
    for path in (raw_dir, candidate_dir, policy_dir, run_audit_dir):
        path.mkdir(parents=True, exist_ok=True)

    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    tau_path = output_root / "tau_service_development.json"
    if tau_path.exists():
        tau_rows = load_json(tau_path)
    else:
        tau_rows = {}
        for base in bases:
            for seed in config["model_seeds"]:
                reference = reference_loss_v2(base, int(seed), incumbent, config)
                tau_rows[f"{base.center_id}:{seed}"] = {
                    "center_id": base.center_id,
                    "seed": int(seed),
                    "L_ref": reference,
                    "eta": config["primary_eta"],
                    "tau_service": (1.0 + config["primary_eta"]) * reference,
                }
        write_json(tau_path, tau_rows)

    all_stage: list[dict] = []
    all_candidates: list[dict] = []
    all_policies: list[dict] = []
    all_run_audits: list[dict] = []
    total = len(config["scenarios"]) * len(bases) * len(config["model_seeds"])
    completed = 0
    started = time.perf_counter()
    status_path = output_root / "execution_status.json"

    for scenario in config["scenarios"]:
        for base in bases:
            for seed_value in config["model_seeds"]:
                seed = int(seed_value)
                run_id = f"{phase}-{scenario}-{base.center_id}-{seed}"
                stem = f"{scenario}_{base.center_id}_{seed}"
                paths = {
                    "stage": raw_dir / f"{stem}.csv",
                    "candidate": candidate_dir / f"{stem}.csv",
                    "policy": policy_dir / f"{stem}.csv",
                    "audit": run_audit_dir / f"{stem}.json",
                }
                resumed = _completed_trajectory(paths, run_id)
                if resumed is None:
                    tau = float(tau_rows[f"{base.center_id}:{seed}"]["tau_service"])
                    result = run_p3_2_trajectory(
                        base,
                        seed,
                        scenario,
                        identities,
                        config,
                        tau,
                        phase,
                        center_pool,
                    )
                    pd.DataFrame(result.stage_rows).to_csv(paths["stage"], index=False)
                    pd.DataFrame(result.candidate_rows).to_csv(paths["candidate"], index=False)
                    pd.DataFrame(result.policy_rows).to_csv(paths["policy"], index=False)
                    write_json(paths["audit"], result.run_audit)
                    resumed = (
                        result.stage_rows,
                        result.candidate_rows,
                        result.policy_rows,
                        result.run_audit,
                    )
                stage_rows, candidate_rows, policy_rows, run_audit = resumed
                all_stage.extend(stage_rows)
                all_candidates.extend(candidate_rows)
                all_policies.extend(policy_rows)
                all_run_audits.append(run_audit)
                completed += 1
                elapsed = time.perf_counter() - started
                print(
                    f"[P3.2] phase={phase} completed={completed}/{total} "
                    f"last={run_id} elapsed_s={elapsed:.1f}",
                    flush=True,
                )
                write_json(
                    status_path,
                    {
                        "status": "RUNNING",
                        "phase": phase,
                        "completed": completed,
                        "expected": total,
                        "last_run_id": run_id,
                        "elapsed_seconds_current_invocation": elapsed,
                        "heldout_accessed": False,
                    },
                )

    stage = pd.DataFrame(all_stage)
    candidates = pd.DataFrame(all_candidates)
    policies = pd.DataFrame(all_policies)
    stage.to_csv(output_root / "stage_records.csv", index=False)
    candidates.to_csv(output_root / "candidate_records.csv", index=False)
    policies.to_csv(output_root / "per_policy_horizon_losses.csv", index=False)
    write_json(output_root / "run_audits.json", all_run_audits)
    audit = run_p3_2_audits(
        all_stage,
        all_candidates,
        all_run_audits,
        identities,
        config,
        [base.center_id for base in bases],
        phase,
    )
    write_json(output_root / "scientific_audit.json", audit)
    if audit["status"] != "PASS":
        write_json(
            status_path,
            {"status": "STOPPED_AUDIT_FAIL", "phase": phase, "heldout_accessed": False},
        )
        raise RuntimeError(f"{phase} scientific/leakage/fairness audit failed")
    write_json(
        status_path,
        {
            "status": "COMPLETED",
            "phase": phase,
            "completed": completed,
            "expected": total,
            "elapsed_seconds_current_invocation": time.perf_counter() - started,
            "heldout_accessed": False,
        },
    )
    scenario_manifest = {
        "schema": "dt-lifecycle-escalation-p3.2-scenario-manifest-v1",
        "phase": phase,
        "generator_revision": config["generator_revision"],
        "bank_hash": bank_hash(identities),
        "source_training_manifest_sha256": sha256_file(source_manifest_path(config)),
        "centers": {
            str(base.center_id): {
                "center_type": base.center_type,
                "budget_tier": base.budget_tier,
                "scenario_hashes": {
                    scenario: str(
                        stage[
                            (stage.center_id == base.center_id) & (stage.scenario == scenario)
                        ].scenario_hash.iloc[0]
                    )
                    for scenario in config["scenarios"]
                },
            }
            for base in bases
        },
        "heldout_materialized": False,
        "heldout_accessed": False,
    }
    write_json(output_root / "scenario_manifest.json", scenario_manifest)
    return stage, candidates, policies, all_run_audits, audit, scenario_manifest


def _summary_rows(analysis: dict) -> list[dict]:
    rows = []
    for scenario, values in analysis["scenario_summary"].items():
        rows.append(
            {
                "scenario": scenario,
                "negative_R_rate": values["negative_R_rate"],
                "negative_R_count/n": f"{values['negative_R_count']}/{values['n']}",
                "persistent_trajectory_rate": values["trajectory_persistent_negative_rate"],
                "alt_benefit_when_negative": values["conditional_alternative_benefit_rate"],
                "mean_alt_gain_when_negative": values["conditional_mean_alternative_gain"],
                "R<0_no_better_alt": values["negative_R_but_no_better_alternative_count"],
            }
        )
    return rows


def write_p3_2a_report(config, structural, source_manifest, analysis, audit, frozen: bool) -> None:
    aggregate_rows = [
        {"scenario": scenario, **values}
        for scenario, values in structural["aggregate_ratios"].items()
    ]
    if source_manifest:
        source_rows = [
            {
                "identity": item["identity_id"],
                "architecture": item["architecture"],
                "regime": item["regime"],
                "checkpoint_sha256": item["checkpoint_sha256"],
                "source_validation_mse": item["source_validation_mse"],
            }
            for item in source_manifest["assets"]
        ]
        source_table = markdown_table(
            source_rows,
            ["identity", "architecture", "regime", "source_validation_mse", "checkpoint_sha256"],
        )
    else:
        source_table = "Not run because the generator-only structural stop rule fired."
    result_table = (
        markdown_table(
            _summary_rows(analysis),
            [
                "scenario",
                "negative_R_rate",
                "negative_R_count/n",
                "persistent_trajectory_rate",
                "alt_benefit_when_negative",
                "mean_alt_gain_when_negative",
                "R<0_no_better_alt",
            ],
        )
        if analysis
        else "Oracle phenomenon analysis was not run."
    )
    if analysis:
        primary_grid = [
            row for row in analysis["grid"]
            if row["recoverability_horizon"] == 4 and row["eta"] == 0.25
        ]
        budget_table = markdown_table(
            primary_grid,
            ["scenario", "budget_subset", "negative_R_rate", "negative_R_count", "n"],
        )
        sensitivity_table = markdown_table(
            [row for row in analysis["grid"] if row["budget_subset"] == "B50"],
            ["scenario", "recoverability_horizon", "eta", "negative_R_rate", "negative_R_count", "n"],
        )
        verdict_table = markdown_table(
            [{"gate": key, "verdict": value} for key, value in analysis["verdicts"].items()],
            ["gate", "verdict"],
        )
        separation = analysis["separation_center_bootstrap"]
        normalized = analysis["normalized_loss_diagnostic"]
        numerical_diagnostics = (
            f"C0/C1 negative-R={_format(analysis['maintainable_negative_R_rate'])}; "
            f"C3/C4 negative-R={_format(analysis['mismatch_negative_R_rate'])}. "
            f"Center-bootstrap separation={_format(separation['mean_difference'])}, "
            f"95% CI [{_format(separation['ci_low'])}, {_format(separation['ci_high'])}] "
            f"over {separation['n_centers']} design centers. Conditional feasible "
            f"re-instantiation benefit rate={_format(analysis['mismatch_conditional_alternative_benefit_rate'])}, "
            f"mean gain={_format(analysis['mismatch_conditional_mean_alternative_gain'])}; "
            f"R<0 with no better alternative={analysis['mismatch_negative_R_but_no_better_alternative_count']} "
            f"(retained). C3/C4 normalized diagnostic negative-R="
            f"{_format(normalized['mismatch_negative_R_rate'])}, raw-minus-normalized="
            f"{_format(normalized['raw_minus_normalized_mismatch_rate'])}; "
            f"by scenario C3={_format(normalized['scenario_negative_rates']['C3'])}, "
            f"C4={_format(normalized['scenario_negative_rates']['C4'])}. "
            "This reveals C4 service-scale sensitivity even though the C3 effect "
            "is stable under normalization. The formal decision uses raw MSE and "
            "the unchanged tau_svc; the combined scale gate passes close to its limit."
        )
    else:
        budget_table = sensitivity_table = verdict_table = numerical_diagnostics = "Not run."
    revision_rationales = {
        "p3_mismatch_v2_r1": "replace teacher-output blending with direct telemetry-regime C3 and nonlinear multi-lag C4",
        "p3_mismatch_v2_r2": "test causal load-feedback C3; rejected before models because it inflated target scale/roughness",
        "p3_mismatch_v2_r3": "replace C3 response orientation at near-preserved target scale/dynamics",
    }
    revision_rows = []
    revision_parent = ROOT / "results" / "p3_2a" / "revisions"
    for path in sorted(revision_parent.glob("p3_mismatch_v2_r*")):
        audit_path = path / "structural" / "generator_structural_audit.json"
        if not audit_path.exists():
            continue
        structural_result = load_json(audit_path)
        outcome_path = path / "analysis.json"
        outcome = load_json(outcome_path)["overall_verdict"] if outcome_path.exists() else "NOT RUN"
        revision_rows.append({
            "revision": path.name,
            "mechanism_rationale": revision_rationales.get(path.name, "see revision config"),
            "structural": structural_result["status"],
            "oracle": outcome,
            "action": "freeze" if path == REVISION_ROOT and frozen else "retain evidence; do not freeze",
        })
    revision_table = markdown_table(
        revision_rows, ["revision", "mechanism_rationale", "structural", "oracle", "action"]
    )
    overall = analysis["overall_verdict"] if analysis else "FAIL"
    report = f"""# P3.2a Generator Redesign

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: run + validate
- Origin Date: {datetime.now(timezone.utc).date().isoformat()}
- Verification Status: {"VERIFIED" if audit and audit['status'] == 'PASS' else "ANALYZED"}
- Version Label: p3_2a_generator_redesign_v1
- Generator Revision: `{config['generator_revision']}`
- Overall Verdict: **{overall}**

## 1. Scope and safeguards

P3.2a used only design centers `{config['design_centers']}` and seeds `{config['model_seeds']}`. No recoverability estimator, gate calibration, Proposed method, baseline comparison, Alibaba data, calibration center, or held-out center was used. The first- and second-paper repositories were read only.

## 2. Source-identity provenance finding

The prior names `msa_a57_pt` and `msa_a57_medet` do **not** establish a source-domain mismatch. The upstream frozen source manifest shows that both were produced from source centers 0–19 with the same source generator; they differ by training procedure (ordinary pretraining versus MeDeT-style meta-training). P3.2 therefore does not use the checkpoint names as evidence of different source-generating regimes.

A new controlled same-architecture pair was constructed. The native `msa_a57_pt` remains the regime-A GRU-32 incumbent. `p3v2_a57_regime_b` is the same GRU-32 architecture trained only on a directly defined regime B: a fixed telemetry channel-semantic permutation plus monotone per-channel calibration and the revision-specific response rule (`{config['c3_regime_b']['mechanism']}`). The source pool is disjoint from all P3.2 target-side pools.

## 3. Mechanism definitions

- C3: direct A→B source-domain replacement at stage 9. It splices the generated joint telemetry regime; it never interpolates predictions or labels from a teacher model.
- C4: direct replacement of the target dependency with the prespecified nonlinear multi-lag equation using lags `{config['c4_regime_c']['lags']}`. `p3v2_a46_regime_c` is a TCN source initialization trained on this regime; `p3v2_a57_regime_c_control` is a same-regime GRU control retained in the candidate bank.
- C0 and C1 retain their earlier native/stable and within-family gradual mechanisms.

## 4. Generator-only structural audit (performed before model/oracle outcomes)

{markdown_table(aggregate_rows, ['scenario', 'mean_std_ratio_vs_C0', 'mean_range_ratio_vs_C0', 'mean_adjacent_rmse_ratio_vs_C0'])}

Status: **{structural['status']}**. Raw mean, SD, range, adjacent-step RMSE, lag correlations, spectral peak/periodicity summaries, target hashes, and observation-shift magnitude are in `{(REVISION_ROOT / 'structural').relative_to(ROOT).as_posix()}/`.

## 5. New source assets

{source_table}

Source validation values are provenance/quality records only; they were not used to tune the generator.

## 6. Design-pool offline oracle phenomenon

Primary setting remains `H_R=4`, `eta=0.25`, B50=`{{P0,P10,P20,P50}}`.

{result_table}

The complete `H_R × eta × B0/B10/B20/B50` grid is saved in the analysis JSON and per-policy raw table. No losing-policy loss is missing in P3.2.

Primary numerical diagnostics: {numerical_diagnostics}

## 7. Exact maintenance-budget subsets at the frozen primary setting

{budget_table}

`J(P0)`, `J(P10)`, `J(P20)`, `J(P50)`, exact subset minima and winning policies are in `{(REVISION_ROOT / 'per_policy_horizon_losses.csv').relative_to(ROOT).as_posix()}`. `R_B0/R_B10/R_B20/R_B50` are in the stage records. No easier sensitivity combination replaces `H_R=4, eta=0.25`.

## 8. Full prespecified horizon and service-margin sensitivity (B50)

{sensitivity_table}

## 9. Preregistered decision gates

{verdict_table}

The combined C3/C4 `>=50%` negative-R gate remains mandatory even when it fails. Persistent interval rates and mechanism-matched feasible alternative rates are in the analysis JSON. Negative-R cases without a better alternative remain in all denominators.

## 10. Revision ledger and freeze decision

{revision_table}

Scientific/leakage/fairness audit: **{audit['status'] if audit else 'NOT RUN'}**.

## 11. Scope of inference and disposition

This is a controlled generator intervention, not evidence of natural mismatch prevalence. Center-level bootstrap retains seed/stage clustering; scenario and budget denominators are explicit. The design pool is separate from the precommitted fresh-development pool, which has not been accessed for generator design.

**{overall}**. {"The generator, source assets, primary oracle setting, policy family, and six prespecified fresh-development center IDs were frozen before P3.2b." if frozen else "P3.2b was not authorized because P3.2a did not pass."}
"""
    (ROOT / "reports" / "P3_2A_GENERATOR_REDESIGN.md").write_text(report, encoding="utf-8")
    REVISION_ROOT.mkdir(parents=True, exist_ok=True)
    (REVISION_ROOT / "generator_redesign_report.md").write_text(report, encoding="utf-8")


def write_p3_2b_report(config, structural, analysis, audit, freeze_sha: str) -> None:
    structural_table = markdown_table(
        [{"scenario": name, **values} for name, values in structural["aggregate_ratios"].items()],
        ["scenario", "mean_std_ratio_vs_C0", "mean_range_ratio_vs_C0", "mean_adjacent_rmse_ratio_vs_C0"],
    )
    stage = pd.read_csv(FRESH_ROOT / "stage_records.csv")
    primary = stage[
        (stage.stage >= 9)
        & (stage.recoverability_horizon == config["primary_recoverability_horizon"])
    ].copy()
    primary["negative_R"] = primary.R_B50 < 0
    stratified = primary.groupby(["center_id", "scenario"]).negative_R.agg(["sum", "size"])
    center_metadata = load_json(FRESH_ROOT / "scenario_manifest.json")["centers"]
    center_rows = []
    for center_id in config["fresh_development_centers"]:
        metadata = center_metadata[str(center_id)]
        row = {
            "center_id": int(center_id),
            "center_type": metadata["center_type"],
            "budget_tier": metadata["budget_tier"],
        }
        for scenario in ("C0", "C1", "C3", "C4"):
            values = stratified.loc[(center_id, scenario)]
            row[scenario] = f"{int(values['sum'])}/{int(values['size'])}"
        center_rows.append(row)
    center_table = markdown_table(
        center_rows, ["center_id", "center_type", "budget_tier", "C0", "C1", "C3", "C4"]
    )
    summary_table = markdown_table(
        _summary_rows(analysis),
        [
            "scenario",
            "negative_R_rate",
            "negative_R_count/n",
            "persistent_trajectory_rate",
            "alt_benefit_when_negative",
            "mean_alt_gain_when_negative",
            "R<0_no_better_alt",
        ],
    )
    primary_grid = [
        row
        for row in analysis["grid"]
        if row["recoverability_horizon"] == 4 and row["eta"] == 0.25
    ]
    grid_table = markdown_table(
        primary_grid,
        ["scenario", "budget_subset", "negative_R_rate", "negative_R_count", "n"],
    )
    b50_grid = [row for row in analysis["grid"] if row["budget_subset"] == "B50"]
    b50_table = markdown_table(
        b50_grid,
        ["scenario", "recoverability_horizon", "eta", "negative_R_rate", "negative_R_count", "n"],
    )
    separation = analysis["separation_center_bootstrap"]
    normalized = analysis["normalized_loss_diagnostic"]
    verdicts = analysis["verdicts"]
    overall = analysis["overall_verdict"]
    c4_raw = analysis["scenario_summary"]["C4"]["negative_R_rate"]
    c4_normalized = normalized["scenario_negative_rates"]["C4"]
    c4_scale_gap = c4_normalized - c4_raw
    c4_scale_note = (
        "material sensitivity that warrants caution"
        if abs(c4_scale_gap) > 0.15
        else "a modest shift that does not explain the C4 primary failure"
    )
    report = f"""# P3.2b Fresh-Development Confirmation

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: run + validate
- Origin Date: {datetime.now(timezone.utc).date().isoformat()}
- Verification Status: VERIFIED
- Version Label: p3_2b_fresh_development_confirmation_v1
- Frozen Generator SHA-256: `{freeze_sha}`
- Overall Verdict: **{overall}**

## 1. Confirmatory boundary

The frozen generator was run once on the six precommitted fresh-development centers `{config['fresh_development_centers']}` with seeds `{config['model_seeds']}`. These centers are disjoint from the P3/P3.1/P3.2a design centers, calibration pool, and final held-out pool. No generator parameter was changed after viewing these outcomes. No estimator, gate, Proposed method, baseline, Alibaba trace, calibration center, or held-out center was accessed.

## 2. Generator-only structural confirmation

Status: **{structural['status']}**. C3 uses the frozen source-regime response definition (`{config['c3_regime_b']['mechanism']}`) and changes the observation mechanism; C4 does not breach the frozen smoothing/compression thresholds.

{structural_table}

Complete mean/SD/range/roughness, selected ACF lags, and spectral summaries are in `results/p3_2b/structural/`. These statistics were checked before oracle outcomes.

## 3. Primary raw-MSE oracle results

Primary setting: `H_R=4`, `eta=0.25`, `tau_svc=(1+eta)L_ref`, B50=`{{P0,P10,P20,P50}}`.

{summary_table}

- Maintainable C0/C1 negative-R rate: {_format(analysis['maintainable_negative_R_rate'])}.
- Mismatch C3/C4 negative-R rate: {_format(analysis['mismatch_negative_R_rate'])}.
- Center-clustered mismatch-minus-maintainable difference: {_format(separation['mean_difference'])}, 95% bootstrap CI [{_format(separation['ci_low'])}, {_format(separation['ci_high'])}], `n={separation['n_centers']}` centers.
- Conditional alternative-benefit rate when mismatch R<0: {_format(analysis['mismatch_conditional_alternative_benefit_rate'])}; mean gain: {_format(analysis['mismatch_conditional_mean_alternative_gain'])}.
- Mismatch rows with R<0 but no better feasible alternative: {analysis['mismatch_negative_R_but_no_better_alternative_count']} (retained, not deleted).

Fresh-center primary negative-R counts, each out of 48 seed×post-shift-stage records:

{center_table}

C4 is strongly heterogeneous across centers (including 0/48 in both loose-tier centers and 48/48 in two tight-tier centers). This descriptive association is not a preregistered subgroup verdict and does not establish that resource tier causes the failure. It shows why the pooled C3/C4 >=50% result cannot stand in for C4 replication. C3 is 48/48 at every fresh center; this is a deliberately strong synthetic response-orientation stress condition, not a prevalence estimate.

## 4. Exact local-maintenance budget subsets

{grid_table}

All four `J(P)` values, exact subset minima, `best_policy_B0/B10/B20/B50`, and `R_B0/R_B10/R_B20/R_B50` are in `results/p3_2b/per_policy_horizon_losses.csv`.

## 5. Prespecified H_R and eta sensitivity (B50)

{b50_table}

The primary setting was not selected from this grid.

## 6. Confirmatory questions

1. C0/C1 predominantly recoverable: **{_format(verdicts['maintainable_vs_mismatch_separation'])}** under the preregistered rate and center-bootstrap separation gate.
2. C3 persistent negative-R intervals: **{_format(verdicts['C3'])}**.
3. C4 has persistent negative-R intervals in {_format(analysis['scenario_summary']['C4']['trajectory_persistent_negative_rate'])} of its trajectories, but its overall 123/288={_format(c4_raw)} negative-R rate is below the prespecified 0.50 single-scenario threshold: **{_format(verdicts['C4'])}**.
4. C3/C4 higher negative-R than C0/C1: difference and center-cluster bootstrap CI reported above; verdict **{_format(verdicts['maintainable_vs_mismatch_separation'])}**.
5. Original combined C3/C4 `>=50%` gate: **{_format(verdicts['original_50_percent_gate'])}**.
6. Better feasible re-instantiation when R<0: **{_format(verdicts['alternative_benefit'])}**.
7. R<0 without a better alternative: {analysis['mismatch_negative_R_but_no_better_alternative_count']} records, retained.
8. Budget sensitivity: reported exactly for B0/B10/B20/B50 above and in the full grid.
9. Dependence on target scale: combined prespecified diagnostic gate **{_format(verdicts['scale_confounding'])}**; per-scenario scale sensitivity is stated below.

Mechanism-matched alternative selection when R<0: C3={_format(analysis['mechanism_match_rates_when_negative']['C3'])}, C4={_format(analysis['mechanism_match_rates_when_negative']['C4'])}; joint verdict **{_format(verdicts['mechanism_matched_alternatives'])}**.

## 7. Scale diagnostic (secondary; does not replace primary)

The diagnostic normalizes scenario MSE by its own post-shift target variance and normalizes `tau_svc` by matched C0 variance. Its combined mismatch negative-R rate is {_format(normalized['mismatch_negative_R_rate'])}, versus raw {_format(analysis['mismatch_negative_R_rate'])}; raw-minus-normalized difference is {_format(normalized['raw_minus_normalized_mismatch_rate'])}. Per-scenario normalized negative-R rates are C3={_format(normalized['scenario_negative_rates']['C3'])}, C4={_format(c4_normalized)}. The C4 normalized-minus-raw difference is {_format(c4_scale_gap)}: {c4_scale_note}. The formal verdict above remains raw-MSE based.

## 8. Scientific integrity

Scientific/leakage/fairness audit: **{audit['status']}**. The schema omits `probe_effort`; the only response features retained are `gain,residual`. All per-policy horizon losses are persisted. All trajectories completed; no outcome-based center replacement occurred.

Interpretation safeguards: the center-stratified counts above expose heterogeneity rather than hiding it in a pooled average; all 72 trajectories and all negative-R rows remain in their denominators; the full prespecified grid prevents selecting a favorable H/eta after the fact; design and fresh-development pools are separate; causal claims are confined to the controlled synthetic generator. These selected development centers do not establish natural mismatch prevalence.

Traceability note: the `scenario_hash` in stage records and scenario manifest fingerprints the scenario *metadata*, so it is not a cross-center raw-data checksum. Actual C0/C3/C4 target and joint-data digests are in the generator-only structural table; this naming limitation does not enter the oracle or verdict calculations.

## 9. Required verdicts

- C3 verdict: **{"PASS" if verdicts['C3'] else "FAIL"}**
- C4 verdict: **{"PASS" if verdicts['C4'] else "FAIL"}**
- Original `>=50%` gate verdict: **{"PASS" if verdicts['original_50_percent_gate'] else "FAIL"}**
- Maintainable-vs-mismatch separation verdict: **{"PASS" if verdicts['maintainable_vs_mismatch_separation'] else "FAIL"}**
- Alternative-benefit verdict: **{"PASS" if verdicts['alternative_benefit'] else "FAIL"}**
- Scale-confounding verdict: **{"PASS" if verdicts['scale_confounding'] else "FAIL"}**

## 10. Final disposition

**P3.2b {overall}.** The combined >=50% gate passes largely because C3 is 288/288 negative-R; it does not override the C4 single-scenario failure. Stop after P3.2b. Do not enter P4; await manual scientific review.
"""
    (ROOT / "reports" / "P3_2B_FRESH_DEVELOPMENT_CONFIRMATION.md").write_text(report, encoding="utf-8")


def freeze(config: dict, source_manifest: dict, analysis: dict, audit: dict) -> str:
    if analysis["overall_verdict"] != "PASS" or audit["status"] != "PASS":
        raise RuntimeError("cannot freeze a failed P3.2a revision")
    if FROZEN_CONFIG.exists() or FROZEN_HASH.exists():
        raise FileExistsError("frozen P3.2 generator already exists; refusing to overwrite")
    frozen = {
        **config,
        "frozen_label": config["frozen_label_on_pass"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "revision_config_sha256": sha256_file(CONFIG_PATH),
        "source_training_manifest_sha256": sha256_file(source_manifest_path(config)),
        "source_training_manifest_path": source_manifest_path(config).relative_to(ROOT).as_posix(),
        "p3_2a_analysis_sha256": sha256_file(REVISION_ROOT / "analysis.json"),
        "p3_2a_scientific_audit_sha256": sha256_file(REVISION_ROOT / "scientific_audit.json"),
        "fresh_development_centers_committed_before_confirmation": config[
            "fresh_development_centers"
        ],
        "generator_modification_after_confirmation_forbidden": True,
    }
    write_json(FROZEN_CONFIG, frozen)
    digest = sha256_file(FROZEN_CONFIG)
    FROZEN_HASH.write_text(
        f"{digest}  configs/p3_mismatch_v2_frozen.json\n"
        f"{frozen['source_training_manifest_sha256']}  {frozen['source_training_manifest_path']}\n"
        f"{frozen['p3_2a_analysis_sha256']}  {(REVISION_ROOT / 'analysis.json').relative_to(ROOT).as_posix()}\n"
        f"{frozen['p3_2a_scientific_audit_sha256']}  {(REVISION_ROOT / 'scientific_audit.json').relative_to(ROOT).as_posix()}\n",
        encoding="utf-8",
    )
    return digest


def validate_freeze() -> tuple[dict, str]:
    if not FROZEN_CONFIG.exists() or not FROZEN_HASH.exists():
        raise FileNotFoundError("P3.2 frozen generator artifacts are missing")
    expected = FROZEN_HASH.read_text(encoding="utf-8").splitlines()[0].split()[0]
    actual = sha256_file(FROZEN_CONFIG)
    if expected != actual:
        raise RuntimeError("frozen generator SHA-256 mismatch")
    config = load_json(FROZEN_CONFIG)
    validate_config(config)
    return config, actual


def execute_design() -> tuple[dict, dict, dict, str | None]:
    config, source_manifest, identities = prepare()
    bases = generate_base_centers(config["design_centers"], data_seed=config["data_seed"])
    stage, _, _, _, audit, _ = run_phase(
        config,
        source_manifest,
        identities,
        bases,
        REVISION_ROOT,
        phase="p3_2a",
        center_pool="generator_design",
    )
    analysis_path = REVISION_ROOT / "analysis.json"
    freeze_sha = None
    if FROZEN_CONFIG.exists():
        frozen, freeze_sha = validate_freeze()
        if (
            frozen["generator_revision"] != config["generator_revision"]
            or frozen["p3_2a_analysis_sha256"] != sha256_file(analysis_path)
            or frozen["source_training_manifest_sha256"] != sha256_file(source_manifest_path(config))
        ):
            raise RuntimeError("existing frozen generator disagrees with completed design artifacts")
        analysis = load_json(analysis_path)
        if analysis["overall_verdict"] != "PASS":
            raise RuntimeError("frozen generator has a failed design verdict")
    else:
        structural_frame = pd.read_csv(REVISION_ROOT / "structural" / "target_structural_statistics.csv")
        analysis = analyze_phase(stage, structural_frame, config, phase="p3_2a")
        write_json(analysis_path, analysis)
        pd.DataFrame(analysis["grid"]).to_csv(REVISION_ROOT / "recoverability_grid.csv", index=False)
        pd.DataFrame(analysis["persistence_rows"]).to_csv(REVISION_ROOT / "persistence_by_trajectory.csv", index=False)
        if analysis["overall_verdict"] == "PASS":
            freeze_sha = freeze(config, source_manifest, analysis, audit)
    write_p3_2a_report(
        config,
        load_json(REVISION_ROOT / "structural" / "generator_structural_audit.json"),
        source_manifest,
        analysis,
        audit,
        frozen=freeze_sha is not None,
    )
    return config, source_manifest, analysis, freeze_sha


def execute_design_analysis_only() -> tuple[dict, dict, dict, str | None]:
    """Finalize completed design outputs without constructing any trajectory."""
    status = load_json(REVISION_ROOT / "execution_status.json")
    audit = load_json(REVISION_ROOT / "scientific_audit.json")
    if status.get("status") != "COMPLETED" or status.get("completed") != status.get("expected"):
        raise RuntimeError("P3.2a design trajectories are not complete")
    if audit.get("status") != "PASS" or audit.get("trajectories") != status["expected"]:
        raise RuntimeError("P3.2a scientific audit did not pass")
    revision = REVISION_ROOT.name
    config = load_json(REVISION_ROOT / f"{revision}_config.json")
    validate_config(config)
    if canonical_hash(config) != canonical_hash(load_protocol(CONFIG_PATH)):
        raise RuntimeError("revision config differs from protocol")
    source_manifest = load_json(source_manifest_path(config))
    structural = load_json(REVISION_ROOT / "structural" / "generator_structural_audit.json")
    if structural.get("status") != "PASS":
        raise RuntimeError("generator-only structural audit did not pass")
    stage = pd.read_csv(REVISION_ROOT / "stage_records.csv")
    if len(stage) != audit["stage_rows"] or stage.run_id.nunique() != status["expected"]:
        raise RuntimeError("completed stage records disagree with scientific audit")
    if len(pd.read_csv(REVISION_ROOT / "candidate_records.csv")) != audit["candidate_rows"]:
        raise RuntimeError("completed candidate records disagree with scientific audit")
    analysis_path = REVISION_ROOT / "analysis.json"
    freeze_sha = None
    if FROZEN_CONFIG.exists():
        frozen, freeze_sha = validate_freeze()
        if (
            frozen["generator_revision"] != config["generator_revision"]
            or frozen["p3_2a_analysis_sha256"] != sha256_file(analysis_path)
            or frozen["source_training_manifest_sha256"] != sha256_file(source_manifest_path(config))
        ):
            raise RuntimeError("existing frozen generator disagrees with completed design artifacts")
        analysis = load_json(analysis_path)
        if analysis["overall_verdict"] != "PASS":
            raise RuntimeError("frozen generator has a failed design verdict")
    else:
        structural_frame = pd.read_csv(REVISION_ROOT / "structural" / "target_structural_statistics.csv")
        analysis = analyze_phase(stage, structural_frame, config, phase="p3_2a")
        write_json(analysis_path, analysis)
        pd.DataFrame(analysis["grid"]).to_csv(REVISION_ROOT / "recoverability_grid.csv", index=False)
        pd.DataFrame(analysis["persistence_rows"]).to_csv(REVISION_ROOT / "persistence_by_trajectory.csv", index=False)
        if analysis["overall_verdict"] == "PASS":
            freeze_sha = freeze(config, source_manifest, analysis, audit)
    write_p3_2a_report(config, structural, source_manifest, analysis, audit, frozen=freeze_sha is not None)
    revision_hash = ROOT / "audits" / f"{revision}.sha256"
    revision_hash.parent.mkdir(parents=True, exist_ok=True)
    revision_hash.write_text(
        "\n".join(
            f"{sha256_file(path)}  {path.relative_to(ROOT).as_posix()}"
            for path in (
                REVISION_ROOT / f"{revision}_config.json",
                REVISION_ROOT / "structural" / "generator_structural_audit.json",
                source_manifest_path(config),
                REVISION_ROOT / "scientific_audit.json",
                REVISION_ROOT / "analysis.json",
            )
        ) + "\n",
        encoding="utf-8",
    )
    return config, source_manifest, analysis, freeze_sha


def execute_fresh() -> dict:
    config, freeze_sha = validate_freeze()
    if (FRESH_ROOT / "execution_status.json").exists():
        status = load_json(FRESH_ROOT / "execution_status.json")
        if status.get("status") == "COMPLETED" and (ROOT / "reports" / "P3_2B_FRESH_DEVELOPMENT_CONFIRMATION.md").exists():
            raise RuntimeError("P3.2b was already completed; refusing a second confirmation run")
    source_manifest = load_json(source_manifest_path(config))
    identities = build_p3_2_identity_bank(source_manifest)
    bases = generate_base_centers(
        config["fresh_development_centers"], data_seed=config["data_seed"]
    )
    structural = generator_structural_audit(bases, config, FRESH_ROOT / "structural", phase="p3_2b")
    if structural["status"] != "PASS":
        write_json(
            FRESH_ROOT / "execution_status.json",
            {"status": "STOPPED_STRUCTURAL_FAIL", "heldout_accessed": False},
        )
        raise RuntimeError("fresh-development generator structural audit failed; oracle was not run")
    stage, _, _, _, audit, _ = run_phase(
        config,
        source_manifest,
        identities,
        bases,
        FRESH_ROOT,
        phase="p3_2b",
        center_pool="fresh_development_confirmation",
    )
    structural_frame = pd.read_csv(FRESH_ROOT / "structural" / "target_structural_statistics.csv")
    analysis = analyze_phase(stage, structural_frame, config, phase="p3_2b")
    write_json(FRESH_ROOT / "analysis.json", analysis)
    pd.DataFrame(analysis["grid"]).to_csv(FRESH_ROOT / "recoverability_grid.csv", index=False)
    pd.DataFrame(analysis["persistence_rows"]).to_csv(FRESH_ROOT / "persistence_by_trajectory.csv", index=False)
    write_p3_2b_report(config, structural, analysis, audit, freeze_sha)
    return analysis


def execute_fresh_report_only() -> dict:
    """Re-render a completed confirmation report without any oracle rerun."""
    config, freeze_sha = validate_freeze()
    status = load_json(FRESH_ROOT / "execution_status.json")
    audit = load_json(FRESH_ROOT / "scientific_audit.json")
    if (
        status.get("status") != "COMPLETED"
        or status.get("completed") != status.get("expected")
        or status.get("expected") != 72
        or audit.get("status") != "PASS"
        or audit.get("trajectories") != 72
    ):
        raise RuntimeError("fresh confirmation is not complete and scientifically audited")
    analysis = load_json(FRESH_ROOT / "analysis.json")
    structural = load_json(FRESH_ROOT / "structural" / "generator_structural_audit.json")
    if structural.get("status") != "PASS" or analysis.get("phase") != "p3_2b":
        raise RuntimeError("fresh structural audit or analysis is invalid")
    write_p3_2b_report(config, structural, analysis, audit, freeze_sha)
    confirmation_hash = ROOT / "audits" / "p3_2b_fresh_development.sha256"
    confirmation_hash.write_text(
        "\n".join(
            f"{sha256_file(path)}  {path.relative_to(ROOT).as_posix()}"
            for path in (
                FROZEN_CONFIG,
                FRESH_ROOT / "structural" / "generator_structural_audit.json",
                FRESH_ROOT / "scientific_audit.json",
                FRESH_ROOT / "analysis.json",
                FRESH_ROOT / "stage_records.csv",
                FRESH_ROOT / "per_policy_horizon_losses.csv",
            )
        ) + "\n",
        encoding="utf-8",
    )
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("structural_only", "prepare", "p3_2a", "p3_2a_analysis_only", "p3_2b", "p3_2b_report_only", "all"), required=True)
    parser.add_argument("--revision", choices=("r1", "r2", "r3"), default="r1")
    args = parser.parse_args()
    select_revision(args.revision)
    if args.phase == "structural_only":
        prepare_structural_only()
        return
    if args.phase == "prepare":
        prepare()
        return
    if args.phase == "p3_2a":
        execute_design()
        return
    if args.phase == "p3_2a_analysis_only":
        execute_design_analysis_only()
        return
    if args.phase == "p3_2b":
        execute_fresh()
        return
    if args.phase == "p3_2b_report_only":
        execute_fresh_report_only()
        return
    _, _, design_analysis, freeze_sha = execute_design()
    if design_analysis["overall_verdict"] != "PASS" or freeze_sha is None:
        print("P3.2a failed; P3.2b not run", file=sys.stderr)
        raise SystemExit(2)
    fresh = execute_fresh()
    raise SystemExit(0 if fresh["overall_verdict"] == "PASS" else 3)


if __name__ == "__main__":
    main()
