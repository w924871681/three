"""Exact, separately bound import-origin extension for a new scheduler worker.

The frozen manifest and all existing import origins remain unchanged.  This
module changes only one private process's origin-table provider, before the
original worker installs its guards.  It never hides a loaded module, changes
``__file__``, modifies a scientific function, or writes a file.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import re
import sys
from types import MappingProxyType


REPO_ROOT = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
SCHEDULER_ROOT = REPO_ROOT / "verification/paper3_canonical_inputs/replication_dynamic_scheduler_v1"
EXECUTOR_ROOT = REPO_ROOT / "verification/paper3_canonical_inputs/replication_executor_batch20_env_v3"
EXTENSION_SCOPE = "ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256"


class GuardExtensionError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise GuardExtensionError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def no_reparse(path):
    path = Path(path)
    require(path.is_absolute(), "absolute source path required")
    for item in (path, *path.parents):
        require(not item.is_symlink(), "source symlink rejected: " + str(item))
        if item.exists():
            require(not getattr(item.lstat(), "st_file_attributes", 0) & 0x400,
                    "source reparse point rejected: " + str(item))


def sha(path):
    no_reparse(path)
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_sidecar(contract):
    require(contract.get("source_extension_scope") == EXTENSION_SCOPE, "source extension scope differs")
    sources = contract.get("sidecar_sources")
    require(type(sources) is dict and sources, "nonempty exact sidecar source map required")
    require(contract.get("sidecar_digest") == canonical(sources), "sidecar source digest differs")
    normalized = {}
    for name, expected in sources.items():
        require(type(name) is str and type(expected) is str and
                re.fullmatch(r"[0-9a-f]{64}", expected), "malformed sidecar source binding")
        path = Path(name)
        require(path.is_absolute() and path.is_relative_to(SCHEDULER_ROOT) and path.suffix == ".py",
                "sidecar source outside independent scheduler: " + name)
        no_reparse(path)
        require(path.resolve() == path and path.is_file(), "sidecar source missing or aliased")
        key = str(path).casefold()
        require(key not in normalized, "duplicate sidecar source alias")
        require(sha(path) == expected, "sidecar source SHA differs: " + name)
        normalized[key] = expected
    required = {str(SCHEDULER_ROOT / name).casefold() for name in ("guard_extension.py", "frozen_bridge.py")}
    require(required <= set(normalized), "both production bridge sources must be explicitly bound")
    return MappingProxyType(normalized)


def install(provenance, manifest, contract):
    """Extend the original immutable origin map; retain every original check.

    Production callers must use a fresh original provenance module before
    ``executor_worker._prepare``.  The returned receipt is metadata, never a
    claim that a model, runtime smoke, or experiment has succeeded.
    """
    additions = validate_sidecar(contract)
    source = Path(provenance.__file__)
    require(source == EXECUTOR_ROOT / "provenance.py", "unexpected original provenance source")
    require(Path(manifest["paths"]["executor_root"]) == EXECUTOR_ROOT, "original executor root differs")
    original_source_sha = manifest["executor_sha256"].get("provenance.py")
    require(sha(source) == original_source_sha, "original provenance SHA differs")
    require(not getattr(provenance, "_paper3_dynamic_import_extension", None), "extension already installed")
    require(not getattr(provenance, "_WRITE_GUARD_INSTALLED", False), "extension must precede original preparation")
    require(not any(isinstance(finder, provenance.ModelImportGuard) for finder in sys.meta_path),
            "model import guard already installed")
    original = provenance._bound_imports
    require(Path(original.__code__.co_filename) == source and original.__globals__ is provenance.__dict__,
            "original origin provider is not the freshly imported function")
    original_source_function_sha = hashlib.sha256(inspect.getsource(original).encode()).hexdigest()
    original_table = original(manifest)
    require(type(original_table) is MappingProxyType, "original origin table is not immutable")
    baseline = dict(original_table)
    require(not set(additions) & set(baseline), "sidecar cannot replace an original import origin")
    baseline_digest = canonical(baseline)
    manifest_digest = manifest["manifest_digest"]
    combined = MappingProxyType({**baseline, **dict(additions)})

    def extended_bound_imports(current_manifest):
        require(current_manifest.get("manifest_digest") == manifest_digest, "extension used with another manifest")
        require(sha(source) == original_source_sha, "original provenance bytes changed")
        require(validate_sidecar(contract) == additions, "sidecar bindings changed")
        current = original(current_manifest)
        require(type(current) is MappingProxyType and dict(current) == baseline,
                "original import origin closure changed")
        require(all(combined[name] == expected for name, expected in current.items()),
                "original import origin removed or replaced")
        return combined

    provenance._bound_imports = extended_bound_imports
    receipt = {
        "schema": "paper3-dynamic-exact-import-extension-v1", "metadata_only": True,
        "manifest_digest": manifest_digest, "source_extension_scope": EXTENSION_SCOPE,
        "sidecar_digest": contract["sidecar_digest"], "sidecar_sources": dict(contract["sidecar_sources"]),
        "original_provenance_path": str(source), "original_provenance_sha256": original_source_sha,
        "original_origin_provider_source_sha256": original_source_function_sha,
        "original_origin_count": len(baseline), "original_origin_digest": baseline_digest,
        "added_origin_count": len(additions), "combined_origin_digest": canonical(dict(combined)),
        "original_origins_preserved": True, "original_import_and_loaded_module_checks_retained": True,
        "original_manifest_modified": False, "loaded_modules_hidden": False,
        "module_file_attributes_changed": False, "scientific_algorithm_modified": False,
        "real_model_execution_claimed": False,
    }
    provenance._paper3_dynamic_import_extension = MappingProxyType(receipt)
    require(provenance._bound_imports(manifest) == combined, "installed extension differs")
    return receipt
