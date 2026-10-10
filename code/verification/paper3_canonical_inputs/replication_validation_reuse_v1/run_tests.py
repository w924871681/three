"""Run only independent fake/native-NEW-fixture tests, never science programs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-root", required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError("independent test runner requires -I -S -B")
    root = Path(args.record_root).resolve()
    if root.parent != HERE / "synthetic_tests" or root.exists():
        raise RuntimeError("exclusive unused direct synthetic_tests child required")
    # The ONLY writes/native fixture changes are in this NEW independent dir.
    root.mkdir(parents=True, exist_ok=False)
    fixtures = root / "native_fixtures"
    fixtures.mkdir()
    before = {str(p): sha(p) for p in HERE.glob("*.py")}
    sys.path.insert(0, str(HERE))
    import test_session
    import test_windows_handles
    test_windows_handles.FIXTURE_PARENT = str(fixtures)
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py", top_level_dir=str(HERE))
    with (root / "test_output.log").open("x", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = {str(p): sha(p) for p in HERE.glob("*.py")}
    same = before == after
    receipt = {"schema": "paper3-validation-reuse-independent-test-proof-v1", "observed_utc": datetime.now(timezone.utc).isoformat(),
        "all_pass": result.wasSuccessful() and not result.skipped and same,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "implementation_sha256": before, "source_bytes_unchanged_during_tests": same,
        "synthetic_read_counters": test_session.COUNTERS, "actual_native_fixture_checks": test_windows_handles.NATIVE_OBSERVATIONS,
        "native_fixture_parent": str(fixtures), "retained_native_backend_production_files_opened_or_locked": False,
        "original_provenance_source_metadata_import_fixture_included": True,
        "original_project_full_verifier_called": False,
        "original_project_verifier_or_scientific_programs_executed": False,
        "models_generators_training_statistics_or_bootstrap_executed": False,
        "production_pipeline_modified_or_hot_patched": False,
        "python_executable": sys.executable, "python_version": sys.version,
        "test_log_sha256": sha(root / "test_output.log"), "exit_code": 0 if result.wasSuccessful() and not result.skipped and same else 1}
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    with (root / "results.json").open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"all_pass": receipt["all_pass"], "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "results": str(root / "results.json"), "sha256": hashlib.sha256(payload).hexdigest(),
        "counters": test_session.COUNTERS, "actual_native_fixture_checks": test_windows_handles.NATIVE_OBSERVATIONS}, sort_keys=True), flush=True)
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
