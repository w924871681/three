"""One intentional, fully journaled static-to-dynamic ownership cutover.

Importing this module performs no Windows API call. There is deliberately no
production CLI. A separately audited caller must supply the exact twelve native
identities, certified new downstream route, and source-pinned read-only snapshot
callback. A model task is never executed here. This is an intentional in-flight
interruption with exact pre-run RNG replay, NOT a trajectory-boundary drain.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from datetime import datetime, timezone

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v3"
HERE = REPO / "verification/paper3_canonical_inputs/replication_dynamic_takeover_v1"
DYNAMIC = REPO / "verification/paper3_canonical_inputs/replication_dynamic_scheduler_v1"
MANIFEST = "7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
F1 = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
OLD_ATTEMPT = "A_FULL_0002"
CONTROL_ROLES = ("durable_supervisor", "delivery_successor", "finalizer", "continuation",
                 "phase_wrapper", "phase_base", "driver_wrapper", "driver_base")
MODEL_ROLES = ("worker_wrapper", "worker_base")
METHODS = {"B0": "B0_Frozen_ratio10", "B1": "B1_AlwaysMaintainP50_ratio10",
           "B2": "B2_RAVM_ratio10", "B8": "B8_AlwaysOpen_ratio10",
           "P7.7": "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"}


class CutoverError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CutoverError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def no_reparse(path):
    path = Path(path)
    require(path.is_absolute(), "absolute path required")
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "reparse/symlink path forbidden: " + str(item))
    return path


def sha(path):
    no_reparse(path)
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    no_reparse(path)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes().decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(CutoverError("nonfinite JSON")))


def child(root, relative):
    root, relative = no_reparse(root), Path(relative)
    require(relative.parts and not relative.is_absolute() and ".." not in relative.parts,
            "unsafe relative path")
    target = no_reparse(root / relative)
    require(target.resolve().is_relative_to(root.resolve()) and target.resolve() != root.resolve(),
            "owned child path escapes root")
    return target


def publish(root, relative, value):
    """Complete-byte hardlink publication; never delete/replace existing data."""
    target = child(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not target.exists(), "immutable publication already exists")
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
    temporary = target.parent / (target.name + ".pending_" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.link(temporary, target, follow_symlinks=False)
    return {"path": str(target), "sha256": hashlib.sha256(data).hexdigest()}


def task_stem(task):
    require(type(task) is dict and set(task) == {"center_id", "seed", "scenario", "method", "config_id"},
            "task identity fields differ")
    require(type(task["center_id"]) is int and 33000 <= task["center_id"] <= 33019 and
            type(task["seed"]) is int and task["seed"] in (7311, 7312, 7313) and
            task["scenario"] in ("C0", "C1", "C3", "C4") and
            METHODS.get(task["method"]) == task["config_id"], "task outside frozen matrix")
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"


def verify_sources(contract, callback):
    sources = contract["snapshot_source_sha256"]
    require(type(sources) is dict and sources, "source-pinned snapshot callback required")
    filename = Path(callback.__code__.co_filename).resolve()
    required = {str(filename), str(Path(__file__).resolve())}
    required.update(str(path.resolve()) for path in DYNAMIC.rglob("*.py")
                    if "synthetic_tests" not in path.relative_to(DYNAMIC).parts)
    require(required <= set(sources), "snapshot/controller/dynamic dependency source pin missing")
    for name, expected in sources.items():
        require(type(expected) is str and re.fullmatch("[0-9a-f]{64}", expected) and sha(name) == expected,
                "source SHA differs: " + name)


def verify_identity(actual, expected):
    for key in ("pid", "creation_filetime", "image", "command_line", "parent_pid"):
        require(actual.get(key) == expected[key], "native process identity differs: " + key)
    require(actual.get("exit_code") == 259, "owned process is no longer running")


def validate_contract(contract, callback):
    require(contract.get("schema") == "paper3-controlled-dynamic-cutover-contract-v1", "contract schema differs")
    require(Path(contract["repository"]) == REPO and Path(contract["results_root"]) == RESULTS,
            "target repository/results differ")
    require(contract.get("old_attempt_id") == OLD_ATTEMPT and
            contract.get("intentional_inflight_interruption_authorized") is True and
            contract.get("performance_used_for_cutover") is False,
            "intentional same-protocol cutover authorization absent")
    bindings = contract["bindings"]
    require(bindings.get("manifest_digest") == MANIFEST and bindings.get("input_bundle_digest") == F1,
            "canonical scientific population differs")
    for name in ("environment_binding", "initial_state_manifest_sha256", "source_bindings_digest",
                 "executor_bundle_digest", "scientific_runtime_signature"):
        require(type(bindings.get(name)) is str and re.fullmatch("[0-9a-f]{64}", bindings[name]),
                "missing exact scientific binding: " + name)
    require(canonical(contract["scientific_runtime"]) == bindings["scientific_runtime_signature"],
            "bound initial scientific runtime differs")
    manifest = read(RESULTS / "provenance_manifest.json")
    require(manifest["manifest_digest"] == MANIFEST and
            canonical({k: v for k, v in manifest.items() if k != "manifest_digest"}) == MANIFEST and
            manifest["input_bundle_digest"] == F1 and
            canonical(manifest["environment"]) == bindings["environment_binding"] and
            canonical(manifest["critical_files_sha256"]) == bindings["source_bindings_digest"] and
            canonical(manifest["executor_sha256"]) == bindings["executor_bundle_digest"],
            "original immutable manifest/scientific binding differs")
    require(sha(RESULTS / "initial_state_manifest.json") == bindings["initial_state_manifest_sha256"],
            "initial60 manifest bytes differ")
    initial = read(RESULTS / "initial_state_manifest.json")
    require(initial.get("completed_cases") == 60 and
            initial.get("manifest_digest") == MANIFEST and initial.get("input_bundle_digest") == F1 and
            initial.get("scientific_runtime_signature") == bindings["scientific_runtime_signature"],
            "initial certificate differs")
    verify_sources(contract, callback)
    certification = contract["pre_stop_certification"]
    require(sha(certification["path"]) == certification["sha256"], "pre-stop certification bytes differ")
    gate = read(certification["path"])
    require(gate.get("schema") == "paper3-dynamic-pre-stop-certification-v1" and
            gate.get("status") == "STATIC_AND_SYNTHETIC_ROUTE_CERTIFIED" and
            gate.get("manifest_digest") == MANIFEST and gate.get("input_bundle_digest") == F1 and
            gate.get("source_bindings_digest") == canonical(contract["snapshot_source_sha256"]),
            "pre-stop static route certification identity differs")
    for key in ("guard_extension_certified", "statistics_provenance_adapter_certified", "delivery_route_certified",
                "quiesce_synthetic_tests_passed", "real_model_smoke_before_full_required"):
        require(gate.get(key) is True, "pre-stop prerequisite absent: " + key)
    owners = contract["processes"]
    require(type(owners) is list and len(owners) == 12 and len({p["pid"] for p in owners}) == 12,
            "exact twelve unique owner identities required")
    controls = [p for p in owners if p["role"] in CONTROL_ROLES]
    require(len(controls) == 8 and {p["role"] for p in controls} == set(CONTROL_ROLES),
            "complete eight-process control chain required")
    models = [p for p in owners if p["role"] in MODEL_ROLES]
    require(len(models) == 4 and {(p["role"], p["worker_id"]) for p in models} ==
            {(r, w) for r in MODEL_ROLES for w in ("W1", "W2")}, "complete two-worker base/wrapper chain required")
    for process in owners:
        require(type(process["pid"]) is int and process["pid"] > 0 and
                type(process["creation_filetime"]) is int and process["creation_filetime"] > 0 and
                type(process["parent_pid"]) is int and process["parent_pid"] > 0 and
                type(process["command_line"]) is str and process["command_line"] and
                str(REPO).casefold() in process["command_line"].casefold(), "incomplete native identity")
        require(Path(process["image"]).is_absolute(), "absolute native image required")
    for worker in ("W1", "W2"):
        base = next(p for p in models if p["role"] == "worker_base" and p["worker_id"] == worker)
        wrapper = next(p for p in models if p["role"] == "worker_wrapper" and p["worker_id"] == worker)
        require(base["parent_pid"] == wrapper["pid"], "model base/wrapper ancestry differs")
    require(set(contract["requests"]) == {"W1", "W2"}, "both immutable worker requests required")
    requests = {}
    assigned = set()
    for worker, reference in contract["requests"].items():
        path = RESULTS / f"execution/full/{OLD_ATTEMPT}/{worker}_request.json"
        require(Path(reference["path"]) == path and sha(path) == reference["sha256"], "old worker request bytes differ")
        value = read(path)
        require(value.get("schema") == "paper3-replication-worker-request-v1" and
                value.get("manifest_digest") == MANIFEST and value.get("worker_id") == worker and
                value.get("attempt_id") == OLD_ATTEMPT and value.get("mode") == "trajectory" and
                value.get("worker_count") == 2 and value.get("performance_based_continuation", False) is False,
                "old worker request identity differs")
        tasks = {task_stem(t): t for t in value["tasks"]}
        require(tasks and len(tasks) == len(value["tasks"]) and not assigned & set(tasks), "duplicate old static assignment")
        assigned.update(tasks)
        requests[worker] = tasks
    return requests


def validate_rng(value, pending, contract):
    runtime, bindings = contract["scientific_runtime"], contract["bindings"]
    require(value.get("schema") == "paper3-original-task-torch-rng-v1" and
            value.get("scope") == "EXISTING_EXECUTION_RNG_PROVENANCE" and value.get("manual_seed_called") is False,
            "RNG schema/scope/manual seed differs")
    require(value.get("state_digest") == pending["rng_state_digest"] ==
            canonical({k: v for k, v in value.items() if k != "state_digest"}), "RNG canonical digest differs")
    require(value.get("torch_version") == runtime["torch_version"] and
            value.get("cuda_runtime") == runtime["torch_cuda_build_version"], "RNG runtime differs")
    manifest = read(RESULTS / "provenance_manifest.json")
    expected = {"task": pending["task"], "input_bundle_digest": F1,
                "source_bindings_digest": bindings["source_bindings_digest"],
                "environment_binding": bindings["environment_binding"],
                "final_configuration_sha256": manifest["critical_files_sha256"]["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
                "expected_initial_state_hash": pending["initial_state_hash"]}
    require(value.get("bindings") == expected, "RNG task/source/environment/initial binding differs")
    devices = runtime["cuda_devices"]
    require(type(value.get("cuda")) is list and len(value["cuda"]) == len(devices), "RNG CUDA coverage differs")
    for index, (entry, device) in enumerate(zip(value["cuda"], devices)):
        require(type(entry.get("device_index")) is int and entry["device_index"] == device["index"] == index and
                entry.get("device_name") == device["name"], "RNG CUDA identity differs")
    for state in [value["cpu"]] + [entry["state"] for entry in value["cuda"]]:
        raw = base64.b64decode(state["base64"], validate=True)
        require(raw and state.get("dtype") == "uint8" and state.get("shape") == [len(raw)] and
                type(state.get("byte_count")) is int and state["byte_count"] == len(raw) and
                hashlib.sha256(raw).hexdigest() == state["sha256"], "RNG byte binding differs")


def audit_snapshot(snapshot, contract, requests):
    """Recheck file bytes and inventory; full scientific validation is callback-bound."""
    require(snapshot.get("schema") == "paper3-dynamic-cutover-snapshot-v1" and
            snapshot.get("bindings") == contract["bindings"] and snapshot.get("unknown_artifacts") == [] and
            snapshot.get("validation_scope") == "FROZEN_REFERENCE_VALIDATE_COMPLETION_ALL_SAVED_24_STAGES",
            "snapshot scientific identity/scope/unknown artifacts differs")
    records, artifacts = snapshot["saved_records"], snapshot["saved_artifacts"]
    require(type(records) is dict and records and type(artifacts) is dict and artifacts and
            type(snapshot.get("completed_count")) is int and snapshot["completed_count"] == len(records) < 1200,
            "snapshot saved-record count differs")
    for name, expected in artifacts.items():
        require(Path(name).is_absolute() and re.fullmatch("[0-9a-f]{64}", expected) and sha(name) == expected,
                "saved artifact bytes differ: " + name)
    raw = RESULTS / "raw"
    raw_csv = {p.stem for p in raw.glob("*.csv")}
    raw_receipts = {p.name.removesuffix(".integrity.json") for p in raw.glob("*.integrity.json")}
    require(raw_csv == raw_receipts == set(records), "partial/unknown raw CSV or receipt")
    initial = read(RESULTS / "initial_state_manifest.json")
    initials = {(v["center_id"], v["seed"]): v["initial_state_hash"] for v in initial["states"]}
    require(len(initials) == 60 and set(initials) == {(c, s) for c in range(33000, 33020) for s in (7311, 7312, 7313)},
            "initial sixty case identities differ")
    receipts, groups = {}, {}
    for name, expected in records.items():
        path = raw / f"{name}.integrity.json"
        require(sha(path) == expected == artifacts.get(str(path)), "raw receipt bytes not bound")
        receipt = read(path); task = receipt["task"]
        require(task_stem(task) == name and receipt.get("valid") is True and receipt.get("trajectory_rows") == 24,
                "saved raw receipt task/coverage differs")
        for key in ("manifest_digest", "input_bundle_digest", "environment_binding", "initial_state_manifest_sha256",
                    "source_bindings_digest", "executor_bundle_digest", "scientific_runtime_signature"):
            require(receipt.get(key) == contract["bindings"][key], "saved receipt binding differs: " + key)
        require(receipt["initial_state_hash"] == initials[task["center_id"], task["seed"]], "saved initial case differs")
        csv_path = raw / f"{name}.csv"
        require(sha(csv_path) == receipt["output_hash"] == artifacts.get(str(csv_path)), "raw CSV byte binding differs")
        for path_key, hash_key in (("audit_relative", "audit_hash"), ("rng_relative", "rng_file_sha256"),
                                   ("attempt_csv_relative", "attempt_csv_hash"), ("runtime_receipt_path", "runtime_receipt_sha256")):
            linked = child(RESULTS, receipt[path_key])
            require(sha(linked) == receipt[hash_key] == artifacts.get(str(linked)), "linked saved artifact missing/changed")
        receipts[name] = receipt
        key = (task["center_id"], task["seed"], task["scenario"])
        group = groups.setdefault(key, set()); require(task["method"] not in group, "duplicate saved paired method")
        group.add(task["method"])
    require(type(snapshot.get("paired_count")) is int and snapshot["paired_count"] ==
            sum(group == set(METHODS) for group in groups.values()), "paired group count differs")
    pending = snapshot["pending"]
    require(type(pending) is list and len(pending) <= 2, "at most two incomplete old tasks allowed")
    seen_workers, seen_tasks, pending_dirs = set(), set(), set()
    for item in pending:
        worker, task = item["worker_id"], item["task"]
        name = task_stem(task)
        require(worker in requests and item["attempt_id"] == OLD_ATTEMPT and
                requests[worker].get(name) == task and name not in records and
                worker not in seen_workers and name not in seen_tasks, "pending old assignment/task identity differs")
        seen_workers.add(worker); seen_tasks.add(name)
        relative = f"attempts/{name}/{OLD_ATTEMPT}/{worker}/rng_before.json"
        path = child(RESULTS, relative)
        require(item["rng_relative"] == relative and path.is_file() and
                {p.name for p in path.parent.iterdir()} == {"rng_before.json"}, "pending attempt is not RNG-only")
        require(sha(path) == item["rng_file_sha256"] == artifacts.get(str(path)), "pending RNG file bytes differ")
        require(item["initial_state_hash"] == initials[task["center_id"], task["seed"]], "pending initial case differs")
        validate_rng(read(path), item, contract)
        pending_dirs.add(path.parent)
    # Static full002 may have only completed exact original publications or the
    # declared RNG-only claims. Never delete or reinterpret partial outputs.
    for attempt in (RESULTS / "attempts").glob(f"*/{OLD_ATTEMPT}"):
        for directory in attempt.iterdir():
            require(directory.is_dir() and directory.name in ("W1", "W2"), "unknown old attempt artifact")
            if directory in pending_dirs:
                continue
            name = attempt.parent.name
            require(name in receipts and receipts[name].get("attempt_id") == OLD_ATTEMPT and
                    receipts[name].get("worker_id") == directory.name and
                    {p.name for p in directory.iterdir()} == {"rng_before.json", "trajectory.csv", "audit.json", "receipt.json"},
                    "partial/unpublished old attempt body")
            require(sha(directory / "receipt.json") == records[name] and
                    all(artifacts.get(str(p)) == sha(p) for p in directory.iterdir()), "completed attempt bytes not bound")
    return {"completed_count": len(records), "paired_count": snapshot["paired_count"],
            "pending_count": len(pending), "snapshot_digest": canonical({k: v for k, v in snapshot.items() if k != "captured_utc"}),
            "scientific_runtime_executed": False, "performance_used": False}


def _ordered_processes(contract):
    controls = sorted((p for p in contract["processes"] if p["role"] in CONTROL_ROLES),
                      key=lambda p: CONTROL_ROLES.index(p["role"]))
    models = sorted((p for p in contract["processes"] if p["role"] in MODEL_ROLES),
                    key=lambda p: (MODEL_ROLES.index(p["role"]), p["worker_id"]))
    return controls + models


def failure_receipt(pending, contract, base_outcome, evidence):
    require(base_outcome["observed_dead"] is True and type(base_outcome["exit_code"]) is int and
            base_outcome["exit_code"] != 259, "actual native terminal evidence required")
    return {"schema": "paper3-batch20-failed-task-receipt-v1", "status": "INTERRUPTED", "completed_valid": False,
            "task": pending["task"], "manifest_digest": MANIFEST, "input_bundle_digest": F1,
            "environment_binding": contract["bindings"]["environment_binding"],
            "initial_state_hash": pending["initial_state_hash"], "worker_id": pending["worker_id"], "attempt_id": OLD_ATTEMPT,
            "rng_relative": pending["rng_relative"], "rng_file_sha256": pending["rng_file_sha256"],
            "rng_state_digest": pending["rng_state_digest"], "failed_before_rng_capture": False,
            "created_utc": utc(), "producer": "intentional-cutover-observer", "external_observer": True,
            "error_type": "IntentionalSchedulingOwnershipCutover", "worker_exception_observed": False,
            "termination_actor": "AUTHORIZED_EXTERNAL_CUTOVER_CONTROLLER", "intentional_cutover": True,
            "actual_exit_code": base_outcome["exit_code"], "native_terminal_evidence": evidence,
            "message": "The exact identity-checked static worker was intentionally stopped after a frozen RNG-only audit. This external observer record is not a worker exception or a normal completion.",
            "automatic_new_draw_retry": False, "originals_overwritten": False,
            "trajectory_boundary_drain_claimed": False, "model_output_worker_invariance_claimed": False}


def run_quiescence(contract, evidence_dir, backend, snapshot_builder):
    """Explicit destructive action: caller authorization/gates are prerequisites.

    backend: open(pid), info(handle,pid), inventory(), suspend(handle),
    resume(handle), terminate_and_wait(handle,pid), exit_code(handle), close(handle).
    inventory() returns actual current old-owner PID integers, with unrecognized
    experiment writers rejected rather than silently excluded by the adapter.
    """
    requests = validate_contract(contract, snapshot_builder)
    directory = Path(evidence_dir)
    require(directory.is_absolute() and directory.is_relative_to(HERE) and directory != HERE,
            "new independent evidence directory required")
    no_reparse(directory)
    require(not directory.exists(), "exclusive cutover evidence directory already exists")
    directory.mkdir(parents=True)
    publish(HERE, "CONTROLLED_QUIESCE_EXCLUSIVE_LOCK.json", {"pid": os.getpid(), "created_utc": utc(),
            "contract_digest": canonical(contract), "evidence_directory": str(directory), "automatic_retry": False})
    publish(directory, "intent.json", {"schema": "paper3-intentional-static-dynamic-cutover-v1", "created_utc": utc(),
            "contract": contract, "contract_digest": canonical(contract), "actual_stop_performed": False,
            "intentional_inflight_interruption": True, "trajectory_boundary_drain_claimed": False})
    opened, suspended, dead, outcomes = [], [], set(), []
    current = "native_identity_admission"
    success, error, rollback = None, None, []
    try:
        expected_pids = {p["pid"] for p in contract["processes"]}
        require(set(backend.inventory()) == expected_pids, "additional/missing old experiment owner")
        for process in _ordered_processes(contract):
            handle = backend.open(process["pid"])
            opened.append((handle, process))
            verify_identity(backend.info(handle, process["pid"]), process)
        current = "suspend_control_chain_then_models"
        for handle, process in opened:
            verify_identity(backend.info(handle, process["pid"]), process)
            backend.suspend(handle)
            suspended.append((handle, process))
        require(set(backend.inventory()) == expected_pids, "owner inventory changed during quiescence")
        for handle, process in opened:
            verify_identity(backend.info(handle, process["pid"]), process)
        current = "frozen_snapshot_validation"
        verify_sources(contract, snapshot_builder)
        first = snapshot_builder(contract); first_audit = audit_snapshot(first, contract, requests)
        cpu_first = {p["pid"]: backend.info(h, p["pid"]).get("cpu_100ns") for h, p in opened}
        second = snapshot_builder(contract); second_audit = audit_snapshot(second, contract, requests)
        require(first_audit == second_audit, "frozen scientific bytes/inventory changed")
        require(all(type(v) is int for v in cpu_first.values()), "native CPU suspension observation missing")
        for handle, process in opened:
            info = backend.info(handle, process["pid"]); verify_identity(info, process)
            require(info.get("cpu_100ns") == cpu_first[process["pid"]], "paused owner still executed CPU work")
        verify_sources(contract, snapshot_builder)
        snapshot_ref = publish(directory, "frozen_snapshot.json", second)
        audit_ref = publish(directory, "frozen_snapshot_audit.json", second_audit)
        publish(directory, "termination_intent.json", {"created_utc": utc(), "snapshot": snapshot_ref,
                "audit": audit_ref, "processes": contract["processes"], "actual_stop_performed": False})
        current = "intentional_native_termination"
        # Model bases/wrappers first; every control owner is already suspended.
        for index, (handle, process) in enumerate(reversed(opened), 1):
            outcome = backend.terminate_and_wait(handle, process["pid"])
            require(outcome.get("pid") == process["pid"] and outcome.get("observed_dead") is True and
                    type(outcome.get("exit_code")) is int and outcome["exit_code"] != 259 and
                    type(outcome.get("termination_requested")) is bool,
                    "native termination result not actually observed")
            dead.add(process["pid"])
            outcome = {**outcome, "creation_filetime": process["creation_filetime"], "role": process["role"],
                       "worker_id": process.get("worker_id"), "observed_utc": utc()}
            outcomes.append(outcome)
            publish(directory, f"native_termination_{index:03d}.json", outcome)
        require(not backend.inventory(), "old/new experiment owner still active after controlled stop")
        require(all(backend.exit_code(handle) != 259 for handle, _ in opened), "pinned old handle remains active")
        current = "post_stop_byte_revalidation"
        post = snapshot_builder(contract); post_audit = audit_snapshot(post, contract, requests)
        require(post_audit == second_audit, "scientific bytes changed while stopping owners")
        verify_sources(contract, snapshot_builder)
        termination = publish(directory, "actual_termination_evidence.json", {"created_utc": utc(),
            "schema": "paper3-intentional-cutover-native-termination-v1", "outcomes": outcomes,
            "all_twelve_old_owners_dead": True, "snapshot": snapshot_ref, "audit": audit_ref,
            "normal_completion_claimed": False, "worker_exception_invented": False})
        current = "truthful_pending_interruption_receipts"
        receipts = []
        for item in post["pending"]:
            base = next(o for o in outcomes if o["role"] == "worker_base" and o["worker_id"] == item["worker_id"])
            value = failure_receipt(item, contract, base, termination)
            prepared = publish(directory, f"pending_{item['worker_id']}_interruption.json", value)
            rng = child(RESULTS, item["rng_relative"])
            require({p.name for p in rng.parent.iterdir()} == {"rng_before.json"} and
                    sha(rng) == item["rng_file_sha256"], "pending bytes changed before observer receipt")
            destination = child(rng.parent, "failure.json")
            os.link(prepared["path"], destination, follow_symlinks=False)
            require(sha(destination) == prepared["sha256"], "observer receipt link differs")
            receipts.append({"path": str(destination), "sha256": prepared["sha256"], "worker_id": item["worker_id"],
                             "task": item["task"], "rng_state_digest": item["rng_state_digest"]})
        success = {"schema": "paper3-controlled-quiescence-result-v1", "status": "OLD_OWNERS_INTENTIONALLY_QUIESCED",
                   "finished_utc": utc(), "completed_count": post["completed_count"], "paired_count": post["paired_count"],
                   "pending_interruption_receipts": receipts, "termination_evidence": termination,
                   "snapshot": snapshot_ref, "snapshot_audit": audit_ref, "bindings": contract["bindings"],
                   "new_dynamic_workers_started": False, "statistics_executed": False, "scientific_integrity_pass": False,
                   "intentional_inflight_interruption": True, "trajectory_boundary_drain_claimed": False,
                   "automatic_retry": False, "model_output_worker_invariance_claimed": False}
        publish(directory, "quiescence_complete.json", success)
    except BaseException as caught:
        error = caught
    finally:
        # Even after partial termination, every other still-live suspended handle
        # receives its matching resume attempt. Never claim an impossible rollback
        # of an already-dead process. Native handles stay pinned until this ends.
        for handle, process in reversed(suspended):
            if process["pid"] in dead:
                continue
            try:
                code = backend.exit_code(handle)
                if code == 259:
                    backend.resume(handle)
                    rollback.append({"pid": process["pid"], "resumed": True})
                else:
                    dead.add(process["pid"])
                    rollback.append({"pid": process["pid"], "resumed": False, "observed_already_dead_exit_code": code})
            except BaseException as resume_error:
                rollback.append({"pid": process["pid"], "resumed": False, "resume_error": str(resume_error)})
        for handle, process in reversed(opened):
            try:
                backend.close(handle)
            except BaseException as close_error:
                rollback.append({"pid": process["pid"], "close_error": str(close_error)})
        if error is not None:
            publish(directory, "stopped.json", {"status": "STOPPED_FOR_DIAGNOSIS", "phase": current,
                "observed_utc": utc(), "error_type": type(error).__name__, "message": str(error),
                "actual_terminated_count": len(dead), "actual_termination_outcomes": outcomes,
                "resume_or_terminal_observations": rollback, "automatic_retry": False,
                "originals_deleted_or_overwritten": False, "new_dynamic_workers_started": False,
                "scientific_integrity_pass": False, "all_prior_evidence_preserved": True})
    if error is not None:
        raise CutoverError(f"Controlled cutover stopped at {current}: {type(error).__name__}: {error}") from error
    return success


class NativeWindowsBackend:
    """Explicitly instantiated pinned-handle native adapter; no module import effect.

    `inventory_callback` is a separately source-pinned read-only root callback
    which must reject inaccessible/unrecognized experiment commands. It returns
    actual owner PIDs; the controller compares the whole set, never PID alone.
    """
    def __init__(self, inventory_callback):
        require(os.name == "nt", "Windows-only native adapter")
        import ctypes
        from ctypes import wintypes
        self.c, self.w = ctypes, wintypes
        self.inventory_callback = inventory_callback
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        k, w, c = self.kernel, wintypes, ctypes
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
        k.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4; k.GetProcessTimes.restype = w.BOOL
        k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
        k.QueryFullProcessImageNameW.restype = w.BOOL
        k.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]; k.GetExitCodeProcess.restype = w.BOOL
        k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]; k.TerminateProcess.restype = w.BOOL
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
        for name in ("NtSuspendProcess", "NtResumeProcess"):
            getattr(self.nt, name).argtypes = [w.HANDLE]; getattr(self.nt, name).restype = w.LONG
        self.nt.NtQueryInformationProcess.argtypes = [w.HANDLE, w.ULONG, c.c_void_p, w.ULONG, c.POINTER(w.ULONG)]
        self.nt.NtQueryInformationProcess.restype = w.LONG

    def inventory(self):
        result = self.inventory_callback()
        require(type(result) is list and all(type(pid) is int and pid > 0 for pid in result) and
                len(result) == len(set(result)), "actual native inventory callback differs")
        return result

    def open(self, pid):
        handle = self.kernel.OpenProcess(0x0400 | 0x0010 | 0x0800 | 0x0001 | 0x100000, False, pid)
        require(bool(handle), "OpenProcess failed: " + str(self.c.get_last_error()))
        return handle

    def exit_code(self, handle):
        code = self.w.DWORD()
        require(self.kernel.GetExitCodeProcess(handle, self.c.byref(code)), "GetExitCodeProcess failed")
        return code.value

    def command_line(self, handle):
        c, w = self.c, self.w
        class US(c.Structure):
            _fields_ = [("Length", w.USHORT), ("MaximumLength", w.USHORT), ("Buffer", c.c_void_p)]
        size = w.ULONG()
        self.nt.NtQueryInformationProcess(handle, 60, None, 0, c.byref(size))
        require(c.sizeof(US) <= size.value <= 1024 * 1024, "command line buffer length invalid")
        buf = c.create_string_buffer(size.value)
        require(self.nt.NtQueryInformationProcess(handle, 60, buf, size.value, c.byref(size)) >= 0,
                "native command line query failed")
        value = US.from_buffer(buf); start = c.addressof(buf)
        require(value.Length % 2 == 0 and value.Buffer is not None and start <= value.Buffer and
                value.Buffer + value.Length <= start + len(buf), "native command line bounds invalid")
        return c.wstring_at(value.Buffer, value.Length // 2)

    def info(self, handle, pid):
        c, w = self.c, self.w
        times = [w.FILETIME() for _ in range(4)]
        require(self.kernel.GetProcessTimes(handle, *(c.byref(t) for t in times)), "GetProcessTimes failed")
        ticks = lambda v: (v.dwHighDateTime << 32) | v.dwLowDateTime
        image, size = c.create_unicode_buffer(32768), w.DWORD(32768)
        require(self.kernel.QueryFullProcessImageNameW(handle, 0, image, c.byref(size)), "native image query failed")
        class PBI(c.Structure):
            _fields_ = [("Reserved1", c.c_void_p), ("PebBaseAddress", c.c_void_p), ("Reserved2", c.c_void_p * 2),
                        ("UniqueProcessId", c.c_size_t), ("InheritedFromUniqueProcessId", c.c_size_t)]
        basic, length = PBI(), w.ULONG()
        require(self.nt.NtQueryInformationProcess(handle, 0, c.byref(basic), c.sizeof(basic), c.byref(length)) >= 0
                and basic.UniqueProcessId == pid, "native ancestry/handle identity differs")
        return {"pid": pid, "creation_filetime": ticks(times[0]), "image": image.value,
                "command_line": self.command_line(handle), "parent_pid": basic.InheritedFromUniqueProcessId,
                "exit_code": self.exit_code(handle), "cpu_100ns": ticks(times[2]) + ticks(times[3])}

    def suspend(self, handle):
        require(self.nt.NtSuspendProcess(handle) >= 0, "NtSuspendProcess failed")

    def resume(self, handle):
        require(self.nt.NtResumeProcess(handle) >= 0, "NtResumeProcess failed")

    def terminate_and_wait(self, handle, pid):
        requested = self.exit_code(handle) == 259
        if requested:
            require(self.kernel.TerminateProcess(handle, 0xE0000002), "TerminateProcess failed")
        require(self.kernel.WaitForSingleObject(handle, 30000) == 0, "native exit wait failed")
        code = self.exit_code(handle)
        require(code != 259, "native process still active")
        return {"pid": pid, "observed_dead": True, "exit_code": code, "termination_requested": requested,
                "method": "TerminateProcess" if requested else "OBSERVED_ALREADY_EXITED_AFTER_OWNED_PEER_STOP"}

    def close(self, handle):
        require(self.kernel.CloseHandle(handle), "CloseHandle failed")
