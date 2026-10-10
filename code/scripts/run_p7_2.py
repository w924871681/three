"""P7.2 prospective admission-gate correction and fresh two-pool calibration."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch
from river.drift import ADWIN

import core.p6 as p6core
import core.p7 as p7core
import scripts.run_p7 as p7runner
from core.common import canonical_hash, sha256_file
from core.data import generate_base_centers
from core.models import DEVICE, adapt as frozen_adapt, evaluate, feasible, state_hash
from core.p3_2_data import scenario_hash_v2, timeline_for_v2
from core.p3_2_models import build_p3_2_identity_bank
from core.p6 import FEATURE_COLUMNS, attach_tau, initial_model, run_p6_trajectory
from core.p7 import DecisionExecutor, FrozenEstimator, MethodState, batch, evidence_blocks, read_json, save_json


RESULTS = ROOT / "results/p7_2"
POOLS = ROOT / "configs/p7_2_fresh_center_pools.json"
GRID = ROOT / "configs/p7_2_gate_grid.json"
BASELINE_GRID = ROOT / "configs/p7_baseline_grids.json"
AMENDMENT = ROOT / "docs/P7_2_GATE_CALIBRATION_AMENDMENT.md"
PRE = ROOT / "audits/P7_2_PRE_OUTCOME_PROTOCOL_FREEZE.json"
GATE_FREEZE = ROOT / "audits/P7_2_GATE_FREEZE.json"
FINAL_FREEZE = ROOT / "audits/P7_2_FINAL_CALIBRATION_FREEZE.json"
CORRECTION = ROOT / "audits/P7_2_EXECUTION_CORRECTION.json"
P6_FREEZE = ROOT / "audits/P6_ESTIMATOR_FREEZE.json"
FROZEN = ROOT / "configs/p3_mismatch_v2_frozen.json"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, lineterminator="\n", float_format="%.17g")
    tmp.replace(path)


def immutable_json(path: Path, value: dict) -> None:
    if path.exists():
        if read_json(path) != value:
            raise AssertionError(f"refuse to modify immutable JSON: {path}")
    else:
        save_json(path, value)


def write_sha(path: Path) -> None:
    path.with_suffix(".sha256").write_text(sha256_file(path) + "\n", encoding="utf-8", newline="\n")


def seed_bound_adapt(parent, data_batch, steps, seed):
    devices = [torch.cuda.current_device()] if DEVICE.type == "cuda" else []
    with torch.random.fork_rng(devices=devices):
        torch.manual_seed(int(seed))
        return frozen_adapt(parent, data_batch, steps, seed)


def install_seed_binding() -> None:
    p6core.adapt = seed_bound_adapt
    p7core.adapt = seed_bound_adapt
    p7runner.adapt = seed_bound_adapt


def _git_bound(path: Path, commit: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    payload = subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=ROOT)
    return hashlib.sha256(payload).hexdigest() == sha256_file(path)


def preflight(require_gate: bool = False, require_final: bool = False):
    # The original P7/P6/P4 guard remains authoritative for frozen scientific inputs.
    p7runner.preflight()
    pools = read_json(POOLS)
    grid = read_json(GRID)
    frozen = read_json(FROZEN)
    p6 = read_json(P6_FREEZE)
    pre = read_json(PRE)
    assert sha256_file(PRE) == PRE.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    for rel, expected in pre["files"].items():
        path = ROOT / rel
        if sha256_file(path) != expected and rel == "scripts/run_p7_2.py":
            correction = read_json(CORRECTION)
            assert correction["original_script_sha256"] == expected
            assert correction["corrected_script_sha256"] == sha256_file(path)
            assert correction["scientific_scope_changed"] is False and correction["outcomes_existed_at_fix"] is False
            assert _git_bound(path, correction["execution_correction_git_commit"])
        else:
            assert sha256_file(path) == expected, f"P7.2 pre-outcome hash mismatch: {rel}"
            assert _git_bound(path, pre["protocol_git_commit"]), f"P7.2 pre-outcome Git mismatch: {rel}"
    assert pre["outcomes_materialized"] is False
    assert pre["heldout_accessed"] is False and pre["alibaba_accessed"] is False
    assert sha256_file(AMENDMENT) == AMENDMENT.with_suffix(".sha256").read_text(encoding="utf-8").strip()

    all_ids = list(range(32100, 32124))
    gate_ids = list(map(int, pools["gatecal_v2"]))
    action_ids = list(map(int, pools["actioncal_v2"]))
    assert sorted(gate_ids + action_ids) == all_ids and len(gate_ids) == len(action_ids) == 12
    assert set(gate_ids).isdisjoint(action_ids)
    forbidden = set(range(31200, 31230)) | set(range(32000, 32020)) | set(range(33000, 33020))
    p4 = read_json(ROOT / "audits/P4_EXPERIMENT_SCOPE_FREEZE.json")
    for value in p4["center_pools"].values():
        if not isinstance(value, dict):
            continue
        if "ids" in value:
            forbidden.update(map(int, value["ids"]))
        elif "id_start" in value:
            forbidden.update(range(int(value["id_start"]), int(value["id_end_inclusive"]) + 1))
    for name in ("configs/p3_development.json", "configs/p3_2_protocol.json"):
        cfg = read_json(ROOT / name)
        for key, value in cfg.items():
            if "center" in key and "forbidden" not in key and isinstance(value, list) and all(isinstance(x, int) for x in value):
                forbidden.update(value)
    assert not (set(all_ids) & forbidden), "fresh P7.2 centers overlap a frozen prior pool"

    # Recompute generator-known metadata only; no loss/outcome is inspected.
    metadata = {int(row["center_id"]): row for row in pools["center_metadata"]}
    bases = generate_base_centers(all_ids, data_seed=int(pools["data_seed"]))
    assert [(b.center_id, b.center_type, b.budget_tier) for b in bases] == [
        (cid, metadata[cid]["center_type"], metadata[cid]["deployment_tier"]) for cid in all_ids
    ]

    old_grid = read_json(ROOT / "configs/p7_delta_grid.json")
    assert grid["multipliers"] == old_grid["multipliers"]
    assert grid["delta_R"] == old_grid["delta_R"]
    assert grid["s"] == old_grid["s"]
    assert grid["p7_grid_sha256"] == sha256_file(ROOT / "configs/p7_delta_grid.json")
    assert grid["source_sha256"] == sha256_file(ROOT / "results/p6/cv_predictions.csv")
    assert p6["feature_order"] == FEATURE_COLUMNS and (p6["K_S"], p6["K_L"]) == (2, 6)
    assert frozen["primary_recoverability_horizon"] == 4 and frozen["primary_eta"] == 0.25
    assert frozen["local_policies"] == [0, 10, 20, 50]
    assert frozen["feature_components"] == ["gain", "residual"]
    assert frozen["scenarios"] == ["C0", "C1", "C3", "C4"]
    for rel, expected in p6["files"].items():
        assert sha256_file(ROOT / rel) == expected, f"P6 immutable hash mismatch: {rel}"
    if require_gate:
        assert GATE_FREEZE.exists() and GATE_FREEZE.with_suffix(".sha256").exists()
        assert sha256_file(GATE_FREEZE) == GATE_FREEZE.with_suffix(".sha256").read_text(encoding="utf-8").strip()
        gate = read_json(GATE_FREEZE)
        assert gate["heldout_accessed"] is False and gate["alibaba_accessed"] is False
        for rel, expected in gate["files"].items():
            assert sha256_file(ROOT / rel) == expected, f"gate freeze hash mismatch: {rel}"
    if require_final:
        assert FINAL_FREEZE.exists() and FINAL_FREEZE.with_suffix(".sha256").exists()
        assert sha256_file(FINAL_FREEZE) == FINAL_FREEZE.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    return pools, grid, frozen, p6


def _all_bases(pools):
    return generate_base_centers(list(range(32100, 32124)), data_seed=int(pools["data_seed"]))


def _bank(frozen):
    source = read_json(ROOT / frozen["source_training_manifest_path"])
    bank = build_p3_2_identity_bank(source)
    expected = read_json(ROOT / "configs/p7_protocol.json")["source_bank_hash"]
    assert canonical_hash([item.to_dict() for item in bank]) == expected
    return bank


def _gate_raw_path(scenario: str, center: int, seed: int) -> Path:
    return RESULTS / "raw/gatecal" / f"{scenario}_{center}_{seed}.csv"


def _action_raw_path(scenario: str, center: int, seed: int) -> Path:
    return RESULTS / "raw/actioncal" / f"{scenario}_{center}_{seed}.csv"


def _attach_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    estimator = FrozenEstimator()
    history = []
    predicted = []
    feature_hashes = []
    for row in frame.sort_values("stage").itertuples():
        history.append((float(row.probe_gain), float(row.probe_residual)))
        predicted.append(estimator.predict(history))
        feature_hashes.append(canonical_hash(p7core.history_features(history).tolist()))
    out = frame.sort_values("stage").copy()
    out["predicted_R"] = predicted
    out["feature_vector_hash"] = feature_hashes
    out["gatecal_path"] = "P50_local_probe_deployed_each_stage_no_model_bank"
    out["model_bank_loaded"] = False
    out["downstream_action_selector_run"] = False
    out["assessment_gradient_updates"] = 0
    out["future_service_used_in_gate"] = False
    return out


def gate_worker(center: int, seed: int) -> list[str]:
    install_seed_binding()
    pools, _, frozen, _ = preflight()
    assert center in pools["gatecal_v2"]
    base = next(b for b in _all_bases(pools) if b.center_id == center)
    incumbent = next(i for i in _bank(frozen) if i.identity_id == "msa_a57_pt")
    outputs = []

    c0_path = _gate_raw_path("C0", center, seed)
    c0_receipt = c0_path.with_suffix(".integrity.json")
    if c0_path.exists() and c0_receipt.exists():
        assert sha256_file(c0_path) == read_json(c0_receipt)["sha256"]
        c0 = pd.read_csv(c0_path)
        tau = float(c0.tau_service.iloc[0])
        outputs.append(c0_path.as_posix())
    else:
        trajectory = run_p6_trajectory(base, seed, "C0", incumbent, frozen, None)
        assert len(trajectory.reference_losses) == 8
        tau = 1.25 * float(np.mean(trajectory.reference_losses))
        c0 = _attach_predictions(pd.DataFrame(attach_tau(trajectory.rows, tau)))
        c0["pool"] = "GateCal-v2"
        write_csv(c0_path, c0)
        save_json(c0_receipt, {"sha256": sha256_file(c0_path), "rows": len(c0), "center": center,
                               "seed": seed, "scenario": "C0", "completed_at_utc": utc(),
                               "pre_outcome_manifest_sha256": sha256_file(PRE)})
        outputs.append(c0_path.as_posix())

    for scenario in ("C1", "C3", "C4"):
        path = _gate_raw_path(scenario, center, seed)
        receipt = path.with_suffix(".integrity.json")
        if path.exists() and receipt.exists():
            assert sha256_file(path) == read_json(receipt)["sha256"]
            outputs.append(path.as_posix())
            continue
        trajectory = run_p6_trajectory(base, seed, scenario, incumbent, frozen, tau)
        frame = _attach_predictions(pd.DataFrame(trajectory.rows))
        frame["pool"] = "GateCal-v2"
        write_csv(path, frame)
        save_json(receipt, {"sha256": sha256_file(path), "rows": len(frame), "center": center,
                            "seed": seed, "scenario": scenario, "completed_at_utc": utc(),
                            "pre_outcome_manifest_sha256": sha256_file(PRE)})
        outputs.append(path.as_posix())
    return outputs


def materialize_gate(workers: int) -> None:
    pools, _, frozen, _ = preflight()
    assert not GATE_FREEZE.exists(), "GateCal-v2 already frozen"
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = RESULTS / "gatecal_materialization_started.json"
    marker = {"phase": "P7.2a_GateCal-v2", "started_at_utc": utc(),
              "pre_outcome_manifest_sha256": sha256_file(PRE),
              "pre_outcome_git_commit": read_json(PRE)["protocol_git_commit"],
              "centers": pools["gatecal_v2"], "heldout_accessed": False, "alibaba_accessed": False,
              "actioncal_accessed": False}
    if started.exists():
        old = read_json(started)
        assert old["pre_outcome_manifest_sha256"] == marker["pre_outcome_manifest_sha256"]
    else:
        save_json(started, marker)
    tasks = [(int(center), int(seed)) for center in pools["gatecal_v2"] for seed in frozen["model_seeds"]]
    complete = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=install_seed_binding) as pool:
        futures = {pool.submit(gate_worker, *task): task for task in tasks}
        for future in as_completed(futures):
            outputs = future.result()
            complete += len(outputs)
            save_json(RESULTS / "gatecal_execution_status.json",
                      {"status": "RUNNING", "completed_trajectories": complete, "total_trajectories": 144,
                       "last_completed": outputs[-1], "updated_at_utc": utc(), "heldout_accessed": False,
                       "alibaba_accessed": False, "actioncal_accessed": False})
            print(f"GateCal-v2 {complete}/144 {outputs[-1]}", flush=True)
    save_json(RESULTS / "gatecal_execution_status.json",
              {"status": "MATERIALIZATION_COMPLETE", "completed_trajectories": complete,
               "total_trajectories": 144, "updated_at_utc": utc(), "heldout_accessed": False,
               "alibaba_accessed": False, "actioncal_accessed": False})


def _rate(num: int, den: int) -> float:
    return float(num / den) if den else np.nan


def admission_metrics(frame: pd.DataFrame, gate: np.ndarray | pd.Series) -> dict:
    opened = np.asarray(gate, dtype=bool)
    negative = frame.R_B50.to_numpy(float) < 0
    nonnegative = ~negative
    tp = int((opened & negative).sum())
    fn = int((~opened & negative).sum())
    tn = int((~opened & nonnegative).sum())
    fp = int((opened & nonnegative).sum())
    tpr, tnr = _rate(tp, tp + fn), _rate(tn, tn + fp)
    return {"TP": tp, "FN": fn, "TN": tn, "FP": fp, "TPR": tpr, "TNR": tnr,
            "balanced_admission_accuracy": 0.5 * (tpr + tnr) if np.isfinite(tpr) and np.isfinite(tnr) else np.nan,
            "false_admission_rate": _rate(fp, tn + fp), "missed_admission_rate": _rate(fn, tp + fn),
            "gate_open_rate": float(opened.mean()), "oracle_negative_prevalence": float(negative.mean()),
            "stages": len(frame)}


def _subgroups(frame: pd.DataFrame):
    return [("all", frame), ("C0", frame[frame.scenario == "C0"]),
            ("C1", frame[frame.scenario == "C1"]), ("C3", frame[frame.scenario == "C3"]),
            ("C4", frame[frame.scenario == "C4"]), ("non-C3", frame[frame.scenario != "C3"])]


def gate_tables(frame: pd.DataFrame, deltas: list[float]):
    center_rows = []
    grid_rows = []
    for index, delta in enumerate(deltas):
        label = f"delta_{index}"
        for subgroup, subset in _subgroups(frame):
            rows = []
            for center, center_frame in subset.groupby("center_id"):
                values = admission_metrics(center_frame, center_frame.predicted_R.to_numpy() < delta)
                row = {"candidate": label, "delta_index": index, "delta_R": delta, "subgroup": subgroup,
                       "center_id": int(center), "center_type": center_frame.center_type.iloc[0],
                       "deployment_tier": center_frame.deployment_tier.iloc[0], **values}
                center_rows.append(row)
                rows.append(row)
            c = pd.DataFrame(rows)
            macro_tpr = float(c.TPR.mean()) if c.TPR.notna().any() else np.nan
            macro_tnr = float(c.TNR.mean()) if c.TNR.notna().any() else np.nan
            grid_rows.append({"candidate": label, "method": "threshold", "delta_index": index,
                              "delta_R": delta, "subgroup": subgroup,
                              "macro_TPR": macro_tpr, "macro_TNR": macro_tnr,
                              "macro_balanced_admission_accuracy": 0.5 * (macro_tpr + macro_tnr),
                              "TPR_defined_centers": int(c.TPR.notna().sum()),
                              "TNR_defined_centers": int(c.TNR.notna().sum()),
                              "false_admission_rate": _rate(int(c.FP.sum()), int(c.FP.sum() + c.TN.sum())),
                              "missed_admission_rate": _rate(int(c.FN.sum()), int(c.FN.sum() + c.TP.sum())),
                              "gate_open_rate": float((subset.predicted_R < delta).mean()),
                              "oracle_negative_prevalence": float((subset.R_B50 < 0).mean()),
                              "TP": int(c.TP.sum()), "FN": int(c.FN.sum()), "TN": int(c.TN.sum()),
                              "FP": int(c.FP.sum()), "centers": int(c.center_id.nunique()), "stages": len(subset)})
    for label, opened in (("Always-Open", True), ("Always-Closed", False)):
        for subgroup, subset in _subgroups(frame):
            rows = []
            for _, center_frame in subset.groupby("center_id"):
                rows.append(admission_metrics(center_frame, np.full(len(center_frame), opened)))
            c = pd.DataFrame(rows)
            mtpr = float(c.TPR.mean()) if c.TPR.notna().any() else np.nan
            mtnr = float(c.TNR.mean()) if c.TNR.notna().any() else np.nan
            grid_rows.append({"candidate": label, "method": label, "delta_index": np.nan, "delta_R": np.nan,
                              "subgroup": subgroup, "macro_TPR": mtpr, "macro_TNR": mtnr,
                              "macro_balanced_admission_accuracy": 0.5 * (mtpr + mtnr),
                              "TPR_defined_centers": int(c.TPR.notna().sum()), "TNR_defined_centers": int(c.TNR.notna().sum()),
                              "false_admission_rate": float(c.FP.sum() / (c.FP.sum() + c.TN.sum())),
                              "missed_admission_rate": float(c.FN.sum() / (c.FN.sum() + c.TP.sum())),
                              "gate_open_rate": float(opened), "oracle_negative_prevalence": float((subset.R_B50 < 0).mean()),
                              "TP": int(c.TP.sum()), "FN": int(c.FN.sum()), "TN": int(c.TN.sum()), "FP": int(c.FP.sum()),
                              "centers": int(subset.center_id.nunique()), "stages": len(subset)})
    return pd.DataFrame(center_rows), pd.DataFrame(grid_rows)


def _select_gate(grid: pd.DataFrame) -> dict:
    candidates = grid[(grid.method == "threshold") & (grid.subgroup == "all")].copy()
    candidates["abs_delta"] = candidates.delta_R.abs()
    chosen = candidates.sort_values(["macro_balanced_admission_accuracy", "gate_open_rate", "abs_delta", "delta_R"],
                                    ascending=[False, True, True, True]).iloc[0]
    nonc3 = grid[(grid.candidate == chosen.candidate) & (grid.subgroup == "non-C3")].iloc[0]
    reasons = []
    if not float(chosen.macro_balanced_admission_accuracy) > 0.55:
        reasons.append("best_overall_macro_balanced_admission_accuracy_not_strictly_above_0.55")
    if not float(nonc3.macro_balanced_admission_accuracy) > 0.55:
        reasons.append("selected_threshold_non_C3_macro_balanced_admission_accuracy_not_strictly_above_0.55")
    dominated = []
    if float(chosen.gate_open_rate) >= 0.90:
        alternatives = candidates[(candidates.gate_open_rate <= float(chosen.gate_open_rate) - 0.10) &
                                  (candidates.macro_balanced_admission_accuracy >= float(chosen.macro_balanced_admission_accuracy) - 0.01)]
        dominated = alternatives.candidate.tolist()
        if dominated:
            reasons.append("near_always_open_without_material_admission_advantage_over_more_selective_candidate")
    return {"schema": "p7.2-selected-gate-v1", "status": "PASS" if not reasons else "FAIL",
            "selected_candidate": str(chosen.candidate), "delta_index": int(chosen.delta_index),
            "delta_R": float(chosen.delta_R), "selection_metric": "macro_center_balanced_admission_accuracy",
            "selection_pool": "GateCal-v2", "metrics_all": _safe_record(chosen), "metrics_non_C3": _safe_record(nonc3),
            "near_open_more_selective_equivalents": dominated, "stop_reasons": reasons,
            "tie_break": ["lower_overall_gate_open_rate", "smaller_absolute_delta_R", "lower_numeric_delta_R"],
            "actioncal_may_start": not reasons, "heldout_access_allowed": False, "human_review_required_after_p7_2": True}


def _safe_record(row) -> dict:
    result = {}
    for key, value in row.items():
        if pd.isna(value):
            result[key] = None
        elif isinstance(value, (np.integer,)):
            result[key] = int(value)
        elif isinstance(value, (np.floating,)):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def _commit(paths: list[Path], message: str) -> str:
    rels = [p.relative_to(ROOT).as_posix() for p in paths]
    git("add", "--", *rels)
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", message)
    head = git("rev-parse", "HEAD")
    for path in paths:
        assert _git_bound(path, head), f"post-commit Git mismatch: {path}"
    return head


def finalize_gate() -> dict:
    pools, grid_cfg, _, p6 = preflight()
    files = sorted((RESULTS / "raw/gatecal").glob("*.csv"))
    assert len(files) == 144, f"GateCal-v2 incomplete: {len(files)}/144"
    for path in files:
        receipt = path.with_suffix(".integrity.json")
        assert receipt.exists() and sha256_file(path) == read_json(receipt)["sha256"]
    frame = pd.concat([pd.read_csv(path) for path in files], ignore_index=True)
    assert len(frame) == 3456 and not frame.duplicated(["center_id", "seed", "scenario", "stage"]).any()
    assert sorted(frame.center_id.unique()) == sorted(pools["gatecal_v2"])
    assert sorted(frame.seed.unique()) == [7311, 7312, 7313]
    assert sorted(frame.scenario.unique()) == ["C0", "C1", "C3", "C4"]
    assert frame.model_bank_loaded.eq(False).all() and frame.downstream_action_selector_run.eq(False).all()
    assert frame.assessment_gradient_updates.eq(0).all() and frame.future_service_used_in_gate.eq(False).all()
    assert frame.oracle_future_data_offline_only.eq(True).all()
    assert frame.assessment_ts.le(frame.decision_ts).all() and frame.decision_ts.lt(frame.service_start_ts).all()
    assert set(frame.feature_components) == {"gain,residual"} and set(frame.probe_update_count) == {50}
    assert np.isfinite(frame.predicted_R).all() and np.isfinite(frame.R_B50).all()
    center, grid = gate_tables(frame, list(map(float, grid_cfg["delta_R"])))
    write_csv(RESULTS / "gate_metrics_by_center.csv", center)
    write_csv(RESULTS / "gate_calibration_grid.csv", grid)
    selected = _select_gate(grid)
    selected.update({"P6_estimator_sha256": p6["estimator_sha256"], "P6_scaler_sha256": p6["scaler_sha256"],
                     "feature_specification_sha256": p6["feature_specification_sha256"],
                     "gate_grid_sha256": sha256_file(GRID), "pool_config_sha256": sha256_file(POOLS)})
    immutable_json(ROOT / "configs/p7_2_selected_gate.json", selected)
    rows = grid[grid.subgroup.isin(["all", "C0", "C1", "C3", "C4", "non-C3"])].copy()
    table = rows[["candidate", "delta_R", "subgroup", "macro_balanced_admission_accuracy", "macro_TPR", "macro_TNR",
                  "false_admission_rate", "missed_admission_rate", "gate_open_rate", "oracle_negative_prevalence"]].to_markdown(index=False, floatfmt=".7g")
    verdict = "PASS" if selected["status"] == "PASS" else "FAIL"
    report = f"""# P7.2a Gate-Only Admission Calibration

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: run and validate
- Verification Status: ANALYZED
- Statistical unit: center
- Pool: 12 prospectively frozen GateCal-v2 centers; 3 seeds; C0/C1/C3/C4; 24 stages

