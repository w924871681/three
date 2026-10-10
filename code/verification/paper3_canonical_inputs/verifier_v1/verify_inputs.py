"""Dormant input-only verifier. Separate human execution authorization is mandatory.

Reviewed invocation: python -I -S -B -X pycache_prefix=<new run>/_never_created_pycache <absolute verify_inputs.py> --repo ...
This entry point never starts any model or statistics workflow.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

# Isolated Python excludes cwd/site-packages. Register only this reviewed source
# directory as a local package; never put the repository itself on sys.path.
if not __package__:
    package = types.ModuleType("paper3_civ_verifier")
    package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[package.__name__] = package
    __package__ = package.__name__

from .contract import CENTERS, SCENARIOS, ContractError, canonical_hash, file_sha256, identity_bank, read_json
from .history import recover_history
from .preflight import (CANDIDATE_ID, PROTOCOL_ID, check_loaded_modules, git_snapshot,
                        implementation_inventory, preflight, snapshot_protected)
from .safety import SafeWriter, contained_path, regular_path


def _time() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker(repo_name: str, auth_name: str, run_id: str, run_root: str,
            label: str, expected_dependency: str) -> None:
    """Spawn target: fresh interpreter and local RNG, no inherited generator state."""
    repo = Path(repo_name)
    state = preflight(repo, Path(auth_name), run_id, enable_numpy=True)
    if state["dependency_digest"] != expected_dependency:
        raise ContractError("child dependency binding differs from reviewed parent")
    root = regular_path(Path(run_root))
    expected_root = repo / "verification" / "paper3_canonical_inputs" / PROTOCOL_ID / run_id
    if root != expected_root.resolve(strict=True):
        raise ContractError("worker output root mismatch")
    if read_json(contained_path(root, "authorization_manifest.json")) != state["authorization"]:
        raise ContractError("worker has no matching reserved parent authorization")
    from .materialization import materialize_context
    worker_writer = SafeWriter(root)
    bundle = materialize_context(repo, label, worker_writer, state["definition_digest"],
                                 state["dependency_digest"], identity_bank(repo), state["pins"]["sources"])
    # Byte SHA captured immediately after exclusive creation is separate from
    # legacy array hashes and from scientific fingerprints.
    bundle["created_file_sha256"] = dict(worker_writer.created_sha256)
    check_loaded_modules(state["source_environment"]["environment"])
    end = preflight(repo, Path(auth_name), run_id, enable_numpy=False)
    if end["dependency_digest"] != state["dependency_digest"]:
        raise ContractError("worker source/environment changed during materialization")
    SafeWriter(root).write_json(f"contexts/{label}.json", bundle)


def _flatten(value, prefix: str = "") -> dict:
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            if key in {"files", "source_files", "replicate", "provenance_fingerprint",
                       "scenario_provenance_fingerprint", "base_provenance_fingerprint"}:
                continue
            result.update(_flatten(value[key], f"{prefix}/{key}"))
        return result
    return {prefix: value}


def worker_command(repo: Path, authorization_file: Path, run_id: str, label: str) -> list[str]:
    if label not in ("F1", "F2", "S1", "S2"):
        raise ContractError("invalid isolated context")
    cache = repo / "verification" / "paper3_canonical_inputs" / PROTOCOL_ID / run_id / "_never_created_pycache"
    return [sys.executable, "-I", "-S", "-B", "-X", f"pycache_prefix={cache}",
            str(Path(__file__).resolve()), "--repo", str(repo), "--authorization-file", str(authorization_file),
            "--run-id", run_id, "--internal-context", label]


def compare_fields(left: dict, right: dict) -> list[dict]:
    """Exact per-field F/S comparison; never compare storage/replicate paths."""
    rows = []
    for collection in ("base", "scenarios", "roles", "references"):
        keys = sorted(set(left[collection]) | set(right[collection]))
        for key in keys:
            a, b = _flatten(left[collection].get(key, {})), _flatten(right[collection].get(key, {}))
            for field in sorted(set(a) | set(b)):
                status = "NOT_AVAILABLE" if field not in a or field not in b else (
                    "MATCH" if canonical_hash(a[field]) == canonical_hash(b[field]) else "MISMATCH")
                # Values are input/profile/resource metadata only, not outcomes.
                rows.append({"collection": collection, "entry": key, "field": field,
                             "status": status, "F_value": a.get(field), "S_value": b.get(field)})
    return rows


def repeatability_checks(bundles: dict) -> list[dict]:
    checks = []
    for a, b in (("F1", "F2"), ("S1", "S2")):
        for collection, count in (("base",20),("scenarios",80),("roles",5760),("references",160)):
            first, second = bundles[a][collection], bundles[b][collection]
            keys = sorted(set(first) | set(second))
            mismatches = [key for key in keys if first.get(key, {}).get("provenance_fingerprint") !=
                          second.get(key, {}).get("provenance_fingerprint")]
            checks.append({"matrix": "M1", "replicates": [a,b], "collection": collection,
                           "expected_count": count, "count_a": len(first), "count_b": len(second),
                           "mismatched_entries": mismatches,
                           "pass": len(first) == len(second) == count and not mismatches})
        checks.append({"matrix": "M1", "replicates": [a,b], "field": "input_bundle_digest",
                       "pass": bundles[a]["input_bundle_digest"] == bundles[b]["input_bundle_digest"]})
    for label, bundle in bundles.items():
        for center in CENTERS:
            for role in ("warmup", "reference"):
                values = [bundle["references"][f"{center}/{scenario}/{role}"]["feature_legacy_array_digest"]
                          for scenario in SCENARIOS]
                checks.append({"matrix": "M5", "replicate": label, "center": center, "role": role,
                               "check": "pre_onset_scene_input_parity", "pass": len(set(values)) == 1})
    return checks


def _finish(writer: SafeWriter, state: dict, started: str, protected_before: dict,
            git_before: dict, *, complete: bool, error: str | None = None) -> int:
    protected_after = snapshot_protected(Path(state["git"]["root"]), state["pins"])
    git_after = git_snapshot(Path(state["git"]["root"]))
    implementation_after = implementation_inventory()
    unchanged = (protected_before == protected_after and git_before == git_after and
                 implementation_after == state["source_environment"]["implementation"])
    output_unchanged = all(file_sha256(contained_path(writer.root, relative)) == expected
                           for relative, expected in writer.created_sha256.items())
    unchanged = unchanged and output_unchanged
    manifest = {"schema": "paper3-civ-run-manifest-v1", "candidate_id": CANDIDATE_ID,
                "verification_id": PROTOCOL_ID, "run_id": state["authorization"]["run_id"],
                "authorization_sha256": state["authorization_sha256"],
                "definition_digest": state["definition_digest"], "dependency_digest": state["dependency_digest"],
                "started": started, "finished": _time(), "complete": complete and unchanged,
                "frozen_files_unchanged": unchanged, "error": error,
                "file_bindings": writer.inventory(), "initial_state_verified": False,
                "R2": "PENDING_SEPARATE_AUTHORIZATION", "R3": "PENDING_SEPARATE_AUTHORIZATION"}
    writer.write_json("run_manifest.json", manifest)
    inventory = writer.inventory()
    writer.write_json("outputs_inventory.json", {"schema": "paper3-civ-output-inventory-v1", "files": inventory})
    final_inventory = writer.inventory()
    receipt = {"schema": "paper3-civ-execution-receipt-v1", "run_manifest_sha256": final_inventory["run_manifest.json"],
               "outputs_inventory_sha256": final_inventory["outputs_inventory.json"],
               "protected_start_sha256": protected_before, "protected_end_sha256": protected_after,
               "git_start": git_before, "git_end": git_after, "originals_unchanged": unchanged,
               "exit_code": 0 if complete and unchanged else 2,
               "status": "INPUT_ONLY_CHECKS_COMPLETED" if complete and unchanged else "FAILED_PARTIAL_RETAINED",
               "initial_state_verified": False, "model_execution_performed": False,
               "statistics_performed": False, "R2": "PENDING_SEPARATE_AUTHORIZATION",
               "R3": "PENDING_SEPARATE_AUTHORIZATION", "error": error}
    writer.write_json("execution_receipt.json", receipt)
    return receipt["exit_code"]


def run(repo: Path, authorization_file: Path, run_id: str) -> int:
    started = _time()
    state = preflight(repo, authorization_file, run_id, enable_numpy=False)
    repo = Path(state["git"]["root"])
    history_info = recover_history(Path(state["pins"]["history_session"]["path"]),
                                   state["pins"]["history_session"]["sha256"])
    protected_before = snapshot_protected(repo, state["pins"])
    git_before = state["git"]
    writer = SafeWriter.reserve(repo, run_id)
    try:
        writer.write_json("authorization_manifest.json", state["authorization"])
        writer.write_json("definition_manifest.json", state["definition"])
        writer.write_json("source_environment_manifest.json", {
            **state["source_environment"], "recovered_history": history_info,
            "history_is_evidence_only": True, "definition_digest": state["definition_digest"],
            "dependency_digest": state["dependency_digest"]})
        bank = identity_bank(repo)
        writer.write_json("bank_feasibility_inventory.json", bank)
        # Explicit fresh interpreters retain all isolation flags. Python 3.11
        # multiprocessing does not forward -X pycache_prefix, so it is avoided.
        # Sequential replicates reduce RAM without sharing scientific RNG state.
        bundles = {}
        for label in ("F1", "F2", "S1", "S2"):
            child = subprocess.run(worker_command(repo, authorization_file, run_id, label),
                                   stdin=subprocess.DEVNULL, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if child.returncode != 0:
                raise ContractError(f"input materialization process {label} failed: {child.returncode}")
            bundles[label] = read_json(contained_path(writer.root, f"contexts/{label}.json"))
            writer._record(f"contexts/{label}.json")  # Acyclic parent publication binding.
            for relative, expected in bundles[label]["created_file_sha256"].items():
                if file_sha256(contained_path(writer.root, relative)) != expected:
                    raise ContractError("input container changed since exclusive creation")
        for collection, filename in (("base", "base_input_inventory.jsonl"),
                                     ("scenarios", "scenario_input_inventory.jsonl"),
                                     ("roles", "stage_role_inventory.jsonl"),
                                     ("references", "reference_input_inventory.jsonl")):
            writer.write_jsonl(filename, ({"replicate": label, "entry_key": key, **value}
                                         for label, bundle in bundles.items()
                                         for key, value in sorted(bundle[collection].items())))
        checks = repeatability_checks(bundles)
        resolved = {label: bundle["resolved_config"] for label, bundle in bundles.items()}
        writer.write_json("resolved_configuration_manifest.json", resolved)
        checks.append({"matrix": "M0", "check": "resolved_MainCfg_equal_across_four_processes",
                       "pass": len({canonical_hash(value) for value in resolved.values()}) == 1})
        writer.write_csv("full_vs_singleton_matrix.csv", compare_fields(bundles["F1"], bundles["S1"]))
        # Resume/scheduling reads fixed arrays only. It never calls the generator.
        active = preflight(repo, authorization_file, run_id, enable_numpy=True)
        if active["dependency_digest"] != state["dependency_digest"]:
            raise ContractError("parent dependency binding changed")
        from .records import inspect_existing
        from .schedule import verify_schedule
        mapping = inspect_existing(repo, bundles)
        writer.write_csv("existing_input_match_inventory.csv", mapping["inventory"])
        writer.write_csv("existing_input_field_match_inventory.csv", mapping["field_inventory"])
        writer.write_json("existing_group_input_parity.json", mapping["groups"])
        writer.write_json("existing_input_mapping_summary.json", mapping["summary"])
        schedule_results = {}
        for label in ("F1", "S1"):
            schedule_results[label] = verify_schedule(bundles[label], writer.root)
        checks.extend({"matrix": "M8_M10", "replicate": label, **value}
                      for label, value in schedule_results.items())
        writer.write_jsonl("repeatability_schedule_resume_checks.jsonl", checks)
        repeat_ok = all(item["pass"] for item in checks if "pass" in item)
        schedule_ok = all(item["all_checks_pass"] for item in schedule_results.values())
        provenance_ok = (mapping["summary"]["r0_qualified_count"] == 1200 and
                         mapping["summary"]["expected_source_cohorts_match"] and
                         mapping["summary"]["record_set_complete"] and
                         not mapping["summary"]["unverifiable_groups"])
        complete = repeat_ok and schedule_ok and provenance_ok
        certificate = {"schema": "paper3-civ-input-certificate-v1", "checks_completed": complete,
                       "status": "PROVISIONAL_REQUIRES_FINAL_SUCCESS_RECEIPT",
                       "valid_only_with_final_success_receipt": True,
                       "definition_digest": state["definition_digest"], "dependency_digest": state["dependency_digest"],
                       "input_bundle_digests": {k: v["input_bundle_digest"] for k,v in bundles.items()},
                       "M0": "VERIFIED_CURRENT_BINDINGS_EXACT_OLD_SOURCE_RECOVERED_HISTORY_ENV_NOT_VERIFIED",
                       "M1": repeat_ok, "M2": "EXACT_FIELD_COMPARISON_REPORTED_NO_CONTEXT_EQUIVALENCE_ASSUMED",
                       "M3_M4_M5_M6": "INVENTORIES_RECORDED_NO_MODEL_EXECUTION",
                       "M7": mapping["summary"], "M8": schedule_ok,
                       "M9": "SAVED_INITIAL_METADATA_ONLY_PENDING_SEPARATE_AUTHORIZATION",
                       "M10": "INPUT_RESUME_GATES_CHECKED_MODEL_RESUME_FORBIDDEN",
                       "R0": "SEE_PER_RECORD_BYTE_AND_SOURCE_QUALIFICATION",
                       "R1": "SEE_PER_RECORD_SAVED_FIELD_COVERAGE_ONLY",
                       "R2": "PENDING_SEPARATE_AUTHORIZATION", "R3": "PENDING_SEPARATE_AUTHORIZATION",
                       "initial_state_verified": False, "historical_environment_reproduced": False,
                       "full_scientific_certification": False, "original_statistics_replaced": False,
                       "existing_mismatched_groups": mapping["summary"]["mismatched_groups"],
                       "outcome_based_reuse_or_protocol_selection": False}
        writer.write_json("validation_certificate.json", certificate)
        check_loaded_modules(state["source_environment"]["environment"])
        end = preflight(repo, authorization_file, run_id, enable_numpy=False)
        if end["dependency_digest"] != state["dependency_digest"]:
            raise ContractError("source/environment binding changed at end")
        for bundle in bundles.values():
            for relative, expected in bundle["created_file_sha256"].items():
                if file_sha256(contained_path(writer.root, relative)) != expected:
                    raise ContractError("immutable input or inventory bytes changed during verification")
        return _finish(writer, state, started, protected_before, git_before, complete=complete)
    except Exception as exc:
        writer.write_json("failure.json", {"status": "FAILED_PARTIAL_RETAINED", "type": type(exc).__name__,
                                          "message": str(exc), "no_retry_or_cleanup": True})
        return _finish(writer, state, started, protected_before, git_before,
                       complete=False, error=f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--internal-context", choices=("F1","F2","S1","S2"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.internal_context:
            state = preflight(args.repo, args.authorization_file, args.run_id, enable_numpy=False)
            root = args.repo / "verification" / "paper3_canonical_inputs" / PROTOCOL_ID / args.run_id
            _worker(str(args.repo), str(args.authorization_file), args.run_id, str(root),
                    args.internal_context, state["dependency_digest"])
            return 0
        return run(args.repo, args.authorization_file, args.run_id)
    except Exception as error:
        print(f"INPUT_ONLY_VERIFICATION_STOPPED: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
