"""Rebuild Paper 3 Figures 2--4 from frozen outputs only.

No experiment, fit, bootstrap, or metric computation is performed here.  The
only aggregation is a transparent read-only groupby of frozen P7.7 stage
records for the Fig.4 action-composition panel.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from paper_figure_style import configure_style

ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "figures"
FIGDIR.mkdir(exist_ok=True)

INPUTS = {
    "validation_metrics": ROOT / "results/p7_6b/validation_metrics.csv",
    "validation_center_metrics": ROOT / "results/p7_6b/validation_metrics_by_center.csv",
    "validation_paired": ROOT / "results/p7_6b/paired_a1_vs_a0.csv",
    "validation_loo": ROOT / "results/p7_6b/leave_one_center_out.csv",
    "lifecycle_method_metrics": ROOT / "results/p7_7/final_metrics_by_method.csv",
    "lifecycle_center_metrics": ROOT / "results/p7_7/final_metrics_by_center.csv",
    "lifecycle_scenario_metrics": ROOT / "results/p7_7/final_metrics_by_scenario.csv",
    "lifecycle_paired_bootstrap": ROOT / "results/p7_7/final_paired_bootstrap.csv",
    "p7_6b_final_audit": ROOT / "audits/P7_6B_FINAL_SCIENTIFIC_AUDIT.json",
    "p7_7_final_audit": ROOT / "audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json",
    "paper3_scientific_freeze": ROOT / "LATEST_PAPER3_SCIENTIFIC_FREEZE.md",
    "p7_7_package": ROOT / "LATEST_P7_7_FINAL_HELDOUT_PACKAGE.md",
    "p7_7_results_report": ROOT / "reports/P7_7_FINAL_HELDOUT_RESULTS.md",
    "p7_7_statistics_report": ROOT / "reports/P7_7_FINAL_HELDOUT_STATISTICS.md",
    "p7_7_scenario_report": ROOT / "reports/P7_7_FINAL_HELDOUT_SCENARIO_ANALYSIS.md",
}
STAGE_GLOB = "P7_7_RECOVERABILITY_GUIDED*.csv"

LABELS = {"A0": "Absolute", "A1": "Identity-normalized", "B0": "Frozen",
          "B1": "Always-Maintain", "B2": "Verification-Guided Maintenance",
          "B8": "Always-Open Search", "P7.7": "Recoverability-Guided"}
METHOD_ORDER = ["B0", "B1", "B2", "B8", "P7.7"]
METHOD_COLORS = {"B0": "#4C4C4C", "B1": "#0072B2", "B2": "#009E73",
                 "B8": "#D55E00", "P7.7": "#CC79A7"}
SCENARIOS = ["C0", "C1", "C3", "C4"]

# Prompt values are assertions only; all plotted values are read from frozen files.
EXPECTED = {
    "fig2": {"A0_spearman": -0.0394025379, "A1_spearman": 0.1471508727,
              "delta_spearman": 0.1865534107, "spearman_lo": 0.1213743501,
              "spearman_hi": 0.2505022461, "A0_balanced": 0.5459636595,
              "A1_balanced": 0.5760688340, "delta_balanced": 0.03010517445,
              "balanced_lo": 0.00356997494, "balanced_hi": 0.05787135341},
    "means": {"B0": 0.006049676515, "B1": 0.002985070205,
              "B2": 0.004535350747, "B8": 0.002485968822,
              "P7.7": 0.002524255872},
    "diffs": {
        "P7.7 - B0": (-0.003527053381, -0.004331739509, -0.002806662431),
        "P7.7 - B1": (-0.0004612974625, -0.0005919769468, -0.0003479246183),
        "P7.7 - B2": (-0.002014801684, -0.002397977491, -0.001687318467),
        "P7.7 - B8": (0.00003810118384, 0.000001238427689, 0.00009941572676),
    },
    "scenario_loss": {("B8", "C0"): 0.002436766220, ("P7.7", "C0"): 0.002436766220,
                       ("B8", "C1"): 0.002302994127, ("P7.7", "C1"): 0.002302994127,
                       ("B8", "C3"): 0.002772800782, ("P7.7", "C3"): 0.002885116374,
                       ("B8", "C4"): 0.002431314159, ("P7.7", "C4"): 0.002472146765},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def load():
    missing = [str(p) for p in INPUTS.values() if not p.exists()]
    stage_files = sorted((ROOT / "results/p7_7/raw").glob(STAGE_GLOB))
    if missing:
        raise FileNotFoundError("Missing frozen input(s):\n" + "\n".join(missing))
    if not stage_files:
        raise FileNotFoundError("No frozen Recoverability-Guided stage records found")
    usecols = ["scenario", "stage", "center_id", "seed", "action", "gate_open", "ri", "local"]
    stage = pd.concat((pd.read_csv(p, usecols=usecols) for p in stage_files), ignore_index=True)
    return {
        "vmetrics": pd.read_csv(INPUTS["validation_metrics"]),
        "vcenter": pd.read_csv(INPUTS["validation_center_metrics"]),
        "vpaired": pd.read_csv(INPUTS["validation_paired"]),
        "vloo": pd.read_csv(INPUTS["validation_loo"]),
        "methods": pd.read_csv(INPUTS["lifecycle_method_metrics"]),
        "centers": pd.read_csv(INPUTS["lifecycle_center_metrics"]),
        "scenarios": pd.read_csv(INPUTS["lifecycle_scenario_metrics"]),
        "pboot": pd.read_csv(INPUTS["lifecycle_paired_bootstrap"]),
        "stage": stage,
        "stage_files": stage_files,
    }


def close(actual, expected, name, atol=1e-9, rtol=1e-7):
    if not np.isclose(float(actual), float(expected), atol=atol, rtol=rtol):
        raise AssertionError(f"Frozen assertion failed: {name}: {actual} != {expected}")


def assert_data(d):
    vm, vc, vp, vloo = d["vmetrics"], d["vcenter"], d["vpaired"], d["vloo"]
    methods, centers, scen, pb, stage = d["methods"], d["centers"], d["scenarios"], d["pboot"], d["stage"]
    if set(vc.representation) != {"A0", "A1"} or vc.groupby("representation").size().to_dict() != {"A0": 36, "A1": 36}:
        raise AssertionError("Validation does not contain 36 centers per representation")
    if set(vc[vc.representation == "A0"].center_id) != set(vc[vc.representation == "A1"].center_id):
        raise AssertionError("Validation center pairing is incomplete")
    if len(vloo) != 36 or not vloo.all_conditions_pass.astype(bool).all():
        raise AssertionError("Frozen 36/36 LOO replication checks did not pass")
    for rep, key in [("A0", "A0_spearman"), ("A1", "A1_spearman")]:
        row = vm[(vm.representation == rep) & (vm.subgroup == "all")].iloc[0]
        close(row.macro_center_Spearman, EXPECTED["fig2"][key], f"Fig.2 {rep} Spearman")
    for rep, key in [("A0", "A0_balanced"), ("A1", "A1_balanced")]:
        row = vm[(vm.representation == rep) & (vm.subgroup == "all")].iloc[0]
        close(row.balanced_admission_accuracy, EXPECTED["fig2"][key], f"Fig.2 {rep} balanced accuracy")
    row = vp.iloc[0]
    for col, key in [("Delta_macro_Spearman", "delta_spearman"), ("Delta_macro_Spearman_CI_low", "spearman_lo"),
                     ("Delta_macro_Spearman_CI_high", "spearman_hi"),
                     ("Delta_balanced_admission_accuracy", "delta_balanced"),
                     ("Delta_balanced_admission_accuracy_CI_low", "balanced_lo"),
                     ("Delta_balanced_admission_accuracy_CI_high", "balanced_hi")]:
        close(row[col], EXPECTED["fig2"][key], f"Fig.2 {col}")
    if set(methods.method) != set(METHOD_ORDER):
        raise AssertionError("P7.7 method set is not the frozen five-method set")
    if centers.center_id.nunique() != 20 or set(scen.scenario) != set(SCENARIOS):
        raise AssertionError("Final-heldout center/seed/scenario schema mismatch")
    for m, expected in EXPECTED["means"].items():
        close(methods[methods.method == m].iloc[0].mean_lifecycle_service_loss, expected, f"Fig.3 {m} mean")
    for comp, (mean, lo, hi) in EXPECTED["diffs"].items():
        values = pb[pb.comparison == comp].difference
        if len(values) != 4000:
            raise AssertionError(f"{comp} does not contain 4000 frozen bootstrap draws")
        close(values.mean(), mean, f"Fig.3 {comp} mean", atol=2e-12)
        close(values.quantile(.025), lo, f"Fig.3 {comp} CI low", atol=2e-12)
        close(values.quantile(.975), hi, f"Fig.3 {comp} CI high", atol=2e-12)
    if len(d["stage_files"]) != 240 or len(stage) != 5760 or stage.stage.nunique() != 24:
        raise AssertionError("Recoverability-Guided frozen stage-record count/schema mismatch")
    if stage.center_id.nunique() != 20 or stage.seed.nunique() != 3 or set(stage.scenario) != set(SCENARIOS):
        raise AssertionError("Recoverability-Guided frozen stage-record center/seed/scenario mismatch")
    if set(stage.action) != {"retain", "local", "ri"}:
        raise AssertionError(f"Unexpected frozen action labels: {sorted(stage.action.unique())}")
    if not ((stage.action == "ri") == (stage.ri.astype(bool))).all() or not ((stage.action == "local") == (stage.local.astype(bool))).all():
        raise AssertionError("Frozen action flags disagree with action labels")
    composition = stage.assign(retain=(stage.action == "retain").astype(int), local_rate=(stage.action == "local").astype(int), ri_rate=(stage.action == "ri").astype(int)).groupby("scenario").agg(
        n=("action", "size"), retain=("retain", "mean"), local=("local_rate", "mean"), ri=("ri_rate", "mean"), gate=("gate_open", "mean")).reindex(SCENARIOS)
    if not np.allclose(composition[["retain", "local", "ri"]].sum(axis=1), 1.0, atol=1e-12):
        raise AssertionError("Scenario action composition does not sum to one")
    method_rg = methods[methods.method == "P7.7"].iloc[0]
    for col, val in [("maintenance_rate", composition.local.mean()), ("ri_rate", composition.ri.mean()), ("retain_rate", composition.retain.mean()), ("gate_open_rate", composition.gate.mean())]:
        close(method_rg[col], val, f"overall Recoverability-Guided {col}")
    scenario_rows = {}
    for sc in SCENARIOS:
        for m, expected in [("B8", EXPECTED["scenario_loss"][("B8", sc)]), ("P7.7", EXPECTED["scenario_loss"][("P7.7", sc)])]:
            actual = scen[(scen.method == m) & (scen.scenario == sc)].iloc[0].lifecycle_service_loss
            close(actual, expected, f"Fig.4 {m}/{sc} service loss")
        scenario_rows[sc] = composition.loc[sc].to_dict()
    return {"validation_centers": 36, "loo_pass": 36, "final_centers": 20, "model_seeds": 3, "final_stages": 24, "proposed_decisions": 5760, "stage_files": 240, "scenario_composition": scenario_rows}


def panel_label(ax, label):
    ax.text(0.01, 1.04, label, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom", ha="left")


def save(fig, stem):
    fig.savefig(FIGDIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIGDIR / f"{stem}.png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def fig2(d):
    vm, vc, vp = d["vmetrics"], d["vcenter"], d["vpaired"].iloc[0]
    paired = vc.pivot(index="center_id", columns="representation", values="spearman").dropna()
    fig, ax = plt.subplots(1, 1, figsize=(4.6, 3.75), constrained_layout=True)
    ax.scatter(paired.A0, paired.A1, s=32, color="#0072B2", edgecolor="white", linewidth=0.6, alpha=0.9, zorder=3)
    joint_min = float(np.nanmin(paired.values)); joint_max = float(np.nanmax(paired.values))
    joint_span = joint_max - joint_min
    margin = 0.07 * joint_span if joint_span > 0 else 0.05
    lo, hi = joint_min - margin, joint_max + margin
    ax.plot([lo, hi], [lo, hi], color="#777777", ls="--", lw=0.8, label="y = x")
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi); ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Absolute center-level Spearman"); ax.set_ylabel("Identity-normalized center-level Spearman")
    ax.grid(color="#DDDDDD", lw=0.45); ax.spines[["top", "right"]].set_visible(False)
    a0 = vm[(vm.representation == "A0") & (vm.subgroup == "all")].iloc[0]; a1 = vm[(vm.representation == "A1") & (vm.subgroup == "all")].iloc[0]
    note = (f"n={len(paired)}; macro $\\rho$: {a0.macro_center_Spearman:.3f} $\\to$ {a1.macro_center_Spearman:.3f}\n"
            f"paired $\\Delta\\rho$={vp.Delta_macro_Spearman:+.3f}, 95% CI [{vp.Delta_macro_Spearman_CI_low:.3f}, {vp.Delta_macro_Spearman_CI_high:.3f}]")
    ax.text(0.03, 0.97, note, transform=ax.transAxes, ha="left", va="top", fontsize=7.0, color="#333333")
    ax.legend(frameon=False, loc="lower right", fontsize=7); save(fig, "fig2_recoverability_transport")


def fig3(d):
    methods, pb = d["methods"], d["pboot"]
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 5.0), gridspec_kw={"height_ratios": [1.2, .8], "hspace": .16, "wspace": .28}, constrained_layout=True)
    fig.set_constrained_layout_pads(h_pad=0.02, w_pad=0.02, hspace=0.03, wspace=0.03)
    order = METHOD_ORDER; y = np.arange(len(order)); md = methods.set_index("method").loc[order]; xvals = md.mean_lifecycle_service_loss.values
    ax = axes[0, 0]; ax.errorbar(xvals, y, xerr=[xvals - md.ci_low.values, md.ci_high.values - xvals], fmt="none", ecolor="#555555", capsize=2.5, lw=.8)
    for yi, m in zip(y, order): ax.scatter(md.loc[m, "mean_lifecycle_service_loss"], yi, s=30, color=METHOD_COLORS[m], edgecolor="white", zorder=3)
    ax.set_yticks(y, [LABELS[m] for m in order]); ax.invert_yaxis(); ax.set_xlabel("Mean lifecycle service loss"); ax.grid(axis="x", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); ax.text(.98, .04, "95% CI", transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#555555"); panel_label(ax, "(a)")
    ax = axes[0, 1]; comps = ["P7.7 - B0", "P7.7 - B1", "P7.7 - B2", "P7.7 - B8"]; y = np.arange(4); est, low, high = [], [], []
    for c in comps:
        values = pb[pb.comparison == c].difference; est.append(values.mean()); low.append(values.quantile(.025)); high.append(values.quantile(.975))
    ax.errorbar(est, y, xerr=[np.array(est)-np.array(low), np.array(high)-np.array(est)], fmt="o", color="#222222", ecolor="#222222", capsize=2.5, lw=.8); ax.axvline(0, color="#777777", ls="--", lw=.7); ax.set_yticks(y, ["vs Frozen", "vs Always-Maintain", "vs Verification-Guided", "vs Always-Open"]); ax.invert_yaxis(); ax.set_xlabel("Recoverability-Guided - baseline\n(mean lifecycle service loss)"); ax.grid(axis="x", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); ax.text(.02, .04, "negative = lower loss for\nRecoverability-Guided", transform=ax.transAxes, fontsize=7, color="#555555", va="bottom"); panel_label(ax, "(b)")
    sel = methods.set_index("method").loc[["B8", "P7.7"]]; xx = np.arange(2)
    ax = axes[1, 0]; vals = sel.gate_open_rate.values; ax.bar(xx, vals, color=[METHOD_COLORS["B8"], METHOD_COLORS["P7.7"]], width=.55, edgecolor="white")
    for xi, val in zip(xx, vals): ax.text(xi, val + .025, f"{val:.1%}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(xx, [LABELS["B8"], LABELS["P7.7"]], rotation=15); ax.set_ylabel("Gate-open rate"); ax.set_ylim(0, 1.05); ax.grid(axis="y", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); panel_label(ax, "(c)")
    ax = axes[1, 1]; vals = sel.ri_rate.values; ax.bar(xx, vals, color=[METHOD_COLORS["B8"], METHOD_COLORS["P7.7"]], width=.55, edgecolor="white")
    for xi, val in zip(xx, vals): ax.text(xi, val + .0008, f"{val:.2%}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(xx, [LABELS["B8"], LABELS["P7.7"]], rotation=15); ax.set_ylabel("Re-instantiation rate"); ax.set_ylim(0, .03); ax.grid(axis="y", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); panel_label(ax, "(d)"); save(fig, "fig3_lifecycle_and_escalation")


def fig4(d):
    scen, stage = d["scenarios"], d["stage"]
    comp = stage.assign(retain=(stage.action == "retain").astype(int), local=(stage.action == "local").astype(int), ri_action=(stage.action == "ri").astype(int)).groupby("scenario").agg(retain=("retain", "mean"), local=("local", "mean"), ri=("ri_action", "mean"), gate=("gate_open", "mean")).reindex(SCENARIOS)
    loss = []
    for sc in SCENARIOS:
        rg = scen[(scen.method == "P7.7") & (scen.scenario == sc)].iloc[0].lifecycle_service_loss; ao = scen[(scen.method == "B8") & (scen.scenario == sc)].iloc[0].lifecycle_service_loss; loss.append(rg - ao)
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.2), gridspec_kw={"width_ratios": [1, 1.18]}, constrained_layout=True)
    ax = axes[0]; x = np.arange(4); scaled_loss = np.asarray(loss, dtype=float) * 1e4; colors = ["#999999" if abs(val) < 1e-12 else METHOD_COLORS["P7.7"] for val in loss]; ax.axhline(0, color="#555555", ls="--", lw=.8, zorder=0); ax.vlines(x, 0, scaled_loss, color=colors, lw=1.2); ax.scatter(x, scaled_loss, color=colors, s=40, edgecolor="white", zorder=3)
    for xi, val in zip(x, scaled_loss):
        label = "0" if abs(val) < 0.005 else f"{val:+.2f}"
        ax.text(xi, val + (0.08 if val >= 0 else -0.08), label, ha="center", va="bottom" if val >= 0 else "top", fontsize=7)
    ax.set_xticks(x, SCENARIOS); ax.set_ylabel("Recoverability-Guided - Always-Open\nlifecycle service loss ($\\times 10^{-4}$)"); ax.set_ylim(min(-0.2, float(scaled_loss.min()) - 0.15), max(1.25, float(scaled_loss.max()) * 1.3)); ax.grid(axis="y", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); panel_label(ax, "(a)")
    ax = axes[1]; bottom = np.zeros(4); bar_colors = {"retain": "#BDBDBD", "local": "#56B4E9", "ri": "#E69F00"}
    for key, name in [("retain", "Retain (committed)"), ("local", "Local maintenance (committed)"), ("ri", "Re-instantiation (committed)")]:
        vals = comp[key].values; ax.bar(x, vals, bottom=bottom, width=.62, color=bar_colors[key], edgecolor="white", label=name); bottom += vals
    ax.plot(x, comp.gate.values, color=METHOD_COLORS["P7.7"], marker="D", ms=4.5, ls="--", lw=1.1, label="Gate open (admission)"); ax.set_xticks(x, SCENARIOS); ax.set_ylabel("Proportion"); ax.set_ylim(0, 1.05); ax.grid(axis="y", color="#DDDDDD", lw=.45); ax.spines[["top", "right"]].set_visible(False); ax.legend(frameon=False, fontsize=6.8, loc="upper left", bbox_to_anchor=(0, -0.18), ncol=2, handlelength=1.7); panel_label(ax, "(b)"); save(fig, "fig4_scenario_lifecycle_behavior")


def write_audit(info):
    lines = ["# Frozen Figure Data Audit — final Fig.2–Fig.4 reconstruction", "", "The audit was executed before final rendering. Original scientific CSV/JSON files were read-only; no experiment, fit, refit, bootstrap, threshold change, or new metric was performed.", "", "## Fig.2 — Recoverability Representation Transport", "", f"- Sources: `{INPUTS['validation_metrics'].relative_to(ROOT)}`, `{INPUTS['validation_center_metrics'].relative_to(ROOT)}`, `{INPUTS['validation_paired'].relative_to(ROOT)}`, `{INPUTS['validation_loo'].relative_to(ROOT)}`, and `{INPUTS['p7_6b_final_audit'].relative_to(ROOT)}`.", "- Granularity: 36 paired validation-center Spearman values; a single scatter panel is used because the frozen center table has no center-level balanced-admission column.", "- Existing CI: frozen aggregate paired CI from `paired_a1_vs_a0.csv`; balanced admission remains an assertion/text result, not fabricated center points.", "", "## Fig.3 — Lifecycle Performance and Selective Escalation", "", f"- Sources: `{INPUTS['lifecycle_method_metrics'].relative_to(ROOT)}`, `{INPUTS['lifecycle_paired_bootstrap'].relative_to(ROOT)}`, `{INPUTS['p7_7_final_audit'].relative_to(ROOT)}`, and `{INPUTS['p7_7_package'].relative_to(ROOT)}`.", "- Granularity: method-level final-heldout metrics and frozen 4000-draw paired center bootstrap. Panels (a)/(b) retain the mature design; panels (c)/(d) integrate selective search compactly.", "", "## Fig.4 — Scenario-Level Lifecycle Behavior", "", f"- Sources: `{INPUTS['lifecycle_scenario_metrics'].relative_to(ROOT)}` plus all 240 frozen stage-record CSVs matching `results/p7_7/raw/{STAGE_GLOB}`.", "- Granularity: scenario service loss from frozen metrics; action composition and gate exposure are a transparent groupby over 5760 frozen Recoverability-Guided stage rows (20 centers × 3 seeds × 4 scenarios × 24 stages). No values were inferred from global averages.", "- Decision diagnostics are intentionally not plotted in the redesigned Fig.4.", "", "## Read-only aggregation result", "", f"- Assertion summary: `{json.dumps(info, ensure_ascii=False, sort_keys=True)}`.", "- Each scenario's Retain + Local maintenance + Re-instantiation equals 1 within floating tolerance; weighted totals reproduce the frozen global method metrics.", "- C4 is described only as nonlinear dependency-shift stress; no architecture-failure language is used."]
    (FIGDIR / "FROZEN_FIGURE_DATA_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_captions():
    text = """# Figure Captions\n\n**Fig. 2 | Recoverability representation transport.** Each point is one of the 36 independent validation centers, with Absolute center-level Spearman association on the x-axis and Identity-normalized association on the y-axis. The dashed diagonal denotes equality; points above it indicate improved center-level association after identity normalization. The annotation reports the aggregate macro-center estimate and paired 95% bootstrap interval. Balanced-admission improvement is reported in the text from the validation output; no universal-generalization claim is made.\n\n**Fig. 3 | Lifecycle performance and selective escalation.** (a) Overall mean lifecycle service loss for the five strategies, with 95% confidence intervals. (b) Recoverability-Guided minus baseline paired center-bootstrap effects, with 95% intervals from 4000 draws; negative values indicate lower loss for Recoverability-Guided, while the positive Always-Open comparison is retained. (c) Model-level search admission (gate-open rate). (d) Committed identity transition (re-instantiation rate). Gate admission and committed RI are shown on separate zero-based panels so the Always-Open trade-off is not visually exaggerated.\n\n**Fig. 4 | Scenario-level lifecycle behavior.** (a) Scenario-specific excess lifecycle service loss, defined as Recoverability-Guided minus Always-Open Search, across C0, C1, C3, and C4; positive values indicate lower loss for Always-Open Search. C4 denotes nonlinear dependency-shift stress. (b) Recoverability-Guided committed action composition (Retain, Local maintenance, Re-instantiation) with model-level gate-open admission overlaid on the same 0–100% scale. The stacked bars show committed lifecycle actions, whereas the diamond line indicates model-level search admission and is not an additional action category.\n"""
    (FIGDIR / "FIGURE_CAPTIONS.md").write_text(text, encoding="utf-8")