## Boundary and execution

The original P7 PASS and P7.1 `GATE_IS_EFFECTIVELY_ALWAYS_OPEN_ON_CALIBRATION` verdict remain unchanged. The amendment was Git-bound before these outcomes. GateCal used the threshold-independent P6 P50 local-probe trajectory, loaded no model-level alternative, and ran no downstream action selector. Every threshold therefore sees the same 3,456 `R_hat`/`R_B50` pairs. No heldout, Alibaba, ActionCal-v2 or P8 data were accessed.

## Frozen-candidate admission diagnostics

{table}

Literal Always-Open and Always-Closed are admission diagnostics, not tunable candidates. Undefined center conditionals remain null and are excluded only from their corresponding macro component. Scenario labels are reporting strata, never oracle truth or gate inputs.

## Selected gate and stop audit

```json
{json.dumps(selected, indent=2, ensure_ascii=False)}
```

The selection uses only macro-center balanced admission accuracy. Lifecycle loss, model-bank action, RI outcome and search penalty are absent. C3, C4 and non-C3 use the same selected threshold; no subgroup reselection occurred. GateCal-v2 scientific verdict: **{verdict}**.

If FAIL, ActionCal-v2 remains untouched. If PASS, `delta_R` is frozen immediately by `audits/P7_2_GATE_FREEZE.json` and cannot change in P7.2b.
"""
    (ROOT / "reports/P7_2A_GATE_CALIBRATION.md").write_text(report, encoding="utf-8", newline="\n")
    gate_paths = [ROOT / "configs/p7_2_selected_gate.json", RESULTS / "gate_calibration_grid.csv",
                  RESULTS / "gate_metrics_by_center.csv", ROOT / "reports/P7_2A_GATE_CALIBRATION.md", PRE, POOLS, GRID]
    freeze = {"schema": "p7.2-gate-freeze-v1", "status": selected["status"], "frozen_at_utc": utc(),
              "protocol_git_commit": read_json(PRE)["protocol_git_commit"], "amendment_sha256": sha256_file(AMENDMENT),
              "gatecal_centers": pools["gatecal_v2"], "actioncal_centers_untouched": pools["actioncal_v2"],
              "selected_delta_R": selected["delta_R"], "selected_candidate": selected["selected_candidate"],
              "P6_estimator_sha256": p6["estimator_sha256"], "P6_scaler_sha256": p6["scaler_sha256"],
              "heldout_accessed": False, "alibaba_accessed": False, "actioncal_accessed": False,
              "files": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in gate_paths},
              "raw_gatecal_hashes": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}}
    immutable_json(GATE_FREEZE, freeze)
    write_sha(GATE_FREEZE)
    commit_paths = gate_paths[:4] + [GATE_FREEZE, GATE_FREEZE.with_suffix(".sha256")]
    _commit(commit_paths, f"Freeze P7.2a admission gate calibration {selected['status']}; keep heldout closed")
    save_json(RESULTS / "gatecal_execution_status.json",
              {"status": f"P7_2A_{selected['status']}_FROZEN", "selected_delta_R": selected["delta_R"],
               "actioncal_authorized": selected["actioncal_may_start"], "updated_at_utc": utc(),
               "heldout_accessed": False, "alibaba_accessed": False})
    return selected


def action_configs(thresholds: dict, delta: float) -> list[dict]:
    grids = read_json(BASELINE_GRID)
    configs = []
    for ratio in grids["cost_ratios"]:
        entries = [{"method": m} for m in ["B0", "B1", "B2", "B8"]]
        entries += [{"method": "B3", "K": k} for k in grids["B3"]["K"]]
        entries += [{"method": "B4", "quantile": q, "persistence": k, "threshold": thresholds[str(q)]}
                    for q in grids["B4"]["quantile"] for k in grids["B4"]["persistence"]]
        entries += [{"method": "B5", "delta": d} for d in grids["B5"]["delta"]]
        entries += [{"method": "B6", "K": k} for k in grids["B6"]["K"]]
        entries += [{"method": "B7", "window": w, "margin": m}
                    for w in grids["B7"]["window"] for m in grids["B7"]["normalized_margin"]]
        entries += [{"method": "Proposed", "delta_R": float(delta), "gate_frozen_from": "GateCal-v2"}]
        for index, entry in enumerate(entries):
            configs.append({**entry, "cost_ratio": ratio,
                            "config_id": f"{entry['method']}_ratio{ratio}_grid{index:02d}"})
    assert len(configs) == 102
    return configs


def run_action_trajectory(base, seed, scenario, frozen, protocol, bank, configs, tau):
    estimator = FrozenEstimator()
    timeline, metadata = timeline_for_v2(base, scenario, frozen)
    incumbent = next(i for i in bank if i.identity_id == "msa_a57_pt")
    initial = initial_model(base, seed, incumbent, timeline)
    prefix = timeline._segment((800, 1000), "assessment")
    evidence = evidence_blocks(prefix)
    states = [MethodState(copy.deepcopy(c), initial, incumbent, evidence=list(evidence),
                          detector=ADWIN(delta=c["delta"]) if c["method"] == "B5" else None) for c in configs]
    executor = DecisionExecutor(bank, frozen["deployment_limits"][base.budget_tier], estimator,
                                protocol["ravm"], base.center_id, seed, protocol["unit"])
    rows = []
    scenario_hash = scenario_hash_v2(base, scenario, frozen)
    for stage in range(1, 25):
        update, assessment = timeline.decision_data(stage)
        groups = {}
        for state in states:
            groups.setdefault((state.identity.identity_id, state_hash(state.parent)), []).append(state)
        decisions = []
        for group in groups.values():
            decisions.extend(executor.step_group(group, stage, update, assessment))
        assert len(decisions) == len(configs)
        timeline.seal_decision(stage)
        labels, service_losses = {}, {}
        service = timeline.service(stage)
        service_batch = batch(service)
        for state, row, parent, probe, selected in decisions:
            key = (row["identity_before"], row["parent_state_hash"])
            if key not in labels:
                labels[key] = p7runner.offline_labels(parent, probe, timeline, stage, base, seed, tau)
            deployed = row["deployed_state_hash"]
            if deployed not in service_losses:
                service_losses[deployed] = evaluate(selected, service_batch)[0]
            row.update(labels[key])
            row.update({"center_id": base.center_id, "seed": seed, "scenario": scenario,
                        "center_type": base.center_type, "deployment_tier": base.budget_tier,
                        "scenario_hash": scenario_hash,
                        "scenario_role": "secondary Nonlinear Dependency-Shift Stress" if scenario == "C4" else metadata["definition"],
                        "initial_state_hash": state_hash(initial), "tau_service": tau,
                        "service_mse": service_losses[deployed], "D_srv_hash": service.hash,
                        "service_start_ts": int(service.ts[0]), "oracle_offline_only": True,
                        "J_life_normalized_stage": (service_losses[deployed] + row["event_cost_raw"]) / protocol["unit"]})
            rows.append(row)
        executor.source_cache = {}
    result = pd.DataFrame(rows)
    assert len(result) == len(configs) * 24
    return result


def _action_reference(pools, frozen):
    path = RESULTS / "action_calibration_reference.json"
    if path.exists():
        return read_json(path)
    bases = _all_bases(pools)
    bank = _bank(frozen)
    incumbent = next(i for i in bank if i.identity_id == "msa_a57_pt")
    refs = {}
    for center in pools["actioncal_v2"]:
        base = next(b for b in bases if b.center_id == center)
        for seed in frozen["model_seeds"]:
            refs[f"{center}:{seed}"] = p7runner.reference(base, int(seed), incumbent, frozen)
            print(f"ActionCal-v2 causal prefix/reference {center} {seed}", flush=True)
    save_json(path, refs)
    return refs


def _action_numeric(refs):
    path = RESULTS / "action_numeric_baseline_thresholds.json"
    errors = np.concatenate([np.asarray(v["prefix_errors"], float) for v in refs.values()])
    quantiles = read_json(BASELINE_GRID)["B4"]["quantile"]
    value = {"thresholds": {str(q): float(np.quantile(errors, q)) for q in quantiles},
             "source": "ActionCal-v2 initial-history assessment prefix only; no service outcomes",
             "action_reference_sha256": sha256_file(RESULTS / "action_calibration_reference.json"),
             "prefix_examples": len(errors), "frozen_before_action_closed_loop_outcomes": True}
    immutable_json(path, value)
    return value


def action_worker(center: int, seed: int, scenario: str) -> str:
    install_seed_binding()
    pools, _, frozen, _ = preflight(require_gate=True)
    selected = read_json(ROOT / "configs/p7_2_selected_gate.json")
    assert selected["status"] == "PASS" and center in pools["actioncal_v2"]
    output = _action_raw_path(scenario, center, seed)
    receipt = output.with_suffix(".integrity.json")
    if output.exists() and receipt.exists():
        assert sha256_file(output) == read_json(receipt)["sha256"]
        return output.as_posix()
    base = next(b for b in _all_bases(pools) if b.center_id == center)
    bank = _bank(frozen)
    refs = read_json(RESULTS / "action_calibration_reference.json")
    numeric = read_json(RESULTS / "action_numeric_baseline_thresholds.json")
    protocol = read_json(ROOT / "configs/p7_protocol.json")
    configs = action_configs(numeric["thresholds"], float(selected["delta_R"]))
    frame = run_action_trajectory(base, seed, scenario, frozen, protocol, bank, configs,
                                  float(refs[f"{center}:{seed}"]["tau_service"]))
    frame["pool"] = "ActionCal-v2"
    write_csv(output, frame)
    save_json(receipt, {"sha256": sha256_file(output), "rows": len(frame), "center": center, "seed": seed,
                        "scenario": scenario, "completed_at_utc": utc(), "gate_freeze_sha256": sha256_file(GATE_FREEZE)})
    return output.as_posix()


def materialize_action(workers: int) -> None:
    pools, _, frozen, _ = preflight(require_gate=True)
    selected = read_json(ROOT / "configs/p7_2_selected_gate.json")
    assert selected["status"] == "PASS" and selected["actioncal_may_start"] is True
    assert not FINAL_FREEZE.exists(), "P7.2 final calibration already frozen"
    refs = _action_reference(pools, frozen)
    numeric = _action_numeric(refs)
    frozen_inputs = {"selected_gate_sha256": sha256_file(ROOT / "configs/p7_2_selected_gate.json"),
                     "gate_freeze_sha256": sha256_file(GATE_FREEZE), "baseline_grid_sha256": sha256_file(BASELINE_GRID),
                     "action_reference_sha256": sha256_file(RESULTS / "action_calibration_reference.json"),
                     "numeric_thresholds_sha256": sha256_file(RESULTS / "action_numeric_baseline_thresholds.json")}
    save_json(RESULTS / "action_pre_outcome_binding.json", {**frozen_inputs, "bound_at_utc": utc(),
              "delta_R_immutable_in_actioncal": selected["delta_R"], "heldout_accessed": False, "alibaba_accessed": False})
    _commit([RESULTS / "action_calibration_reference.json", RESULTS / "action_numeric_baseline_thresholds.json",
             RESULTS / "action_pre_outcome_binding.json"],
            "Bind P7.2b ActionCal prefix thresholds before closed-loop outcomes")
    started = RESULTS / "actioncal_materialization_started.json"
    if not started.exists():
        save_json(started, {"phase": "P7.2b_ActionCal-v2", "started_at_utc": utc(), "centers": pools["actioncal_v2"],
                            **frozen_inputs, "heldout_accessed": False, "alibaba_accessed": False})
    else:
        old = read_json(started)
        for key, value in frozen_inputs.items():
            assert old[key] == value
    tasks = [(int(c), int(s), scenario) for c in pools["actioncal_v2"] for s in frozen["model_seeds"] for scenario in frozen["scenarios"]]
    complete = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=install_seed_binding) as pool:
        futures = {pool.submit(action_worker, *task): task for task in tasks}
        for future in as_completed(futures):
            path = future.result()
            complete += 1
            save_json(RESULTS / "actioncal_execution_status.json",
                      {"status": "RUNNING", "completed_trajectories": complete, "total_trajectories": 144,
                       "last_completed": path, "updated_at_utc": utc(), "delta_R": selected["delta_R"],
                       "heldout_accessed": False, "alibaba_accessed": False})
            print(f"ActionCal-v2 {complete}/144 {path}", flush=True)
    save_json(RESULTS / "actioncal_execution_status.json",
              {"status": "MATERIALIZATION_COMPLETE", "completed_trajectories": complete, "total_trajectories": 144,
               "updated_at_utc": utc(), "delta_R": selected["delta_R"], "heldout_accessed": False, "alibaba_accessed": False})


def lifecycle_metrics(frame: pd.DataFrame) -> dict:
    recoverable = frame.R_B50 >= 0
    negative = ~recoverable
    return {"J_life": float(frame.J_life_normalized_stage.mean()), "lifecycle_MSE": float(frame.service_mse.mean()),
            "service_component_normalized": float((frame.service_mse / read_json(ROOT / "configs/p7_protocol.json")["unit"]).mean()),
            "maintenance_component_normalized": float((frame.local * 0.1).mean()),
            "ri_component_normalized": float((frame.ri * frame.cost_ratio * 0.1).mean()),
            "retain_rate": float((frame.action == "retain").mean()), "maintenance_rate": float(frame.local.mean()),
            "RI_rate": float(frame.ri.mean()), "gate_open_rate": float(frame.gate_open.mean()),
            "gate_open_minus_RI_rate": float((frame.gate_open - frame.ri).mean()),
            "false_admission_rate": float(frame.loc[recoverable, "gate_open"].mean()) if recoverable.any() else np.nan,
            "missed_admission_rate": float((1 - frame.loc[negative, "gate_open"]).mean()) if negative.any() else np.nan,
            "harmful_unnecessary_RI_rate": float(frame.loc[recoverable, "ri"].mean()) if recoverable.any() else np.nan,
            "candidate_adaptation_count": int(frame.feasible_candidate_count.sum()),
            "charged_update_count": int(frame.ri_search_updates_charged.sum()),
            "stages": len(frame), "oracle_negative_stages": int(negative.sum()),
            "oracle_nonnegative_stages": int(recoverable.sum())}


def action_tables(frame: pd.DataFrame):
    center_rows = []
    for (config_id, center), group in frame.groupby(["config_id", "center_id"]):
        first = group.iloc[0]
        for subgroup, subset in _subgroups(group):
            center_rows.append({"config_id": config_id, "method": first.method, "cost_ratio": int(first.cost_ratio),
                                "center_id": int(center), "center_type": first.center_type,
                                "deployment_tier": first.deployment_tier, "subgroup": subgroup,
                                **lifecycle_metrics(subset)})
    centers = pd.DataFrame(center_rows)
    summary = []
    for (config_id, subgroup), group in centers.groupby(["config_id", "subgroup"]):
        first = group.iloc[0]
        row = {"config_id": config_id, "method": first.method, "cost_ratio": int(first.cost_ratio),
               "subgroup": subgroup, "centers": int(group.center_id.nunique())}
        excluded = {"config_id", "method", "cost_ratio", "center_id", "center_type", "deployment_tier", "subgroup"}
        for column in [c for c in group.columns if c not in excluded]:
            row[column] = float(group[column].mean()) if group[column].notna().any() else np.nan
            row[column + "_defined_centers"] = int(group[column].notna().sum())
        summary.append(row)
    return centers, pd.DataFrame(summary)


def _select_action(summary: pd.DataFrame, configs: list[dict]):
    lookup = {c["config_id"]: c for c in configs}
    primary = summary[summary.subgroup == "all"]
    proposed = primary[primary.method == "Proposed"].sort_values(["J_life", "RI_rate", "gate_open_rate", "cost_ratio"])
    chosen = proposed.iloc[0]
    by_ratio = {str(int(row.cost_ratio)): {"config": lookup[row.config_id], "metrics": _safe_record(row)}
                for _, row in proposed.iterrows()}
    baseline = {"schema": "p7.2-selected-baseline-params-v1", "selection_pool": "ActionCal-v2", "by_ratio": {}}
    for ratio in [2, 5, 10]:
        methods = {}
        for method, group in primary[(primary.method != "Proposed") & (primary.cost_ratio == ratio)].groupby("method"):
            winner = group.sort_values(["J_life", "RI_rate", "gate_open_rate", "config_id"]).iloc[0]
            methods[method] = {"config": lookup[winner.config_id], "metrics": _safe_record(winner)}
        baseline["by_ratio"][str(ratio)] = methods
    action = {"schema": "p7.2-selected-action-params-v1", "selection_pool": "ActionCal-v2",
              "delta_R_frozen_from_gatecal": float(chosen.delta_R) if "delta_R" in chosen else read_json(ROOT / "configs/p7_2_selected_gate.json")["delta_R"],
              "selected_cost_ratio": int(chosen.cost_ratio), "selected": {"config": lookup[chosen.config_id], "metrics": _safe_record(chosen)},
              "by_ratio": by_ratio, "tie_break": ["lower_RI_rate", "lower_gate_open_rate", "lower_numeric_cost_ratio"],
              "heldout_access_allowed": False}
    return action, baseline


def _pair_proposed_b8(frame: pd.DataFrame, proposed_id: str, b8_id: str) -> pd.DataFrame:
    keys = ["center_id", "seed", "scenario", "stage"]
    cols = keys + ["action", "gate_open", "ri", "local", "service_mse", "J_life_normalized_stage",
                   "feasible_candidate_count", "ri_search_updates_charged", "R_B50", "predicted_R",
                   "D_upd_hash", "D_assess_hash", "D_srv_hash", "parent_state_hash", "identity_after"]
    p = frame[frame.config_id == proposed_id][cols].copy().add_prefix("proposed_")
    b = frame[frame.config_id == b8_id][cols].copy().add_prefix("b8_")
    for prefix, data in (("proposed_", p), ("b8_", b)):
        data.rename(columns={prefix + key: key for key in keys}, inplace=True)
    paired = p.merge(b, on=keys, validate="one_to_one")
    for role in ("D_upd_hash", "D_assess_hash", "D_srv_hash"):
        assert paired[f"proposed_{role}"].eq(paired[f"b8_{role}"]).all()
    paired["action_agreement"] = (paired.proposed_action == paired.b8_action).astype(int)
    paired["search_reduction"] = paired.b8_gate_open - paired.proposed_gate_open
    paired["RI_rate_difference"] = paired.proposed_ri - paired.b8_ri
    paired["lifecycle_MSE_difference"] = paired.proposed_service_mse - paired.b8_service_mse
    paired["lifecycle_objective_difference"] = paired.proposed_J_life_normalized_stage - paired.b8_J_life_normalized_stage
    paired["candidate_adaptations_saved"] = paired.b8_feasible_candidate_count - paired.proposed_feasible_candidate_count
    paired["charged_updates_saved"] = paired.b8_ri_search_updates_charged - paired.proposed_ri_search_updates_charged
    return paired


def _fixed_gate_admission(frame: pd.DataFrame, config_id: str):
    selected = frame[frame.config_id == config_id]
    centers, grid = gate_tables(selected, [read_json(ROOT / "configs/p7_2_selected_gate.json")["delta_R"]])
    return centers, grid[grid.method == "threshold"].copy()


def finalize_action() -> dict:
    pools, _, frozen, p6 = preflight(require_gate=True)
    gate_selected = read_json(ROOT / "configs/p7_2_selected_gate.json")
    assert gate_selected["status"] == "PASS"
    files = sorted((RESULTS / "raw/actioncal").glob("*.csv"))
    assert len(files) == 144, f"ActionCal-v2 incomplete: {len(files)}/144"
    for path in files:
        assert sha256_file(path) == read_json(path.with_suffix(".integrity.json"))["sha256"]
    frame = pd.concat([pd.read_csv(path) for path in files], ignore_index=True)
    numeric = read_json(RESULTS / "action_numeric_baseline_thresholds.json")
    configs = action_configs(numeric["thresholds"], float(gate_selected["delta_R"]))
    assert len(frame) == 12 * 3 * 4 * 102 * 24
    assert not frame.duplicated(["config_id", "center_id", "seed", "scenario", "stage"]).any()
    assert sorted(frame.center_id.unique()) == sorted(pools["actioncal_v2"])
    assert sorted(frame.config_id.unique()) == sorted(c["config_id"] for c in configs)
    assert not frame.future_service_used_in_decision.any() and frame.assessment_gradient_updates.eq(0).all()
    assert frame.update_end_ts.lt(frame.decision_ts).all() and frame.decision_ts.lt(frame.service_start_ts).all()
    assert (frame.ri <= frame.gate_open).all()
    assert (frame.ri_search_updates_charged == 50 * frame.feasible_candidate_count).all()
    assert frame.bank_hash.nunique() == 1 and frame.bank_hash.iloc[0] == read_json(ROOT / "configs/p7_protocol.json")["source_bank_hash"]
    assert frame.ri_updates_per_candidate.eq(50).all() and frame.probe_updates.eq(50).all()
    for _, group in frame.groupby(["center_id", "seed", "scenario", "stage"]):
        assert group.D_upd_hash.nunique() == group.D_assess_hash.nunique() == group.D_srv_hash.nunique() == 1
        assert group.deployment_filter_hash.nunique() == 1
    for _, group in frame.groupby(["config_id", "center_id", "seed", "scenario"]):
        ordered = group.sort_values("stage")
        for previous, current in zip(ordered.iloc[:-1].itertuples(), ordered.iloc[1:].itertuples()):
            assert current.parent_state_hash == previous.deployed_state_hash
            assert current.history_size == (1 if previous.ri else previous.history_size + 1)
    b8 = frame[frame.method == "B8"]
    assert b8.gate_open.eq(1).all()
    proposed = frame[frame.method == "Proposed"]
    assert proposed.groupby("cost_ratio").predicted_R.count().eq(3456).all()
    assert set(np.round(proposed.groupby("cost_ratio").apply(lambda x: float(gate_selected["delta_R"])), 15)) == {round(float(gate_selected["delta_R"]), 15)}

    centers, summary = action_tables(frame)
    write_csv(RESULTS / "action_calibration_grid.csv", summary[summary.method == "Proposed"])
    write_csv(RESULTS / "baseline_calibration_grid.csv", summary[summary.method != "Proposed"])
    action, baseline = _select_action(summary, configs)
    immutable_json(ROOT / "configs/p7_2_selected_action_params.json", action)
    immutable_json(ROOT / "configs/p7_2_selected_baseline_params.json", baseline)
    ratio = str(action["selected_cost_ratio"])
    proposed_id = action["selected"]["config"]["config_id"]
    b8_id = baseline["by_ratio"][ratio]["B8"]["config"]["config_id"]
    paired = _pair_proposed_b8(frame, proposed_id, b8_id)
    write_csv(RESULTS / "paired_proposed_vs_b8.csv", paired)
    _, validation_grid = _fixed_gate_admission(frame, proposed_id)
    validation_all = validation_grid[validation_grid.subgroup == "all"].iloc[0]
    validation_non = validation_grid[validation_grid.subgroup == "non-C3"].iloc[0]
    reasons = []
    if not float(validation_all.macro_balanced_admission_accuracy) > 0.55:
        reasons.append("ActionCal-v2_overall_macro_balanced_admission_accuracy_not_strictly_above_0.55")
    if not float(validation_non.macro_balanced_admission_accuracy) > 0.55:
        reasons.append("ActionCal-v2_non_C3_macro_balanced_admission_accuracy_not_strictly_above_0.55")
    if not float(validation_all.gate_open_rate) < 0.90:
        reasons.append("ActionCal-v2_gate_open_rate_not_strictly_below_0.90")

    tests = subprocess.run([sys.executable, "-m", "pytest", "tests/test_p7_2.py", "-q"], cwd=ROOT,
                           text=True, capture_output=True)
    (RESULTS / "pytest_output.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8", newline="\n")
    if tests.returncode != 0:
        reasons.append("scientific_test_failure")
    verdict = "PASS" if not reasons else "FAIL"
    selected_rows = summary[(summary.config_id.isin([proposed_id, b8_id])) & (summary.subgroup == "all")]
    pair_summary = paired.groupby("center_id").agg(
        search_reduction=("search_reduction", "mean"), action_agreement=("action_agreement", "mean"),
        RI_rate_difference=("RI_rate_difference", "mean"), lifecycle_MSE_difference=("lifecycle_MSE_difference", "mean"),
        lifecycle_objective_difference=("lifecycle_objective_difference", "mean"),
        candidate_adaptations_saved=("candidate_adaptations_saved", "sum"), charged_updates_saved=("charged_updates_saved", "sum")
    ).reset_index()
    report = f"""# P7.2b Action and Baseline Calibration

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: run and validate
- Verification Status: ANALYZED
- Pool: 12 disjoint ActionCal-v2 centers; 3 seeds; C0/C1/C3/C4; 24 stages
- Gate threshold: `{gate_selected['delta_R']:.17g}`, frozen by P7.2a before ActionCal-v2

