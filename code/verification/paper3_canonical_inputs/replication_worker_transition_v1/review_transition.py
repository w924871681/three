"""Pure supplied-evidence review for the single authorized V3 W1->two-worker switch.

No filesystem, package/model import, process control, RNG mutation, or statistics.
The controller must truthfully collect actual native/file observations. A passing
pure audit proves their internal byte/identity consistency, not their authenticity
independently of that controller. See snapshot_schema.json.

Post-termination API: audit_external_interruption(receipt, journal), where journal
is {file_sha256, payload_base64}. Journal JSON must have schema
paper3-external-worker-termination-journal-v1, snapshot, snapshot_audit,
termination={pid,creation_time_utc,creation_filetime,method:'TerminateProcess',confirmed_dead:true,
exit_code:nonzero-int,worker_exception_observed:false,terminated_utc}.
The external failure receipt keeps the frozen retry schema but must add
producer='external-migration-controller', worker_exception_observed=false,
external_termination_journal_sha256. No fabricated traceback is accepted.
"""
from __future__ import annotations
import base64
from datetime import datetime
import hashlib
import json
from pathlib import PureWindowsPath
from subprocess import list2cmdline

REPO = r"D:\dt-talk\DT_LIFECYCLE_ESCALATION"
EXECUTOR = REPO + r"\verification\paper3_canonical_inputs\replication_executor_batch20_env_v3"
RESULTS = REPO + r"\results\p7_7_integrity_replication_batch20_env_v3"
PYTHON = REPO + r"\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1\Scripts\python.exe"
MANIFEST_DIGEST = "7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
F1_DIGEST = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
INITIAL_MANIFEST_SHA256 = "18b329d5468d85961e28f24a1f45df9b2191530a9b26244642dbf6d2304e19dc"
GIB = 1024 ** 3
BASE_PID, BASE_FILETIME = 36468, 134360128955562955
WRAPPER_PID, WRAPPER_FILETIME = 26012, 134360128955140400
METHODS = (("B0", "B0_Frozen_ratio10"), ("B1", "B1_AlwaysMaintainP50_ratio10"),
           ("B2", "B2_RAVM_ratio10"), ("B8", "B8_AlwaysOpen_ratio10"),
           ("P7.7", "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"))
INPUT_FIELDS = ("scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash", "center_type",
                "deployment_tier", "deployment_filter_hash", "bank_hash", "update_end_ts",
                "decision_ts", "scenario_role", "initial_state_hash")

class TransitionAuditError(RuntimeError):
    pass

def require(value, message):
    if not value:
        raise TransitionAuditError(message)

def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()

def hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result

def decoded_json(payload_base64, expected_sha):
    require(hex64(expected_sha), "invalid expected file SHA")
    payload = base64.b64decode(payload_base64, validate=True)
    require(sha_bytes(payload) == expected_sha, "payload does not match saved file SHA")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(TransitionAuditError("nonfinite JSON")))

def instant(value):
    require(isinstance(value, str), "timestamp not a string")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "timestamp offset absent")
    return result

def absolute(value):
    path = PureWindowsPath(value)
    require(path.is_absolute() and ".." not in path.parts, "unsafe absolute evidence path")
    return str(path).casefold()

def relative(value):
    path = PureWindowsPath(value)
    require(not path.is_absolute() and path.parts and ".." not in path.parts, "unsafe relative evidence path")
    return path.as_posix()

def join(root, value):
    return absolute(str(PureWindowsPath(root) / relative(value)))

def normalized_map(value):
    require(isinstance(value, dict) and value, "empty binding map")
    result = {}
    for name, expected in value.items():
        key = absolute(name)
        require(key not in result and hex64(expected), "aliased path or invalid binding SHA")
        result[key] = expected
    return result

def bound_maps(value):
    expected = normalized_map(value["expected"])
    require(normalized_map(value["observed"]) == expected, "actual file binding mismatch")
    return expected

