"""Authorized Stage C synthetic tests, with exact import and new-output guards.

The original 42 Stage A tests remain a separate completed gate. This launcher
discovers every test method in the new replication executor and rejects changes
during execution. No canonical data, model, generator or statistic is executed.
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
import stat
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
EXECUTOR = ROOT
RESULTS = REPO / "results" / "p7_7_integrity_replication_batch20_env_v2"
PRIOR_EXECUTION = ROOT.parent / "execution_20261009"
ENVIRONMENT = PRIOR_EXECUTION / "environment.reviewed.json"
ORIGINAL_SNAPSHOT = PRIOR_EXECUTION / "original_protected_start_sha256.json"
FORBIDDEN_MODULES = {"core", "imported", "scripts", "torch", "pandas", "sklearn", "verification", "river", "scipy"}


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def regular(path, must_exist=True):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RuntimeError("linked/reparse test path forbidden: " + str(ancestor))
    return path.resolve(strict=must_exist)


def inventory():
    return {path.relative_to(EXECUTOR).as_posix(): sha256(regular(path))
            for path in sorted(EXECUTOR.rglob("*.py"))}


def all_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from all_tests(item)
        else:
            yield item


def protected_check(snapshot):
    errors = [name for name, expected in snapshot.items() if sha256(regular(REPO / name)) != expected]
    return {"protected_files_checked": len(snapshot), "all_original_bytes_unchanged": not errors,
            "errors": errors,
            "original_csv_count": sum(name.startswith("results/p7_7/raw/") and name.endswith(".csv") for name in snapshot),
            "original_receipt_count": sum(name.startswith("results/p7_7/raw/") and name.endswith(".integrity.json") for name in snapshot)}


def main():
    if len(sys.argv) not in (2, 3) or not sys.argv[1].isdigit() or int(sys.argv[1]) < 1:
        raise RuntimeError("supply an exclusive numeric test attempt and optional reviewed model-runtime JSON")
    attempt = int(sys.argv[1])
    output_root = regular(RESULTS / "stage_c_tests" / f"attempt{attempt:03d}", must_exist=False)
    if output_root.exists():
        raise RuntimeError("refusing to overwrite a previous Stage C test attempt")
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError("Stage C synthetic tests require -I -S -B")
    expected_cache = output_root / "_never_created_pycache"
    if not sys.pycache_prefix or regular(sys.pycache_prefix, must_exist=False) != expected_cache or expected_cache.exists():
        raise RuntimeError("dedicated nonexistent Stage C bytecode prefix required")
    approved = json.loads(ENVIRONMENT.read_text(encoding="utf-8"))
    independent_runtime = None
    numpy_parent = approved["numpy_parent"]
    if len(sys.argv) == 3:
        runtime_path = regular(sys.argv[2])
        independent_runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        if (independent_runtime.get("schema") != "paper3-reviewed-independent-model-runtime-v1" or
                independent_runtime.get("environment_id") != "P7_7_REPLICATION_MODEL_ENV_V1" or
                regular(sys.executable) != regular(independent_runtime["python_executable"]) or
                regular(sys.base_prefix) != regular(independent_runtime["base_prefix"]) or
                regular(independent_runtime["stdlib_root"]) != regular(approved["stdlib_root"]) or
                sha256(Path(independent_runtime["base_prefix"])/"python.exe") != approved["python_executable_sha256"]):
            raise RuntimeError("independent synthetic runtime/base interpreter differs from reviewed contract")
        numpy_parent = independent_runtime["site_packages_root"]
        venv_cfg = Path(independent_runtime["prefix"])/"pyvenv.cfg"
        if "include-system-site-packages = false" not in venv_cfg.read_text(encoding="utf-8").casefold():
            raise RuntimeError("synthetic test venv must not share system site-packages")
    elif sha256(sys.executable) != approved["python_executable_sha256"]:
        raise RuntimeError("unapproved interpreter bytes")
    start = inventory()
    bound = {str(regular(EXECUTOR / name)).casefold(): digest for name, digest in start.items()}
    bound[str(regular(__file__)).casefold()] = sha256(__file__)
    for root_key, key in (("stdlib_root", "stdlib_files_sha256"), ("numpy_parent", "numpy_files_sha256")):
        source_root = Path(numpy_parent if root_key == "numpy_parent" else approved[root_key])
        for relative, digest in approved[key].items():
            path = regular(source_root / relative)
            if sha256(path) != digest:
                raise RuntimeError("approved synthetic-test dependency changed: " + str(path))
            bound[str(path).casefold()] = digest
    for filename, digest in approved["runtime_binary_files_sha256"].items():
        path = regular(filename)
        if sha256(path) != digest:
            raise RuntimeError("approved runtime binary changed")
        bound[str(path).casefold()] = digest

    def check_origin(filename, name):
        if filename in (None, "built-in", "frozen") or str(filename).startswith("<"):
            return
        path = regular(filename)
        expected = bound.get(str(path).casefold())
        if expected is None or sha256(path) != expected:
            raise RuntimeError(f"unapproved test import: {name}: {path}")

    class ApprovedImportGuard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in FORBIDDEN_MODULES:
                raise RuntimeError("actual project/model/scientific package import forbidden: " + fullname)
            for finder in (importlib.machinery.BuiltinImporter, importlib.machinery.FrozenImporter,
                           importlib.machinery.PathFinder):
                spec = finder.find_spec(fullname, path, target)
                if spec is not None:
                    check_origin(spec.origin, fullname)
                    return spec
            return None

    sys.meta_path.insert(0, ApprovedImportGuard())
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in FORBIDDEN_MODULES:
            raise RuntimeError("forbidden package loaded before test guard")
        check_origin(getattr(module, "__file__", None), name)
    sys.path.append(numpy_parent)
    sys.path.append(str(EXECUTOR))  # new, exactly byte-bound fixture modules only

    # Create only this fresh authorized attempt before installing its stricter
    # mutation guard. No original directory is changed or recreated.
    output_root.mkdir(parents=True, exist_ok=False)
    temporary = output_root / "temporary"
    temporary.mkdir(exist_ok=False)
    tempfile.tempdir = str(temporary)
    os.environ["TEMP"] = str(temporary)
    os.environ["TMP"] = str(temporary)
    os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"] = str(temporary)

    def writable(path, dir_fd=None, mutates_bytes=True):
        if isinstance(path, int):
            if path not in (0, 1, 2):
                raise RuntimeError("unidentified test write descriptor")
            return
        if dir_fd not in (None, -1):
            raise RuntimeError("test directory-FD mutation forbidden")
        target = regular(os.fsdecode(path), must_exist=False)
        if target != output_root and output_root not in target.parents:
            raise RuntimeError("test write outside its independent output root forbidden: " + str(target))
        if mutates_bytes and target.is_file() and target.stat().st_nlink > 1:
            raise RuntimeError("writing multiply linked test output forbidden")

    synthetic_filename = str(EXECUTOR / "synthetic_frozen_offline.py").casefold()
    def audit(event, args):
        if event == "exec":
            filename = getattr(args[0], "co_filename", "")
            if filename and not filename.startswith("<"):
                path = Path(filename)
                if path.is_absolute():
                    resolved = path.resolve()
                    if REPO in resolved.parents:
                        if str(resolved).casefold() == synthetic_filename:
                            return  # one literal fake offline diagnostic fixture
                        permitted_fixture_root = (EXECUTOR in resolved.parents or
                            regular(numpy_parent) in resolved.parents)
                        if not permitted_fixture_root or str(resolved).casefold() not in bound:
                            raise RuntimeError("actual project source execution forbidden in synthetic tests")
                        check_origin(resolved, "exec")
                elif filename.replace("\\", "/").split("/")[0] in {"core", "imported", "scripts"}:
                    raise RuntimeError("relative actual project code execution forbidden")
        if event == "open":
            filename, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                writable(filename)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.utime", "os.truncate"}:
            descriptor = args[-1] if event != "os.truncate" and isinstance(args[-1], int) else None
            writable(args[0], descriptor, mutates_bytes=event not in {"os.remove", "os.rmdir", "os.mkdir"})
        elif event in {"os.rename", "os.link", "os.symlink"}:
            if event in {"os.rename", "os.link"}:
                if any(fd not in (None, -1) for fd in args[2:4]):
                    raise RuntimeError("test directory-FD link/rename forbidden")
            elif len(args) > 2 and args[2] not in (None, -1):
                raise RuntimeError("test directory-FD symlink forbidden")
            writable(args[0], mutates_bytes=False); writable(args[1], mutates_bytes=False)
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            raise RuntimeError("subprocess/OS execution forbidden in synthetic tests")
    sys.addaudithook(audit)

    def save(name, value):
        path = output_root / name
        with path.open("xb") as handle:
            handle.write((json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))

    snapshot = json.loads(ORIGINAL_SNAPSHOT.read_text(encoding="utf-8"))
    original_start = protected_check(snapshot)
    save("original_integrity_start.json", original_start)
    if (not original_start["all_original_bytes_unchanged"] or original_start["protected_files_checked"] != 2535
            or original_start["original_csv_count"] != 1200 or original_start["original_receipt_count"] != 1200):
        raise RuntimeError("original protected starting bytes/count differ")
    save("implementation_start_sha256.json", start)
    test_paths = sorted(path for path in EXECUTOR.rglob("test_*.py") if path.is_file())
    if not test_paths:
        raise RuntimeError("new Stage C independent tests missing")
    suite = unittest.TestSuite()
    method_ids = []
    for index, path in enumerate(test_paths):
        check_origin(path, path.name)
        tree = ast.parse(path.read_bytes(), filename=str(path))
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        name = f"paper3_stage_c_test_{index}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        cases = list(all_tests(unittest.defaultTestLoader.loadTestsFromModule(module)))
        if len(cases) != len(methods):
            raise RuntimeError("actual Stage C discovery differs from static method inventory")
        suite.addTests(cases)
        method_ids.extend(case.id() for case in cases)
    if len(method_ids) != len(set(method_ids)):
        raise RuntimeError("duplicate Stage C test method IDs")
    save("method_inventory.json", method_ids)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    with (output_root / "tests.log").open("xb") as handle:
        handle.write(output.getvalue().encode("utf-8"))
    end = inventory()
    original_end = protected_check(snapshot)
    save("original_integrity_end.json", original_end)
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in FORBIDDEN_MODULES:
            raise RuntimeError("forbidden package loaded during synthetic tests")
        check_origin(getattr(module, "__file__", None), name)
    summary = {"scope": "STAGE_C_NEW_EXECUTOR_SYNTHETIC_TESTS_ONLY", "attempt": attempt,
               "tests_run": result.testsRun, "expected_methods": len(method_ids),
               "failures": [{"test": case.id(), "traceback": message} for case, message in result.failures],
               "errors": [{"test": case.id(), "traceback": message} for case, message in result.errors],
               "skipped": [{"test": case.id(), "reason": reason} for case, reason in result.skipped],
               "all_current_methods_pass": result.testsRun == len(method_ids) and result.wasSuccessful() and not result.skipped,
               "all_pass": (result.testsRun == len(method_ids) and result.wasSuccessful() and not result.skipped
                            and end == start and original_end["all_original_bytes_unchanged"]),
               "implementation_unchanged_during_test": end == start,
               "implementation_sha256": end,
               "implementation_start_sha256": start, "implementation_end_sha256": end,
               "environment_manifest_sha256": sha256(ENVIRONMENT),
               "independent_model_runtime_used": independent_runtime is not None,
               "independent_model_runtime_descriptor_sha256":sha256(sys.argv[2]) if independent_runtime is not None else None,
               "original_snapshot_source_sha256": sha256(ORIGINAL_SNAPSHOT),
               "original_end_check": original_end, "generator_executed": False,
               "model_executed": False, "statistics_executed": False,
               "original_42_tests_scope": "SEPARATE_ALREADY_COMPLETED_STAGE_A_GATE",
               "test_results_are_not_experimental_performance_results": True}
    save("results.json", summary)
    print(output.getvalue())
    print(json.dumps({key: summary[key] for key in ("tests_run", "all_current_methods_pass", "implementation_unchanged_during_test", "generator_executed", "model_executed")}))
    return 0 if summary["all_current_methods_pass"] and end == start and original_end["all_original_bytes_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