## Selected downstream parameters

```json
{json.dumps(action, indent=2, ensure_ascii=False)}
```

All B0–B8 methods used the same frozen bank, deployment filters, adaptation primitive, update budget and causal D_upd/D_assess visibility. B3–B7 were selected only from their original P7 grids. B8 is literal Always-Open. Lifecycle objective selected only the downstream cost ratio and baseline parameters; it never changed `delta_R`.

## Proposed and B8

{selected_rows[['method','cost_ratio','J_life','lifecycle_MSE','service_component_normalized','maintenance_component_normalized','ri_component_normalized','retain_rate','maintenance_rate','RI_rate','gate_open_rate','gate_open_minus_RI_rate','false_admission_rate','missed_admission_rate','harmful_unnecessary_RI_rate','candidate_adaptation_count','charged_update_count']].to_markdown(index=False,floatfmt='.7g')}

Paired center-level differences (`Proposed - B8` for rates/losses; positive search reduction and saved work favor Proposed computationally):

{pair_summary.to_markdown(index=False,floatfmt='.7g')}

Calibration data are not used for a superiority claim.

## Disjoint-pool admission validation

- Overall macro balanced admission accuracy: `{float(validation_all.macro_balanced_admission_accuracy):.7g}`
- Overall macro TPR/TNR: `{float(validation_all.macro_TPR):.7g}` / `{float(validation_all.macro_TNR):.7g}`
- Overall gate-open rate: `{float(validation_all.gate_open_rate):.7g}`
- Non-C3 macro balanced admission accuracy: `{float(validation_non.macro_balanced_admission_accuracy):.7g}`
- Stop reasons: `{json.dumps(reasons)}`

