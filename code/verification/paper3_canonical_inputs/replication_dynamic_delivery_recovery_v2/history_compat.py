"""Read-only compatibility for the three SHA-pinned legacy full worker requests.

This metadata adapter never imports an executor, model, NumPy, or statistics.
It does not manufacture a request field or a historical success.  The original
worker's optional-field semantics are retained only for identified legacy bytes.
The caller remains responsible for the original scientific integrity gate.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REQUEST_SCHEMA = "paper3-replication-worker-request-v1"
RESULT_NAME = "p7_7_integrity_replication_batch20_env_v3"
ISSUER_SHA = "33f687c4b4a9ecd25b2b7e4c891ed4a859c75e3a44a2eca9e8e31f765ad3d0c2"
WORKER_SHA = "c351d51f90f09358a607888a8db6f41fe2185ef819e18a5c5a3f9ca0aeff939c"
INITIAL_SHA = "18b329d5468d85961e28f24a1f45df9b2191530a9b26244642dbf6d2304e19dc"
LEGACY_REQUEST_SHA = {
    ("A_FULL_0001", "W1_request.json"): "369bc430268871a8e032a0a6f33a43d54e0ca3625246d4537f9bff3bf7f63e5b",
    ("A_FULL_0002", "W1_request.json"): "dd3a119f91c9526c941de9366c6def624722ca743f16f6910a1970834e4a5647",
    ("A_FULL_0002", "W2_request.json"): "0cbf82583bdca85075fbab965be1b1b9f34209f6620dc8c95062013878b4da4e",
}
LEGACY_PROCESS_SHA = {
    ("A_FULL_0001", "W1_request.json"): "fc873a16d56de5b628e36e9b37d416c9d85dbecc11b6e843c88abf676eac6c6a",
    ("A_FULL_0002", "W1_request.json"): "5cd165826c35c51e0ab4edd96da5312e73603c66e18d7972025fbe8461b6b3f0",
    ("A_FULL_0002", "W2_request.json"): "3c43b4ca01598905b6cb4e856ba2ab8a4cc95efd27d39f13c31fb158ca3ae4c5",
}
TASK_FIELDS = {"center_id", "seed", "scenario", "method", "config_id"}
METHODS = {
    "B0": "B0_Frozen_ratio10", "B1": "B1_AlwaysMaintainP50_ratio10",
    "B2": "B2_RAVM_ratio10", "B8": "B8_AlwaysOpen_ratio10",
    "P7.7": "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33",
}
REQUEST_FIELDS = {"schema", "manifest_digest", "mode", "worker_id", "attempt_id",
                  "worker_count", "tasks", "initial_state_manifest", "retries"}


class HistoryCompatibilityError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise HistoryCompatibilityError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def read(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, "duplicate metadata JSON key")
            out[key] = value
        return out
    def nonfinite(value):
        raise HistoryCompatibilityError("nonfinite metadata JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique, parse_constant=nonfinite)


def regular(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    require(path.is_relative_to(root), "metadata path escapes repository")
    for part in (path, *path.parents):
        require(not part.is_symlink(), "metadata symlink is prohibited")
        if part.exists():
            require(not getattr(part.lstat(), "st_file_attributes", 0) & 0x400,
                    "metadata reparse point is prohibited")
        if part == root:
            break
    require(path.is_file(), "required metadata file missing: " + str(path))
    return path.resolve()


def bound(path, digest, root, bindings):
    path = regular(path, root)
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
            and sha(path) == digest, "metadata SHA binding differs: " + str(path))
    prior = bindings.setdefault(str(path), digest)
    require(prior == digest, "metadata evidence changed during validation")
    return path


def task_stem(task):
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"


def validate_task(task, expected_names):
    require(isinstance(task, dict) and set(task) == TASK_FIELDS, "task requires exact five fields")
    require(type(task["center_id"]) is int and 33000 <= task["center_id"] <= 33019
            and type(task["seed"]) is int and task["seed"] in (7311, 7312, 7313),
            "task center/seed outside fixed protocol")
    require(task["scenario"] in ("C0", "C1", "C3", "C4")
            and METHODS.get(task["method"]) == task["config_id"], "task scenario/method/config differs")
    require(canonical(task) in expected_names, "task outside predeclared full task domain")


def validate_request(path, request, *, directory, manifest_digest, expected_names):
    """Validate real bytes and provenance; return metadata bindings, never outcomes.

    Missing performance_based_continuation is accepted only for the three exact
    recorded request AND process SHA pairs.  Explicit False remains the genuine
    original worker rule.  True, null, zero, and other values are all rejected.
    """
    directory, path = Path(directory).absolute(), Path(path).absolute()
    require(re.fullmatch(r"A_FULL_[0-9]{4}", directory.name)
            and directory.parent.name == "full" and directory.parent.parent.name == "execution",
            "static full request directory identity differs")
    results = directory.parent.parent.parent
    repo = results.parent.parent
    require(results.name == RESULT_NAME and results.parent.name == "results",
            "static request results identity differs")
    require(path.parent == directory and re.fullmatch(r"W[1-3]_request\.json", path.name),
            "worker request path/identity differs")
    evidence = {}
    path = regular(path, repo)
    require(read(path) == request, "supplied request differs from actual preserved JSON")
    require(isinstance(request, dict) and set(request) in
            (REQUEST_FIELDS, REQUEST_FIELDS | {"performance_based_continuation"}),
            "legacy worker request fields differ")
    require(request.get("schema") == REQUEST_SCHEMA
            and request.get("manifest_digest") == manifest_digest
            and request.get("attempt_id") == directory.name and request.get("mode") == "trajectory",
            "static full request binding differs")
    require(request.get("performance_based_continuation", False) is False,
            "outcome-based or nonboolean continuation is prohibited")
    worker_id = path.name.removesuffix("_request.json")
    require(request.get("worker_id") == worker_id and type(request.get("worker_count")) is int
            and 1 <= request["worker_count"] <= 3
            and int(worker_id[1:]) <= request["worker_count"], "request worker allocation differs")
    require(request.get("initial_state_manifest") == "initial_state_manifest.json",
            "initial certificate path differs")
    key = (directory.name, path.name)
    absent = "performance_based_continuation" not in request
    if absent:
        require(key in LEGACY_REQUEST_SHA, "missing optional flag is not an identified legacy request")
        bound(path, LEGACY_REQUEST_SHA[key], repo, evidence)
    else:
        evidence[str(path)] = sha(path)
    tasks = request.get("tasks")
    require(isinstance(tasks, list) and bool(tasks), "full request has no preassigned tasks")
    for task in tasks:
        validate_task(task, expected_names)
    names = [canonical(task) for task in tasks]
    require(len(names) == len(set(names)), "duplicate preassigned tasks")
    task_by_stem = {task_stem(task): task for task in tasks}

    manifest_path = regular(results / "provenance_manifest.json", repo)
    manifest = read(manifest_path)
    require(manifest.get("manifest_digest") == manifest_digest, "request manifest identity differs")
    require(Path(manifest["paths"]["repo"]).resolve() == repo.resolve()
            and Path(manifest["paths"]["results_root"]).resolve() == results.resolve(),
            "manifest repository/results paths differ")
    evidence[str(manifest_path)] = sha(manifest_path)
    base = repo / "verification/paper3_canonical_inputs"
    executor = base / "replication_executor_batch20_env_v3"
    pins = manifest.get("executor_sha256", {})
    require(pins.get("executor_driver.py") == ISSUER_SHA and pins.get("executor_worker.py") == WORKER_SHA,
            "original issuer/worker source pins differ")
    bound(executor / "executor_driver.py", ISSUER_SHA, repo, evidence)
    bound(executor / "executor_worker.py", WORKER_SHA, repo, evidence)
    launch = base / "autonomous_replication_execution_20261009_v3/phase_launches" / (
        "full_" + f"{int(directory.name[-4:]):03d}")
    bound(launch / "invoked_script_source_snapshot.py", ISSUER_SHA, repo, evidence)
    start_path = regular(launch / "start.json", repo)
    start = read(start_path)
    require(start.get("phase") == "full" and start.get("attempt") == int(directory.name[-4:])
            and start.get("workers") == request["worker_count"]
            and start.get("performance_based_continuation") is False
            and start.get("launch_source_sha256", {}).get(str(executor / "executor_driver.py")) == ISSUER_SHA,
            "historical phase launcher/source evidence differs")
    evidence[str(start_path)] = sha(start_path)
    bound(results / "initial_state_manifest.json", INITIAL_SHA, repo, evidence)

    process_path = path.with_name(worker_id + "_process.json")
    if absent:
        bound(process_path, LEGACY_PROCESS_SHA[key], repo, evidence)
    else:
        process_path = regular(process_path, repo)
        evidence[str(process_path)] = sha(process_path)
    process = read(process_path)
    require(process.get("request_sha256") == sha(path), "request/process SHA link differs")
    pycache = results / f"_never_created_pycache_full_{directory.name}_{worker_id}"
    expected_command = [manifest["environment"]["python_executable"], "-I", "-S", "-B", "-X",
        f"pycache_prefix={pycache}", str(executor / "executor_worker.py"), "--manifest",
        str(results / "provenance_manifest.json"), "--mode", "trajectory", "--request-file", str(path),
        "--worker-id", worker_id, "--attempt-id", directory.name]
    require(process.get("command") == expected_command, "original worker invocation differs")

    retries = request.get("retries")
    require(isinstance(retries, dict) and set(retries) <= set(task_by_stem), "retry outside assigned tasks")
    for stem, descriptor in retries.items():
        require(isinstance(descriptor, dict) and set(descriptor) ==
                {"failed_receipt_relative", "failed_receipt_sha256"}, "retry descriptor fields differ")
        relative = Path(descriptor["failed_receipt_relative"])
        require(not relative.is_absolute() and ".." not in relative.parts
                and relative.parts[0] == "attempts" and relative.parts[1] == stem,
                "retry failed receipt path differs")
        failed_path = bound(results / relative, descriptor["failed_receipt_sha256"], repo, evidence)
        failed = read(failed_path)
        require(failed.get("schema") == "paper3-batch20-failed-task-receipt-v1"
                and failed.get("manifest_digest") == manifest_digest
                and failed.get("task") == task_by_stem[stem]
                and failed.get("status") in ("FAILED", "INTERRUPTED")
                and failed.get("completed_valid") is False, "retry is not exact incomplete same-task failure")
        if failed.get("rng_relative") is None:
            require(failed.get("failed_before_rng_capture") is True,
                    "retry without captured RNG lacks certified pre-run boundary")
        else:
            rng_relative = Path(failed["rng_relative"])
            require(not rng_relative.is_absolute() and ".." not in rng_relative.parts
                    and rng_relative.parent == relative.parent, "retry RNG path differs")
            rng = read(bound(results / rng_relative, failed.get("rng_file_sha256"), repo, evidence))
            require(rng.get("bindings", {}).get("task") == task_by_stem[stem]
                    and rng.get("bindings", {}).get("input_bundle_digest") == manifest.get("input_bundle_digest")
                    and rng.get("manual_seed_called") is False
                    and rng.get("state_digest") == canonical({k: v for k, v in rng.items() if k != "state_digest"}),
                    "retry captured RNG metadata differs")
    return {"request_sha256": sha(path), "worker_id": worker_id, "task_count": len(tasks),
            "missing_optional_flag_accepted_as_original_worker_default": absent,
            "source_and_evidence_sha256": evidence, "outcomes_read": False,
            "requests_modified": False}


def full_history(s, plan, c, p, bindings, manifest, expected_tasks, certificate):
    """Original full_history logic with strict legacy request compatibility only."""
    cert = s.read(certificate)
    s.require(cert.get("schema") == "paper3-dynamic-full-integrity-certificate-v1"
              and cert.get("status") == "PASS" and cert.get("dynamic_attempt_id") == c["attempt_id"],
              "independent dynamic full certificate absent")
    for n, h in cert["evidence_sha256"].items():
        s.bound(n, h)
        prior = bindings.setdefault(n, h)
        s.require(prior == h, "certificate binding changed during history validation")
    for path in (Path(certificate), Path(plan["_plan_path"]), s.RESULTS / "full_experiment_integrity_gate.json"):
        bindings[str(path)] = s.sha(path)
    publication_path = Path(certificate).parent / "FULL_GATE_PUBLICATION.json"
    publication = s.read(publication_path)
    s.bound(certificate, publication["certificate_sha256"])
    s.bound(s.RESULTS / "full_experiment_integrity_gate.json", publication["sha256"])
    bindings[str(publication_path)] = s.sha(publication_path)
    expected = {s.canonical(task) for task in expected_tasks}
    s.require(len(expected) == len(expected_tasks), "duplicate expected full task")
    seen, attempts, compatibility = set(), [], []
    for directory in sorted((s.RESULTS / "execution/full").iterdir()):
        s.require(directory.is_dir() and re.fullmatch(r"A_FULL_[0-9]{4}", directory.name),
                  "static full history identity differs")
        for path in directory.rglob("*"):
            if path.is_file():
                regular_path = p.regular_path(path)
                h = p.file_sha256(path)
                prior = bindings.setdefault(str(regular_path), h)
                s.require(prior == h, "static full evidence changed during history validation")
        tasks = []
        for path in sorted(directory.glob("W*_request.json")):
            request = s.read(path)
            validated = validate_request(path, request, directory=directory,
                manifest_digest=s.MANIFEST, expected_names=expected)
            for n, h in validated["source_and_evidence_sha256"].items():
                prior = bindings.setdefault(n, h)
                s.require(prior == h, "request provenance differs from prior binding")
            compatibility.append({"path": str(path), **{k: v for k, v in validated.items()
                                    if k != "source_and_evidence_sha256"}})
            tasks.extend(request["tasks"])
        names = [s.canonical(task) for task in tasks]
        s.require(tasks and len(names) == len(set(names)) and set(names) <= expected,
                  "static requested population differs")
        seen.update(names)
        completion, failure = directory / "completion.json", directory / "failure.json"
        s.require(not (completion.exists() and failure.exists()), "static terminal ambiguous")
        status = "INTERRUPTED_BY_CERTIFIED_DYNAMIC_TAKEOVER"
        if completion.exists() or failure.exists():
            value = s.read(completion if completion.exists() else failure)
            s.require(value.get("manifest_digest") == s.MANIFEST
                      and value.get("attempt_id") == directory.name and value.get("phase") == "full",
                      "static terminal identity differs")
            status = "ORIGINAL_STATIC_COMPLETION_PRESERVED" if completion.exists() else "ORIGINAL_STATIC_FAILURE_PRESERVED"
        attempts.append({"attempt_id": directory.name, "requested_tasks": len(tasks),
                         "status": status, "claimed_dynamic_success": False})
    s.require(seen == expected, "preserved static full requests did not cover original 1195-task domain")
    return {"phase": "full", "attempt_count": len(attempts) + 1, "preserved_static_attempts": attempts,
            "last_attempt_id": c["attempt_id"], "phase_complete": True,
            "terminal_schema": "paper3-dynamic-full-integrity-certificate-v1",
            "unique_predeclared_tasks": len(expected), "retained_tasks": cert["retained_tasks"],
            "completed_dynamic_tasks": cert["completed_dynamic_tasks"], "end_integrity_pass": True,
            "old_static_success_fabricated": False, "legacy_request_compatibility": compatibility}


def real_request_preflight(repo):
    """Optional read-only preflight; reads only request/provenance metadata."""
    repo = Path(repo).resolve()
    results = repo / "results" / RESULT_NAME
    tasks = [{"center_id": center, "seed": seed, "scenario": scenario,
              "method": method, "config_id": config}
             for center in range(33000, 33020) for seed in (7311, 7312, 7313)
             for scenario in ("C0", "C1", "C3", "C4") for method, config in METHODS.items()]
    manifest = read(results / "provenance_manifest.json")
    expected = {canonical(task) for task in tasks[5:]}
    out = []
    for attempt, name in LEGACY_REQUEST_SHA:
        path = results / "execution/full" / attempt / name
        out.append(validate_request(path, read(path), directory=path.parent,
            manifest_digest=manifest["manifest_digest"], expected_names=expected))
    return {"status": "LEGACY_REQUEST_METADATA_PREFLIGHT_PASS", "requests": out,
            "models_or_statistics_executed": False, "files_modified": False}
