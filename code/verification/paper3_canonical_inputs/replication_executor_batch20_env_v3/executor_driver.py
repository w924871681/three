"""Researcher-authorized phase coordinator for the independent batch20 replication.

No model, generator or statistics module is imported in this coordinator.
Workers are isolated, own new output paths, and use the unchanged frozen method.
Phase transitions require integrity evidence rather than observed performance.
"""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    package = types.ModuleType("paper3_replication")
    package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[package.__name__] = package
    __package__ = package.__name__
from . import provenance as p

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v3"
INPUT_RUN = REPO / "verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1/CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"
EXECUTOR = Path(__file__).resolve().parent
METHODS = (("B0", "B0_Frozen_ratio10"), ("B1", "B1_AlwaysMaintainP50_ratio10"),
           ("B2", "B2_RAVM_ratio10"), ("B8", "B8_AlwaysOpen_ratio10"),
           ("P7.7", "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"))
INPUT_FIELDS = ("scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash",
                "center_type", "deployment_tier", "deployment_filter_hash", "bank_hash",
                "update_end_ts", "decision_ts", "scenario_role", "initial_state_hash")

def utc(): return datetime.now(timezone.utc).isoformat()
def stem(task):
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"
def tasks():
    return [{"center_id": c, "seed": s, "scenario": q, "method": m, "config_id": i}
            for c in range(33000,33020) for s in (7311,7312,7313)
            for q in ("C0","C1","C3","C4") for m,i in METHODS]
def load_manifest():
    return p.read_json(p.checked_path(RESULTS,"provenance_manifest.json"))
def publish(relative, obj): return p.publish_json(RESULTS, relative, obj)