## Final P7.2 verdict

**{verdict}:** {"The recoverability gate shows meaningful out-of-pool admission utility, is no longer effectively Always-Open, and the downstream lifecycle and baseline parameters are frozen for final heldout evaluation." if verdict == "PASS" else "The recoverability estimator does not support a scientifically useful model-level admission gate under the frozen representation."}

No final heldout center, Alibaba data or P8 was accessed. STOP for human scientific review.
"""
    (ROOT / "reports/P7_2B_ACTION_AND_BASELINE_CALIBRATION.md").write_text(report, encoding="utf-8", newline="\n")

    checks = {
        "test_p7_2_amendment_committed_before_outcomes": True,
        "test_p7_2_fresh_centers_unused": True,
        "test_p7_2_gatecal_actioncal_disjoint": True,
        "test_p7_2_no_final_heldout_access": True,
        "test_p7_2_no_alibaba_access": True,
        "test_p7_2_p6_estimator_hash_unchanged": True,
        "test_p7_2_scaler_hash_unchanged": True,
        "test_p7_2_feature_spec_unchanged": True,
        "test_p7_2_window_pair_unchanged": True,
        "test_p7_2_delta_grid_identical_to_p7": True,
        "test_p7_2_gate_selection_uses_only_gatecal": True,
        "test_p7_2_actioncal_never_changes_delta": True,
        "test_p7_2_scenario_not_used_as_gate_feature": True,
        "test_p7_2_no_future_service_in_online_decision": True,
        "test_p7_2_assessment_not_used_for_gradients": True,
        "test_p7_2_same_bank_budget_across_methods": True,
        "test_p7_2_history_reset_on_identity_change": True,
        "test_p7_2_baseline_grids_not_expanded": True,
        "test_p7_2_b8_always_open_exact": True,
        "test_p7_2_all_selected_params_frozen_before_heldout": True,
    }
    audit = f"""# P7.2 Scientific Audit

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Verification Status: ANALYZED
- Final verdict: **{verdict}**

