"""Immutable input-reader scheduling and fail-closed resume simulations.

This module has no generator or model import/call. Worker counts alter reader
dispatch only, never materialization. It neither writes nor mutates arrays.
"""
from __future__ import annotations

import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .contract import CENTERS, METHODS, SCENARIOS, SEEDS, ContractError, canonical_hash, check_shapes, file_sha256, legacy_array_digest, read_json, stage_spans


def task_list() -> list[dict]:
    return [{"center_id": center, "seed": seed, "scenario": scenario, "method": method, "config_id": config_id}
            for center in CENTERS for seed in SEEDS for scenario in SCENARIOS for method, config_id in METHODS]


def _read_path(run_root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise ContractError("unsafe immutable-input path")
    root = Path(run_root).absolute()
    path = root.joinpath(*parts)
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ContractError("reparse immutable-input path")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or not path.is_file():
        raise ContractError("input path escapes verification run")
    return path


def resume_decision(saved: dict, expected: dict, *, initial_state_certificate: bool = False) -> dict:
    """Runner compatibility alone is insufficient; R2/R3 always remain blocked."""
    required = ("definition_digest", "dependency_digest", "input_bundle_digest", "scenario_fingerprint",
                "profile_fingerprint", "deployment_fingerprint", "group_reference_fingerprint",
                "role_manifest_fingerprint", "role_entry_count", "group_method_ids", "blob_manifest_fingerprint", "completion_state")
    checks = {field: field in saved and field in expected and saved[field] == expected[field] for field in required}
    checks["complete_24x3_role_coverage"] = saved.get("role_entry_count") == expected.get("role_entry_count") == 72
    checks["complete_five_method_group"] = saved.get("group_method_ids") == expected.get("group_method_ids") == [method for method, _ in METHODS]
    checks["input_materialization_complete"] = saved.get("completion_state") == expected.get("completion_state") == "INPUT_MATERIALIZATION_COMPLETE"
    input_qualified = all(checks.values())
    return {"input_resume_qualified": input_qualified, "checks": checks,
            "runner_hash_compatibility_used_as_scientific_exemption": False,
            "initial_state_verified": False, "external_initial_certificate_not_consumed": bool(initial_state_certificate),
            "model_resume_allowed": False, "r2_qualified": False, "r3_qualified": False,
            "status": "INPUT_METADATA_MATCH_ONLY_INITIAL_PENDING" if input_qualified else "SCIENTIFIC_INPUT_MISMATCH_BLOCKED"}


def _reader(task: dict, bundle: dict, run_root: Path) -> dict:
    import numpy as np  # loaded only in an explicitly authorized future run

    center, scenario = task["center_id"], task["scenario"]
    base = bundle["base"][str(center)]
    base_paths = {key: _read_path(run_root, path) for key, path in base["files"].items()}
    if set(base_paths) != {"x", "y", "ts"}:
        raise ContractError("unexpected base array keys")
    base_arrays = {key: np.load(path, mmap_mode="r", allow_pickle=False) for key, path in base_paths.items()}
    for array in base_arrays.values():
        if array.flags.writeable or array.dtype.hasobject:
            raise ContractError("mutable or object base input array")
    check_shapes(base_arrays["x"], base_arrays["y"], base_arrays["ts"])
    if legacy_array_digest(base_arrays["x"], base_arrays["y"], base_arrays["ts"]) != base["legacy_array_digest"]:
        raise ContractError("reader original base bytes changed")
    profile_relative = str(Path(base["files"]["x"]).parent / "profile.json")
    profile_path = _read_path(run_root, profile_relative)
    profile = read_json(profile_path)
    if profile != base["profile"] or canonical_hash(profile) != base["profile_digest"]:
        raise ContractError("reader original center profile changed")
    scene = bundle["scenarios"][f"{center}/{scenario}"]
    scene_paths = {key: _read_path(run_root, path) for key, path in scene["files"].items()}
    arrays = {key: np.load(path, mmap_mode="r", allow_pickle=False) for key, path in scene_paths.items()}
    if set(arrays) != {"x", "y", "ts", "feature_x"}:
        raise ContractError("unexpected scenario array keys")
    for value in arrays.values():
        if value.flags.writeable or value.dtype.hasobject:
            raise ContractError("mutable or object input array")
    x, y, ts, features = (arrays[key] for key in ("x", "y", "ts", "feature_x"))
    if x.shape != (17000, 24) or features.shape != (17000, 25) or y.shape != (17000,) or ts.shape != (17000,):
        raise ContractError("reader array shape violates frozen contract")
    if x.dtype != np.dtype("float32") or features.dtype != np.dtype("float32") or y.dtype != np.dtype("float32") or ts.dtype != np.dtype("int64"):
        raise ContractError("reader array dtype violates frozen contract")
    if not np.array_equal(features[:, :24], x) or not bool(np.all(features[:, 24] == np.float32(base["profile"]["dt"] / 4.0))):
        raise ContractError("reader engineered features differ from raw x plus dt/4")
    scenario_digest = legacy_array_digest(x, y, ts)
    feature_digest = legacy_array_digest(features, y, ts)
    if scenario_digest != scene["legacy_scenario_hash"] or feature_digest != scene["feature_arrays"]["legacy_array_digest"]:
        raise ContractError("reader scenario bytes changed")
    roles = []
    for stage in range(1, 25):
        spans = stage_spans(stage)
        for role, expected_span in zip(("update", "assessment", "service"), spans):
            item = bundle["roles"][f"{center}/{scenario}/{stage}/{role}"]
            a, b = item["span"]
            if (a, b) != tuple(expected_span) or item["raw_count"] != b - a or item["window_count"] != b - a - 96:
                raise ContractError("reader role span/count differs from frozen stage contract")
            if item["update_end_ts"] != int(ts[spans[0][1] - 1]) or item["decision_ts"] != int(ts[spans[1][1] - 1]):
                raise ContractError("reader stage time endpoints differ from raw timestamps")
            digest = legacy_array_digest(features[a:b], y[a:b], ts[a:b])
            if digest != item["legacy_role_hash"]:
                raise ContractError("reader stage-role bytes changed")
            roles.append({"stage": stage, "role": role, "legacy_role_hash": digest, "fingerprint": item["provenance_fingerprint"]})
    references = []
    for role in ("warmup", "reference"):
        item = bundle["references"][f"{center}/{scenario}/{role}"]
        a, b = item["span"]
        if (a, b) != ((0, 800) if role == "warmup" else (800, 1000)):
            raise ContractError("reader reference span differs from frozen raw indices")
        raw_digest = legacy_array_digest(x[a:b], y[a:b], ts[a:b])
        feature_reference_digest = legacy_array_digest(features[a:b], y[a:b], ts[a:b])
        if raw_digest != item["raw_legacy_array_digest"] or feature_reference_digest != item["feature_legacy_array_digest"]:
            raise ContractError("reader warmup/reference bytes changed")
        references.append({"role": role, "raw_digest": raw_digest, "feature_digest": feature_reference_digest})
    scientific = {"center_id": center, "scenario": scenario, "scenario_digest": scenario_digest,
                  "feature_digest": feature_digest, "scenario_fingerprint": scene["provenance_fingerprint"],
                  "base_digest": base["legacy_array_digest"], "profile_digest": base["profile_digest"],
                  "deployment": base["deployment"], "roles": roles, "references": references}
    blobs = {"base." + key: file_sha256(path) for key, path in base_paths.items()}
    blobs.update({"scenario." + key: file_sha256(path) for key, path in scene_paths.items()})
    blobs["profile.json"] = file_sha256(profile_path)
    blob_fingerprint = canonical_hash(blobs)
    scientific["blob_manifest_fingerprint"] = blob_fingerprint
    return {"task_key": f"{center}/{task['seed']}/{scenario}/{task['method']}",
            "group_key": f"{center}/{task['seed']}/{scenario}", "scientific_signature": canonical_hash(scientific),
            "blob_manifest_fingerprint": blob_fingerprint,
            "role_manifest_fingerprint": canonical_hash(roles), "role_entry_count": len(roles)}


def verify_schedule(bundle: dict, run_root: Path) -> dict:
    """M8/M10 only: six schedules of all 1200 references, read-only threads."""
    tasks = task_list()
    if len(tasks) != 1200:
        raise ContractError("incorrect frozen task count")
    orders = {"canonical": tasks, "reversed": list(reversed(tasks)),
              "fixed_permutation_7i": [tasks[(7 * index) % 1200] for index in range(1200)]}
    expected_keys = {f"{t['center_id']}/{t['seed']}/{t['scenario']}/{t['method']}" for t in tasks}
    checks, baseline, canonical_readers = [], None, None
    for workers in (1, 3):
        for name, ordered in orders.items():
            with ThreadPoolExecutor(max_workers=workers) as pool:
                returned = list(pool.map(lambda task: _reader(task, bundle, run_root), ordered))
            signatures = {row["task_key"]: row["scientific_signature"] for row in returned}
            coverage = len(returned) == 1200 and set(signatures) == expected_keys
            if baseline is None:
                baseline = signatures
                canonical_readers = {row["task_key"]: row for row in returned}
            invariant = coverage and signatures == baseline
            group_members = {}
            for row in returned:
                group_members.setdefault(row["group_key"], []).append(row["scientific_signature"])
            group_parity = len(group_members) == 240 and all(len(values) == 5 and len(set(values)) == 1 for values in group_members.values())
            checks.append({"workers": workers, "order": name, "task_count": len(returned), "coverage": coverage,
                           "input_invariance": invariant, "five_method_reference_parity": group_parity,
                           "task_signatures_digest": canonical_hash(signatures), "reader_only": True,
                           "generators_called": False, "models_called": False, "arrays_written": False})
    resume_inventory = []
    for task in tasks:
        center, scenario = task["center_id"], task["scenario"]
        task_key = f"{center}/{task['seed']}/{scenario}/{task['method']}"
        scene, base = bundle["scenarios"][f"{center}/{scenario}"], bundle["base"][str(center)]
        reader = canonical_readers[task_key]
        expected = {"definition_digest": bundle["definition_digest"], "dependency_digest": bundle["dependency_digest"],
                    "input_bundle_digest": bundle["input_bundle_digest"], "scenario_fingerprint": scene["provenance_fingerprint"],
                    "profile_fingerprint": base["profile_digest"], "deployment_fingerprint": canonical_hash(base["deployment"]),
                    "group_reference_fingerprint": canonical_hash({"center_id": center, "seed": task["seed"], "scenario": scenario,
                        "methods": list(METHODS), "scenario_fingerprint": scene["provenance_fingerprint"]}),
                    "role_manifest_fingerprint": reader["role_manifest_fingerprint"], "role_entry_count": reader["role_entry_count"],
                    "group_method_ids": [method for method, _ in METHODS], "blob_manifest_fingerprint": reader["blob_manifest_fingerprint"],
                    "completion_state": "INPUT_MATERIALIZATION_COMPLETE"}
        resume_inventory.append({"task_key": task_key, "expected_metadata": expected, "decision": resume_decision(dict(expected), expected)})
    expected = resume_inventory[0]["expected_metadata"]
    same = resume_decision(dict(expected), expected)
    mutated = dict(expected, scenario_fingerprint="0" * 64)
    mismatch = resume_decision(mutated, expected)
    missing_initial = resume_decision(dict(expected), expected, initial_state_certificate=True)
    incomplete_roles = resume_decision(dict(expected, role_entry_count=71), expected)
    incomplete_group = resume_decision(dict(expected, group_method_ids=expected["group_method_ids"][:-1]), expected)
    interrupted = resume_decision(dict(expected, completion_state="INTERRUPTED"), expected)
    stale_blob = resume_decision(dict(expected, blob_manifest_fingerprint="0" * 64), expected)
    resume_checks = {"same_input_metadata": same, "changed_input_with_compatible_runner": mismatch,
                     "external_initial_claim_cannot_upgrade_input_verifier": missing_initial,
                     "incomplete_stage_roles": incomplete_roles, "incomplete_five_method_group": incomplete_group,
                     "interrupted_new_verification_receipt": interrupted, "stale_input_blob_binding": stale_blob}
    negative = (mismatch, incomplete_roles, incomplete_group, interrupted, stale_blob)
    pass_resume = (same["input_resume_qualified"] and all(not item["input_resume_qualified"] for item in negative)
                   and all(not item["model_resume_allowed"] for item in resume_checks.values())
                   and len(resume_inventory) == 1200 and all(item["decision"]["input_resume_qualified"] for item in resume_inventory))
    return {"schema": "p7.7-fixed-input-reader-schedule-v1", "checks": checks, "resume_checks": resume_checks,
            "all_checks_pass": all(c["coverage"] and c["input_invariance"] and c["five_method_reference_parity"] for c in checks) and pass_resume,
            "resume_inventory": resume_inventory, "original_claims_read_or_written": False,
            "initial_state_verified": False, "r2_qualified": False, "r3_qualified": False}
