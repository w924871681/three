"""Current-environment provenance and guarded independent replication IO.

Importing this module uses only standard-library modules. It never imports a
project, generator, model, checkpoint deserializer or statistical routine.
Historical runtime equality is never inferred from present file bindings.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import platform
import re
import stat
import sys
import threading
import uuid
from datetime import datetime, timezone
from importlib.machinery import BuiltinImporter, FrozenImporter, PathFinder
from pathlib import Path
from types import MappingProxyType, ModuleType

REPOSITORY = Path(__file__).resolve().parents[3]
CANONICAL_ROOT = REPOSITORY / "verification" / "paper3_canonical_inputs"
EXECUTION_ROOT = CANONICAL_ROOT / "execution_20261009"
RESULTS_NAME = "results/p7_7_integrity_replication_batch20_env_v2"
CANDIDATE_ID = "P7_7_ORIGINAL_BATCH20_CANDIDATE_V1"
INPUT_PROTOCOL = "P7_7_CANONICAL_INPUT_VERIFICATION_V1"
REPLICATION_ID = "P7_7_INTEGRITY_REPLICATION_BATCH20_V1"
RUNTIME_ID = "P7_7_INTEGRITY_REPLICATION_BATCH20_ENV_V2"
MODEL_ENVIRONMENT_ID = "P7_7_REPLICATION_MODEL_ENV_V1"
EXPECTED_MODEL_VERSIONS = {
    "numpy": "2.4.6", "torch": "2.5.1+cu121", "scipy": "1.17.1",
    "scikit-learn": "1.9.0", "river": "0.23.0", "pandas": "2.3.3",
    "psutil": "7.2.2",
}
FILE_SUFFIXES = {".py", ".pyi", ".pyd", ".dll", ".so", ".dylib", ".zip"}
DIST_FILES = {"METADATA", "RECORD", "WHEEL", "INSTALLER", "top_level.txt", "direct_url.json"}
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_DYNAMIC", "MKL_DYNAMIC",
              "NPY_DISABLE_CPU_FEATURES", "OPENBLAS_CORETYPE", "MKL_CBWR")
# Independent present-runtime bindings, separate from the unchanged Stage B
# input environment. Cache/temporary output paths intentionally vary by worker
# and are checked by require_isolation, not treated as scientific input changes.
MODEL_RUNTIME_ENV = THREAD_ENV + (
    "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "CUBLAS_WORKSPACE_CONFIG",
    "MKL_THREADING_LAYER", "MKL_INTERFACE_LAYER", "MKL_SERVICE_FORCE_INTEL",
    "OMP_WAIT_POLICY", "OMP_PROC_BIND", "OMP_PLACES", "OMP_SCHEDULE",
    "KMP_AFFINITY", "KMP_BLOCKTIME", "KMP_SETTINGS", "KMP_DUPLICATE_LIB_OK",
    "NUMEXPR_MAX_THREADS", "NVIDIA_TF32_OVERRIDE", "TORCH_ALLOW_TF32_CUBLAS_OVERRIDE",
    "PYTORCH_CUDA_ALLOC_CONF", "PYTORCH_ALLOC_CONF", "PYTORCH_NO_CUDA_MEMORY_CACHING",
    "TORCH_CUDNN_V8_API_DISABLED", "TORCH_CUDNN_V8_API_LRU_CACHE_LIMIT",
)
DENIED_GENERATION = {
    "generate_base_centers", "simulate_centers", "_generate_latent_workload",
    "_generate_clean_metrics", "_apply_monitoring_missingness", "_make_type_schedule",
    "_sample_budget_tier", "make_scenario", "make_scenario_v2", "timeline_for_v2",
    "scenario_hash_v2", "timeline_for", "scenario_hash", "source_regime",
    "apply_c3_regime_b", "c4_target", "_physical_shift", "fit_scaler",
    "train_source_assets", "run_final_heldout", "_run_final_task", "run_qualification",
}
_WRITE_ROOT = None
_GENERATOR_REPO = None
_WRITE_GUARD_INSTALLED = False
_GENERATOR_PROFILE = None
_IMPORT_BINDINGS_CACHE = {}
_IMPORT_BINDINGS_CACHE_LOCK = threading.RLock()
_PLATFORM_BOOTSTRAP = None
_PLATFORM_BOOTSTRAP_LOCK = threading.RLock()


class ProvenanceError(RuntimeError):
    pass


def regular_path(path, *, must_exist=True):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ProvenanceError(f"symlink/junction/reparse path forbidden: {ancestor}")
    return path.resolve(strict=must_exist)


def checked_path(root, relative, *, must_exist=True):
    root = regular_path(root)
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ProvenanceError("relative POSIX path required")
    components = relative.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", component) or component in {".",".."}
           or component.endswith(".") or component.split(".")[0].upper() in reserved for component in components):
        raise ProvenanceError("unsafe relative publication/source path")
    result = regular_path(root.joinpath(*components), must_exist=must_exist)
    if result == root or root not in result.parents:
        raise ProvenanceError("path escaped designated root")
    return result


def file_sha256(path):
    digest = hashlib.sha256()
    with regular_path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite(value):
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value): raise ProvenanceError("non-finite JSON")
        return value
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    if isinstance(value, dict) and all(type(key) is str for key in value):
        return {key:_finite(item) for key,item in value.items()}
    raise ProvenanceError(f"unsupported JSON value: {type(value).__name__}")


def read_json(path):
    with regular_path(path).open("r", encoding="utf-8") as stream:
        return _finite(json.load(stream, object_pairs_hook=_unique))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(_finite(value), sort_keys=True, separators=(",",":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _assert(condition, message):
    if not condition: raise ProvenanceError(message)


def bootstrap_platform_metadata():
    """Read identical stdlib OS metadata once, before the worker IO guard.

    Windows platform.platform() may shell out to cmd VER. No subprocess is
    admitted after write protection: a missing cache then fails closed. These
    non-scientific identity values are immutable and belong to this process;
    environment variables, executable/dependency bytes and all scientific
    runtime/input checks remain freshly checked at their original boundaries.
    """
    global _PLATFORM_BOOTSTRAP
    with _PLATFORM_BOOTSTRAP_LOCK:
        if _PLATFORM_BOOTSTRAP is None:
            _assert(not _WRITE_GUARD_INSTALLED,"platform metadata must be bootstrapped before worker guard")
            values = {"platform":platform.platform(),"machine":platform.machine(),"processor":platform.processor()}
            _assert(all(type(value) is str for value in values.values()),"invalid stdlib platform metadata")
            _PLATFORM_BOOTSTRAP = (os.getpid(),MappingProxyType(values),canonical_hash(values))
        _assert(type(_PLATFORM_BOOTSTRAP) is tuple and len(_PLATFORM_BOOTSTRAP)==3,
                "invalid platform metadata bootstrap record")
        pid, values, digest = _PLATFORM_BOOTSTRAP
        _assert(pid==os.getpid() and type(values) is MappingProxyType and
                set(values)=={"platform","machine","processor"} and canonical_hash(dict(values))==digest,
                "platform bootstrap process/immutable-value binding differs")
        return values


def _target_repo(repo):
    repo = regular_path(repo)
    _assert(repo == REPOSITORY, "wrong target repository")
    return repo


def _results_root(repo, results_root):
    root = regular_path(results_root)
    _assert(root == checked_path(repo, RESULTS_NAME), "wrong authorized independent results root")
    return root


def verify_stage_b(repo, input_run):
    """Verify final gate/manifest graph and saved immutable F1 metadata only.

    Actual role arrays are independently verified by FixedInputStore per task;
    this helper never loads an array or regenerates any input.
    """
    repo, run = _target_repo(repo), regular_path(input_run)
    _assert(run.parent == checked_path(CANONICAL_ROOT, INPUT_PROTOCOL), "wrong canonical input run root")
    gate_path = checked_path(EXECUTION_ROOT, "stage_b_scientific_gate.json")
    gate = read_json(gate_path)
    _assert(gate.get("stage_c_allowed") is True and gate.get("execution_pass") is True and
            gate.get("expected_historical_cohort_correspondence_pass") is True, "Stage B scientific gate did not pass")
    _assert(regular_path(gate["input_verification_root"]) == run, "Stage B gate points to another run")
    load = lambda name:read_json(checked_path(run,name))
    receipt, inventory = load("execution_receipt.json"), load("outputs_inventory.json")
    _assert(file_sha256(checked_path(run,"execution_receipt.json")) == gate["execution_receipt_sha256"], "Stage B receipt changed")
    _assert(receipt.get("exit_code") == 0 and receipt.get("status") == "INPUT_ONLY_CHECKS_COMPLETED" and receipt.get("originals_unchanged") is True, "Stage B final receipt incomplete")
    _assert(receipt.get("model_execution_performed") is False and receipt.get("statistics_performed") is False, "Stage B scope changed")
    bindings = inventory["files"]
    for relative, expected in (("run_manifest.json",receipt["run_manifest_sha256"]),
                               ("outputs_inventory.json",receipt["outputs_inventory_sha256"])):
        _assert(file_sha256(checked_path(run,relative)) == expected, "Stage B final publication graph changed")
    names = ("run_manifest.json", "definition_manifest.json", "source_environment_manifest.json",
             "validation_certificate.json", "bank_feasibility_inventory.json", "contexts/F1.json")
    objects = {}
    for name in names:
        _assert(bindings.get(name) == file_sha256(checked_path(run,name)), f"Stage B metadata byte mismatch: {name}")
        objects[name] = load(name)
    manifest, definition = objects["run_manifest.json"], objects["definition_manifest.json"]
    sources, cert = objects["source_environment_manifest.json"], objects["validation_certificate.json"]
    base = objects["contexts/F1.json"]
    _assert(manifest.get("candidate_id") == CANDIDATE_ID and manifest.get("verification_id") == INPUT_PROTOCOL and manifest.get("complete") is True, "canonical candidate publication changed")
    _assert(cert.get("checks_completed") is True and cert.get("valid_only_with_final_success_receipt") is True and cert.get("initial_state_verified") is False, "Stage B certificate scope changed")
    definition_digest = canonical_hash(definition)
    dependencies = {key:sources[key] for key in ("sources","implementation","environment","historical_source_binding")}
    dependency_digest = canonical_hash(dependencies)
    _assert(all(value.get("definition_digest") == definition_digest and value.get("dependency_digest") == dependency_digest for value in (manifest,cert,base,sources)), "Stage B scientific binding mismatch")
    _assert(base.get("replicate") == "F1" and base.get("context") == "F" and base.get("input_bundle_digest") == cert["input_bundle_digests"]["F1"], "selected F1 bundle mismatch")
    _assert(tuple(len(base[key]) for key in ("base","scenarios","roles","references")) == (20,80,5760,160), "selected F1 coverage incomplete")
    for relative, expected in base["created_file_sha256"].items():
        _assert(bindings.get(relative) == expected, f"F1 creation binding mismatch: {relative}")
    for relative, expected in sources["sources"].items():
        _assert(file_sha256(checked_path(repo,relative)) == expected, f"Stage B frozen source changed: {relative}")
    verifier_root = checked_path(CANONICAL_ROOT,"verifier_v1")
    verifier_dependencies = {}
    for relative,expected in sources["implementation"].items():
        path = checked_path(verifier_root,relative)
        _assert(file_sha256(path)==expected,f"Stage B verifier implementation changed: {relative}")
        verifier_dependencies[str(path)] = expected
    environment_path = checked_path(EXECUTION_ROOT,"environment.reviewed.json")
    _assert(read_json(environment_path)==sources["environment"],"reviewed input environment differs from Stage B")
    verifier_dependencies[str(environment_path)] = file_sha256(environment_path)
    gate_helper = checked_path(EXECUTION_ROOT,"check_stage_b_gate.py")
    verifier_dependencies[str(gate_helper)] = file_sha256(gate_helper)
    return {"run_manifest":manifest,"outputs_inventory":inventory,"receipt":receipt,"certificate":cert,
            "file_bindings":bindings,"F1":base,"stage_b_gate":gate,"source_environment":sources,
            "bank":objects["bank_feasibility_inventory.json"],"definition":definition,
            "current_verifier_dependencies_sha256":verifier_dependencies,
            "binding_sha256":{"gate":file_sha256(gate_path),"receipt":file_sha256(checked_path(run,"execution_receipt.json")),
                "outputs_inventory":file_sha256(checked_path(run,"outputs_inventory.json")),
                "run_manifest":file_sha256(checked_path(run,"run_manifest.json")),"F1":bindings["contexts/F1.json"],
                "source_environment":bindings["source_environment_manifest.json"],
                "reviewed_environment":file_sha256(environment_path),"gate_helper":file_sha256(gate_helper),
                "verifier_implementation_digest":canonical_hash(sources["implementation"])}}


def _scan_files(root, *, exclude=(), include_dist_info=False):
    root = regular_path(root)
    output = []
    for directory, names, files in os.walk(root, followlinks=False):
        regular_path(directory)
        names[:] = sorted(name for name in names if name not in set(exclude)|{"__pycache__"})
        for name in names: regular_path(Path(directory)/name)
        for name in sorted(files):
            path = Path(directory)/name
            is_dist = include_dist_info and any(part.endswith(".dist-info") for part in path.relative_to(root).parts) and name in DIST_FILES
            if path.suffix.lower() in FILE_SUFFIXES or is_dist:
                output.append(regular_path(path))
    return output


def _normalized_versions(values):
    """Canonical installed distribution identifiers per PEP 503; no imports."""
    _assert(isinstance(values, dict) and values, "exact dependency versions required")
    result = {}
    for raw_name, version in values.items():
        _assert(isinstance(raw_name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", raw_name)
                and isinstance(version, str) and version, "invalid dependency name/version")
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        _assert(name not in result, "duplicate canonical installed distribution name")
        result[name] = version
    return result


def _runtime_layout(model_runtime):
    """Read the explicitly reviewed venv/base-library layout, without site startup.

    On Python 3.11, -S may report the base prefix even when sys.executable is
    the venv launcher. This contract therefore binds both paths explicitly;
    only the independent venv site-packages is ever added to the import path.
    """
    _assert(isinstance(model_runtime, dict), "reviewed independent model-runtime descriptor required")
    _assert(model_runtime.get("schema") == "paper3-reviewed-independent-model-runtime-v1" and
            model_runtime.get("environment_id") == MODEL_ENVIRONMENT_ID,
            "unapproved independent model-runtime identity")
    paths = {name:regular_path(model_runtime[name]) for name in (
        "prefix", "base_prefix", "python_executable", "site_packages_root", "stdlib_root")}
    _assert(paths["python_executable"] == paths["prefix"] / "Scripts" / "python.exe" and
            paths["site_packages_root"] == paths["prefix"] / "Lib" / "site-packages" and
            paths["stdlib_root"] == paths["base_prefix"] / "Lib",
            "independent model-runtime layout differs from reviewed Windows venv")
    cfg = read_json(model_runtime["layout_evidence_path"]) if model_runtime.get("layout_evidence_path") else None
    if cfg is not None:
        _assert(cfg.get("environment_id") == MODEL_ENVIRONMENT_ID,
                "runtime layout evidence belongs to another environment")
    pyvenv = paths["prefix"] / "pyvenv.cfg"
    _assert(pyvenv.is_file(), "independent model venv configuration missing")
    values = {}
    for line in pyvenv.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            values[name.strip().casefold()] = value.strip()
    _assert(values.get("include-system-site-packages", "").casefold() == "false",
            "system site-packages sharing is prohibited")
    _assert(regular_path(values["home"]) == paths["base_prefix"],
            "venv base interpreter differs from reviewed descriptor")
    expected = _normalized_versions(model_runtime.get("expected_versions"))
    _assert(all(expected.get(name) == value
            for name,value in EXPECTED_MODEL_VERSIONS.items()),
            "model scientific versions differ from authorized exact pins")
    evidence = model_runtime.get("installation_evidence_files_sha256")
    _assert(isinstance(evidence, dict) and evidence, "independent dependency installation evidence required")
    for filename, digest in evidence.items():
        _assert(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) and
                file_sha256(filename) == digest, "dependency installation evidence byte mismatch")
    if model_runtime.get("layout_evidence_path") is not None:
        layout_path = regular_path(model_runtime["layout_evidence_path"])
        _assert(any(regular_path(filename) == layout_path and digest == file_sha256(layout_path)
                    for filename,digest in evidence.items()),
                "runtime layout evidence requires a complete byte binding")
    if model_runtime.get("descriptor_source_file") is not None:
        source = regular_path(model_runtime["descriptor_source_file"])
        _assert(file_sha256(source) == model_runtime.get("descriptor_source_sha256"),
                "reviewed model-runtime descriptor source changed")
        original = {key:value for key,value in model_runtime.items()
                    if key not in {"descriptor_source_file", "descriptor_source_sha256"}}
        _assert(read_json(source) == original,
                "model-runtime descriptor differs from reviewed source object")
    return paths, pyvenv, values


def capture_model_environment(input_environment, model_runtime, progress=None):
    """Read full current package/native/source metadata; never import a package.

    Pinned native dependencies are trusted. This is a current environment freeze,
    not a claim that every external GPU driver/system binary was historically bound.
    """
    env = input_environment
    paths, pyvenv, venv_values = _runtime_layout(model_runtime)
    executable = regular_path(sys.executable)
    _assert(executable == paths["python_executable"], "model interpreter differs from reviewed independent venv")
    _assert(regular_path(sys.base_prefix) == paths["base_prefix"], "current model base prefix differs from reviewed layout")
    platform_values = bootstrap_platform_metadata()
    _assert(platform.python_version() == env["python_version"] and sys.byteorder == env["byteorder"] and platform_values["platform"] == env["platform"], "model Python/platform differs from Stage B")
    hardware = {"machine":platform_values["machine"],"processor":platform_values["processor"],"processor_identifier":os.environ.get("PROCESSOR_IDENTIFIER")}
    thread_env = {name:os.environ.get(name) for name in THREAD_ENV}
    _assert(hardware == env["hardware"] and thread_env == env["thread_environment"], "model hardware/thread environment differs from Stage B")
    _assert(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            "model environment capture requires -I -S -B")
    _assert(sys.pycache_prefix is not None and not regular_path(sys.pycache_prefix,must_exist=False).exists(),
            "model capture requires an exclusive nonexistent bytecode prefix")
    site = paths["site_packages_root"]
    startup = []
    for pattern in ("*.pth", "*.egg-link"):
        for path in sorted(site.glob(pattern)):
            _assert(path.suffix.casefold() != ".egg-link" and "editable" not in path.name.casefold(),
                    "editable package startup is prohibited")
            startup.append({"path":str(regular_path(path)), "sha256":file_sha256(path), "executed":False})
    for path in site.glob("*.dist-info/direct_url.json"):
        direct = read_json(path)
        _assert(direct.get("dir_info",{}).get("editable") is not True,
                "editable scientific dependency is prohibited")
    files = _scan_files(site, include_dist_info=True)
    prefix = paths["prefix"]
    for relative in ("DLLs", "Library/bin"):
        directory = paths["base_prefix"]/relative
        if directory.exists(): files += _scan_files(directory)
    for directory in (paths["base_prefix"], prefix / "Scripts"):
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in {".exe",".dll",".pyd",".zip"}: files.append(regular_path(path))
    stdlib = paths["stdlib_root"]
    _assert(stdlib == regular_path(env["stdlib_root"]), "base standard library differs from approved Stage B interpreter")
    files += _scan_files(stdlib, exclude={"site-packages"})
    files += [pyvenv] + [Path(item["path"]) for item in startup]
    files = sorted(set(files),key=lambda path:str(path).casefold())
    bound = {}
    for index,path in enumerate(files,1):
        bound[str(path)] = file_sha256(path)
        if progress and (index % 500 == 0 or index == len(files)):
            progress({"kind":"environment_hash_progress","completed":index,"total":len(files)})
    for relative, expected in env["numpy_files_sha256"].items():
        _assert(bound.get(str(checked_path(site,relative))) == expected, "model NumPy differs from Stage B")
    distributions = {}
    for metadata in sorted(site.glob("*.dist-info/METADATA")):
        regular_path(metadata)
        info = {}
        for line in metadata.read_text(encoding="utf-8").splitlines():
            if line.startswith("Name: "): info["name"] = line[6:]
            elif line.startswith("Version: "): info["version"] = line[9:]
            if len(info) == 2: break
        _assert(len(info) == 2, "incomplete installed distribution metadata")
        distributions[metadata.parent.name] = {**info,"metadata_path":str(metadata),"metadata_sha256":file_sha256(metadata)}
    normalized = {}
    for value in distributions.values():
        name = re.sub(r"[-_.]+", "-", value["name"]).lower()
        _assert(name not in normalized, "duplicate installed distribution name")
        normalized[name] = value["version"]
    names = set(normalized)
    _assert({"numpy","torch","pandas","psutil","river","scipy","scikit-learn"} <= names, "required scientific packages missing from frozen distribution metadata")
    for name, expected in _normalized_versions(model_runtime["expected_versions"]).items():
        _assert(normalized.get(name) == expected, f"independent model dependency version mismatch: {name}")
    runtime_variables = _model_runtime_environment()
    return {"schema":"paper3-current-model-environment-v1","site_packages_root":str(site),
            "model_environment_id":MODEL_ENVIRONMENT_ID,"model_runtime_descriptor":model_runtime,
            "model_runtime_descriptor_digest":canonical_hash(model_runtime),
            "venv_prefix":str(prefix),"base_prefix":str(paths["base_prefix"]),
            "stdlib_root":str(stdlib),"venv_configuration":venv_values,
            "startup_files_present_but_not_executed":startup,"site_startup_processed":False,
            "python_executable":str(executable),"python_executable_sha256":file_sha256(executable),
            "python_version":platform.python_version(),"platform":platform_values["platform"],"byteorder":sys.byteorder,
            "hardware":hardware,"thread_environment":thread_env,"bound_files_sha256":bound,
            "model_runtime_environment":runtime_variables,
            "model_runtime_environment_digest":canonical_hash(runtime_variables),
            "distributions":distributions,"exact_versions":normalized,"input_environment_digest":canonical_hash(env),
            "input_environment":env,"historical_environment_reproduced":False,
            "gpu_driver_binary_history_verified":False,"packages_imported_during_capture":False}


def _hash_relative(repo, paths):
    return {relative:file_sha256(checked_path(repo,relative)) for relative in sorted(set(paths))}


def _adapter_source_pins(executor):
    """Extract the new adapter's literal expected-byte contract without importing it."""
    path = checked_path(executor,"science_adapter.py")
    before = file_sha256(path)
    tree = ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
    assignments = [node for node in tree.body if isinstance(node,ast.Assign) and
                   any(isinstance(target,ast.Name) and target.id=="SOURCE_PINS" for target in node.targets)]
    _assert(len(assignments)==1,"one literal adapter source-pin assignment required")
    pins = ast.literal_eval(assignments[0].value)
    _assert(isinstance(pins,dict) and pins and all(type(name) is str and type(digest) is str and
            re.fullmatch(r"[0-9a-f]{64}",digest) for name,digest in pins.items()),"invalid adapter source-pin contract")
    _assert(file_sha256(path)==before,"adapter changed during literal source-pin extraction")
    return pins