def tasks():
    return [{"center_id": c, "seed": s, "scenario": q, "method": m, "config_id": i}
            for c in range(33000, 33020) for s in (7311, 7312, 7313)
            for q in ("C0", "C1", "C3", "C4") for m, i in METHODS]

def task_key(task):
    return tuple(task[name] for name in ("center_id", "seed", "scenario", "method", "config_id"))

def stem(task):
    return "{config_id}_{center_id}_{seed}_{scenario}".format(**task)

def rng_tensor(value):
    require(value.get("dtype") == "uint8" and type(value.get("byte_count")) is int
            and value["byte_count"] > 0 and value.get("shape") == [value["byte_count"]], "RNG tensor schema mismatch")
    raw = base64.b64decode(value["base64"], validate=True)
    require(len(raw) == value["byte_count"] and sha_bytes(raw) == value["sha256"], "RNG tensor bytes mismatch")

def expected_inputs(bundle, task, initial_hash):
    center, scenario = task["center_id"], task["scenario"]
    base, scene = bundle["base"][str(center)], bundle["scenarios"][f"{center}/{scenario}"]
    result = []
    for stage in range(1, 25):
        update = bundle["roles"][f"{center}/{scenario}/{stage}/update"]
        row = {"stage": stage, "scenario_hash": scene["legacy_scenario_hash"],
               "center_type": base["profile"]["center_type"], "deployment_tier": base["profile"]["budget_tier"],
               "bank_hash": base["deployment"]["bank_hash"], "deployment_filter_hash": base["deployment"]["deployment_filter_hash"],
               "scenario_role": scene["metadata"]["definition"], "update_end_ts": str(update["update_end_ts"]),
               "decision_ts": str(update["decision_ts"]), "initial_state_hash": initial_hash}
        for role, field in (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash")):
            row[field] = bundle["roles"][f"{center}/{scenario}/{stage}/{role}"]["legacy_role_hash"]
        result.append(row)
    return result

def audit_snapshot(snapshot):
    """Fail closed; never stop a process or create a scientific certificate."""
    try:
        return _audit_snapshot(snapshot)
    except TransitionAuditError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise TransitionAuditError("malformed snapshot: " + str(error)) from error

def _audit_snapshot(s):
    require(s.get("schema") == "paper3-worker-transition-snapshot-v1", "snapshot schema mismatch")
    captured = instant(s["captured_utc"])
    context = s["context"]; manifest = context["manifest"]
    unsigned = dict(manifest); unsigned.pop("manifest_digest", None)
    require(manifest.get("manifest_digest") == MANIFEST_DIGEST and digest(unsigned) == MANIFEST_DIGEST, "frozen manifest mismatch")
    require(manifest["input_bundle_digest"] == F1_DIGEST, "F1 identity changed")
    paths = manifest["paths"]
    require(absolute(paths["repo"]) == absolute(REPO) and absolute(paths["results_root"]) == absolute(RESULTS)
            and absolute(paths["executor_root"]) == absolute(EXECUTOR), "frozen roots mismatch")
    require(manifest.get("original_records_mixed_into_new_results") is False, "mixed historical provenance")
    require(manifest.get("historical_environment_reproduced") is False, "false historical-runtime assertion")
    source_map = bound_maps(s["source_bindings"])
    critical, executor = manifest["critical_files_sha256"], manifest["executor_sha256"]
    require(len(critical) == 94 and len(executor) == 18, "critical/executor source inventory changed")
    for root, items in ((REPO, critical), (EXECUTOR, executor)):
        for name, expected in items.items():
            require(source_map.get(join(root, name)) == expected, "mandatory scientific source binding absent")
    input_map = bound_maps(s["input_files"])
    require(input_map == {join(paths["input_run"], name): h for name, h in manifest["input_files_sha256"].items()}, "F1 file inventory mismatch")
    initial = decoded_json(context["initial_manifest_payload_base64"], INITIAL_MANIFEST_SHA256)
    require(initial["manifest_digest"] == MANIFEST_DIGEST and initial["input_bundle_digest"] == F1_DIGEST
            and initial["completed_cases"] == 60 and len(initial["states"]) == 60, "initial60 certificate mismatch")
    initial_hashes = {f"{x['center_id']}_{x['seed']}": x["initial_state_hash"] for x in initial["states"]}
    require(len(initial_hashes) == 60 and set(initial_hashes) == {f"{c}_{seed}" for c in range(33000,33020) for seed in (7311,7312,7313)}
            and all(hex64(h) for h in initial_hashes.values()) and context["initial_hashes"] == initial_hashes, "initial hash coverage mismatch")
    runtime = context["scientific_runtime"]
    require(digest(runtime) == initial["scientific_runtime_signature"], "scientific runtime map mismatch")
    bundle = decoded_json(context["f1_context_payload_base64"], manifest["stage_b_bindings"]["F1"])
    require(bundle.get("context") == "F" and bundle.get("replicate") == "F1" and bundle["input_bundle_digest"] == F1_DIGEST
            and tuple(len(bundle[k]) for k in ("base","scenarios","roles")) == (20,80,5760), "bound F1 context coverage mismatch")
    worker = s["worker"]; identity = worker["expected_identity"]
    require(set(identity) == {"pid","creation_time_utc","creation_filetime","executable","command","request_path","request_sha256","worker_id","attempt_id"}
            and worker["observed_identity"] == identity, "live process identity changed")
    require(type(identity["pid"]) is int and identity["pid"] == BASE_PID and type(identity["creation_filetime"]) is int
            and identity["creation_filetime"] == BASE_FILETIME and instant(identity["creation_time_utc"]) <= captured, "invalid process identity")
    require(identity["worker_id"] == "W1" and identity["attempt_id"] == "A_FULL_0001", "wrong original worker")
    base_python = str(PureWindowsPath(manifest["environment"]["base_prefix"]) / "python.exe")
    require(absolute(identity["executable"]) == absolute(base_python), "wrong scientific base process executable")
    env_files = normalized_map(manifest["environment"]["bound_files_sha256"])
    require(absolute(base_python) in env_files, "scientific base executable absent from frozen environment byte inventory")
    request_path = str(PureWindowsPath(RESULTS) / "execution/full/A_FULL_0001/W1_request.json")
    require(absolute(identity["request_path"]) == absolute(request_path), "wrong worker request path")
    command = identity["command"]
    expected_command = [PYTHON,"-I","-S","-B","-X",f"pycache_prefix={RESULTS}\\_never_created_pycache_full_A_FULL_0001_W1",
                        EXECUTOR+"\\executor_worker.py","--manifest",RESULTS+"\\provenance_manifest.json","--mode","trajectory",
                        "--request-file",request_path,"--worker-id","W1","--attempt-id","A_FULL_0001"]
    require(command == expected_command, "worker command not exact frozen invocation")
    wrapper = worker["wrapper_identity"]
    expected_wrapper = {"pid":WRAPPER_PID,"creation_filetime":WRAPPER_FILETIME,"executable":PYTHON,
                        "command":expected_command,"scientific_child_pid":BASE_PID}
    require(wrapper["expected"] == expected_wrapper and wrapper["observed"] == expected_wrapper, "wrapper/base ancestry identity mismatch")
    native = worker["native_processes"]
    require(isinstance(native,list) and len(native) == 2, "two actual native process observations required")
    for info,pid,ticks,image in ((native[0],BASE_PID,BASE_FILETIME,base_python),(native[1],WRAPPER_PID,WRAPPER_FILETIME,PYTHON)):
        require(info["pid"] == pid and info["creation_filetime"] == ticks and absolute(info["image"]) == absolute(image)
                and info["exit_code"] == 259 and type(info["private_bytes"]) is int and info["private_bytes"] > 0,
                "actual kernel process identity/liveness mismatch")
        command_line = ('"'+base_python+'" '+list2cmdline(expected_command[1:])) if pid == BASE_PID else list2cmdline(expected_command)
        require(info["command_line"] == command_line, "actual native command line differs from exact frozen request")
    require(native[0]["parent_pid"] == WRAPPER_PID, "scientific base process not actual child of frozen wrapper")
    require(all(worker.get(k) is True for k in ("suspended","suspension_verified","snapshot_stable"))
            and worker["active_scientific_worker_pids"] == [identity["pid"]], "worker not exclusively suspended/stable")
    request_binding = s["request_binding"]
    require(request_binding["observed_sha256_before"] == identity["request_sha256"] == request_binding["observed_sha256_after"], "request SHA changed")
    request = decoded_json(request_binding["payload_base64"], identity["request_sha256"])
    require(request == s["request"] and request.get("schema") == "paper3-replication-worker-request-v1"
            and request.get("manifest_digest") == MANIFEST_DIGEST and request.get("mode") == "trajectory"
            and type(request.get("worker_count")) is int and request.get("worker_count") == 1 and request.get("worker_id") == "W1" and request.get("attempt_id") == "A_FULL_0001"
            and request.get("retries") == {} and request.get("initial_state_manifest") == "initial_state_manifest.json", "original request changed")
    matrix = tasks(); require(request["tasks"] == matrix[5:], "original1195 task order changed")
    records = s["raw_entries"]; require(isinstance(records,list) and len(records) >= 5, "missing previously completed trajectories")
    completed = {}
    for item in records:
        receipt = decoded_json(item["receipt_payload_base64"], item["receipt_file_sha256"])
        require(receipt == item["receipt"] and item["receipt_file_sha256"] == item["receipt_file_sha256_rechecked"], "receipt payload/snapshot changed")
        task = receipt["task"]; key = task_key(task); require(task in matrix and key not in completed, "unknown/duplicate completed task")
        name = stem(task)
        require(relative(item["csv_relative"]) == f"raw/{name}.csv" and relative(item["receipt_relative"]) == f"raw/{name}.integrity.json", "raw filename/task mismatch")
        initial_hash = initial_hashes[f"{task['center_id']}_{task['seed']}"]
        required = {"schema":"paper3-batch20-replication-trajectory-receipt-v1","valid":True,"trajectory_rows":24,
            "manifest_digest":MANIFEST_DIGEST,"input_bundle_digest":F1_DIGEST,"environment_binding":manifest["environment_binding"],
            "initial_state_hash":initial_hash,"initial_state_manifest_sha256":INITIAL_MANIFEST_SHA256,
            "source_bindings_digest":digest(critical),"executor_bundle_digest":digest(executor),
            "scientific_runtime_signature":initial["scientific_runtime_signature"],"runner_hash":critical["scripts/run_p7_7_final.py"],
            "implementation_hash":critical["core/p7.py"],"protocol_hash":critical["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
            "full_24_stage_input_parity_checked":True,"future_online_access_violation_count":0,"performance_based_continuation":False,"statistics_executed":False}
        require(all(receipt.get(k) == v and type(receipt.get(k)) is type(v) for k,v in required.items()), "completed receipt scientific binding mismatch")
        require(hex64(item["csv_sha256"]) and item["csv_sha256"] == item["csv_sha256_rechecked"] == receipt["output_hash"], "actual CSV hash changed")
        expected_artifacts = {receipt["audit_relative"]:receipt["audit_hash"],receipt["rng_relative"]:receipt["rng_file_sha256"],
                              receipt["attempt_csv_relative"]:receipt["attempt_csv_hash"],receipt["runtime_receipt_path"]:receipt["runtime_receipt_sha256"]}
        require(item["bound_artifacts"] == expected_artifacts and len(expected_artifacts) == 4
                and receipt["attempt_csv_hash"] == receipt["output_hash"] and all(hex64(v) for v in expected_artifacts.values()), "completed artifact hash mismatch")
        for path in expected_artifacts: relative(path)
        expected = expected_inputs(bundle,task,initial_hash)
        require(item["expected_stage_inputs"] == expected, "stage reference is not bound F1 metadata")
        rows = item["input_projection"]
        require(len(rows) == 24 and [str(x["stage"]) for x in rows] == [str(i) for i in range(1,25)], "actual24 stage coverage mismatch")
        for row, reference in zip(rows,expected):
            require(all(row[k] == str(v) for k,v in task.items()), "CSV task changed")
            require(all(str(row[k]) == str(reference[k]) for k in INPUT_FIELDS), "CSV inputs differ from bound F1")
            require(row["future_service_used_in_decision"] == "False" and row["online_future_service_used"] == "False", "future service accessed")
        require(rows[0]["identity_before"] == "msa_a57_pt", "initial identity changed")
        stages = [{"stage":x["stage"],**{k:x[k] for k in ("D_upd_hash","D_assess_hash","D_srv_hash")}} for x in expected]
        require(receipt["stage_input_hashes"] == stages and all(receipt[k] == expected[0][k] for k in ("deployment_tier","deployment_filter_hash","bank_hash")), "receipt input/deployment changed")
        completed[key] = receipt
    require(set(completed) == {task_key(t) for t in matrix[:len(records)]}, "completed tasks are not exact original serial prefix")
    require(len(records) < 1200 and s["unknown_artifacts"] == [], "unknown or partial artifacts present")
    pending = s["pending"]; require(isinstance(pending,list) and len(pending) == 1, "exactly one RNG-only in-flight task required")
    task = matrix[len(records)]; item = pending[0]
    require(item["task"] == task and set(item["artifacts"]) == {"rng_before.json"}, "pending task not exact next task or extra artifacts")
    artifact = item["artifacts"]["rng_before.json"]
    rng_relative = f"attempts/{stem(task)}/A_FULL_0001/W1/rng_before.json"
    require(relative(artifact["relative_path"]) == rng_relative, "pending RNG path mismatch")
    rng = decoded_json(artifact["payload_base64"], artifact["file_sha256"])
    bindings = {"task":task,"input_bundle_digest":F1_DIGEST,"source_bindings_digest":digest(critical),
                "environment_binding":manifest["environment_binding"],"final_configuration_sha256":critical["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
                "expected_initial_state_hash":initial_hashes[f"{task['center_id']}_{task['seed']}"]}
    require(rng.get("schema") == "paper3-original-task-torch-rng-v1" and rng.get("manual_seed_called") is False
            and rng.get("scope") == "EXISTING_EXECUTION_RNG_PROVENANCE" and rng.get("bindings") == bindings, "pending RNG scientific binding mismatch")
    body = dict(rng); body.pop("state_digest",None)
    require(rng["state_digest"] == digest(body) and rng["torch_version"] == runtime["torch_version"]
            and rng["cuda_runtime"] == runtime["torch_cuda_build_version"], "pending RNG digest/runtime mismatch")
    rng_tensor(rng["cpu"])
    devices = runtime["cuda_devices"]
    require(len(rng["cuda"]) == len(devices), "RNG device count mismatch")
    for index,(state,device) in enumerate(zip(rng["cuda"],devices)):
        require(state["device_index"] == index and state["device_name"] == device["name"], "RNG device identity mismatch")
        rng_tensor(state["state"])
    resources = s["resources"]
    require(0 <= (captured-instant(resources["sampled_utc"])).total_seconds() <= 60, "resource sample stale/future")
    free, private, threshold = (resources[k] for k in ("free_commit_bytes","existing_worker_private_bytes","requested_minimum_free_commit_bytes"))
    require(all(type(x) is int and x > 0 for x in (free,private,threshold)) and resources["reserved_extra_worker_count"] == 1,
            "invalid resource observation")
    require(private == native[0]["private_bytes"], "resource private bytes not actual scientific process observation")
    require(threshold >= private+GIB and free >= threshold, "insufficient dynamic commit headroom for extra worker")
    result = {"schema":"paper3-worker-transition-pure-audit-v1","status":"SNAPSHOT_CONSISTENT","eligible_to_terminate":True,
        "snapshot_digest":digest(s),"completed_trajectories":len(records),"pending_task":task,
        "pending_rng_relative":rng_relative,"pending_rng_file_sha256":artifact["file_sha256"],"pending_rng_state_digest":rng["state_digest"],
        "source_binding_count":len(source_map),"input_file_binding_count":len(input_map),"minimum_free_commit_bytes":threshold,
        "independent_runtime_authenticity_certified":False,"new_unstarted_task_rng_equals_old_serial_path":False,
        "no_performance_values_interpreted":True,"process_or_filesystem_actions_performed":False}
    result["audit_digest"] = digest(result)
    return result

def audit_external_interruption(receipt, journal):
    """Validate honest external termination evidence, never fabricate worker proof."""
    try:
        record = decoded_json(journal["payload_base64"],journal["file_sha256"])
        require(record.get("schema") == "paper3-external-worker-termination-journal-v1", "termination journal schema mismatch")
        audited = audit_snapshot(record["snapshot"])
        require(record["snapshot_audit"] == audited, "pretermination snapshot audit differs")
        termination = record["termination"]; identity = record["snapshot"]["worker"]["expected_identity"]
        require(termination["pid"] == identity["pid"] and termination["creation_time_utc"] == identity["creation_time_utc"]
                and type(termination["creation_filetime"]) is int and termination["creation_filetime"] == identity["creation_filetime"]
                and termination["method"] == "TerminateProcess" and termination["confirmed_dead"] is True
                and type(termination["exit_code"]) is int and termination["exit_code"] != 0
                and termination["worker_exception_observed"] is False, "actual external termination not proven")
        require(instant(termination["terminated_utc"]) >= instant(record["snapshot"]["captured_utc"]), "termination precedes snapshot")
        context = record["snapshot"]["context"]; manifest=context["manifest"]; task=audited["pending_task"]
        expected = {"schema":"paper3-batch20-failed-task-receipt-v1","status":"INTERRUPTED","completed_valid":False,
            "task":task,"manifest_digest":MANIFEST_DIGEST,"input_bundle_digest":F1_DIGEST,"environment_binding":manifest["environment_binding"],
            "initial_state_hash":context["initial_hashes"][f"{task['center_id']}_{task['seed']}"],"worker_id":"W1","attempt_id":"A_FULL_0001",
            "rng_relative":audited["pending_rng_relative"],"rng_file_sha256":audited["pending_rng_file_sha256"],"failed_before_rng_capture":False,
            "producer":"external-migration-controller","worker_exception_observed":False,"error_type":"ExternalControlledInterruption",
            "external_termination_journal_sha256":journal["file_sha256"],"automatic_new_draw_retry":False,"originals_overwritten":False}
        require(all(receipt.get(k) == v and type(receipt.get(k)) is type(v) for k,v in expected.items()), "external interruption receipt binding/honesty mismatch")
        require("traceback" not in receipt and isinstance(receipt.get("message"),str) and receipt["message"], "fabricated worker traceback or missing truthful external message")
        require(instant(receipt["created_utc"]) >= instant(termination["terminated_utc"]), "receipt precedes actual termination")
        return {"status":"EXTERNAL_INTERRUPTION_EVIDENCE_CONSISTENT","journal_file_sha256":journal["file_sha256"],
                "snapshot_audit_digest":audited["audit_digest"],"worker_caught_exception_claimed":False,"actual_runtime_authenticity_independently_certified":False}
    except TransitionAuditError:
        raise
    except (KeyError,TypeError,ValueError,OverflowError) as error:
        raise TransitionAuditError("malformed external interruption proof: "+str(error)) from error
