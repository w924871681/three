"""Frozen input-only contracts. Importing this module performs no project imports.

LEGACY hashes reproduce core/common.py for finite supported values. New metadata
provenance uses metadata-json-v1: JSON primitives, string-keyed mappings and lists;
NumPy scalars become Python primitives and ndarrays carry a reserved type tag,
dtype.str, shape and row-major nested data. Arrays retain dtype/endian metadata.
Neither function uses a model, checkpoint deserializer or random-number API.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


CENTERS = tuple(range(33000, 33020))
SEEDS = (7311, 7312, 7313)
SCENARIOS = ("C0", "C1", "C3", "C4")
METHODS = [
    ("B0", "B0_Frozen_ratio10"),
    ("B1", "B1_AlwaysMaintainP50_ratio10"),
    ("B2", "B2_RAVM_ratio10"),
    ("B8", "B8_AlwaysOpen_ratio10"),
    ("P7.7", "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"),
]
IDENTITY_FIELDS = (
    "identity_id", "architecture_index", "architecture", "family",
    "source_initialization_id", "checkpoint", "checkpoint_sha256",
    "parameter_count", "operation_count",
)
NATIVE_IDS = (
    "msa_a1_pt", "msa_a6_pt", "msa_a46_pt", "msa_a55_pt",
    "msa_a56_pt", "msa_a57_pt", "msa_a62_pt", "msa_a57_medet",
)
SOURCE_IDS = (
    "p3v2_a57_regime_b", "p3v2_a57_regime_c_control", "p3v2_a46_regime_c",
)
INCUMBENT_ID = "msa_a57_pt"
METADATA_SCHEMA = "paper3-metadata-json-v1"
ARRAY_TAG = "$paper3_ndarray_v1"
LEGACY_ARRAY_DIGEST_ALGORITHM = "sha256-shape-dtype-str-c-contiguous-bytes-v1"
LEGACY_CANONICAL_HASH_ALGORITHM = "sha256-json-sort-compact-utf8-v1"


class ContractError(ValueError):
    """Scientific input contract violation; never corrected automatically."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def _native_json(value: Any) -> Any:
    """Validate JSON-native inputs without importing NumPy or casting values."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractError("non-finite JSON float")
        return value
    if isinstance(value, (list, tuple)):
        return [_native_json(item) for item in value]
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ContractError("JSON mapping keys must be strings")
        return {key: _native_json(item) for key, item in value.items()}
    raise ContractError(f"not a JSON-native value: {type(value).__name__}")


def read_json(path: str | Path) -> Any:
    """Read existing JSON only; reject duplicate keys and non-finite numbers."""
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            value = json.load(
                stream, object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        return _native_json(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"invalid JSON at {path}: {exc}") from exc


def file_sha256(path: str | Path) -> str:
    """Hash bytes by streaming. No file is created or modified."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    """Legacy JSON algorithm, restricted to finite validated JSON values.

    Identical to core/common.py:32-34 for accepted inputs; allow_nan=False adds a
    rejection gate and does not alter bytes for any accepted finite value.
    A provenance fingerprint must pass an explicit schema/context object here.
    """
    payload = json.dumps(
        _native_json(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _checked_array(array: Any) -> Any:
    import numpy as np

    if not isinstance(array, np.ndarray):
        raise ContractError("expected an ndarray; implicit input conversion forbidden")
    if array.dtype.hasobject or array.dtype.fields or array.dtype.subdtype:
        raise ContractError("object, structured and subarray dtype forbidden")
    if array.dtype.kind not in "biuf":
        raise ContractError(f"unsupported numeric dtype: {array.dtype.str}")
    if not bool(np.isfinite(array).all()):
        raise ContractError("non-finite array values")
    return array


def legacy_array_digest(*arrays: Any) -> str:
    """Exactly core/common.py:22-29, with finite numeric input rejection only.

    No dtype/endian conversion, JSON tags, context IDs or new provenance data is
    inserted in this digest. Array order remains significant.
    """
    import numpy as np

    digest = hashlib.sha256()
    for array in arrays:
        value = np.ascontiguousarray(_checked_array(array))
        digest.update(str(value.shape).encode())
        digest.update(value.dtype.str.encode())
        digest.update(value.tobytes())
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    """Deterministic full metadata conversion; never omit unsupported values.

    Array tag collisions in original mapping keys are rejected. NumPy float
    precision above Python's 64-bit representation is rejected rather than
    silently reduced. Signed zero remains preserved by Python JSON encoding.
    """
    if value is None or type(value) in (str, bool, int, float):
        return _native_json(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ContractError("metadata mapping keys must be strings")
        if ARRAY_TAG in value:
            raise ContractError("metadata contains reserved ndarray type tag")
        return {key: jsonable(item) for key, item in value.items()}

    import numpy as np

    if isinstance(value, np.ndarray):
        array = _checked_array(value)
        if array.dtype.kind == "f" and array.dtype.itemsize > 8:
            raise ContractError("extended-precision metadata float forbidden")
        return {
            ARRAY_TAG: True,
            "dtype_str": array.dtype.str,
            "shape": list(array.shape),
            "data": _native_json(array.tolist()),
        }
    if isinstance(value, np.generic):
        if value.dtype.kind not in "biufSU":
            raise ContractError("unsupported metadata scalar")
        if value.dtype.kind == "f" and value.dtype.itemsize > 8:
            raise ContractError("extended-precision metadata scalar forbidden")
        scalar = value.item()
        if isinstance(scalar, bytes):
            raise ContractError("byte-string metadata scalar forbidden")
        return _native_json(scalar)
    raise ContractError(f"unsupported metadata type: {type(value).__name__}")


def stage_spans(stage: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Exact half-open raw-index slices from core/protocol.py:10-17."""
    if type(stage) is not int or not 1 <= stage <= 24:
        raise ContractError(f"stage must be an integer in 1..24: {stage!r}")
    boundary = 1400 + (stage - 1) * 640
    update = (1000, 1400) if stage == 1 else (boundary - 400, boundary)
    return update, (boundary, boundary + 240), (boundary + 240, boundary + 640)