def check_original_snapshot(repo, snapshot):
    errors = [relative for relative,expected in snapshot.items() if file_sha256(checked_path(repo,relative)) != expected]
    _assert(not errors, "original protected bytes changed: "+", ".join(errors[:10]))
    return {"count":len(snapshot),"all_original_bytes_unchanged":True,"snapshot_digest":canonical_hash(snapshot)}


def freeze_provenance(repo, input_run, results_root, executor_root, *, environment=None, model_runtime=None, progress=None):
    """Freeze and exclusively publish one independent replication manifest.

    All original scientific bytes and eleven source checkpoints are read-only.
    No model is loaded and no generation function is called during this function.
    """
    repo, run = _target_repo(repo), regular_path(input_run)
    results, executor = _results_root(repo,results_root), regular_path(executor_root)
    _assert(executor == Path(__file__).resolve().parent, "wrong executor implementation root")
    stage_b = verify_stage_b(repo,run)
    baseline_path = checked_path(EXECUTION_ROOT,"original_protected_start_sha256.json")
    original = read_json(baseline_path)
    original_check = check_original_snapshot(repo,original)
    config = read_json(checked_path(repo,"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"))
    frozen_bindings = config["source_bindings_sha256"]
    for relative,expected in frozen_bindings.items():
        _assert(file_sha256(checked_path(repo,relative)) == expected, f"frozen protocol source mismatch: {relative}")
    source26 = stage_b["source_environment"]["sources"]
    adapter_pins = _adapter_source_pins(executor)
    for relative,expected in adapter_pins.items():
        _assert(file_sha256(checked_path(repo,relative))==expected,f"adapter scientific pin changed: {relative}")
    python_paths = []
    for folder in ("core","imported","scripts"):
        for path in _scan_files(checked_path(repo,folder)):
            if path.suffix.lower() == ".py": python_paths.append(path.relative_to(repo).as_posix())
    checkpoint_paths = []
    for identity in stage_b["bank"]["identities"]:
        relative = identity["checkpoint"]
        _assert(file_sha256(checked_path(repo,relative)) == identity["checkpoint_sha256"], f"source checkpoint mismatch: {identity['identity_id']}")
        checkpoint_paths.append(relative)
    _assert(len(checkpoint_paths) == len(set(checkpoint_paths)) == 11, "source checkpoint coverage is not eleven unique identities")
    critical = _hash_relative(repo,set(source26)|set(frozen_bindings)|set(adapter_pins)|set(python_paths)|set(checkpoint_paths))
    for relative,expected in source26.items():
        _assert(critical[relative] == expected, f"Stage B source pin changed: {relative}")
    executor_files = {path.relative_to(executor).as_posix():file_sha256(path) for path in _scan_files(executor) if path.suffix.lower() == ".py"}
    input_files = {relative:expected for relative,expected in stage_b["F1"]["created_file_sha256"].items()}
    for relative,expected in input_files.items():
        _assert(file_sha256(checked_path(run,relative)) == expected, f"F1 input bytes changed: {relative}")
    environment = environment or capture_model_environment(stage_b["source_environment"]["environment"],model_runtime,progress=progress)
    _assert(environment.get("input_environment_digest") == canonical_hash(stage_b["source_environment"]["environment"]), "model environment not bound to Stage B environment")
    _assert(environment.get("input_environment")==stage_b["source_environment"]["environment"],"model input-environment object differs from Stage B")
    _verify_current_environment(environment,check_files=True)
    manifest = {"schema":"paper3-integrity-replication-provenance-v1","replication_id":REPLICATION_ID,
        "runtime_id":RUNTIME_ID,"model_environment_id":MODEL_ENVIRONMENT_ID,
        "candidate_id":CANDIDATE_ID,"input_protocol":INPUT_PROTOCOL,
        "paths":{"repo":str(repo),"input_run":str(run),"results_root":str(results),"executor_root":str(executor)},
        "scientific_definition":stage_b["definition"],"input_definition_digest":stage_b["F1"]["definition_digest"],
        "input_dependency_digest":stage_b["F1"]["dependency_digest"],"input_bundle_digest":stage_b["F1"]["input_bundle_digest"],
        "stage_b_bindings":stage_b["binding_sha256"],"stage_b_gate":stage_b["stage_b_gate"],
        "stage_b_dependencies_sha256":stage_b["current_verifier_dependencies_sha256"],
        "source_bindings_sha256":frozen_bindings,"stage_b_source_pins":source26,"adapter_source_pins":adapter_pins,
        "critical_files_sha256":critical,"original_python_dependency_sha256":_hash_relative(repo,python_paths),
        "source_checkpoint_files":checkpoint_paths,"identity_metadata":stage_b["bank"],
        "input_files_sha256":input_files,"executor_sha256":executor_files,"environment":environment,
        "environment_binding":canonical_hash(environment),
        "original_protected_snapshot":original,"original_snapshot_source_sha256":file_sha256(baseline_path),
        "original_start_check":original_check,"frozen_final_configuration":config,
        "authorization_record_sha256":file_sha256(checked_path(results,"RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md")),
        "historical_environment_reproduced":False,"historical_full_metadata_certified":False,
        "initial_state_verified":False,"initial_state_certificate":"PENDING_STAGE_C",
        "new_output_only":True,"original_records_mixed_into_new_results":False,
        "guard_scope":"Python audited IO and pinned trusted native dependencies; not a general OS sandbox assertion.",
        "created_utc":datetime.now(timezone.utc).isoformat()}
    manifest["manifest_digest"] = canonical_hash(manifest)
    publish_json(results,"provenance_manifest.json",manifest)
    return manifest