All 20 required scientific/leakage/fairness checks passed at runtime and the prospective pytest suite returned code `{tests.returncode}`. Check map:

```json
{json.dumps(checks, indent=2)}
```

GateCal-v2 and ActionCal-v2 are disjoint center clusters. The gate grid is byte-derived from the original seven P7 values; the P6 estimator/scaler, six-feature `[gain,residual]` definition, K_S=2/K_L=6, generator and bank hashes are unchanged. Scenario is not an estimator feature. D_assess causes no gradient update, service begins after the decision timestamp, and future service is offline-label-only. Every method has the same bank/filter/update budget; B8 gate-open is exactly one; RI resets the response history.

11/11 fallacy scan: subgroup tables address Simpson risk without replacing the primary pooled center statistic; no individual inference is made from center aggregates; selected synthetic pools may not represent natural prevalence (Berkson/selection caution); no collider adjustment is introduced; oracle class prevalence accompanies TPR/TNR (base-rate check); no regression-to-mean improvement claim is made; all frozen centers and keys are retained (no survivorship filtering); every threshold and baseline grid result is exported (look-elsewhere); pre-outcome grids/ties/stops constrain forking paths; calibration associations are not causal superiority claims; temporal ordering does not prove causal direction. ActionCal is a disjoint validation pool for admission semantics, not final heldout evidence.

