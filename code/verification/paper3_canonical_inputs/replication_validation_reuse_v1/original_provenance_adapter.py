"""Future metadata-only caller adapter; this file does not adopt a live pipeline.

Initial/final callbacks invoke the exact frozen original full verifier. Middle
checks perform no file-content reads. They support a preloaded metadata process
only: scientific imports, runtime-default transitions and module-graph changes
fail closed. The caller must supply reviewed byte bindings and exact inventories.
No CLI, scientific execution, publication or process control is provided here.
"""
from __future__ import annotations

import hashlib
from importlib.machinery import ModuleSpec
import json
import os
from pathlib import Path
import platform
import re
import sys
import threading
from types import ModuleType
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROVENANCE = HERE.parent / "replication_executor_batch20_env_v3/provenance.py"
PROVENANCE_SHA256 = "6eca27e3bc1c79a21a1a1643611adbb8e95e16acdd3d848d10a93914be899823"
SCIENCE = frozenset(("numpy", "torch", "scipy", "sklearn", "river", "pandas", "core", "imported", "scripts"))
IDENTITIES = {"candidate_id": "P7_7_ORIGINAL_BATCH20_CANDIDATE_V1",
    "input_protocol": "P7_7_CANONICAL_INPUT_VERIFICATION_V1",
    "replication_id": "P7_7_INTEGRITY_REPLICATION_BATCH20_V1",
    "runtime_id": "P7_7_INTEGRITY_REPLICATION_BATCH20_ENV_V3",
    "model_environment_id": "P7_7_REPLICATION_MODEL_ENV_V1"}
EXPECTED_MODEL_VERSIONS = {"numpy": "2.4.6", "torch": "2.5.1+cu121", "scipy": "1.17.1",
    "scikit-learn": "1.9.0", "river": "0.23.0", "pandas": "2.3.3", "psutil": "7.2.2"}