def _verify_current_environment(environment, *, check_files):
    executable = regular_path(sys.executable)
    _assert(executable==regular_path(environment["python_executable"]) and
            file_sha256(executable)==environment["python_executable_sha256"] and
            platform.python_version()==environment["python_version"],"model interpreter changed")
    _assert({name:os.environ.get(name) for name in THREAD_ENV}==environment["thread_environment"],"numeric thread environment changed")
    _verify_model_runtime_environment(environment)
    metadata = bootstrap_platform_metadata()
    _assert(sys.byteorder==environment["byteorder"] and metadata["platform"]==environment["platform"],"platform/endian changed")
    hardware = {"machine":metadata["machine"],"processor":metadata["processor"],
                "processor_identifier":os.environ.get("PROCESSOR_IDENTIFIER")}
    _assert(hardware==environment["hardware"],"current hardware identity changed")
    _assert(environment.get("packages_imported_during_capture") is False and environment.get("historical_environment_reproduced") is False,
            "current environment metadata scope changed")
    _assert(environment.get("model_environment_id") == MODEL_ENVIRONMENT_ID and
            environment.get("site_startup_processed") is False,
            "independent venv runtime scope changed")
    descriptor = environment["model_runtime_descriptor"]
    _assert(canonical_hash(descriptor) == environment.get("model_runtime_descriptor_digest"),
            "independent runtime descriptor changed")
    paths, _, _ = _runtime_layout(descriptor)
    _assert(paths["site_packages_root"] == regular_path(environment["site_packages_root"]) and
            paths["python_executable"] == executable and paths["base_prefix"] == regular_path(sys.base_prefix),
            "current independent venv layout changed")
    _assert(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            "model runtime requires isolated no-site no-bytecode execution")
    _assert(environment.get("input_environment_digest") == canonical_hash(environment["input_environment"]),
            "historical input environment object changed")
    for name, expected in _normalized_versions(descriptor["expected_versions"]).items():
        _assert(environment["exact_versions"].get(name) == expected,
                "bound model dependency version changed: " + name)
    bound = environment["bound_files_sha256"]
    _assert(isinstance(bound,dict) and bound,"current dependency file inventory missing")
    if check_files:
        for filename,expected in bound.items():
            _assert(file_sha256(filename)==expected,f"bound scientific dependency changed: {filename}")


