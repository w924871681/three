"""Read-only completion, pairing, and exact-failed-RNG identity checks.

This module projects integrity fields only. It never uses loss values, ranks,
confidence intervals, or the sign of an experimental outcome.
"""
from __future__ import annotations

import base64
import csv
import hashlib
from pathlib import Path
from queue_store import IntegrityError, canonical, read_json, safe, sha, task_stem

PAIR_FIELDS = ("scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash",
               "center_type", "deployment_tier", "deployment_filter_hash", "bank_hash",
               "update_end_ts", "decision_ts", "scenario_role", "initial_state_hash")
METHODS = {"B0", "B1", "B2", "B8", "P7.7"}


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def rng_identity(value, expected_bindings, expected_runtime):
    require(value.get("schema") == "paper3-original-task-torch-rng-v1", "RNG schema differs")
    require(value.get("manual_seed_called") is False, "scheduler may not introduce a seed")
    require(value.get("scope") == "EXISTING_EXECUTION_RNG_PROVENANCE", "RNG provenance scope differs")
    require(value.get("torch_version") == expected_runtime["torch_version"]
            and value.get("cuda_runtime") == expected_runtime["torch_cuda_build_version"], "RNG runtime differs")
    require(value.get("bindings") == expected_bindings, "RNG belongs to different task/input/source/environment")
    require(value.get("state_digest") == canonical({k: v for k, v in value.items() if k != "state_digest"}), "RNG digest differs")
    require(isinstance(value.get("cuda"), list), "RNG CUDA states missing")
    devices = expected_runtime["cuda_devices"]
    require(len(value["cuda"]) == len(devices), "RNG device coverage differs")
    seen = set()
    for index, (entry, device) in enumerate(zip(value["cuda"], devices)):
        require(type(entry["device_index"]) is int and entry["device_index"] == index
                and device["index"] == index and entry["device_name"] == device["name"], "RNG CUDA identity differs")
        require(entry["device_index"] not in seen, "duplicate CUDA device state")
        seen.add(entry["device_index"])
    for state in [value["cpu"]] + [entry["state"] for entry in value["cuda"]]:
        raw = base64.b64decode(state["base64"], validate=True)
        require(len(raw) > 0 and type(state.get("byte_count")) is int
                and state.get("dtype") == "uint8" and state.get("shape") == [len(raw)]
                and state.get("byte_count") == len(raw)
                and hashlib.sha256(raw).hexdigest() == state.get("sha256"), "RNG byte identity differs")
    return value["state_digest"]


def retry_identity(root, task, descriptor, expected):
    """Validate existing failure + exact RNG; never create a new random draw."""
    path = safe(root, descriptor["failed_receipt_relative"], exists=True)
    require(sha(path) == descriptor["failed_receipt_sha256"], "failed receipt bytes differ")
    failure = read_json(path)
    require(failure.get("task") == task and failure.get("status") in ("FAILED", "INTERRUPTED")
            and failure.get("completed_valid") is False, "retry is not this incomplete task")
    for key in ("manifest_digest", "input_bundle_digest", "environment_binding"):
        require(failure.get(key) == expected[key], "retry provenance differs")
    relative = failure.get("rng_relative")
    if relative is None:
        require(failure.get("failed_before_rng_capture") is True, "missing uncertified pre-run RNG")
        return {"failed_before_rng_capture": True, "new_seed_introduced": False}
    rng_path = safe(root, relative, exists=True)
    require(sha(rng_path) == failure["rng_file_sha256"], "retry RNG file changed")
    state = rng_identity(read_json(rng_path), expected["rng_bindings"], expected["scientific_runtime"])
    return {"exact_failed_state_digest": state, "new_random_draw": False}


