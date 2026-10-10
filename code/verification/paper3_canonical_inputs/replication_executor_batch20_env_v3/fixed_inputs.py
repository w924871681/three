"""Read the published F1 inputs; preserve the frozen causal timeline semantics.

Module import is standard-library only. No generator, model, random-number API,
checkpoint loader or writer is invoked. Authorized callers import the original
BaseCenter/CausalTimeline definitions only when loading an already saved case.
Original segment copies and role-contained windowing are preserved. The audit
records the frozen post-commit offline oracle explicitly rather than treating it
as online data. This guard supplements source/hash audits; it is not a sandbox
against arbitrary access to Python's private attributes.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
import math
import stat
from pathlib import Path
from typing import Any


CENTERS = tuple(range(33000, 33020))
SCENARIOS = ("C0", "C1", "C3", "C4")
ROLES = ("update", "assessment", "service")
F1_BUNDLE_SHA256 = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
DEFINITION_SHA256 = "1e2863758cd5303c7d64457c012ce49d4aef4339781a01bf5869ab41e67f32e5"
DEPENDENCY_SHA256 = "c6735cd6c8c7a0ca8f6c6ec369d6d2222911c3594549f28126853af439d240d6"
SOURCE_PINS = {
    "core/data.py": "6cd7e375d40c8ecf390fe37dee270d93890b3981f666e521e17441612f304d5e",
    "core/protocol.py": "8468b32f245e91c9bcbbb95d93b2dea07b75087d951184fb429cc1f7201cc367",
    "core/common.py": "10c8dcf936e60e6b9b992778310648e258ed5a105d290d09434ba0c968183aaa",
    "scripts/run_p7.py": "51dd05f494ae561858c8de804eb34a4ef0590f69480aae0cc5dbae2baff25494",
    "configs/p3_mismatch_v2_frozen.json": "529655647c1359e2a164cddc3c5c8b534f5cdbad53e2ede29ada477910975646",
}
ARRAY_TAG = "$paper3_ndarray_v1"
FINGERPRINT_SCHEMA = "paper3-canonical-input-fingerprint-v1"
LEGACY_ARRAY_ALGORITHM = "sha256-shape-dtype-str-c-contiguous-bytes-v1"


class FixedInputIntegrityError(RuntimeError):
    """A fixed-input or causal condition failed; never repaired automatically."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FixedInputIntegrityError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise FixedInputIntegrityError(f"non-finite JSON constant: {value}")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    if type(relative) is not str or "\\" in relative:
        raise FixedInputIntegrityError("invalid relative input path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise FixedInputIntegrityError("unsafe relative input path")
    path = root.joinpath(*parts)
    for item in (root, *[root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FixedInputIntegrityError("linked/reparse-point input path forbidden")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise FixedInputIntegrityError("input file escaped publication root")
    return path


def _spans(stage: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    if type(stage) is not int or not 1 <= stage <= 24:
        raise FixedInputIntegrityError("invalid lifecycle stage")
    boundary = 1400 + (stage - 1) * 640
    return ((1000, 1400) if stage == 1 else (boundary - 400, boundary),
            (boundary, boundary + 240), (boundary + 240, boundary + 640))


def _legacy_digest(*arrays: Any) -> str:
    import numpy as np

    result = hashlib.sha256()
    for array in arrays:
        if not isinstance(array, np.ndarray) or array.dtype.hasobject or array.dtype.kind not in "biuf":
            raise FixedInputIntegrityError("non-numeric fixed array")
        value = np.ascontiguousarray(array)
        if not bool(np.isfinite(value).all()):
            raise FixedInputIntegrityError("non-finite fixed array")
        result.update(str(value.shape).encode())
        result.update(value.dtype.str.encode())
        result.update(value.tobytes())
    return result.hexdigest()


def _fingerprint(kind: str, bundle: dict[str, Any], payload: dict[str, Any]) -> str:
    return _json_hash({"schema": FINGERPRINT_SCHEMA, "kind": kind, "context": "F",
                       "definition_digest": bundle["definition_digest"],
                       "dependency_digest": bundle["dependency_digest"], "payload": payload})


def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items()
            if key not in ("provenance_fingerprint", "files", "source_files")}


def _restore_metadata(value: Any) -> Any:
    """Restore only the documented array tag, keeping its dtype and shape."""
    import numpy as np

    if isinstance(value, dict):
        if ARRAY_TAG in value:
            if value[ARRAY_TAG] is not True or set(value) != {ARRAY_TAG, "dtype_str", "shape", "data"}:
                raise FixedInputIntegrityError("invalid typed metadata array")
            dtype = np.dtype(value["dtype_str"])
            if dtype.hasobject or dtype.fields or dtype.subdtype or dtype.kind not in "biuf":
                raise FixedInputIntegrityError("unsafe metadata dtype")
            if dtype.str != value["dtype_str"]:
                raise FixedInputIntegrityError("metadata dtype representation changed")
            array = np.array(value["data"], dtype=dtype)
            if list(array.shape) != value["shape"] or not bool(np.isfinite(array).all()):
                raise FixedInputIntegrityError("metadata shape/finite contract failed")
            array.flags.writeable = False
            return array
        return {key: _restore_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_metadata(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise FixedInputIntegrityError("unknown serialized metadata value")


def _check_array(array: Any, description: dict[str, Any], shape: tuple[int, ...]) -> None:
    import numpy as np

    if (not isinstance(array, np.ndarray) or array.dtype.hasobject or array.dtype.fields
            or array.dtype.subdtype or array.dtype.kind not in "biuf"):
        raise FixedInputIntegrityError("unsafe fixed array dtype")
    if (array.shape != shape or list(array.shape) != description["shape"]
            or array.dtype.str != description["dtype_str"] or array.dtype.name != description["dtype_name"]
            or bool(array.flags.c_contiguous) != description["c_contiguous"]
            or description["finite"] is not True or array.flags.writeable):
        raise FixedInputIntegrityError("fixed array shape/dtype/layout/read-only contract failed")
    if _legacy_digest(array) != description["legacy_array_digest"]:
        raise FixedInputIntegrityError("fixed array legacy digest differs")


def _check_triplet(x: Any, y: Any, ts: Any, description: dict[str, Any], n: int, features: int) -> str:
    if description["legacy_array_digest_algorithm"] != LEGACY_ARRAY_ALGORITHM:
        raise FixedInputIntegrityError("legacy digest definition changed")
    for name, value, shape in (("x", x, (n, features)), ("y", y, (n,)), ("ts", ts, (n,))):
        _check_array(value, description["arrays"][name], shape)
    digest = _legacy_digest(x, y, ts)
    if digest != description["legacy_array_digest"]:
        raise FixedInputIntegrityError("combined legacy input digest differs")
    return digest


class FixedInputStore:
    """One publication verification per worker; one selected-case check per load."""

    def __init__(self, repo: Path, verification_run_root: Path):
        from .provenance import verify_stage_b

        self.repo = Path(repo).resolve(strict=True)
        self.verification_run_root = Path(verification_run_root).resolve(strict=True)
        verified = verify_stage_b(self.repo, self.verification_run_root)
        self.publication = verified
        self.bundle = copy.deepcopy(verified["F1"])
        self.bank = copy.deepcopy(verified["bank"])
        self.file_bindings = dict(verified["file_bindings"])
        self.source_bindings = dict(verified["source_environment"]["sources"])
        self.source_bindings.update(SOURCE_PINS)
        self._loaded_cases: list[dict[str, Any]] = []
        for relative, expected in SOURCE_PINS.items():
            if _file_hash(_safe_path(self.repo, relative)) != expected:
                raise FixedInputIntegrityError(f"original dependency changed: {relative}")
        self._verify_bundle()
        frozen = _read_json(_safe_path(self.repo, "configs/p3_mismatch_v2_frozen.json"))
        if frozen["deployment_limits"] != self.bank["limits_by_tier"]:
            raise FixedInputIntegrityError("published bank limits differ from original frozen limits")
        if len(self.bank["identities"]) != 11 or _json_hash(self.bank["identities"]) != self.bank["bank_hash"]:
            raise FixedInputIntegrityError("published identity bank metadata differs")
        self._verify_deployments()

    def _verify_bundle(self) -> None:
        bundle = self.bundle
        if (bundle["context"] != "F" or bundle["replicate"] != "F1"
                or bundle["definition_digest"] != DEFINITION_SHA256
                or bundle["dependency_digest"] != DEPENDENCY_SHA256
                or bundle["input_bundle_digest"] != F1_BUNDLE_SHA256):
            raise FixedInputIntegrityError("selected canonical F1 binding changed")
        keys = {
            "base": {str(c) for c in CENTERS},
            "scenarios": {f"{c}/{s}" for c in CENTERS for s in SCENARIOS},
            "roles": {f"{c}/{s}/{t}/{r}" for c in CENTERS for s in SCENARIOS
                      for t in range(1, 25) for r in ROLES},
            "references": {f"{c}/{s}/{r}" for c in CENTERS for s in SCENARIOS for r in ("warmup", "reference")},
        }
        kinds = {"base": "base", "scenarios": "scenario", "roles": "stage_role", "references": "reference"}
        for group, expected_keys in keys.items():
            if set(bundle[group]) != expected_keys:
                raise FixedInputIntegrityError(f"incomplete canonical inventory: {group}")
            for key, entry in bundle[group].items():
                if _fingerprint(kinds[group], bundle, _entry_payload(entry)) != entry["provenance_fingerprint"]:
                    raise FixedInputIntegrityError(f"canonical fingerprint differs: {group}/{key}")
        payload = {"context": "F", "resolved_config": bundle["resolved_config"], "bank_hash": self.bank["bank_hash"]}
        payload.update({group: {key: entry["provenance_fingerprint"] for key, entry in bundle[group].items()}
                        for group in keys})
        if _fingerprint("input_bundle", bundle, payload) != F1_BUNDLE_SHA256:
            raise FixedInputIntegrityError("canonical F1 bundle fingerprint differs")

    def _verify_deployments(self) -> None:
        bank = self.bank
        ids = [entry["identity_id"] for entry in bank["identities"]]
        if len(set(ids)) != 11:
            raise FixedInputIntegrityError("duplicate identity in published bank")
        for tier, limits in bank["limits_by_tier"].items():
            feasible = [entry["parameter_count"] <= limits["parameters"]
                        and entry["operation_count"] <= limits["operations"] for entry in bank["identities"]]
            available = [identity for identity, ok in zip(ids, feasible) if ok]
            expected = bank["feasibility"][tier]
            if (expected["feasible_mask"] != feasible or expected["feasible_ids"] != available
                    or expected["initial_candidate_ids"] != [identity for identity in available if identity != "msa_a57_pt"]
                    or expected["deployment_filter_hash"] != _json_hash(limits)):
                raise FixedInputIntegrityError("published feasibility metadata differs from frozen resource filter")
        for center in CENTERS:
            entry = self.bundle["base"][str(center)]
            profile = entry["profile"]
            tier = profile["budget_tier"]
            expected = {**bank["feasibility"][tier], "bank_hash": bank["bank_hash"], "limits": bank["limits_by_tier"][tier]}
            if (entry["deployment"] != expected or profile["center_id"] != center
                    or entry["profile_digest"] != _json_hash(profile)):
                raise FixedInputIntegrityError("canonical center deployment/profile binding differs")

    def _bound_file(self, relative: str) -> Path:
        if relative not in self.file_bindings:
            raise FixedInputIntegrityError("selected file absent from publication bindings")
        path = _safe_path(self.verification_run_root, relative)
        if _file_hash(path) != self.file_bindings[relative]:
            raise FixedInputIntegrityError(f"selected published file changed: {relative}")
        return path

    def expected_role(self, center: int, scenario: str, stage: int, role: str) -> dict[str, Any]:
        if type(center) is not int or center not in CENTERS or scenario not in SCENARIOS or role not in ROLES:
            raise FixedInputIntegrityError("unknown selected role")
        _spans(stage)
        return copy.deepcopy(self.bundle["roles"][f"{center}/{scenario}/{stage}/{role}"])

    def load(self, center: int, scenario: str) -> tuple[Any, Any, dict[str, Any], str]:
        """Load existing arrays only, validate the entire selected-case inventory."""
        import numpy as np

        if type(center) is not int or center not in CENTERS or scenario not in SCENARIOS:
            raise FixedInputIntegrityError("unknown canonical center/scenario")
        base_entry = self.bundle["base"][str(center)]
        scene = self.bundle["scenarios"][f"{center}/{scenario}"]
        base_arrays = {name: np.load(self._bound_file(relative), mmap_mode="r", allow_pickle=False)
                       for name, relative in base_entry["files"].items()}
        arrays = {name: np.load(self._bound_file(relative), mmap_mode="r", allow_pickle=False)
                  for name, relative in scene["files"].items()}
        if set(base_arrays) != {"x", "y", "ts"} or set(arrays) != {"x", "y", "ts", "feature_x"}:
            raise FixedInputIntegrityError("selected array roles differ")
        base_hash = _check_triplet(base_arrays["x"], base_arrays["y"], base_arrays["ts"], base_entry["arrays"], 17000, 24)
        scene_hash = _check_triplet(arrays["x"], arrays["y"], arrays["ts"], scene["arrays"], 17000, 24)
        _check_triplet(arrays["feature_x"], arrays["y"], arrays["ts"], scene["feature_arrays"], 17000, 25)
        if base_hash != base_entry["legacy_array_digest"] or scene_hash != scene["legacy_scenario_hash"]:
            raise FixedInputIntegrityError("selected legacy hash binding differs")
        profile_relative = f"inputs/F1/center_{center}/base/profile.json"
        metadata_relative = f"inputs/F1/center_{center}/scenario_{scenario}/metadata.json"
        profile = _read_json(self._bound_file(profile_relative))
        metadata = _read_json(self._bound_file(metadata_relative))
        if profile != base_entry["profile"] or metadata != scene["metadata"]:
            raise FixedInputIntegrityError("selected profile/scenario metadata changed")
        dt = profile["dt"]
        if type(dt) is not int or dt not in {"A": (1,), "B": (1, 2), "C": (2, 3, 4)}[profile["center_type"]]:
            raise FixedInputIntegrityError("center time interval differs from frozen type")
        if (not np.array_equal(base_arrays["ts"], 8 + np.arange(17000, dtype=np.int64) * dt)
                or not np.array_equal(arrays["ts"], base_arrays["ts"])
                or not np.array_equal(arrays["feature_x"][:, :24], arrays["x"])
                or arrays["feature_x"].dtype.str != "<f4"
                or not bool(np.all(arrays["feature_x"][:, 24] == np.float32(dt / 4.0)))):
            raise FixedInputIntegrityError("saved feature/timestamp definition differs")
        role_entries: dict[tuple[int, str], dict[str, Any]] = {}
        for stage in range(1, 25):
            spans = _spans(stage)
            for role, span in zip(ROLES, spans):
                entry = self.expected_role(center, scenario, stage, role)
                self._check_segment_entry(entry, arrays, scene, span)
                if (entry["stage"] != stage or entry["role"] != role
                        or entry["update_end_ts"] != int(arrays["ts"][spans[0][1] - 1])
                        or entry["decision_ts"] != int(arrays["ts"][spans[1][1] - 1])):
                    raise FixedInputIntegrityError("stage role/timing binding differs")
                role_entries[(stage, role)] = entry
        references = {}
        for role, span in (("warmup", (0, 800)), ("reference", (800, 1000))):
            entry = copy.deepcopy(self.bundle["references"][f"{center}/{scenario}/{role}"])
            self._check_segment_entry(entry, arrays, scene, span)
            a, b = span
            raw_digest = _check_triplet(arrays["x"][a:b], arrays["y"][a:b], arrays["ts"][a:b], entry["raw_arrays"], b - a, 24)
            if (entry["role"] != role or raw_digest != entry["raw_legacy_array_digest"]
                    or entry["feature_arrays"] != entry["arrays"]
                    or entry["feature_legacy_array_digest"] != entry["legacy_role_hash"]):
                raise FixedInputIntegrityError("initial input/reference binding differs")
            references[role] = entry
        for relative, expected in SOURCE_PINS.items():
            if _file_hash(_safe_path(self.repo, relative)) != expected:
                raise FixedInputIntegrityError("original timeline dependency changed before load")
        from .provenance import require_authorized_execution
        require_authorized_execution(self.repo, self.verification_run_root)
        # Imports expose frozen data containers and timeline code only; no function
        # that generates inputs, calls a model, or sets a random seed is invoked.
        data_module = importlib.import_module("core.data")
        protocol_module = importlib.import_module("core.protocol")
        for module, relative in ((data_module, "core/data.py"), (protocol_module, "core/protocol.py")):
            if Path(module.__file__).resolve() != _safe_path(self.repo, relative).resolve():
                raise FixedInputIntegrityError("original container imported from a different repository")
        base = data_module.BaseCenter(center_id=center, center_type=profile["center_type"],
                                      budget_tier=profile["budget_tier"], dt=dt,
                                      x=base_arrays["x"], y=base_arrays["y"], ts=base_arrays["ts"],
                                      metadata=_restore_metadata(profile["metadata"]))
        timeline_type = _audit_timeline_type(protocol_module.CausalTimeline)
        timeline = timeline_type(arrays["feature_x"], arrays["y"], arrays["ts"], scenario, center,
                                 roles=role_entries, references=references,
                                 diagnostic_path=_safe_path(self.repo, "scripts/run_p7.py"))
        self._loaded_cases.append({"center_id": center, "scenario": scenario,
                                   "scenario_hash": scene_hash, "selected_input_checks_passed": True})
        return base, timeline, _restore_metadata(metadata), scene_hash

    def _check_segment_entry(self, entry: dict[str, Any], arrays: dict[str, Any], scene: dict[str, Any], span: tuple[int, int]) -> None:
        a, b = span
        digest = _check_triplet(arrays["feature_x"][a:b], arrays["y"][a:b], arrays["ts"][a:b], entry["arrays"], b - a, 25)
        if (entry["span"] != [a, b] or entry["legacy_role_hash"] != digest
                or entry["raw_count"] != b - a or entry["window_length"] != 96
                or entry["window_count"] != b - a - 96
                or entry["start_ts"] != int(arrays["ts"][a]) or entry["end_ts"] != int(arrays["ts"][b - 1])
                or entry["source_files"] != scene["files"]
                or entry["scenario_provenance_fingerprint"] != scene["provenance_fingerprint"]):
            raise FixedInputIntegrityError("selected segment inventory differs")

    def integrity(self) -> dict[str, Any]:
        return {"input_bundle_digest": self.bundle["input_bundle_digest"],
                "definition_digest": self.bundle["definition_digest"], "dependency_digest": self.bundle["dependency_digest"],
                "publication_verified_once": True, "selected_case_checks": copy.deepcopy(self._loaded_cases),
                "generation_performed": False, "source_bindings": dict(self.source_bindings),
                "initial_model_state_certification": "SEPARATE_STAGE_C_PREFLIGHT_REQUIRED"}


def _audit_timeline_type(original_type: type) -> type:
    """Build the subclass lazily; importing this file never imports the project."""

    class AuditedTimeline(original_type):
        def __init__(self, x: Any, y: Any, ts: Any, scenario: str, center_id: int, *, roles: dict,
                     references: dict, diagnostic_path: Path):
            super().__init__(x, y, ts, scenario, center_id)
            self._audit_roles = roles
            self._audit_references = references
            self._audit_diagnostic_path = str(diagnostic_path.resolve())
            self._audit_phase = "INITIAL"
            self._audit_stage = 0
            self._audit_next_stage = 1
            self._audit_permission: tuple[tuple[int, int], str, dict, str] | None = None
            self._audit_events: list[dict[str, Any]] = []
            self._audit_violations: list[str] = []

        def _deny(self, reason: str) -> None:
            self._audit_violations.append(reason)
            raise FixedInputIntegrityError(reason)

        def _event(self, kind: str, **fields: Any) -> None:
            self._audit_events.append({"sequence": len(self._audit_events), "kind": kind,
                                       "current_stage": self._audit_stage, "phase": self._audit_phase, **fields})

        def _diagnostic_stage(self) -> int | None:
            # Require the unchanged frozen diagnostic's actual Python frame, not
            # just oracle_mode=True or a caller-supplied marker. The source bytes
            # are bound before the container/timeline is made.
            frame = inspect.currentframe()
            try:
                frame = frame.f_back if frame is not None else None
                while frame is not None:
                    if (frame.f_code.co_name == "offline_labels"
                            and str(Path(frame.f_code.co_filename).resolve()) == self._audit_diagnostic_path
                            and frame.f_locals.get("timeline") is self):
                        stage = frame.f_locals.get("stage")
                        return stage if type(stage) is int else None
                    frame = frame.f_back
                return None
            finally:
                del frame

        def _read_original(self, bounds: tuple[int, int], role: str, entry: dict, purpose: str) -> Any:
            previous = self._audit_permission
            self._audit_permission = (bounds, role, entry, purpose)
            try:
                return self._segment(bounds, role)
            finally:
                self._audit_permission = previous

        def _segment(self, bounds: tuple[int, int], role: str) -> Any:
            permission = self._audit_permission
            if permission is None:
                if self._audit_phase != "INITIAL" or tuple(bounds) != (800, 1000) or role != "assessment":
                    self._deny("direct segment access outside initial fixed reference")
                entry = self._audit_references["reference"]
                purpose = "initial_reference"
            else:
                allowed_bounds, allowed_role, entry, purpose = permission
                if tuple(bounds) != allowed_bounds or role != allowed_role:
                    self._deny("segment role/span differs from authorized causal call")
            result = super()._segment(bounds, role)
            if result.hash != entry["legacy_role_hash"] or result.role != role:
                self._deny("original returned segment differs from fixed input inventory")
            self._event("segment", purpose=purpose, role=role, span=list(bounds), legacy_hash=result.hash,
                        requested_stage=entry.get("stage"), current_decision_sealed=self._audit_stage in self._decisions)
            return result

        def warmup(self) -> Any:
            if self._audit_phase != "INITIAL":
                self._deny("warmup input access after lifecycle decision began")
            return self._read_original((0, 800), "warmup", self._audit_references["warmup"], "initial_warmup")

        def decision_data(self, stage: int) -> tuple[Any, Any]:
            spans = _spans(stage)
            diagnostic = self._diagnostic_stage()
            if diagnostic is not None:
                if (diagnostic != self._audit_stage or stage != diagnostic or self._audit_phase != "SERVICED"
                        or diagnostic not in self._decisions):
                    self._deny("offline diagnostic decision data accessed before current commit/service")
                purpose = "offline_diagnostic_after_commit"
            else:
                if stage != self._audit_next_stage or self._audit_phase not in ("INITIAL", "SERVICED"):
                    self._deny("online decision input order/stage differs from frozen sequence")
                self._audit_stage = stage
                self._audit_phase = "DECISION_READ"
                purpose = "online_decision"
            return (self._read_original(spans[0], "update", self._audit_roles[(stage, "update")], purpose),
                    self._read_original(spans[1], "assessment", self._audit_roles[(stage, "assessment")], purpose))

        def seal_decision(self, stage: int) -> None:
            _spans(stage)
            if stage != self._audit_stage or self._audit_phase != "DECISION_READ" or stage in self._decisions:
                self._deny("commit seal does not follow current online decision inputs")
            super().seal_decision(stage)
            self._audit_phase = "SEALED"
            self._event("decision_sealed", stage=stage)

        def service(self, stage: int) -> Any:
            if stage != self._audit_stage or self._audit_phase != "SEALED" or stage not in self._decisions:
                self._deny("online service access before current decision seal or repeated service")
            result = self._read_original(_spans(stage)[2], "service", self._audit_roles[(stage, "service")], "online_service_after_commit")
            self._audit_phase = "SERVICED"
            self._audit_next_stage = stage + 1
            self._event("service_returned", stage=stage)
            return result

        def offline_service(self, stage: int, *, oracle_mode: bool) -> Any:
            _spans(stage)
            diagnostic = self._diagnostic_stage()
            if (oracle_mode is not True or diagnostic != self._audit_stage or self._audit_phase != "SERVICED"
                    or self._audit_stage not in self._decisions
                    or not self._audit_stage <= stage <= min(24, self._audit_stage + 3)):
                self._deny("future service access outside sealed frozen offline diagnostic")
            return self._read_original(_spans(stage)[2], "offline_oracle_service", self._audit_roles[(stage, "service")],
                                       "offline_oracle_after_commit")

        def get_access_evidence(self) -> dict[str, Any]:
            return {"schema": "paper3-fixed-input-causal-access-v1", "center_id": self.center_id,
                    "scenario": self.scenario, "violation_count": len(self._audit_violations),
                    "violations": list(self._audit_violations), "events": copy.deepcopy(self._audit_events),
                    "completed_stages": self._audit_next_stage - 1, "phase": self._audit_phase,
                    "offline_oracle_policy": "exact_frozen_offline_labels_after_current_seal_and_service",
                    "scope": "guarded_timeline_access_plus_separately_bound_frozen_source"}

    AuditedTimeline.__name__ = "FixedInputAuditedCausalTimeline"
    return AuditedTimeline