def _model_runtime_environment():
    """Read actual current backend/CPU-thread controls without setting any value."""
    return {name:os.environ.get(name) for name in MODEL_RUNTIME_ENV}


def _verify_model_runtime_environment(environment):
    recorded = environment.get("model_runtime_environment")
    _assert(isinstance(recorded,dict) and set(recorded)==set(MODEL_RUNTIME_ENV),
            "complete independent model-runtime variable binding required")
    _assert(canonical_hash(recorded)==environment.get("model_runtime_environment_digest"),
            "model-runtime environment digest differs")
    _assert(_model_runtime_environment()==recorded,"current model-runtime variables changed")


def verify_frozen(manifest, repo=None, input_run=None, results_root=None, *, verify_environment=True, full=False, check_inputs=False):
    """Critical bytes at task boundaries; full closure/originals per worker phase.

    Environment file hashing may cover GB and is intentionally performed at
    worker/phase start and end, not 1200 times. Import guards verify first loads.
    Actual per-task array/role bytes remain the FixedInputStore obligation.
    """
    if isinstance(manifest,(str,Path)): manifest = read_json(manifest)
    payload = {key:value for key,value in manifest.items() if key != "manifest_digest"}
    _assert(canonical_hash(payload) == manifest["manifest_digest"], "replication manifest digest mismatch")
    paths = manifest["paths"]
    repo = _target_repo(repo or paths["repo"])
    run = regular_path(input_run or paths["input_run"])
    results = _results_root(repo,results_root or paths["results_root"])
    _assert(str(repo) == paths["repo"] and str(run) == paths["input_run"] and str(results) == paths["results_root"], "replication manifest path identity changed")
    _assert(canonical_hash(read_json(checked_path(results,"provenance_manifest.json")))==canonical_hash(manifest),
            "published replication manifest differs from supplied manifest")
    _assert(manifest["candidate_id"]==CANDIDATE_ID and manifest["input_protocol"]==INPUT_PROTOCOL and
            manifest["replication_id"]==REPLICATION_ID and manifest.get("runtime_id")==RUNTIME_ID and
            manifest.get("model_environment_id")==MODEL_ENVIRONMENT_ID,"replication scientific/runtime identity changed")
    _assert(file_sha256(checked_path(results,"RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md"))==manifest["authorization_record_sha256"],"authorization record changed")
    for relative,expected in manifest["critical_files_sha256"].items():
        _assert(file_sha256(checked_path(repo,relative)) == expected, f"critical scientific byte changed: {relative}")
    for filename,expected in manifest.get("stage_b_dependencies_sha256",{}).items():
        _assert(file_sha256(filename)==expected,f"Stage B verifier dependency changed: {filename}")
    executor = regular_path(paths["executor_root"])
    actual_executor = {path.relative_to(executor).as_posix():file_sha256(path) for path in _scan_files(executor) if path.suffix.lower() == ".py"}
    _assert(actual_executor == manifest["executor_sha256"], "executor implementation changed or gained files")
    current_env = manifest["environment"]
    _assert(canonical_hash(current_env)==manifest["environment_binding"],"current environment binding changed")
    _verify_current_environment(current_env,check_files=verify_environment)
    if full:
        observed_python = {path.relative_to(repo).as_posix():file_sha256(path) for folder in ("core","imported","scripts") for path in _scan_files(checked_path(repo,folder)) if path.suffix.lower()==".py"}
        _assert(observed_python == manifest["original_python_dependency_sha256"], "original Python closure changed or gained files")
        check_original_snapshot(repo,manifest["original_protected_snapshot"])
        _assert(file_sha256(checked_path(EXECUTION_ROOT,"original_protected_start_sha256.json"))==manifest["original_snapshot_source_sha256"],"original protected baseline changed")
        stage_b = verify_stage_b(repo,run)
        _assert(stage_b["binding_sha256"] == manifest["stage_b_bindings"], "Stage B final evidence changed")
    if check_inputs:
        for relative,expected in manifest["input_files_sha256"].items():
            _assert(file_sha256(checked_path(run,relative)) == expected, f"immutable F1 byte changed: {relative}")
    return {"manifest_digest":manifest["manifest_digest"],"critical_scientific_bytes_unchanged":True,
            "environment_file_bytes_checked":verify_environment,"original_full_snapshot_checked":full,
            "all_F1_inputs_checked":check_inputs,"historical_environment_reproduced":False}


