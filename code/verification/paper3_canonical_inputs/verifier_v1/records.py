"""Read-only, outcome-blind mapping of saved P7.7 input evidence.

No project module, model, estimator or statistical routine is imported. CSV
tokens outside INPUT_FIELDS are discarded at the parse boundary. Reading opaque
file bytes for SHA256 is deliberately separate from scientific field access.
"""
from __future__ import annotations

import csv
import stat
from collections import Counter
from pathlib import Path

from .contract import CENTERS, INCUMBENT_ID, METHODS, SCENARIOS, SEEDS, ContractError, file_sha256, read_json

INPUT_FIELDS = (
    "method", "config_id", "center_id", "seed", "scenario", "stage",
    "scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash",
    "center_type", "deployment_tier", "deployment_filter_hash", "bank_hash",
    "update_end_ts", "decision_ts", "scenario_role", "identity_before", "initial_state_hash",
)
RECEIPT_FIELDS = (
    "schema", "valid", "method", "method_config_id", "center_id", "seed", "scenario",
    "protocol_hash", "runner_hash", "implementation_hash", "output_hash", "trajectory_rows",
    "final_heldout_accessed", "alibaba_accessed", "p8_executed",
)
LEGACY_BINDING = (
    "8785dc1ecf9e8123f47d786b880011774ed952daa56345b6f61e60361d15838d",
    "20c0a3546f5cff28dc0dccb3737bc27ee47d81b06fcb94f9fe294ca576e43ec5",
)
PARALLEL_BINDING = (
    "6339a9247b984b497d1543198b3a7b7c0cfdf9c7bcfd1c52b47b62e17d2fd0df",
    "ced000f213f8fc9b52a859e683fc6d27dd04a268641c3d6024500f56c1c158fe",
)
IMPLEMENTATION_HASH = "378f2b8644f97e87fa819661da694d1bfcb163e7d183d110edf5f08c9d6dfe3d"
PARITY_FIELDS = (
    "scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash", "center_type",
    "deployment_tier", "deployment_filter_hash", "bank_hash", "update_end_ts",
    "decision_ts", "scenario_role",
)
ROLE_FIELDS = (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash"))


def _safe_file(repo: Path, relative: str) -> Path:
    """Reject traversal, symlinks and Windows junctions before a read."""
    repo = Path(repo).absolute()
    normalized = relative.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(p in ("", ".", "..") or ":" in p for p in parts):
        raise ContractError("unsafe evidence path")
    target = repo.joinpath(*parts)
    for path in (target, *target.parents):
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ContractError(f"reparse evidence path: {path}")
    if not target.resolve(strict=False).is_relative_to(repo.resolve(strict=True)):
        raise ContractError("evidence path escapes target repository")
    return target


def projected_csv(path: Path) -> list[dict]:
    """Return only the approved input projection; do not retain other tokens.

    csv.reader necessarily tokenizes one opaque physical row. Non-whitelisted
    tokens are never assigned names, returned, compared or used as conditions.
    identity_before/initial_state_hash are retained only for stage 1.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header or len(set(header)) != len(header):
            raise ContractError("missing or duplicate CSV header")
        indices = {name: header.index(name) for name in INPUT_FIELDS if name in header}
        missing = {"method", "config_id", "center_id", "seed", "scenario", "stage"} - set(indices)
        if missing:
            raise ContractError("missing input CSV fields: " + ",".join(sorted(missing)))
        rows = []
        for tokens in reader:
            if len(tokens) != len(header):
                raise ContractError("malformed CSV row")
            row = {name: tokens[index] for name, index in indices.items()}
            del tokens
            for name in ("center_id", "seed", "stage"):
                row[name] = int(row[name])
            for name in ("update_end_ts", "decision_ts"):
                if name in row and row[name] != "":
                    row[name] = int(row[name])
                else:
                    row.pop(name, None)
            for name in ("initial_state_hash", "identity_before"):
                if row.get(name) == "":
                    row.pop(name, None)
            if row["stage"] != 1:
                row.pop("identity_before", None)
                row.pop("initial_state_hash", None)
            rows.append(row)
    return rows


def _cohort(receipt: dict) -> str:
    binding = (receipt.get("protocol_hash"), receipt.get("runner_hash"))
    if binding == LEGACY_BINDING:
        return "LEGACY_SERIAL"
    if binding == PARALLEL_BINDING:
        return "SINGLETON_PARALLEL"
    return "UNRECOGNIZED_SOURCE"


def _observation(field: str, saved, reference, stage: int | None = None) -> dict:
    status = "NOT_RECORDED" if saved in (None, "") else "NOT_VERIFIABLE" if reference is None else (
        "OBSERVED_MATCH" if saved == reference else "OBSERVED_MISMATCH")
    result = {"field": field, "status": status, "saved": saved, "reference": reference}
    if stage is not None:
        result["stage"] = stage
    return result


def match_reference(rows: list[dict], bundle: dict, center: int, scenario: str) -> dict:
    """R1 covers saved fields, never missing historical profile or model state."""
    base = bundle.get("base", {}).get(str(center))
    scene = bundle.get("scenarios", {}).get(f"{center}/{scenario}")
    if base is None or scene is None:
        return {"status": "NOT_VERIFIABLE", "r1_qualified": False, "observations": [], "missing_reference": True}
    profile, deployment = base["profile"], base["deployment"]
    observations = []
    for row in rows:
        stage = row["stage"]
        expected = {
            "scenario_hash": scene["legacy_scenario_hash"], "center_type": profile["center_type"],
            "deployment_tier": profile["budget_tier"], "bank_hash": deployment["bank_hash"],
            "deployment_filter_hash": deployment["deployment_filter_hash"],
            "scenario_role": scene.get("metadata", {}).get("definition"),
        }
        for role, field in ROLE_FIELDS:
            item = bundle.get("roles", {}).get(f"{center}/{scenario}/{stage}/{role}")
            expected[field] = None if item is None else item["legacy_role_hash"]
            if role == "update":
                expected["update_end_ts"] = None if item is None else item["update_end_ts"]
                expected["decision_ts"] = None if item is None else item["decision_ts"]
        for field, reference in expected.items():
            observations.append(_observation(field, row.get(field), reference, stage))
    missing = ["base.x/y/ts raw arrays", "full historical profile/metadata", "historical dtype/shape/endian",
               "explicit dt", "historical dependency/environment binding", "explicit full feasible identity mask"]
    complete_stages = len(rows) == 24 and {r["stage"] for r in rows} == set(range(1, 25))
    observed_match = complete_stages and all(o["status"] == "OBSERVED_MATCH" for o in observations)
    return {
        "status": "SAVED_INPUT_DIGEST_MATCHED" if observed_match else "SAVED_INPUT_UNMATCHED_OR_UNRESOLVED",
        "r1_qualified": observed_match, "observations": observations,
        "saved_field_coverage": len(observations),
        "not_recorded": [{"field": name, "status": "NOT_RECORDED"} for name in missing],
        "static_feasibility": {
            "evidence_form": "INDIRECT_FROM_MATCHED_TIER_BANK_HASH_AND_LIMITS_HASH",
            "status": "OBSERVED_MATCH" if observed_match else "NOT_VERIFIABLE",
            "reference_feasible_mask": deployment["feasible_mask"],
            "reference_feasible_ids": deployment["feasible_ids"],
            "reference_initial_candidate_ids": deployment["initial_candidate_ids"],
            "actual_later_candidate_counts_checked": False,
        },
        "initial_state_verified": False, "r2_status": "PENDING_SEPARATE_AUTHORIZATION",
        "r3_status": "PENDING_SEPARATE_AUTHORIZATION",
    }


def group_parity(records: list[dict]) -> dict:
    """Exogenous input parity is separate from stage-1 saved-state equality."""
    by_method = {item["task"]["method"]: item for item in records}
    expected_methods = {item[0] for item in METHODS}
    complete = len(records) == 5 and set(by_method) == expected_methods
    comparable = complete and all(
        len(item.get("rows", [])) == 24 and [r["stage"] for r in item["rows"]] == list(range(1, 25))
        and all(all(row.get(field) not in (None, "") for field in PARITY_FIELDS) for row in item["rows"])
        for item in records)
    differences = []
    if comparable:
        baseline = records[0]
        for other in records[1:]:
            for left, right in zip(baseline["rows"], other["rows"]):
                for field in PARITY_FIELDS:
                    if left.get(field) != right.get(field):
                        differences.append({"stage": left["stage"], "field": field,
                                            "method_a": baseline["task"]["method"], "method_b": other["task"]["method"]})
    initial_hashes = {item["task"]["method"]: (item.get("rows") or [{}])[0].get("initial_state_hash") for item in records}
    initial_identities = {item["task"]["method"]: (item.get("rows") or [{}])[0].get("identity_before") for item in records}
    initial_hashes_valid = complete and all(isinstance(value, str) and len(value) == 64 and
        all(char in "0123456789abcdef" for char in value) for value in initial_hashes.values())
    saved_initial_equal = comparable and initial_hashes_valid and len(set(initial_hashes.values())) == 1
    saved_identity_equal = comparable and all(isinstance(value, str) and bool(value) for value in initial_identities.values()) and len(set(initial_identities.values())) == 1
    r1_candidates = {
        context: complete and all(item.get("r0_qualified", False) and item.get("matches", {}).get(context, {}).get("r1_qualified", False) for item in records)
        for context in ("F", "S")
    }
    return {
        "complete_five_methods": complete, "exogenous_parity": "MATCH" if comparable and not differences else "MISMATCH" if comparable else "NOT_VERIFIABLE",
        "differences": differences, "saved_initial_hashes": initial_hashes,
        "saved_initial_identities": initial_identities, "saved_initial_state_parity": saved_initial_equal,
        "saved_initial_identity_parity": saved_identity_equal,
        "saved_initial_state_evidence": "MATCH" if saved_initial_equal else "MISMATCH" if comparable and initial_hashes_valid else "NOT_VERIFIABLE",
        "saved_initial_identity_matches_frozen_incumbent": comparable and all(value == INCUMBENT_ID for value in initial_identities.values()),
        "all_five_r1_candidates": r1_candidates, "initial_state_verified": False,
        "r2_qualified": False, "r2_status": "PENDING_SEPARATE_AUTHORIZATION",
        "r3_qualified": False, "r3_status": "PENDING_SEPARATE_AUTHORIZATION",
        "later_deployed_state_parity_required": False,
    }


def inspect_existing(repo: Path, contexts: dict) -> dict:
    """Inspect all 1200 immutable records. This function never writes files."""
    repo = Path(repo)
    audit_path = _safe_file(repo, "audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json")
    audit = read_json(audit_path)
    # Project only the existing byte-integrity ledger; no metrics or CI are read.
    output_hashes = dict(audit.get("output_hashes", {}))
    del audit
    raw_root = _safe_file(repo, "results/p7_7/raw")
    expected_stems = {f"{config_id}_{center}_{seed}_{scenario}" for center in CENTERS for seed in SEEDS
                      for scenario in SCENARIOS for _, config_id in METHODS}
    observed_csv_names, observed_receipt_names = set(), set()
    if raw_root.is_dir():
        for path in raw_root.iterdir():
            if path.name.endswith(".csv") or path.name.endswith(".integrity.json"):
                _safe_file(repo, "results/p7_7/raw/" + path.name)
                if path.is_file():
                    (observed_csv_names if path.name.endswith(".csv") else observed_receipt_names).add(path.name)
    expected_csv_names = {stem + ".csv" for stem in expected_stems}
    expected_receipt_names = {stem + ".integrity.json" for stem in expected_stems}
    record_set_complete = observed_csv_names == expected_csv_names and observed_receipt_names == expected_receipt_names
    records, all_fields, groups = [], [], {}
    for center in CENTERS:
        for seed in SEEDS:
            for scenario in SCENARIOS:
                group_key = f"{center}/{seed}/{scenario}"
                groups[group_key] = []
                for method, config_id in METHODS:
                    task = {"method": method, "config_id": config_id, "center_id": center, "seed": seed, "scenario": scenario}
                    name = f"results/p7_7/raw/{config_id}_{center}_{seed}_{scenario}"
                    csv_path = _safe_file(repo, name + ".csv")
                    receipt_path = _safe_file(repo, name + ".integrity.json")
                    item = {"task": task, "csv_path": str(csv_path), "receipt_path": str(receipt_path),
                            "rows": [], "errors": [], "r0_qualified": False, "cohort": "NOT_VERIFIABLE", "matches": {}}
                    if not csv_path.is_file() or not receipt_path.is_file():
                        item["errors"].append("MISSING_CSV_OR_RECEIPT")
                    else:
                        try:
                            raw_receipt = read_json(receipt_path)
                            receipt = {key: raw_receipt.get(key) for key in RECEIPT_FIELDS}
                            del raw_receipt
                            item["receipt"] = receipt
                            item["receipt_file_sha256"] = file_sha256(receipt_path)
                            item["csv_file_sha256"] = file_sha256(csv_path)
                            item["cohort"] = _cohort(receipt)
                            rows = projected_csv(csv_path)
                            rows.sort(key=lambda row: row["stage"])
                            item["rows"] = rows
                            stage_valid = len(rows) == 24 and [r["stage"] for r in rows] == list(range(1, 25))
                            task_valid = stage_valid and all(all(row.get(key) == value for key, value in task.items()) for row in rows)
                            receipt_task_valid = all(receipt.get(key) == task[key] for key in ("method", "center_id", "seed", "scenario")) and receipt.get("method_config_id") == config_id
                            audit_hash = output_hashes.get((name + ".csv").replace("/", "\\"))
                            if audit_hash is None:
                                audit_hash = output_hashes.get(name + ".csv")
                            checks = {
                                "task_binding": task_valid and receipt_task_valid,
                                "receipt_schema": receipt.get("schema") == "p7.7-final-heldout-trajectory-receipt-v1",
                                "receipt_valid": receipt.get("valid") is True,
                                "receipt_rows": receipt.get("trajectory_rows") == 24,
                                "output_byte_hash": receipt.get("output_hash") == item["csv_file_sha256"],
                                "audit_ledger_hash": audit_hash == item["csv_file_sha256"],
                                "recognized_source_binding": item["cohort"] != "UNRECOGNIZED_SOURCE",
                                "implementation_binding": receipt.get("implementation_hash") == IMPLEMENTATION_HASH,
                                "access_scope": receipt.get("final_heldout_accessed") is True and receipt.get("alibaba_accessed") is False and receipt.get("p8_executed") is False,
                            }
                            item["r0_checks"] = checks
                            item["r0_qualified"] = all(checks.values())
                            item["errors"].extend(key for key, passed in checks.items() if not passed)
                        except (ContractError, ValueError, KeyError, OSError) as error:
                            item["errors"].append(f"INPUT_EVIDENCE_PARSE_ERROR:{type(error).__name__}:{error}")
                    for context, replicate in (("F", "F1"), ("S", "S1")):
                        bundle = contexts.get(replicate) or contexts.get(context) or {}
                        match = match_reference(item["rows"], bundle, center, scenario)
                        match["r1_qualified"] = match.get("r1_qualified", False) and item["r0_qualified"]
                        match["r1_status"] = "SAVED_INPUT_DIGEST_MATCHED" if match["r1_qualified"] else "NOT_QUALIFIED"
                        item["matches"][context] = match
                        for observation in match.get("observations", []):
                            all_fields.append({**task, "reference_context": context, **observation})
                        for observation in match.get("not_recorded", []):
                            all_fields.append({**task, "reference_context": context, **observation})
                    item["r0_status"] = "HISTORICAL_ONLY" if item["r0_qualified"] else "HISTORICAL_UNQUALIFIED"
                    item["initial_state_verified"] = False
                    item["r2_status"] = item["r3_status"] = "PENDING_SEPARATE_AUTHORIZATION"
                    records.append(item)
                    groups[group_key].append(item)
    parity = {key: group_parity(items) for key, items in groups.items()}
    cohorts = dict(Counter(item["cohort"] for item in records))
    matched = [key for key, item in parity.items() if item["exogenous_parity"] == "MATCH"]
    mismatched = [key for key, item in parity.items() if item["exogenous_parity"] == "MISMATCH"]
    inventory = []
    for item in records:
        row = {**item["task"], "csv_path": item["csv_path"], "receipt_path": item["receipt_path"],
               "cohort": item["cohort"], "r0_status": item["r0_status"], "r0_qualified": item["r0_qualified"],
               "F_r1_qualified": item["matches"]["F"].get("r1_qualified", False),
               "S_r1_qualified": item["matches"]["S"].get("r1_qualified", False),
               "initial_state_verified": False, "r2_status": item["r2_status"], "r3_status": item["r3_status"],
               "csv_file_sha256": item.get("csv_file_sha256"), "receipt_file_sha256": item.get("receipt_file_sha256"),
               "errors": item["errors"]}
        row.update({field: item.get("receipt", {}).get(field) for field in
                    ("protocol_hash", "runner_hash", "implementation_hash", "output_hash")})
        inventory.append(row)
    return {
        "schema": "p7.7-existing-input-mapping-v1", "inventory": inventory, "field_inventory": all_fields,
        "groups": parity, "records": records,
        "summary": {
            "expected_trajectories": 1200, "inspected_trajectories": len(records),
            "record_set_complete": record_set_complete,
            "observed_csv_count": len(observed_csv_names), "observed_receipt_count": len(observed_receipt_names),
            "unexpected_csv_names": sorted(observed_csv_names - expected_csv_names),
            "unexpected_receipt_names": sorted(observed_receipt_names - expected_receipt_names),
            "missing_csv_names": sorted(expected_csv_names - observed_csv_names),
            "missing_receipt_names": sorted(expected_receipt_names - observed_receipt_names),
            "r0_qualified_count": sum(item["r0_qualified"] for item in records), "cohorts": cohorts,
            "expected_source_cohorts_match": cohorts == {"LEGACY_SERIAL": 239, "SINGLETON_PARALLEL": 961},
            "expected_groups": 240, "matched_groups": len(matched), "mismatched_groups": mismatched,
            "unverifiable_groups": [key for key, item in parity.items() if item["exogenous_parity"] == "NOT_VERIFIABLE"],
            "r1_F_count": sum(item["matches"]["F"].get("r1_qualified", False) for item in records),
            "r1_S_count": sum(item["matches"]["S"].get("r1_qualified", False) for item in records),
            "initial_state_verified": False, "r2_qualified_count": 0, "r3_qualified_count": 0,
            "outcome_fields_read_scientifically": False, "performance_or_statistics_computed": False,
        },
        "evidence_bindings": {"historical_audit_file": str(audit_path), "historical_audit_sha256": file_sha256(audit_path)},
        "start_evidence_hashes": {item["csv_path"]: item["csv_file_sha256"] for item in records if "csv_file_sha256" in item}
            | {item["receipt_path"]: item["receipt_file_sha256"] for item in records if "receipt_file_sha256" in item}
            | {str(audit_path): file_sha256(audit_path)},
    }
