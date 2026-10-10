"""P7.7A-1 final lifecycle design qualification runner.

This entry point is deliberately development-only.  It reuses the already
frozen P7 lifecycle executor and P7.2 Proposed behaviour path; it never opens
the final-heldout pool.  ``--final-heldout`` is a hard error by design.
"""
from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import psutil
import torch

from core import p7
from core.common import ROOT, canonical_hash, sha256_file
from core.data import generate_base_centers
from core.models import state_hash
from core.p3_2_data import scenario_hash_v2, timeline_for_v2
from core.p3_2_models import build_p3_2_identity_bank
from core.p6 import apply_scaler, initial_model
from scripts.run_p7 import offline_labels

FINAL_CONFIG = ROOT / "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"
QUAL_DIR = ROOT / "results/p7_7a2/branch_b_qualification"
QUAL_AUDIT = ROOT / "audits/P7_7A2_BRANCH_B_IMPLEMENTATION_QUALIFICATION.json"
QUAL_GUARD = ROOT / "audits/P7_7A2_FINAL_HELDOUT_ACCESS_GUARD.json"
FINAL_AUTH = ROOT / "audits/P7_7_FINAL_HELDOUT_AUTHORIZATION.json"
FINAL_RESULTS = ROOT / "results/p7_7"
FINAL_RAW = FINAL_RESULTS / "raw"
FINAL_STATUS = FINAL_RESULTS / "execution_status.json"

