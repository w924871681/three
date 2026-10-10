"""Persistent task stream around byte-unchanged original worker functions.

No production invocation is permitted without a genuine quiescent takeover
gate.  FULL additionally needs a real bridge smoke certificate.  Synthetic
tests use fake original modules and never call a project model.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import uuid


REPO_ROOT = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
SCHEDULER_ROOT = REPO_ROOT / "verification/paper3_canonical_inputs/replication_dynamic_scheduler_v1"
EXECUTOR_ROOT = REPO_ROOT / "verification/paper3_canonical_inputs/replication_executor_batch20_env_v3"
RESULTS_ROOT = REPO_ROOT / "results/p7_7_integrity_replication_batch20_env_v3"
MANIFEST_DIGEST = "7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
F1_DIGEST = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
EXTENSION_SCOPE = "ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256"


class BridgeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise BridgeError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def no_reparse(path):
    path = Path(path)
    require(path.is_absolute(), "absolute path required")
    for item in (path, *path.parents):
        require(not item.is_symlink(), "symlink rejected: " + str(item))
        if item.exists():
            require(not getattr(item.lstat(), "st_file_attributes", 0) & 0x400,
                    "reparse point rejected: " + str(item))


def sha(path):
    no_reparse(path)
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def parse(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(BridgeError("nonfinite JSON")))


def load(path):
    no_reparse(path)
    return parse(Path(path).read_bytes())


def safe_child(root, relative):
    root, relative = Path(root), Path(relative)
    require(root.is_absolute() and relative.parts and not relative.is_absolute() and
            ".." not in relative.parts, "unsafe child path")
    result = root / relative
    no_reparse(result)
    require(result.resolve().is_relative_to(root.resolve()), "path escapes owned root")
    return result


def publish(root, relative, value):
    path = safe_child(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("immutable worker publication already exists")
    temporary = path.parent / (path.name + ".pending_" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                                 allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)
    return {"path": str(path), "sha256": sha(path)}


def worker_root_check(worker_id, worker_root):
    require(type(worker_id) is str and re.fullmatch(r"DW[0-9]{4,8}", worker_id), "invalid dynamic worker ID")
    root = Path(worker_root)
    require(root.is_absolute() and root.is_relative_to(RESULTS_ROOT) and root != RESULTS_ROOT and
            root.name == worker_id, "worker root is not its owned independent-result child")
    no_reparse(root)
    require(root.resolve() == root and root.is_dir(), "worker root missing or aliased")
    return root


def validate_contract(contract_path):
    """Read-only admission; no imports of the original scientific worker here."""
    path = Path(contract_path)
    require(path.is_absolute() and path.is_relative_to(REPO_ROOT), "contract outside target repository")
    no_reparse(path)
    contract_sha = sha(path)
    contract = load(path)
    require(contract.get("source_extension_scope") == EXTENSION_SCOPE, "source extension scope differs")
    require(Path(contract["manifest_path"]) == RESULTS_ROOT / "provenance_manifest.json", "manifest path differs")
    require(Path(contract["original_executor_root"]) == EXECUTOR_ROOT, "original executor root differs")
    require(contract.get("initial_state_manifest") == "initial_state_manifest.json", "initial manifest path differs")
    require(type(contract.get("attempt_id")) is str and
            re.fullmatch(r"A_DYNAMIC_[0-9]{4}", contract["attempt_id"]), "invalid dynamic attempt identity")
    manifest = load(contract["manifest_path"])
    body = dict(manifest); body.pop("manifest_digest", None)
    require(manifest.get("manifest_digest") == MANIFEST_DIGEST == canonical(body), "frozen manifest digest differs")
    require(manifest.get("input_bundle_digest") == F1_DIGEST and
            Path(manifest["paths"]["results_root"]) == RESULTS_ROOT, "canonical input/result identity differs")
    sources = contract.get("sidecar_sources")
    require(type(sources) is dict and sources and contract.get("sidecar_digest") == canonical(sources),
            "sidecar source map/digest differs")
    for name, expected in sources.items():
        source = Path(name)
        require(source.is_absolute() and source.is_relative_to(SCHEDULER_ROOT) and source.suffix == ".py",
                "sidecar source outside independent implementation")
        require(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) and sha(source) == expected,
                "sidecar source bytes differ")
    for name in ("frozen_bridge.py", "guard_extension.py"):
        require(str(SCHEDULER_ROOT / name) in sources, "production bridge source missing from sidecar")
    proof_path, gate_path = Path(contract["sourceproof_path"]), Path(contract["activation_gate_path"])
    for item, field in ((proof_path, "sourceproof_sha256"), (gate_path, "activation_gate_sha256")):
        require(item.is_absolute() and item.is_relative_to(REPO_ROOT) and sha(item) == contract[field],
                "source proof/takeover gate SHA or path differs")
    proof = load(proof_path)
    require(proof.get("schema") == "paper3-dynamic-synthetic-test-proof-v1" and proof.get("all_pass") is True and
            proof.get("actual_model_execution") is False and proof.get("model_runtime_verification") == "NOT_EXECUTED",
            "synthetic proof scope or result differs")
    require(type(proof.get("tests_run")) is int and proof["tests_run"] > 0 and
            all(type(proof.get(key)) is int and proof[key] == 0 for key in ("failures", "errors", "skipped")) and
            proof.get("implementation_sha256") == sources, "synthetic proof counts/source closure differ")
    gate = load(gate_path)
    require(gate.get("schema") == "paper3-dynamic-takeover-gate-v1" and gate.get("status") == "PASS" and
            gate.get("source_extension_scope") == EXTENSION_SCOPE and
            gate.get("sidecar_digest") == contract["sidecar_digest"], "takeover gate identity differs")
    require(gate.get("manifest_digest") == MANIFEST_DIGEST and gate.get("input_bundle_digest") == F1_DIGEST and
            gate.get("initial_manifest_sha256") == sha(RESULTS_ROOT / "initial_state_manifest.json"),
            "takeover scientific/initial identity differs")
    require(gate.get("old_owners_quiescent") is True and gate.get("delivery_route_certified") is True,
            "old ownership or downstream certification is not ready")
    mode = contract.get("execution_mode", "FULL")
    require(mode in {"FULL", "BRIDGE_SMOKE"}, "unknown execution mode")
    tasks = contract.get("eligible_tasks")
    require(type(tasks) is list and tasks and all(type(task) is dict for task in tasks), "eligible task domain empty/invalid")
    require(len({canonical(task) for task in tasks}) == len(tasks), "duplicate eligible task")
    require(type(contract.get("retries", {})) is dict, "retry descriptors must be a map")
    if mode == "FULL":
        require(gate.get("real_model_bridge_smoke_passed") is True, "real model bridge smoke not certified")
    else:
        require(len(tasks) == 1 and gate.get("scope") == "ONE_PREDECLARED_PENDING_TASK" and
                gate.get("smoke_task_digest") == canonical(tasks[0]), "smoke mode exceeds its one declared task")
    require(sha(path) == contract_sha, "contract changed during admission")
    return contract, manifest, contract_sha


class TaskStream(list):
    """Iterator driven by immutable commands, only at original task boundaries."""
    def __init__(self, worker_root, worker_id, contract, contract_sha, complete,
                 *, pause=time.sleep, monotonic=time.monotonic):
        super().__init__()
        self.root, self.worker_id = Path(worker_root), worker_id
        self.contract = copy.deepcopy(contract)
        self.contract_sha = contract_sha
        self.allowed = {canonical(task): copy.deepcopy(task) for task in contract["eligible_tasks"]}
        self.complete, self.pause, self.monotonic = complete, pause, monotonic
        self.sequence, self.claimed = 1, 0
        self.pending, self.stopped = None, False
        self.seen_tasks, self.seen_claims = set(), set()

    def __len__(self):
        return self.claimed

    def __iter__(self):
        return self

    def _acknowledge(self):
        if self.pending is None:
            return
        command, command_sha, sequence = self.pending
        evidence = self.complete(copy.deepcopy(command["task"]))
        event = {"schema": "paper3-dynamic-task-done-v1", "worker_id": self.worker_id,
                 "sequence": sequence, "task": command["task"], "task_digest": command["task_digest"],
                 "claim_id": command["claim_id"], "contract_sha256": self.contract_sha,
                 "command_sha256": command_sha, "finished_utc": utc(), **evidence}
        publish(self.root, f"events/{sequence:06d}.done.json", event)
        self.pending = None

    def _command(self):
        path = safe_child(self.root, f"commands/{self.sequence:06d}.json")
        malformed_since = None
        while True:
            if not path.exists():
                self.pause(0.2)
                continue
            no_reparse(path)
            payload = path.read_bytes()
            try:
                command = parse(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                if malformed_since is None:
                    malformed_since = self.monotonic()
                require(self.monotonic() - malformed_since <= 2.0, "command JSON remained incomplete/malformed")
                self.pause(0.05)
                continue
            require(type(command) is dict and command.get("contract_sha256") == self.contract_sha,
                    "command contract binding differs")
            require(path.read_bytes() == payload, "command changed during read")
            if "worker_id" in command:
                require(command["worker_id"] == self.worker_id, "command belongs to another worker")
            if "sequence" in command:
                require(command["sequence"] == self.sequence, "command sequence differs")
            return command, hashlib.sha256(payload).hexdigest()

    def __next__(self):
        if self.stopped:
            raise StopIteration
        self._acknowledge()
        if self.contract.get("execution_mode", "FULL") == "BRIDGE_SMOKE" and self.claimed == 1:
            self.stopped = True
            raise StopIteration
        command, command_sha = self._command()
        if command.get("action") == "STOP":
            require("task" not in command and "claim_id" not in command, "STOP cannot hold a task claim")
            self.stopped = True
            raise StopIteration
        require(command.get("action") == "TASK", "unknown worker command")
        task = command.get("task")
        task_digest = command.get("task_digest")
        require(type(task) is dict and task_digest == canonical(task) and
                self.allowed.get(task_digest) == task, "task is outside the frozen eligible domain")
        claim = command.get("claim_id")
        require(type(claim) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", claim), "unsafe claim ID")
        require(task_digest not in self.seen_tasks and claim not in self.seen_claims, "duplicate task or claim assignment")
        self.seen_tasks.add(task_digest); self.seen_claims.add(claim)
        self.claimed += 1
        self.pending = (copy.deepcopy(command), command_sha, self.sequence)
        self.sequence += 1
        return copy.deepcopy(task)


def load_worker(contract, manifest):
    """Load byte-pinned original stdlib modules; install the explicit extension."""
    root = Path(contract["original_executor_root"])
    for name in ("executor_worker.py", "provenance.py"):
        require(sha(root / name) == manifest["executor_sha256"][name], "original worker source SHA differs")
    guard_path = SCHEDULER_ROOT / "guard_extension.py"
    require(sha(guard_path) == contract["sidecar_sources"][str(guard_path)], "guard extension SHA differs before import")
    guard_name = "paper3_dynamic_guard_extension"
    require(guard_name not in sys.modules, "guard module already loaded")
    spec = importlib.util.spec_from_file_location(guard_name, guard_path)
    guard = importlib.util.module_from_spec(spec)
    sys.modules[guard_name] = guard; spec.loader.exec_module(guard)
    package_name = "paper3_dynamic_frozen_executor"
    require(package_name not in sys.modules, "original worker package already loaded")
    package = types.ModuleType(package_name); package.__path__ = [str(root)]
    sys.modules[package_name] = package
    worker_name = package_name + ".executor_worker"
    spec = importlib.util.spec_from_file_location(worker_name, root / "executor_worker.py")
    worker = importlib.util.module_from_spec(spec)
    sys.modules[worker_name] = worker; spec.loader.exec_module(worker)
    extension = guard.install(worker.provenance, manifest, contract)
    return worker, extension


def bootstrap_request_check(contract, manifest, worker_id, root):
    path = safe_child(root, "bootstrap_request.json")
    value = load(path)
    expected = {"schema": "paper3-replication-worker-request-v1", "manifest_digest": manifest["manifest_digest"],
                "mode": "trajectory", "worker_id": worker_id, "attempt_id": contract["attempt_id"],
                "tasks": contract["eligible_tasks"], "initial_state_manifest": "initial_state_manifest.json"}
    require(all(value.get(key) == item for key, item in expected.items()), "bootstrap eligible-domain request differs")
    require(type(value.get("worker_count")) is int and 1 <= value["worker_count"] <= 3 and
            value.get("performance_based_continuation", False) is False, "bootstrap resource/selection rule differs")
    require(value.get("retries", {}) == contract.get("retries", {}), "bootstrap retry binding differs")
    return path, sha(path)


def completion_validator(worker, manifest, request, store):
    initial_hashes, initial_sha = worker._initial_references(
        manifest, runtime_signature=request["scientific_runtime_signature"])
    root = Path(manifest["paths"]["results_root"])

    def complete(task):
        receipt = worker._existing_completed(manifest, store, task,
            initial_hashes[(task["center_id"], task["seed"])], initial_sha,
            runtime_signature=request["scientific_runtime_signature"])
        require(receipt is not None, "original worker has not published a complete valid trajectory")
        stem = worker._stem(task)
        relative = f"raw/{stem}.integrity.json"
        receipt_path = safe_child(root, relative)
        require(load(receipt_path) == receipt, "published receipt changed before DONE")
        return {"receipt_relative": relative, "receipt_sha256": sha(receipt_path),
                "output_sha256": receipt["output_hash"], "audit_relative": receipt["audit_relative"],
                "audit_sha256": receipt["audit_hash"], "rng_relative": receipt["rng_relative"],
                "rng_sha256": receipt["rng_file_sha256"],
                "attempt_csv_relative": receipt["attempt_csv_relative"],
                "attempt_csv_sha256": receipt["attempt_csv_hash"],
                "original_completed_validator_passed": True,
                "scientific_acceptance_by_final_full_audit_still_required": True}
    return complete


def run(contract_path, worker_id, worker_root, *, loader=load_worker):
    root = worker_root_check(worker_id, worker_root)
    for name in ("ready.json", "finished.json", "failure.json"):
        require(not safe_child(root, name).exists(), "worker lifecycle journal already exists")
    contract, manifest, contract_sha = validate_contract(contract_path)
    bootstrap_path, bootstrap_sha = bootstrap_request_check(contract, manifest, worker_id, root)
    worker, extension = loader(contract, manifest)
    prepared_manifest, request, store = worker._prepare(Path(contract["manifest_path"]), bootstrap_path,
                                                       "trajectory", worker_id, contract["attempt_id"])
    require(prepared_manifest == manifest and request["request_file_sha256"] == bootstrap_sha,
            "original preparation used different manifest/bootstrap bytes")
    require(sha(contract_path) == contract_sha, "contract changed during original preparation")
    stream = TaskStream(root, worker_id, contract, contract_sha,
                        completion_validator(worker, manifest, request, store))
    # The original _request validator has finished before this substitution.
    # This list is an explicit dynamic sidecar stream, not a preassigned list.
    request["tasks"] = stream
    publish(root, "ready.json", {"schema": "paper3-dynamic-worker-ready-v1", "created_utc": utc(),
        "pid": os.getpid(), "worker_id": worker_id, "contract_sha256": contract_sha,
        "execution_mode": contract.get("execution_mode", "FULL"),
        "bootstrap_request_sha256": bootstrap_sha, "bootstrap_tasks_meaning": "ELIGIBLE_DOMAIN_NOT_PREASSIGNMENT",
        "eligible_tasks": len(contract["eligible_tasks"]), "runtime_receipt_path": request["runtime_receipt_path"],
        "runtime_receipt_sha256": request["runtime_receipt_sha256"],
        "scientific_runtime_signature": request["scientific_runtime_signature"],
        "import_origin_extension": extension, "model_task_started_claimed": False})
    summary = worker._trajectories(manifest, request, store)
    require(stream.stopped and stream.pending is None, "original loop exited with an unacknowledged claim")
    require(summary.get("assigned_tasks") == len(stream) and
            summary.get("completed_tasks", 0) + summary.get("skipped_valid_tasks", 0) == len(stream),
            "original summary differs from dynamic claimed coverage")
    require(sha(contract_path) == contract_sha, "contract changed during worker execution")
    result = {"schema": "paper3-dynamic-worker-finished-v1", "finished_utc": utc(),
        "pid": os.getpid(), "worker_id": worker_id, "contract_sha256": contract_sha,
        "execution_mode": contract.get("execution_mode", "FULL"), "summary": summary,
        "runtime_receipt_path": request["runtime_receipt_path"],
        "runtime_receipt_sha256": request["runtime_receipt_sha256"],
        "original_trajectories_returned_after_full_checks": True,
        "new_manual_seed_introduced": False, "scientific_algorithm_modified": False,
        "model_output_worker_invariance_claimed": False, "statistics_executed": False}
    publish(root, "finished.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--worker-root", type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "requires -I -S -B")
    require(Path(__file__).resolve().parent == SCHEDULER_ROOT, "unexpected production bridge source root")
    root = worker_root_check(args.worker_id, args.worker_root)
    try:
        run(args.contract, args.worker_id, root)
        return 0
    except BaseException as error:
        pending = None
        # The original task failure/RNG receipt remains authoritative. This
        # lifecycle observation never invents a failed task or a fresh draw.
        try:
            publish(root, "failure.json", {"schema": "paper3-dynamic-worker-failure-v1",
                "observed_utc": utc(), "pid": os.getpid(), "worker_id": args.worker_id,
                "error_type": type(error).__name__, "message": str(error),
                "automatic_retry": False, "original_records_overwritten": False,
                "task_failure_or_RNG_fabricated": False, "scientific_pass_claimed": False})
        except BaseException:
            print("DYNAMIC_FAILURE_JOURNAL_NOT_PUBLISHED", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
