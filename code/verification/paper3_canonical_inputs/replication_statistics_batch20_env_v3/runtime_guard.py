"""Fail-closed, stdlib-only import/read guard for the independent statistics task.

No project model/generator or training module is admitted. These Python guards
supplement SHA closure checks; they do not claim to sandbox native NumPy IO.
"""
from __future__ import annotations

import hashlib
import os
import sys
import sysconfig
from importlib.machinery import BuiltinImporter,FrozenImporter,PathFinder
from pathlib import Path

_INSTALLED = None


class StatisticsGuardError(RuntimeError):
    pass


def _assert(condition,message):
    if not condition: raise StatisticsGuardError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576),b""): digest.update(chunk)
    return digest.hexdigest()


def allowed_module_origin(fullname,path, *, bound,repo,statistics_root,executor_root,site_root,stdlib_root):
    """Pure allowlist predicate; synthetic path contracts are testable without IO."""
    path = Path(path).resolve()
    repo,stats,executor,site,stdlib = (Path(value).resolve() for value in
        (repo,statistics_root,executor_root,site_root,stdlib_root))
    key = str(path).casefold()
    if key not in bound: return False
    if path==stats or stats in path.parents: return path.suffix==".py"
    if path==executor or executor in path.parents:
        return path.parent==executor and path.name in {"provenance.py","executor_driver.py"}
    # The independent venv is deliberately inside the repository. Admit only
    # its bound NumPy package before rejecting other repository origins; the
    # module name alone cannot admit another package from site-packages.
    if path==site or site in path.parents:
        numpy_root = site/"numpy"
        return (fullname=="numpy" or fullname.startswith("numpy.")) and numpy_root in path.parents
    if path==repo or repo in path.parents: return False
    # Stdlib plus its interpreter-extension directory may be bound outside Lib.
    if path==stdlib or stdlib in path.parents: return True
    return fullname.partition(".")[0] in sys.stdlib_module_names


class StatisticsImportGuard:
    def __init__(self, *, bound,repo,statistics_root,executor_root,site_root,stdlib_root,provenance):
        self.contract = dict(bound=bound,repo=repo,statistics_root=statistics_root,executor_root=executor_root,
                             site_root=site_root,stdlib_root=stdlib_root)
        self.provenance = provenance

    def check(self,fullname,path):
        origin = self.provenance.regular_path(path)
        _assert(allowed_module_origin(fullname,origin,**self.contract),"statistics import forbidden: "+fullname+":"+str(origin))
        expected = self.contract["bound"][str(origin).casefold()]
        _assert(self.provenance.file_sha256(origin)==expected,"statistics imported source/binary byte changed: "+str(origin))
        return origin

    def find_spec(self,fullname,path=None,target=None):
        spec = BuiltinImporter.find_spec(fullname,path,target) or FrozenImporter.find_spec(fullname,path,target)
        if spec is not None: return spec
        spec = PathFinder.find_spec(fullname,path,target)
        if spec is None: return None
        if spec.origin is None and spec.submodule_search_locations:
            # No unbound namespace packages are necessary for stdlib/NumPy.
            raise StatisticsGuardError("namespace package forbidden in statistics: "+fullname)
        _assert(spec.origin not in {None,"built-in","frozen"},"statistics module has no bound origin")
        self.check(fullname,spec.origin)
        return spec