def accepted_records(manifest, *, require_complete=False):
    """Re-read actual new receipts and input projection; retain no outcome values."""
    if not (RESULTS/"raw").exists(): return {}
    stage_b = p.verify_stage_b(REPO, INPUT_RUN)
    bundle = stage_b["F1"]
    initial_path = p.checked_path(RESULTS,"initial_state_manifest.json")
    initial = p.read_json(initial_path)
    initial_sha = p.file_sha256(initial_path)
    environment_binding = p.canonical_hash(manifest["environment"])
    if (initial.get("manifest_digest") != manifest["manifest_digest"]
            or initial.get("input_bundle_digest") != manifest["input_bundle_digest"]
            or initial.get("environment_binding") != environment_binding
            or initial.get("completed_cases") != 60
            or initial.get("canonical_warmup_reference_created") is not True):
        raise RuntimeError("Initial reference certificate binding differs")
    runtime_path = p.checked_path(RESULTS,initial["runtime_receipt_path"])
    runtime_receipt = p.read_json(runtime_path)
    if (p.file_sha256(runtime_path) != initial["runtime_receipt_sha256"]
            or runtime_receipt.get("schema") != "paper3-batch20-scientific-runtime-receipt-v1"
            or runtime_receipt.get("manifest_digest") != manifest["manifest_digest"]
            or runtime_receipt.get("environment_binding") != environment_binding
            or runtime_receipt.get("source_bindings_digest") != p.canonical_hash(manifest["critical_files_sha256"])
            or runtime_receipt.get("scientific_runtime_signature") != initial["scientific_runtime_signature"]
            or p.canonical_hash(runtime_receipt["scientific_runtime"]) != initial["scientific_runtime_signature"]):
        raise RuntimeError("Initial scientific runtime certificate differs")
    initial_hashes = {}
    for item in initial["states"]:
        key = (item["center_id"],item["seed"])
        if key in initial_hashes: raise RuntimeError("Duplicate initial reference")
        state_path = p.checked_path(RESULTS,item["path"])
        state_receipt_path = p.checked_path(RESULTS,item["receipt_path"])
        if p.file_sha256(state_path) != item["sha256"] or p.file_sha256(state_receipt_path) != item["receipt_sha256"]:
            raise RuntimeError("Initial reference byte hash differs")
        saved = p.read_json(state_path)
        audit = saved["audit"]
        state_receipt = p.read_json(state_receipt_path)
        case = {"center_id":key[0],"seed":key[1]}
        if (saved.get("task") != case or state_receipt.get("task") != case
                or state_receipt.get("valid") is not True
                or saved.get("manifest_digest") != manifest["manifest_digest"]
                or state_receipt.get("manifest_digest") != manifest["manifest_digest"]
                or audit.get("source_bindings_sha256") != manifest["critical_files_sha256"]
                or audit.get("initial_state_hash") != item["initial_state_hash"]
                or audit.get("original_initial_model_called") is not True
                or audit.get("warmup_steps") != 50 or audit.get("warmup_seed") != sum(key)):
            raise RuntimeError("Initial reference scientific evidence differs")
        initial_hashes[key] = item["initial_state_hash"]
    expected_initial = {(c,s) for c in range(33000,33020) for s in (7311,7312,7313)}
    if len(initial_hashes) != 60 or set(initial_hashes) != expected_initial:
        raise RuntimeError("Complete 60-case initial reference required")
    entries = {}
    for task in tasks():
        name = stem(task)
        receipt_path = RESULTS / "raw" / (name + ".integrity.json")
        if not receipt_path.exists(): continue
        receipt_path = p.checked_path(RESULTS, f"raw/{name}.integrity.json")
        receipt = p.read_json(receipt_path)
        csv_path = p.checked_path(RESULTS, f"raw/{name}.csv")
        if receipt.get("valid") is not True or receipt.get("task") != task:
            raise RuntimeError(f"Invalid new receipt/task: {name}")
        if receipt.get("manifest_digest") != manifest["manifest_digest"]:
            raise RuntimeError(f"New receipt belongs to another provenance: {name}")
        if receipt.get("output_hash") != p.file_sha256(csv_path):
            raise RuntimeError(f"New CSV byte hash differs: {name}")
        if receipt.get("input_bundle_digest") != manifest["input_bundle_digest"]:
            raise RuntimeError(f"New receipt input identity differs: {name}")
        expected_hash = initial_hashes[task["center_id"],task["seed"]]
        expected_stage_hashes = {
            str(stage): {role:bundle["roles"][f"{task['center_id']}/{task['scenario']}/{stage}/{role}"]["legacy_role_hash"]
                         for role in ("update","assessment","service")}
            for stage in range(1,25)
        }
        expected_receipt = {
            "schema":"paper3-batch20-replication-trajectory-receipt-v1","initial_state_hash":expected_hash,
            "initial_state_manifest_sha256":initial_sha,"environment_binding":environment_binding,
            "trajectory_rows":24,"runner_hash":manifest["critical_files_sha256"]["scripts/run_p7_7_final.py"],
            "implementation_hash":manifest["critical_files_sha256"]["core/p7.py"],
            "protocol_hash":manifest["critical_files_sha256"]["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
            "source_bindings_digest":p.canonical_hash(manifest["critical_files_sha256"]),
            "executor_bundle_digest":p.canonical_hash(manifest["executor_sha256"]),
            "scientific_runtime_signature":initial["scientific_runtime_signature"],
            "stage_input_hashes":[{"stage":stage,
                "D_upd_hash":expected_stage_hashes[str(stage)]["update"],
                "D_assess_hash":expected_stage_hashes[str(stage)]["assessment"],
                "D_srv_hash":expected_stage_hashes[str(stage)]["service"]} for stage in range(1,25)],
        }
        if any(receipt.get(k) != v for k,v in expected_receipt.items()):
            raise RuntimeError(f"New scientific receipt binding differs: {name}")
        task_runtime_path = p.checked_path(RESULTS,receipt["runtime_receipt_path"])
        task_runtime = p.read_json(task_runtime_path)
        if (p.file_sha256(task_runtime_path) != receipt["runtime_receipt_sha256"]
                or task_runtime.get("manifest_digest") != manifest["manifest_digest"]
                or task_runtime.get("environment_binding") != environment_binding
                or task_runtime.get("source_bindings_digest") != p.canonical_hash(manifest["critical_files_sha256"])
                or task_runtime.get("scientific_runtime_signature") != initial["scientific_runtime_signature"]
                or task_runtime.get("scientific_runtime") != runtime_receipt["scientific_runtime"]):
            raise RuntimeError("Worker runtime differs from common initial reference")
        audit_path = p.checked_path(RESULTS,receipt["audit_relative"])
        rng_path = p.checked_path(RESULTS,receipt["rng_relative"])
        attempt_csv = p.checked_path(RESULTS,receipt["attempt_csv_relative"])
        if (p.file_sha256(audit_path) != receipt["audit_hash"]
                or p.file_sha256(rng_path) != receipt["rng_file_sha256"]
                or p.file_sha256(attempt_csv) != receipt["attempt_csv_hash"]
                or receipt["attempt_csv_hash"] != receipt["output_hash"]):
            raise RuntimeError("Attempt/audit/RNG byte binding differs")
        audit = p.read_json(audit_path)
        rng = p.read_json(rng_path)
        if (receipt.get("audit_path") != receipt["audit_relative"]
                or receipt.get("audit_sha256") != receipt["audit_hash"]
                or receipt.get("rng_before_path") != receipt["rng_relative"]
                or receipt.get("rng_before_sha256") != receipt["rng_file_sha256"]):
            raise RuntimeError("Receipt alias bindings differ")
        rng_body = {k:v for k,v in rng.items() if k != "state_digest"}
        rng_bindings = {"task":task,"input_bundle_digest":manifest["input_bundle_digest"],
            "source_bindings_digest":p.canonical_hash(manifest["critical_files_sha256"]),
            "environment_binding":environment_binding,
            "final_configuration_sha256":manifest["critical_files_sha256"]["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
            "expected_initial_state_hash":expected_hash}
        if (rng.get("schema") != "paper3-original-task-torch-rng-v1"
                or rng.get("manual_seed_called") is not False or rng.get("bindings") != rng_bindings
                or rng.get("state_digest") != p.canonical_hash(rng_body)):
            raise RuntimeError("Recorded task RNG provenance differs")
        for state in [rng["cpu"]]+[entry["state"] for entry in rng["cuda"]]:
            raw_state = base64.b64decode(state["base64"],validate=True)
            if (state.get("dtype") != "uint8" or state.get("shape") != [len(raw_state)]
                    or state.get("byte_count") != len(raw_state)
                    or hashlib.sha256(raw_state).hexdigest() != state.get("sha256")):
                raise RuntimeError("Recorded RNG byte identity differs")
        state_audit = audit.get("initial_state",{})
        access = audit.get("timeline_access",{})
        if (audit.get("task") != task or audit.get("source_bindings_sha256") != manifest["critical_files_sha256"]
                or audit.get("original_run_one_code_object_preserved") is not True
                or audit.get("original_globals_mutated") is not False
                or audit.get("globals_overridden") != ["timeline_for_v2","scenario_hash_v2","initial_model"]
                or audit.get("input_bundle_digest") != manifest["input_bundle_digest"]
                or audit.get("environment_binding") != environment_binding
                or audit.get("scientific_runtime_signature") != initial["scientific_runtime_signature"]
                or audit.get("scientific_runtime") != runtime_receipt["scientific_runtime"]
                or state_audit.get("initial_state_hash") != expected_hash
                or state_audit.get("before_first_decision_verified") is not True
                or access.get("violation_count") != 0 or access.get("completed_stages") != 24
                or access.get("phase") != "SERVICED" or audit.get("generator_called") is not False
                or audit.get("rng_state_before_original_run") != rng):
            raise RuntimeError("Exact method/input/initial/causal/RNG audit differs")
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            if len(header) != len(set(header)): raise RuntimeError("Duplicate CSV fields")
            selected = {k:header.index(k) for k in INPUT_FIELDS + ("stage","method","config_id","center_id","seed","scenario","identity_before","future_service_used_in_decision","online_future_service_used")}
            rows = []
            for tokens in reader:
                if len(tokens) != len(header): raise RuntimeError("Malformed new CSV")
                row = {k:tokens[i] for k,i in selected.items()}
                del tokens
                if any(row[k] != str(v) for k,v in task.items()): raise RuntimeError("CSV task mismatch")
                row["stage"] = int(row["stage"])
                for field in ("future_service_used_in_decision","online_future_service_used"):
                    if row[field] != "False": raise RuntimeError("Future-service flag not false")
                rows.append(row)
        if [r["stage"] for r in rows] != list(range(1,25)):
            raise RuntimeError("Trajectory stage coverage differs")
        if rows[0]["identity_before"] != "msa_a57_pt": raise RuntimeError("Initial identity differs")
        if len({r["initial_state_hash"] for r in rows}) != 1:
            raise RuntimeError("Initial-state evidence changes within trajectory")
        scene = bundle["scenarios"][f"{task['center_id']}/{task['scenario']}"]
        base = bundle["base"][str(task["center_id"])]
        for row in rows:
            stage = row["stage"]
            role_metadata = bundle["roles"][f"{task['center_id']}/{task['scenario']}/{stage}/update"]
            expected_fields = {
                "scenario_hash":scene["legacy_scenario_hash"],"scenario_role":scene["metadata"]["definition"],
                "initial_state_hash":expected_hash,"center_type":base["profile"]["center_type"],
                "deployment_tier":base["profile"]["budget_tier"],"bank_hash":base["deployment"]["bank_hash"],
                "deployment_filter_hash":base["deployment"]["deployment_filter_hash"],
                "update_end_ts":str(role_metadata["update_end_ts"]),"decision_ts":str(role_metadata["decision_ts"]),
            }
            for role,field in (("update","D_upd_hash"),("assessment","D_assess_hash"),("service","D_srv_hash")):
                expected_fields[field] = expected_stage_hashes[str(stage)][role]
            if any(row[k] != v for k,v in expected_fields.items()):
                raise RuntimeError("Stored CSV inputs differ from actual verified F1 reference")
        entries[name] = {"task":task,"receipt":receipt,"rows":rows,
                         "csv_sha256":p.file_sha256(csv_path),"receipt_sha256":p.file_sha256(receipt_path)}
    expected_csv = {k+".csv" for k in entries}
    expected_receipts = {k+".integrity.json" for k in entries}
    raw = RESULTS / "raw"
    if raw.exists():
        observed_csv = {x.name for x in raw.glob("*.csv")}
        observed_receipts = {x.name for x in raw.glob("*.integrity.json")}
        if observed_csv != expected_csv or observed_receipts != expected_receipts:
            raise RuntimeError("Unreceipted/unrecognized final output; preserve and stop")
    if require_complete and len(entries) != 1200: raise RuntimeError("1200 complete new receipts required")
    return entries

def paired_groups(entries):
    groups = {}
    for entry in entries.values():
        task = entry["task"]
        groups.setdefault(f"{task['center_id']}/{task['seed']}/{task['scenario']}",[]).append(entry)
    complete = {}
    for key, values in groups.items():
        if len(values) != 5: continue
        if {(v["task"]["method"],v["task"]["config_id"]) for v in values} != set(METHODS):
            raise RuntimeError("Duplicate/incomplete five-method group")
        first = values[0]["rows"]
        for other in values[1:]:
            for left,right in zip(first,other["rows"]):
                if any(left[f] != right[f] for f in INPUT_FIELDS):
                    raise RuntimeError(f"New exogenous/initial/deployment pairing failure: {key}")
        complete[key] = {"five_methods":True,"all_24_stage_input_fields_equal":True,
                         "initial_state_hash":first[0]["initial_state_hash"],
                         "scenario_hash":first[0]["scenario_hash"],
                         "deployment_tier":first[0]["deployment_tier"],
                         "deployment_filter_hash":first[0]["deployment_filter_hash"],
                         "bank_hash":first[0]["bank_hash"],
                         "receipt_sha256":{v["task"]["method"]:v["receipt_sha256"] for v in values}}
    return complete

def _new_phase_attempt(phase):
    """Reserve one new attempt directory; all earlier evidence stays untouched."""
    if phase not in {"initial", "minimal", "full"}: raise RuntimeError("Unknown execution phase")
    phase_root = p.checked_path(RESULTS, f"execution/{phase}", must_exist=False)
    phase_root.mkdir(parents=True, exist_ok=True)
    observed = []
    for child in phase_root.iterdir():
        if not child.is_dir() or not child.name.startswith(f"A_{phase.upper()}_"):
            raise RuntimeError("Unrecognized pre-existing phase evidence; refuse overwrite")
        suffix = child.name.rsplit("_", 1)[-1]
        if len(suffix) != 4 or not suffix.isdigit() or int(suffix) < 1:
            raise RuntimeError("Malformed phase attempt identity")
        observed.append(int(suffix))
    number = max(observed, default=0) + 1
    if number > 9999: raise RuntimeError("Phase attempt inventory exhausted")
    attempt_id = f"A_{phase.upper()}_{number:04d}"
    relative = f"execution/{phase}/{attempt_id}"
    p.checked_path(RESULTS, relative, must_exist=False).mkdir(exist_ok=False)
    return attempt_id, relative


def _retry_descriptors(manifest, selected):
    """Only exact failed-task RNG artifacts authorize a changed worker schedule.

    Absence of RNG means the frozen run_one body was never entered; the bound
    failure receipt explicitly records that boundary. No failure is selected by
    model outcome. Partial final publications or interrupted tasks without an
    explicit failure/RNG evidence chain remain blocking integrity conditions.
    """
    result = {}
    for task in selected:
        name = stem(task)
        folder = p.checked_path(RESULTS, f"attempts/{name}", must_exist=False)
        if not folder.exists(): continue
        failures = []
        captured_failures = []
        for path in sorted(folder.glob("*/*/failure.json")):
            path = p.regular_path(path)
            item = p.read_json(path)
            if (item.get("task") != task or item.get("status") not in {"FAILED", "INTERRUPTED"}
                    or item.get("completed_valid") is not False
                    or item.get("manifest_digest") != manifest["manifest_digest"]
                    or item.get("input_bundle_digest") != manifest["input_bundle_digest"]
                    or item.get("environment_binding") != p.canonical_hash(manifest["environment"])):
                raise RuntimeError("Failed-task retry provenance differs")
            if item.get("rng_relative") is None:
                if item.get("failed_before_rng_capture") is not True:
                    raise RuntimeError("Failure without a certified pre-run RNG boundary cannot be retried")
            else:
                rng_path = p.checked_path(RESULTS, item["rng_relative"])
                if p.file_sha256(rng_path) != item.get("rng_file_sha256"):
                    raise RuntimeError("Failed-task RNG bytes changed")
                rng = p.read_json(rng_path)
                body = {k:v for k,v in rng.items() if k != "state_digest"}
                if (rng.get("state_digest") != p.canonical_hash(body)
                        or rng.get("bindings",{}).get("task") != task
                        or rng.get("bindings",{}).get("input_bundle_digest") != manifest["input_bundle_digest"]
                        or rng.get("bindings",{}).get("environment_binding") != p.canonical_hash(manifest["environment"])):
                    raise RuntimeError("Failed-task RNG scientific binding differs")
                captured_failures.append(path)
            failures.append(path)
        pending_rng = list(folder.glob("*/*/rng_before.json"))
        pending_receipts = list(folder.glob("*/*/receipt.json"))
        if pending_receipts:
            raise RuntimeError("Unpublished completed attempt requires independent recovery audit; no rerun")
        if any(not (path.parent/"failure.json").is_file() for path in pending_rng):
            raise RuntimeError("Interrupted task lacks explicit failure/RNG receipt; preserve and stop")
        if failures:
            # Attempt labels are zero-padded and chronologically allocated; this
            # chooses the latest failed attempt, never its service loss.
            # A later ordinary import/setup failure before RNG capture must not
            # erase an earlier captured original-task RNG state. Preserve and
            # replay the most recent available captured state for this task.
            latest = (captured_failures or failures)[-1]
            result[name] = {"failed_receipt_relative":latest.relative_to(RESULTS).as_posix(),
                            "failed_receipt_sha256":p.file_sha256(latest)}
    return result


def dispatch(manifest, phase, worker_count, selected):
    if worker_count not in (1,2,3): raise RuntimeError("At most three workers")
    if not selected: raise RuntimeError("No pending tasks; refuse an empty execution attempt")
    if phase == "initial" and worker_count != 1: raise RuntimeError("Complete initial phase requires one worker")
    worker_count = min(worker_count, len(selected))
    children = []
    retries = {} if phase == "initial" else _retry_descriptors(manifest, selected)
    attempt_id, phase_root = _new_phase_attempt(phase)
    started = utc()
    try:
        for index in range(worker_count):
            worker_id = f"W{index+1}"
            subset = selected[index::worker_count]
            request = {"schema":"paper3-replication-worker-request-v1",
                       "manifest_digest":manifest["manifest_digest"],"mode":"initial" if phase=="initial" else "trajectory",
                       "worker_id":worker_id,"attempt_id":attempt_id,"worker_count":worker_count}
            if phase == "initial": request["cases"] = subset
            else:
                request["tasks"] = subset
                request["initial_state_manifest"] = "initial_state_manifest.json"
                request["retries"] = {stem(task):retries[stem(task)] for task in subset if stem(task) in retries}
            request_relative = f"{phase_root}/{worker_id}_request.json"
            publish(request_relative,request)
            cache = RESULTS / "runtime_cache" / phase / attempt_id / worker_id
            for folder in ("temp","torch","cuda"):
                target = p.regular_path(cache / folder, must_exist=False)
                if RESULTS not in target.parents: raise RuntimeError("Runtime path escape")
                target.mkdir(parents=True,exist_ok=False)
            env = dict(os.environ)
            env.update(TEMP=str(cache/"temp"),TMP=str(cache/"temp"),TORCH_HOME=str(cache/"torch"),CUDA_CACHE_PATH=str(cache/"cuda"))
            pycache = RESULTS / f"_never_created_pycache_{phase}_{attempt_id}_{worker_id}"
            if pycache.exists(): raise RuntimeError("Bytecode prefix collision")
            command = [sys.executable,"-I","-S","-B","-X",f"pycache_prefix={pycache}",
                       str(EXECUTOR/"executor_worker.py"),"--manifest",str(RESULTS/"provenance_manifest.json"),
                       "--mode",request["mode"],"--request-file",str(RESULTS/request_relative),
                       "--worker-id",worker_id,"--attempt-id",attempt_id]
            log_path = p.regular_path(RESULTS/f"{phase_root}/{worker_id}.log",must_exist=False)
            log = log_path.open("xb")
            process = subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                       env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            children.append((worker_id,process,log))
            publish(f"{phase_root}/{worker_id}_process.json",{"pid":process.pid,"command":command,"started":utc(),
                "request_sha256":p.file_sha256(RESULTS/request_relative),"temporary_cache_only_environment_overrides":{k:env[k] for k in ("TEMP","TMP","TORCH_HOME","CUDA_CACHE_PATH")}})
        previous = None
        while any(child.poll() is None for _,child,_ in children):
            failed = [(name,child.returncode) for name,child,_ in children if child.poll() not in (None,0)]
            if failed: raise RuntimeError(f"Worker failure; preserve outputs and stop phase: {failed}")
            count = len(list((RESULTS/"raw").glob("*.integrity.json"))) if (RESULTS/"raw").exists() else 0
            if count != previous:
                print(json.dumps({"phase":phase,"completed_receipts":count,"timestamp":utc()}),flush=True)
                previous = count
            time.sleep(5)
        exits = {name:child.returncode for name,child,_ in children}
        if any(value != 0 for value in exits.values()): raise RuntimeError(f"Worker failure: {exits}")
        publish(f"{phase_root}/completion.json",{"phase":phase,"attempt_id":attempt_id,"manifest_digest":manifest["manifest_digest"],
            "start":started,"finish":utc(),"worker_count":worker_count,"worker_exit_codes":exits,"success":True,
            "preassigned_task_count":len(selected),"performance_based_continuation":False})
    except BaseException as error:
        for _,child,_ in children:
            if child.poll() is None: child.terminate()
        for _,child,_ in children: child.wait()
        publish(f"{phase_root}/failure.json",{"phase":phase,"attempt_id":attempt_id,"manifest_digest":manifest["manifest_digest"],
            "start":started,"finish":utc(),"error":f"{type(error).__name__}:{error}","outputs_preserved":True,"no_automatic_protocol_change":True})
        raise
    finally:
        for _,_,log in children: log.close()
    return {"attempt_id":attempt_id,"relative":phase_root,"worker_count":worker_count}

def run(args):
    if args.phase == "prepare":
        if (RESULTS/"provenance_manifest.json").exists(): raise RuntimeError("Source freeze exists; no overwrite")
        allowed_existing = {"RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md","stage_c_tests"}
        if {x.name for x in RESULTS.iterdir()} - allowed_existing:
            raise RuntimeError("Unexpected pre-existing output before new source freeze; stop without overwrite")
        if args.test_attempt < 1: raise RuntimeError("Valid executed synthetic test attempt required")
        test_evidence = p.read_json(p.checked_path(RESULTS,f"stage_c_tests/attempt{args.test_attempt:03d}/results.json"))
        if test_evidence.get("all_pass") is not True: raise RuntimeError("Independent executor tests must pass before freeze")
        actual_implementation = {x.relative_to(EXECUTOR).as_posix():p.file_sha256(x)
                                 for x in EXECUTOR.rglob("*.py")}
        if test_evidence.get("implementation_sha256") != actual_implementation:
            raise RuntimeError("Executor changed after independent tests; repeat all executor tests")
        if not getattr(args, "model_runtime", None): raise RuntimeError("Reviewed independent model-runtime descriptor required")
        model_runtime_path = p.regular_path(args.model_runtime)
        if (test_evidence.get("independent_model_runtime_used") is not True or
                test_evidence.get("independent_model_runtime_descriptor_sha256") != p.file_sha256(model_runtime_path)):
            raise RuntimeError("Executor synthetic tests must pass in this exact independent model environment before freeze")
        model_runtime = p.read_json(model_runtime_path)
        model_runtime["descriptor_source_file"] = str(model_runtime_path)
        model_runtime["descriptor_source_sha256"] = p.file_sha256(model_runtime_path)
        manifest = p.freeze_provenance(REPO,INPUT_RUN,RESULTS,EXECUTOR,model_runtime=model_runtime,
            progress=lambda x:print(json.dumps(x),flush=True))
        publish("input_reference_manifest.json",{"schema":"paper3-fixed-F1-input-reference-v1","manifest_digest":manifest["manifest_digest"],
            "input_run":str(INPUT_RUN),"input_bundle_digest":manifest["input_bundle_digest"],"files":manifest["input_files_sha256"],
            "generation_performed_by_executor":False,"all_methods_read_same_F1":True,"provisional_requires_initial_and_full_parity":True})
        print(json.dumps({"phase":"prepare","manifest_digest":manifest["manifest_digest"]}),flush=True)
        return
    manifest = load_manifest()
    p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
    if args.phase == "initial":
        if args.workers != 1: raise RuntimeError("Initial-only phase is one separate process")
        selected = [{"center_id":c,"seed":s} for c in range(33000,33020) for s in (7311,7312,7313)]
        attempt = dispatch(manifest,"initial",1,selected)
        if not (RESULTS/"initial_state_manifest.json").is_file(): raise RuntimeError("Initial certificate missing")
    elif args.phase == "minimal":
        existing = accepted_records(manifest)
        expected_minimal = {stem(task) for task in tasks()[:5]}
        if set(existing) - expected_minimal: raise RuntimeError("Minimal resume cannot mix unrelated tasks")
        if len(existing) == 5:
            if not (RESULTS/"stage_c_minimal_gate.json").is_file(): raise RuntimeError("Complete minimal outputs require existing checked gate or independent publication recovery")
            print(json.dumps({"phase":"minimal","already_completed_and_verified":True}),flush=True)
            return
        attempt = dispatch(manifest,"minimal",args.workers,[task for task in tasks()[:5] if stem(task) not in existing])
        records = accepted_records(manifest)
        groups = paired_groups(records)
        if len(records) != 5 or set(groups) != {"33000/7311/C0"}: raise RuntimeError("Minimal five-method integrity check failed")
        p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
        publish("stage_c_minimal_gate.json",{"stage_c_pass":True,"manifest_digest":manifest["manifest_digest"],"predeclared_group":"33000/7311/C0",
            "completed_trajectories":5,"groups":groups,"performance_used_for_gate":False,"included_in_predeclared_new_1200":True})
    elif args.phase == "full":
        gate = p.read_json(p.checked_path(RESULTS,"stage_c_minimal_gate.json"))
        if gate.get("stage_c_pass") is not True or gate.get("manifest_digest") != manifest["manifest_digest"]:
            raise RuntimeError("Stage C integrity gate required")
        existing = accepted_records(manifest)
        selected = [t for t in tasks() if stem(t) not in existing]
        if not selected:
            if not (RESULTS/"full_experiment_integrity_gate.json").is_file(): raise RuntimeError("Complete outputs require existing checked gate or independent publication recovery")
            print(json.dumps({"phase":"full","already_completed_and_verified":True}),flush=True)
            return
        attempt = dispatch(manifest,"full",args.workers,selected)
        records = accepted_records(manifest,require_complete=True)
        groups = paired_groups(records)
        if len(groups) != 240: raise RuntimeError("240 paired groups required; statistics forbidden")
        p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
        publish("full_experiment_integrity_gate.json",{"scientific_integrity_pass":True,"manifest_digest":manifest["manifest_digest"],
            "trajectories":1200,"paired_groups":240,"groups":groups,"old_results_reused":False,
            "all_inputs_F1":True,"future_flags_false":True,"outcomes_used_to_select_protocol":False,
            "point_estimates_or_bootstrap_not_yet_computed":True,"not_unseen_heldout":True})
    else: raise RuntimeError("Unknown phase")
    final = p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
    # The phase proof belongs to this exclusive dispatch attempt. It is never
    # substituted by or written over a proof from an earlier failed attempt.
    relative = attempt["relative"]
    publish(f"{relative}/phase_integrity_end.json",final)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("prepare","initial","minimal","full"),required=True)
    parser.add_argument("--workers",type=int,default=3)
    parser.add_argument("--test-attempt",type=int,default=1)
    parser.add_argument("--model-runtime", help="Explicit reviewed independent Python 3.11 venv descriptor; required for prepare")
    args = parser.parse_args()
    run(args)

if __name__ == "__main__": main()
