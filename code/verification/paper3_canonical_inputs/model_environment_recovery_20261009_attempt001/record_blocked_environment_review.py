"""Stdlib-only evidence collection; no package/model imports or installations.

This records an already identified STOP condition. It does not repair an
environment, generate input, load weights, run tests or calculate statistics.
All output files are exclusive. Original files are read only.
"""
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
INPUT = REPO / "verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1/CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"
PRIOR = REPO / "results/p7_7_integrity_replication_batch20_v1"
PACKAGE = REPO / "handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_20261009_BLOCKED_V1"
BASE = Path(r"C:\Users\92487\anaconda3")
SCIENCE = {"numpy", "pandas", "torch", "river", "psutil", "scipy", "scikit-learn", "torchaudio", "torchvision"}

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def publish(name, obj):
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")

def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True, encoding="utf-8").strip()

def clean_url(value):
    if not isinstance(value, str):
        return value
    u = urlsplit(value)
    if u.scheme in {"https", "http"}:
        return urlunsplit((u.scheme, u.hostname or "", u.path, "", ""))
    return value if u.scheme == "file" else None

def binding(path):
    return {"path": str(path), "sha256": sha(path), "size": path.stat().st_size}

def check_ledger(root, ledger):
    mismatches = []
    for relative, expected in ledger.items():
        path = root / relative
        if not path.is_file():
            mismatches.append({"path": str(path), "reason": "missing"})
        elif sha(path) != expected:
            mismatches.append({"path": str(path), "reason": "sha256_mismatch"})
    return {"checked_files": len(ledger), "mismatches": mismatches, "pass": not mismatches}

def fields(text):
    result = {}
    for n, line in enumerate(text.splitlines(), 1):
        if ": " not in line:
            continue
        k, v = line.split(": ", 1)
        if k in {"Name", "Version", "Requires-Python", "Requires-Dist", "Tag"}:
            result.setdefault(k, []).append({"line": n, "value": v})
    return result

