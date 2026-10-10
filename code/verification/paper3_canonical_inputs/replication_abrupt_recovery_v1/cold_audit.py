"""Pure metadata audit of an already-disappeared execution, never process control.

This is distinct from a suspended live-worker transition. It verifies saved
provenance and truthful absence observations; it cannot infer the old exit code,
exit actor, or a worker exception. Inputs supplied by a collector are not an
independent authentication of that collector.
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

class ColdAuditError(RuntimeError):
    pass

def require(value, message):
    if not value:
        raise ColdAuditError(message)

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
                      parse_constant=lambda value: (_ for _ in ()).throw(ColdAuditError("nonfinite JSON")))

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


ROOT_SHA = "f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8"
EXPECTED_PIDS = (22732,16880,30160,26012,36468,20440,776)
PENDING_TASK = {"center_id":33002,"seed":7311,"scenario":"C0","method":"B8","config_id":"B8_AlwaysOpen_ratio10"}

def audit_snapshot(snapshot):
    try:
        return _audit_snapshot(snapshot)
    except ColdAuditError:
        raise
    except (KeyError,TypeError,ValueError,OverflowError) as error:
        raise ColdAuditError("malformed cold snapshot: "+str(error)) from error

def _audit_snapshot(s):
    require(s.get("schema") == "paper3-abrupt-recovery-snapshot-v1", "cold snapshot schema mismatch")
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
    request_binding = s["request_binding"]
    require(request_binding["observed_sha256_before"] == s["request_sha256"] == request_binding["observed_sha256_after"], "request SHA changed")
    request = decoded_json(request_binding["payload_base64"], s["request_sha256"])
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
    require(len(records) == 123 and s["unknown_artifacts"] == [], "expected exact 123 completed tasks and zero partial artifacts")
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

    require(task == PENDING_TASK, "unexpected interrupted task")
    require(s["root_handoff_sha256"] == ROOT_SHA, "bound root handoff changed")
    require(s["old_terminal_records"] == {"sequence_stopped":False,"finalizer_stopped":False,
        "phase_launcher_finished":False,"phase_completion":False,"phase_failure":False,
        "worker_completion":False,"pending_failure":False}, "old terminal conflicts or fabricated old evidence")
    absence=s["process_absence"]
    require(isinstance(absence,list) and len(absence)==7 and {x["pid"] for x in absence}==set(EXPECTED_PIDS), "original seven process inventory differs")
    for info in absence:
        require(0 <= (captured-instant(info["observed_utc"])).total_seconds() <= 60, "process absence sample stale/future")
        require(info.get("original_identity_absent") is True and info.get("old_exit_code") is None,
            "old process still alive or invented unavailable exit code")
        if info["observation"] == "OPEN_PROCESS_INVALID_PARAMETER":
            require(info.get("winerror")==87 and info.get("observed_creation_filetime") is None,
                "absence is not actual OpenProcess error87")
        elif info["observation"] == "PID_REUSED":
            observed=info.get("observed_creation_filetime");expected=info.get("expected_creation_filetime")
            known_identity_differs=(type(expected) is int and type(observed) is int and observed != expected)
            after_prior_absence=False
            if info.get("earlier_absence_observed_utc") is not None:
                prior=instant(info["earlier_absence_observed_utc"])
                require(prior <= instant(info["observed_utc"]), "earlier absence observation is future")
                delta=prior-datetime(1601,1,1,tzinfo=prior.tzinfo)
                prior_ticks=(delta.days*86400+delta.seconds)*10_000_000+delta.microseconds*10
                after_prior_absence=(type(observed) is int and observed > prior_ticks)
            require(known_identity_differs or after_prior_absence, "PID reuse not proved")
        else:
            require(False,"unverified original process disappearance")
    require(s["active_target_processes"] == [], "target execution process remains active")
    require(s["native_processes_modified"] is False and s["worker_exception_observed"] is False
        and s["termination_actor"] == "NOT_VERIFIED", "false native termination or worker failure assertion")
    require(s["stable_file_inventory"] is True and s["initial60_accepted_records_verified"] is True
        and s["model_or_generator_or_statistics_executed"] is False and s["performance_values_used"] is False,
        "cold byte stability or frozen initial60 acceptance absent")
    evidence = bound_maps(s["evidence_bindings"])
    initial_files = bound_maps(s["initial_file_bindings"])
    require(len(initial_files) == 120, "initial60 actual state/receipt inventory incomplete")
    for state in initial["states"]:
        for path_key,hash_key in (("path","sha256"),("receipt_path","receipt_sha256")):
            path=join(RESULTS,state[path_key]);h=state[hash_key]
            require(initial_files.get(path)==h and evidence.get(path)==h, "initial state bytes absent from evidence")
    require(evidence.get(absolute(REPO+"\\PAPER3_FINAL_REPLICATION_HANDOFF.md")) == ROOT_SHA,
        "root handoff absent from actual bound evidence")
    for entry in records:
        require(evidence.get(join(RESULTS,entry["csv_relative"])) == entry["csv_sha256"]
            and evidence.get(join(RESULTS,entry["receipt_relative"])) == entry["receipt_file_sha256"], "completed record absent from evidence map")
        for path,h in entry["bound_artifacts"].items():
            require(evidence.get(join(RESULTS,path)) == h, "completed artifact absent from actual evidence")
    require(evidence.get(join(RESULTS,rng_relative)) == artifact["file_sha256"], "RNG absent from evidence")
    resources=s["resources"]
    require(0 <= (captured-instant(resources["sampled_utc"])).total_seconds() <= 60, "resource sample stale/future")
    historical=resources["historical_worker_private_bytes"]
    minimum=max(7*GIB,2*historical+GIB)
    require(type(historical) is int and historical >= 3*GIB and resources["private_bytes_source"] == "CONSERVATIVE_BOUND_NOT_CURRENT_MEASUREMENT"
        and resources["requested_worker_count"] == 2 and resources["minimum_free_commit_bytes"] == minimum
        and type(resources["free_commit_bytes"]) is int and resources["free_commit_bytes"] >= minimum,
        "two-worker commit resource gate failed")
    require(instant(s["phase_started_utc"]) <= captured, "phase start after cold observation")
    result={"schema":"paper3-abrupt-recovery-pure-audit-v1","status":"COLD_SNAPSHOT_CONSISTENT",
        "all_checks_pass":True,"initial_cases":60,"original_files_unchanged":True,
        "frozen_sources_unchanged":True,"all_existing_records_verified":True,
        "models_generators_or_statistics_executed":False,"processes_modified":False,
        "eligible_for_truthful_interruption_receipt":True,"snapshot_digest":digest(s),
        "completed_trajectories":len(records),"complete_paired_groups":24,"pending_task":task,
        "pending_rng_relative":rng_relative,"pending_rng_file_sha256":artifact["file_sha256"],
        "pending_rng_state_digest":rng["state_digest"],"initial_state_manifest_sha256":INITIAL_MANIFEST_SHA256,
        "root_handoff_sha256":ROOT_SHA,"source_binding_count":len(source_map),"evidence_binding_count":len(evidence),
        "minimum_free_commit_bytes":minimum,"all_old_processes_absent":True,"unknown_or_partial_artifacts":0,
        "worker_exception_observed":False,"old_exit_code":None,"termination_actor":"NOT_VERIFIED",
        "no_performance_values_interpreted":True,"native_processes_modified":False,
        "independent_runtime_authenticity_certified":False,"model_output_worker_invariance_claimed":False}
    result["audit_digest"]=digest(result)
    return result

def failure_receipts(snapshot,audit,observer_sha256,created_utc):
    """Truthful NEW observer authored retry/phase receipts, never worker terminals."""
    require(audit_snapshot(snapshot)==audit and hex64(observer_sha256),"unaudited cold recovery proof")
    require(instant(created_utc)>=instant(snapshot["captured_utc"]),"receipt predates observation")
    manifest=snapshot["context"]["manifest"];task=audit["pending_task"]
    failure={"schema":"paper3-batch20-failed-task-receipt-v1","status":"INTERRUPTED","completed_valid":False,
        "task":task,"manifest_digest":MANIFEST_DIGEST,"input_bundle_digest":F1_DIGEST,
        "environment_binding":manifest["environment_binding"],
        "initial_state_hash":snapshot["context"]["initial_hashes"][f"{task['center_id']}_{task['seed']}"],
        "worker_id":"W1","attempt_id":"A_FULL_0001","rng_relative":audit["pending_rng_relative"],
        "rng_file_sha256":audit["pending_rng_file_sha256"],"failed_before_rng_capture":False,
        "producer":"external-cold-recovery-observer","worker_exception_observed":False,
        "error_type":"UnexpectedProcessDisappearance","termination_actor":"NOT_VERIFIED","exit_code":None,
        "original_worker_terminal_record":False,"observer_snapshot_sha256":observer_sha256,
        "message":"All seven previously recorded execution identities are now absent. The in-flight task has only its saved pre-run Torch RNG state and no partial or completed publication. The old exit code and termination actor are unavailable. This new receipt is authored by an independent cold observer, not a worker exception handler.",
        "created_utc":created_utc,"automatic_new_draw_retry":False,"originals_overwritten":False}
    phase={"schema":"paper3-external-cold-observer-phase-failure-v1","phase":"full","attempt_id":"A_FULL_0001",
        "manifest_digest":MANIFEST_DIGEST,"input_bundle_digest":F1_DIGEST,"status":"INTERRUPTED",
        "started":snapshot["phase_started_utc"],"finished":created_utc,"created_utc":created_utc,
        "error":"Original full-phase driver and worker disappeared without a saved terminal record. Exit cause and code are NOT_VERIFIED.",
        "error_type":"UnexpectedProcessDisappearance","exit_code":None,"child_exit_code":None,"external_observer":True,
        "original_driver_terminal_record":False,"worker_exception_observed":False,"termination_actor":"NOT_VERIFIED",
        "observer_snapshot_sha256":observer_sha256,"producer":"external-cold-recovery-observer",
        "performance_based_continuation":False,"originals_overwritten":False}
    return failure,phase
