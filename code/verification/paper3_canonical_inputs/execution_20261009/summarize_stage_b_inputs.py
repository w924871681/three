"""Summarize authorized input-only evidence after a successful scientific gate.

No project imports, generator, model, loss, action metric or inferential statistic.
Only input hashes, profiles, resource metadata, source cohorts and parity evidence
are interpreted. All output paths are fixed and exclusive; existing bytes remain.
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
from collections import Counter
from pathlib import Path

EXECUTION = Path(__file__).resolve().parent
ROOT = EXECUTION.parent
PROTOCOL = "P7_7_CANONICAL_INPUT_VERIFICATION_V1"
CENTERS = tuple(range(33000, 33020))
SCENARIOS = ("C0", "C1", "C3", "C4")
ROLES = ("update", "assessment", "service")


def regular(path, *, exists=True):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"reparse/symlink input-summary path forbidden: {ancestor}")
    return path.resolve(strict=exists)


def inside(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("relative POSIX path required")
    parts = relative.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".",".."}
           or part.endswith(".") or part.split(".")[0].upper() in reserved for part in parts):
        raise ValueError("unsafe input-summary ledger path")
    result = regular(root.joinpath(*parts))
    if result == root or root not in result.parents or not result.is_file():
        raise ValueError("input-summary file escapes authorized root")
    return result


def sha(path):
    digest = hashlib.sha256()
    with regular(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate input-summary JSON key: {key}")
        result[key] = value
    return result


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite input-summary JSON")
    if isinstance(value, dict):
        for item in value.values(): finite(item)
    elif isinstance(value, list):
        for item in value: finite(item)
    return value


def read(path):
    with regular(path).open("r", encoding="utf-8") as stream:
        return finite(json.load(stream, object_pairs_hook=unique))


def canonical(value):
    return hashlib.sha256(json.dumps(finite(value), sort_keys=True, separators=(",",":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def csv_rows(path):
    with regular(path).open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("missing/duplicate summary inventory header")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("malformed summary inventory row")
            yield row


def repeats(first, second, labels):
    collections = {}
    for collection, count in (("base",20),("scenarios",80),("roles",5760),("references",160)):
        left, right = first[collection], second[collection]
        keys = set(left) | set(right)
        unequal = [key for key in sorted(keys) if left.get(key,{}).get("provenance_fingerprint") != right.get(key,{}).get("provenance_fingerprint")]
        collections[collection] = {"expected_entries":count, "entries_first":len(left),
                                   "entries_second":len(right), "mismatched_entries":unequal,
                                   "exact_same_context_fingerprints":len(left)==len(right)==count and not unequal}
    return {"replicates":labels, "context":first["context"], "collections":collections,
            "input_bundle_digest_equal":first["input_bundle_digest"]==second["input_bundle_digest"],
            "input_bundle_digests":[first["input_bundle_digest"],second["input_bundle_digest"]],
            "exact_repeat_pass":all(item["exact_same_context_fingerprints"] for item in collections.values()) and first["input_bundle_digest"]==second["input_bundle_digest"]}


def base_comparison(first, second, center):
    left, right = first["base"][str(center)], second["base"][str(center)]
    arrays = {}
    for name in ("x","y","ts"):
        a, b = left["arrays"]["arrays"][name], right["arrays"]["arrays"][name]
        arrays[name] = {"F_legacy_array_digest":a["legacy_array_digest"], "S_legacy_array_digest":b["legacy_array_digest"],
                        "legacy_array_digest_equal":a["legacy_array_digest"]==b["legacy_array_digest"],
                        "F_shape":a["shape"], "S_shape":b["shape"], "shape_equal":a["shape"]==b["shape"],
                        "F_dtype_str":a["dtype_str"], "S_dtype_str":b["dtype_str"],
                        "dtype_str_equal":a["dtype_str"]==b["dtype_str"], "F_endian":a["endian"], "S_endian":b["endian"]}
    profiles = {field:{"F":left["profile"][field], "S":right["profile"][field],
                      "equal":left["profile"][field]==right["profile"][field]} for field in ("center_type","budget_tier","dt")}
    profile_values_equal = canonical(left["profile"]) == canonical(right["profile"])
    for value in (left,right):
        if canonical(value["profile"]) != value["profile_digest"]:
            raise ValueError("profile digest does not bind complete profile metadata")
    deploy_a, deploy_b = left["deployment"], right["deployment"]
    feasible_a, feasible_b = set(deploy_a["feasible_ids"]), set(deploy_b["feasible_ids"])
    candidates_a, candidates_b = set(deploy_a["initial_candidate_ids"]), set(deploy_b["initial_candidate_ids"])
    return {"center_id":center, "base_arrays":arrays,
            "F_joint_legacy_digest":left["legacy_array_digest"], "S_joint_legacy_digest":right["legacy_array_digest"],
            "joint_legacy_digest_equal":left["legacy_array_digest"]==right["legacy_array_digest"],
            "profile_fields":profiles, "full_profile_metadata_equal":profile_values_equal,
            "F_profile_digest":left["profile_digest"], "S_profile_digest":right["profile_digest"],
            "F_rng_context":left["rng_context"], "S_rng_context":right["rng_context"],
            "context_labelled_provenance": {"F":left["provenance_fingerprint"], "S":right["provenance_fingerprint"],
                "equal":left["provenance_fingerprint"]==right["provenance_fingerprint"],
                "interpretation":"Distinct context tags remain provenance evidence; equality of array digests is assessed separately."},
            "deployment": {"F_limits":deploy_a["limits"], "S_limits":deploy_b["limits"],
                "limits_equal":deploy_a["limits"]==deploy_b["limits"], "bank_hash_equal":deploy_a["bank_hash"]==deploy_b["bank_hash"],
                "F_bank_hash":deploy_a["bank_hash"], "S_bank_hash":deploy_b["bank_hash"],
                "F_deployment_filter_hash":deploy_a["deployment_filter_hash"], "S_deployment_filter_hash":deploy_b["deployment_filter_hash"],
                "F_feasible_ids":deploy_a["feasible_ids"], "S_feasible_ids":deploy_b["feasible_ids"],
                "feasible_id_sets_equal":feasible_a==feasible_b,
                "feasible_order_equal":deploy_a["feasible_ids"]==deploy_b["feasible_ids"],
                "feasible_only_F":sorted(feasible_a-feasible_b), "feasible_only_S":sorted(feasible_b-feasible_a),
                "F_initial_candidate_ids":deploy_a["initial_candidate_ids"], "S_initial_candidate_ids":deploy_b["initial_candidate_ids"],
                "initial_candidate_sets_equal":candidates_a==candidates_b,
                "initial_candidate_order_equal":deploy_a["initial_candidate_ids"]==deploy_b["initial_candidate_ids"]}}


def scenario_comparison(first, second, center, scenario):
    key = f"{center}/{scenario}"
    left, right = first["scenarios"][key], second["scenarios"][key]
    roles = {}
    for role in ROLES:
        differing, entries = [], []
        for stage in range(1,25):
            role_key = f"{center}/{scenario}/{stage}/{role}"
            a, b = first["roles"][role_key], second["roles"][role_key]
            equal = a["legacy_role_hash"] == b["legacy_role_hash"]
            if not equal: differing.append(stage)
            entries.append({"stage":stage, "F_legacy_role_hash":a["legacy_role_hash"],
                            "S_legacy_role_hash":b["legacy_role_hash"], "equal":equal,
                            "span_equal":a["span"]==b["span"]})
        roles[role] = {"entries":24,"differing_legacy_role_hash_count":len(differing),
                       "differing_stages":differing,"per_stage":entries}
    return {"center_id":center, "scenario":scenario,
            "F_raw_scenario_hash":left["legacy_scenario_hash"], "S_raw_scenario_hash":right["legacy_scenario_hash"],
            "raw_scenario_hash_equal":left["legacy_scenario_hash"]==right["legacy_scenario_hash"],
            "F_feature_joint_legacy_hash":left["feature_arrays"]["legacy_array_digest"],
            "S_feature_joint_legacy_hash":right["feature_arrays"]["legacy_array_digest"],
            "feature_joint_legacy_hash_equal":left["feature_arrays"]["legacy_array_digest"]==right["feature_arrays"]["legacy_array_digest"],
            "role_entry_count":72,"different_role_hash_count":sum(value["differing_legacy_role_hash_count"] for value in roles.values()),
            "roles":roles,
            "context_labelled_provenance":{"F":left["provenance_fingerprint"],"S":right["provenance_fingerprint"]}}


def summarize(run):
    gate_path = inside(EXECUTION,"stage_b_scientific_gate.json")
    gate = read(gate_path)
    if gate.get("stage_c_allowed") is not True or gate.get("execution_pass") is not True or gate.get("expected_historical_cohort_correspondence_pass") is not True:
        raise ValueError("independent Stage B scientific gate has not passed")
    if regular(Path(gate["input_verification_root"])) != run:
        raise ValueError("gate belongs to another input-verification run")
    receipt_path, inventory_path = inside(run,"execution_receipt.json"), inside(run,"outputs_inventory.json")
    receipt, inventory_object = read(receipt_path), read(inventory_path)
    if gate.get("execution_receipt_sha256") != sha(receipt_path) or receipt.get("exit_code") != 0 or receipt.get("status") != "INPUT_ONLY_CHECKS_COMPLETED" or receipt.get("originals_unchanged") is not True:
        raise ValueError("final successful receipt is absent, changed or inconsistent")
    if sha(inventory_path) != receipt["outputs_inventory_sha256"] or sha(inside(run,"run_manifest.json")) != receipt["run_manifest_sha256"]:
        raise ValueError("final input output-ledger binding changed")
    inventory = inventory_object["files"]
    names = [f"contexts/{label}.json" for label in ("F1","F2","S1","S2")]+[
        "full_vs_singleton_matrix.csv", "existing_input_match_inventory.csv",
        "existing_group_input_parity.json", "existing_input_mapping_summary.json", "validation_certificate.json"]
    bindings = {"helper": {"path":str(regular(Path(__file__))), "sha256":sha(Path(__file__))},
                "scientific_gate": {"path":str(gate_path), "sha256":sha(gate_path)},
                "final_execution_receipt":{"path":str(receipt_path),"sha256":sha(receipt_path)},
                "outputs_inventory":{"path":str(inventory_path),"sha256":sha(inventory_path)},
                "run_manifest":{"path":str(inside(run,"run_manifest.json")),"sha256":receipt["run_manifest_sha256"]},
                "input_files":{}}
    for name in names:
        path, digest = inside(run,name), inventory.get(name)
        if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest) or sha(path) != digest:
            raise ValueError(f"summarized input changed since completion: {name}")
        bindings["input_files"][name] = {"path":str(path),"sha256":digest}
    bundles = {label:read(inside(run,f"contexts/{label}.json")) for label in ("F1","F2","S1","S2")}
    repeat = [repeats(bundles["F1"],bundles["F2"],["F1","F2"]),repeats(bundles["S1"],bundles["S2"],["S1","S2"])]
    if not all(value["exact_repeat_pass"] for value in repeat):
        raise ValueError("context repeatability changed or did not pass")
    first, second = bundles["F1"], bundles["S1"]
    base = [base_comparison(first,second,center) for center in CENTERS]
    scenarios = [scenario_comparison(first,second,center,scenario) for center in CENTERS for scenario in SCENARIOS]
    population = {label:{"type_counts":dict(sorted(Counter(value["profile"]["center_type"] for value in bundle["base"].values()).items())),
                         "tier_counts":dict(sorted(Counter(value["profile"]["budget_tier"] for value in bundle["base"].values()).items())),
                         "population_size":len(bundle["base"])} for label,bundle in bundles.items()}
    matrix_counts, matrix_center_counts = {}, {str(center):{} for center in CENTERS}
    for row in csv_rows(inside(run,"full_vs_singleton_matrix.csv")):
        collection,status = row["collection"],row["status"]
        center = row["entry"].split("/")[0]
        if center not in matrix_center_counts or status not in {"MATCH","MISMATCH","NOT_AVAILABLE"}:
            raise ValueError("unexpected full-v-singleton matrix row")
        matrix_counts.setdefault(collection,Counter())[status] += 1
        matrix_center_counts[center].setdefault(collection,Counter())[status] += 1
    cohorts = {"LEGACY_SERIAL":{"count":0,"expected_context":"F","saved_fields_matched":0},
               "SINGLETON_PARALLEL":{"count":0,"expected_context":"S","saved_fields_matched":0}}
    record_count = 0
    for row in csv_rows(inside(run,"existing_input_match_inventory.csv")):
        record_count += 1
        cohort = cohorts[row["cohort"]]
        cohort["count"] += 1
        if row["r0_qualified"] == "True" and row[f"{cohort['expected_context']}_r1_qualified"] == "True":
            cohort["saved_fields_matched"] += 1
    if record_count != 1200 or not (cohorts["LEGACY_SERIAL"]["count"] == cohorts["LEGACY_SERIAL"]["saved_fields_matched"] == 239) or not (cohorts["SINGLETON_PARALLEL"]["count"] == cohorts["SINGLETON_PARALLEL"]["saved_fields_matched"] == 961):
        raise ValueError("saved-field cohort correspondence does not pass")
    groups = read(inside(run,"existing_group_input_parity.json"))
    bad_groups = {key:value for key,value in groups.items() if value["exogenous_parity"] != "MATCH"}
    initial_bad = {key:value["saved_initial_state_evidence"] for key,value in groups.items() if value["saved_initial_state_evidence"] != "MATCH"}
    result = {"schema":"paper3-stage-b-input-summary-v1", "input_verification_root":str(run),
        "evidence_grade":"VERIFIED_SAVED_INPUT_FIELDS_AND_AUTHORIZED_CURRENT_ENV_REFERENCES",
        "repeatability":repeat,"population_type_and_tier_counts":population,
        "full_vs_singleton":{"center_count":20,"scenario_count":80,
            "base_per_center":base,"scenario_per_center":scenarios,
            "different_joint_base_legacy_digest_centers":[value["center_id"] for value in base if not value["joint_legacy_digest_equal"]],
            "different_base_array_digest_centers":{name:[value["center_id"] for value in base if not value["base_arrays"][name]["legacy_array_digest_equal"]] for name in ("x","y","ts")},
            "different_full_profile_centers":[value["center_id"] for value in base if not value["full_profile_metadata_equal"]],
            "different_type_centers":[value["center_id"] for value in base if not value["profile_fields"]["center_type"]["equal"]],
            "different_tier_centers":[value["center_id"] for value in base if not value["profile_fields"]["budget_tier"]["equal"]],
            "different_dt_centers":[value["center_id"] for value in base if not value["profile_fields"]["dt"]["equal"]],
            "different_static_feasible_set_centers":[value["center_id"] for value in base if not value["deployment"]["feasible_id_sets_equal"]],
            "different_raw_scenario_hash_count":sum(not value["raw_scenario_hash_equal"] for value in scenarios),
            "different_stage_role_hash_count":sum(value["different_role_hash_count"] for value in scenarios),
            "stage_role_pairs_compared":5760,
            "M2_status_counts_by_collection":{key:dict(value) for key,value in matrix_counts.items()},
            "M2_status_counts_by_center":{center:{key:dict(value) for key,value in counts.items()} for center,counts in matrix_center_counts.items()},
            "context_labelled_fingerprints_are_not_legacy_array_equality":True},
        "existing_results_input_evidence":{"trajectory_count":record_count,"cohorts":cohorts,
            "five_method_group_count":len(groups),"bad_cross_method_exogenous_groups":bad_groups,
            "sole_previously_known_bad_group_verified":set(bad_groups)=={"33003/7313/C4"},
            "saved_initial_state_nonmatching_groups":initial_bad,
            "saved_initial_hash_parity_is_not_canonical_initial_state_verification":True},
        "source_bindings":bindings,"initial_state_verified":False,"historical_environment_reproduced":False,
        "historical_full_metadata_certified":False,"R2":"PENDING_STAGE_C_INITIAL_MODEL_AND_CAUSAL_CERTIFICATION",
        "R3":"PENDING_FULL_REPLICATION","model_performance_fields_read":False,
        "new_statistics_or_bootstrap_performed":False,"original_result_replacement_authorized":False}
    # Recheck every consumed immutable file after interpretation as well.
    for name,item in bindings["input_files"].items():
        if sha(inside(run,name)) != item["sha256"]:
            raise ValueError("input evidence changed during summary")
    if sha(gate_path) != bindings["scientific_gate"]["sha256"] or sha(receipt_path) != bindings["final_execution_receipt"]["sha256"]:
        raise ValueError("gate or final receipt changed during summary")
    if sha(inventory_path) != bindings["outputs_inventory"]["sha256"] or sha(inside(run,"run_manifest.json")) != bindings["run_manifest"]["sha256"] or sha(Path(__file__)) != bindings["helper"]["sha256"]:
        raise ValueError("output ledger, manifest or helper changed during summary")
    return result


def main():
    if len(sys.argv) != 2: raise ValueError("require explicit input-verification run root")
    execution, run = regular(EXECUTION), regular(Path(sys.argv[1]))
    if run.parent != regular(ROOT/PROTOCOL) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}",run.name):
        raise ValueError("run is not a reserved independent canonical input root")
    output = execution/"stage_b_input_summary.json"
    regular(output,exists=False)
    if output.exists(): raise ValueError("input summary already exists; overwrite forbidden")
    result = summarize(run)
    with output.open("xb") as stream:
        stream.write((json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    print(json.dumps({"path":str(output),"sha256":sha(output),"input_only":True},ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
