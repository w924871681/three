"""P7.6B prospective runner. P7.6B-0 never opens scientific outcomes.

The scientific trajectory is the frozen P7.4B implementation; only its
dispatch, selected-center loading, checkpointing, and artifact namespace differ.
Real Fit/Validation requires a later, separately Git-bound human authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.common import sha256_file

ASSIGNMENT = ROOT / "configs/P7_6B_CENTER_ASSIGNMENT.json"
PROTOCOL = ROOT / "configs/P7_6B_FROZEN_PROTOCOL.json"
EXECUTION_CONFIG = ROOT / "configs/P7_6B_EXECUTION_CONFIG.json"
RESOURCE_DOWNSCALE = ROOT / "audits/P7_6B_RESOURCE_DOWNSCALE.json"
AUTHORIZATION = ROOT / "audits/P7_6B_EXECUTION_AUTHORIZATION.json"
R0_LOCK = ROOT / "audits/P7_6B_FIT_R0_RECOVERY_LOCK.json"
R0_RELEASE = ROOT / "audits/P7_6B_FIT_R0_RECOVERY_RELEASE.json"
FIT_FREEZE = ROOT / "audits/P7_6B_FIT_FREEZE.json"
VALIDATION_OPENING = ROOT / "audits/P7_6B_VALIDATION_OPENING.json"
RESULTS = ROOT / "results/p7_6b"
SCENARIOS = ("C0", "C1", "C3", "C4")
ASSIGNMENT_SHA = "172c694057fea9926fecabe800538a5f8ff5bddf8880c078dd457b705b53fb95"
PROTOCOL_SHA = "86272adb9a335ff72030cc4ba5c1fbc5f52e543eacd58ba032433e590251ee23"


@dataclass(frozen=True, order=True)
class Task:
    center_id: int
    model_seed: int
    scenario: str
    protocol_sha256: str
    generator_sha256: str
    behavior_sha256: str

    @property
    def key(self) -> str:
        return f"{self.center_id}_{self.model_seed}_{self.scenario}"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_bound(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    try:
        head = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
    except subprocess.CalledProcessError:
        return False
    return hashlib.sha256(head).hexdigest() == sha256_file(path)


def assert_digest(path: Path, expected: str, *, bound: bool = True) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise RuntimeError(f"frozen SHA-256 mismatch: {path}")
    if bound and not git_bound(path):
        raise RuntimeError(f"file not Git-bound at HEAD: {path}")


def deny_center(center_id: int) -> None:
    if 33000 <= center_id <= 33019:
        raise RuntimeError("final heldout center hard-denied")


def deny_mode(mode: str) -> None:
    if mode.lower().replace("_", "-") in {"final-heldout", "alibaba", "p8"}:
        raise RuntimeError(f"mode hard-denied: {mode}")


def validate_assignment(assignment: dict, protocol: dict) -> None:
    assert protocol["center_design"]["total"] == 72
    pools = assignment["pools"]
    fit, val = list(map(int, pools["ReplicationFit"])), list(map(int, pools["ReplicationValidation"]))
    assert len(fit) == len(val) == 36 and len(set(fit) | set(val)) == 72
    assert not set(fit) & set(val)
    assert sorted(fit + val) == sorted(map(int, assignment["center_ids"]))
    assert all(32248 <= x <= 32631 for x in fit + val)
    for center in fit + val:
        deny_center(center)
    rows = assignment["centers"]
    assert len(rows) == 72 and {int(x["center_id"]) for x in rows} == set(fit + val)
    for pool, ids in (("ReplicationFit", fit), ("ReplicationValidation", val)):
        selected = [x for x in rows if x["pool"] == pool]
        assert {int(x["center_id"]) for x in selected} == set(ids)
        strata = Counter((x["center_type"], x["deployment_tier"]) for x in selected)
        assert len(strata) == 9 and set(strata.values()) == {4}
    folds = assignment["fit_center_group_folds"]
    assert len(folds) == 4 and {int(x["fold"]) for x in folds} == set(range(4))
    heldout = []
    type_tier = {int(x["center_id"]): (x["center_type"], x["deployment_tier"]) for x in rows}
    for fold in folds:
        ids = list(map(int, fold["validation_centers"]))
        assert len(ids) == 9 and fold["training_center_count"] == 27
        assert len({type_tier[x] for x in ids}) == 9
        heldout += ids
    assert len(heldout) == len(set(heldout)) == 36 and set(heldout) == set(fit)
    assert assignment["random_stage_split_forbidden"] is True
    assert assignment["outcome_dependent_assignment"] is False


def preflight(*, phase: str = "preflight", require_opening: bool = False) -> tuple[dict, dict]:
    deny_mode(phase)
    assert_digest(ASSIGNMENT, ASSIGNMENT_SHA)
    assert_digest(PROTOCOL, PROTOCOL_SHA)
    assignment, protocol = read_json(ASSIGNMENT), read_json(PROTOCOL)
    validate_assignment(assignment, protocol)
    assert protocol["authorization"]["p7_6b_execution"] is False
    assert protocol["common_behavior"]["A0_A1_observational_only"] is True
    assert protocol["common_behavior"]["delta_R"] == -0.000272181217042075
    assert protocol["common_behavior"]["cost_ratio"] == 10
    assert protocol["common_design"]["model_seeds"] == [7311, 7312, 7313]
    assert protocol["common_design"]["scenarios"] == list(SCENARIOS)
    assert protocol["common_design"]["stages"] == 24
    for rel, expected in protocol["source_bindings_sha256"].items():
        assert_digest(ROOT / rel, expected)
    from scripts.p7_6a_1_metadata_replay import metadata_stream
    stream = {x["center_id"]: x for x in metadata_stream(32248, 384, 7311)}
    for row in assignment["centers"]:
        meta = stream[int(row["center_id"])]
        assert (meta["center_type"], meta["deployment_tier"]) == (row["center_type"], row["deployment_tier"])
    if require_opening:
        verify_opening()
    return assignment, protocol


def require_execution_authorization(phase: str) -> dict:
    """Separate post-P7.6B-0 approval; a CLI flag alone never authorizes outcomes."""
    if not AUTHORIZATION.is_file() or not git_bound(AUTHORIZATION):
        raise RuntimeError("P7.6B scientific execution NOT authorized; separate Git-bound human authorization required")
    value = read_json(AUTHORIZATION)
    if value.get("status") != "HUMAN_AUTHORIZED_P7_6B_EXECUTION":
        raise RuntimeError("P7.6B authorization status invalid")
    if value.get("protocol_sha256") != PROTOCOL_SHA or value.get("assignment_sha256") != ASSIGNMENT_SHA:
        raise RuntimeError("P7.6B authorization bindings invalid")
    if phase not in value.get("authorized_phases", []):
        raise RuntimeError(f"P7.6B {phase} not separately authorized")
    return value


def require_r0_fit_release() -> None:
    """The prior Fit authorization cannot reopen outcomes during R0 review."""
    if not R0_LOCK.is_file() or not git_bound(R0_LOCK):
        raise RuntimeError("P7.6B formal Fit locked; R0 recovery lock missing or unbound")
    lock = read_json(R0_LOCK)
    if lock.get("status") != "R0_TEST_ONLY_FORMAL_FIT_LOCKED":
        raise RuntimeError("P7.6B formal Fit locked; invalid R0 lock")
    if not R0_RELEASE.is_file() or not git_bound(R0_RELEASE):
        raise RuntimeError("P7.6B formal Fit locked pending separate human R0 recovery review")
    release = read_json(R0_RELEASE)
    if not (release.get("status") == "HUMAN_AUTHORIZED_P7_6B_FIT_RECOVERY" and
            release.get("r0_lock_sha256") == sha256_file(R0_LOCK) and
            release.get("fit_recovery_authorized") is True and
            release.get("validation_authorized") is False):
        raise RuntimeError("P7.6B formal Fit locked; invalid separate recovery release")


def canonical_tasks(assignment: dict, phase: str) -> list[Task]:
    pool = {"fit": "ReplicationFit", "validation": "ReplicationValidation"}[phase]
    frozen = read_json(ROOT / "configs/p3_mismatch_v2_frozen.json")
    behavior = read_json(ROOT / "configs/p7_2_selected_action_params.json")
    seeds = frozen["model_seeds"]
    scenarios = frozen["scenarios"]
    assert seeds == [7311, 7312, 7313] and scenarios == list(SCENARIOS)
    assert behavior["selected"]["config"]["delta_R"] == -0.000272181217042075
    return [Task(c, s, scenario, PROTOCOL_SHA,
                 sha256_file(ROOT / "configs/p3_mismatch_v2_frozen.json"),
                 sha256_file(ROOT / "configs/p7_2_selected_action_params.json"))
            for c in sorted(map(int, assignment["pools"][pool]))
            for s in seeds for scenario in SCENARIOS]


def output_paths(phase: str, task: Task) -> tuple[Path, Path, Path, Path]:
    base = RESULTS / "raw" / phase / task.key
    return base.with_suffix(".csv"), base.with_suffix(".scales.csv"), base.with_suffix(".integrity.json"), base.with_suffix(".claim")


def task_state_path(phase: str, task: Task) -> Path:
    return RESULTS / "task_states" / phase / f"{task.key}.json"


def failure_path(phase: str, task: Task) -> Path:
    return RESULTS / "failures" / phase / f"{task.key}.json"


def write_task_state(phase: str, task: Task, status: str, **details) -> None:
    atomic_json(task_state_path(phase, task), {
        "trajectory_id": task.key, "center_id": task.center_id,
        "seed": task.model_seed, "scenario": task.scenario,
        "status": status, "worker_pid": details.pop("worker_pid", None),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(), **details})


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def validate_receipt(phase: str, task: Task, runtime_sha: str) -> bool:
    csv_path, scales_path, receipt_path, _ = output_paths(phase, task)
    present = [x.exists() for x in (csv_path, scales_path, receipt_path)]
    if not any(present):
        return False
    if not all(present):
        raise RuntimeError(f"incomplete trajectory, not resumable as complete: {task.key}")
    r = read_json(receipt_path)
    expected = {"trajectory_id": task.key, "center_id": task.center_id, "model_seed": task.model_seed,
                "scenario": task.scenario, "protocol_sha256": task.protocol_sha256,
                "generator_sha256": task.generator_sha256, "behavior_sha256": task.behavior_sha256,
                "runtime_config_sha256": runtime_sha, "status": "COMPLETE", "rows": 24,
                "all_stage_path_matches": True}
    if any(r.get(k) != v for k, v in expected.items()):
        raise RuntimeError(f"receipt binding mismatch: {task.key}")
    if sha256_file(csv_path) != r.get("trajectory_sha256") or sha256_file(scales_path) != r.get("scales_sha256"):
        raise RuntimeError(f"receipt artifact SHA mismatch: {task.key}")
    return True


def verify_opening() -> None:
    for path in (FIT_FREEZE, VALIDATION_OPENING):
        if not path.is_file() or not path.with_suffix(".sha256").is_file():
            raise RuntimeError(f"Validation locked; missing {path.name}")
        if sha256_file(path) != path.with_suffix(".sha256").read_text(encoding="utf-8").strip():
            raise RuntimeError(f"Validation locked; invalid {path.name} hash")
        if not git_bound(path) or not git_bound(path.with_suffix(".sha256")):
            raise RuntimeError(f"Validation locked; uncommitted {path.name}")
    freeze, opening = read_json(FIT_FREEZE), read_json(VALIDATION_OPENING)
    if opening.get("validation_open_authorized") is not True or opening.get("fit_freeze_sha256") != sha256_file(FIT_FREEZE):
        raise RuntimeError("Validation locked; Fit freeze/opening linkage invalid")
    mandatory = ("artifacts/p7_6b_A0_scaler.json", "artifacts/p7_6b_A1_scaler.json",
                 "artifacts/p7_6b_A0_estimator.pt", "artifacts/p7_6b_A1_estimator.pt",
                 "results/p7_6b/fit_oof_predictions.csv", "results/p7_6b/fit_metrics.csv",
                 "scripts/run_p7_6b.py", "configs/P7_6B_FROZEN_PROTOCOL.json",
                 "configs/P7_6B_EXECUTION_CONFIG.json")
    files = freeze.get("files", {})
    if not all(rel in files for rel in mandatory):
        raise RuntimeError("Validation locked; Fit freeze missing required binding")
    for rel, expected in files.items():
        assert_digest(ROOT / rel, expected, bound=not rel.startswith("results/p7_6b/raw/"))
    for rel in mandatory:
        if opening.get("files", {}).get(rel) != files[rel]:
            raise RuntimeError("Validation locked; opening binding mismatch")


def _worker_init(device: str, threads: int) -> None:
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import torch
    torch.set_num_threads(threads)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    try:
        torch.use_deterministic_algorithms(True)
    except RuntimeError as exc:
        raise RuntimeError(f"device cannot guarantee deterministic algorithms: {exc}") from exc
    from scripts import run_p7_4b as p7b
    p7b.install_seed_binding()
    install_p6_attribute_provenance_compatibility()
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")


def install_p6_attribute_provenance_compatibility() -> None:
    """Validate the exact post-P6 Git-attribute extension without changing P6.

    P6 froze the old .gitattributes bytes. A later test-output byte-preservation
    rule appended two lines. The P6 estimator's check is allowed to see its
    original hash only after both historical bytes and the exact append are
    independently verified. All other P6 manifest checks remain untouched.
    """
    from core import p7 as p7core

    path = ROOT / ".gitattributes"
    manifest = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
    expected = manifest["files"][".gitattributes"]
    historic = subprocess.check_output(["git", "show", "9622819^:.gitattributes"], cwd=ROOT)
    suffix = (b"# Qualification manifests bind exact test-only bytes, including monitor CRLF logs.\n"
              b"results/p7_6b_qualification/** -text\n")
    if hashlib.sha256(historic).hexdigest() != expected or path.read_bytes() != historic + suffix:
        raise RuntimeError("P6 .gitattributes provenance extension differs from exact audited bytes")
    original_sha256 = p7core.sha256_file
    resolved = path.resolve()

    def checked_sha256(candidate: Path) -> str:
        if Path(candidate).resolve() == resolved:
            if path.read_bytes() != historic + suffix:
                raise RuntimeError("P6 .gitattributes provenance changed during execution")
            return expected
        return original_sha256(candidate)

    p7core.sha256_file = checked_sha256


def _trajectory_worker(phase: str, task: Task, runtime_sha: str) -> str:
    import pandas as pd
    from core.p7_6b_selected_data import selected_base_centers
    from core import p7 as p7core
    from scripts import run_p7_4b as p7b
    from scripts import run_p7 as p7runner
    csv_path, scales_path, receipt_path, claim_path = output_paths(phase, task)
    if validate_receipt(phase, task, runtime_sha):
        return task.key
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"duplicate/stale trajectory claim: {task.key}") from exc
    progress = {"phase": "claim_created", "stage_entered": None, "stage_completed": None}
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
            handle.flush(); os.fsync(handle.fileno())
        write_task_state(phase, task, "RUNNING", worker_pid=os.getpid(),
                         last_confirmed_phase=progress["phase"])
        progress["phase"] = "preflight"
        assignment, protocol = preflight(phase=phase, require_opening=(phase == "validation"))
        allowed = assignment["pools"]["ReplicationFit" if phase == "fit" else "ReplicationValidation"]
        if task.center_id not in allowed:
            raise RuntimeError("task center outside authorized pool")
        stream = assignment["candidate_stream"]
        base = selected_base_centers(start=stream["start"], count=stream["count"],
                                     selected_ids=[task.center_id], data_seed=stream["data_seed"])[0]
        expected = next(x for x in assignment["centers"] if x["center_id"] == task.center_id)
        if (base.center_type, base.budget_tier) != (expected["center_type"], expected["deployment_tier"]):
            raise RuntimeError("generated center metadata disagrees with frozen assignment")
        progress["phase"] = "generator_initialized"
        frozen = read_json(ROOT / "configs/p3_mismatch_v2_frozen.json")
        identities = p7b.bank(frozen)
        incumbent = next(x for x in identities if x.identity_id == "msa_a57_pt")
        ref_path = RESULTS / "references" / phase / f"{task.center_id}_{task.model_seed}.json"
        if ref_path.exists():
            ref = read_json(ref_path)
        else:
            ref = p7runner.reference(base, task.model_seed, incumbent, frozen)
            atomic_json(ref_path, ref)
        progress["phase"] = "causal_reference_available"
        original_step = p7core.DecisionExecutor.step_group

        def observed_step(self, states, stage, update, assessment):
            progress["phase"] = "stage_decision_entered"
            progress["stage_entered"] = int(stage)
            result = original_step(self, states, stage, update, assessment)
            progress["phase"] = "stage_decision_completed"
            progress["stage_completed"] = int(stage)
            return result

        p7core.DecisionExecutor.step_group = observed_step
        try:
            progress["phase"] = "trajectory_entered"
            frame, scales = p7b.run_trajectory(base, task.model_seed, task.scenario, frozen,
                                                read_json(ROOT / "configs/p7_protocol.json"), identities,
                                                float(ref["tau_service"]))
        finally:
            p7core.DecisionExecutor.step_group = original_step
        progress["phase"] = "trajectory_complete"
        frame["A0_parent_identity"] = frame["identity_before"]
        frame["A1_parent_identity"] = frame["identity_before"]
        frame["A0_RI"] = frame["action"].eq("ri")
        frame["A1_RI"] = frame["action"].eq("ri")
        if len(frame) != 24 or not frame.behavior_path_match.astype(bool).all():
            raise RuntimeError("mandatory 24-stage paired behavior-path equality failed")
        for lhs, rhs in (("A0_parent_identity", "A1_parent_identity"),
                         ("A0_parent_state_hash", "A1_parent_state_hash"),
                         ("A0_action", "A1_action"),
                         ("A0_RI", "A1_RI"),
                         ("A0_post_action_identity", "A1_post_action_identity"),
                         ("A0_post_action_path_hash", "A1_post_action_path_hash")):
            if not frame[lhs].astype(str).equals(frame[rhs].astype(str)):
                raise RuntimeError(f"mandatory paired behavior divergence: {lhs}")
        frame["pool"] = phase
        scales["pool"] = phase
        def csv_bytes(data: pd.DataFrame) -> bytes:
            return data.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")
        atomic_bytes(csv_path, csv_bytes(frame))
        progress["phase"] = "trajectory_csv_written"
        atomic_bytes(scales_path, csv_bytes(scales))
        progress["phase"] = "scales_csv_written"
        receipt = {"schema": "p7.6b-paired-trajectory-integrity-v1", "trajectory_id": task.key,
                   "center_id": task.center_id, "model_seed": task.model_seed, "scenario": task.scenario,
                   "protocol_sha256": task.protocol_sha256, "generator_sha256": task.generator_sha256,
                   "behavior_sha256": task.behavior_sha256, "runtime_config_sha256": runtime_sha,
                   "implementation_sha256": sha256_file(Path(__file__)), "status": "COMPLETE", "rows": 24,
                   "all_stage_path_matches": True, "trajectory_sha256": sha256_file(csv_path),
                   "scales_sha256": sha256_file(scales_path)}
        atomic_json(receipt_path, receipt)
        progress["phase"] = "integrity_receipt_written"
        validate_receipt(phase, task, runtime_sha)
        write_task_state(phase, task, "COMPLETE", worker_pid=os.getpid(),
                         last_confirmed_phase="receipt_validated", stage_completed=24)
        return task.key
    except BaseException as exc:
        cuda = {"available": False}
        try:
            import torch
            if torch.cuda.is_available():
                cuda = {"available": True, "allocated_bytes": torch.cuda.memory_allocated(),
                        "reserved_bytes": torch.cuda.memory_reserved(),
                        "max_allocated_bytes": torch.cuda.max_memory_allocated()}
        except BaseException as gpu_exc:
            cuda = {"available": None, "telemetry_error": type(gpu_exc).__name__}
        failure = {"trajectory_id": task.key, "center_id": task.center_id,
                   "seed": task.model_seed, "scenario": task.scenario,
                   "worker_pid": os.getpid(), "exception_class": type(exc).__name__,
                   "exception_message": str(exc), "traceback": traceback.format_exc(),
                   "last_confirmed_phase": progress["phase"],
                   "stage_entered": progress["stage_entered"],
                   "stage_completed": progress["stage_completed"],
                   "cuda_memory": cuda, "status": "FAILED"}
        try:
            if not failure_path(phase, task).exists():
                atomic_json(failure_path(phase, task), failure)
            write_task_state(phase, task, "FAILED", worker_pid=os.getpid(),
                             last_confirmed_phase=progress["phase"],
                             stage_entered=progress["stage_entered"],
                             stage_completed=progress["stage_completed"])
        except BaseException:
            # Preserve the original exception for the coordinator fallback.
            pass
        raise
    finally:
        # A crash leaves a claim, requiring an explicit audited recovery.
        if receipt_path.exists() and claim_path.exists():
            claim_path.unlink()


def run_phase(phase: str, workers: int, device: str, resume: bool, dry_run: bool) -> None:
    assignment, _ = preflight(phase=phase, require_opening=(phase == "validation"))
    tasks = canonical_tasks(assignment, phase)
    if len(tasks) != 432:
        raise RuntimeError("frozen phase must contain exactly 432 shared trajectories")
    if dry_run:
        print(json.dumps({"phase": phase, "tasks": len(tasks), "first": tasks[0].key,
                          "last": tasks[-1].key, "scientific_outcomes_generated": False}))
        return
    if phase == "fit":
        require_r0_fit_release()
    require_execution_authorization(phase)
    if not EXECUTION_CONFIG.is_file() or not git_bound(EXECUTION_CONFIG):
        raise RuntimeError("frozen execution configuration unavailable")
    runtime = read_json(EXECUTION_CONFIG)
    if device != runtime["EXECUTION_DEVICE"]:
        raise RuntimeError("requested runtime differs from frozen benchmark selection")
    if workers != runtime["EXECUTION_WORKERS"]:
        if not (isinstance(runtime["EXECUTION_WORKERS"], int) and
                1 <= workers < runtime["EXECUTION_WORKERS"] and
                RESOURCE_DOWNSCALE.is_file() and git_bound(RESOURCE_DOWNSCALE)):
            raise RuntimeError("worker count outside frozen runtime; reduction needs Git-bound safety record")
        change = read_json(RESOURCE_DOWNSCALE)
        if not (change.get("status") == "SAFETY_DOWNSCALE_ONLY" and
                change.get("original_config_sha256") == sha256_file(EXECUTION_CONFIG) and
                change.get("workers") == workers and
                change.get("reason") and change.get("no_scientific_change") is True):
            raise RuntimeError("invalid worker safety-downscale record")
    runtime_sha = sha256_file(EXECUTION_CONFIG)
    completed = 0
    pending = []
    for task in tasks:
        _, _, receipt, claim = output_paths(phase, task)
        if claim.exists() or failure_path(phase, task).exists():
            raise RuntimeError(f"audited recovery required for stale claim/failure: {task.key}")
        if task_state_path(phase, task).exists() and not receipt.exists():
            state = read_json(task_state_path(phase, task))
            if state.get("status") != "INTERRUPTED":
                raise RuntimeError(f"audited recovery required for incomplete task state: {task.key}")
        if validate_receipt(phase, task, runtime_sha):
            if not resume:
                raise RuntimeError("existing result requires --resume")
            completed += 1
        else:
            pending.append(task)
    threads = int(runtime["TORCH_NUM_THREADS"])
    dispatch_pending(phase, pending, workers, device, runtime_sha, completed,
                     len(tasks), initializer=_worker_init, initargs=(device, threads))


def dispatch_pending(phase: str, pending: list[Task], workers: int, device: str,
                     runtime_sha: str, completed: int, total: int, *, initializer,
                     initargs: tuple) -> None:
    """Bounded, fail-fast trajectory scheduler; test-only harness uses this too."""
    initial_completed = completed
    start = time.monotonic()
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"),
                               initializer=initializer, initargs=initargs)
    active = {}
    submitted = []
    pending_iter = iter(pending)
    clean_exit = False

    def submit_one() -> bool:
        try:
            task = next(pending_iter)
        except StopIteration:
            return False
        write_task_state(phase, task, "QUEUED", last_confirmed_phase="submitted_to_pool")
        submitted.append(task)
        active[pool.submit(_trajectory_worker, phase, task, runtime_sha)] = task
        return True

    try:
        for _ in range(min(workers, len(pending))):
            submit_one()
        while active:
            done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
            for future in done:
                task = active.pop(future)
                try:
                    future.result()
                except BaseException as exc:
                    path = failure_path(phase, task)
                    if not path.exists():
                        atomic_json(path, {"trajectory_id": task.key,
                            "center_id": task.center_id, "seed": task.model_seed,
                            "scenario": task.scenario, "worker_pid": None,
                            "exception_class": type(exc).__name__,
                            "exception_message": str(exc),
                            "traceback": "".join(traceback.format_exception(
                                type(exc), exc, exc.__traceback__)),
                            "last_confirmed_phase": "worker_record_unavailable",
                            "stage_entered": None, "stage_completed": None,
                            "cuda_memory": {"available": None}, "status": "FAILED"})
                    recorded = read_json(path)
                    write_task_state(phase, task, "FAILED",
                                     worker_pid=recorded.get("worker_pid"),
                                     last_confirmed_phase=recorded.get("last_confirmed_phase"),
                                     stage_entered=recorded.get("stage_entered"),
                                     stage_completed=recorded.get("stage_completed"))
                    atomic_json(RESULTS / f"{phase}_execution_status.json", {
                        "phase": phase, "completed": completed, "total": total,
                        "workers": workers, "device": device, "valid_failures": 1,
                        "failed_trajectory": task.key, "status": "STOPPED_ON_FIRST_FAILURE"})
                    print(json.dumps({"event": "trajectory_failed", "trajectory_id": task.key,
                                      "failure_record": str(path)}), flush=True)
                    raise RuntimeError(f"trajectory {task.key} failed; attempt=1; no scientific retry; "
                                       f"failure captured at {path}") from exc
                completed += 1
                elapsed = max(time.monotonic() - start, 1e-9)
                rate = (completed - initial_completed) * 3600 / elapsed
                status = {"phase": phase, "completed": completed, "total": total,
                          "remaining": total - completed, "workers": workers, "device": device,
                          "throughput_trajectories_per_hour": rate,
                          "eta_hours": (total - completed) / rate if rate else None,
                          "valid_failures": 0}
                atomic_json(RESULTS / f"{phase}_execution_status.json", status)
                print(json.dumps(status), flush=True)
                submit_one()
        clean_exit = True
    finally:
        if not clean_exit:
            # Only processes owned by this exact pool are stopped. A bounded
            # submission window prevents more tasks starting after failure.
            children = list((getattr(pool, "_processes", None) or {}).values())
            for child in children:
                if child.is_alive():
                    child.terminate()
            for child in children:
                child.join(timeout=5)
                if child.is_alive():
                    child.kill()
                    child.join(timeout=5)
            for task in submitted:
                _, _, receipt, claim = output_paths(phase, task)
                if receipt.exists():
                    try:
                        valid = validate_receipt(phase, task, runtime_sha)
                    except BaseException:
                        valid = False
                    if valid:
                        write_task_state(phase, task, "COMPLETE",
                                         last_confirmed_phase="receipt_validated_after_pool_stop",
                                         stale_claim_requires_audit=claim.exists())
                        continue
                if failure_path(phase, task).exists():
                    recorded = read_json(failure_path(phase, task))
                    write_task_state(phase, task, "FAILED",
                                     worker_pid=recorded.get("worker_pid"),
                                     last_confirmed_phase=recorded.get("last_confirmed_phase"),
                                     stage_entered=recorded.get("stage_entered"),
                                     stage_completed=recorded.get("stage_completed"))
                else:
                    claimed_pid = None
                    if claim.exists():
                        try:
                            claimed_pid = int(claim.read_text(encoding="utf-8").strip())
                        except (OSError, ValueError):
                            pass
                    write_task_state(phase, task, "INTERRUPTED",
                                     worker_pid=claimed_pid,
                                     last_confirmed_phase="peer_failure_pool_stop")
        pool.shutdown(wait=True, cancel_futures=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("preflight", "fit", "fit-freeze", "open-validation", "validation", "finalize", "benchmark"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.benchmark or args.phase == "benchmark":
        from scripts.p7_6b_benchmark import run_benchmark
        run_benchmark(args.workers, args.device)
    elif args.phase == "preflight":
        preflight()
        print("P7_6B_PRE_OUTCOME_PREFLIGHT_PASS")
    elif args.phase in ("fit", "validation"):
        run_phase(args.phase, args.workers, args.device, args.resume, args.dry_run)
    else:
        require_execution_authorization(args.phase)
        from scripts import p7_6b_science
        if args.phase == "fit-freeze":
            p7_6b_science.fit_freeze()
        elif args.phase == "open-validation":
            p7_6b_science.open_validation()
        else:
            p7_6b_science.finalize()


if __name__ == "__main__":
    main()
