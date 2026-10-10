"""Cold recovery observer for already-disappeared processes.

Default execution is read-only except new evidence under this independent
helper directory. No generator/model/optimizer/statistics import or process
control is available. --authorize-cold-recovery adds exactly two NEW honest
observer receipts via exclusive atomic hard links, then emits a fresh gate.
It never rewrites an old terminal, log, CSV, configuration, or source file.
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
import types
from datetime import datetime,timezone
REPO=Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE=Path(__file__).resolve().parent
RESULTS=REPO/"results/p7_7_integrity_replication_batch20_env_v3"
EXECUTOR=REPO/"verification/paper3_canonical_inputs/replication_executor_batch20_env_v3"
MANIFEST_DIGEST="7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
INPUT_DIGEST="ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
ROOT_SHA="f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8"
OLD_ATTEMPT="A_FULL_0001"
NEW_ATTEMPT="A_FULL_0002"
GIB=1024**3
PLANNING_WORKER_PRIVATE_BYTES=7*GIB//2
EXPECTED_PROCESSES=(
 {"pid":22732,"creation_filetime":134360099565017853,"role":"old_sequence"},
 {"pid":16880,"creation_filetime":None,"role":"old_driver_wrapper"},
 {"pid":30160,"creation_filetime":None,"role":"old_driver_base"},
 {"pid":26012,"creation_filetime":134360128955140400,"role":"old_worker_wrapper"},
 {"pid":36468,"creation_filetime":134360128955562955,"role":"old_worker_base"},
 {"pid":20440,"creation_filetime":None,"role":"old_finalizer_wrapper"},
 {"pid":776,"creation_filetime":134360130979815995,"role":"old_finalizer_base"},
)
class RecoveryError(RuntimeError):pass
def require(value, message):
    if not value:
        raise RecoveryError(message)


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
                      parse_constant=lambda x: (_ for _ in ()).throw(RecoveryError("Non-finite JSON")))


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



def load_checked(path,name,expected_sha):
    require(sha(path)==expected_sha,"Module SHA differs before import: "+str(path))
    before=set(sys.modules)
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    forbidden=("torch","numpy","pandas","river","core","imported")
    require(not any(n==x or n.startswith(x+".") for n in set(sys.modules)-before for x in forbidden),
            "Unexpected scientific module import")
    require(sha(path)==expected_sha,"Imported module bytes changed")
    return module

def load_driver(manifest):
    # Import only after *every* executor dependency byte was checked.
    for rel,h in manifest["executor_sha256"].items():
        require(sha(checked(EXECUTOR,rel))==h,"Executor SHA differs before import")
    package_name="paper3_cold_readonly_executor"
    package=types.ModuleType(package_name);package.__path__=[str(EXECUTOR)];sys.modules[package_name]=package
    return load_checked(EXECUTOR/"executor_driver.py",package_name+".executor_driver",
        manifest["executor_sha256"]["executor_driver.py"])

def recheck_hashes(bindings):
    for path,h in bindings.items():require(sha(path)==h,"Audited bytes changed: "+path)

class ReadOnlyWindowsObserver:
    """QUERY_LIMITED_INFORMATION only; no suspend/terminate/write APIs exist."""
    def __init__(self):
        require(os.name=="nt","Actual process observation requires Windows")
        self.kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        self.kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenProcess.restype=wintypes.HANDLE
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE];self.kernel.CloseHandle.restype=wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
        self.kernel.GetProcessTimes.restype=wintypes.BOOL
        self.kernel.GlobalMemoryStatusEx.argtypes=[ctypes.c_void_p];self.kernel.GlobalMemoryStatusEx.restype=wintypes.BOOL
        self.previous_absence_observations=[]
    def absence(self):
        values=[]
        for expected in EXPECTED_PROCESSES:
            ctypes.set_last_error(0)
            handle=self.kernel.OpenProcess(0x1000,False,expected["pid"])
            item={"pid":expected["pid"],"role":expected["role"],
                "expected_creation_filetime":expected["creation_filetime"],"old_exit_code":None}
            if not handle:
                code=ctypes.get_last_error()
                require(code==87,"Process absence unproved, OpenProcess error="+str(code))
                item.update(observation="OPEN_PROCESS_INVALID_PARAMETER",winerror=code,
                    observed_creation_filetime=None,original_identity_absent=True)
            else:
                try:
                    created,exited,kernel,user=(wintypes.FILETIME() for _ in range(4))
                    require(self.kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel),ctypes.byref(user)),"Process identity query failed")
                    ticks=(created.dwHighDateTime<<32)|created.dwLowDateTime
                    prior=next((x for x in self.previous_absence_observations
                        if x["pid"]==expected["pid"] and x.get("observation")=="OPEN_PROCESS_INVALID_PARAMETER"),None)
                    later_than_absence=False
                    if prior is not None:
                        observed=datetime.fromisoformat(prior["observed_utc"])
                        delta=observed-datetime(1601,1,1,tzinfo=timezone.utc)
                        prior_ticks=(delta.days*86400+delta.seconds)*10_000_000+delta.microseconds*10
                        later_than_absence=ticks>prior_ticks
                    require((expected["creation_filetime"] is not None and ticks!=expected["creation_filetime"]) or later_than_absence,
                        "Old process still present or PID reuse cannot be proven")
                    item.update(observation="PID_REUSED",winerror=None,observed_creation_filetime=ticks,original_identity_absent=True)
                    if later_than_absence:item["earlier_absence_observed_utc"]=prior["observed_utc"]
                finally:self.kernel.CloseHandle(handle)
            item["observed_utc"]=utc();values.append(item)
        return values
    def target_processes(self):
        command="Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^python(w)?\.exe$'} | Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 3 -Compress"
        output=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",command],check=True,capture_output=True,text=True).stdout.strip()
        result=[] if not output else json.loads(output)
        result=[result] if isinstance(result,dict) else result
        matches=[]
        tokens=("executor_worker.py","executor_driver.py","authorized_sequence.py","phase_launcher.py",
            "finalizer.py","finalizer_continuation.py","continuation.py","run_p7_7_final.py","run_p7.py")
        for item in result:
            if item["ProcessId"]==os.getpid():continue
            command_line=item.get("CommandLine")
            require(isinstance(command_line,str) and command_line,"Python command inaccessible; target process absence unproved")
            folded=command_line.replace("/","\\").casefold()
            if str(REPO).casefold() in folded and any(token in folded for token in tokens):matches.append(item)
        return matches
    def resources(self):
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_=[("dwLength",wintypes.DWORD),("dwMemoryLoad",wintypes.DWORD)]+[(x,ctypes.c_ulonglong) for x in
                ("ullTotalPhys","ullAvailPhys","ullTotalPageFile","ullAvailPageFile","ullTotalVirtual","ullAvailVirtual","ullAvailExtendedVirtual")]
        m=MEMORYSTATUSEX();m.dwLength=ctypes.sizeof(m)
        require(self.kernel.GlobalMemoryStatusEx(ctypes.byref(m)),"Commit resource query failed")
        return {"sampled_utc":utc(),"free_commit_bytes":m.ullAvailPageFile,"commit_limit_bytes":m.ullTotalPageFile,
            "free_physical_bytes":m.ullAvailPhys,"historical_worker_private_bytes":PLANNING_WORKER_PRIVATE_BYTES,
            "private_bytes_source":"CONSERVATIVE_BOUND_NOT_CURRENT_MEASUREMENT","requested_worker_count":2,
            "minimum_free_commit_bytes":max(7*GIB,2*PLANNING_WORKER_PRIVATE_BYTES+GIB)}


def terminal_observations():
    control=REPO/"verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3"
    paths={"sequence_stopped":control/"authorized_sequence_003/stopped.json",
        "finalizer_stopped":REPO/"verification/paper3_canonical_inputs/replication_finalizer_env_v3/attempt001/stopped.json",
        "phase_launcher_finished":control/"phase_launches/full_001/finish.json",
        "phase_completion":RESULTS/"execution/full/A_FULL_0001/completion.json",
        "phase_failure":RESULTS/"execution/full/A_FULL_0001/failure.json",
        "worker_completion":RESULTS/"workers/W1_A_FULL_0001_trajectory.completion.json",
        "pending_failure":RESULTS/"attempts/B8_AlwaysOpen_ratio10_33002_7311_C0/A_FULL_0001/W1/failure.json"}
    return {k:v.exists() for k,v in paths.items()}

def build_snapshot(manifest,driver,observer,*,source_bindings):
    """Read-only actual frozen acceptance + exhaustive pending/raw inventory."""
    process_path=RESULTS/"execution/full/A_FULL_0001/W1_process.json"
    request_path=RESULTS/"execution/full/A_FULL_0001/W1_request.json"
    process_record=read(process_path);request_data=regular(request_path).read_bytes();request=read(request_path)
    request_sha=hashlib.sha256(request_data).hexdigest()
    require(request_sha==process_record["request_sha256"] and process_record["pid"]==26012,"Original request/process binding differs")
    entries = driver.accepted_records(manifest)
    require(len(entries)==123,"Expected exact123 eligible trajectories")
    require(len(driver.paired_groups(entries))==24,"Expected exact24 complete paired groups")
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
    for child in attempt_root.rglob("*"):
        regular(child)
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
    allowed_directories=set()
    for relative in owned_attempts | {pending[0]["artifacts"]["rng_before.json"]["relative_path"]}:
        parent=Path(relative).parent
        while parent.as_posix()!="attempts":
            allowed_directories.add(parent.as_posix());parent=parent.parent
    require({x.relative_to(RESULTS).as_posix() for x in attempt_root.rglob("*") if x.is_dir()}==allowed_directories,
        "Unknown or empty attempt directory exists")
    source_expected = {str(checked(REPO, rel)): digest for rel, digest in manifest["critical_files_sha256"].items()}
    source_expected.update({str(checked(EXECUTOR, rel)): digest for rel, digest in manifest["executor_sha256"].items()})
    input_expected = {str(checked(manifest["paths"]["input_run"], rel)): digest for rel, digest in manifest["input_files_sha256"].items()}

    evidence=dict(source_bindings)
    def bind(path,h=None):
        path=regular(path);actual=sha(path)
        require(h is None or actual==h,"Actual evidence SHA differs")
        require(str(path) not in evidence or evidence[str(path)]==actual,"Conflicting evidence map")
        evidence[str(path)]=actual
    for entry in raw_entries:
        bind(RESULTS/entry["csv_relative"],entry["csv_sha256"]);bind(RESULTS/entry["receipt_relative"],entry["receipt_file_sha256"])
        for rel,h in entry["bound_artifacts"].items():bind(checked(RESULTS,rel),h)
        bind(checked(RESULTS,str(Path(entry["receipt"]["rng_relative"]).parent/"receipt.json").replace("\\","/")),entry["receipt_file_sha256"])
    initial_files={}
    for item in initial["states"]:
        bind(checked(RESULTS,item["path"]),item["sha256"]);bind(checked(RESULTS,item["receipt_path"]),item["receipt_sha256"])
        initial_files[str(checked(RESULTS,item["path"]))]=item["sha256"]
        initial_files[str(checked(RESULTS,item["receipt_path"]))]=item["receipt_sha256"]
    bind(initial_path);bind(checked(RESULTS,initial["runtime_receipt_path"]),initial["runtime_receipt_sha256"])
    for tree in (RESULTS/"execution/full/A_FULL_0001",RESULTS/"execution/initial/A_INITIAL_0001",
        RESULTS/"execution/minimal/A_MINIMAL_0001",
        REPO/"verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/authorized_sequence_003",
        REPO/"verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/phase_launches/full_001",
        REPO/"verification/paper3_canonical_inputs/replication_finalizer_env_v3/attempt001"):
        for path in tree.rglob("*"):
            regular(path)
            if path.is_file():bind(path)
    for path in (RESULTS/"workers").glob("W1_A_FULL_0001*"):
        if path.is_file():bind(path)
    bind(pending_rng)
    # No active original writer is allowed. Re-read all collected bytes before and
    # after the native observations; observer records a new UTC observation only.
    before_inventory={x.relative_to(RESULTS).as_posix():sha(x) for folder in ("raw","attempts") for x in (RESULTS/folder).rglob("*") if x.is_file()}
    after_inventory={x.relative_to(RESULTS).as_posix():sha(x) for folder in ("raw","attempts") for x in (RESULTS/folder).rglob("*") if x.is_file()}
    recheck_hashes(evidence)
    require(before_inventory==after_inventory,"Cold scientific output inventory changed")
    phase_start=read(REPO/"verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/phase_launches/full_001/start.json")
    observed_evidence={path:sha(path) for path in evidence}
    absence=observer.absence();active=observer.target_processes();resources=observer.resources()
    return {"schema":"paper3-abrupt-recovery-snapshot-v1","captured_utc":utc(),
        "context":{"manifest":manifest,"initial_manifest_payload_base64":base64.b64encode(initial_data).decode(),
            "f1_context_payload_base64":base64.b64encode(f1_data).decode(),"initial_hashes":initial_hashes,"scientific_runtime":runtime["scientific_runtime"]},
        "source_bindings":{"expected":source_expected,"observed":{path:sha(path) for path in source_expected}},
        "input_files":{"expected":input_expected,"observed":{path:sha(path) for path in input_expected}},
        "request":request,"request_sha256":request_sha,
        "request_binding":{"payload_base64":base64.b64encode(request_data).decode(),"observed_sha256_before":request_sha,"observed_sha256_after":sha(request_path)},
        "raw_entries":raw_entries,"pending":pending,"unknown_artifacts":unknown,"resources":resources,
        "process_absence":absence,"active_target_processes":active,"native_processes_modified":False,
        "worker_exception_observed":False,"termination_actor":"NOT_VERIFIED","stable_file_inventory":True,
        "initial60_accepted_records_verified":True,"root_handoff_sha256":sha(REPO/"PAPER3_FINAL_REPLICATION_HANDOFF.md"),
        "old_terminal_records":terminal_observations(),"phase_started_utc":phase_start["started_utc"],
        "evidence_bindings":{"expected":evidence,"observed":observed_evidence},
        "initial_file_bindings":{"expected":initial_files,"observed":dict(initial_files)},
        "model_or_generator_or_statistics_executed":False,"performance_values_used":False}


def verify_implementation_pins(path):
    value=read(path)
    require(value.get("schema")=="paper3-abrupt-recovery-reviewed-pins-v1","Unrecognized reviewed implementation pins")
    pins={**value["files_sha256"],**value["evidence_sha256"]};recheck_hashes(pins)
    for name in ("cold_audit.py","recover.py","tests_cold_recovery.py","continuation.py","finalizer.py","test_continuation.py","run_continuation_tests.py"):
        require(str(HERE/name) in pins,"Missing implementation pin: "+name)
    proof=read(HERE/"COLD_RECOVERY_SYNTHETIC_TEST_RESULTS_ATTEMPT001.json")
    require(proof.get("all_pass") is True and proof.get("failures")==proof.get("errors")==proof.get("skipped")==0,
        "Cold recovery synthetic tests not successful")
    require(proof["implementation_sha256"]=={str(HERE/n):sha(HERE/n) for n in ("cold_audit.py","recover.py","tests_cold_recovery.py")},
        "Cold recovery sources changed since synthetic tests")
    peer=read(HERE/"SYNTHETIC_CONTINUATION_TEST_RESULTS_ATTEMPT001.json")
    require(peer.get("all_pass") is True and peer.get("exit_code")==0 and peer.get("tests_skipped")==0
        and type(peer.get("tests_run")) is int and peer["tests_run"]>0,
        "Continuation synthetic tests not successful")
    require(peer["implementation_sha256"]=={n:sha(HERE/n) for n in
        ("continuation.py","finalizer.py","test_continuation.py","run_continuation_tests.py")},
        "Continuation sources changed since synthetic tests")
    require(value.get("independent_review_pass") is True and value.get("real_recovery_authorized") is True,
        "Missing actual reviewed authorization binding")
    pins[str(regular(path))]=sha(path)
    return pins

def run_readonly(execution_dir,implementation_pins,observer=None):
    execution_dir=Path(execution_dir)
    require(execution_dir.parent.resolve()==HERE and not execution_dir.exists(),"Exclusive new evidence child required")
    source_pins=verify_implementation_pins(implementation_pins)
    manifest=read(RESULTS/"provenance_manifest.json")
    frozen=verify_frozen_files(manifest)
    bindings={**frozen,**source_pins}
    driver=load_driver(manifest)
    audit=load_checked(HERE/"cold_audit.py","paper3_cold_audit",source_pins[str(HERE/"cold_audit.py")])
    snapshot=build_snapshot(manifest,driver,observer or ReadOnlyWindowsObserver(),source_bindings=bindings)
    review=audit.audit_snapshot(snapshot)
    execution_dir.mkdir(exist_ok=False)
    snapshot_ref=publish(execution_dir,"cold_snapshot.json",snapshot)
    review_ref=publish(execution_dir,"cold_audit.json",review)
    return {"snapshot":snapshot,"audit":review,"snapshot_ref":snapshot_ref,"audit_ref":review_ref,
        "source_pins":source_pins,"driver":driver,"auditor":audit,"execution_dir":execution_dir}

def publish_new_receipt(execution_dir,name,destination,value):
    """Prepare+fsync independently, atomically link to a never-existing target."""
    prepared=publish(execution_dir,name,value)
    destination=regular(destination,exists=False)
    require(not destination.exists(),"Refuse overwrite of old result evidence")
    os.link(prepared["path"],destination,follow_symlinks=False)
    require(sha(destination)==prepared["sha256"],"Atomic observer receipt differs")
    return {"path":str(destination),"sha256":prepared["sha256"]}

def run_recovery(context,observer=None):
    """Adds two NEW observer records; never launches/resumes any experiment."""
    snapshot=context["snapshot"];review=context["audit"];directory=context["execution_dir"]
    observer=observer or ReadOnlyWindowsObserver()
    observer.previous_absence_observations=snapshot["process_absence"]
    require(not (RESULTS/"execution/full/A_FULL_0002").exists(),"Next full attempt already exists; do not duplicate continuation")
    recheck_hashes(snapshot["evidence_bindings"]["expected"])
    require(terminal_observations()==snapshot["old_terminal_records"],"Old terminal appeared before bridge")
    absence=observer.absence();require(observer.target_processes()==[],"Target process appeared before bridge")
    resources=observer.resources()
    require(resources["free_commit_bytes"]>=resources["minimum_free_commit_bytes"],"Insufficient cold-start resources")
    # The pure auditor checks the original observations; this fresh snapshot
    # checks native absence and resource admission again before any old-path add.
    fresh=dict(snapshot);fresh.update(process_absence=absence,resources=resources,captured_utc=utc())
    fresh_review=context["auditor"].audit_snapshot(fresh)
    fresh_ref=publish(directory,"prepublication_snapshot.json",fresh)
    fresh_audit_ref=publish(directory,"prepublication_cold_audit.json",fresh_review)
    created=utc();failure,phase=context["auditor"].failure_receipts(fresh,fresh_review,fresh_ref["sha256"],created)
    pending=checked(RESULTS,fresh_review["pending_rng_relative"])
    require({p.name for p in pending.parent.iterdir()}=={"rng_before.json"},"Pending attempt acquired partial body/publication")
    phase_destination=RESULTS/"execution/full/A_FULL_0001/failure.json"
    require(not phase_destination.exists() and not (phase_destination.parent/"completion.json").exists(),"Phase terminal conflict")
    task_ref=publish_new_receipt(directory,"NEW_OBSERVER_TASK_INTERRUPTION.json",pending.parent/"failure.json",failure)
    phase_ref=publish_new_receipt(directory,"NEW_OBSERVER_PHASE_INTERRUPTION.json",phase_destination,phase)
    driver=context["driver"];manifest=fresh["context"]["manifest"]
    entries=driver.accepted_records(manifest)
    require(len(entries)==123 and len(driver.paired_groups(entries))==24,"Saved scientific record acceptance changed after bridge")
    remaining=[t for t in driver.tasks() if driver.stem(t) not in entries]
    retry=driver._retry_descriptors(manifest,remaining)
    expected={driver.stem(fresh_review["pending_task"]):{"failed_receipt_relative":str(Path(fresh_review["pending_rng_relative"]).parent/"failure.json").replace("\\","/"),
        "failed_receipt_sha256":task_ref["sha256"]}}
    require(retry==expected,"Frozen retry descriptor rejected exact captured RNG bridge")
    recheck_hashes(fresh["evidence_bindings"]["expected"])
    # The two NEW receipts have already been preserved. A resource/absence
    # failure here emits no PASS gate and never launches a replacement run.
    final_absence=observer.absence()
    require(observer.target_processes()==[],"Target process appeared after observer publication")
    final_resources=observer.resources()
    require(final_resources["free_commit_bytes"]>=final_resources["minimum_free_commit_bytes"],"Commit headroom changed; no continuation gate")
    evidence={**fresh["evidence_bindings"]["expected"],task_ref["path"]:task_ref["sha256"],phase_ref["path"]:phase_ref["sha256"],
        fresh_ref["path"]:fresh_ref["sha256"],fresh_audit_ref["path"]:fresh_audit_ref["sha256"],
        context["snapshot_ref"]["path"]:context["snapshot_ref"]["sha256"],context["audit_ref"]["path"]:context["audit_ref"]["sha256"]}
    gate={"schema":"paper3-abrupt-recovery-gate-v1","status":"PASS","created_utc":utc(),
        "repository":str(REPO),"results_root":str(RESULTS),"manifest_digest":MANIFEST_DIGEST,"input_bundle_digest":INPUT_DIGEST,
        "old_attempt_id":OLD_ATTEMPT,"new_attempt_id":NEW_ATTEMPT,"worker_count":2,
        "completed_trajectories":123,"complete_paired_groups":24,"pending_task":fresh_review["pending_task"],
        "pending_rng_relative":fresh_review["pending_rng_relative"],"pending_rng_file_sha256":fresh_review["pending_rng_file_sha256"],
        "pending_rng_state_digest":fresh_review["pending_rng_state_digest"],
        "initial_state_manifest_sha256":fresh_review["initial_state_manifest_sha256"],"root_handoff_sha256":ROOT_SHA,
        "task_failure_receipt":task_ref,"phase_failure_receipt":phase_ref,"observer_snapshot":fresh_ref,"cold_audit":fresh_audit_ref,
        "source_bindings_sha256":{**fresh["source_bindings"]["expected"],**context["source_pins"]},"evidence_sha256":evidence,
        "process_absence_checked":True,"all_old_processes_absent":True,"old_processes":final_absence,
        "resource_gate_pass":True,"minimum_free_commit_bytes":final_resources["minimum_free_commit_bytes"],
        "actual_prelaunch_resource_sample":final_resources,"unknown_or_partial_artifacts":0,
        "old_worker_private_bytes":PLANNING_WORKER_PRIVATE_BYTES,
        "old_worker_private_bytes_source":"CONSERVATIVE_BOUND_NOT_CURRENT_MEASUREMENT",
        "performance_used_for_recovery":False,"model_output_worker_invariance_claimed":False,
        "human_Codex_close_report":"VERIFIED_USER_REPORT","causal_exit_actor":"NOT_VERIFIED",
        "old_terminal_records":{k:v for k,v in snapshot["old_terminal_records"].items() if k in {"sequence_stopped","finalizer_stopped","phase_launcher_finished"}},
        "old_exit_code":None,"worker_exception_observed":False,"native_processes_modified":False,
        "frozen_retry_descriptor_verified":True,"models_generators_statistics_executed":False}
    gate["gate_digest"]=canonical(gate)
    publish(directory,"cold_recovery_gate.json",gate)
    return gate

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--execution-dir",required=True,type=Path)
    parser.add_argument("--implementation-pins",required=True,type=Path)
    parser.add_argument("--authorize-cold-recovery",action="store_true");args=parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,"Requires -I -S -B")
    require(HERE==REPO/"verification/paper3_canonical_inputs/replication_abrupt_recovery_v1","Wrong helper root")
    context=run_readonly(args.execution_dir,args.implementation_pins)
    if args.authorize_cold_recovery:
        gate=run_recovery(context);print(json.dumps({"status":gate["status"],"cold_gate":str(args.execution_dir/"cold_recovery_gate.json")}))
    else:print(json.dumps({"status":"READONLY_COLD_AUDIT_PASS","existing_result_paths_added":False}))
if __name__=="__main__":main()