def environment(prefix):
    site = prefix / "Lib/site-packages"
    meta = {}
    for path in sorted(site.glob("*.dist-info/METADATA")):
        data = fields(path.read_text(encoding="utf-8"))
        if not data.get("Name") or not data.get("Version"):
            continue
        name = data["Name"][0]["value"].lower().replace("_", "-")
        entry = {"version": data["Version"][0]["value"], "metadata": binding(path), "fields": data}
        for n in ("WHEEL", "INSTALLER", "RECORD", "direct_url.json"):
            p = path.parent / n
            if p.is_file():
                entry[n] = binding(p)
                if n == "WHEEL":
                    entry["wheel_tags"] = fields(p.read_text(encoding="utf-8")).get("Tag", [])
                elif n == "INSTALLER":
                    entry["installer"] = p.read_text(encoding="utf-8").strip()
                elif n == "direct_url.json":
                    u = read(p)
                    entry["direct_origin"] = {"url": clean_url(u.get("url")), "dir_info": u.get("dir_info"), "archive_info": u.get("archive_info"), "vcs_info": u.get("vcs_info")}
        if name in SCIENCE:
            entry["native_files"] = [binding(p) for package_dir in (site/name.replace("-", "_"), site/(name.replace("-", "_")+".libs")) if package_dir.is_dir() for p in sorted(package_dir.rglob("*")) if p.is_file() and p.suffix.lower() in {".pyd", ".dll"}]
        meta[name] = entry
    conda = []
    for path in sorted((prefix / "conda-meta").glob("*.json")):
        data = read(path)
        if data.get("name") in SCIENCE | {"python", "python_abi", "pytorch"}:
            conda.append({"record": binding(path), "name": data.get("name"), "version": data.get("version"), "build": data.get("build"), "channel": clean_url(data.get("channel")), "url": clean_url(data.get("url")), "sha256": data.get("sha256"), "md5": data.get("md5")})
    result = {"prefix": str(prefix), "python_executable": binding(prefix/"python.exe") if (prefix/"python.exe").is_file() else None, "distributions": meta, "conda_records": conda, "scope": "READ_ONLY_INSTALLED_METADATA_AND_RELEVANT_NATIVE_FILE_HASHES_NO_IMPORT", "history_binding": "NOT_VERIFIED"}
    history = prefix / "conda-meta/history"
    if history.is_file():
        result["conda_history"] = binding(history)
    for lib in sorted(prefix.glob("python3*.dll")):
        result.setdefault("python_runtime_dlls", []).append(binding(lib))
    result["inventory_fingerprint_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return result

def main():
    started = now()
    if (HERE / "EVIDENCE.json").exists():
        raise RuntimeError("exclusive evidence already exists; do not overwrite")
    initial_git = {"head": git("rev-parse", "HEAD"), "tracked_status": git("status", "--porcelain=v1", "-uno"), "repo_root": git("rev-parse", "--show-toplevel")}
    baseline_path = REPO / "verification/paper3_canonical_inputs/execution_20261009/original_protected_start_sha256.json"
    baseline = read(baseline_path)
    preservation = check_ledger(REPO, baseline)
    historical_output = check_ledger(REPO, read(REPO/"audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json")["output_hashes"])
    input_manifest = read(INPUT/"run_manifest.json")
    inputs = check_ledger(INPUT, input_manifest["file_bindings"])
    prior_reports = check_ledger(PRIOR, read(PRIOR/"DELIVERY_MANIFEST.json")["files_sha256"])
    package_manifest = read(PACKAGE/"PACKAGE_MANIFEST.json")
    # Independent package copies are kept as historical versions; no editing.
    package_sha = binding(PACKAGE/"PACKAGE_MANIFEST.json")
    package_preservation = check_ledger(PACKAGE, package_manifest["files_sha256"])
    environments = {"rcf-dti-py311": environment(BASE/"envs/rcf-dti-py311"), "base": environment(BASE), "tf-gpu": environment(BASE/"envs/tf-gpu")}
    other_prefix = Path(r"D:\DT_UPDATE_WORKSPACE\.conda\jnca-cuda")
    if (other_prefix/"python.exe").is_file():
        environments["registered_jnca_cuda"] = environment(other_prefix)
    publish("INSTALLED_ENVIRONMENT_INVENTORIES.json", environments)
    frozen = (REPO/"configs/requirements_frozen.txt").read_text(encoding="utf-8")
    pinned = {}
    for n, line in enumerate(frozen.splitlines(), 1):
        m = re.fullmatch(r"([\w.-]+)==(.+)", line.strip())
        if m:
            name = m.group(1).lower().replace("_", "-")
            pinned[name] = {"line": n, "version": m.group(2)}
    installed = environments["rcf-dti-py311"]["distributions"]
    pin_comparison = [{"name": name, "frozen_version": item["version"], "requirements_line": item["line"], "installed_version": installed.get(name,{}).get("version"), "exact": installed.get(name,{}).get("version") == item["version"]} for name,item in pinned.items()]
    core_files = ["configs/requirements_frozen.txt", "audits/environment.json", "scripts/run_p7.py", "scripts/run_p7_7_final.py", "core/p7.py", "configs/p7_baseline_grids.json", "docs/P7_PROTOCOL_AND_EXECUTION_LOG.md", "audits/P7_PRE_OUTCOME_PROTOCOL_FREEZE.json", "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json", "artifacts/p7_6b_A1_estimator.pt", "artifacts/p7_6b_A1_scaler.json", "verification/paper3_canonical_inputs/replication_executor_batch20_v1/provenance.py", "verification/paper3_canonical_inputs/replication_executor_batch20_v1/executor_driver.py", "verification/paper3_canonical_inputs/replication_statistics_batch20_v1/statistics.py"]
    source_bindings = {name: binding(REPO/name) for name in core_files if (REPO/name).is_file()}
    receipt = read(INPUT/"execution_receipt.json")
    f1 = read(INPUT/"inventories/F1/materialization_manifest.json")
    raw = REPO/"results/p7_7/raw"
    original_csv = len(list(raw.glob("*.csv")))
    original_receipts = len(list(raw.glob("*.integrity.json")))
    old_receipt_index = PACKAGE/"indexes/ORIGINAL_RAW_FILE_INDEX.csv"
    with old_receipt_index.open(encoding="utf-8-sig", newline="") as f:
        index_rows = list(csv.DictReader(f))
    final_git = {"head": git("rev-parse", "HEAD"), "tracked_status": git("status", "--porcelain=v1", "-uno"), "repo_root": git("rev-parse", "--show-toplevel")}
    evidence = {"schema": "paper3-authorized-environment-recovery-blocked-evidence-v1", "status": "BLOCKED", "review_started_utc": started, "review_finished_utc": now(), "review_times_are_not_model_experiment_times": True, "repo": str(REPO), "authorization": {"independent_environment_recovery": True, "resume_when_all_gates_pass": True, "stop_if_frozen_dependency_unknown_or_scientific_dependency_changes": True}, "actions": {"package_imports": False, "environment_created": False, "packages_installed_or_changed": False, "generator_executed": False, "model_loaded": False, "warmup_or_optimizer_executed": False, "project_tests_reexecuted": False, "replication_started": False, "bootstrap_or_statistics_executed": False, "executor_modified": False}, "git_start": initial_git, "git_end": final_git, "git_tracked_and_head_unchanged": initial_git == final_git, "original_preservation": preservation, "original_output_ledger": historical_output, "prior_blocked_delivery_preservation": prior_reports, "historical_handoff_package_preservation": package_preservation, "stage_b_all_bound_files_preservation": inputs, "input_manifest": binding(INPUT/"run_manifest.json"), "input_receipt": {**binding(INPUT/"execution_receipt.json"), "saved_status": receipt.get("status"), "saved_exit_code": receipt.get("exit_code")}, "fixed_F1_input_bundle_digest": f1["input_bundle_digest"], "F1_manifest": binding(INPUT/"inventories/F1/materialization_manifest.json"), "environment_inventory": binding(HERE/"INSTALLED_ENVIRONMENT_INVENTORIES.json"), "candidate_environment_fingerprints": {k: v["inventory_fingerprint_sha256"] for k,v in environments.items()}, "requirements_exact_pins_compared": pin_comparison, "requirements_exact_pin_count": len(pinned), "all_exact_pins_match_existing_py311_metadata": all(v["exact"] for v in pin_comparison), "missing_required_py311_distributions": sorted({"psutil","river"}-set(installed)), "original_csv_count": original_csv, "original_receipt_count": original_receipts, "original_raw_index_rows": len(index_rows), "source_bindings": source_bindings, "historical_handoff_manifest": package_sha, "historical_handoff_manifest_keys": list(package_manifest), "historical_handoff_zip": binding(PACKAGE.with_suffix(".zip")), "blockers": [{"id": "B1", "level": "NOT_VERIFIED", "claim": "Exact psutil frozen/final runtime version and acquisition provenance cannot be established from searched evidence."}, {"id": "B2", "level": "VERIFIED_DECLARED_DEPENDENCY_CONFLICT", "claim": "River 0.23.0 METADATA requires pandas >=2.2.3,<3.0.0; frozen pandas==3.0.5 lies outside this declared interval. This does not itself prove runtime failure. Historical --no-deps evidence does not prove final dependency closure."}], "public_primary_source": "https://raw.githubusercontent.com/online-ml/river/0.23.0/pyproject.toml", "new_trajectories_completed": 0, "new_groups_certified": 0, "initial_states_certified": 0, "model_worker_count": 0, "new_results_and_difference": "NOT_COMPUTED", "remaining_executor_issues_static_only": ["separate input-generation environment from independently authorized model runtime without rewriting Stage B", "fresh exclusive output root or manifest-verified existing blocked-output handling", "unfinished Stage E runtime_guard", "exclusive phase attempt identifiers for fail/resume"]}
    publish("EVIDENCE.json", evidence)
    print(json.dumps({"status": evidence["status"], "original_files": preservation["checked_files"], "original_bytes_unchanged": preservation["pass"], "original_output_ledger": historical_output, "stage_b_bound_files": inputs, "prior_delivery": prior_reports, "fixed_F1": f1["input_bundle_digest"], "exact_requirement_pins": len(pinned), "exact_metadata_pins_match": evidence["all_exact_pins_match_existing_py311_metadata"], "installed_anything": False, "model_trajectories": 0, "evidence": str(HERE/"EVIDENCE.json")}, ensure_ascii=False))
    if not all([preservation["pass"], historical_output["pass"], inputs["pass"], prior_reports["pass"], package_preservation["pass"], initial_git == final_git]):
        raise RuntimeError("preservation check failed; evidence retained; no model execution")

if __name__ == "__main__":
    main()