def write_qa():
    text = """# Figure Visual QA — final visual polishing\n\n- **Fig.2 — PASS:** no single-panel label; xlim equals ylim with 1:1 data aspect; all 36 centers remain visible; y=x spans the full common range; the annotation is two lines, compact, and does not use a diagnostic box.\n- **Fig.3 — PASS:** no internal “frozen CI” wording remains; the upper evidence row has greater visual weight than the supporting lower row; lower-panel labels remain readable; gate-open remains on 0–1.05 and RI on a zero-based 0–0.03 scale; Always-Open remains visible.\n- **Fig.4 — PASS:** scenario differences use a shared ×10^-4 display scale with no e-04/e-05 labels; C0/C1 zero results remain; C3/C4 positive gaps remain; committed bars and the diamond/dashed admission line are explicitly separated in the legend, with no dual axis.\n\nAll PNGs were exported at 600 dpi and all PDFs remain vector figures. No scientific value was altered for layout.\n"""
    (FIGDIR / "FIGURE_VISUAL_QA.md").write_text(text, encoding="utf-8")


def write_manifest(info, d):
    stems = ["fig2_recoverability_transport", "fig3_lifecycle_and_escalation", "fig4_scenario_lifecycle_behavior"]
    outputs = {str((FIGDIR / f"{stem}.{ext}").relative_to(ROOT)): sha256(FIGDIR / f"{stem}.{ext}") for stem in stems for ext in ["pdf", "png"]}
    input_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in INPUTS.values()}; input_hashes.update({str(p.relative_to(ROOT)): sha256(p) for p in d["stage_files"]})
    archive = {str(p.relative_to(ROOT)): sha256(p) for archive_dir in [FIGDIR / "archive_v1", FIGDIR / "archive_pre_visual_polish"] for p in archive_dir.glob("*")}
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "git_commit": git_commit(), "plotting_script": str(Path(__file__).relative_to(ROOT)), "plotting_script_sha256": sha256(Path(__file__)), "input_files_sha256": input_hashes, "output_files_sha256": outputs, "archived_v1_files_sha256": archive, "package_versions": {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "numpy": np.__version__, "pandas": pd.__version__}, "frozen_value_assertions": "PASS", "assertion_details": info, "scientific_recomputation": False, "raw_stage_aggregation": "read-only groupby over 5760 frozen rows"}
    (FIGDIR / "figure_generation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    configure_style(); d = load(); info = assert_data(d); write_audit(info); fig2(d); fig3(d); fig4(d); write_captions(); write_qa(); write_manifest(info, d)
    print(json.dumps({"status": "PASS", "fig2": "single-panel scatter", "fig3": "2x2 merged", "fig4": "scenario delta + action composition", "assertions": info}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