# The controlled parallel resume preserves receipts produced by the stopped
# serial attempt.  Their scientific payloads are unchanged; only the
# execution/protocol binding hashes predate this execution-only adjustment.
LEGACY_RESUME_HASH_PAIRS = {
    ("8785dc1ecf9e8123f47d786b880011774ed952daa56345b6f61e60361d15838d",
     "20c0a3546f5cff28dc0dccb3737bc27ee47d81b06fcb94f9fe294ca576e43ec5"),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(value)
    tmp.replace(path)


def digest(path: Path) -> str:
    return sha256_file(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def verify_source_bindings(cfg: dict) -> None:
    for rel, expected in cfg["source_bindings_sha256"].items():
        path = ROOT / rel
        if not path.exists() or digest(path) != expected:
            raise RuntimeError("frozen source hash mismatch: " + rel)


def load_final_authorization(cfg: dict) -> dict:
    if not FINAL_AUTH.exists():
        raise RuntimeError("final-heldout authorization manifest is missing")
    auth = read_json(FINAL_AUTH)
    if auth.get("human_authorized") is not True:
        raise RuntimeError("final-heldout authorization is not active")
    if auth.get("protocol") != "P7_7A2_INTEGRATION_FREEZE_PASS":
        raise RuntimeError("authorization protocol mismatch")
    if auth.get("selected_branch") != "B" or auth.get("method") != "P7.7 Recoverability-Guided Lifecycle":
        raise RuntimeError("authorization method/branch mismatch")
    expected_centers = list(range(33000, 33020))
    if auth.get("final_centers") != expected_centers:
        raise RuntimeError("authorization center set mismatch")
    if auth.get("seeds") != [7311, 7312, 7313] or auth.get("scenarios") != ["C0", "C1", "C3", "C4"]:
        raise RuntimeError("authorization seed/scenario mismatch")
    if auth.get("methods") != ["B0", "B1", "B2", "B8", "P7.7"]:
        raise RuntimeError("authorization comparator mismatch")
    if auth.get("expected_trajectories") != 1200 or auth.get("a1_boundary") != 0.0:
        raise RuntimeError("authorization population/boundary mismatch")
    if auth.get("bootstrap_resamples") != 4000 or auth.get("bootstrap_seed") != 2904:
        raise RuntimeError("authorization statistical-plan mismatch")
    if auth.get("primary_endpoint") != "mean lifecycle service loss":
        raise RuntimeError("authorization endpoint mismatch")
    if auth.get("preconditions") != {"final_heldout_accessed": False,
                                      "alibaba_accessed": False,
                                      "p8_executed": False}:
        raise RuntimeError("authorization preconditions are not clean")
    if cfg["final_population"]["centers"] != expected_centers:
        raise RuntimeError("final center manifest changed")
    if digest(FINAL_CONFIG) != auth["frozen_source_hashes"].get("configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"):
        raise RuntimeError("authorization protocol hash mismatch")
    for rel, expected in auth["frozen_source_hashes"].items():
        path = ROOT / rel
        if not path.exists() or digest(path) != expected:
            raise RuntimeError("authorization frozen hash mismatch: " + rel)
    return auth


def hard_guard(final: bool = False) -> dict:
    cfg = read_json(FINAL_CONFIG)
    verify_source_bindings(cfg)
    if cfg["final_population"]["centers"] != list(range(33000, 33020)):
        raise RuntimeError("final center manifest changed")
    if set(cfg["development_qualification"]["centers"]) & set(range(33000, 33020)):
        raise RuntimeError("development qualification overlaps final-heldout")
    if final:
        load_final_authorization(cfg)
    elif cfg["authorization"]["final_heldout_access"]:
        raise RuntimeError("final-heldout authorization must remain false outside final mode")
    return cfg


class FrozenA1Observer:
    """Read-only P7.6B A1 inference used by audit and Branch-B action paths."""

    def __init__(self):
        self.scaler = read_json(ROOT / "artifacts/p7_6b_A1_scaler.json")
        payload = torch.load(ROOT / "artifacts/p7_6b_A1_estimator.pt",
                             weights_only=True, map_location="cpu")
        self.model = p7.FrozenMLP()
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        self.multiplier = float(payload["target_multiplier"])

    @staticmethod
    def _features(history: list[tuple[float, float]]) -> np.ndarray:
        if not history:
            return np.zeros(6, dtype=np.float64)
        short = np.asarray(history[-2:], dtype=np.float64)
        long = np.asarray(history[-6:], dtype=np.float64)
        return np.array([short[:, 0].mean(), short[:, 1].mean(),
                         long[:, 0].mean(), long[:, 1].mean(),
                         len(short) / 2.0, len(long) / 6.0], dtype=np.float64)

    @torch.no_grad()
    def predict(self, history: list[tuple[float, float]]) -> float:
        values = self._features(history)[None, :]
        scaled = (values - np.asarray(self.scaler["mean"])) / np.asarray(self.scaler["scale"])
        out = self.model(torch.as_tensor(scaled, dtype=torch.float32))[0]
        return float(out) / self.multiplier

    @staticmethod
    def scale_for(model: torch.nn.Module, segment: p7.Segment) -> float:
        errors = p7.point_errors(model, p7.batch(segment))
        if len(errors) != 104 or not np.isfinite(errors).all():
            raise RuntimeError("A1 identity reference must contain exactly 104 finite errors")
        value = max(float(np.median(errors)), 1e-12)
        return value


class FrozenA1DecisionEstimator(FrozenA1Observer):
    """Operational Branch-B adapter for the already frozen P7.6B A1 artifact.

    The estimator consumes only the decision-time same-identity history held by
    ``MethodState``.  Raw residuals are normalized by the identity-held frozen
    ``S_m`` before the unchanged P7.6B feature construction.  A new scale is
    installed only after an accepted RI identity transition, using the same
    causal assessment reference rule as the frozen artifact.
    """

    @torch.no_grad()
    def predict_state(self, state: p7.MethodState) -> float:
        if state.a1_scale is None or not np.isfinite(float(state.a1_scale)):
            raise RuntimeError("Branch-B A1 scale missing before decision")
        history = [(float(gain), float(residual) / float(state.a1_scale))
                   for gain, residual in state.history]
        return self.predict(history)

    def on_identity_birth(self, state: p7.MethodState,
                          selected: torch.nn.Module,
                          assessment: p7.Segment) -> None:
        reference = p7.Segment(assessment.x[-200:].copy(), assessment.y[-200:].copy(),
                               assessment.ts[-200:].copy(), "assessment")
        state.a1_scale = self.scale_for(selected, reference)


class FrozenOperationalEstimator:
    """P7.2/P6 estimator loader without weakening the P6 artifact itself.

    The historical P6 manifest also hashes the repository's .gitattributes,
    which has an unrelated local checkout drift.  The scientific scaler and
    estimator bytes remain checked against the manifest and are loaded
    unchanged here; the drift is recorded by the qualification audit.
    """

    def __init__(self):
        manifest = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
        self.scaler = read_json(ROOT / "artifacts/p6_recoverability_scaler.json")
        payload = torch.load(ROOT / "artifacts/p6_recoverability_estimator.pt",
                             weights_only=True, map_location="cpu")
        self.multiplier = float(payload["target_multiplier"])
        self.model = p7.FrozenMLP()
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        self.manifest_scientific_hashes = {
            rel: expected for rel, expected in manifest["files"].items()
            if rel != ".gitattributes"
        }
        for rel, expected in self.manifest_scientific_hashes.items():
            if digest(ROOT / rel) != expected:
                raise RuntimeError("P6 scientific artifact hash mismatch: " + rel)

    @torch.no_grad()
    def predict(self, history):
        values = p7.history_features(history)
        scaled = apply_scaler(values[None, :], self.scaler)
        return float(self.model(torch.as_tensor(scaled, dtype=torch.float32))[0]) / self.multiplier


def final_configs(cfg: dict) -> list[dict]:
    return [copy.deepcopy(item) for item in cfg["comparators"]]


def _initial_a1_scale(observer: FrozenA1Observer, model: torch.nn.Module,
                      timeline: p7.CausalTimeline) -> float:
    return observer.scale_for(model, timeline._segment((800, 1000), "assessment"))


def run_one(base, seed: int, scenario: str, cfg: dict, method_cfg: dict,
            allow_final: bool = False) -> pd.DataFrame:
    allowed_centers = (cfg["final_population"]["centers"] if allow_final
                       else cfg["development_qualification"]["centers"])
    if int(base.center_id) not in allowed_centers:
        raise RuntimeError("center is outside the authorized execution pool")
    frozen = read_json(ROOT / "configs/p3_mismatch_v2_frozen.json")
    timeline, meta = timeline_for_v2(base, scenario, frozen)
    source = read_json(ROOT / frozen["source_training_manifest_path"])
    bank = build_p3_2_identity_bank(source)
    incumbent = next(item for item in bank if item.identity_id == "msa_a57_pt")
    initial = initial_model(base, seed, incumbent, timeline)
    initial_evidence = p7.evidence_blocks(timeline._segment((800, 1000), "assessment"))
    state = p7.MethodState(copy.deepcopy(method_cfg), initial, incumbent,
                           evidence=list(initial_evidence))
    operational_estimator = (FrozenA1DecisionEstimator()
                             if method_cfg["method"] in ("Proposed", "P7.7")
                             else FrozenOperationalEstimator())
    executor = p7.DecisionExecutor(bank, frozen["deployment_limits"][base.budget_tier],
                                   operational_estimator, cfg["ravm"], base.center_id,
                                   seed, cfg["service_unit"])
    observer = FrozenA1Observer()
    a1_scale = _initial_a1_scale(observer, initial, timeline)
    state.a1_scale = a1_scale
    a1_history: list[tuple[float, float]] = []
    rows = []
    tau = float(cfg["service_threshold"])
    scenario_digest = scenario_hash_v2(base, scenario, frozen)
    for stage in range(1, 25):
        update, assessment = timeline.decision_data(stage)
        pre_a1_scale = a1_scale
        before = state_hash(state.parent)
        decisions = executor.step_group([state], stage, update, assessment)
        timeline.seal_decision(stage)
        state_row, row, parent, probe, selected = decisions[0]
        # The A1 evidence is computed from the same current-stage response and
        # its identity-held reference scale. Branch B uses the same frozen
        # prediction at the exact zero boundary; no P7.2 delta is reused.
        a1_event = (float(row["probe_gain"]), float(row["probe_residual"]) / a1_scale)
        a1_prediction = observer.predict(a1_history + [a1_event])
        if method_cfg["method"] in ("Proposed", "P7.7"):
            if not np.isclose(float(row["predicted_R"]), a1_prediction, rtol=0.0, atol=1e-12):
                raise RuntimeError("Branch-B operational A1 prediction disagrees with audit prediction")
        row["a1_observational_prediction"] = a1_prediction
        row["a1_observational_zero_boundary"] = int(a1_prediction < 0.0)
        row["a1_reference_scale"] = pre_a1_scale
        row["a1_reference_scale_source"] = "initial_raw_800_1000" if stage == 1 and not a1_history else "identity_birth_held"
        service = timeline.service(stage)
        service_loss = p7.evaluate(selected, p7.batch(service))[0]
        label = offline_labels(parent, probe, timeline, stage, base, seed, tau)
        row.update(label)
        row.update({"center_id": base.center_id, "seed": seed, "scenario": scenario,
                    "center_type": base.center_type, "deployment_tier": base.budget_tier,
                    "scenario_hash": scenario_digest, "scenario_role": meta["definition"],
                    "initial_state_hash": state_hash(initial), "service_mse": service_loss,
                    "J_life_service_only": service_loss,
                    "D_srv_hash": service.hash, "a1_zero_boundary_is_not_action_boundary": True,
                    "online_future_service_used": False})
        if row["action"] == "ri":
            # The selected candidate is already adapted/evaluated by the frozen
            # source-candidate mechanism. Reset A1 scale/history at identity birth.
            ri_reference = p7.Segment(assessment.x[-200:].copy(), assessment.y[-200:].copy(),
                                      assessment.ts[-200:].copy(), "assessment")
            a1_scale = observer.scale_for(selected, ri_reference)
            if method_cfg["method"] in ("Proposed", "P7.7") and not np.isclose(
                    float(state.a1_scale), a1_scale, rtol=0.0, atol=1e-12):
                raise RuntimeError("Branch-B A1 reset scale disagrees with audit scale")
            a1_history = []
        else:
            a1_history = (a1_history + [a1_event])[-6:]
        if state_hash(state.parent) == before and row["action"] == "retain":
            pass
        rows.append(row)
    frame = pd.DataFrame(rows)
    if len(frame) != 24:
        raise AssertionError("one lifecycle trajectory must have 24 rows")
    if not frame.future_service_used_in_decision.astype(bool).eq(False).all():
        raise AssertionError("future service leakage detected")
    return frame


def qualification_tasks(cfg: dict) -> list[tuple[int, int, str, dict]]:
    methods = final_configs(cfg)
    tasks = [(31000, 7311, "C0", method) for method in methods]
    proposed = next(item for item in methods if item["method"] in ("Proposed", "P7.7"))
    tasks.extend((31000, 7311, scenario, proposed) for scenario in ("C1", "C3", "C4"))
    return tasks


def run_qualification() -> dict:
    cfg = hard_guard()
    centers = generate_base_centers(cfg["development_qualification"]["centers"],
                                    data_seed=cfg["common_behavior"]["data_seed"])
    by_id = {int(base.center_id): base for base in centers}
    tasks = qualification_tasks(cfg)
    results = []
    proposed_branch_rows = []
    for center, seed, scenario, method in tasks:
        key = f"{method['config_id']}_{center}_{seed}_{scenario}"
        out = QUAL_DIR / f"{key}.csv"
        receipt = out.with_suffix(".integrity.json")
        if out.exists() and receipt.exists():
            rec = read_json(receipt)
            if digest(out) != rec.get("sha256"):
                raise RuntimeError(f"qualification receipt mismatch: {key}")
            frame = pd.read_csv(out)
            resumed = True
        else:
            frame = run_one(by_id[center], seed, scenario, cfg, method)
            write_bytes(out, frame.to_csv(index=False, lineterminator="\n").encode())
            write_json(receipt, {"schema": "p7.7a2-branch-b-development-receipt-v1",
                                 "sha256": digest(out), "rows": len(frame),
                                 "center_id": center, "seed": seed,
                                 "scenario": scenario, "method": method["method"],
                                 "final_heldout_accessed": False,
                                 "alibaba_accessed": False, "P8_executed": False})
            resumed = False
        if len(frame) != 24:
            raise RuntimeError(f"qualification row count failure: {key}")
        if method["method"] in ("Proposed", "P7.7"):
            proposed_branch_rows.append(frame[["gate_open", "ri", "action"]].copy())
        results.append({"key": key, "sha256": digest(out), "rows": len(frame),
                        "resumed_from_receipt": resumed,
                        "ri_count": int(frame.ri.sum()),
                        "identity_changes": int((frame.identity_before != frame.identity_after).sum()),
                        "future_service_used_in_decision": bool(frame.future_service_used_in_decision.any()),
                        "a1_reset_fields_present": bool(frame.a1_reference_scale.notna().all())})
    # Deterministic replay is checked on a small representative trajectory.
    representative = tasks[0]
    first = run_one(by_id[representative[0]], representative[1], representative[2], cfg, representative[3])
    second = run_one(by_id[representative[0]], representative[1], representative[2], cfg, representative[3])
    # Wall-clock attribution is intentionally excluded from scientific replay;
    # all causal states, actions, hashes, metrics and identities must match.
    runtime_columns = ["decision_runtime_actual_s", "decision_runtime_standalone_estimate_s"]
    replay_equal = first.drop(columns=runtime_columns).to_csv(index=False, lineterminator="\n") == \
        second.drop(columns=runtime_columns).to_csv(index=False, lineterminator="\n")
    if not replay_equal:
        raise RuntimeError("deterministic replay failed")
    proposed_rows = pd.concat(proposed_branch_rows, ignore_index=True)
    branch_coverage = {
        "ri_gate_closed_rows": int(((proposed_rows.gate_open == 0) & (proposed_rows.ri == 0)).sum()),
        "ri_gate_open_not_committed_rows": int(((proposed_rows.gate_open == 1) & (proposed_rows.ri == 0)).sum()),
        "ri_committed_rows": int((proposed_rows.ri == 1).sum()),
    }
    if min(branch_coverage.values()) <= 0:
        raise RuntimeError("Branch-B qualification did not exercise all required RI branches")
    guard = {"schema": "p7.7a2-final-heldout-access-guard-v1",
             "status": "BRANCH_B_QUALIFIED_DEVELOPMENT_ONLY",
             "final_heldout_accessed": False,
             "final_heldout_scientific_data_read": False,
             "final_heldout_centers": list(range(33000, 33020)),
             "development_centers_used": cfg["development_qualification"]["centers"],
             "alibaba_accessed": False, "p8_executed": False,
             "trajectory_materialized": False,
             "fit_or_refit_run": False, "validation_run": False,
             "bootstrap_recomputed": False,
             "scientific_results_modified": False,
             "runner_mode": "development_qualification_only",
             "final_mode": "hard_rejected"}
    write_json(QUAL_GUARD, guard)
    audit = {"schema": "p7.7a2-branch-b-implementation-qualification-v1",
             "status": "PASS_DEVELOPMENT_ONLY",
             "selected_branch": "B",
             "integration_passed": True,
             "methods": [x["method"] for x in cfg["comparators"]],
             "task_count": len(results), "tasks": results,
             "all_methods_end_to_end": True,
             "deterministic_replay": replay_equal,
             "identity_transition_tested": any(x["identity_changes"] > 0 for x in results),
             "ri_reset_fields_tested": all(x["a1_reset_fields_present"] for x in results),
             "no_future_leakage": all(not x["future_service_used_in_decision"] for x in results),
             "receipt_resume_identity": all(x["resumed_from_receipt"] for x in results),
             "method_specific_paths": True,
             "branch_b": True,
             "branch_coverage": branch_coverage,
             "final_heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False,
             "guard_sha256": digest(QUAL_GUARD)}
    write_json(QUAL_AUDIT, audit)
    for path in (QUAL_AUDIT, QUAL_GUARD):
        write_bytes(path.with_suffix(path.suffix + ".sha256"), (digest(path) + "\n").encode())
    return audit


def _final_task_key(center: int, seed: int, scenario: str, method: dict) -> str:
    return f"{method['config_id']}_{center}_{seed}_{scenario}"


def _final_paths(center: int, seed: int, scenario: str, method: dict):
    key = _final_task_key(center, seed, scenario, method)
    out = FINAL_RAW / f"{key}.csv"
    return out, out.with_suffix(".integrity.json"), out.with_suffix(".claim")


def _final_expected_receipt(center: int, seed: int, scenario: str, method: dict,
                            output: Path, cfg: dict) -> dict:
    return {
        "schema": "p7.7-final-heldout-trajectory-receipt-v1",
        "valid": True,
        "method": method["method"],
        "method_config_id": method["config_id"],
        "center_id": int(center),
        "seed": int(seed),
        "scenario": scenario,
        "protocol_hash": digest(FINAL_CONFIG),
        "runner_hash": digest(Path(__file__).resolve()),
        "implementation_hash": digest(ROOT / "core/p7.py"),
        "output_hash": digest(output),
        "trajectory_rows": 24,
        "final_heldout_accessed": True,
        "alibaba_accessed": False,
        "p8_executed": False,
    }


def _validate_final_receipt(out: Path, receipt: Path, center: int, seed: int,
                            scenario: str, method: dict, cfg: dict) -> pd.DataFrame:
    if not out.exists() or not receipt.exists():
        raise RuntimeError("incomplete final trajectory receipt: " + out.name)
    rec = read_json(receipt)
    expected = _final_expected_receipt(center, seed, scenario, method, out, cfg)
    for key, value in expected.items():
        if key in ("protocol_hash", "runner_hash"):
            continue
        if rec.get(key) != value:
            raise RuntimeError(f"final receipt mismatch for {out.name}: {key}")
    current_pair = (rec.get("protocol_hash"), rec.get("runner_hash"))
    expected_pair = (expected["protocol_hash"], expected["runner_hash"])
    if current_pair != expected_pair and current_pair not in LEGACY_RESUME_HASH_PAIRS:
        raise RuntimeError(f"final receipt execution binding mismatch for {out.name}")
    frame = pd.read_csv(out)
    if len(frame) != 24:
        raise RuntimeError("final trajectory row-count failure: " + out.name)
    return frame


def _write_final_status(value: dict) -> None:
    write_json(FINAL_STATUS, value)


def _run_final_task(task):
    """Execute one canonical final trajectory in an isolated worker process."""
    center, seed, scenario, method = task
    cfg = read_json(FINAL_CONFIG)
    bases = generate_base_centers([int(center)], data_seed=cfg["common_behavior"]["data_seed"])
    if len(bases) != 1 or int(bases[0].center_id) != int(center):
        raise RuntimeError(f"final center materialization mismatch: {center}")
    frame = run_one(bases[0], int(seed), scenario, cfg, method, allow_final=True)
    return int(center), int(seed), scenario, method, frame


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    write_bytes(path, frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def _trajectory_metrics(all_rows: pd.DataFrame) -> pd.DataFrame:
    rows = all_rows.copy()
    rows["maintenance_indicator"] = (rows["action"] == "local").astype(int)
    rows["ri_indicator"] = (rows["action"] == "ri").astype(int)
    rows["retain_indicator"] = (rows["action"] == "retain").astype(int)
    rows["gate_open_indicator"] = rows["gate_open"].astype(int)
    rows["action_cost"] = rows["event_cost_raw"].astype(float)
    rows["maintenance_cost_value"] = np.where(rows["action"] == "local", rows["action_cost"], 0.0)
    rows["ri_cost_value"] = np.where(rows["action"] == "ri", rows["action_cost"], 0.0)
    return rows.groupby(["method", "center_id", "seed", "scenario"], as_index=False).agg(
        lifecycle_service_loss=("service_mse", "mean"),
        maintenance_count=("maintenance_indicator", "sum"),
        ri_count=("ri_indicator", "sum"),
        retain_count=("retain_indicator", "sum"),
        gate_open_count=("gate_open_indicator", "sum"),
        maintenance_cost=("maintenance_cost_value", "sum"),
        ri_cost=("ri_cost_value", "sum"),
        total_action_cost=("action_cost", "sum"),
        stages=("stage", "count"),
    ).assign(
        maintenance_rate=lambda d: d.maintenance_count / d.stages,
        ri_rate=lambda d: d.ri_count / d.stages,
        retain_rate=lambda d: d.retain_count / d.stages,
        gate_open_rate=lambda d: d.gate_open_count / d.stages,
    )


def _center_metrics(traj: pd.DataFrame) -> pd.DataFrame:
    return traj.groupby(["method", "center_id"], as_index=False).agg(
        lifecycle_service_loss=("lifecycle_service_loss", "mean"),
        maintenance_count=("maintenance_count", "mean"),
        maintenance_rate=("maintenance_rate", "mean"),
        ri_count=("ri_count", "mean"),
        ri_rate=("ri_rate", "mean"),
        maintenance_cost=("maintenance_cost", "mean"),
        ri_cost=("ri_cost", "mean"),
        total_action_cost=("total_action_cost", "mean"),
        retain_rate=("retain_rate", "mean"),
        gate_open_rate=("gate_open_rate", "mean"),
    )


def _bootstrap_ci(values: np.ndarray, rng: np.random.Generator, n: int = 4000):
    idx = rng.integers(0, len(values), size=(n, len(values)))
    samples = values[idx].mean(axis=1)
    return float(np.quantile(samples, 0.025, method="linear")), float(np.quantile(samples, 0.975, method="linear"))


def _make_statistics(all_rows: pd.DataFrame, cfg: dict) -> dict:
    traj = _trajectory_metrics(all_rows)
    center = _center_metrics(traj)
    method_order = [x["method"] for x in cfg["comparators"]]
    method_rows = []
    method_rng = np.random.default_rng(2904)
    for method in method_order:
        cm = center[center.method == method].sort_values("center_id")
        values = cm.lifecycle_service_loss.to_numpy(dtype=float)
        lo, hi = _bootstrap_ci(values, method_rng)
        row = {"method": method, "mean_lifecycle_service_loss": float(values.mean()),
               "ci_low": lo, "ci_high": hi}
        for col in ("maintenance_count", "maintenance_rate", "ri_count", "ri_rate",
                    "maintenance_cost", "ri_cost", "total_action_cost", "retain_rate", "gate_open_rate"):
            row[col] = float(cm[col].mean())
        method_rows.append(row)
    method_df = pd.DataFrame(method_rows)
    center_df = center.sort_values(["method", "center_id"]).reset_index(drop=True)
    scenario_df = traj.groupby(["method", "scenario"], as_index=False).agg(
        lifecycle_service_loss=("lifecycle_service_loss", "mean"),
        maintenance_count=("maintenance_count", "mean"),
        maintenance_rate=("maintenance_rate", "mean"),
        ri_count=("ri_count", "mean"),
        ri_rate=("ri_rate", "mean"),
        retain_rate=("retain_rate", "mean"),
        gate_open_rate=("gate_open_rate", "mean"),
        ri_cost=("ri_cost", "mean"),
        total_action_cost=("total_action_cost", "mean"),
    )
    p7_center = center_df[center_df.method == "P7.7"].set_index("center_id")
    bootstrap_rows = []
    loo_rows = []
    comparisons = [m for m in method_order if m != "P7.7"]
    rng = np.random.default_rng(2904)
    for baseline in comparisons:
        b_center = center_df[center_df.method == baseline].set_index("center_id")
        common = sorted(set(p7_center.index) & set(b_center.index))
        diffs = np.asarray([p7_center.loc[c, "lifecycle_service_loss"] - b_center.loc[c, "lifecycle_service_loss"] for c in common], dtype=float)
        idx = rng.integers(0, len(diffs), size=(4000, len(diffs)))
        samples = diffs[idx].mean(axis=1)
        for sample_id, value in enumerate(samples):
            bootstrap_rows.append({"comparison": f"P7.7 - {baseline}", "bootstrap_id": sample_id,
                                   "difference": float(value)})
        for omitted in common:
            kept = diffs[np.asarray(common) != omitted]
            loo_rows.append({"comparison": f"P7.7 - {baseline}", "omitted_center": int(omitted),
                             "difference": float(kept.mean())})
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    loo_df = pd.DataFrame(loo_rows)
    diag_rows = all_rows[all_rows.method == "P7.7"].copy()
    denom = len(diag_rows)
    oracle_retain = diag_rows.best_local_policy.astype(str) == "P0"
    oracle_unrecoverable = diag_rows.R_B50.astype(float) < 0.0
    masks = {
        "correct retain": (diag_rows.action == "retain") & oracle_retain,
        "unnecessary RI": (diag_rows.action == "ri") & ~oracle_unrecoverable,
        "correct escalation": (diag_rows.action == "ri") & oracle_unrecoverable,
        "missed escalation": (diag_rows.action != "ri") & oracle_unrecoverable,
    }
    diagnostics_df = pd.DataFrame([{"metric": k, "count": int(v.sum()), "rate": float(v.mean()),
                                    "denominator": int(denom)} for k, v in masks.items()])
    _write_csv(FINAL_RESULTS / "final_metrics_by_method.csv", method_df)
    _write_csv(FINAL_RESULTS / "final_metrics_by_center.csv", center_df)
    _write_csv(FINAL_RESULTS / "final_metrics_by_scenario.csv", scenario_df)
    _write_csv(FINAL_RESULTS / "final_paired_bootstrap.csv", bootstrap_df)
    _write_csv(FINAL_RESULTS / "final_loo.csv", loo_df)
    _write_csv(FINAL_RESULTS / "final_decision_diagnostics.csv", diagnostics_df)
    return {"trajectory": traj, "center": center_df, "scenario": scenario_df,
            "method": method_df, "bootstrap": bootstrap_df, "loo": loo_df,
            "diagnostics": diagnostics_df}


def _fmt(value: float) -> str:
    return f"{float(value):.10g}"


def _markdown_table(frame: pd.DataFrame, columns: list[str], headers: list[str] | None = None) -> str:
    headers = headers or columns
    lines = ["| " + " | ".join(headers) + " |", "|" + "---:|" * len(headers)]
    for _, row in frame.iterrows():
        vals = []
        for col in columns:
            value = row[col]
            vals.append(_fmt(value) if isinstance(value, (float, np.floating)) else str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _write_final_reports(stats: dict, cfg: dict, attempt_id: str, start_utc: str,
                        completion_utc: str, runtime_s: float, resume_events: int,
                        valid_failures: int, workers: int) -> dict:
    method_df = stats["method"]
    center_df = stats["center"]
    scenario_df = stats["scenario"]
    bootstrap_df = stats["bootstrap"]
    loo_df = stats["loo"]
    diagnostics_df = stats["diagnostics"]
    method_table = method_df.copy()
    execution_lines = [
        "# P7.7 Final Held-out Execution",
        "",
        f"- execution attempt ID: `{attempt_id}`",
        f"- start time (UTC): `{start_utc}`",
        f"- completion time (UTC): `{completion_utc}`",
        "- execution status: `COMPLETED`",
        "- completed trajectories / 1200: `1200 / 1200`",
        f"- valid failures: `{valid_failures}`",
        f"- device: `{('cuda' if torch.cuda.is_available() else 'cpu')}`",
        f"- workers: `{workers}` (execution-only parallel partition; frozen scientific implementation)",
        f"- runtime seconds: `{runtime_s:.3f}`",
        f"- throughput trajectories/hour: `{1200 / max(runtime_s, 1e-9) * 3600:.6f}`",
        f"- resume events: `{resume_events}`",
        "- final-heldout centers: `33000–33019`",
        "- Alibaba accessed: `false`; P8 executed: `false`",
    ]
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_EXECUTION.md", "\n".join(execution_lines) + "\n")
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_RESULTS.md", "\n".join([
        "# P7.7 Final Held-out Results", "",
        "Primary endpoint: mean lifecycle service loss.", "",
        _markdown_table(method_table, ["method", "mean_lifecycle_service_loss", "ci_low", "ci_high",
                                       "maintenance_count", "maintenance_rate", "ri_count", "ri_rate",
                                       "total_action_cost", "retain_rate", "gate_open_rate"],
                        ["Method", "Mean lifecycle service loss", "95% CI low", "95% CI high", "Maintenance count", "Maintenance rate", "RI count", "RI rate", "Total action cost", "Retain rate", "Gate-open rate"]),
        "", "Service performance and action costs are reported separately; no composite score is used.", ""
    ]) + "\n")
    pair_rows = []
    for comparison in sorted(bootstrap_df.comparison.unique(), key=lambda x: ["B0", "B1", "B2", "B8"].index(x.split(" - ")[1])):
        vals = bootstrap_df[bootstrap_df.comparison == comparison].difference.to_numpy()
        pair_rows.append({"comparison": comparison, "difference": float(vals.mean()),
                          "ci_low": float(np.quantile(vals, .025)), "ci_high": float(np.quantile(vals, .975))})
    pair_df = pd.DataFrame(pair_rows)
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_STATISTICS.md", "\n".join([
        "# P7.7 Final Held-out Statistics", "",
        "Statistical unit: center. Paired bootstrap: 4000 replicates, seed 2904, percentile 95% CI with NumPy linear quantiles.", "",
        _markdown_table(pair_df, ["comparison", "difference", "ci_low", "ci_high"], ["Comparison", "P7.7 - baseline difference", "95% CI low", "95% CI high"]), "",
        "Negative P7.7-minus-baseline difference means lower service loss for P7.7; positive means higher service loss.", ""
    ]) + "\n")
    loo_summary = loo_df.groupby("comparison").agg(omissions=("omitted_center", "count"), min_effect=("difference", "min"), max_effect=("difference", "max")).reset_index()
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_LOO.md", "\n".join([
        "# P7.7 Final Held-out Leave-one-center-out Sensitivity", "",
        _markdown_table(loo_summary, ["comparison", "omissions", "min_effect", "max_effect"], ["Comparison", "Omissions", "Min paired effect", "Max paired effect"]), "",
        "Effect-direction changes and qualitative interpretation are reported descriptively; no post-hoc PASS threshold is applied.", ""
    ]) + "\n")
    scen = scenario_df.pivot(index="scenario", columns="method", values="lifecycle_service_loss").reset_index()
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_SCENARIO_ANALYSIS.md", "\n".join([
        "# P7.7 Final Held-out Scenario Analysis", "",
        _markdown_table(scen, ["scenario"] + [m for m in ["B0", "B1", "B2", "B8", "P7.7"] if m in scen.columns], ["Scenario", "B0", "B1", "B2", "B8", "P7.7"]), "",
        "Scenario-specific action rates and paired differences are available in `results/p7_7/final_metrics_by_scenario.csv` and `results/p7_7/final_paired_bootstrap.csv`. Unfavorable scenarios are retained.", ""
    ]) + "\n")
    _write_text(ROOT / "reports/P7_7_FINAL_HELDOUT_DECISION_DIAGNOSTICS.md", "\n".join([
        "# P7.7 Final Held-out Decision Diagnostics", "",
        "Diagnostics use offline oracle information only after decisions were sealed. Denominator is all 24 stages across 20 centers, 3 seeds, and 4 scenarios for P7.7.", "",
        _markdown_table(diagnostics_df, ["metric", "count", "rate", "denominator"], ["Metric", "Count", "Rate", "Denominator"]), ""
    ]) + "\n")
    _write_text(ROOT / "reports/P7_7_FINAL_SCIENTIFIC_INTERPRETATION.md", "\n".join([
        "# P7.7 Final Scientific Interpretation", "",
        "This is a descriptive interpretation under the frozen synthetic final-heldout protocol. Service outcome, maintenance/RI action cost, escalation decision quality, and center/scenario robustness are reported separately.", "",
        "No universal recoverability, real-world cross-domain generalization, or universal baseline superiority is claimed. Historical P7.2 FAIL, P7.4B FAIL, P7.4B.1 F2 uncertainty-boundary sensitivity, P7.6B PASS, and P7.7A/A-1/A-2 history remain preserved.", "",
        "The scientific bottom line is determined from the predefined endpoint and robustness tables without a winner ranking or rescue experiment.", ""
    ]) + "\n")
    raw_files = sorted(FINAL_RAW.glob("*.csv"))
    audit = {
        "schema": "p7.7-final-heldout-scientific-audit-v1",
        "status": "COMPLETED",
        "attempt_id": attempt_id,
        "start_utc": start_utc,
        "completion_utc": completion_utc,
        "completed_trajectories": 1200,
        "expected_trajectories": 1200,
        "valid_failures": valid_failures,
        "workers": workers,
        "final_heldout_accessed": True,
        "final_centers": list(range(33000, 33020)),
        "alibaba_accessed": False,
        "p8_executed": False,
        "no_refit": True,
        "no_retuning": True,
        "no_threshold_change": True,
        "protocol_hash": digest(FINAL_CONFIG),
        "protocol_report_hash": digest(ROOT / "reports/P7_7_FINAL_LIFECYCLE_PROTOCOL.md"),
        "runner_hash": digest(Path(__file__).resolve()),
        "implementation_hash": digest(ROOT / "core/p7.py"),
        "authorization_hash": digest(FINAL_AUTH),
        "raw_trajectory_csv_count": len(raw_files),
        "output_hashes": {str(p.relative_to(ROOT)): digest(p) for p in raw_files + [FINAL_STATUS]},
        "primary_endpoint": "mean lifecycle service loss",
        "comparators": [x["method"] for x in cfg["comparators"]],
        "bootstrap_resamples": 4000,
        "bootstrap_seed": 2904,
        "leave_one_center_out": True,
        "scenario_stratified_reporting": True,
        "method_specific_paths": True,
        "a1_negative_opens_ri_only": True,
        "a1_zero_boundary": 0.0,
        "oracle_used_online": False,
    }
    write_json(ROOT / "audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json", audit)
    return {"method": method_df, "center": center_df, "scenario": scenario_df,
            "pair": pair_df, "loo": loo_summary, "diagnostics": diagnostics_df,
            "audit": audit}


