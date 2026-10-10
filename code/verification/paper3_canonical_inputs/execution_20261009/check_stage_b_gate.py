"""Independent input-only Stage B scientific gate; no generator/model/outcome access.

Require complete immutable evidence and per-record saved-field correspondence:
239 original serial tasks to F; 961 original parallel tasks to S. Full historical
metadata/environment and initial parameters remain explicitly uncertified.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "verification" / "paper3_canonical_inputs"
EXECUTION = ROOT / "execution_20261009"
CANDIDATE = "P7_7_ORIGINAL_BATCH20_CANDIDATE_V1"
PROTOCOL = "P7_7_CANONICAL_INPUT_VERIFICATION_V1"
CENTERS = tuple(range(33000, 33020))
SEEDS = (7311, 7312, 7313)
SCENARIOS = ("C0", "C1", "C3", "C4")
METHODS = (("B0", "B0_Frozen_ratio10"), ("B1", "B1_AlwaysMaintainP50_ratio10"),
           ("B2", "B2_RAVM_ratio10"), ("B8", "B8_AlwaysOpen_ratio10"),
           ("P7.7", "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"))
FIELDS = ("scenario_hash", "center_type", "deployment_tier", "bank_hash",
          "deployment_filter_hash", "scenario_role", "D_upd_hash", "D_assess_hash",
          "D_srv_hash", "update_end_ts", "decision_ts")
MISSING = {"base.x/y/ts raw arrays", "full historical profile/metadata",
           "historical dtype/shape/endian", "explicit dt",
           "historical dependency/environment binding", "explicit full feasible identity mask"}
LEGACY = ("8785dc1ecf9e8123f47d786b880011774ed952daa56345b6f61e60361d15838d",
          "20c0a3546f5cff28dc0dccb3737bc27ee47d81b06fcb94f9fe294ca576e43ec5")
PARALLEL = ("6339a9247b984b497d1543198b3a7b7c0cfdf9c7bcfd1c52b47b62e17d2fd0df",
            "ced000f213f8fc9b52a859e683fc6d27dd04a268641c3d6024500f56c1c158fe")

def regular(path, *, exists=True):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"reparse/symlink gate path forbidden: {ancestor}")
    return path.resolve(strict=exists)

def inside(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("relative POSIX ledger path required")
    parts = relative.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or p in {".",".."}
           or p.endswith(".") or p.split(".")[0].upper() in reserved for p in parts):
        raise ValueError("unsafe ledger path")
    result = regular(root.joinpath(*parts))
    if result == root or root not in result.parents or not result.is_file():
        raise ValueError("ledger file escapes authorized root")
    return result

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def finite(value):
    if isinstance(value, float) and not math.isfinite(value): raise ValueError("non-finite JSON")
    if isinstance(value, dict):
        for item in value.values(): finite(item)
    elif isinstance(value, list):
        for item in value: finite(item)
    return value

def read_path(path):
    with regular(path).open("r", encoding="utf-8") as f:
        return finite(json.load(f, object_pairs_hook=unique))

def sha(path):
    h = hashlib.sha256()
    with regular(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576), b""): h.update(chunk)
    return h.hexdigest()

def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

def canonical(value):
    return hashlib.sha256(json.dumps(finite(value), sort_keys=True, separators=(",",":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()

def task(row):
    return (int(row["center_id"]), int(row["seed"]), row["scenario"], row["method"], row["config_id"])

def rows(path):
    with regular(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("missing/duplicate CSV header")
        for row in reader:
            if None in row or any(v is None for v in row.values()): raise ValueError("malformed CSV row")
            yield row

def publish(out, name, value):
    path = out / name
    regular(path, exists=False)
    with path.open("xb") as f:
        f.write((json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                            allow_nan=False)+"\n").encode("utf-8"))

def flatten(value, prefix=""):
    if not isinstance(value, dict): return {prefix:value}
    result = {}
    for key in sorted(value):
        if key in {"files","source_files","replicate","provenance_fingerprint",
                   "scenario_provenance_fingerprint","base_provenance_fingerprint"}: continue
        result.update(flatten(value[key], f"{prefix}/{key}"))
    return result

def evaluate(run, out):
    read = lambda name:read_path(inside(run, name))
    errors = []
    def check(condition, name):
        if not condition: errors.append(name)
    receipt, ledger = read("execution_receipt.json"), read("outputs_inventory.json")
    inventory = ledger["files"]
    if not isinstance(inventory, dict): raise ValueError("invalid output ledger")
    for name, digest in inventory.items():
        check(valid_sha(digest) and sha(inside(run, name)) == digest, f"output_hash:{name}")
    observed = {regular(p).relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}
    check(observed == set(inventory)|{"outputs_inventory.json","execution_receipt.json"}, "complete_output_file_set")
    check(ledger.get("schema") == "paper3-civ-output-inventory-v1", "output_ledger_schema")
    check(sha(inside(run,"run_manifest.json")) == receipt.get("run_manifest_sha256"), "receipt_to_manifest")
    check(sha(inside(run,"outputs_inventory.json")) == receipt.get("outputs_inventory_sha256"), "receipt_to_inventory")
    manifest, auth, definition = read("run_manifest.json"), read("authorization_manifest.json"), read("definition_manifest.json")
    sources, cert, summary = read("source_environment_manifest.json"), read("validation_certificate.json"), read("existing_input_mapping_summary.json")
    check(receipt.get("schema") == "paper3-civ-execution-receipt-v1", "receipt_schema")
    check(receipt.get("exit_code") == 0 and receipt.get("status") == "INPUT_ONLY_CHECKS_COMPLETED", "execution_success")
    check(receipt.get("originals_unchanged") is True and manifest.get("frozen_files_unchanged") is True, "originals_unchanged")
    check(receipt.get("model_execution_performed") is False and receipt.get("statistics_performed") is False, "input_only_execution")
    check(cert.get("checks_completed") is True and manifest.get("complete") is True and cert.get("valid_only_with_final_success_receipt") is True, "complete_final_certificate")
    check(manifest.get("file_bindings") == {k:v for k,v in inventory.items() if k != "run_manifest.json"}, "acyclic_manifest_output_graph")
    for obj, label in ((auth,"auth"),(definition,"definition"),(manifest,"manifest")):
        check(obj.get("candidate_id") == CANDIDATE and obj.get("verification_id") == PROTOCOL, f"identity:{label}")
    check(auth.get("run_id") == manifest.get("run_id") == run.name, "reserved_run_id")
    required_auth = {"human_authorized":True, "scope":"INPUT_ONLY_EXECUTION",
        "current_environment_reference_authorized":True, "historical_environment_not_reproduced_acknowledged":True,
        "models_authorized":False, "warmup_authorized":False, "statistics_authorized":False, "historical_overwrite_authorized":False}
    check(all(auth.get(k) == v for k,v in required_auth.items()) and bool(auth.get("human_authorization_reference")), "explicit_input_authorization")
    # The copied authorization is reserialized. Bind original reviewed bytes
    # through their SHA and require content equality, rather than equating copies.
    auth_sources = [p for p in EXECUTION.glob("*authorization*.json")
                    if p.is_file() and sha(p) == manifest.get("authorization_sha256")]
    check(bool(auth_sources) and all(read_path(p) == auth for p in auth_sources), "original_authorization_byte_and_content_binding")
    definition_digest = canonical(definition)
    dependencies = {k:sources[k] for k in ("sources","implementation","environment","historical_source_binding")}
    dependency_digest = canonical(dependencies)
    for obj, label in ((manifest,"manifest"),(sources,"source_env"),(cert,"certificate")):
        check(obj.get("definition_digest") == definition_digest and obj.get("dependency_digest") == dependency_digest, f"scientific_binding:{label}")
    check(sources["implementation"] == auth.get("approved_implementation_sha256"), "approved_implementation")
    for relative, digest in sources["implementation"].items():
        check(valid_sha(digest) and sha(inside(ROOT/"verifier_v1", relative)) == digest, f"implementation:{relative}")
    pins = read_path(inside(ROOT/"verifier_v1","source_pins.json"))
    check(sources["sources"] == pins.get("sources"), "frozen_source_pins")
    check(sources["historical_source_binding"] == pins.get("history_session") == auth.get("history_session"), "history_session_binding")
    for relative, digest in sources["sources"].items():
        check(valid_sha(digest) and sha(inside(REPO,relative)) == digest, f"frozen_source:{relative}")
    environment = regular(Path(auth["environment_manifest_path"]))
    if ROOT not in environment.parents: raise ValueError("environment source outside verification")
    check(sha(environment) == auth.get("environment_manifest_sha256") and read_path(environment) == sources["environment"], "reviewed_resolved_environment")
    history = sources["recovered_history"]
    check(history.get("status") == "VERIFIED_EXACT_HISTORICAL_SOURCE" and history.get("historical_environment_reproduced") is False and history.get("historical_runner_executed") is False, "history_source_not_runtime")
    check(history.get("session_sha256") == pins["history_session"]["sha256"], "recovered_history_session")
    for relative, expected, size in (("scripts/run_p7_7_final.py",LEGACY[1],51010),("configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json",LEGACY[0],12151)):
        obj = history["objects"][relative]
        check(obj.get("sha256") == expected and obj.get("byte_count") == size and hashlib.sha256(obj["recovered_text"].encode("utf-8")).hexdigest() == expected, f"exact_old_source:{relative}")
    check(receipt.get("protected_start_sha256") == receipt.get("protected_end_sha256"), "protected_start_end")
    for relative, digest in receipt["protected_end_sha256"].items():
        check(valid_sha(digest) and sha(inside(REPO,relative)) == digest, f"protected_current:{relative}")
    check(receipt.get("git_start") == receipt.get("git_end") == auth.get("approved_git_snapshot"), "git_start_end_approval")
    check(receipt["git_start"].get("head") == pins.get("git_head"), "git_head")
    check(tuple(definition.get("centers",[])) == CENTERS and tuple(definition.get("model_seeds",[])) == SEEDS and tuple(definition.get("scenarios",[])) == SCENARIOS and tuple(tuple(x) for x in definition.get("methods",[])) == METHODS, "exact_ordered_population")
    check(definition.get("data_seed") == 7311 and definition.get("n_history") == 17000 and definition.get("stages") == 24 and definition.get("scenario_revision") == "p3_mismatch_v2_r3", "fixed_scientific_definition")
    bundles = {label:read(f"contexts/{label}.json") for label in ("F1","F2","S1","S2")}
    for label, bundle in bundles.items():
        check(bundle.get("replicate") == label and bundle.get("context") == label[0], f"context_identity:{label}")
        check(bundle.get("definition_digest") == definition_digest and bundle.get("dependency_digest") == dependency_digest, f"context_binding:{label}")
        check(tuple(len(bundle[k]) for k in ("base","scenarios","roles","references")) == (20,80,5760,160), f"context_coverage:{label}")
        check(set(bundle["base"]) == {str(c) for c in CENTERS} and set(bundle["scenarios"]) == {f"{c}/{s}" for c in CENTERS for s in SCENARIOS}, f"context_IDs:{label}")
        check(set(bundle["roles"]) == {f"{c}/{s}/{t}/{r}" for c in CENTERS for s in SCENARIOS for t in range(1,25) for r in ("update","assessment","service")}, f"context_role_IDs:{label}")
        check(bundle.get("input_bundle_digest") == cert.get("input_bundle_digests",{}).get(label), f"certificate_bundle:{label}")
        for relative, digest in bundle["created_file_sha256"].items():
            check(inventory.get(relative) == digest, f"context_creation_binding:{label}/{relative}")
    check(bundles["F1"]["input_bundle_digest"] == bundles["F2"]["input_bundle_digest"] and bundles["S1"]["input_bundle_digest"] == bundles["S2"]["input_bundle_digest"], "context_repeatability")
    check(len({canonical(b["resolved_config"]) for b in bundles.values()}) == 1, "resolved_config_four_processes")
    bank = read("bank_feasibility_inventory.json")
    check(bank.get("checkpoint_bytes_verified") is False and bank.get("resource_profiling_executed") is False, "static_resource_scope")
    for obj, label in ((receipt,"receipt"),(manifest,"manifest"),(cert,"certificate")):
        check(obj.get("initial_state_verified") is False and obj.get("R2") == "PENDING_SEPARATE_AUTHORIZATION" and obj.get("R3") == "PENDING_SEPARATE_AUTHORIZATION", f"R2_R3_pending:{label}")
    # Independently check exact F/S comparison coverage/status against bundle
    # metadata. Context mismatch is reported, never converted into a run failure.
    expected_matrix = {}
    for collection in ("base","scenarios","roles","references"):
        for key in set(bundles["F1"][collection])|set(bundles["S1"][collection]):
            left, right = flatten(bundles["F1"][collection].get(key,{})), flatten(bundles["S1"][collection].get(key,{}))
            for field in set(left)|set(right):
                expected_matrix[collection,key,field] = "NOT_AVAILABLE" if field not in left or field not in right else ("MATCH" if canonical(left[field]) == canonical(right[field]) else "MISMATCH")
    for row in rows(inside(run,"full_vs_singleton_matrix.csv")):
        key = (row["collection"],row["entry"],row["field"])
        expected = expected_matrix.pop(key,None)
        check(expected is not None and row["status"] == expected, f"exact_F_S_matrix:{key}")
    check(not expected_matrix, "complete_F_S_matrix_coverage")
    ordered = [(c,s,q,m,i) for c in CENTERS for s in SEEDS for q in SCENARIOS for m,i in METHODS]
    expected_tasks, old_tasks, new_tasks = set(ordered), set(ordered[:239]), set(ordered[239:])
    record_rows = list(rows(inside(run,"existing_input_match_inventory.csv")))
    records = {}
    for row in record_rows:
        key = task(row)
        check(key not in records, f"duplicate_task:{key}")
        records[key] = row
    check(len(record_rows) == len(records) == 1200 and set(records) == expected_tasks, "unique_complete_taskset")
    old = {k for k,v in records.items() if v["cohort"] == "LEGACY_SERIAL"}
    new = {k for k,v in records.items() if v["cohort"] == "SINGLETON_PARALLEL"}
    check(old == old_tasks and new == new_tasks, "exact_serial_prefix_parallel_suffix")
    for key,row in records.items():
        check((row["protocol_hash"],row["runner_hash"]) == (LEGACY if key in old_tasks else PARALLEL), f"cohort_receipt_binding:{key}")
    states = {(k,x):{"mask":0,"match":True,"duplicates":0} for k in expected_tasks for x in ("F","S")}
    indices = {f:i for i,f in enumerate(FIELDS)}
    nonmatch_count = 0
    diagnostic_path = out/"stage_b_saved_field_nonmatches.jsonl"
    regular(diagnostic_path,exists=False)
    with diagnostic_path.open("xb") as diagnostic:
        for row in rows(inside(run,"existing_input_field_match_inventory.csv")):
            key, context = task(row), row["reference_context"]
            if key not in expected_tasks or context not in {"F","S"}:
                errors.append(f"unexpected_field_task:{key}/{context}")
                continue
            field, status = row["field"], row["status"]
            if field in FIELDS:
                stage = int(row["stage"])
                if not 1 <= stage <= 24: raise ValueError("invalid field stage")
                state = states[key,context]
                bit = 1 << ((stage-1)*len(FIELDS)+indices[field])
                if state["mask"] & bit: state["duplicates"] += 1
                state["mask"] |= bit
                equal = row["saved"] == row["reference"]
                if field in {"update_end_ts","decision_ts"} and status == "OBSERVED_MATCH":
                    equal = int(row["saved"]) == int(row["reference"])
                state["match"] = state["match"] and status == "OBSERVED_MATCH" and equal
            elif field not in MISSING or status != "NOT_RECORDED":
                errors.append(f"unexpected_field_schema:{field}/{status}")
            if status in {"OBSERVED_MISMATCH","NOT_VERIFIABLE","NOT_RECORDED"}:
                nonmatch_count += 1
                diagnostic.write((json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8"))
    full = (1 << (24*len(FIELDS)))-1
    cohorts = {"LEGACY_SERIAL":{"count":0,"matched_expected":0,"unmatched":[]},
               "SINGLETON_PARALLEL":{"count":0,"matched_expected":0,"unmatched":[]}}
    for key,row in records.items():
        for context in ("F","S"):
            state = states[key,context]
            coverage = state["mask"] == full and state["duplicates"] == 0
            check(coverage, f"saved_field_unique_264:{key}/{context}")
            matched = row["r0_qualified"] == "True" and coverage and state["match"]
            check((row[f"{context}_r1_qualified"] == "True") == matched, f"R1_from_field_evidence:{key}/{context}")
        name = row["cohort"]
        if name not in cohorts: continue
        context = "F" if name == "LEGACY_SERIAL" else "S"
        cohort, state = cohorts[name], states[key,context]
        cohort["count"] += 1
        if row["r0_qualified"] == "True" and state["mask"] == full and not state["duplicates"] and state["match"]:
            cohort["matched_expected"] += 1
        else:
            cohort["unmatched"].append({k:row[k] for k in ("center_id","seed","scenario","method","config_id","r0_qualified","F_r1_qualified","S_r1_qualified","errors")})
    check(summary.get("r0_qualified_count") == 1200 and summary.get("record_set_complete") is True and summary.get("expected_source_cohorts_match") is True and not summary.get("unverifiable_groups"), "mapping_summary_complete")
    check(summary.get("cohorts") == {"LEGACY_SERIAL":239,"SINGLETON_PARALLEL":961}, "mapping_summary_cohorts")
    historical = len(records) == 1200 and old == old_tasks and new == new_tasks and cohorts["LEGACY_SERIAL"]["matched_expected"] == 239 and cohorts["SINGLETON_PARALLEL"]["matched_expected"] == 961
    return {"schema":"paper3-stage-b-scientific-gate-v2", "input_verification_root":str(run),
            "execution_receipt_sha256":sha(inside(run,"execution_receipt.json")),
            "execution_pass":not errors, "binding_and_completeness_errors":errors,
            "expected_historical_cohort_correspondence_pass":historical, "cohorts":cohorts,
            "correspondence_level":"SAVED_FIELDS_R1_CURRENT_ENV_RECOVERED_REFERENCES",
            "existing_group_summary":summary, "required_saved_fields_per_record_context":264,
            "diagnostic_nonmatch_rows":nonmatch_count,
            "full_vs_singleton_comparison":"EXACT_REPORT_NOT_A_REQUIREMENT_TO_MATCH",
            "historical_environment_reproduced":False,"full_historical_metadata_reproduced":False,
            "all_existing_records_canonical_F":False,"initial_state_verified":False,
            "R2":"PENDING_STAGE_C_INITIAL_MODEL_AND_CAUSAL_CERTIFICATION","R3":"PENDING_FULL_REPLICATION",
            "stage_c_allowed":not errors and historical,"decisions_based_on_model_results":False}

def main():
    if len(sys.argv) != 3: raise ValueError("require run/output roots")
    run, out = regular(Path(sys.argv[1])), regular(Path(sys.argv[2]))
    if run.parent != regular(ROOT/PROTOCOL) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}",run.name):
        raise ValueError("run is not a reserved independent verification root")
    execution = regular(EXECUTION)
    if out != execution and execution not in out.parents:
        raise ValueError("gate output outside execution_20261009")
    try:
        result = evaluate(run,out)
    except Exception as error:
        result = {"schema":"paper3-stage-b-scientific-gate-v2","input_verification_root":str(run),
                  "execution_pass":False,"expected_historical_cohort_correspondence_pass":False,
                  "stage_c_allowed":False,"error":f"{type(error).__name__}:{error}",
                  "historical_environment_reproduced":False,"initial_state_verified":False}
    publish(out,"stage_b_scientific_gate.json",result)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result["stage_c_allowed"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
