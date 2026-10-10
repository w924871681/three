"""Authorized Stage A: exactly 42 existing independent synthetic unittest methods.

No canonical/project data generator, model, warm-up or scientific statistic is
executed. Approved exact file hashes gate imports before NumPy module code runs.
Every log/result file is exclusive-create inside this independent execution root.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parent
VERIFIER = ROOT.parent / "verifier_v1"
REPO = ROOT.parents[2]
ENVIRONMENT = ROOT / "environment.reviewed.json"
EXPECTED_TEST_FILES = (
    "test_contract.py", "test_materialization.py", "test_records.py",
    "test_safety_history_entry.py", "test_schedule.py",
)
FORBIDDEN_MODULES = {"core", "imported", "scripts", "torch", "pandas", "sklearn", "verification"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(relative, value):
    path = ROOT / relative
    with path.open("xb") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode() + b"\n")
    return str(path)


def inventory():
    paths = sorted(VERIFIER.rglob("*.py")) + [VERIFIER / "source_pins.json"]
    return {path.relative_to(VERIFIER).as_posix(): sha256(path) for path in paths}


def all_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from all_tests(item)
        else:
            yield item


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise RuntimeError("supply a numeric exclusive attempt ID")
    attempt = int(sys.argv[1])
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError("Stage A requires -I -S -B")
    expected_cache = ROOT / "_never_created_pycache"
    if not sys.pycache_prefix or Path(sys.pycache_prefix).resolve() != expected_cache or expected_cache.exists():
        raise RuntimeError("require nonexistent execution-root pycache_prefix")
    approved = json.loads(ENVIRONMENT.read_text(encoding="utf-8"))
    if sha256(sys.executable) != approved["python_executable_sha256"]:
        raise RuntimeError("unapproved interpreter bytes")
    start = inventory()
    if attempt == 1:
        save_json("stage_a_implementation_start_sha256.json", start)
    save_json(f"stage_a_attempt_{attempt:02d}_implementation_sha256.json", start)

    bound = {str((VERIFIER / name).resolve()).casefold(): digest for name, digest in start.items()}
    bound[str(Path(__file__).resolve()).casefold()] = sha256(__file__)
    for root_key, key in (
        ("stdlib_root", "stdlib_files_sha256"),
        ("numpy_parent", "numpy_files_sha256"),
    ):
        root = Path(approved[root_key])
        for relative, digest in approved[key].items():
            path = root / relative
            if sha256(path) != digest:
                raise RuntimeError("approved import dependency changed: " + str(path))
            bound[str(path.resolve()).casefold()] = digest
    for filename, digest in approved["runtime_binary_files_sha256"].items():
        if sha256(filename) != digest:
            raise RuntimeError("approved runtime binary changed: " + filename)
        bound[str(Path(filename).resolve()).casefold()] = digest

    def check_origin(filename, module_name):
        if filename in (None, "built-in", "frozen") or str(filename).startswith("<"):
            return
        path = Path(filename).resolve()
        expected = bound.get(str(path).casefold())
        if expected is None or sha256(path) != expected:
            raise RuntimeError(f"unapproved import: {module_name}: {path}")

    class ApprovedImportGuard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in FORBIDDEN_MODULES:
                raise RuntimeError("forbidden scientific/project import: " + fullname)
            for finder in (
                importlib.machinery.BuiltinImporter,
                importlib.machinery.FrozenImporter,
                importlib.machinery.PathFinder,
            ):
                spec = finder.find_spec(fullname, path, target)
                if spec is not None:
                    check_origin(spec.origin, fullname)
                    return spec
            return None

    sys.meta_path.insert(0, ApprovedImportGuard())
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in FORBIDDEN_MODULES:
            raise RuntimeError("scientific/project module was loaded before guard")
        check_origin(getattr(module, "__file__", None), name)
    sys.path.append(approved["numpy_parent"])

    # Defense against actual project source execution even if an extraction
    # would bypass normal import machinery. New verifier mock providers are
    # permitted; exact original generator filenames are never executable here.
    prohibited_sources = {"core/data.py", "core/p3_2_data.py", "imported/ravm_dt/main_cfg.py", "imported/ravm_dt/sim.py"}
    def audit(event, args):
        if event == "exec":
            name = getattr(args[0], "co_filename", "").replace("\\", "/")
            if name in prohibited_sources:
                raise RuntimeError("actual project AST/generator execution forbidden during Stage A: " + name)
            full = Path(name) if name and not name.startswith("<") else None
            if full is not None and full.is_absolute():
                resolved = full.resolve()
                if REPO in resolved.parents and VERIFIER not in resolved.parents and resolved != Path(__file__).resolve():
                    raise RuntimeError("project code execution outside verifier forbidden")
        if event == "open" and len(args) >= 3:
            filename, mode, flags = args[:3]
            if isinstance(filename, (str, bytes, os.PathLike)):
                writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing:
                    resolved = Path(filename).resolve()
                    if ROOT not in resolved.parents:
                        raise RuntimeError("Stage A write outside independent execution root forbidden")
    sys.addaudithook(audit)

    synthetic = types.ModuleType("paper3_civ_tests")
    synthetic.__path__ = [str(VERIFIER)]
    sys.modules[synthetic.__name__] = synthetic
    suite = unittest.TestSuite()
    method_ids = []
    for filename in EXPECTED_TEST_FILES:
        path = VERIFIER / "tests" / filename
        check_origin(path, filename)
        tree = ast.parse(path.read_bytes(), filename=str(path))
        names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        name = "paper3_stage_a_" + path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        test_module = importlib.util.module_from_spec(spec)
        sys.modules[name] = test_module
        spec.loader.exec_module(test_module)
        file_suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
        cases = list(all_tests(file_suite))
        if len(cases) != len(names):
            raise RuntimeError("test discovery differs from exact existing method inventory")
        suite.addTests(cases)
        method_ids.extend(case.id() for case in cases)
    if len(method_ids) != 42 or len(set(method_ids)) != 42:
        raise RuntimeError(f"must execute exactly the existing 42 methods, found {len(method_ids)}")
    save_json(f"stage_a_attempt_{attempt:02d}_method_inventory.json", method_ids)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    with (ROOT / f"stage_a_attempt_{attempt:02d}.log").open("xb") as handle:
        handle.write(output.getvalue().encode("utf-8"))
    end = inventory()
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in FORBIDDEN_MODULES:
            raise RuntimeError("forbidden project/model import occurred")
        check_origin(getattr(module, "__file__", None), name)
    summary = {
        "scope": "STAGE_A_SYNTHETIC_UNIT_TESTS_ONLY",
        "attempt": attempt, "tests_run": result.testsRun,
        "failures": [{"test": case.id(), "traceback": text} for case, text in result.failures],
        "errors": [{"test": case.id(), "traceback": text} for case, text in result.errors],
        "skipped": [{"test": case.id(), "reason": reason} for case, reason in result.skipped],
        "all_42_pass": result.testsRun == 42 and result.wasSuccessful() and not result.skipped,
        "implementation_unchanged_during_test": end == start,
        "implementation_start_sha256": start, "implementation_end_sha256": end,
        "environment_manifest_sha256": sha256(ENVIRONMENT),
        "generator_executed": False, "model_executed": False,
        "statistics_executed": False,
        "tests_are_not_experimental_performance_results": True,
        "approved_import_guard": "EXACT_BYTE_BINDING_BEFORE_MODULE_CODE",
    }
    save_json(f"stage_a_attempt_{attempt:02d}_results.json", summary)
    print(output.getvalue())
    print(json.dumps({key: summary[key] for key in (
        "tests_run", "all_42_pass", "implementation_unchanged_during_test",
        "generator_executed", "model_executed", "statistics_executed",
    )}))
    return 0 if summary["all_42_pass"] and summary["implementation_unchanged_during_test"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

