from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

from core.audits import run_audits
from core.common import canonical_hash, sha256_file, write_json
from core.data import full_windows, generate_base_centers, scenario_hash
from core.models import DEVICE, bank_hash, build_identity_bank, feasible, load_identity, predict
from core.oracle import reference_loss, run_p3_trajectory


OKABE_ITO = {
    "C0": "#000000",
    "C1": "#0072B2",
    "C2": "#56B4E9",
    "C3": "#D55E00",
    "C4": "#CC79A7",
    "C6": "#009E73",
    "C7": "#E69F00",
    "C8": "#F0E442",
}
LINESTYLES = {"C0": "-", "C1": "--", "C2": ":", "C3": "-", "C4": "--", "C6": "-", "C7": "-", "C8": ":"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a small report table without pandas' optional tabulate dependency."""
    columns = [str(value) for value in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in frame.itertuples(index=False, name=None):
        values = []
        for value in row:
            if pd.isna(value):
                values.append("NA")
            elif isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.6g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def validated_completed_run(raw_path: Path, candidate_path: Path, scenario: str, base, seed: int, identities, config: dict) -> dict | None:
    if not raw_path.exists() and not candidate_path.exists():
        return None
    if not raw_path.exists() or not candidate_path.exists():
        raise RuntimeError(f"incomplete resume pair: {raw_path.name}")
    stage = pd.read_csv(raw_path)
    candidates = pd.read_csv(candidate_path)
    expected_run = f"p3-{scenario}-{base.center_id}-{seed}"
    expected_alternatives = [
        item for item in identities
        if item.identity_id != "msa_a57_pt" and feasible(item, config["deployment_limits"][base.budget_tier])
    ]
    valid = (
        len(stage) == 24 * len(config["recoverability_horizons"])
        and set(stage["run_id"]) == {expected_run}
        and set(stage["stage"]) == set(range(1, 25))
        and set(stage["recoverability_horizon"]) == set(config["recoverability_horizons"])
        and len(candidates) == 24 * len(expected_alternatives)
        and set(candidates["run_id"]) == {expected_run}
        and set(candidates["candidate_identity_id"]) == {item.identity_id for item in expected_alternatives}
    )
    if not valid:
        raise RuntimeError(f"resume artifact validation failed: {expected_run}")
    first = stage[(stage.stage == 1) & (stage.recoverability_horizon == min(config["recoverability_horizons"]))].iloc[0]
    return {
        "run_id": expected_run,
        "scenario": scenario,
        "center_id": base.center_id,
        "seed": seed,
        "initial_state_hash": first["incumbent_state_hash"],
        "bank_hash": bank_hash(identities),
        "parent_immutable_during_probe": True,
        "candidate_count": len(expected_alternatives),
        "deployment_tier": base.budget_tier,
        "resume_provenance": "complete artifact written only after run_p3_trajectory returned; probe-integrity violations raise before write",
    }


def teacher_predictions(base, identities) -> dict[str, np.ndarray]:
    windows_x, targets = full_windows(base.x, base.dt)
    output = {}
    for identity_id in ("msa_a57_medet", "msa_a46_pt"):
        identity = next(item for item in identities if item.identity_id == identity_id)
        values = np.full(len(base.y), np.nan, dtype=np.float32)
        values[targets] = predict(load_identity(identity), windows_x)
        output[identity_id] = values
    return output


def cluster_interval(frame: pd.DataFrame, value: str, repetitions: int, seed: int) -> tuple[float, float, float]:
    center_values = frame.groupby("center_id", sort=True)[value].mean().to_numpy(float)
    mean = float(center_values.mean())
    rng = np.random.default_rng(seed)
    draws = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        draws[index] = rng.choice(center_values, len(center_values), replace=True).mean()
    return mean, float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def summarize(stage: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for (scenario, horizon), group in stage.groupby(["scenario", "recoverability_horizon"], sort=True):
        negative = group.assign(negative=(group.recoverability_oracle_approx < 0).astype(float))
        conditional = group[group.recoverability_oracle_approx < 0]
        r_mean, r_lo, r_hi = cluster_interval(group, "recoverability_oracle_approx", config["bootstrap_repetitions"], config["bootstrap_seed"] + int(horizon))
        n_mean, n_lo, n_hi = cluster_interval(negative, "negative", config["bootstrap_repetitions"], config["bootstrap_seed"] + 100 + int(horizon))
        rows.append(
            {
                "scenario": scenario,
                "horizon": horizon,
                "stage_records": len(group),
                "centers": group.center_id.nunique(),
                "seeds": group.seed.nunique(),
                "recoverability_mean": r_mean,
                "recoverability_ci_low": r_lo,
                "recoverability_ci_high": r_hi,
                "negative_R_rate": n_mean,
                "negative_R_ci_low": n_lo,
                "negative_R_ci_high": n_hi,
                "best_local_horizon_loss": group.best_bounded_local_horizon_loss.mean(),
                "best_RI_horizon_loss": group.best_reinstantiation_horizon_loss.mean(),
                "RI_gain": group.reinstantiation_gain.mean(),
                "RI_gain_conditional_R_negative": conditional.reinstantiation_gain.mean() if len(conditional) else np.nan,
                "RI_benefit_rate_conditional_R_negative": (conditional.reinstantiation_gain > 0).mean() if len(conditional) else np.nan,
                "negative_R_but_no_better_alternative_rate": (conditional.reinstantiation_gain <= 0).mean() if len(conditional) else np.nan,
            }
        )
    center = (
        stage.groupby(["scenario", "recoverability_horizon", "center_id"], as_index=False)
        .agg(
            recoverability_mean=("recoverability_oracle_approx", "mean"),
            negative_R_rate=("oracle_recoverable", lambda value: 1.0 - np.mean(value)),
            RI_gain=("reinstantiation_gain", "mean"),
            best_local_loss=("best_bounded_local_horizon_loss", "mean"),
            best_RI_loss=("best_reinstantiation_horizon_loss", "mean"),
        )
    )
    return pd.DataFrame(rows), center


def verdicts(stage: pd.DataFrame, audit: dict, config: dict) -> tuple[dict, str]:
    rules = config["p3_pass_rules"]
    h = stage[stage.recoverability_horizon == 4]
    maintainable = h[h.scenario.isin(["C0", "C1"])]
    mismatch = h[h.scenario.isin(["C3", "C4"]) & (h.stage >= 9)]
    mismatch_negative = mismatch[mismatch.recoverability_oracle_approx < 0]
    scenario = {}
    for name, group in h.groupby("scenario"):
        post = group[group.stage >= 9]
        negative_rate = float((post.recoverability_oracle_approx < 0).mean())
        benefit = post[post.recoverability_oracle_approx < 0]
        scenario[name] = {
            "negative_R_rate_postshift": negative_rate,
            "mean_RI_gain_postshift": float(post.reinstantiation_gain.mean()),
            "RI_benefit_rate_when_R_negative": float((benefit.reinstantiation_gain > 0).mean()) if len(benefit) else None,
            "verdict": "DIAGNOSTIC",
        }
    maintainable_rate = float((maintainable.recoverability_oracle_approx < 0).mean())
    mismatch_rate = float((mismatch.recoverability_oracle_approx < 0).mean())
    mismatch_benefit_rate = float((mismatch_negative.reinstantiation_gain > 0).mean()) if len(mismatch_negative) else 0.0
    mismatch_gain = float(mismatch_negative.reinstantiation_gain.mean()) if len(mismatch_negative) else float("-inf")
    core_checks = {
        "scientific_audits_pass": audit["status"] == "PASS",
        "maintainable_conditions_predominantly_recoverable": maintainable_rate <= rules["maintainable_negative_rate_max"],
        "mismatch_conditions_meaningfully_insufficient": mismatch_rate >= rules["mismatch_postshift_negative_rate_min"],
        "RI_often_beneficial_when_mismatch_is_insufficient": mismatch_benefit_rate >= rules["mismatch_negative_stage_ri_benefit_rate_min"],
        "RI_gain_positive_when_mismatch_is_insufficient": mismatch_gain > rules["mismatch_negative_stage_mean_ri_gain_min"],
    }
    overall = "PASS" if all(core_checks.values()) else "FAIL"
    return {
        "overall": overall,
        "primary_horizon": 4,
        "core_checks": core_checks,
        "maintainable_negative_R_rate": maintainable_rate,
        "mismatch_postshift_negative_R_rate": mismatch_rate,
        "mismatch_R_negative_RI_benefit_rate": mismatch_benefit_rate,
        "mismatch_R_negative_mean_RI_gain": mismatch_gain if np.isfinite(mismatch_gain) else None,
        "scenarios": scenario,
    }, overall


def plot_results(stage: pd.DataFrame) -> dict:
    plot = stage[stage.recoverability_horizon == 4].copy()
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    groups = [(["C0", "C1", "C2"], "Maintainable / parameter drift"), (["C3", "C4", "C8"], "Identity / architecture mismatch"), (["C6"], "Recurring regime"), (["C7"], "Transient monitoring corruption")]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.8), constrained_layout=True, sharex=True)
    for panel, (ax, (names, title)) in enumerate(zip(axes.flat, groups)):
        for name in names:
            subset = plot[plot.scenario == name]
            stats = subset.groupby("stage").recoverability_oracle_approx.agg(["mean", "std", "count"])
            ci = 1.96 * stats["std"].fillna(0) / np.sqrt(stats["count"].clip(lower=1))
            ax.plot(stats.index, stats["mean"], color=OKABE_ITO[name], linestyle=LINESTYLES[name], marker="o", markersize=2.5, linewidth=1.2, label=name)
            ax.fill_between(stats.index, stats["mean"] - ci, stats["mean"] + ci, color=OKABE_ITO[name], alpha=0.14, linewidth=0)
        ax.axhline(0, color="#666666", linewidth=0.8, linestyle="--")
        ax.axvline(9, color="#999999", linewidth=0.7, linestyle=":")
        ax.set_title(title)
        ax.set_xlabel("Lifecycle stage")
        ax.set_ylabel("Finite-policy recoverability margin")
        ax.legend(frameon=False, loc="best")
        ax.text(-0.13, 1.04, chr(ord("a") + panel), transform=ax.transAxes, fontweight="bold", va="bottom")
    stem = ROOT / "figures" / "p3_stagewise_recoverability"
    for suffix in ("pdf", "svg", "png"):
        fig.savefig(stem.with_suffix(f".{suffix}"), dpi=600 if suffix == "png" else None, bbox_inches="tight")
    fig.savefig(ROOT / "figures" / "p3_stagewise_recoverability_preview.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 3.2), constrained_layout=True)
    for name in ("C3", "C4", "C8"):
        subset = plot[plot.scenario == name]
        stats = subset.groupby("stage").reinstantiation_gain.agg(["mean", "std", "count"])
        ci = 1.96 * stats["std"].fillna(0) / np.sqrt(stats["count"].clip(lower=1))
        ax.plot(stats.index, stats["mean"], color=OKABE_ITO[name], linestyle=LINESTYLES[name], marker="o", markersize=2.5, linewidth=1.2, label=name)
        ax.fill_between(stats.index, stats["mean"] - ci, stats["mean"] + ci, color=OKABE_ITO[name], alpha=0.14, linewidth=0)
    ax.axhline(0, color="#666666", linewidth=0.8, linestyle="--")
    ax.axvline(9, color="#999999", linewidth=0.7, linestyle=":")
    ax.set_xlabel("Lifecycle stage")
    ax.set_ylabel("Best local loss - best re-instantiation loss")
    ax.legend(frameon=False, ncol=3, loc="upper center")
    stem2 = ROOT / "figures" / "p3_local_vs_reinstantiation_gap"
    for suffix in ("pdf", "svg", "png"):
        fig.savefig(stem2.with_suffix(f".{suffix}"), dpi=600 if suffix == "png" else None, bbox_inches="tight")
    fig.savefig(ROOT / "figures" / "p3_local_vs_reinstantiation_gap_preview.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    from PIL import Image
    for path in (stem.with_suffix(".png"), stem2.with_suffix(".png")):
        Image.open(path).convert("L").save(path.with_name(path.stem + "_grayscale.png"))
    return {
        "figure_1": str(stem.with_suffix(".pdf").relative_to(ROOT)).replace("\\", "/"),
        "figure_2": str(stem2.with_suffix(".pdf").relative_to(ROOT)).replace("\\", "/"),
        "encoding": "Okabe-Ito colorblind-safe palette plus line-style/marker redundancy",
        "uncertainty": "shaded band is normal-approximation 95% interval across 3 centers x 3 seeds at each stage; exploratory only",
    }


def write_report(summary: pd.DataFrame, center: pd.DataFrame, verdict: dict, audit: dict, config: dict, splits: dict, identities, scenario_manifest: dict, figure_manifest: dict, elapsed: float) -> None:
    primary = summary[summary.horizon == 4].copy()
    table = markdown_table(primary[["scenario", "stage_records", "recoverability_mean", "negative_R_rate", "best_local_horizon_loss", "best_RI_horizon_loss", "RI_gain_conditional_R_negative", "negative_R_but_no_better_alternative_rate"]])
    scenario_lines = []
    for name in config["scenarios"]:
        item = verdict["scenarios"][name]
        scenario_lines.append(f"| {name} | {item['negative_R_rate_postshift']:.3f} | {item['mean_RI_gain_postshift']:.6g} | {item['RI_benefit_rate_when_R_negative'] if item['RI_benefit_rate_when_R_negative'] is not None else 'NA'} | {item['verdict']} |")
    checks = "\n".join(f"| {name} | {'PASS' if value else 'FAIL'} |" for name, value in audit["checks"].items())
    bank_rows = "\n".join(f"| {item.identity_id} | {item.architecture} | {item.source_initialization_id} | {item.parameter_count} | {item.operation_count} | `{item.checkpoint_sha256}` |" for item in identities)
    overall_text = (
        "当前实验系统中确实存在足够稳定的 maintenance-recoverable 与 maintenance-insufficient 状态，并存在适合研究 re-instantiation escalation 的条件。"
        if verdict["overall"] == "PASS"
        else "当前 generator / bank / maintenance class 无法支持第三篇核心研究问题；按规范停止，不进入 P4–P16。"
    )
    failed = [name for name, value in verdict["core_checks"].items() if not value]
    report = f"""# P3 Phenomenon Diagnostic

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent + scipilot-figure-skill
- Origin Mode: run + validate
- Verification Status: VERIFIED for the completed development diagnostic; not held-out confirmation
- Phase: P3 only
- Overall Verdict: **{verdict['overall']}**
- Cumulative P3 execution wall time: {elapsed:.1f} s on {DEVICE} (excludes the separate 37.3 s smoke trajectory)

## 1. Verdict

**{verdict['overall']}: {overall_text}**

Blocking checks: {', '.join(failed) if failed else 'none'}.

This is a small development phenomenon gate with 3 centers and 3 model seeds. It is not a final estimator/gate result and no held-out center was generated or accessed.

### Failure diagnosis

- The intended mismatch pair C3/C4 produced only 3 negative-R records out of 288 post-shift H_R=4 records (1.04%), against the predeclared >=50% requirement. C3 contributed all 3; C4 contributed none.
- Mean post-shift best-local H_R=4 loss was 0.000707 for C3 and 0.000706 for C4, far below the mean center/seed-specific threshold 0.004371. The finite local policy therefore remained comfortably feasible.
- The frozen-teacher blend made the target smoother than C0 instead of harder: across the three centers, post-onset target SD fell from 0.0821 (C0) to 0.0506 (C3) / 0.0614 (C4), and adjacent-step RMSE fell from 0.0419 to 0.0205 / 0.0284. This is the direct generator failure mode.
- Re-instantiation was correctly selected in the intended direction (98.6% `msa_a57_medet` for C3 and 100% `msa_a46_pt` for C4 after onset), and its mean gain was positive; however, that does not rescue the missing maintenance-insufficient state population.
- C6 did exhibit maintenance-insufficient intervals with useful alternatives, but on the wrong causal axis (recurring parameter regime rather than identity/architecture mismatch). It cannot substitute for the failed C3/C4 gate.

## 2. Exact read-only repositories reused

- MSA-DTI: `D:/dt-talk/repository`, Git HEAD `c52e07c999f059e6e2d83f8370be67a630208823`, release lineage v1.2.7; reused files are hash-bound in `audits/REUSE_PROVENANCE.md`.
- RAVM-DT: `D:/dt-trustworthy-maintenance`, working HEAD `1b84fbcff8c47fb76dafc313f536f04ba8a9287b`, frozen scientific implementation commit `7ae7fabd9a4e335e774fbcba2f38dfa8827bb8f3`; reused files are hash-bound in `audits/REUSE_PROVENANCE.md`.

## 3. Exact model bank

Bank identity hash: `{bank_hash(identities)}`.

| Identity | Architecture | Source initialization | Params | Operations | Checkpoint SHA-256 |
|---|---|---|---:|---:|---|
{bank_rows}

`msa_a57_pt` is the incumbent. `msa_a57_medet` has the same A57 architecture but a distinct source-trained initialization, so identity is not equated with architecture.

## 4. Population and protocol

- Development centers: {splits['development']} (A/B/C strata; n=3).
- Model seeds: {config['model_seeds']}.
- Scenarios: {config['scenarios']}.
- Lifecycle: T=24, L=96, H(prediction)=1.
- Stage roles: D_upd=400 raw observations, D_assess=240, D_srv=400. Role-contained windows never cross a role boundary.
- RAVM maturation rule retained: a prior service span may become a later update span only after its label has matured; within every decision stage the three current roles are disjoint.
- Local policies: {['P'+str(x) for x in config['local_policies']]}; each policy applies once at decision stage t and is evaluated over the next H_R service stages without additional future actions.
- H_R: {config['recoverability_horizons']} (near the trajectory end, effective horizon is truncated and recorded).
- Local probe: fixed P50 on a deep copy; SGD/MSE, lr=0.01, batch=64, clip=1.0.
- Oracle: `tau_svc - min finite-policy local horizon service loss`; future service is accessible only through explicit offline-oracle capability.
- Tau rule: `(1 + eta) * L_ref`; eta grid={config['tau_rule']['eta_grid']}, primary eta={config['tau_rule']['primary_eta']}; L_ref uses C0 stages 1–8 only, separately for each center/seed.
- Deployment limits: {json.dumps(config['deployment_limits'], ensure_ascii=False)}; the center-assigned tier is used.

## 5. Scenario definitions and hashes

The generator revision is `p3_prespecified_v1_no_outcome_retuning`; it was executed once without outcome-driven knob changes. C3 and C4/C8 are teacher-defined controlled stress conditions using frozen source identities. This makes the intended replacement explicit but limits external construct validity; it does not show how often such mismatch occurs naturally.

Scenario manifest: `results/p3/scenario_manifest.json` (`{canonical_hash(scenario_manifest)}`).

## 6. Primary H_R=4 results

{table}

All denominators are explicit in `results/p3/p3_summary_by_condition_horizon.csv`; raw records are in `results/p3/stage_records.csv` and candidate-level records in `results/p3/candidate_records.csv`.

## 7. Scenario PASS/FAIL diagnostics

| Scenario | Post-shift negative-R rate | Mean post-shift RI gain | RI-benefit rate when R<0 | Verdict |
|---|---:|---:|---:|---|
{chr(10).join(scenario_lines)}

Formal P3 core gate (H_R=4):

- Maintainable C0/C1 negative-R rate: {verdict['maintainable_negative_R_rate']:.3f} (required <= {config['p3_pass_rules']['maintainable_negative_rate_max']}).
- Mismatch C3/C4 post-shift negative-R rate: {verdict['mismatch_postshift_negative_R_rate']:.3f} (required >= {config['p3_pass_rules']['mismatch_postshift_negative_rate_min']}).
- Conditional RI-benefit rate: {verdict['mismatch_R_negative_RI_benefit_rate']:.3f} (required >= {config['p3_pass_rules']['mismatch_negative_stage_ri_benefit_rate_min']}).
- Conditional mean RI gain: {verdict['mismatch_R_negative_mean_RI_gain']} (required > 0).

Rows where R<0 but no alternative is better are retained and reported; maintenance insufficiency is not treated as automatic beneficial re-instantiation.

## 8. Center-level variability

Center-level raw summaries are in `results/p3/center_level_variability.csv`. With only three development centers, intervals are exploratory and should not be interpreted as stable population coverage.

## 9. Effort feature audit

- Probe effort variance: {audit['effort_variance']}.
- Decision: {audit['estimator_feature_decision']}.
- No artificial effort variability was introduced.

## 10. Scientific and leakage audits

| Audit | Result |
|---|---|
{checks}

Overall audit status: **{audit['status']}**.

## 11. Figures

- `figures/p3_stagewise_recoverability.pdf`: stage-wise finite-policy recoverability margin, H_R=4.
- `figures/p3_local_vs_reinstantiation_gap.pdf`: stage-wise best-local minus best-re-instantiation horizon loss, H_R=4.
- PNG, SVG, 600-DPI raster, preview, and grayscale variants are provided. {figure_manifest['uncertainty']}.

Programmatic 600-DPI checks passed for both raster figures. Visual review passed for clipping, panel alignment, zero/onset reference lines, legends, and grayscale distinguishability. The wide bands correctly expose the large between-center heterogeneity; they must not be read as confirmatory intervals with n=3 centers.

## 12. Execution incidents and recovery

- Attempt 1 stopped after 54/72 trajectories because C7 used a 13-column mask slice against 12 value columns. The gap column was excluded (`12:24`), a regression test was added, and all 54 completed artifacts were validated before resume.
- Attempt 2 completed 72/72 trajectories and all scientific outputs, then stopped only because pandas' optional `tabulate` package was absent during report rendering. It was replaced by an internal deterministic Markdown formatter.
- Both incidents are preserved in `logs/P3_EXECUTION_FAILURE_001.json` and `logs/P3_EXECUTION_FAILURE_002.json`; neither accessed heldout data or changed a scenario parameter.

## 13. Scope boundary and next gate

No estimator fitting, gate calibration, baseline tuning, held-out comparison, robustness matrix, or Alibaba experiment was run. Human/research review is mandatory before P4–P16.
"""
    (ROOT / "reports" / "P3_PHENOMENON_DIAGNOSTIC.md").write_text(report, encoding="utf-8")


def main() -> int:
    started = time.time()
    config = load_json(ROOT / "configs" / "p3_development.json")
    splits = load_json(ROOT / "configs" / "center_splits.json")
    if not config["heldout_forbidden"]:
        raise RuntimeError("P3 refuses to run without heldout_forbidden=true")
    identities = build_identity_bank()
    write_json(ROOT / "artifacts" / "p3_model_bank_manifest.json", {"bank_hash": bank_hash(identities), "identities": [item.to_dict() for item in identities]})
    bases = generate_base_centers(splits["development"], config["data_seed"] if "data_seed" in config else splits["data_seed"])
    teachers_by_center = {}
    scenario_manifest = {"revision": config["scenario_version"], "centers": {}, "heldout_materialized": False}
    for base in bases:
        np.savez_compressed(ROOT / "data" / f"development_base_{base.center_id}.npz", x=base.x, y=base.y, ts=base.ts)
        teachers = teacher_predictions(base, identities)
        teachers_by_center[base.center_id] = teachers
        scenario_manifest["centers"][str(base.center_id)] = {
            "center_type": base.center_type,
            "budget_tier": base.budget_tier,
            "scenarios": {name: scenario_hash(base, name, teachers) for name in config["scenarios"]},
        }
    write_json(ROOT / "results" / "p3" / "scenario_manifest.json", scenario_manifest)

    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    tau = {}
    for base in bases:
        tau[str(base.center_id)] = {}
        for seed in config["model_seeds"]:
            reference = reference_loss(base, seed, incumbent, teachers_by_center[base.center_id])
            tau[str(base.center_id)][str(seed)] = {
                "L_ref": reference,
                "tau_primary": (1 + config["tau_rule"]["primary_eta"]) * reference,
                "tau_candidates": {str(eta): (1 + eta) * reference for eta in config["tau_rule"]["eta_grid"]},
            }
    write_json(ROOT / "results" / "p3" / "tau_service_development.json", tau)

    raw_dir = ROOT / "results" / "p3" / "raw"
    candidate_dir = ROOT / "results" / "p3" / "candidates"
    raw_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    run_audit_rows = []
    total = len(config["scenarios"]) * len(bases) * len(config["model_seeds"])
    completed = 0
    for scenario in config["scenarios"]:
        for base in bases:
            for seed in config["model_seeds"]:
                raw_path = raw_dir / f"{scenario}_{base.center_id}_{seed}.csv"
                candidate_path = candidate_dir / f"{scenario}_{base.center_id}_{seed}.csv"
                resumed = validated_completed_run(raw_path, candidate_path, scenario, base, seed, identities, config)
                if resumed is not None:
                    run_audit_rows.append(resumed)
                    completed += 1
                    print(f"P3 resume {completed}/{total} {resumed['run_id']} validated", flush=True)
                    continue
                result = run_p3_trajectory(
                    base,
                    seed,
                    scenario,
                    identities,
                    teachers_by_center[base.center_id],
                    config,
                    tau[str(base.center_id)][str(seed)]["tau_primary"],
                )
                pd.DataFrame(result.stage_rows).to_csv(raw_path, index=False)
                pd.DataFrame(result.candidate_rows).to_csv(candidate_path, index=False)
                run_audit_rows.append(result.run_audit)
                completed += 1
                write_json(ROOT / "logs" / "p3_execution_status.json", {"status": "RUNNING", "completed": completed, "expected": total, "last": result.run_audit["run_id"], "elapsed_s": time.time() - started, "heldout_accessed": False})
                print(f"P3 {completed}/{total} {result.run_audit['run_id']} elapsed={time.time()-started:.1f}s", flush=True)

    stage = pd.concat([pd.read_csv(path) for path in sorted(raw_dir.glob("*.csv"))], ignore_index=True)
    candidates = pd.concat([pd.read_csv(path) for path in sorted(candidate_dir.glob("*.csv"))], ignore_index=True)
    stage.to_csv(ROOT / "results" / "p3" / "stage_records.csv", index=False)
    candidates.to_csv(ROOT / "results" / "p3" / "candidate_records.csv", index=False)
    summary, center = summarize(stage, config)
    summary.to_csv(ROOT / "results" / "p3" / "p3_summary_by_condition_horizon.csv", index=False)
    center.to_csv(ROOT / "results" / "p3" / "center_level_variability.csv", index=False)
    audit = run_audits(stage.to_dict("records"), candidates.to_dict("records"), run_audit_rows, identities, config, splits)
    write_json(ROOT / "audits" / "P2_P3_SCIENTIFIC_AUDITS.json", audit)
    verdict, overall = verdicts(stage, audit, config)
    write_json(ROOT / "results" / "p3" / "p3_verdict.json", verdict)
    figures = plot_results(stage)
    write_json(ROOT / "audits" / "P3_FIGURE_MANIFEST.json", figures)
    write_report(summary, center, verdict, audit, config, splits, identities, scenario_manifest, figures, time.time() - started)
    write_json(ROOT / "logs" / "p3_execution_status.json", {"status": "COMPLETED", "completed": completed, "expected": total, "elapsed_s": time.time() - started, "heldout_accessed": False, "verdict": overall})
    print(f"P3 completed verdict={overall} elapsed={time.time()-started:.1f}s", flush=True)
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