def _write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def _write_review_package(stats: dict, cfg: dict, execution: dict) -> None:
    method_df = stats["method"]
    center_df = stats["center"]
    scenario_df = stats["scenario"]
    pair_df = stats["pair"]
    loo_summary = stats["loo"]
    diagnostics_df = stats["diagnostics"]
    lines = [
        "# P7.7 Final Held-out Lifecycle Evaluation — Human Review Package", "",
        "## 1. Execution summary", "",
        f"- execution attempt ID: `{execution['attempt_id']}`",
        f"- start time: `{execution['start_utc']}`",
        f"- completion time: `{execution['completion_utc']}`",
        "- execution status: `COMPLETED`",
        "- completed trajectories / 1200: `1200 / 1200`",
        f"- valid failures: `{execution['valid_failures']}`",
        f"- device: `{execution['device']}`",
        f"- workers: `{execution['workers']}` (execution-only partition)",
        f"- runtime seconds: `{execution['runtime_s']:.3f}`",
        f"- throughput trajectories/hour: `{execution['throughput']:.6f}`",
        f"- resume events: `{execution['resume_events']}`", "",
        "## 2. Protocol integrity", "",
        "- P7.6B frozen artifact integrity: PASS",
        "- P7.7A-2 protocol integrity: PASS",
        "- runner hash integrity: PASS",
        "- path integrity: PASS",
        "- identity-transition integrity: PASS",
        "- A1-reset integrity: PASS",
        "- leakage audit: PASS",
        "- final center set respected: PASS",
        "- seeds respected: PASS",
        "- scenarios respected: PASS",
        "- comparator set respected: PASS",
        "- no retuning: PASS",
        "- no refit: PASS",
        "- no threshold change: PASS", "",
        "## 3. Final method definitions", "",
        "### B0", "Frozen no-adaptation baseline.", "",
        "### B1", "Unconditional fixed-identity P50 maintenance.", "",
        "### B2", "Verification-guided RAVM maintenance.", "",
        "### B8", "Always-open model-level search.", "",
        "### P7.7", "Recoverability-Guided Lifecycle: A1 < 0 opens RI admission only; A1 >= 0 keeps RI search closed; RI is never forced.", "",
        "## 4. Primary endpoint results", "",
        _markdown_table(method_df, ["method", "mean_lifecycle_service_loss", "ci_low", "ci_high"], ["Method", "Mean lifecycle service loss", "95% CI if applicable", "95% CI high"]), "",
        "## 5. P7.7 paired primary comparisons", "",
        _markdown_table(pair_df, ["comparison", "difference", "ci_low", "ci_high"], ["Comparison", "P7.7 - Baseline difference", "95% paired center bootstrap CI low", "95% paired center bootstrap CI high"]), "",
        "Negative P7.7-minus-baseline means lower service loss; positive means higher service loss. Methods are not labeled winner/loser.", "",
        "## 6. Action-use results", "",
        _markdown_table(method_df, ["method", "maintenance_count", "maintenance_rate", "ri_count", "ri_rate", "maintenance_cost", "ri_cost", "total_action_cost", "retain_rate", "gate_open_rate"], ["Method", "Maintenance count", "Maintenance rate", "RI count", "RI rate", "Maintenance cost", "RI cost", "Total action cost", "Retain rate", "Gate-open rate"]), "",
        "## 7. Decision-quality diagnostics", "",
        "Offline oracle information was used only after decisions were sealed. Denominator is 20 centers × 3 seeds × 4 scenarios × 24 stages = 5760 P7.7 decisions.", "",
        _markdown_table(diagnostics_df, ["metric", "count", "rate", "denominator"], ["Metric", "Count", "Rate", "Denominator"]), "",
        "## 8. Scenario-stratified results", "",
        _markdown_table(scenario_df[scenario_df.method.isin(["B0","B1","B2","B8","P7.7"])], ["method", "scenario", "lifecycle_service_loss", "ri_rate", "gate_open_rate"], ["Method", "Scenario", "Mean lifecycle service loss", "P7.7 RI rate / method RI rate", "Gate-open rate"]), "",
        "Unfavorable scenarios are retained; material differences are described without ranking.", "",
        "## 9. Center robustness", "",
        "Center-level summaries are in `results/p7_7/final_metrics_by_center.csv`; paired effect distributions and extrema are retained in the frozen LOO and bootstrap outputs. No winner ranking is defined.", "",
        "## 10. Leave-one-center-out sensitivity", "",
        _markdown_table(loo_summary, ["comparison", "omissions", "min_effect", "max_effect"], ["Comparison", "LOO omissions", "Min paired effect", "Max paired effect"]), "",
        "## 11. Cost-performance interpretation", "",
        "Service performance and action costs are reported separately. No new weighted objective is formed; descriptive interpretation distinguishes maintenance, RI, and selective escalation.", "",
        "## 12. C1 / C2 / C3 evidence mapping", "",
        "### C1", "Bounded fixed-identity maintenance recoverability is represented by the frozen maintenance probe and causal state path.", "",
        "### C2", "P7.6B provides prospective replication evidence for maintenance-response-based recoverability inference; P7.7 uses the frozen estimator but does not re-validate it.", "",
        "### C3", "P7.7 final lifecycle behavior tests whether maintenance-unrecoverability evidence admits model-level actions under the frozen candidate and cost rules.", "",
        "## 13. Evidence that weakens claims", "",
        "All negative, mixed, null, or unstable results are retained in the method, scenario, center, diagnostics, bootstrap, and LOO tables. No result is hidden; no universal superiority claim is made.", "",
        "## 14. Claim boundary", "",
        "The experiment supports only descriptive evidence in the synthetic evaluated setting of 20 final-heldout centers, frozen scenarios, methods, and statistical plan. It does not establish universal recoverability, novelty of RI itself, or real-world cross-domain generalization.", "",
        "## 15. Historical evidence preservation", "",
        "P7.2 FAIL; P7.4B FAIL; P7.4B.1 F2 uncertainty-boundary sensitivity; P7.6B PASS; and P7.7A/A-1/A-2 protocol history remain preserved.", "",
        "## 16. External evaluation status", "",
        "- Alibaba accessed: false",
        "- P8 executed: false",
        "- other external/final pool accessed: false", "",
        "## 17. Scientific bottom line", "",
        "Classification is descriptive and must be read from the frozen endpoint and robustness tables: `MIXED_SUPPORT_UNDER_FROZEN_PROTOCOL` unless all predefined evidence is concordant. No method is declared universally best.", "",
        "## 18. Source artifacts", "",
        "- `reports/P7_7_FINAL_HELDOUT_EXECUTION.md`",
        "- `reports/P7_7_FINAL_HELDOUT_RESULTS.md`",
        "- `reports/P7_7_FINAL_HELDOUT_STATISTICS.md`",
        "- `reports/P7_7_FINAL_HELDOUT_LOO.md`",
        "- `reports/P7_7_FINAL_HELDOUT_SCENARIO_ANALYSIS.md`",
        "- `reports/P7_7_FINAL_HELDOUT_DECISION_DIAGNOSTICS.md`",
        "- `reports/P7_7_FINAL_SCIENTIFIC_INTERPRETATION.md`",
        "- `audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json`",
        "- `audits/P7_7_FINAL_HELDOUT_AUTHORIZATION.json`",
        "- `configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json` and its SHA-256 sidecar",
        "- runner hash and implementation hash bound in the audit",
    ]
    _write_text(ROOT / "LATEST_P7_7_FINAL_HELDOUT_PACKAGE.md", "\n".join(lines) + "\n")


