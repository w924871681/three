"""Authorization/source/environment gates; never import any project module."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from importlib.machinery import BuiltinImporter, FrozenImporter, PathFinder
from pathlib import Path

from .contract import (CENTERS, METHODS, SCENARIOS, SEEDS, ContractError,
                       canonical_hash, file_sha256, jsonable, read_json)
from .safety import contained_path, regular_path

CANDIDATE_ID = "P7_7_ORIGINAL_BATCH20_CANDIDATE_V1"
PROTOCOL_ID = "P7_7_CANONICAL_INPUT_VERIFICATION_V1"
PACKAGE_DIR = Path(__file__).resolve().parent
THREAD_ENV_NAMES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_DYNAMIC", "MKL_DYNAMIC",
                    "NPY_DISABLE_CPU_FEATURES", "OPENBLAS_CORETYPE", "MKL_CBWR")


def implementation_inventory() -> dict:
    files = sorted(PACKAGE_DIR.rglob("*.py")) + [PACKAGE_DIR / "source_pins.json"]
    return {p.relative_to(PACKAGE_DIR).as_posix(): file_sha256(regular_path(p)) for p in files}


def git_snapshot(repo: Path) -> dict:
    def query(*arguments):
        completed = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *arguments],
                                   check=True, capture_output=True, text=True,
                                   env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return completed.stdout.rstrip("\r\n")
    top = Path(query("rev-parse", "--show-toplevel")).resolve()
    if top != repo:
        raise ContractError("target path is not the actual Git repository root")
    return {"root": str(top), "head": query("rev-parse", "HEAD"),
            "branch": query("symbolic-ref", "--short", "HEAD"),
            "tracked_status": query("status", "--porcelain", "--untracked-files=no")}


def definition() -> dict:
    return {"schema": "paper3-civ-scientific-definition-v1",
            "candidate_id": CANDIDATE_ID, "verification_id": PROTOCOL_ID,
            "centers": list(CENTERS), "model_seeds": list(SEEDS),
            "scenarios": list(SCENARIOS), "methods": [list(x) for x in METHODS],
            "data_seed": 7311, "n_history": 17000, "raw_features": 24,
            "model_features": 25, "kmax": 12, "stages": 24, "window": 96,
            "scenario_revision": "p3_mismatch_v2_r3", "onset_raw_index": 6520,
            "contexts": {"F": {"ordered_centers": list(CENTERS), "n_centers": 20,
                               "seed_offset": 561000, "start_center_id": 33000},
                         "S": {"n_centers": 1, "seed_offset_rule": "center_id*17",
                               "start_center_id_rule": "center_id"}},
            "replicates": {"F1": "ascending-full20", "F2": "ascending-full20",
                           "S1": "ascending-singletons", "S2": "descending-singletons"},
            "drift_prob_override": {"A": 0.0, "B": 0.0, "C": 0.0},
            "stage_span_rule": "b=1400+(t-1)*640;upd=[1000,1400) if t=1 else[b-400,b);assess=[b,b+240);srv=[b+240,b+640)",
            "warmup_span": [0,800], "reference_span": [800,1000],
            "legacy_hash": "core/common.py:22-29 shape+dtype.str+Cbytes SHA256",
            "provenance_hash": "finite deterministic JSON; distinct schema and context bindings",
            "metadata_schema": "$paper3_ndarray_v1 with dtype_str/shape/data; numpy scalars to native JSON",
            "schedule_workers": [1,3], "schedule_orders": ["canonical","reversed","7i_mod1200"],
            "R2": "PENDING_SEPARATE_AUTHORIZATION", "R3": "PENDING_SEPARATE_AUTHORIZATION",
            "selection_based_on_performance": False}


def snapshot_protected(repo: Path, pins: dict) -> dict:
    output = {key: file_sha256(contained_path(repo, key)) for key in pins["sources"]}
    root = contained_path(repo, "results/p7_7")
    for path in sorted(root.rglob("*")):
        regular_path(path)
        if path.is_file():
            output[path.relative_to(repo).as_posix()] = file_sha256(path)
    return output


def _environment(approved: dict, *, enable_numpy: bool) -> dict:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ContractError("require Python -I -S -B; no site startup or bytecode writes")
    executable = regular_path(Path(sys.executable))
    if str(executable).casefold() != str(regular_path(Path(approved["python_executable"]))).casefold():
        raise ContractError("unapproved interpreter")
    if file_sha256(executable) != approved["python_executable_sha256"]:
        raise ContractError("interpreter binary changed")
    if platform.python_version() != approved["python_version"] or sys.byteorder != approved["byteorder"]:
        raise ContractError("interpreter version/endian differs from approved environment")
    if platform.platform() != approved["platform"]:
        raise ContractError("OS/platform differs from approved environment")
    hardware = {"machine": platform.machine(), "processor": platform.processor(),
                "processor_identifier": os.environ.get("PROCESSOR_IDENTIFIER")}
    thread_environment = {name: os.environ.get(name) for name in THREAD_ENV_NAMES}
    if hardware != approved["hardware"] or thread_environment != approved["thread_environment"]:
        raise ContractError("CPU/architecture or numeric thread environment differs from approval")
    package_root = regular_path(Path(approved["numpy_parent"]))
    numpy_root = regular_path(package_root / "numpy")
    actual = {}
    for library in (numpy_root, package_root / "numpy.libs"):
        if not library.exists():
            continue
        regular_path(library)
        for path in sorted(library.rglob("*")):
            regular_path(path)
            if path.is_file() and path.suffix.lower() in {".py", ".pyi", ".pyd", ".dll"}:
                actual[path.relative_to(package_root).as_posix()] = file_sha256(path)
    if not actual or actual != approved["numpy_files_sha256"]:
        raise ContractError("NumPy source/native closure is missing, changed or has extra files")
    stdlib_root = regular_path(Path(approved["stdlib_root"]))
    standard = {}
    for directory, names, files in os.walk(stdlib_root, followlinks=False):
        regular_path(Path(directory))
        names[:] = sorted(name for name in names if name not in {"site-packages", "__pycache__"})
        for name in names:
            regular_path(Path(directory) / name)
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() in {".py", ".pyd", ".dll", ".zip"}:
                regular_path(path)
                standard[path.relative_to(stdlib_root).as_posix()] = file_sha256(path)
    if not standard or standard != approved["stdlib_files_sha256"]:
        raise ContractError("standard library closure differs from approved environment")
    binary_files = approved["runtime_binary_files_sha256"]
    if not binary_files:
        raise ContractError("Python runtime DLL/native dependency bindings required")
    for name, expected in binary_files.items():
        if file_sha256(regular_path(Path(name))) != expected:
            raise ContractError("runtime binary dependency changed")
    install_import_guard(approved)
    if enable_numpy:
        if str(package_root) not in sys.path:
            sys.path.append(str(package_root))  # Explicit pinned root; never process .pth.
        import numpy as np
        if np.__version__ != approved["numpy_version"] or Path(np.__file__).resolve().parent != numpy_root:
            raise ContractError("unapproved resolved NumPy")
        if jsonable(np.__config__.CONFIG) != approved["numpy_build_configuration"]:
            raise ContractError("resolved NumPy/BLAS build metadata differs from approval")
    return {"approved_environment": approved, "numpy_enabled": enable_numpy,
            "actual_numpy_files_sha256": actual, "actual_stdlib_files_sha256": standard,
            "hardware": hardware, "thread_environment": thread_environment,
            "historical_environment_reproduced": False,
            "no_site": True, "no_bytecode": True}


def _bound_module_files(approved: dict) -> dict[str, str]:
    # Concrete reviewed byte bindings, rather than broad directories. In
    # particular Lib/site-packages cannot inherit the Lib allowlist.
    bound = {str((PACKAGE_DIR / relative).resolve()).casefold(): digest
             for relative, digest in implementation_inventory().items() if relative.endswith(".py")}
    for root_key, files_key in (("stdlib_root", "stdlib_files_sha256"),
                                ("numpy_parent", "numpy_files_sha256")):
        root = regular_path(Path(approved[root_key]))
        for relative, digest in approved[files_key].items():
            path = contained_path(root, relative)
            bound[str(path).casefold()] = digest
    for filename, digest in approved["runtime_binary_files_sha256"].items():
        bound[str(regular_path(Path(filename))).casefold()] = digest
    return bound


class BoundImportGuard:
    """Reject an unbound dependency before its loader can execute it."""
    def __init__(self, approved: dict):
        self.bound = _bound_module_files(approved)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "pandas", "core", "imported", "scripts", "sklearn"}:
            raise ContractError(f"forbidden module before import: {fullname}")
        spec = BuiltinImporter.find_spec(fullname, path, target)
        if spec is None:
            spec = FrozenImporter.find_spec(fullname, path, target)
        if spec is not None:
            return spec
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is None:
            return None  # Normal missing optional dependency; nothing executes.
        if not spec.origin or spec.origin in {"built-in", "frozen"}:
            raise ContractError(f"unbound namespace/dependency before import: {fullname}")
        module_path = regular_path(Path(spec.origin))
        expected = self.bound.get(str(module_path).casefold())
        if expected is None or file_sha256(module_path) != expected:
            raise ContractError(f"unapproved module before import: {fullname}: {module_path}")
        return spec


def install_import_guard(approved: dict) -> None:
    guard = BoundImportGuard(approved)
    existing_guard = None
    for item in sys.meta_path:
        if isinstance(item, BoundImportGuard):
            if existing_guard is not None or item.bound != guard.bound:
                raise ContractError("import binding changed within one verifier process")
            existing_guard = item
            continue
        if item not in (BuiltinImporter, FrozenImporter, PathFinder):
            raise ContractError("unapproved preexisting import finder")
    if existing_guard is not None:
        return
    sys.meta_path.insert(0, guard)


def check_loaded_modules(approved: dict) -> None:
    bound = _bound_module_files(approved)
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] in {"torch", "pandas", "core", "imported", "scripts", "sklearn"}:
            raise ContractError(f"forbidden imported module: {name}")
        filename = getattr(module, "__file__", None)
        if not filename or filename.startswith("<"):
            continue
        path = Path(filename).resolve()
        expected = bound.get(str(path).casefold())
        if expected is None or file_sha256(regular_path(path)) != expected:
            raise ContractError(f"module outside pinned import closure: {name}: {path}")


def preflight(repo: Path, authorization_file: Path, run_id: str, *, enable_numpy: bool = False) -> dict:
    repo = regular_path(repo)
    if repo != PACKAGE_DIR.parents[2]:
        raise ContractError("verifier must run in its reviewed target repository")
    authorization_file = regular_path(authorization_file)
    if PACKAGE_DIR.parent not in authorization_file.parents:
        raise ContractError("authorization manifest must be inside verification/paper3_canonical_inputs")
    auth = read_json(authorization_file)
    required = {"human_authorized": True, "scope": "INPUT_ONLY_EXECUTION",
                "candidate_id": CANDIDATE_ID, "verification_id": PROTOCOL_ID, "run_id": run_id,
                "models_authorized": False, "warmup_authorized": False,
                "statistics_authorized": False, "historical_overwrite_authorized": False,
                "current_environment_reference_authorized": True,
                "historical_environment_not_reproduced_acknowledged": True}
    if any(auth.get(key) != value for key, value in required.items()):
        raise ContractError("missing separate explicit human input-only execution authorization")
    if not auth.get("human_authorization_reference"):
        raise ContractError("human authorization evidence/reference required")
    # -B alone still reads existing pyc. A never-created alternate cache root
    # forces source loading without touching any original __pycache__ directory.
    expected_cache = repo / "verification" / "paper3_canonical_inputs" / PROTOCOL_ID / run_id / "_never_created_pycache"
    if not sys.pycache_prefix or Path(sys.pycache_prefix).resolve(strict=False) != expected_cache.resolve(strict=False):
        raise ContractError("require -X pycache_prefix=<new run root>/_never_created_pycache")
    regular_path(expected_cache, must_exist=False)
    if expected_cache.exists():
        raise ContractError("alternate bytecode cache root must not exist")
    implementation = implementation_inventory()
    if implementation != auth["approved_implementation_sha256"]:
        raise ContractError("verifier implementation differs from approved immutable bundle")
    pins = read_json(PACKAGE_DIR / "source_pins.json")
    sources = {key: file_sha256(contained_path(repo, key)) for key in pins["sources"]}
    if sources != pins["sources"]:
        raise ContractError("frozen source/config/evidence dependency changed")
    git = git_snapshot(repo)
    if git["head"] != pins["git_head"] or git != auth["approved_git_snapshot"]:
        raise ContractError("repository identity/tracked status changed")
    if auth.get("history_session") != pins["history_session"]:
        raise ContractError("historical provenance source is unapproved")
    environment_file = regular_path(Path(auth["environment_manifest_path"]))
    if PACKAGE_DIR.parent not in environment_file.parents:
        raise ContractError("environment manifest must stay inside verification subtree")
    if file_sha256(environment_file) != auth["environment_manifest_sha256"]:
        raise ContractError("environment manifest hash mismatch")
    environment = _environment(read_json(environment_file), enable_numpy=enable_numpy)
    dependencies = {"sources": sources, "implementation": implementation,
                    "environment": environment["approved_environment"],
                    "historical_source_binding": pins["history_session"]}
    check_loaded_modules(environment["approved_environment"])
    return {"authorization": auth, "authorization_sha256": file_sha256(authorization_file),
            "authorization_file": str(authorization_file), "pins": pins,
            "git": git, "source_environment": dependencies,
            "dependency_digest": canonical_hash(dependencies), "definition": definition(),
            "definition_digest": canonical_hash(definition())}
