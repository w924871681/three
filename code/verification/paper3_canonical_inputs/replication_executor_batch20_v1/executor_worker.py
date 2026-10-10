"""Gated independent batch-20 model worker; never invoke the old final CLI.

The parent freezes this implementation before execution. This worker writes only
the independent replication directory, preserves failed attempts, reads fixed
F1 inputs, and uses the exact frozen trajectory function via science_adapter.
Progress contains task identities/counts only, never model performance values.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
import traceback
import types
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    _package = types.ModuleType("paper3_replication")
    _package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[_package.__name__] = _package
    __package__ = _package.__name__

from . import provenance as provenance


REQUEST_SCHEMA = "paper3-replication-worker-request-v1"
RECEIPT_SCHEMA = "paper3-batch20-replication-trajectory-receipt-v1"
INITIAL_SCHEMA = "paper3-batch20-initial-state-manifest-v1"


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _assert(condition, message):
    if not condition:
        raise provenance.ProvenanceError(message)


def _label(value):
    _assert(isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value), "unsafe worker/attempt label")
    return value


def _stem(task):
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"


def _request(manifest, path, mode, worker_id, attempt_id):
    root = Path(manifest["paths"]["results_root"])
    path = provenance.regular_path(path)
    _assert(root in path.parents, "worker request must stay in independent results")
    value = provenance.read_json(path)
    expected = {"schema": REQUEST_SCHEMA, "manifest_digest": manifest["manifest_digest"],
                "mode": mode, "worker_id": worker_id, "attempt_id": attempt_id}
    _assert(all(value.get(key) == item for key, item in expected.items()), "worker request identity differs from frozen invocation")
    _assert(type(value.get("worker_count")) is int and 1 <= value["worker_count"] <= 3, "worker count exceeds authorized maximum")
    _assert(value.get("performance_based_continuation", False) is False, "outcome-based continuation is prohibited")
    if mode == "initial":
        cases = [{"center_id": center, "seed": seed} for center in range(33000, 33020) for seed in (7311, 7312, 7313)]
        _assert(value.get("cases") == cases, "initial request must contain the complete ordered sixty center/seed cases")
    else:
        _assert(isinstance(value.get("tasks"), list) and value["tasks"], "trajectory request must contain preassigned frozen tasks")
        from .science_adapter import _check_task
        for task in value["tasks"]:
            _check_task(task, manifest["frozen_final_configuration"])
        _assert(len({_stem(task) for task in value["tasks"]}) == len(value["tasks"]), "duplicate tasks in one worker request")
        _assert(value.get("initial_state_manifest", "initial_state_manifest.json") == "initial_state_manifest.json", "initial certificate path differs")
    value["request_file_sha256"] = provenance.file_sha256(path)
    return value


def _prepare(manifest_path, request_path, mode, worker_id, attempt_id):
    manifest_path = provenance.regular_path(manifest_path)
    manifest = provenance.read_json(manifest_path)
    root = Path(manifest["paths"]["results_root"])
    _assert(manifest_path == root / "provenance_manifest.json", "worker must use the frozen canonical replication manifest")
    provenance.require_isolation(root)
    # Write protection precedes imports of trusted scientific native packages.
    provenance.install_write_guard(root)
    provenance.verify_frozen(manifest, verify_environment=True, full=True, check_inputs=False)
    provenance.install_generator_guard(manifest["paths"]["repo"])
    provenance.install_model_import_guard(manifest)
    repo = str(provenance.regular_path(manifest["paths"]["repo"]))
    site = str(provenance.regular_path(manifest["environment"]["site_packages_root"]))
    if repo not in sys.path:
        sys.path.append(repo)  # Original containers are bound by the import guard.
    if site not in sys.path:
        sys.path.append(site)  # No .pth or site startup is processed under -S.
    provenance.require_authorized_execution(manifest["paths"]["repo"], manifest["paths"]["input_run"])
    request = _request(manifest, request_path, mode, _label(worker_id), _label(attempt_id))
    from .fixed_inputs import FixedInputStore
    store = FixedInputStore(Path(manifest["paths"]["repo"]), Path(manifest["paths"]["input_run"]))
    from .science_adapter import runtime_preflight
    runtime = runtime_preflight(Path(manifest["paths"]["repo"]), Path(manifest["paths"]["input_run"]),
                                source_pins=manifest["critical_files_sha256"])
    runtime_receipt = {"schema": "paper3-batch20-scientific-runtime-receipt-v1", **runtime,
                       "manifest_digest": manifest["manifest_digest"], "mode": mode,
                       "worker_id": worker_id, "attempt_id": attempt_id,
                       "request_file_sha256": request["request_file_sha256"], "created_utc": _utc(),
                       "outcome_values_included": False}
    publication = provenance.publish_json(root,
        f"workers/{worker_id}_{attempt_id}_{mode}.runtime.json", runtime_receipt)
    request.update(scientific_runtime_signature=runtime["scientific_runtime_signature"],
                   runtime_receipt_path=publication["relative"], runtime_receipt_sha256=publication["sha256"])
    if mode == "trajectory":
        _initial_references(manifest, runtime_signature=request["scientific_runtime_signature"])
    return manifest, request, store


def _initial(manifest, request, store):
    from .science_adapter import initial_preflight
    root = Path(manifest["paths"]["results_root"])
    repo, input_run = Path(manifest["paths"]["repo"]), Path(manifest["paths"]["input_run"])
    environment = provenance.canonical_hash(manifest["environment"])
    states = []
    for index, case in enumerate(request["cases"], 1):
        center, seed = case["center_id"], case["seed"]
        relative = f"initial_states/{center}_{seed}.json"
        integrity_relative = f"initial_states/{center}_{seed}.integrity.json"
        path = provenance.checked_path(root, relative, must_exist=False)
        integrity_path = provenance.checked_path(root, integrity_relative, must_exist=False)
        provenance.verify_frozen(manifest, verify_environment=False, full=False)
        print(f"INITIAL_STARTED {center}/{seed} {index}/60", flush=True)
        if path.exists() or integrity_path.exists():
            _assert(path.is_file() and integrity_path.is_file(), "partial initial publication cannot be overwritten")
            saved, integrity = provenance.read_json(path), provenance.read_json(integrity_path)
            _assert(integrity.get("valid") is True and integrity.get("output_hash") == provenance.file_sha256(path), "saved initial byte receipt invalid")
            _assert(saved.get("manifest_digest") == manifest["manifest_digest"] and saved.get("task") == case
                    and saved.get("environment_binding") == environment, "saved initial provenance differs")
            audit = saved["audit"]
            _assert(audit.get("source_bindings_sha256") == manifest["critical_files_sha256"] and audit.get("input_bundle_digest") == manifest["input_bundle_digest"], "saved initial source/input binding differs")
            _assert(integrity.get("task") == case and integrity.get("manifest_digest") == manifest["manifest_digest"]
                    and integrity.get("input_bundle_digest") == manifest["input_bundle_digest"]
                    and integrity.get("environment_binding") == environment
                    and integrity.get("initial_state_hash") == audit["initial_state_hash"], "saved initial scientific receipt differs")
            print(f"INITIAL_SKIPPED_VALID {center}/{seed} {index}/60", flush=True)
        else:
            try:
                audit = initial_preflight(repo, input_run, center, seed, manifest["frozen_final_configuration"],
                                          source_pins=manifest["critical_files_sha256"], input_store=store)
            except BaseException as error:
                provenance.publish_json(root,
                    f"attempts/initial_{center}_{seed}/{request['attempt_id']}/{request['worker_id']}/failure.json",
                    {"schema": "paper3-batch20-failed-initial-preflight-v1", "task": case,
                     "status": "INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "FAILED",
                     "completed_valid": False, "manifest_digest": manifest["manifest_digest"],
                     "input_bundle_digest": manifest["input_bundle_digest"], "environment_binding": environment,
                     "error_type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc(),
                     "service_evaluated": False, "lifecycle_executed": False, "created_utc": _utc(),
                     "automatic_retry": False})
                raise
            saved = {"schema": "paper3-batch20-initial-state-publication-v1", "task": case,
                     "manifest_digest": manifest["manifest_digest"], "input_bundle_digest": manifest["input_bundle_digest"],
                     "environment_binding": environment, "audit": audit, "created_utc": _utc(),
                     "service_evaluated": False, "lifecycle_executed": False}
            output = provenance.publish_json(root, relative, saved)
            provenance.publish_json(root, integrity_relative, {"schema": "paper3-batch20-initial-state-receipt-v1",
                "valid": True, "task": case, "manifest_digest": manifest["manifest_digest"],
                "output_hash": output["sha256"], "initial_state_hash": audit["initial_state_hash"],
                "input_bundle_digest": manifest["input_bundle_digest"], "environment_binding": environment})
            print(f"INITIAL_COMPLETED {center}/{seed} {index}/60", flush=True)
        _assert(audit.get("original_initial_model_called") is True and audit.get("warmup_steps") == 50
                and audit.get("warmup_seed") == seed + center and audit.get("lifecycle_executed") is False
                and audit.get("service_evaluated") is False and audit.get("estimator_loaded") is False,
                "initial-only scientific boundaries changed")
        _assert(audit["bank"]["bank_hash"] == store.bank["bank_hash"], "initial bank differs")
        _assert(audit.get("scientific_runtime_signature") == request["scientific_runtime_signature"], "initial runtime flags or device changed")
        states.append({**case, "path": relative, "sha256": provenance.file_sha256(path),
                       "receipt_path": integrity_relative, "receipt_sha256": provenance.file_sha256(integrity_path),
                       "initial_state_hash": audit["initial_state_hash"]})
        provenance.verify_frozen(manifest, verify_environment=False, full=False)
    provenance.verify_frozen(manifest, verify_environment=True, full=True, check_inputs=False)
    provenance.check_loaded_modules(manifest)
    publication = {"schema": INITIAL_SCHEMA, "manifest_digest": manifest["manifest_digest"],
                   "input_bundle_digest": manifest["input_bundle_digest"], "environment_binding": environment,
                   "states": states, "expected_cases": 60, "completed_cases": 60,
                   "canonical_warmup_reference_created": True, "five_method_actual_initial_state_parity": "PENDING_TRAJECTORIES",
                   "warmup_steps": 50, "warmup_seed_rule": "seed+center_id", "initial_scenario": "C0",
                   "other_scenario_prefix_input_parity_source": "PUBLISHED_STAGE_B_F1_REFERENCE_PARITY",
                   "source_checkpoints_frozen": True, "service_evaluated": False, "statistics_executed": False,
                   "created_utc": _utc(), "request_file_sha256": request["request_file_sha256"]}
    publication.update(scientific_runtime_signature=request["scientific_runtime_signature"],
                       runtime_receipt_path=request["runtime_receipt_path"],
                       runtime_receipt_sha256=request["runtime_receipt_sha256"])
    path = provenance.checked_path(root, "initial_state_manifest.json", must_exist=False)
    if path.exists():
        existing = provenance.read_json(path)
        _assert(existing.get("states") == states and existing.get("manifest_digest") == manifest["manifest_digest"], "completed initial manifest differs")
    else:
        provenance.publish_json(root, "initial_state_manifest.json", publication)
    print("INITIAL_PHASE_COMPLETED 60/60", flush=True)
    return {"initial_cases": 60, "trajectories_executed": 0}


def _initial_references(manifest, *, runtime_signature=None):
    root = Path(manifest["paths"]["results_root"])
    path = provenance.checked_path(root, "initial_state_manifest.json")
    value = provenance.read_json(path)
    _assert(value.get("schema") == INITIAL_SCHEMA and value.get("manifest_digest") == manifest["manifest_digest"]
            and value.get("input_bundle_digest") == manifest["input_bundle_digest"]
            and value.get("environment_binding") == provenance.canonical_hash(manifest["environment"])
            and value.get("canonical_warmup_reference_created") is True and value.get("completed_cases") == 60,
            "complete canonical sixty-case initial certificate missing")
    if runtime_signature is not None:
        _assert(value.get("scientific_runtime_signature") == runtime_signature, "trajectory runtime differs from initial-state certification")
    runtime_path = provenance.checked_path(root, value["runtime_receipt_path"])
    _assert(provenance.file_sha256(runtime_path) == value["runtime_receipt_sha256"], "initial runtime receipt bytes changed")
    runtime = provenance.read_json(runtime_path)
    _assert(runtime.get("manifest_digest") == manifest["manifest_digest"]
            and runtime.get("scientific_runtime_signature") == value["scientific_runtime_signature"]
            and provenance.canonical_hash(runtime["scientific_runtime"]) == value["scientific_runtime_signature"], "initial runtime scientific signature changed")
    expected = {(center, seed) for center in range(33000, 33020) for seed in (7311, 7312, 7313)}
    observed = {(item["center_id"], item["seed"]) for item in value["states"]}
    _assert(len(value["states"]) == 60 and observed == expected, "initial certificate coverage differs")
    hashes = {}
    for item in value["states"]:
        audit_path = provenance.checked_path(root, item["path"])
        receipt_path = provenance.checked_path(root, item["receipt_path"])
        _assert(provenance.file_sha256(audit_path) == item["sha256"] and provenance.file_sha256(receipt_path) == item["receipt_sha256"], "initial certificate byte binding changed")
        saved = provenance.read_json(audit_path)
        audit = saved["audit"]
        receipt = provenance.read_json(receipt_path)
        case = {"center_id": item["center_id"], "seed": item["seed"]}
        _assert(receipt.get("valid") is True and receipt.get("output_hash") == item["sha256"]
                and receipt.get("task") == case and receipt.get("manifest_digest") == manifest["manifest_digest"]
                and receipt.get("initial_state_hash") == item["initial_state_hash"]
                and receipt.get("input_bundle_digest") == manifest["input_bundle_digest"]
                and receipt.get("environment_binding") == value["environment_binding"]
                and saved.get("task") == case and saved.get("manifest_digest") == manifest["manifest_digest"]
                and saved.get("environment_binding") == value["environment_binding"]
                and audit.get("source_bindings_sha256") == manifest["critical_files_sha256"]
                and audit.get("input_bundle_digest") == manifest["input_bundle_digest"]
                and audit.get("original_initial_model_called") is True and audit.get("warmup_steps") == 50
                and audit.get("warmup_seed") == item["seed"] + item["center_id"]
                and audit.get("lifecycle_executed") is False and audit.get("service_evaluated") is False
                and audit.get("estimator_loaded") is False
                and audit.get("scientific_runtime_signature") == value["scientific_runtime_signature"]
                and audit["initial_state_hash"] == item["initial_state_hash"], "initial certificate source/input/parameter binding differs")
        hashes[(item["center_id"], item["seed"])] = item["initial_state_hash"]
    return hashes, provenance.file_sha256(path)


def _expected_stage_hashes(store, task):
    result = []
    for stage in range(1, 25):
        row = {"stage": stage}
        for role, field in (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash")):
            row[field] = store.bundle["roles"][f"{task['center_id']}/{task['scenario']}/{stage}/{role}"]["legacy_role_hash"]
        result.append(row)
    return result


def _existing_completed(manifest, store, task, initial_hash, initial_manifest_sha, *, runtime_signature=None):
    root = Path(manifest["paths"]["results_root"])
    stem = _stem(task)
    csv_path = provenance.checked_path(root, f"raw/{stem}.csv", must_exist=False)
    receipt_path = provenance.checked_path(root, f"raw/{stem}.integrity.json", must_exist=False)
    if not csv_path.exists() and not receipt_path.exists():
        return None
    _assert(csv_path.is_file() and receipt_path.is_file(), "partial final trajectory publication cannot be overwritten")
    receipt = provenance.read_json(receipt_path)
    expected = {"schema": RECEIPT_SCHEMA, "valid": True, "task": task, "manifest_digest": manifest["manifest_digest"],
                "input_bundle_digest": manifest["input_bundle_digest"], "initial_state_hash": initial_hash,
                "initial_state_manifest_sha256": initial_manifest_sha,
                "environment_binding": provenance.canonical_hash(manifest["environment"]), "trajectory_rows": 24,
                "runner_hash": manifest["critical_files_sha256"]["scripts/run_p7_7_final.py"],
                "implementation_hash": manifest["critical_files_sha256"]["core/p7.py"],
                "protocol_hash": manifest["critical_files_sha256"]["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
                "source_bindings_digest": provenance.canonical_hash(manifest["critical_files_sha256"]),
                "stage_input_hashes": _expected_stage_hashes(store, task)}
    _assert(all(receipt.get(key) == value for key, value in expected.items()), "completed new trajectory scientific receipt differs")
    if runtime_signature is not None:
        _assert(receipt.get("scientific_runtime_signature") == runtime_signature, "completed trajectory runtime differs from current/initial runtime")
        runtime_path = provenance.checked_path(root, receipt["runtime_receipt_path"])
        _assert(provenance.file_sha256(runtime_path) == receipt["runtime_receipt_sha256"], "completed runtime receipt bytes changed")
        runtime = provenance.read_json(runtime_path)
        _assert(runtime.get("scientific_runtime_signature") == runtime_signature
                and provenance.canonical_hash(runtime["scientific_runtime"]) == runtime_signature, "completed runtime signature changed")
    _assert(provenance.file_sha256(csv_path) == receipt.get("output_hash"), "completed new trajectory bytes changed")
    audit_path = provenance.checked_path(root, receipt["audit_relative"])
    _assert(provenance.file_sha256(audit_path) == receipt["audit_hash"], "completed trajectory audit bytes changed")
    audit = provenance.read_json(audit_path)
    _assert(audit.get("task") == task and audit.get("original_run_one_code_object_preserved") is True
            and audit.get("original_globals_mutated") is False and audit.get("source_bindings_sha256") == manifest["critical_files_sha256"]
            and audit.get("initial_state", {}).get("initial_state_hash") == initial_hash
            and audit.get("initial_state", {}).get("before_first_decision_verified") is True,
            "completed trajectory exact-code/initial audit invalid")
    _assert(audit.get("timeline_access", {}).get("violation_count") == 0
            and audit.get("timeline_access", {}).get("completed_stages") == 24
            and audit.get("timeline_access", {}).get("phase") == "SERVICED", "completed trajectory causal audit invalid")
    _assert(receipt.get("audit_path") == receipt["audit_relative"] and receipt.get("audit_sha256") == receipt["audit_hash"]
            and receipt.get("rng_before_path") == receipt["rng_relative"]
            and receipt.get("rng_before_sha256") == receipt["rng_file_sha256"], "completed receipt reference aliases differ")
    rng_path = provenance.checked_path(root, receipt["rng_relative"])
    _assert(provenance.file_sha256(rng_path) == receipt["rng_file_sha256"], "completed trajectory RNG bytes changed")
    attempt_csv_path = provenance.checked_path(root, receipt["attempt_csv_relative"])
    _assert(provenance.file_sha256(attempt_csv_path) == receipt["attempt_csv_hash"] == receipt["output_hash"], "attempt/final CSV byte binding differs")
    return receipt


def _retry(root, task, request):
    descriptor = request.get("retries", {}).get(_stem(task))
    if descriptor is None:
        return None
    path = provenance.checked_path(root, descriptor["failed_receipt_relative"])
    expected = descriptor["failed_receipt_sha256"]
    _assert(provenance.file_sha256(path) == expected, "retry failed receipt byte binding differs")
    receipt = provenance.read_json(path)
    _assert(receipt.get("task") == task and receipt.get("status") in {"FAILED", "INTERRUPTED"}
            and receipt.get("completed_valid") is False, "retry requires the exact incomplete same-task receipt")
    rng_path = provenance.checked_path(root, receipt["rng_relative"])
    _assert(provenance.file_sha256(rng_path) == receipt["rng_file_sha256"], "retry RNG artifact bytes changed")
    return {"failed_attempt_status": receipt["status"], "completed_valid": False,
            "failed_attempt_receipt_sha256": expected, "rng_state": provenance.read_json(rng_path)}


def _trajectories(manifest, request, store):
    from .science_adapter import run_task
    root = Path(manifest["paths"]["results_root"])
    repo, input_run = Path(manifest["paths"]["repo"]), Path(manifest["paths"]["input_run"])
    environment = provenance.canonical_hash(manifest["environment"])
    initial_hashes, initial_manifest_sha = _initial_references(manifest, runtime_signature=request["scientific_runtime_signature"])
    completed, skipped = 0, 0
    for index, task in enumerate(request["tasks"], 1):
        stem = _stem(task)
        prefix = f"attempts/{stem}/{request['attempt_id']}/{request['worker_id']}"
        expected_initial = initial_hashes[(task["center_id"], task["seed"])]
        provenance.verify_frozen(manifest, verify_environment=False, full=False)
        if _existing_completed(manifest, store, task, expected_initial, initial_manifest_sha,
                               runtime_signature=request["scientific_runtime_signature"]) is not None:
            skipped += 1
            print(f"TASK_SKIPPED_VALID {stem} {index}/{len(request['tasks'])}", flush=True)
            continue
        print(f"TASK_STARTED {stem} {index}/{len(request['tasks'])}", flush=True)
        rng_publication = {}
        def save_rng(value):
            rng_publication.update(provenance.publish_json(root, prefix + "/rng_before.json", value))
        try:
            retry = _retry(root, task, request)
            frame, audit = run_task(repo, input_run, task, manifest["frozen_final_configuration"],
                                   expected_initial_state_hash=expected_initial, environment_binding=environment,
                                   source_pins=manifest["critical_files_sha256"], retry_rng_state=retry,
                                   rng_capture_sink=save_rng, input_store=store)
            # Integrity only: no mean, ranking, significance or result selection.
            _assert(len(frame) == 24 and all(math.isfinite(float(value)) for value in frame["service_mse"]), "nonfinite primary service value")
            _assert(audit.get("scientific_runtime_signature") == request["scientific_runtime_signature"], "trajectory runtime flags or device changed")
            data = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
            attempt_csv = provenance.publish_bytes(root, prefix + "/trajectory.csv", data)
            attempt_audit = provenance.publish_json(root, prefix + "/audit.json", audit)
            provenance.verify_frozen(manifest, verify_environment=False, full=False)
            provenance.check_loaded_modules(manifest)
            csv = provenance.publish_bytes(root, f"raw/{stem}.csv", data)
            receipt = {"schema": RECEIPT_SCHEMA, "valid": True, "task": task,
                       "manifest_digest": manifest["manifest_digest"], "input_bundle_digest": manifest["input_bundle_digest"],
                       "environment_binding": environment, "initial_state_hash": expected_initial,
                       "initial_state_manifest_sha256": initial_manifest_sha, "trajectory_rows": 24,
                       "scientific_runtime_signature": request["scientific_runtime_signature"],
                       "runtime_receipt_path": request["runtime_receipt_path"],
                       "runtime_receipt_sha256": request["runtime_receipt_sha256"],
                       "output_hash": csv["sha256"], "runner_hash": manifest["critical_files_sha256"]["scripts/run_p7_7_final.py"],
                       "implementation_hash": manifest["critical_files_sha256"]["core/p7.py"],
                       "protocol_hash": manifest["critical_files_sha256"]["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
                       "source_bindings_digest": provenance.canonical_hash(manifest["critical_files_sha256"]),
                       "executor_bundle_digest": provenance.canonical_hash(manifest["executor_sha256"]),
                       "audit_relative": attempt_audit["relative"], "audit_hash": attempt_audit["sha256"],
                       "audit_path": attempt_audit["relative"], "audit_sha256": attempt_audit["sha256"],
                       "rng_relative": rng_publication["relative"], "rng_file_sha256": rng_publication["sha256"],
                       "rng_before_path": rng_publication["relative"], "rng_before_sha256": rng_publication["sha256"],
                       "attempt_csv_relative": attempt_csv["relative"], "attempt_csv_hash": attempt_csv["sha256"],
                       "stage_input_hashes": _expected_stage_hashes(store, task),
                       "deployment_tier": audit["initial_state"]["deployment_tier"],
                       "deployment_filter_hash": audit["initial_state"]["bank"]["deployment_filter_hash"],
                       "bank_hash": audit["initial_state"]["bank"]["bank_hash"],
                       "full_24_stage_input_parity_checked": True, "future_online_access_violation_count": 0,
                       "primary_service_values_finite": True, "performance_based_continuation": False,
                       "statistics_executed": False, "worker_id": request["worker_id"], "attempt_id": request["attempt_id"],
                       "created_utc": _utc()}
            provenance.publish_json(root, prefix + "/receipt.json", receipt)
            provenance.publish_json(root, f"raw/{stem}.integrity.json", receipt)
            completed += 1
            print(f"TASK_COMPLETED {stem} {index}/{len(request['tasks'])}", flush=True)
        except BaseException as error:
            status = "INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "FAILED"
            failure = {"schema": "paper3-batch20-failed-task-receipt-v1", "status": status, "completed_valid": False,
                       "task": task, "manifest_digest": manifest["manifest_digest"],
                       "input_bundle_digest": manifest["input_bundle_digest"], "environment_binding": environment,
                       "initial_state_hash": expected_initial, "worker_id": request["worker_id"], "attempt_id": request["attempt_id"],
                       "error_type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc(),
                       "rng_relative": rng_publication.get("relative"), "rng_file_sha256": rng_publication.get("sha256"),
                       "created_utc": _utc(), "automatic_new_draw_retry": False, "originals_overwritten": False}
            provenance.publish_json(root, prefix + "/failure.json", failure)
            print(f"TASK_FAILED {stem} {status}", flush=True)
            raise
    provenance.verify_frozen(manifest, verify_environment=True, full=True, check_inputs=False)
    provenance.check_loaded_modules(manifest)
    return {"assigned_tasks": len(request["tasks"]), "completed_tasks": completed, "skipped_valid_tasks": skipped,
            "statistics_executed": False, "performance_based_continuation": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("initial", "trajectory"), required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--attempt-id", default="A0001")
    args = parser.parse_args()
    manifest = request = None
    try:
        manifest, request, store = _prepare(args.manifest, args.request_file, args.mode, args.worker_id, args.attempt_id)
        summary = _initial(manifest, request, store) if args.mode == "initial" else _trajectories(manifest, request, store)
        provenance.publish_json(Path(manifest["paths"]["results_root"]),
            f"workers/{request['worker_id']}_{request['attempt_id']}_{args.mode}.completion.json",
            {"schema": "paper3-batch20-worker-completion-v1", "mode": args.mode, "valid": True,
             "manifest_digest": manifest["manifest_digest"], "request_file_sha256": request["request_file_sha256"],
             "worker_id": request["worker_id"], "attempt_id": request["attempt_id"], "summary": summary,
             "original_scientific_files_unchanged": True, "statistics_executed": False, "finished_utc": _utc()})
        print(f"WORKER_COMPLETED {request['worker_id']} {args.mode}", flush=True)
        return 0
    except BaseException as error:
        if manifest is not None:
            try:
                provenance.publish_json(Path(manifest["paths"]["results_root"]),
                    f"workers/{_label(args.worker_id)}_{_label(args.attempt_id)}_{args.mode}.failure.json",
                    {"status": "FAILED", "mode": args.mode, "worker_id": args.worker_id, "attempt_id": args.attempt_id,
                     "manifest_digest": manifest["manifest_digest"], "error_type": type(error).__name__,
                     "message": str(error), "traceback": traceback.format_exc(), "finished_utc": _utc(),
                     "automatic_retry": False})
            except Exception:
                print("WORKER_FAILURE_RECORD_COULD_NOT_BE_PUBLISHED", file=sys.stderr, flush=True)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