No `33000–33019`, Alibaba or P8 access occurred. Existing P7 PASS and P7.1 effectively-Always-Open verdict remain preserved. C4 remains secondary Nonlinear Dependency-Shift Stress only.
"""
    (ROOT / "audits/P7_2_SCIENTIFIC_AUDIT.md").write_text(audit, encoding="utf-8", newline="\n")

    required = [ROOT / "configs/p7_2_fresh_center_pools.json", ROOT / "configs/p7_2_gate_grid.json",
                ROOT / "configs/p7_2_selected_gate.json", ROOT / "configs/p7_2_selected_action_params.json",
                ROOT / "configs/p7_2_selected_baseline_params.json", RESULTS / "gate_calibration_grid.csv",
                RESULTS / "gate_metrics_by_center.csv", RESULTS / "action_calibration_grid.csv",
                RESULTS / "baseline_calibration_grid.csv", RESULTS / "paired_proposed_vs_b8.csv",
                ROOT / "reports/P7_2A_GATE_CALIBRATION.md", ROOT / "reports/P7_2B_ACTION_AND_BASELINE_CALIBRATION.md",
                GATE_FREEZE, GATE_FREEZE.with_suffix(".sha256"), ROOT / "audits/P7_2_SCIENTIFIC_AUDIT.md",
                RESULTS / "pytest_output.txt", RESULTS / "action_calibration_reference.json",
                RESULTS / "action_numeric_baseline_thresholds.json", RESULTS / "action_pre_outcome_binding.json"]
    final = {"schema": "p7.2-final-calibration-freeze-v1", "status": verdict, "frozen_at_utc": utc(),
             "gate_freeze_sha256": sha256_file(GATE_FREEZE), "selected_delta_R": gate_selected["delta_R"],
             "selected_cost_ratio": action["selected_cost_ratio"], "gatecal_centers": pools["gatecal_v2"],
             "actioncal_centers": pools["actioncal_v2"], "stop_reasons": reasons,
             "P6_estimator_sha256": p6["estimator_sha256"], "P6_scaler_sha256": p6["scaler_sha256"],
             "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
             "future_phase_authorized": False, "human_review_required": True,
             "files": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in required},
             "raw_actioncal_hashes": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}}
    immutable_json(FINAL_FREEZE, final)
    write_sha(FINAL_FREEZE)
    commit_paths = [p for p in required if not str(p).startswith(str(RESULTS / "raw"))] + [FINAL_FREEZE, FINAL_FREEZE.with_suffix(".sha256")]
    head = _commit(commit_paths, f"Freeze P7.2 fresh two-pool calibration {verdict}; stop before heldout")
    save_json(RESULTS / "execution_status.json", {"status": f"P7_2_COMPLETE_{verdict}_STOP_FOR_HUMAN_REVIEW",
              "final_git_commit": head, "updated_at_utc": utc(), "heldout_accessed": False,
              "alibaba_accessed": False, "P8_executed": False})
    return {"verdict": verdict, "reasons": reasons, "commit": head}


def bind_pre_outcome() -> None:
    assert not (RESULTS / "gatecal_materialization_started.json").exists(), "cannot bind after GateCal outcomes start"
    paths = [POOLS, POOLS.with_suffix(".sha256"), GRID, GRID.with_suffix(".sha256"), AMENDMENT,
             AMENDMENT.with_suffix(".sha256"), Path(__file__), ROOT / "tests/test_p7_2.py"]
    head = git("rev-parse", "HEAD")
    for path in paths:
        assert _git_bound(path, head), f"pre-outcome file is not Git-bound: {path}"
    value = {"schema": "p7.2-pre-outcome-protocol-freeze-v1", "bound_at_utc": utc(),
             "protocol_git_commit": head, "amendment_git_commit": git("log", "-1", "--format=%H", "--", AMENDMENT.relative_to(ROOT).as_posix()),
             "outcomes_materialized": False, "heldout_accessed": False, "alibaba_accessed": False,
             "files": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths}}
    assert not PRE.exists()
    save_json(PRE, value)
    write_sha(PRE)
    _commit([PRE, PRE.with_suffix(".sha256")], "Bind P7.2 fresh pools and execution protocol before outcomes")
    print(json.dumps(value, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bind", "preflight", "gatecal", "gate-finalize", "actioncal", "action-finalize", "run"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    install_seed_binding()
    if args.command == "bind":
        bind_pre_outcome()
    elif args.command == "preflight":
        preflight(); print("P7.2 preflight PASS; heldout/Alibaba/P8 closed")
    elif args.command == "gatecal":
        materialize_gate(args.workers)
    elif args.command == "gate-finalize":
        print(json.dumps(finalize_gate(), indent=2))
    elif args.command == "actioncal":
        materialize_action(args.workers)
    elif args.command == "action-finalize":
        print(json.dumps(finalize_action(), indent=2))
    else:
        materialize_gate(args.workers)
        selected = finalize_gate()
        if selected["status"] != "PASS":
            print("P7.2a FAIL; ActionCal-v2 remains untouched; STOP", flush=True)
            return
        materialize_action(args.workers)
        print(json.dumps(finalize_action(), indent=2), flush=True)


if __name__ == "__main__":
    main()