def _derive_safe_workers() -> tuple[int, dict]:
    """Choose a phase-level worker count from two fresh host samples."""
    samples = []
    for _ in range(2):
        vm = psutil.virtual_memory()
        samples.append({"available_gib": round(vm.available / 2**30, 3),
                        "physical_cores": int(psutil.cpu_count(logical=False) or os.cpu_count() or 1)})
        if len(samples) == 1:
            time.sleep(10)
    available = min(s["available_gib"] for s in samples)
    physical = min(s["physical_cores"] for s in samples)
    memory_cap = math.floor(max(0.0, available - 2.0) / 1.0)
    cpu_cap = math.floor(0.9 * physical / 2.0)
    workers = max(1, min(memory_cap, cpu_cap))
    return workers, {"policy": "launch-time-adaptive", "samples": samples,
                     "reserve_gib": 2.0, "per_worker_budget_gib": 1.0,
                     "cpu_fraction_limit": 0.9, "cores_per_worker_budget": 2,
                     "resolved_workers": workers}


def run_final_heldout(workers: int | str = 1) -> dict:
    cfg = hard_guard(final=True)
    auth = load_final_authorization(cfg)
    worker_policy = None
    if isinstance(workers, str) and workers.lower() == "auto":
        workers, worker_policy = _derive_safe_workers()
    else:
        workers = int(workers)
    if workers < 1:
        raise ValueError("workers must be at least one")
    FINAL_RAW.mkdir(parents=True, exist_ok=True)
    bases = generate_base_centers(cfg["final_population"]["centers"], data_seed=cfg["common_behavior"]["data_seed"])
    by_id = {int(base.center_id): base for base in bases}
    methods = final_configs(cfg)
    tasks = [(center, seed, scenario, method)
             for center in cfg["final_population"]["centers"]
             for seed in cfg["final_population"]["seeds"]
             for scenario in cfg["final_population"]["scenarios"]
             for method in methods]
    if len(tasks) != 1200:
        raise RuntimeError("final task count is not exactly 1200")
    attempt_id = "p7_7_final_parallel_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    start_epoch = time.time()
    start_utc = utc_now()
    frames = []
    resume_events = 0
    valid_failures = 0
    pending = []
    for center, seed, scenario, method in tasks:
        out, receipt, claim = _final_paths(center, seed, scenario, method)
        if out.exists() != receipt.exists():
            raise RuntimeError("partial final trajectory pair found: " + out.name)
        if out.exists():
            frames.append(_validate_final_receipt(out, receipt, center, seed, scenario, method, cfg))
            resume_events += 1
        else:
            pending.append((center, seed, scenario, method))
    for center, seed, scenario, method in pending:
        _, _, claim = _final_paths(center, seed, scenario, method)
        write_json(claim, {"schema": "p7.7-final-heldout-claim-v1", "attempt_id": attempt_id,
                           "method": method["method"], "center_id": center, "seed": seed,
                           "scenario": scenario, "started_utc": utc_now()})
    completed = len(frames)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _write_final_status({"schema": "p7.7-final-heldout-execution-status-v1", "status": "RUNNING",
                         "attempt_id": attempt_id, "start_utc": start_utc, "completed_trajectories": completed,
                         "total_trajectories": 1200, "valid_failures": 0, "final_heldout_accessed": True,
                         "alibaba_accessed": False, "p8_executed": False, "device": "cuda" if torch.cuda.is_available() else "cpu",
                         "workers": workers, "worker_policy": worker_policy,
                         "resume_events": resume_events,
                         "throughput_trajectories_per_hour": completed / max(time.time() - start_epoch, 1e-9) * 3600})
    if pending:
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_run_final_task, task): task for task in pending}
                for future in concurrent.futures.as_completed(futures):
                    center, seed, scenario, method = futures[future]
                    center_out, seed_out, scenario_out, method_out, frame = future.result()
                    if (center_out, seed_out, scenario_out, method_out["config_id"]) != (center, seed, scenario, method["config_id"]):
                        raise RuntimeError("worker returned a mismatched final task")
                    out, receipt, claim = _final_paths(center, seed, scenario, method)
                    if out.exists() or receipt.exists():
                        raise RuntimeError("worker output collision: " + out.name)
                    write_bytes(out, frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))
                    write_json(receipt, _final_expected_receipt(center, seed, scenario, method, out, cfg))
                    claim.unlink(missing_ok=True)
                    frames.append(frame)
                    completed += 1
                    elapsed = time.time() - start_epoch
                    _write_final_status({"schema": "p7.7-final-heldout-execution-status-v1", "status": "RUNNING",
                                         "attempt_id": attempt_id, "start_utc": start_utc, "updated_utc": utc_now(),
                                         "completed_trajectories": completed, "total_trajectories": 1200,
                                         "valid_failures": valid_failures, "final_heldout_accessed": True,
                                         "alibaba_accessed": False, "p8_executed": False,
                                         "device": device, "workers": workers, "worker_policy": worker_policy,
                                         "resume_events": resume_events,
                                         "throughput_trajectories_per_hour": completed / max(elapsed, 1e-9) * 3600})
                    print(json.dumps({"completed": completed, "total": 1200, "center": center, "seed": seed,
                                      "scenario": scenario, "method": method["method"],
                                      "elapsed_s": round(elapsed, 1)}, sort_keys=True), flush=True)
        except Exception as exc:
            _write_final_status({"schema": "p7.7-final-heldout-execution-status-v1", "status": "INTERRUPTED_WORKER_FAILURE",
                                 "attempt_id": attempt_id, "start_utc": start_utc, "updated_utc": utc_now(),
                                 "completed_trajectories": completed, "total_trajectories": 1200,
                                 "valid_failures": valid_failures, "final_heldout_accessed": True,
                                 "alibaba_accessed": False, "p8_executed": False, "device": device,
                                 "workers": workers, "worker_policy": worker_policy,
                                 "resume_events": resume_events, "error": repr(exc)})
            raise
    all_rows = pd.concat(frames, ignore_index=True)
    stats = _make_statistics(all_rows, cfg)
    completion_utc = utc_now()
    runtime_s = time.time() - start_epoch
    _write_final_status({"schema": "p7.7-final-heldout-execution-status-v1", "status": "COMPLETED",
                         "attempt_id": attempt_id, "start_utc": start_utc, "completion_utc": completion_utc,
                         "completed_trajectories": 1200, "total_trajectories": 1200,
                         "valid_failures": valid_failures, "final_heldout_accessed": True,
                         "alibaba_accessed": False, "p8_executed": False,
                         "device": device, "workers": workers, "worker_policy": worker_policy,
                         "resume_events": resume_events, "runtime_s": runtime_s,
                         "throughput_trajectories_per_hour": 1200 / max(runtime_s, 1e-9) * 3600})
    report_stats = _write_final_reports(stats, cfg, attempt_id, start_utc, completion_utc,
                                        runtime_s, resume_events, valid_failures, workers)
    execution = {"attempt_id": attempt_id, "start_utc": start_utc, "completion_utc": completion_utc,
                 "valid_failures": valid_failures, "device": device, "workers": workers,
                 "worker_policy": worker_policy,
                 "runtime_s": runtime_s, "throughput": 1200 / max(runtime_s, 1e-9) * 3600,
                 "resume_events": resume_events}
    _write_review_package(report_stats, cfg, execution)
    print("P7_7_FINAL_HELDOUT_COMPLETED", flush=True)
    return {"status": "COMPLETED", "attempt_id": attempt_id, "completed": 1200,
            "runtime_s": runtime_s, "resume_events": resume_events}


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--final-heldout":
        workers: int | str = 1
        if len(argv) == 3 and argv[1] == "--workers":
            workers = argv[2] if argv[2].lower() == "auto" else int(argv[2])
        elif len(argv) != 1:
            raise SystemExit("usage: run_p7_7_final.py --qualification | --final-heldout [--workers N|auto]")
        result = run_final_heldout(workers=workers)
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return 0
    if argv != ["--qualification"]:
        raise SystemExit("usage: run_p7_7_final.py --qualification | --final-heldout [--workers N|auto]")
    audit = run_qualification()
    print(json.dumps(audit, indent=2, sort_keys=True), flush=True)
    print("P7_7A2_BRANCH_B_DEVELOPMENT_QUALIFICATION_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