def _all_bound_files(manifest,bindings,provenance):
    bound = dict(manifest["environment"]["bound_files_sha256"])
    descriptor = manifest["environment"].get("model_runtime_descriptor",{})
    installed = descriptor.get("installation_evidence_files_sha256",{})
    bound.update(installed)
    if descriptor.get("descriptor_source_file"):
        bound[descriptor["descriptor_source_file"]] = descriptor["descriptor_source_sha256"]
    if descriptor.get("layout_evidence_path"):
        layout = provenance.regular_path(descriptor["layout_evidence_path"])
        _assert(str(layout) in installed,"runtime layout evidence lacks explicit installation SHA binding")
    repo = provenance.regular_path(manifest["paths"]["repo"])
    executor = provenance.regular_path(manifest["paths"]["executor_root"])
    run = provenance.regular_path(manifest["paths"]["input_run"])
    for name in ("critical_files_sha256","original_python_dependency_sha256","original_protected_snapshot"):
        for relative,digest in manifest[name].items():
            path = provenance.checked_path(repo,relative)
            previous = bound.setdefault(str(path),digest)
            _assert(previous==digest,"conflicting statistics/original byte binding")
    for relative,digest in manifest["executor_sha256"].items():
        bound[str(provenance.checked_path(executor,relative))] = digest
    for relative,digest in manifest["input_files_sha256"].items():
        bound[str(provenance.checked_path(run,relative))] = digest
    bound.update(manifest.get("stage_b_dependencies_sha256",{}))
    for filename,digest in bindings.items():
        previous = bound.setdefault(filename,digest)
        _assert(previous==digest,"conflicting statistics input binding")
    # Stage B closure is re-read by verify_frozen; every inventory byte belongs
    # to the previously passed input-only run, never to an alternate dataset.
    inventory = provenance.read_json(provenance.checked_path(run,"outputs_inventory.json"))["files"]
    for relative,digest in inventory.items():
        bound[str(provenance.checked_path(run,relative))] = digest
    execution = repo/"verification/paper3_canonical_inputs/execution_20261009"
    for relative in ("original_protected_start_sha256.json","stage_b_scientific_gate.json","environment.reviewed.json"):
        path = provenance.checked_path(execution,relative)
        bound.setdefault(str(path),provenance.file_sha256(path))
    for relative in ("execution_receipt.json","outputs_inventory.json"):
        path = provenance.checked_path(run,relative)
        bound.setdefault(str(path),provenance.file_sha256(path))
    return {str(provenance.regular_path(filename)).casefold():digest for filename,digest in bound.items()}


def install_statistics_import_guard(manifest,bindings,provenance):
    global _INSTALLED
    _assert(_INSTALLED is None,"statistics guards require one fresh dedicated process")
    stats = Path(__file__).resolve().parent
    bound = _all_bound_files(manifest,bindings,provenance)
    guard = StatisticsImportGuard(bound=bound,repo=manifest["paths"]["repo"],statistics_root=stats,
        executor_root=manifest["paths"]["executor_root"],site_root=manifest["environment"]["site_packages_root"],
        stdlib_root=sysconfig.get_path("stdlib"),provenance=provenance)
    _assert(all(finder in {BuiltinImporter,FrozenImporter,PathFinder} for finder in sys.meta_path),"unexpected import hook before statistics")
    for name,module in tuple(sys.modules.items()):
        path = getattr(module,"__file__",None)
        if path and not path.startswith("<"): guard.check(name,path)
    output = provenance.regular_path(manifest["paths"]["results_root"])/"statistics_batch20_env_v3"
    def read_hook(event,args):
        if event!="open": return
        path,mode,flags = args
        writes = (isinstance(mode,str) and any(char in mode for char in "wax+")) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
        if writes or isinstance(path,int): return  # separate irreversible write guard
        value = os.fsdecode(path)
        if value.casefold() in {"nul","/dev/null"}: return
        candidate = provenance.regular_path(value,must_exist=False)
        # Python's source loader can probe a nonexistent cached bytecode path;
        # -B/-I/-S prevents its creation/use from untrusted external search paths.
        if not candidate.exists() and candidate.suffix==".pyc":
            cache_prefix = Path(sys.pycache_prefix).resolve() if sys.pycache_prefix else None
            if "__pycache__" in candidate.parts or cache_prefix is not None and cache_prefix in candidate.parents: return
        _assert(str(candidate).casefold() in bound or output in candidate.parents,
                "unbound read outside statistics evidence: "+str(candidate))
    sys.meta_path.insert(0,guard)
    sys.addaudithook(read_hook)
    _INSTALLED = guard
    return {"model_generator_imports_forbidden":True,"numpy_and_stdlib_only":True,
            "read_allowlist_file_count":len(bound),"output_only_publication_root":str(output)}
