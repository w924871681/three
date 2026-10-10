"""Session-local retained-handle reuse of an already verified byte binding.

No project imports, model calls, process launches, writes, or JSON-cache loading.
The injected original full and runtime validators remain part of the trusted
reviewed call site. Bookends ALSO hash every protected binding independently.
Metadata-only boundary success is never represented as a new SHA verification.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import threading
from types import MappingProxyType
import uuid


class ReuseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReuseError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha_string(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def absolute(path):
    value = Path(path)
    require(value.is_absolute() and ".." not in value.parts, "absolute non-traversing path required")
    # Do not resolve: following an unexamined reparse point is forbidden.
    return Path(os.path.normpath(str(value)))


@dataclass(frozen=True)
class TreeSpec:
    """Exact predeclared filesystem inventory; no automatic baseline discovery.

    Entries map relative POSIX paths to 'file' or 'directory'. Exclusions are
    immutable predeclared *directory names* (e.g. a frozen __pycache__ rule).
    Every selected file must also have a protected SHA binding. Empty selected
    directories count, so additions/removals are not hidden by file-only scans.
    """
    root: str
    entries: object
    excluded_directory_names: tuple = ()
    file_suffixes: tuple = ()

    def __post_init__(self):
        root = str(absolute(self.root))
        require(isinstance(self.entries, dict) and self.entries, "nonempty expected tree inventory required")
        entries = dict(self.entries)
        for relative, kind in entries.items():
            require(isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative,
                "canonical relative inventory path required")
            item = Path(relative)
            require(not item.is_absolute() and ".." not in item.parts and "." not in item.parts,
                "unsafe inventory entry")
            require(PurePosixPath(relative).as_posix() == relative and not relative.startswith("/"),
                "normalized relative inventory path required")
            require(kind in ("file", "directory"), "unsupported inventory entry kind")
        excluded = tuple(self.excluded_directory_names)
        require(all(isinstance(n, str) and n and "/" not in n and "\\" not in n and n not in (".", "..")
                    for n in excluded) and len(excluded) == len(set(excluded)), "invalid directory exclusion")
        suffixes = tuple(self.file_suffixes)
        require(all(isinstance(n, str) and n.startswith(".") and "/" not in n and "\\" not in n
                    for n in suffixes), "invalid file suffix selector")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "entries", MappingProxyType(entries))
        object.__setattr__(self, "excluded_directory_names", excluded)
        object.__setattr__(self, "file_suffixes", suffixes)


class ValidationSession:
    """An unpicklable, single-owner, same-process validation epoch.

    Backend API: process_identity(), open_read(path,directory), identity(handle),
    close(handle), inventory(TreeSpec), hash_file(path). Native handles must be
    non-inheritable, FILE_SHARE_READ only, with reparse rejection and FILE_ID.
    Construction does no filesystem IO. start() must be called once; an error
    permanently invalidates the epoch and attempts to close every owned handle.
    """
    def __init__(self, *, bindings, trees, manifest_digest, verifier_sources,
                 original_full_verify, runtime_verify, backend,
                 accept_documented_native_limitations=False):
        require(isinstance(bindings, dict) and bindings, "protected SHA bindings required")
        frozen = {str(absolute(p)): h for p, h in bindings.items()}
        require(len(frozen) == len(bindings) and all(sha_string(h) for h in frozen.values()), "invalid/aliased bindings")
        require(len({p.casefold() for p in frozen}) == len(frozen), "case-aliased protected bindings")
        sources = {str(absolute(p)): h for p, h in verifier_sources.items()}
        require(sources and all(frozen.get(p) == h for p, h in sources.items()), "validator sources must be protected")
        require(sha_string(manifest_digest), "canonical manifest digest required")
        require(callable(original_full_verify) and callable(runtime_verify), "both original validators required")
        require(accept_documented_native_limitations is True, "explicit acceptance of documented native trust limits required")
        self.bindings = MappingProxyType(frozen)
        self.verifier_sources = MappingProxyType(sources)
        self.trees = tuple(trees)
        require(self.trees and all(isinstance(t, TreeSpec) for t in self.trees), "predeclared exact inventories required")
        for tree in self.trees:
            for relative, kind in tree.entries.items():
                if kind == "file":
                    require(str(absolute(Path(tree.root) / relative)) in frozen, "inventory file lacks protected SHA")
        self.manifest_digest = manifest_digest
        self._full = original_full_verify
        self._runtime = runtime_verify
        self.backend = backend
        self._process = backend.process_identity()
        self._owner_thread = threading.get_ident()
        self._mutex = threading.RLock()
        self._handles = {}
        self._temporary_handles = {}
        self._identities = {}
        self._nonce = uuid.uuid4().hex
        self._state = "NEW"
        self._events = []
        self._bookend_count = 0
        self._close_errors = []

    def __reduce_ex__(self, protocol):
        raise ReuseError("native session leases cannot be serialized or reused across processes")

    def __copy__(self):
        raise ReuseError("native session leases cannot be copied")

    __deepcopy__ = lambda self, memo: self.__copy__()

    @property
    def state(self):
        return self._state

    def _owner(self):
        require(threading.get_ident() == self._owner_thread, "session thread owner changed")
        require(self.backend.process_identity() == self._process, "session process identity changed; no cross-process cache")

    def _event(self, action, **fields):
        self._events.append({"sequence": len(self._events) + 1, "utc": utc(), "action": action, **fields})

    def _inventories(self):
        for tree in self.trees:
            require(self.backend.inventory(tree) == dict(tree.entries), "exact inventory changed: " + tree.root)

    def _path_set(self):
        files = set(self.bindings)
        directories = set()
        for filename in files:
            directories.update(str(p) for p in absolute(filename).parents)
        for tree in self.trees:
            directories.add(tree.root)
            directories.update(str(p) for p in absolute(tree.root).parents)
            for relative, kind in tree.entries.items():
                if kind == "directory":
                    p = absolute(Path(tree.root) / relative)
                    directories.add(str(p))
                    directories.update(str(parent) for parent in p.parents)
        require(not files & directories, "file/directory identity collision")
        return sorted(directories, key=lambda p: (len(Path(p).parts), p.casefold())), sorted(files)

    def _check_paths(self):
        self._inventories()
        for path, handle in self._handles.items():
            expected = self._identities[path]
            require(self.backend.identity(handle) == expected, "retained handle identity changed: " + path)
            fresh = None
            try:
                fresh = self.backend.open_read(path, directory=expected["directory"])
                self._temporary_handles[fresh] = path
                require(self.backend.identity(fresh) == expected, "path FILE_ID/volume/attributes changed: " + path)
            finally:
                if fresh is not None:
                    self._close_temporary(fresh)
        self._inventories()

    def _close_temporary(self, handle):
        try:
            self.backend.close(handle)
        except BaseException as error:
            self._close_errors.append({"path": self._temporary_handles[handle], "kind": "temporary",
                "error_type": type(error).__name__, "message": str(error)})
            raise
        else:
            self._temporary_handles.pop(handle, None)

    def _runtime_check(self):
        result = self._runtime()
        require(isinstance(result, dict) and result.get("manifest_digest") == self.manifest_digest
            and result.get("runtime_semantics_checked") is True,
            "fresh original environment/import/runtime predicates did not pass")
        # A byte lease does not replace these semantic checks.
        self._event("RUNTIME_PREDICATES_PASSED")

    def _full_check(self, phase):
        self._event("ORIGINAL_FULL_VERIFY_STARTED", phase=phase)
        result = self._full()
        required = ("critical_scientific_bytes_unchanged", "environment_file_bytes_checked",
                    "original_full_snapshot_checked", "all_F1_inputs_checked")
        require(isinstance(result, dict) and result.get("manifest_digest") == self.manifest_digest
            and all(result.get(key) is True for key in required), "original full verifier did not pass all four closures")
        # Independent complete SHA coverage also binds assets outside the original
        # API's closure. Neither metadata nor a serialized success record suffices.
        for path, expected in self.bindings.items():
            require(self.backend.hash_file(path) == expected, "bookend byte SHA changed: " + path)
        self._check_paths()
        self._runtime_check()
        self._bookend_count += 1
        self._event("ORIGINAL_FULL_VERIFY_AND_ALL_BOUND_SHAS_PASSED", phase=phase,
                    protected_files=len(self.bindings))

    def start(self):
        with self._mutex:
            try:
                require(self._state == "NEW", "session cannot start/restart")
                self._owner()
                self._state = "ACQUIRING"
                self._inventories()
                directories, files = self._path_set()
                for path, directory in [(p, True) for p in directories] + [(p, False) for p in files]:
                    handle = self.backend.open_read(path, directory=directory)
                    self._handles[path] = handle
                    self._identities[path] = self.backend.identity(handle)
                self._check_paths()
                # The original verifier must run *after* all deny-write/delete
                # handles exist. An old full receipt cannot initialize this epoch.
                self._state = "INITIAL_FULL_VERIFY"
                self._full_check("INITIAL")
                self._state = "ACTIVE"
                self._event("RETAINED_READ_EPOCH_ACTIVE", process_identity=self._process)
                return self.observation()
            except BaseException:
                self._invalidate()
                raise

    def boundary(self, label):
        with self._mutex:
            try:
                self._owner()
                require(self._state == "ACTIVE", "boundary needs live active lease")
                require(isinstance(label, str) and label, "boundary label required")
                self._check_paths()
                self._runtime_check()
                self._check_paths()
                self._event("METADATA_IDENTITY_AND_LIVE_HANDLE_BOUNDARY_PASSED", label=label,
                            new_full_SHA_scan=False, metadata_not_new_byte_equality_proof=True)
                return self.observation()
            except BaseException:
                self._invalidate()
                raise

    @contextmanager
    def publication_guard(self, *, output_paths):
        """Mandatory fresh original full SHA immediately before one publication.

        Only reviewed callers may publish, outside all protected bindings/trees.
        Existing root-handoff replacement must be explicitly excluded before
        session creation, authorized and archived by the existing publisher.
        This layer never releases one protected input to permit publication.
        """
        with self._mutex:
            try:
                self._owner()
                require(self._state == "ACTIVE", "publication requires live active epoch")
                outputs = tuple(str(absolute(p)) for p in output_paths)
                require(outputs and len(outputs) == len({p.casefold() for p in outputs}), "explicit unique output paths required")
                protected_keys = {p.casefold() for p in self.bindings}
                for output in outputs:
                    require(output.casefold() not in protected_keys and all(not absolute(output).is_relative_to(absolute(t.root))
                        and not absolute(t.root).is_relative_to(absolute(output)) for t in self.trees),
                        "publication aliases protected input/tree")
                    # A lexical output outside a tree could otherwise traverse
                    # an unprotected junction into it. Require already-existing
                    # parents and retain each no-reparse directory before yield.
                    # Future publishers must create their exclusive independent
                    # output directories before requesting this guard.
                    for parent in reversed(absolute(output).parents):
                        name = str(parent)
                        require(self.backend.path_exists(name), "publication parent missing; precreate independent output directory")
                        if name not in self._handles:
                            handle = self.backend.open_read(name, directory=True)
                            self._handles[name] = handle
                            self._identities[name] = self.backend.identity(handle)
                    if self.backend.path_exists(output):
                        probe = None
                        try:
                            probe = self.backend.open_read(output, directory=False)
                            self._temporary_handles[probe] = output
                            identity = self.backend.identity(probe)
                            # Includes differently named hardlinks outside a
                            # selected tree. A shared path is never unlocked.
                            require(all(not self.backend.same_file_identity(identity, self._identities[p])
                                for p in self.bindings), "publication hardlink aliases a protected file")
                        finally:
                            if probe is not None:
                                self._close_temporary(probe)
                self._check_paths()
                self._state = "FINAL_FULL_VERIFY"
                self._full_check("FINAL_PREPUBLICATION")
                self._state = "PUBLISHING"
                self._event("PUBLICATION_GUARD_ENTERED", output_paths=list(outputs),
                            original_full_verify_reexecuted=True)
                yield self.observation()
                self._owner()
                self._check_paths()
                self._runtime_check()
                self._event("PUBLICATION_GUARD_EXITED")
                self._state = "SEALED"
            except BaseException:
                self._invalidate()
                raise

    def observation(self):
        """An informational record ONLY, never accepted as a lease/cache token."""
        return {"schema": "paper3-retained-read-validation-observation-v1", "state": self._state,
            "session_nonce": self._nonce, "process_identity": self._process,
            "manifest_digest": self.manifest_digest, "binding_inventory_digest": canonical(dict(self.bindings)),
            "protected_files": len(self.bindings), "retained_handles": len(self._handles),
            "temporary_handles_pending_cleanup": len(self._temporary_handles),
            "original_full_and_complete_SHA_bookends_passed": self._bookend_count,
            "events": json.loads(json.dumps(self._events)),
            "cross_process_reuse_supported": False, "JSON_observation_is_not_a_cache_token": True,
            "boundary_metadata_is_not_new_SHA_equality_proof": True,
            "original_runtime_predicates_required_at_each_boundary": True,
            "native_trust_limits_accepted_not_proven_absent": True,
            "privileged_raw_disk_driver_or_kernel_writers_excluded_from_threat_model": True,
            "special_filesystems_or_write_mapping_bypasses_not_universally_excluded": True,
            "mandatory_final_original_full_SHA": True, "production_pipeline_modified": False,
            "close_errors": list(self._close_errors)}

    def _release(self):
        for failure in self.backend.pending_cleanup():
            self._temporary_handles[failure["handle"]] = failure["path"]
            evidence = {k: v for k, v in failure.items() if k != "handle"}
            if evidence not in self._close_errors:
                self._close_errors.append(evidence)
        for handle in list(self._temporary_handles):
            try:
                self._close_temporary(handle)
            except BaseException:
                pass  # Remains tracked, poisonous and retryable.
        for path, handle in reversed(list(self._handles.items())):
            try:
                self.backend.close(handle)
            except BaseException as error:
                self._close_errors.append({"path": path, "error_type": type(error).__name__, "message": str(error)})
            else:
                self._handles.pop(path, None)
                self._identities.pop(path, None)

    def _invalidate(self):
        self._state = "FAILED"
        self._release()

    def close(self):
        with self._mutex:
            previous = self._state
            self._release()
            self._state = "FAILED" if previous == "FAILED" or self._close_errors else "CLOSED"
            if self._close_errors:
                raise ReuseError("one or more native handles could not be closed; audit close_errors")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, kind, value, trace):
        if kind is not None:
            self._invalidate()
        self.close()
        return False