def validate_completion(root, task, expected):
    """Validate actual 24-stage stored bytes, audits, runtime and RNG references."""
    root = Path(root)
    name = task_stem(task)
    receipt_path = safe(root, f"raw/{name}.integrity.json", exists=True)
    csv_path = safe(root, f"raw/{name}.csv", exists=True)
    value = read_json(receipt_path)
    require(value.get("schema") == "paper3-batch20-replication-trajectory-receipt-v1"
            and value.get("valid") is True and value.get("task") == task, "invalid completion receipt")
    for key in ("manifest_digest", "input_bundle_digest", "environment_binding", "initial_state_hash",
                "initial_state_manifest_sha256", "scientific_runtime_signature", "runner_hash",
                "implementation_hash", "protocol_hash", "source_bindings_digest", "executor_bundle_digest"):
        require(value.get(key) == expected[key], "completion binding differs: " + key)
    require(value.get("trajectory_rows") == 24 and value.get("full_24_stage_input_parity_checked") is True
            and value.get("future_online_access_violation_count") == 0
            and value.get("statistics_executed") is False
            and value.get("performance_based_continuation") is False, "trajectory admission flags differ")
    require(sha(csv_path) == value["output_hash"], "CSV output SHA differs")
    linked = (("audit_relative", "audit_hash"), ("rng_relative", "rng_file_sha256"),
              ("attempt_csv_relative", "attempt_csv_hash"), ("runtime_receipt_path", "runtime_receipt_sha256"))
    for path_key, hash_key in linked:
        require(sha(safe(root, value[path_key], exists=True)) == value[hash_key], "bound artifact changed: " + path_key)
    require(value["attempt_csv_hash"] == value["output_hash"], "attempt and canonical CSV differ")
    for alias, original in (("audit_path", "audit_relative"), ("audit_sha256", "audit_hash"),
                            ("rng_before_path", "rng_relative"), ("rng_before_sha256", "rng_file_sha256")):
        require(value.get(alias) == value[original], "receipt alias differs")
    audit = read_json(safe(root, value["audit_relative"], exists=True))
    access = audit.get("timeline_access", {})
    require(audit.get("task") == task and audit.get("original_run_one_code_object_preserved") is True
            and audit.get("original_globals_mutated") is False
            and audit.get("globals_overridden") == ["timeline_for_v2", "scenario_hash_v2", "initial_model"]
            and audit.get("generator_called") is False
            and audit.get("source_bindings_sha256") == expected["critical_files_sha256"]
            and audit.get("input_bundle_digest") == expected["input_bundle_digest"]
            and audit.get("environment_binding") == expected["environment_binding"]
            and audit.get("scientific_runtime_signature") == expected["scientific_runtime_signature"], "method/source/input audit differs")
    require(access.get("violation_count") == 0 and access.get("completed_stages") == 24
            and access.get("phase") == "SERVICED", "causal access audit differs")
    initial = audit.get("initial_state", {})
    require(initial.get("initial_state_hash") == expected["initial_state_hash"]
            and initial.get("before_first_decision_verified") is True, "actual pre-decision initial state differs")
    runtime = read_json(safe(root, value["runtime_receipt_path"], exists=True))
    require(runtime.get("manifest_digest") == expected["manifest_digest"]
            and runtime.get("environment_binding") == expected["environment_binding"]
            and runtime.get("source_bindings_digest") == expected["source_bindings_digest"]
            and runtime.get("scientific_runtime_signature") == expected["scientific_runtime_signature"]
            and canonical(runtime["scientific_runtime"]) == expected["scientific_runtime_signature"], "scientific runtime signature differs")
    require(audit.get("scientific_runtime") == runtime["scientific_runtime"], "audit/runtime settings differ")
    rng = read_json(safe(root, value["rng_relative"], exists=True))
    rng_identity(rng, expected["rng_bindings"], expected["scientific_runtime"])
    require(audit.get("rng_state_before_original_run") == rng, "RNG capture/audit differ")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        require(len(header) == len(set(header)), "duplicate CSV fields")
        # Project no service_mse or other outcome values into the scheduler.
        projection_fields = PAIR_FIELDS + ("stage", "method", "config_id", "center_id", "seed", "scenario",
                                           "future_service_used_in_decision", "online_future_service_used", "identity_before")
        selected = {key: header.index(key) for key in projection_fields}
        rows = []
        for tokens in reader:
            require(len(tokens) == len(header), "CSV row width differs")
            rows.append({key: tokens[index] for key, index in selected.items()})
    require(len(rows) == 24 and [int(r["stage"]) for r in rows] == list(range(1, 25)), "stage coverage differs")
    require(all(all(row[k] == str(v) for k, v in task.items()) for row in rows), "CSV task identity differs")
    require(all(row["initial_state_hash"] == expected["initial_state_hash"] for row in rows), "initial hash changes within trajectory")
    require(rows[0]["identity_before"] == "msa_a57_pt", "initial deployed identity differs")
    require(all(row[k] == "False" for row in rows for k in ("future_service_used_in_decision", "online_future_service_used")), "future data flag differs")
    stage_hashes = value["stage_input_hashes"]
    require(len(stage_hashes) == 24, "input-hash stage evidence incomplete")
    for row, hashes in zip(rows, stage_hashes):
        require(hashes["stage"] == int(row["stage"])
                and all(row[key] == hashes[key] for key in ("D_upd_hash", "D_assess_hash", "D_srv_hash")), "stored stage input hashes differ")
    references = expected["reference_rows"]
    require(len(references) == 24, "bound F1 reference coverage differs")
    for row, reference in zip(rows, references):
        require(all(row[key] == str(reference[key]) for key in PAIR_FIELDS),
                "CSV exogenous/state/deployment field differs from bound F1 reference")
    require(all(value.get(key) == references[0][key] for key in ("deployment_tier", "deployment_filter_hash", "bank_hash")),
            "receipt deployment fields differ from bound F1 reference")
    return {"validated": True, "task_digest": canonical(task), "receipt_sha256": sha(receipt_path),
            "output_hash": value["output_hash"], "rows": [{key: r[key] for key in PAIR_FIELDS} for r in rows],
            "task": dict(task), "receipt_relative": f"raw/{name}.integrity.json",
            "rng_state_digest": rng["state_digest"], "loss_values_used": False}


def paired_groups(proofs):
    groups = {}
    for proof in proofs:
        require(proof.get("validated") is True, "unvalidated pairing input")
        task = proof["task"]
        key = (task["center_id"], task["seed"], task["scenario"])
        group = groups.setdefault(key, {})
        require(task["method"] not in group, "duplicate method in pairing group")
        group[task["method"]] = proof["rows"]
    complete = 0
    for group in groups.values():
        if set(group) == METHODS:
            first = next(iter(group.values()))
            require(all(rows == first for rows in group.values()), "five-method exogenous/initial/deployment pairing differs")
            complete += 1
    return {"complete_paired_groups": complete, "final_scientific_gate": False}