class AdapterError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise AdapterError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def lexical(path):
    """No resolve/stat: middle checks must not read or hash file contents."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def exact_source_module(path, name, expected_sha256):
    """Compile exactly one SHA-approved source read; never select a .pyc file.

    expected_sha256 is a predeclared reviewed pin, not a digest adopted from an
    unknown file. Later session acquisition/bookends independently bind the
    current on-disk file; a transient source replacement cannot select the code
    executed here. Registration precedes exec for dataclasses/normal module APIs.
    """
    path = Path(path)
    require(path.is_absolute() and name not in sys.modules, "fresh absolute source module required")
    require(isinstance(expected_sha256, str) and re.fullmatch(r"[a-f0-9]{64}", expected_sha256),
        "predeclared exact source SHA required")
    source = path.read_bytes()
    require(hashlib.sha256(source).hexdigest() == expected_sha256, "exact source bytes differ from reviewed SHA")
    code = compile(source, str(path), "exec", dont_inherit=True, optimize=0)
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name.rpartition(".")[0]
    module.__loader__ = None
    module.__cached__ = None
    module.__spec__ = ModuleSpec(name, loader=None, origin=str(path), is_package=False)
    module.__spec__.has_location = True
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
        return module
    except BaseException:
        sys.modules.pop(name, None)
        raise


def load_original_provenance():
    """Small source-pin verification/import only; never invokes its full gate."""
    name = "paper3_future_metadata_provenance_" + uuid.uuid4().hex
    module = exact_source_module(PROVENANCE, name, PROVENANCE_SHA256)
    try:
        require(lexical(module.verify_frozen.__code__.co_filename) == lexical(PROVENANCE),
            "original verifier code origin differs")
        return module
    except BaseException:
        sys.modules.pop(name, None)
        raise


def non_file_predicates(manifest, observed):
    """Pure predicates corresponding to the metadata-only original runtime case.

    Immutable file-backed layout/config facts remain protected by the session;
    the original bookends still re-read/revalidate them. This is deliberately
    narrower than the original scientific post-import transition machinery.
    """
    payload = {k: v for k, v in manifest.items() if k != "manifest_digest"}
    require(canonical(payload) == manifest["manifest_digest"], "manifest object changed")
    require(all(manifest.get(k) == v for k, v in IDENTITIES.items()), "scientific/runtime identity changed")
    require(isinstance(manifest.get("frozen_final_configuration"), dict) and
        manifest["frozen_final_configuration"], "frozen configuration missing")
    env = manifest["environment"]
    require(canonical(env) == manifest["environment_binding"], "environment object changed")
    require(observed["executable"] == lexical(env["python_executable"]) and
        observed["python_version"] == env["python_version"], "model interpreter semantic identity changed")
    require(observed["thread_environment"] == env["thread_environment"], "numeric thread environment changed")
    require(observed["model_runtime_environment"] == env["model_runtime_environment"] and
        canonical(env["model_runtime_environment"]) == env["model_runtime_environment_digest"],
        "raw model runtime environment changed")
    require(observed["byteorder"] == env["byteorder"] and observed["platform"] == env["platform"],
        "platform/endian changed")
    require(observed["hardware"] == env["hardware"], "hardware metadata changed")
    require(env.get("packages_imported_during_capture") is False and
        env.get("historical_environment_reproduced") is False and
        env.get("site_startup_processed") is False and env.get("model_environment_id") == IDENTITIES["model_environment_id"],
        "runtime scope changed")
    descriptor = env["model_runtime_descriptor"]
    require(canonical(descriptor) == env["model_runtime_descriptor_digest"], "runtime descriptor changed")
    require(observed["base_prefix"] == lexical(descriptor["base_prefix"]), "base runtime prefix changed")
    require(descriptor.get("schema") == "paper3-reviewed-independent-model-runtime-v1" and
        descriptor.get("environment_id") == IDENTITIES["model_environment_id"], "runtime descriptor identity changed")
    prefix = lexical(descriptor["prefix"])
    require(lexical(descriptor["python_executable"]) == lexical(Path(prefix) / "Scripts/python.exe") and
        lexical(descriptor["site_packages_root"]) == lexical(Path(prefix) / "Lib/site-packages") and
        lexical(descriptor["stdlib_root"]) == lexical(Path(descriptor["base_prefix"]) / "Lib") and
        lexical(env["site_packages_root"]) == lexical(descriptor["site_packages_root"]), "runtime layout object changed")
    require(observed["isolated"] and observed["no_site"] and observed["no_bytecode"], "isolated runtime flags changed")
    require(canonical(env["input_environment"]) == env["input_environment_digest"], "historical input environment changed")
    versions = descriptor.get("expected_versions")
    require(isinstance(versions, dict) and versions, "exact dependency versions missing")
    normalized = {}
    for name, version in versions.items():
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) and
            isinstance(version, str) and version, "invalid dependency version")
        key = re.sub(r"[-_.]+", "-", name).lower()
        require(key not in normalized, "duplicate canonical dependency name")
        normalized[key] = version
    require(all(normalized.get(k) == v for k, v in EXPECTED_MODEL_VERSIONS.items()) and
        all(env["exact_versions"].get(k) == v for k, v in normalized.items()), "bound dependency versions changed")
    require(observed["scientific_import_pending"] is False and observed["scientific_import_post"] is False and
        not observed["scientific_modules"], "scientific process requires a separate reviewed phase-aware adapter")
    return {"manifest_digest": manifest["manifest_digest"], "runtime_semantics_checked": True,
        "scope": "PRELOADED_METADATA_ONLY_NO_SCIENTIFIC_IMPORT_TRANSITION",
        "new_file_SHA_check_performed": False}


def require_manifest_bindings(manifest, bindings):
    """Require original full-gate leaves; additional caller assets are allowed."""
    normalized = {lexical(k): v for k, v in bindings.items()}
    require(len(normalized) == len(bindings), "aliased protected paths")
    required = {}
    def add(path, value):
        name = lexical(path)
        require(name not in required or required[name] == value, "conflicting full-gate binding")
        required[name] = value
    paths = manifest["paths"]
    for key in ("critical_files_sha256", "original_python_dependency_sha256", "original_protected_snapshot"):
        for name, value in manifest[key].items():
            add(Path(paths["repo"]) / name, value)
    for key in ("bound_files_sha256",):
        for name, value in manifest["environment"][key].items():
            add(name, value)
    add(manifest["environment"]["python_executable"], manifest["environment"]["python_executable_sha256"])
    for name, value in manifest.get("stage_b_dependencies_sha256", {}).items():
        add(name, value)
    for name, value in manifest["executor_sha256"].items():
        add(Path(paths["executor_root"]) / name, value)
    for name, value in manifest["input_files_sha256"].items():
        add(Path(paths["input_run"]) / name, value)
    descriptor = manifest["environment"]["model_runtime_descriptor"]
    for name, value in descriptor["installation_evidence_files_sha256"].items():
        add(name, value)
    if descriptor.get("descriptor_source_file"):
        add(descriptor["descriptor_source_file"], descriptor["descriptor_source_sha256"])
    add(Path(paths["results_root"]) / "RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md", manifest["authorization_record_sha256"])
    execution = Path(paths["repo"]) / "verification/paper3_canonical_inputs/execution_20261009"
    add(execution / "original_protected_start_sha256.json", manifest["original_snapshot_source_sha256"])
    names = {"gate": execution / "stage_b_scientific_gate.json", "reviewed_environment": execution / "environment.reviewed.json",
        "gate_helper": execution / "check_stage_b_gate.py", "receipt": Path(paths["input_run"]) / "execution_receipt.json",
        "outputs_inventory": Path(paths["input_run"]) / "outputs_inventory.json", "run_manifest": Path(paths["input_run"]) / "run_manifest.json",
        "F1": Path(paths["input_run"]) / "contexts/F1.json", "source_environment": Path(paths["input_run"]) / "source_environment_manifest.json"}
    for key, path in names.items():
        add(path, manifest["stage_b_bindings"][key])
    add(PROVENANCE, PROVENANCE_SHA256)
    require(all(normalized.get(k) == v for k, v in required.items()), "protected graph omits/differs from original full-gate binding")
    # These additional JSON objects are read by verify_stage_b and must also be
    # supplied from its predeclared, hash-bound outputs inventory by the caller.
    for name in ("definition_manifest.json", "validation_certificate.json", "bank_feasibility_inventory.json"):
        require(lexical(Path(paths["input_run"]) / name) in normalized, "Stage B metadata leaf missing: " + name)
    for path in (Path(paths["results_root"]) / "provenance_manifest.json", Path(descriptor["prefix"]) / "pyvenv.cfg"):
        require(lexical(path) in normalized, "published manifest/runtime configuration not protected")
    return normalized


class OriginalProvenanceCallbacks:
    def __init__(self, manifest, bindings):
        self._serialized = json.dumps(manifest, sort_keys=True, ensure_ascii=False, allow_nan=False)
        self._manifest_digest = manifest["manifest_digest"]
        self._bindings = require_manifest_bindings(manifest, bindings)
        self._p = load_original_provenance()
        self._full = self._p.verify_frozen
        self._bootstrap = self._p.bootstrap_platform_metadata
        self._baseline = None

    def full_verify(self):
        require(self._p.verify_frozen is self._full and self._p.bootstrap_platform_metadata is self._bootstrap,
            "original verifier callback was replaced")
        manifest = json.loads(self._serialized)
        paths = manifest["paths"]
        # Deliberately call the original implementation; never return a receipt
        # or synthetic success in place of these four complete byte closures.
        return self._full(manifest, Path(paths["repo"]), Path(paths["input_run"]), Path(paths["results_root"]),
            verify_environment=True, full=True, check_inputs=True)

    def runtime_verify(self):
        require(self._p.verify_frozen is self._full and self._p.bootstrap_platform_metadata is self._bootstrap,
            "original callback identity changed")
        manifest = json.loads(self._serialized)
        env = manifest["environment"]
        require(self._p._PLATFORM_BOOTSTRAP is not None, "runtime check requires the actual original initial full gate")
        metadata = self._bootstrap()  # Process-bound cached immutable OS values; no file reads.
        modules = {}
        science = []
        for name, module in tuple(sys.modules.items()):
            if name.split(".")[0] in SCIENCE:
                science.append(name)
            if module is None:
                modules[name] = None
                continue
            require(type(module) is ModuleType, "nonmodule entry in metadata module graph")
            values = vars(module)
            filename = values.get("__file__")
            spec = values.get("__spec__")
            origin = getattr(spec, "origin", None)
            if filename and not filename.startswith("<"):
                require(lexical(filename) in self._bindings, "loaded metadata module is not protected: " + name)
            modules[name] = (id(module), filename, origin)
        observed = {"executable": lexical(sys.executable), "python_version": platform.python_version(),
            "base_prefix": lexical(sys.base_prefix), "thread_environment": {n: os.environ.get(n) for n in self._p.THREAD_ENV},
            "model_runtime_environment": {n: os.environ.get(n) for n in self._p.MODEL_RUNTIME_ENV},
            "byteorder": sys.byteorder, "platform": metadata["platform"],
            "hardware": {"machine": metadata["machine"], "processor": metadata["processor"], "processor_identifier": os.environ.get("PROCESSOR_IDENTIFIER")},
            "isolated": bool(sys.flags.isolated), "no_site": bool(sys.flags.no_site), "no_bytecode": bool(sys.dont_write_bytecode),
            "scientific_import_pending": self._p._SCIENTIFIC_IMPORT_PENDING is not None,
            "scientific_import_post": self._p._SCIENTIFIC_IMPORT_POST is not None, "scientific_modules": sorted(science)}
        result = non_file_predicates(manifest, observed)
        current = (os.getpid(), threading.get_ident(), tuple(sys.path), tuple(id(f) for f in sys.meta_path),
            id(sys.getprofile()), id(sys.gettrace()), sys.pycache_prefix, modules)
        if self._baseline is None:
            self._baseline = current
        else:
            require(current == self._baseline, "metadata process/module/import graph changed; fresh full session required")
        return result


def make_metadata_session(*, manifest, bindings, trees, verifier_sources, backend,
                          accept_documented_native_limitations=False):
    """Future caller factory. Does not start a session or claim production adoption.

    All metadata modules must be preloaded; original inventory TreeSpecs must be
    reviewed before invocation. Publication/root archive/ZIP remains the caller's
    existing audited implementation, inside session.publication_guard(...).
    """
    for path in (Path(__file__), HERE / "session.py", HERE / "windows_handles.py", PROVENANCE):
        require(bindings.get(str(path)) == digest(path) and verifier_sources.get(str(path)) == digest(path),
            "adapter/session/original verifier source lacks exact protected pin")
    expected_roots = {lexical(Path(manifest["paths"]["repo"]) / n) for n in ("core", "imported", "scripts")}
    expected_roots.add(lexical(manifest["paths"]["executor_root"]))
    covered = {lexical(t.root) for t in trees if tuple(t.file_suffixes) == (".py",) and
        set(t.excluded_directory_names) <= {"__pycache__"}}
    require(expected_roots <= covered, "original Python/executor exact inventories are required")
    module = exact_source_module(HERE / "session.py", "paper3_future_metadata_session_" + uuid.uuid4().hex,
        verifier_sources[str(HERE / "session.py")])
    # TreeSpec's class identity belongs to the loaded session module. Accept only
    # serialized reviewed inventory declarations, then reconstruct its own types.
    declarations = [module.TreeSpec(t.root, dict(t.entries), tuple(t.excluded_directory_names), tuple(t.file_suffixes)) for t in trees]
    callbacks = OriginalProvenanceCallbacks(manifest, bindings)
    return module.ValidationSession(bindings=bindings, trees=declarations, manifest_digest=manifest["manifest_digest"],
        verifier_sources=verifier_sources, original_full_verify=callbacks.full_verify, runtime_verify=callbacks.runtime_verify,
        backend=backend, accept_documented_native_limitations=accept_documented_native_limitations)