def publish_bytes(root, relative, payload):
    """Exclusive complete publication via same-directory hardlink; no overwrite.

    Failed partials are retained. Successful temporary hardlink cleanup is confined
    to this new output root. Atomic link creation fails if destination exists.
    """
    root = _results_root(REPOSITORY,root)
    target = checked_path(root,relative,must_exist=False)
    _assert(not target.exists(), "refusing to overwrite independent result")
    target.parent.mkdir(parents=True,exist_ok=True)
    checked_path(root,relative,must_exist=False)
    partial = target.parent/(target.name+f".partial_{os.getpid()}_{uuid.uuid4().hex}")
    regular_path(partial,must_exist=False)
    with partial.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(partial,target)
    partial.unlink()
    return {"path":str(target),"relative":relative,"sha256":file_sha256(target)}


def publish_json(root, relative, value):
    payload = (json.dumps(_finite(value),sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
    return publish_bytes(root,relative,payload)


def _write_path(path, *, dir_fd=None, mutates_bytes=True):
    if isinstance(path,int):
        if path in {1,2}: return
        path = _descriptor_path(path)
    _assert(dir_fd in {None,-1}, "relative directory-FD mutation forbidden")
    value = os.fsdecode(path)
    if value.casefold() in {"nul","/dev/null"}: return
    candidate = regular_path(value,must_exist=False)
    _assert(candidate == _WRITE_ROOT or _WRITE_ROOT in candidate.parents, f"write outside independent results forbidden: {candidate}")
    if mutates_bytes and candidate.exists() and candidate.is_file():
        _assert(candidate.stat().st_nlink <= 1, "writing a multiply linked output is forbidden")


def _descriptor_path(descriptor):
    """Resolve an existing descriptor read-only; required for tempfile fd wrappers."""
    _assert(type(descriptor) is int and descriptor>=0,"invalid writable file descriptor")
    if os.name=="nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        function = ctypes.WinDLL("kernel32",use_last_error=True).GetFinalPathNameByHandleW
        function.argtypes = (wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD)
        function.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(msvcrt.get_osfhandle(descriptor),buffer,len(buffer),0)
        _assert(0<length<len(buffer),"unidentified writable file descriptor forbidden")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"): value = "\\\\"+value[8:]
        elif value.startswith("\\\\?\\"): value = value[4:]
        return value
    try: return os.readlink(f"/proc/self/fd/{descriptor}")
    except OSError as error:
        raise ProvenanceError("unidentified writable file descriptor forbidden") from error


def install_write_guard(results_root):
    """Install irreversible Python audit guard in a dedicated model worker.

    Launcher subprocess creation must happen before this worker-only guard. Native
    OS IO is trusted within frozen packages and additionally checked by original
    byte snapshots. No broader OS sandbox protection is claimed.
    """
    global _WRITE_ROOT, _WRITE_GUARD_INSTALLED
    root = _results_root(REPOSITORY,results_root)
    if _WRITE_GUARD_INSTALLED:
        _assert(root == _WRITE_ROOT,"write guard root cannot change")
        bootstrap_platform_metadata()
        return
    # Complete Windows VER/processor queries before the irreversible subprocess
    # prohibition. Trusted scientific package import still occurs only afterward.
    bootstrap_platform_metadata()
    _WRITE_ROOT = root
    def hook(event,args):
        if event == "open":
            path,mode,flags = args
            writes = (isinstance(mode,str) and any(char in mode for char in "wax+")) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if writes: _write_path(path)
        elif event in {"os.remove","os.rmdir","os.mkdir","os.chmod","os.chown","os.utime","os.truncate"}:
            descriptor = args[-1] if event in {"os.remove","os.rmdir","os.mkdir","os.chmod","os.chown","os.utime"} and isinstance(args[-1],int) else None
            _write_path(args[0],dir_fd=descriptor if descriptor != -1 else None,
                        mutates_bytes=event not in {"os.remove","os.rmdir","os.mkdir"})
        elif event in {"os.rename","os.link"}:
            _write_path(args[0],mutates_bytes=False); _write_path(args[1],mutates_bytes=False)
            if len(args)>2:
                _assert(all(value is None or type(value) is int and value==-1 for value in args[2:]),"relative directory-FD mutation forbidden")
        elif event=="os.symlink":
            raise ProvenanceError("new symbolic links forbidden inside scientific worker")
        elif event in {"subprocess.Popen","os.system","os.exec","os.posix_spawn"}:
            raise ProvenanceError("subprocess/OS execution forbidden inside scientific worker")
    sys.addaudithook(hook)
    _WRITE_GUARD_INSTALLED = True


def install_generator_guard(repo):
    """Profile actual code frames; original generation calls fail regardless alias."""
    global _GENERATOR_REPO, _GENERATOR_PROFILE
    repo = _target_repo(repo)
    if _GENERATOR_PROFILE is not None:
        _assert(repo == _GENERATOR_REPO and sys.getprofile() is _GENERATOR_PROFILE,"generation call guard changed")
        return
    _GENERATOR_REPO = repo
    def trace(frame,event,arg):
        if event == "call" and frame.f_code.co_name in DENIED_GENERATION:
            filename = Path(frame.f_code.co_filename)
            try: relative = filename.resolve().relative_to(repo)
            except (OSError,ValueError): return
            if relative.parts and relative.parts[0] in {"core","imported","scripts"}:
                name = frame.f_code.co_name
                raise ProvenanceError(f"original generation/refit/entry point forbidden: {relative}:{name}")
        return trace
    _GENERATOR_PROFILE = trace
    sys.setprofile(trace)
    threading.setprofile(trace)


def _bound_imports(manifest):
    """Cache only an immutable normalized origin table, never a file check.

    The full import binding graph determines the key. Every actual import and
    loaded-module check still revalidates its current regular path and byte SHA;
    all phase/task scientific checks remain independent of this metadata cache.
    """
    payload = {"schema":"paper3-frozen-import-origin-bindings-v1",
        "paths":{name:manifest["paths"][name] for name in ("repo","executor_root")},
        "environment":manifest["environment"]["bound_files_sha256"],
        "original_python_dependency_sha256":manifest["original_python_dependency_sha256"],
        "executor_sha256":manifest["executor_sha256"]}
    key = canonical_hash(payload)
    with _IMPORT_BINDINGS_CACHE_LOCK:
        cached = _IMPORT_BINDINGS_CACHE.get(key)
        if cached is not None:
            _assert(type(cached) is MappingProxyType,"mutable/invalid cached import binding table")
            return cached
        bound = {}
        def add(path,digest):
            _assert(isinstance(digest,str) and re.fullmatch(r"[0-9a-f]{64}",digest),"invalid import origin SHA")
            filename = str(path).casefold()
            _assert(filename not in bound or bound[filename]==digest,"conflicting import origin bindings")
            bound[filename] = digest
        for filename,digest in payload["environment"].items(): add(regular_path(filename),digest)
        repo, executor = regular_path(payload["paths"]["repo"]),regular_path(payload["paths"]["executor_root"])
        for relative,digest in payload["original_python_dependency_sha256"].items(): add(checked_path(repo,relative),digest)
        for relative,digest in payload["executor_sha256"].items(): add(checked_path(executor,relative),digest)
        result = MappingProxyType(bound)
        # Workers normally have one immutable manifest. Bound synthetic/migration
        # contexts may differ; a small cache avoids unbounded metadata growth.
        if len(_IMPORT_BINDINGS_CACHE)>=4: _IMPORT_BINDINGS_CACHE.clear()
        _IMPORT_BINDINGS_CACHE[key] = result
        return result


def _module_dict(module):
    _assert(isinstance(module,ModuleType),"expected an actual module namespace")
    return ModuleType.__getattribute__(module,"__dict__")


def _verify_torch_generated_namespace(name, module, manifest, bound):
    """Certify exactly two Torch 2.5.1 generated ModuleType namespaces.

    Their relative __file__ class markers are not file origins. Approval binds
    their real creator files, constructor code origin, exact class and canonical
    owner/root/sys.modules identities. No other missing-file module is admitted.
    """
    identities = {"torch.ops":("torch._ops","_Ops","ops","_ops.py"),
                  "torch.classes":("torch._classes","_Classes","classes","_classes.py")}
    if name not in identities: return False
    owner_name, class_name, attribute, marker = identities[name]
    torch = sys.modules.get("torch")
    owner = sys.modules.get(owner_name)
    torch_values, owner_values, values = _module_dict(torch),_module_dict(owner),_module_dict(module)
    site = regular_path(manifest["environment"]["site_packages_root"])
    root_file = checked_path(site,"torch/__init__.py")
    owner_file = checked_path(site,"torch/"+marker)
    for actual,expected_path,expected_name in ((torch_values,root_file,"torch"),(owner_values,owner_file,owner_name)):
        _assert(actual.get("__name__")==expected_name and regular_path(actual["__file__"])==expected_path,
                "Torch generated namespace creator file/name differs")
        spec = actual.get("__spec__")
        _assert(spec is not None and spec.name==expected_name and regular_path(spec.origin)==expected_path,
                "Torch generated namespace creator module spec differs")
        expected_sha = bound.get(str(expected_path).casefold())
        _assert(expected_sha is not None and file_sha256(expected_path)==expected_sha,
                "Torch generated namespace creator source bytes differ")
    _assert(str(torch_values.get("__version__"))==EXPECTED_MODEL_VERSIONS["torch"],
            "Torch generated namespace runtime version differs")
    constructor_class = owner_values.get(class_name)
    _assert(type(module) is constructor_class and constructor_class.__name__==class_name and
            constructor_class.__module__==owner_name and
            owner_values.get(attribute) is module and torch_values.get(attribute) is module and
            sys.modules.get(name) is module and values.get("__name__")==name and
            values.get("__spec__") is None and
            ModuleType.__getattribute__(module,"__file__")==marker,
            "Torch generated namespace exact class/owner/root/marker identity differs")
    initializer = constructor_class.__dict__.get("__init__")
    _assert(initializer is not None and initializer.__module__==owner_name and
            initializer.__globals__ is owner_values and
            regular_path(initializer.__code__.co_filename)==owner_file,
            "Torch generated namespace constructor is not from its bound creator source")
    if name=="torch.ops":
        libraries = values.get("loaded_libraries")
        _assert(type(libraries) is set,"Torch generated namespace custom-library table differs")
        for filename in libraries:
            path = regular_path(filename)
            expected_sha = bound.get(str(path).casefold())
            _assert(expected_sha is not None and file_sha256(path)==expected_sha,
                    "unbound native custom library in Torch generated namespace")
    return True


class ModelImportGuard:
    def __init__(self,manifest): self.bound = _bound_imports(manifest)
    def find_spec(self,fullname,path=None,target=None):
        spec = BuiltinImporter.find_spec(fullname,path,target) or FrozenImporter.find_spec(fullname,path,target)
        if spec is not None: return spec
        spec = PathFinder.find_spec(fullname,path,target)
        if spec is None: return None
        if spec.origin is None and spec.submodule_search_locations:
            for location in spec.submodule_search_locations:
                prefix = str(regular_path(location)).casefold()+os.sep
                _assert(any(filename.startswith(prefix) for filename in self.bound), "unbound namespace package")
            return spec
        _assert(spec.origin not in {None,"built-in","frozen"},"unbound module origin")
        origin = regular_path(spec.origin)
        expected = self.bound.get(str(origin).casefold())
        _assert(expected is not None and file_sha256(origin)==expected, f"unbound import before execution: {fullname}:{origin}")
        return spec


def install_model_import_guard(manifest):
    guard = ModelImportGuard(manifest)
    existing = None
    for finder in sys.meta_path:
        if isinstance(finder,ModelImportGuard):
            _assert(existing is None and finder.bound==guard.bound,"changed/duplicate model import guard")
            existing = finder
        else: _assert(finder in {BuiltinImporter,FrozenImporter,PathFinder},"unapproved import finder")
    if existing is None: sys.meta_path.insert(0,guard)
    check_loaded_modules(manifest)


def check_loaded_modules(manifest):
    bound = _bound_imports(manifest)
    for name,module in tuple(sys.modules.items()):
        if _verify_torch_generated_namespace(name,module,manifest,bound): continue
        filename = getattr(module,"__file__",None)
        if not filename or filename.startswith("<"): continue
        path = regular_path(filename)
        expected = bound.get(str(path).casefold())
        _assert(expected is not None and file_sha256(path)==expected, f"loaded module is unbound: {name}:{path}")
    return {"loaded_module_file_bindings_valid":True,"historical_environment_reproduced":False}


def require_isolation(results_root):
    root = _results_root(REPOSITORY,results_root)
    _assert(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,"model worker requires -I -S -B")
    _assert(sys.pycache_prefix is not None,"dedicated nonexisting bytecode prefix required")
    prefix = regular_path(sys.pycache_prefix,must_exist=False)
    _assert(root in prefix.parents and not prefix.exists(),"bytecode prefix must stay absent within new results")
    for name in ("TEMP","TMP","TORCH_HOME","CUDA_CACHE_PATH"):
        value = os.environ.get(name)
        _assert(value is not None,"worker temporary/cache location missing: "+name)
        location = regular_path(value,must_exist=False)
        _assert(location==root or root in location.parents,"worker temporary/cache path outside new results: "+name)
    return {"isolated":True,"no_site":True,"no_bytecode":True,"never_created_pycache_prefix":str(prefix)}


def require_authorized_execution(repo, input_run):
    """Fail closed before a caller imports any original project/model module.

    Stage C-E authorization alone is insufficient: the independent immutable
    manifest, input-only scientific gate and all three worker guards are required.
    Initial-state certification is produced by the separately authorized warm-up
    preflight, so it is deliberately not invented or required at this first gate.
    """
    repo, run = _target_repo(repo),regular_path(input_run)
    results = checked_path(repo,RESULTS_NAME)
    manifest = read_json(checked_path(results,"provenance_manifest.json"))
    verify_frozen(manifest,repo,run,results,verify_environment=False)
    require_isolation(results)
    _assert(_WRITE_GUARD_INSTALLED and _WRITE_ROOT==results,"worker write guard absent")
    _assert(_GENERATOR_REPO==repo and _GENERATOR_PROFILE is not None and
            sys.getprofile() is _GENERATOR_PROFILE,"worker generation-call guard absent or changed")
    guards = [finder for finder in sys.meta_path if isinstance(finder,ModelImportGuard)]
    _assert(len(guards)==1 and guards[0].bound==_bound_imports(manifest),"worker import byte guard absent or changed")
    _assert(manifest["stage_b_gate"].get("stage_c_allowed") is True,"Stage B did not authorize Stage C")
    _assert(file_sha256(checked_path(EXECUTION_ROOT,"stage_b_scientific_gate.json"))==manifest["stage_b_bindings"]["gate"],
            "Stage B scientific gate bytes changed")
    _assert(file_sha256(checked_path(run,"execution_receipt.json"))==manifest["stage_b_bindings"]["receipt"],
            "Stage B final-success receipt bytes changed")
    return manifest