def _inside(repo: Path, relative: str) -> Path:
    path = repo / relative
    try:
        path.resolve().relative_to(repo.resolve())
    except ValueError as exc:
        raise ContractError(f"metadata path resolves outside target repository: {path}") from exc
    return path


def _identity(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or any(key not in item for key in IDENTITY_FIELDS):
        raise ContractError("identity metadata is incomplete")
    result = {key: _native_json(item[key]) for key in IDENTITY_FIELDS}
    for key in ("identity_id", "architecture", "family", "source_initialization_id", "checkpoint"):
        if type(result[key]) is not str or not result[key]:
            raise ContractError(f"identity field {key} must be nonempty text")
    for key in ("architecture_index", "parameter_count", "operation_count"):
        if type(result[key]) is not int or result[key] < (0 if key == "architecture_index" else 1):
            raise ContractError(f"identity field {key} must be a nonnegative index / positive count")
    if not isinstance(result["checkpoint_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", result["checkpoint_sha256"]):
        raise ContractError("invalid declared checkpoint SHA256")
    checkpoint = result["checkpoint"]
    if "\\" in checkpoint or checkpoint.startswith("/") or ":" in checkpoint or ".." in checkpoint.split("/"):
        raise ContractError("checkpoint metadata must be a confined relative POSIX path")
    return result


def identity_bank(repo: str | Path) -> dict[str, Any]:
    """Rebuild exactly nine metadata fields, native8 then source3, without models.

    Reads JSON only. Checkpoint hashes remain manifest declarations, not newly
    verified file-byte hashes; source training/performance fields are excluded.
    Static feasibility is the two <= comparisons from core/models.py:156-157.
    """
    root = Path(repo).resolve()
    paths = (
        "artifacts/p3_model_bank_manifest.json",
        "artifacts/p3_2_source_bank/p3_mismatch_v2_r3/source_training_manifest.json",
        "configs/p3_mismatch_v2_frozen.json",
    )
    native, source, config = [read_json(_inside(root, value)) for value in paths]
    if not all(isinstance(value, dict) for value in (native, source, config)):
        raise ContractError("bank manifests/config must be objects")
    if source.get("generator_revision") != "p3_mismatch_v2_r3" or config.get("generator_revision") != "p3_mismatch_v2_r3":
        raise ContractError("source/config generator revision mismatch")
    native_items = native.get("identities")
    source_items = source.get("assets")
    if not isinstance(native_items, list) or not isinstance(source_items, list):
        raise ContractError("native identities and source assets must be ordered lists")
    native_ids = [_identity(value) for value in native_items]
    source_ids = [_identity(value) for value in source_items]
    if tuple(value["identity_id"] for value in native_ids) != NATIVE_IDS:
        raise ContractError("native eight identities/order changed")
    if tuple(value["identity_id"] for value in source_ids) != SOURCE_IDS:
        raise ContractError("source three identities/order changed")
    if canonical_hash(native_ids) != native.get("bank_hash"):
        raise ContractError("native manifest bank_hash mismatch")
    incumbent = next(value for value in native_ids if value["identity_id"] == INCUMBENT_ID)
    if _identity(source.get("native_incumbent")) != incumbent:
        raise ContractError("source manifest native incumbent metadata mismatch")
    identities = native_ids + source_ids
    limits = config.get("deployment_limits")
    expected_limits = {
        "tight": {"operations": 1500000, "parameters": 30000},
        "medium": {"operations": 5000000, "parameters": 100000},
        "loose": {"operations": 20000000, "parameters": 500000},
    }
    if limits != expected_limits:
        raise ContractError("frozen deployment limits changed")
    for tier_limits in limits.values():
        if any(type(tier_limits[key]) is not int for key in ("parameters", "operations")):
            raise ContractError("deployment limits must be integer counts")
    feasibility: dict[str, Any] = {}
    for tier, tier_limits in limits.items():
        mask = [
            value["parameter_count"] <= tier_limits["parameters"]
            and value["operation_count"] <= tier_limits["operations"]
            for value in identities
        ]
        feasible_ids = [value["identity_id"] for value, keep in zip(identities, mask) if keep]
        feasibility[tier] = {
            "feasible_mask": mask,
            "feasible_ids": feasible_ids,
            "initial_candidate_ids": [value for value in feasible_ids if value != INCUMBENT_ID],
            "deployment_filter_hash": canonical_hash(tier_limits),
        }
    return {
        "identities": identities,
        "bank_hash": canonical_hash(identities),
        "limits_by_tier": limits,
        "feasibility": feasibility,
        "checkpoint_bytes_verified": False,
        "resource_profiling_executed": False,
        "metadata_provenance_schema": METADATA_SCHEMA,
        "source_files": {value: {"path": str(_inside(root, value)), "sha256": file_sha256(_inside(root, value))} for value in paths},
    }


def _describe_array(array: Any) -> dict[str, Any]:
    value = _checked_array(array)
    byteorder = value.dtype.byteorder
    endian = "not-applicable" if byteorder == "|" else sys.byteorder if byteorder == "=" else "little" if byteorder == "<" else "big"
    return {
        "shape": list(value.shape),
        "dtype_str": value.dtype.str,
        "dtype_name": value.dtype.name,
        "endian": endian,
        "c_contiguous": bool(value.flags.c_contiguous),
        "finite": True,
        "legacy_array_digest": legacy_array_digest(value),
    }


def describe_arrays(x: Any, y: Any, ts: Any) -> dict[str, Any]:
    """Shape/dtype/finite/legacy byte summaries; no arrays or RNG are modified."""
    return {
        "arrays": {name: _describe_array(value) for name, value in (("x", x), ("y", y), ("ts", ts))},
        "legacy_array_digest": legacy_array_digest(x, y, ts),
        "legacy_array_digest_algorithm": LEGACY_ARRAY_DIGEST_ALGORITHM,
    }


def check_shapes(x: Any, y: Any, ts: Any, raw_features: int = 24, n: int = 17000) -> None:
    """Validate exact shapes and dtype names without silently coercing endian.

    Endian is recorded by describe_arrays and participates in legacy digest.
    Raw feature count and length are explicit to also validate engineered role
    segments. Timestamp spacing must be strictly positive and constant.
    """
    import numpy as np

    if type(raw_features) is not int or raw_features < 1 or type(n) is not int or n < 2:
        raise ContractError("invalid declared shape contract")
    for value in (x, y, ts):
        _checked_array(value)
    if x.shape != (n, raw_features) or y.shape != (n,) or ts.shape != (n,):
        raise ContractError(f"shape contract violated: {x.shape}, {y.shape}, {ts.shape}")
    if x.dtype.kind != "f" or x.dtype.itemsize != 4 or y.dtype.kind != "f" or y.dtype.itemsize != 4:
        raise ContractError("x/y must be float32; dtype casting forbidden")
    if ts.dtype.kind != "i" or ts.dtype.itemsize != 8:
        raise ContractError("timestamps must be int64; dtype casting forbidden")
    # Python integers avoid int64 subtraction overflow in hostile/corrupt inputs.
    first_gap = int(ts[1]) - int(ts[0])
    if first_gap <= 0 or not bool(np.all(ts[1:] > ts[:-1])):
        raise ContractError("timestamps must be strictly increasing")
    if any(int(ts[index]) - int(ts[index - 1]) != first_gap for index in range(2, n)):
        raise ContractError("timestamps must have constant positive spacing")
