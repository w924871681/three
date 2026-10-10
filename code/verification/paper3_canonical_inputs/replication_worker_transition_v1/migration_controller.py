"""Explicit, outcome-blind 1 -> 2 worker interruption and provenance bridge.

No model, generator, training, optimizer, statistical or experiment module is
executed here.  The frozen coordinator is imported only for its read-only
saved-record verifier.  Real process actions require the explicit CLI switch;
the default command is a read-only preflight.  Termination is irreversible.
Any error before the first termination resumes both suspended processes.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
from datetime import datetime, timezone

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v3"
EXECUTOR = REPO / "verification/paper3_canonical_inputs/replication_executor_batch20_env_v3"
MANIFEST_DIGEST = "7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
INPUT_DIGEST = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
ROOT_SHA = "f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8"
OLD_ATTEMPT = "A_FULL_0001"
NEW_ATTEMPT = "A_FULL_0002"
GIB = 1024 ** 3
EXPECTED_PROCESSES = (
    {"pid": 36468, "created_utc": "2026-10-09T09:48:15.556295+00:00", "creation_filetime": 134360128955562955, "role": "worker_base",
     "image": r"C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe"},
    {"pid": 26012, "created_utc": "2026-10-09T09:48:15.514040+00:00", "creation_filetime": 134360128955140400, "role": "worker_wrapper",
     "image": str(REPO / "verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/P7_7_REPLICATION_MODEL_ENV_V1/Scripts/python.exe")},
)


class MigrationError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise MigrationError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def regular(path, *, exists=True):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(not item.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                    f"Reparse/symlink path forbidden: {item}")
    return path.resolve(strict=exists)


def checked(root, relative, *, exists=True):
    root = regular(root)
    require(isinstance(relative, str) and relative and "\\" not in relative, "POSIX relative path required")
    require(not any(x in {"", ".", ".."} for x in relative.split("/")), "Unsafe path component")
    path = regular(root / relative, exists=exists)
    require(root in path.parents, "Path escaped designated root")
    return path


def sha(path):
    digest = hashlib.sha256()
    with regular(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read(path):
    return json.loads(regular(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(MigrationError("Non-finite JSON")))


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def publish(root, name, value):
    """Exclusive new-file publication; never truncate or replace a destination."""
    root = regular(root)
    path = checked(root, name, exists=False)
    require(path.parent.exists(), "Publication parent must already exist")
    payload = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path), "sha256": sha(path)}


def publish_bridge_atomically(execution_dir, destination_dir, value):
    """Flush a retained journal copy, then atomically hard-link a NEW failure file.

    A crash before the link leaves only the independent journal; after the link
    readers see the complete receipt.  No destination is replaced or removed.
    """
    prepared = publish(execution_dir, "EXTERNAL_INTERRUPTION_RECEIPT.json", value)
    target = checked(destination_dir, "failure.json", exists=False)
    require(not target.exists(), "External interruption destination already exists")
    os.link(prepared["path"], target, follow_symlinks=False)
    require(sha(target) == prepared["sha256"], "External interruption publication differs")
    return {"path": str(target), "sha256": prepared["sha256"]}


def expected_filetime(iso):
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    delta = datetime.fromisoformat(iso).astimezone(timezone.utc) - epoch
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def verify_identity(info, expected, request_path, expected_command=None):
    require(info["pid"] == expected["pid"], "Unexpected PID")
    require(info["creation_filetime"] == expected["creation_filetime"],
            "PID creation identity differs; refuse reused PID")
    require(os.path.normcase(info["image"]) == os.path.normcase(expected["image"]), "Process image differs")
    require(info["exit_code"] == 259, "Expected worker is not running")
    command = info["command_line"].replace("/", "\\").casefold()
    for token in (str(EXECUTOR / "executor_worker.py"), str(request_path),
                  str(RESULTS / "provenance_manifest.json"), "--worker-id", "W1", "--attempt-id", OLD_ATTEMPT):
        require(token.replace("/", "\\").casefold() in command, f"Worker command binding absent: {token}")
    if expected_command is None:
        argv = read(RESULTS / "execution/full/A_FULL_0001/W1_process.json")["command"]
        expected_command = ('"' + expected["image"] + '" ' + subprocess.list2cmdline(argv[1:])) if expected["role"] == "worker_base" else subprocess.list2cmdline(argv)
    require(info["command_line"] == expected_command, "Full native worker command line differs from immutable saved argv")


class NativeBackend:
    """Pinned-handle Windows lifecycle, without shell kills or PID-only actions."""
    def __init__(self):
        require(os.name == "nt", "Native transition is Windows-only")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        self.handles = []
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateProcess.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        for name in ("NtSuspendProcess", "NtResumeProcess"):
            fn = getattr(self.nt, name)
            fn.argtypes = [wintypes.HANDLE]
            fn.restype = wintypes.LONG
        self.nt.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
        self.nt.NtQueryInformationProcess.restype = wintypes.LONG

    def open(self, pid):
        # QUERY_INFORMATION | VM_READ | SUSPEND_RESUME | TERMINATE | SYNCHRONIZE
        handle = self.kernel.OpenProcess(0x0400 | 0x0010 | 0x0800 | 0x0001 | 0x100000, False, pid)
        require(bool(handle), f"OpenProcess failed ({ctypes.get_last_error()})")
        self.handles.append(handle)
        return handle

    def command_line(self, handle):
        class US(ctypes.Structure):
            _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]
        size = wintypes.ULONG()
        self.nt.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))
        require(ctypes.sizeof(US) <= size.value <= 1024 * 1024, "Unusable process command-line length")
        buf = ctypes.create_string_buffer(size.value)
        status = self.nt.NtQueryInformationProcess(handle, 60, buf, size.value, ctypes.byref(size))
        require(status >= 0, "Process command-line query failed")
        value = US.from_buffer(buf)
        start = ctypes.addressof(buf)
        require(value.Length % 2 == 0 and start <= value.Buffer <= start + len(buf)
                and value.Buffer + value.Length <= start + len(buf), "Command-line buffer bounds differ")
        return ctypes.wstring_at(value.Buffer, value.Length // 2)

    def info(self, handle, pid):
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        require(self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)), "GetProcessTimes failed")
        image, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        require(self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)), "QueryFullProcessImageNameW failed")
        code = wintypes.DWORD()
        require(self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)), "GetExitCodeProcess failed")
        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (x, ctypes.c_size_t) for x in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
        counters = PMC()
        counters.cb = ctypes.sizeof(counters)
        self.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        self.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        require(self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb), "GetProcessMemoryInfo failed")
        class PBI(ctypes.Structure):
            _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                        ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_size_t),
                        ("InheritedFromUniqueProcessId", ctypes.c_size_t)]
        basic = PBI()
        length = wintypes.ULONG()
        status = self.nt.NtQueryInformationProcess(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), ctypes.byref(length))
        require(status >= 0 and basic.UniqueProcessId == pid, "Native process ancestry query failed")
        return {"pid": pid, "creation_filetime": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                "image": image.value, "command_line": self.command_line(handle) if code.value == 259 else "",
                "exit_code": code.value, "private_bytes": counters.PrivateUsage,
                "working_set_bytes": counters.WorkingSetSize, "parent_pid": basic.InheritedFromUniqueProcessId}

    def resources(self):
        class PI(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD)] + [(x, ctypes.c_size_t) for x in (
                "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable", "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [
                (x, wintypes.DWORD) for x in ("HandleCount", "ProcessCount", "ThreadCount")]
        value = PI()
        value.cb = ctypes.sizeof(value)
        self.psapi.GetPerformanceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.psapi.GetPerformanceInfo.restype = wintypes.BOOL
        require(self.psapi.GetPerformanceInfo(ctypes.byref(value), value.cb), "GetPerformanceInfo failed")
        return {"captured_utc": utc(), "free_commit_bytes": (value.CommitLimit - value.CommitTotal) * value.PageSize,
                "commit_limit_bytes": value.CommitLimit * value.PageSize,
                "free_physical_bytes": value.PhysicalAvailable * value.PageSize}

    def scientific_workers(self):
        """Actual read-only CIM inventory, independent of the selected handles."""
        command = ("[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
                   "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
                   "Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Compress")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        records = json.loads(result.stdout, object_pairs_hook=_pairs)
        require(isinstance(records, list), "CIM process inventory was not complete")
        relevant = []
        for record in records:
            require(isinstance(record, dict) and type(record.get("ProcessId")) is int
                    and isinstance(record.get("CommandLine"), str) and record["CommandLine"],
                    "A Python process command line is inaccessible; cannot prove exclusive experiment execution")
            command_line = record["CommandLine"].replace("/", "\\").casefold()
            if str(REPO).casefold() in command_line and any(name in command_line for name in (
                    "executor_worker.py", "run_p7_7_final.py", "run_p7.py")):
                relevant.append(record)
        require({item["ProcessId"] for item in relevant} == {36468, 26012},
                "Additional or missing scientific worker process; refuse overlapping execution")
        base = next(item for item in relevant if item["ProcessId"] == 36468)
        require(base["ParentProcessId"] == 26012, "Actual CIM scientific child ancestry differs")
        return relevant

    def suspend(self, handle):
        require(self.nt.NtSuspendProcess(handle) >= 0, "NtSuspendProcess failed")

    def resume(self, handle):
        require(self.nt.NtResumeProcess(handle) >= 0, "NtResumeProcess failed")

    def terminate_and_wait(self, handle, pid):
        code = wintypes.DWORD()
        require(self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)), "GetExitCodeProcess failed before termination")
        already = code.value != 259
        if not already:
            require(self.kernel.TerminateProcess(handle, 0xE0000001), "TerminateProcess failed")
        require(self.kernel.WaitForSingleObject(handle, 30000) == 0, "Worker termination not observed")
        require(self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value != 259,
                "Worker still active after termination wait")
        return {"pid": pid, "observed_terminated": True, "exit_code": code.value,
                "already_exited_after_peer_termination": already, "observed_utc": utc()}

    def close(self):
        for handle in reversed(self.handles):
            self.kernel.CloseHandle(handle)
        self.handles.clear()


def load_driver():
    package_name = "paper3_transition_readonly_executor"
    package = types.ModuleType(package_name)
    package.__path__ = [str(EXECUTOR)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(package_name + ".executor_driver", EXECUTOR / "executor_driver.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_frozen_files(manifest, *, driver=None):
    require(manifest.get("manifest_digest") == MANIFEST_DIGEST and canonical({k: v for k, v in manifest.items() if k != "manifest_digest"}) == MANIFEST_DIGEST,
            "Frozen manifest differs")
    require(manifest.get("input_bundle_digest") == INPUT_DIGEST, "Canonical F1 input identity differs")
    require(manifest["paths"]["repo"] == str(REPO) and manifest["paths"]["results_root"] == str(RESULTS)
            and manifest["paths"]["executor_root"] == str(EXECUTOR), "Scientific path binding differs")
    require(sha(REPO / "PAPER3_FINAL_REPLICATION_HANDOFF.md") == ROOT_SHA, "Bound handoff changed")
    bindings = {}
    def bind(path, digest):
        path = regular(path)
        require(path.is_file(), "Bound file is not regular")
        require(sha(path) == digest, f"Frozen byte hash differs: {path}")
        require(str(path) not in bindings or bindings[str(path)] == digest, "Conflicting source SHA")
        bindings[str(path)] = digest
    for rel, digest in manifest["critical_files_sha256"].items():
        bind(checked(REPO, rel), digest)
    observed = {x.relative_to(EXECUTOR).as_posix(): sha(x) for x in EXECUTOR.rglob("*.py")}
    require(observed == manifest["executor_sha256"], "Frozen executor source closure differs")
    for rel, digest in observed.items():
        bind(checked(EXECUTOR, rel), digest)
    for path, digest in manifest["stage_b_dependencies_sha256"].items():
        bind(path, digest)
    for rel, digest in manifest["input_files_sha256"].items():
        bind(checked(manifest["paths"]["input_run"], rel), digest)
    for path, digest in manifest["environment"]["bound_files_sha256"].items():
        bind(path, digest)
    bind(manifest["environment"]["python_executable"], manifest["environment"]["python_executable_sha256"])
    for rel, digest in manifest["original_protected_snapshot"].items():
        bind(checked(REPO, rel), digest)
    baseline = REPO / "verification/paper3_canonical_inputs/execution_20261009/original_protected_start_sha256.json"
    bind(baseline, manifest["original_snapshot_source_sha256"])
    require(read(baseline) == manifest["original_protected_snapshot"], "Original protected inventory differs")
    # Detect added/removed original Python sources, not merely changes to known ones.
    source_closure = {x.relative_to(REPO).as_posix(): sha(x) for folder in ("core", "imported", "scripts")
                      for x in (REPO / folder).rglob("*.py") if not any(y in {"__pycache__", ".venv", "venv"} for y in x.parts)}
    require(source_closure == manifest["original_python_dependency_sha256"], "Original Python source closure differs")
    for rel, digest in source_closure.items():
        bind(checked(REPO, rel), digest)
    bind(RESULTS / "provenance_manifest.json", sha(RESULTS / "provenance_manifest.json"))
    bind(REPO / "PAPER3_FINAL_REPLICATION_HANDOFF.md", ROOT_SHA)
    old_pins_path = REPO / "verification/paper3_canonical_inputs/replication_finalizer_env_v3/attempt001/source_pins.json"
    old_pins = read(old_pins_path)
    require(canonical(old_pins) == "6f07d7c12126218835bfe1b8a8527b6ebeedf35bec6505ebb92eb0b36dbb2a74", "Old live finalizer source pins differ")
    for path, digest in old_pins.items():
        bind(path, digest)
    bind(old_pins_path, sha(old_pins_path))
    old_control = REPO / "verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3"
    require(sha(old_control / "authorized_sequence_003/sequence_source_snapshot.py") == sha(old_control / "authorized_sequence.py"), "Old running sequence/source snapshot differs")
    for path in (old_control / "authorized_sequence_003/start.json", old_control / "authorized_sequence_003/sequence_source_snapshot.py",
                 old_control / "phase_launches/full_001/start.json"):
        bind(path, sha(path))
    return bindings


def resource_check(resources, private_bytes, *, after_stop=False):
    require(type(private_bytes) is int and private_bytes > 0, "Unusable existing worker memory measurement")
    minimum = max(7 * GIB, 2 * private_bytes + GIB) if after_stop else max(int(4.5 * GIB), private_bytes + GIB)
    require(resources["free_commit_bytes"] >= minimum, f"Insufficient system commit headroom: need {minimum} bytes")
    return minimum


def recheck_hashes(bindings):
    for path, digest in bindings.items():
        require(sha(path) == digest, f"Previously audited bytes changed: {path}")


def build_snapshot(manifest, driver, processes, resources, *, native_suspension_observed=False, process_inventory=None):
    """Read all saved inputs/receipts; never read loss columns into decisions."""
    require(len(processes) == 2, "Exact wrapper/base identity pair required")
    require(isinstance(process_inventory, list) and {v["ProcessId"] for v in process_inventory} == {36468, 26012},
            "Actual two-process worker inventory required")
    process_path = RESULTS / "execution/full/A_FULL_0001/W1_process.json"
    request_path = RESULTS / "execution/full/A_FULL_0001/W1_request.json"
    process_record = read(process_path)
    request_data = request_path.read_bytes()
    request = read(request_path)
    request_sha = hashlib.sha256(request_data).hexdigest()
    require(request_sha == process_record["request_sha256"], "Request differs from frozen worker launch")
    require(process_record["pid"] == EXPECTED_PROCESSES[1]["pid"], "Saved worker wrapper PID differs")
    require(request.get("worker_count") == 1 and request.get("worker_id") == "W1"
            and request.get("attempt_id") == OLD_ATTEMPT and request.get("manifest_digest") == MANIFEST_DIGEST,
            "Unexpected old-worker request")
    entries = driver.accepted_records(manifest)
    raw_expected = {f"{name}.csv" for name in entries} | {f"{name}.integrity.json" for name in entries}
    raw_actual = set()
    for item in (RESULTS / "raw").iterdir():
        regular(item)
        require(item.is_file(), "Unknown raw directory or nonregular artifact before stop")
        raw_actual.add(item.name)
    require(raw_actual == raw_expected, "Unknown or partial raw artifact before stop")
    initial_path = RESULTS / "initial_state_manifest.json"
    initial_data = initial_path.read_bytes()
    initial = read(initial_path)
    initial_hashes = {f"{v['center_id']}_{v['seed']}": v["initial_state_hash"] for v in initial["states"]}
    runtime = read(checked(RESULTS, initial["runtime_receipt_path"]))
    f1_path = checked(manifest["paths"]["input_run"], "contexts/F1.json")
    f1_data = f1_path.read_bytes()
    f1 = read(f1_path)
    require(hashlib.sha256(f1_data).hexdigest() == manifest["stage_b_bindings"]["F1"], "Authoritative F1 context bytes differ")
    raw_entries, owned_attempts = [], set()
    for name, saved in sorted(entries.items()):
        task, receipt = saved["task"], saved["receipt"]
        raw_csv_rel, raw_receipt_rel = f"raw/{name}.csv", f"raw/{name}.integrity.json"
        raw_receipt = checked(RESULTS, raw_receipt_rel)
        raw_csv = checked(RESULTS, raw_csv_rel)
        receipt_data = raw_receipt.read_bytes()
        artifacts = {rel: sha(checked(RESULTS, rel)) for rel in (
            receipt["audit_relative"], receipt["rng_relative"], receipt["attempt_csv_relative"], receipt["runtime_receipt_path"])}
        owned_attempts.update(rel for rel in artifacts if rel.startswith("attempts/"))
        attempt_receipt_rel = str(Path(receipt["rng_relative"]).parent / "receipt.json").replace("\\", "/")
        require(sha(checked(RESULTS, attempt_receipt_rel)) == saved["receipt_sha256"], "Attempt/final receipt differs")
        owned_attempts.add(attempt_receipt_rel)
        scene = f1["scenarios"][f"{task['center_id']}/{task['scenario']}"]
        base = f1["base"][str(task["center_id"])]
        expected_rows = []
        for stage in range(1, 25):
            upd = f1["roles"][f"{task['center_id']}/{task['scenario']}/{stage}/update"]
            row = {"stage": stage, "scenario_hash": scene["legacy_scenario_hash"],
                   "scenario_role": scene["metadata"]["definition"], "center_type": base["profile"]["center_type"],
                   "deployment_tier": base["profile"]["budget_tier"], "deployment_filter_hash": base["deployment"]["deployment_filter_hash"],
                   "bank_hash": base["deployment"]["bank_hash"], "update_end_ts": str(upd["update_end_ts"]),
                   "decision_ts": str(upd["decision_ts"]), "initial_state_hash": initial_hashes[f"{task['center_id']}_{task['seed']}"]}
            for role, field in (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash")):
                row[field] = f1["roles"][f"{task['center_id']}/{task['scenario']}/{stage}/{role}"]["legacy_role_hash"]
            expected_rows.append(row)
        raw_entries.append({"receipt": receipt, "receipt_payload_base64": base64.b64encode(receipt_data).decode(),
                            "receipt_file_sha256": saved["receipt_sha256"], "receipt_file_sha256_rechecked": sha(raw_receipt),
                            "csv_relative": raw_csv_rel, "receipt_relative": raw_receipt_rel,
                            "csv_sha256": saved["csv_sha256"], "csv_sha256_rechecked": sha(raw_csv),
                            "bound_artifacts": artifacts, "input_projection": saved["rows"], "expected_stage_inputs": expected_rows})
    task_map = {driver.stem(t): t for t in request["tasks"]}
    pending, unknown = [], []
    attempt_root = RESULTS / "attempts"
    files = [x for x in attempt_root.rglob("*") if x.is_file()]
    for path in files:
        regular(path)
        rel = path.relative_to(RESULTS).as_posix()
        if rel in owned_attempts:
            continue
        parts = path.relative_to(attempt_root).parts
        if len(parts) == 4 and parts[1:] == (OLD_ATTEMPT, "W1", "rng_before.json") and parts[0] in task_map and parts[0] not in entries:
            data = path.read_bytes()
            pending.append({"task": task_map[parts[0]], "artifacts": {"rng_before.json": {
                "relative_path": rel, "file_sha256": hashlib.sha256(data).hexdigest(), "payload_base64": base64.b64encode(data).decode()}}})
        else:
            unknown.append(rel)
    require(len(pending) == 1 and not unknown,
            f"Exactly one RNG-only incomplete task and zero unknown/partial artifacts required; pending={len(pending)}, unknown={unknown}")
    pending_rng = checked(RESULTS, pending[0]["artifacts"]["rng_before.json"]["relative_path"])
    require({x.name for x in pending_rng.parent.iterdir()} == {"rng_before.json"}, "Pending folder is not RNG-only")
    source_expected = {str(checked(REPO, rel)): digest for rel, digest in manifest["critical_files_sha256"].items()}
    source_expected.update({str(checked(EXECUTOR, rel)): digest for rel, digest in manifest["executor_sha256"].items()})
    input_expected = {str(checked(manifest["paths"]["input_run"], rel)): digest for rel, digest in manifest["input_files_sha256"].items()}
    scientific_identity = {"pid": EXPECTED_PROCESSES[0]["pid"], "creation_time_utc": EXPECTED_PROCESSES[0]["created_utc"],
                        "creation_filetime": EXPECTED_PROCESSES[0]["creation_filetime"],
                        "executable": EXPECTED_PROCESSES[0]["image"], "command": process_record["command"],
                        "request_path": str(request_path), "request_sha256": request_sha, "worker_id": "W1", "attempt_id": OLD_ATTEMPT}
    # Each actual kernel handle identity was independently checked before suspend;
    # the snapshot attaches the exact saved argv/request binding for the wrapper.
    observed = dict(scientific_identity)
    wrapper_identity = {"pid": EXPECTED_PROCESSES[1]["pid"], "creation_filetime": EXPECTED_PROCESSES[1]["creation_filetime"],
                        "executable": EXPECTED_PROCESSES[1]["image"], "command": process_record["command"],
                        "scientific_child_pid": EXPECTED_PROCESSES[0]["pid"]}
    require(processes[1]["pid"] == wrapper_identity["pid"] and processes[1]["creation_filetime"] == EXPECTED_PROCESSES[1]["creation_filetime"]
            and processes[0]["parent_pid"] == processes[1]["pid"],
            "Suspended wrapper identity differs")
    snapshot_resources = {"sampled_utc": resources["captured_utc"], "free_commit_bytes": resources["free_commit_bytes"],
                          "existing_worker_private_bytes": processes[0]["private_bytes"], "reserved_extra_worker_count": 1,
                          "requested_minimum_free_commit_bytes": max(int(4.5 * GIB), processes[0]["private_bytes"] + GIB)}
    return {"schema": "paper3-worker-transition-snapshot-v1", "captured_utc": utc(),
            "context": {"manifest": manifest, "initial_manifest_payload_base64": base64.b64encode(initial_data).decode(),
                        "f1_context_payload_base64": base64.b64encode(f1_data).decode(),
                        "initial_hashes": initial_hashes, "scientific_runtime": runtime["scientific_runtime"]},
            "source_bindings": {"expected": source_expected, "observed": {path: sha(path) for path in source_expected}},
            "input_files": {"expected": input_expected, "observed": {path: sha(path) for path in input_expected}},
            "worker": {"expected_identity": scientific_identity, "observed_identity": observed,
                       "wrapper_identity": {"expected": wrapper_identity, "observed": dict(wrapper_identity)},
                       "native_processes": processes, "actual_cim_process_inventory": process_inventory,
                       "suspended": native_suspension_observed, "suspension_verified": native_suspension_observed,
                       "snapshot_stable": False,
                       "active_scientific_worker_pids": [EXPECTED_PROCESSES[0]["pid"]]},
            "request": request, "request_binding": {"payload_base64": base64.b64encode(request_data).decode(),
                         "observed_sha256_before": request_sha, "observed_sha256_after": sha(request_path)},
            "raw_entries": raw_entries, "pending": pending, "unknown_artifacts": unknown, "resources": snapshot_resources}


def bridge_failure(snapshot, termination_evidence, termination_ref, execution_dir, external_journal_ref):
    pending = snapshot["pending"][0]
    rng = pending["artifacts"]["rng_before.json"]
    return {"schema": "paper3-batch20-failed-task-receipt-v1", "status": "INTERRUPTED", "completed_valid": False,
            "task": pending["task"], "manifest_digest": MANIFEST_DIGEST, "input_bundle_digest": INPUT_DIGEST,
            "environment_binding": snapshot["context"]["manifest"]["environment_binding"],
            "initial_state_hash": snapshot["context"]["initial_hashes"][f"{pending['task']['center_id']}_{pending['task']['seed']}"],
            "worker_id": "W1", "attempt_id": OLD_ATTEMPT,
            "producer": "external-migration-controller", "error_type": "ExternalControlledInterruption",
            "message": "The independently identity-checked Windows worker processes were terminated after a suspended RNG-only boundary audit to change scheduling from one to two workers. This record is authored by the external controller, not by the worker exception handler.",
            "worker_python_exception_claimed": False, "worker_exception_observed": False, "rng_relative": rng["relative_path"],
            "rng_file_sha256": rng["file_sha256"], "failed_before_rng_capture": False,
            "created_utc": utc(), "automatic_new_draw_retry": False, "originals_overwritten": False,
            "termination_evidence_path": termination_ref["path"], "termination_evidence_sha256": termination_ref["sha256"],
            "external_termination_journal_sha256": external_journal_ref["sha256"],
            "transition_execution_dir": str(execution_dir), "stopped_processes": termination_evidence["stopped_processes"],
            "performance_used_for_transition": False}


def controlled_stop(*, execution_dir, backend, snapshot_builder, reviewer, external_reviewer, frozen_verifier,
                    expected_processes=EXPECTED_PROCESSES):
    """Dependency-injected transaction; fake backends make every failure testable.

    Returns only after honest external interruption evidence has been published.
    It does not launch replacement workers, statistics, models or finalizers.
    """
    execution_dir = regular(execution_dir)
    require(execution_dir.parent == HERE and execution_dir.name.startswith("transition_"), "Exclusive transition directory required")
    require(not any(execution_dir.iterdir()), "Transition directory is not empty")
    handles, suspended, terminated = [], [], []
    request_path = RESULTS / "execution/full/A_FULL_0001/W1_request.json"
    try:
        for expected in expected_processes:
            handle = backend.open(expected["pid"])
            info = backend.info(handle, expected["pid"])
            verify_identity(info, expected, request_path)
            handles.append((handle, info))
        old_private = handles[0][1]["private_bytes"]
        resources = backend.resources()
        preminimum = resource_check(resources, old_private)
        frozen = frozen_verifier()
        recheck_hashes(frozen)
        resource_check(backend.resources(), old_private)
        intent = {"schema": "paper3-authorized-worker-transition-intent-v1", "created_utc": utc(),
                  "manifest_digest": MANIFEST_DIGEST, "input_bundle_digest": INPUT_DIGEST,
                  "worker_count_before": 1, "worker_count_after": 2, "performance_used_for_transition": False,
                  "processes": [info for _, info in handles], "resources": resources,
                  "pre_stop_minimum_free_commit_bytes": preminimum, "source_sha256": frozen}
        publish(execution_dir, "intent.json", intent)
        for handle, _ in handles:
            backend.suspend(handle)
            suspended.append(handle)
        for handle, info in handles:
            observed = backend.info(handle, info["pid"])
            require(observed["creation_filetime"] == info["creation_filetime"] and observed["image"] == info["image"]
                    and observed["command_line"] == info["command_line"] and observed["exit_code"] == 259,
                    "Suspended native process identity changed")
        inventory_first = backend.scientific_workers()
        first = snapshot_builder([info for _, info in handles], backend.resources())
        inventory_second = backend.scientific_workers()
        require(inventory_first == inventory_second, "Scientific worker inventory changed while suspended")
        second = snapshot_builder([info for _, info in handles], backend.resources())
        # Timestamps and instantaneous resource counters vary; scientific bytes may not.
        stable = lambda value: {k: v for k, v in value.items() if k not in {"captured_utc", "resources"}}
        require(canonical(stable(first)) == canonical(stable(second)), "Suspended scientific snapshot is not stable")
        second["worker"]["snapshot_stable"] = True
        review = reviewer(second)
        require(review.get("status") == "SNAPSHOT_CONSISTENT" and review.get("eligible_to_terminate") is True,
                "Independent transition review did not pass")
        resource_check(backend.resources(), old_private)
        recheck_hashes(frozen)
        resource_check(backend.resources(), old_private)
        snapshot_ref = publish(execution_dir, "suspended_snapshot.json", second)
        review_ref = publish(execution_dir, "independent_review.json", review)
        publish(execution_dir, "termination_intent.json", {"created_utc": utc(), "snapshot": snapshot_ref, "review": review_ref,
                "processes": [info for _, info in handles], "actual_termination_not_yet_performed": True})
        # No fallible work outside this transaction may be inserted between the
        # audited snapshot and termination. Both exact kernel handles stay open.
        for index, (handle, info) in enumerate(handles):
            outcome = backend.terminate_and_wait(handle, info["pid"])
            outcome["creation_filetime"] = info["creation_filetime"]
            require(outcome.get("observed_terminated") is True and outcome.get("exit_code") != 259,
                    "Process stop has not been observed")
            terminated.append(handle)
            publish(execution_dir, f"process_termination_{index + 1:03d}.json", outcome)
        termination = {"schema": "paper3-observed-native-process-termination-v1", "created_utc": utc(),
                       "stopped_processes": [read(execution_dir / f"process_termination_{i + 1:03d}.json") for i in range(len(handles))],
                       "snapshot": snapshot_ref, "independent_review": review_ref,
                       "native_process_handles_used": True, "worker_exception_invented": False}
        term_ref = publish(execution_dir, "termination_evidence.json", termination)
        base_outcome = termination["stopped_processes"][0]
        journal = {"schema": "paper3-external-worker-termination-journal-v1", "snapshot": second, "snapshot_audit": review,
                   "termination": {"pid": base_outcome["pid"], "creation_time_utc": expected_processes[0]["created_utc"],
                                   "creation_filetime": base_outcome["creation_filetime"], "method": "TerminateProcess",
                                   "confirmed_dead": True, "exit_code": base_outcome["exit_code"],
                                   "worker_exception_observed": False, "terminated_utc": base_outcome["observed_utc"]},
                   "termination_evidence": term_ref}
        journal_ref = publish(execution_dir, "external_termination_journal.json", journal)
        # Revalidate every byte audited in the pending task. A partial publication
        # is a blocking condition, never deleted or reinterpreted as a failed run.
        for item in second["raw_entries"]:
            require(sha(checked(RESULTS, item["csv_relative"])) == item["csv_sha256"], "Completed CSV changed after stop")
            require(sha(checked(RESULTS, item["receipt_relative"])) == item["receipt_file_sha256"], "Completed receipt changed after stop")
        pending = second["pending"][0]
        rng = pending["artifacts"]["rng_before.json"]
        rng_path = checked(RESULTS, rng["relative_path"])
        require({x.name for x in rng_path.parent.iterdir()} == {"rng_before.json"}, "Pending attempt gained a partial publication")
        require(sha(rng_path) == rng["file_sha256"], "Saved original-task RNG changed after stop")
        failure = bridge_failure(second, termination, term_ref, execution_dir, journal_ref)
        external_review = external_reviewer(failure, {"file_sha256": journal_ref["sha256"],
                              "payload_base64": base64.b64encode(Path(journal_ref["path"]).read_bytes()).decode()})
        require(external_review.get("status") == "EXTERNAL_INTERRUPTION_EVIDENCE_CONSISTENT", "External termination review rejected retry bridge")
        external_ref = publish(execution_dir, "external_interruption_review.json", external_review)
        failure_ref = publish_bridge_atomically(execution_dir, rng_path.parent, failure)
        result = {"status": "OLD_WORKERS_STOPPED_WITH_TRUTHFUL_RETRY_BRIDGE", "snapshot": snapshot_ref,
                  "review": review_ref, "termination": term_ref, "failure_receipt": failure_ref,
                  "external_journal": journal_ref, "external_review": external_ref,
                  "old_worker_private_bytes": old_private, "pre_stop_minimum_free_commit_bytes": preminimum}
        publish(execution_dir, "controlled_stop.json", result)
        return result
    except BaseException as error:
        resumed, resume_errors = [], []
        for handle in reversed(suspended):
            if handle in terminated:
                continue
            try:
                backend.resume(handle)
                resumed.append(handle)
            except BaseException as resume_error:
                resume_errors.append(str(resume_error))
        if execution_dir.exists() and not (execution_dir / "controller_failure.json").exists():
            publish(execution_dir, "controller_failure.json", {"created_utc": utc(), "status": "STOPPED_FOR_DIAGNOSIS",
                    "error_type": type(error).__name__, "message": str(error), "terminated_count": len(terminated),
                    "resumed_count": len(resumed), "resume_errors": resume_errors,
                    "scientific_files_overwritten": False, "retry_or_replacement_launched": False})
        raise
    finally:
        backend.close()


def wait_and_publish_transition_gate(execution_dir, stop_result, backend, *, implementation_pins, implementation_evidence,
                                     timeout_seconds=600):
    """Wait for OLD parent stages to fail naturally; never terminate those parents."""
    execution_dir = regular(execution_dir)
    control = REPO / "verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3"
    old_sequence = control / "authorized_sequence_003"
    old_finalizer = REPO / "verification/paper3_canonical_inputs/replication_finalizer_env_v3/attempt001"
    full = RESULTS / "execution/full/A_FULL_0001"
    required = (old_sequence / "stopped.json", old_finalizer / "stopped.json", full / "failure.json",
                control / "phase_launches/full_001/finish.json")
    deadline = time.monotonic() + timeout_seconds
    while not all(path.is_file() for path in required):
        require(time.monotonic() < deadline, "Old pipeline did not reach truthful stopped terminal; preserve state")
        require(not (old_sequence / "finish.json").exists() and not (full / "completion.json").exists(), "Old pipeline unexpectedly claims success")
        time.sleep(1)
    seq, fin, phase, launcher = (read(path) for path in required)
    require(seq.get("status") == fin.get("status") == "STOPPED_FOR_DIAGNOSIS", "Old parent stop status differs")
    require(phase.get("phase") == "full" and phase.get("attempt_id") == OLD_ATTEMPT and phase.get("manifest_digest") == MANIFEST_DIGEST,
            "Old full failure provenance differs")
    require(type(launcher.get("exit_code")) is int and type(launcher.get("child_exit_code")) is int
            and launcher["exit_code"] != 0 and launcher["child_exit_code"] != 0, "Old launcher did not record actual nonzero exits")
    require(not (old_sequence / "finish.json").exists() and not (full / "completion.json").exists(), "Old attempt has contradictory terminal records")
    require(not (RESULTS / "execution/full/A_FULL_0002").exists(), "Replacement full attempt already exists; no duplicate dispatch")
    snapshot = read(stop_result["snapshot"]["path"])
    review = read(stop_result["review"]["path"])
    termination = read(stop_result["termination"]["path"])
    require(review.get("status") == "SNAPSHOT_CONSISTENT" and review.get("eligible_to_terminate") is True
            and len(termination["stopped_processes"]) == 2, "Missing reviewed stop proof")
    recheck_hashes(implementation_pins)
    recheck_hashes(implementation_evidence)
    # The manifest and all frozen model, environment, input and original bytes
    # are checked again, independently of the old pipeline's failure.
    frozen = verify_frozen_files(snapshot["context"]["manifest"])
    raw_expected = {item["csv_relative"] for item in snapshot["raw_entries"]} | {item["receipt_relative"] for item in snapshot["raw_entries"]}
    raw_actual = {x.relative_to(RESULTS).as_posix() for x in (RESULTS / "raw").iterdir() if x.is_file()}
    require(raw_actual == raw_expected, "Raw record inventory changed after controlled stop")
    for item in snapshot["raw_entries"]:
        require(sha(checked(RESULTS, item["csv_relative"])) == item["csv_sha256"]
                and sha(checked(RESULTS, item["receipt_relative"])) == item["receipt_file_sha256"], "Completed raw records changed")
        for rel, digest in item["bound_artifacts"].items():
            require(sha(checked(RESULTS, rel)) == digest, "Completed audit/RNG/runtime artifacts changed")
    bridge_path = regular(stop_result["failure_receipt"]["path"])
    require(sha(bridge_path) == stop_result["failure_receipt"]["sha256"], "Honest retry bridge changed")
    bridge = read(bridge_path)
    pending = snapshot["pending"][0]
    rng = pending["artifacts"]["rng_before.json"]
    require(set(x.name for x in bridge_path.parent.iterdir()) == {"rng_before.json", "failure.json"}, "Partial pending task publications appeared")
    require(sha(checked(RESULTS, rng["relative_path"])) == rng["file_sha256"], "Interrupted task RNG changed")
    require(bridge.get("producer") == "external-migration-controller"
            and bridge.get("status") == "INTERRUPTED" and bridge.get("completed_valid") is False,
            "Retry bridge does not truthfully describe external interruption")
    resources = backend.resources()
    postminimum = resource_check(resources, stop_result["old_worker_private_bytes"], after_stop=True)
    evidence_paths = [*required, RESULTS / "provenance_manifest.json",
                      control / "authorized_sequence_003/start.json", control / "authorized_sequence_003/sequence_source_snapshot.py",
                      control / "phase_launches/full_001/start.json", old_finalizer / "start.json", old_finalizer / "source_pins.json",
                      execution_dir / "intent.json", execution_dir / "termination_intent.json",
                      execution_dir / "controlled_stop.json", execution_dir / "suspended_snapshot.json",
                      execution_dir / "independent_review.json", execution_dir / "termination_evidence.json",
                      execution_dir / "external_termination_journal.json", execution_dir / "external_interruption_review.json",
                      execution_dir / "process_termination_001.json", execution_dir / "process_termination_002.json", bridge_path,
                      checked(RESULTS, rng["relative_path"])]
    source_pins = dict(snapshot["source_bindings"]["expected"])
    source_pins.update(read(old_finalizer / "source_pins.json"))
    source_pins.update(implementation_pins)
    source_pins[str(REPO / "PAPER3_FINAL_REPLICATION_HANDOFF.md")] = ROOT_SHA
    recheck_hashes(source_pins)
    gate = {"schema": "paper3-worker-transition-gate-v1", "status": "PASS", "created_utc": utc(),
            "scope": "Controlled scheduling transition only; no claim of final experiment completion or model-output worker invariance",
            "worker_count": 2, "manifest_digest": MANIFEST_DIGEST, "input_bundle_digest": INPUT_DIGEST,
            "previous_root_handoff_sha256": ROOT_SHA, "root_handoff_sha256": ROOT_SHA, "execution_dir": str(execution_dir),
            "old_full_attempt_id": OLD_ATTEMPT, "new_full_attempt_id": NEW_ATTEMPT,
            "interrupted_tasks": [{"stem": "_".join((pending['task']['config_id'], str(pending['task']['center_id']), str(pending['task']['seed']), pending['task']['scenario'])),
                                   "task": pending["task"], "failure_receipt_path": str(bridge_path),
                                   "failure_receipt_sha256": sha(bridge_path), "rng_path": str(checked(RESULTS, rng["relative_path"])),
                                   "rng_file_sha256": rng["file_sha256"]}],
            "performance_used_for_transition": False, "resource_gate_pass": True,
            "old_sequence_stopped": True, "old_finalizer_stopped": True, "old_full_attempt_failed": True,
            "pending_partial_publications": 0, "pending_unreceipted_rng": 0,
            "all_existing_records_verified": True, "verified_existing_trajectories": len(snapshot["raw_entries"]),
            "original_files_unchanged": True, "frozen_sources_unchanged": True,
            "source_sha256": source_pins,
            "evidence_sha256": {**{str(path): sha(path) for path in evidence_paths}, **implementation_evidence},
            "stopped_processes": termination["stopped_processes"], "old_worker_private_bytes": stop_result["old_worker_private_bytes"],
            "resource_minimum_free_commit_bytes": postminimum,
            "pre_stop_minimum_free_commit_bytes": stop_result["pre_stop_minimum_free_commit_bytes"],
            "actual_prelaunch_resource_sample": resources, "model_output_worker_invariance_claimed": False,
            "original_task_rng_restoration_required": True, "new_scientific_protocol_created": False}
    return publish(execution_dir, "transition_gate.json", gate)


def verify_implementation_proofs(pins_object):
    """New helper/proof admission is fixed before touching the running worker."""
    require(pins_object.get("schema") == "paper3-worker-transition-reviewed-implementation-pins-v1", "Unreviewed implementation pin schema")
    pins, evidence = pins_object["files_sha256"], pins_object["evidence_sha256"]
    for name in ("migration_controller.py", "tests_migration_controller.py", "review_transition.py",
                 "root_readonly_preflight.py", "continuation.py", "finalizer_continuation.py"):
        require(str(HERE / name) in pins, f"Required reviewed helper source missing: {name}")
    for path in (*pins, *evidence):
        require(REPO in regular(path).parents, "Reviewed helper/evidence escaped target repository")
    recheck_hashes(pins)
    recheck_hashes(evidence)
    controller_proof = HERE / "CONTROLLER_SYNTHETIC_TEST_RESULTS_002.json"
    preflight_proof = HERE / "root_checks/READONLY_PREFLIGHT_002.json"
    review_proof = HERE / "REVIEW_TRANSITION_SYNTHETIC_TEST_RESULTS_002.json"
    helper_proof = HERE / "SYNTHETIC_CONTINUATION_TEST_RESULTS_ATTEMPT001.json"
    require(all(str(path) in evidence for path in (controller_proof, preflight_proof, review_proof, helper_proof)),
            "Controller/review/continuation tests and root full preflight proofs required")
    controller = read(controller_proof)
    require(controller.get("schema") == "paper3-worker-transition-controller-synthetic-tests-v1"
            and controller.get("status") == "PASS" and controller.get("all_pass") is True
            and type(controller.get("tests_run")) is int and controller["tests_run"] >= 18
            and controller.get("failures") == controller.get("errors") == controller.get("skipped") == 0
            and controller.get("native_owned_child_lifecycle_passed") is True
            and controller.get("real_experiment_processes_controlled") is False,
            "Actual controller/fault/native lifecycle tests must pass")
    require(controller["implementation_sha256"] == {str(HERE / name): pins[str(HERE / name)] for name in ("migration_controller.py", "tests_migration_controller.py")},
            "Controller changed after actual synthetic tests")
    preflight = read(preflight_proof)
    require(preflight.get("schema") == "paper3-worker-transition-root-readonly-preflight-v1"
            and preflight.get("status") == "PASS" and preflight.get("mismatches") == []
            and preflight.get("implementation_sha256") == pins[str(HERE / "root_readonly_preflight.py")]
            and preflight.get("manifest_digest") == MANIFEST_DIGEST and preflight.get("input_bundle_digest") == INPUT_DIGEST
            and preflight.get("root_handoff_sha256") == ROOT_SHA
            and preflight.get("models_generators_or_statistics_executed") is False and preflight.get("processes_modified") is False,
            "Independent root full-byte preflight did not pass")
    review = read(review_proof)
    require(review.get("schema") == "paper3-worker-transition-review-synthetic-tests-v1"
            and review.get("status") == "PASS" and review.get("all_pass") is True
            and type(review.get("tests_run")) is int and review["tests_run"] > 0
            and review.get("failures") == review.get("errors") == review.get("skipped") == 0,
            "Independent transition review tests did not pass")
    require(review["implementation_sha256"].get(str(HERE / "review_transition.py")) == pins[str(HERE / "review_transition.py")],
            "Reviewer changed after actual tests")
    helper = read(helper_proof)
    require(helper.get("all_pass") is True and helper.get("exit_code") == 0
            and type(helper.get("tests_run")) is int and helper["tests_run"] >= 75 and helper.get("tests_skipped") == 0
            and helper.get("models_generators_or_statistics_executed") is False
            and helper.get("real_processes_stopped_or_started") is False,
            "Continuation/finalizer synthetic tests did not pass")
    for name, digest in helper["implementation_sha256"].items():
        require(str(HERE / name) in pins and pins[str(HERE / name)] == digest, "Continuation helper changed after actual tests")
    return pins, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-dir", type=Path, required=True)
    parser.add_argument("--implementation-pins", type=Path, required=True,
                        help="Reviewed immutable JSON with files_sha256 for the NEW controller/reviewer/continuation helpers")
    parser.add_argument("--authorize-native-transition", action="store_true")
    args = parser.parse_args()
    require(args.authorize_native_transition, "No native action authorized; use read-only build_snapshot/verify_frozen_files APIs")
    require(args.execution_dir.parent.resolve() == HERE and not args.execution_dir.exists(), "New exclusive transition directory required")
    manifest = read(RESULTS / "provenance_manifest.json")
    # Validate frozen source bytes BEFORE importing the read-only frozen checker.
    frozen = verify_frozen_files(manifest)
    pins_object = read(args.implementation_pins)
    pins, implementation_evidence = verify_implementation_proofs(pins_object)
    spec = importlib.util.spec_from_file_location("paper3_independent_transition_review", HERE / "review_transition.py")
    reviewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reviewer)
    driver = load_driver()
    args.execution_dir.mkdir(exist_ok=False)
    real_backend = NativeBackend()
    result = controlled_stop(execution_dir=args.execution_dir, backend=real_backend,
                             snapshot_builder=lambda processes, resources: build_snapshot(manifest, driver, processes, resources,
                                                   native_suspension_observed=True, process_inventory=real_backend.scientific_workers()),
                             reviewer=reviewer.audit_snapshot, external_reviewer=reviewer.audit_external_interruption,
                             frozen_verifier=lambda: {**frozen, **pins, **implementation_evidence})
    followup_backend = NativeBackend()
    try:
        gate = wait_and_publish_transition_gate(args.execution_dir, result, followup_backend, implementation_pins=pins,
                                                implementation_evidence=implementation_evidence)
    finally:
        followup_backend.close()
    result["transition_gate"] = gate
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
