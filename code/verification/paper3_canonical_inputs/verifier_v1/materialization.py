"""Input-only materialization, dormant until an explicitly authorized invocation.

No repository module is imported. Runtime extraction uses exact hash-pinned AST
definitions in four isolated namespaces. It omits imports, module-level CFG and
all teacher/model/timeline/target-statistics functions. NumPy is imported lazily
after all extracted source bytes and AST call surfaces have passed validation.
This module has no command-line entry point and creates no files on import.

F1/F2 use one ordered twenty-center call. S1 uses ascending singleton calls and
S2 descending singleton calls. Replicate labels, process metadata and file paths
are excluded from scientific fingerprints; F/S contexts remain distinct even
if their array bytes happen to match.
"""
from __future__ import annotations

import ast
import builtins
import dataclasses
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import contract


EXTRACTED_SOURCE_PINS = {
    "imported/ravm_dt/main_cfg.py":
        "fea128a2649301017a2a8ad6cab3db30392e180c2f3aa1216e9a83fefcd5d005",
    "imported/ravm_dt/sim.py":
        "930fa8ebe34a442d53af16a054955580f2d0c41ef2514a3cfd125b0e6905883d",
    "core/data.py":
        "6cd7e375d40c8ecf390fe37dee270d93890b3981f666e521e17441612f304d5e",
    "core/p3_2_data.py":
        "0f5a5bff889a0ac866793dc49b21680f927af13c9e6fc3d5c3d75bbf4d9d5b27",
}
MISMATCH_CONFIG_PIN = "529655647c1359e2a164cddc3c5c8b534f5cdbad53e2ede29ada477910975646"
N_HISTORY = 17000
DATA_SEED = 7311
WINDOW_LENGTH = 96
ONSET_RAW_INDEX = 6520
FINGERPRINT_SCHEMA = "paper3-canonical-input-fingerprint-v1"

_SELECTED = {
    "imported/ravm_dt/main_cfg.py": (
        "CenterTypeCfg", "MissingBlockCfg", "SimDataCfg", "TaskCfg", "BudgetTier",
        "BudgetCfg", "ArchSpaceCfg", "SearchBudgetCfg", "SplitCfg", "MainCfg",
    ),
    "imported/ravm_dt/sim.py": (
        "CenterData", "_sigmoid", "_sample_budget_tier", "_make_type_schedule",
        "_generate_latent_workload", "_generate_clean_metrics",
        "_apply_monitoring_missingness", "simulate_centers",
    ),
    "core/data.py": (
        "BaseCenter", "feature_matrix", "generate_base_centers", "_logit",
        "_sigmoid", "_physical_shift",
    ),
    "core/p3_2_data.py": (
        "apply_c3_regime_b", "c4_target", "make_scenario_v2",
    ),
}
_SAFE_BUILTIN_NAMES = (
    "__build_class__", "object", "property", "ValueError", "bool", "int",
    "float", "str", "dict", "list", "tuple", "set", "len", "range",
    "enumerate", "min", "max", "abs", "any", "sorted", "getattr",
)
_SAFE_NP_CALLS = {
    "np.clip", "np.exp", "np.asarray", "np.arange", "np.sin", "np.zeros",
    "np.empty_like", "np.log", "np.flatnonzero", "np.ones",
    "np.random.RandomState", "np.concatenate", "np.full", "np.repeat",
    "np.tanh", "np.zeros_like", "np.any",
}
_SAFE_RNG_METHODS = {"choice", "shuffle", "uniform", "normal", "poisson", "rand", "randint"}
_SAFE_VALUE_METHODS = {"astype", "copy", "sum", "tolist", "mean", "append", "extend", "update"}


def _attribute_path(value: ast.AST) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        parent = _attribute_path(value.value)
        return f"{parent}.{value.attr}" if parent is not None else None
    return None


def _inside(repo: Path, relative: str) -> Path:
    path = repo / relative
    try:
        path.resolve(strict=True).relative_to(repo.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise contract.ContractError(f"extracted source is missing or outside target repo: {path}") from exc
    return path


def _audit_node(node: ast.AST, allowed_names: set[str]) -> None:
    """Fail closed on imports, dynamic evaluation, global writes and unknown calls.

    Exact immutable source pins provide the trust boundary. This call-surface
    audit is additional defense, not a general sandbox for arbitrary Python.
    """
    for item in ast.walk(node):
        if isinstance(item, (
            ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.With,
            ast.AsyncWith, ast.AsyncFunctionDef, ast.Await, ast.Yield,
            ast.YieldFrom,
        )):
            raise contract.ContractError(f"forbidden AST node in pure extraction: {type(item).__name__}")
        if isinstance(item, ast.Attribute) and item.attr.startswith("__"):
            raise contract.ContractError("dunder attribute access forbidden in pure extraction")
        if not isinstance(item, ast.Call):
            continue
        function = item.func
        if isinstance(function, ast.Name):
            if function.id not in allowed_names:
                raise contract.ContractError(f"unknown extracted call: {function.id}")
        elif isinstance(function, ast.Attribute):
            text = ast.unparse(function)
            path = _attribute_path(function)
            if path is not None and path.startswith("np."):
                if path not in _SAFE_NP_CALLS:
                    raise contract.ContractError(f"unknown NumPy extracted call: {text}")
            elif isinstance(function.value, ast.Name) and function.value.id in {"rng", "rng0"}:
                if function.attr not in _SAFE_RNG_METHODS:
                    raise contract.ContractError(f"unknown local RNG call: {text}")
            elif function.attr not in _SAFE_VALUE_METHODS:
                raise contract.ContractError(f"unknown extracted value method: {text}")
        else:
            raise contract.ContractError("computed/dynamic call target forbidden")


def _selected_ast(source: bytes, relative: str) -> ast.Module:
    """Parse exact definitions without executing the original module body."""
    tree = ast.parse(source, filename=relative)
    expected = _SELECTED[relative]
    nodes: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in expected:
            if node.name in nodes:
                raise contract.ContractError(f"duplicate selected source definition: {node.name}")
            nodes[node.name] = node
    if tuple(nodes) != expected:
        raise contract.ContractError(f"selected definition names/order changed in {relative}")
    selected = list(nodes.values())
    if relative == "core/p3_2_data.py":
        constants = [
            node for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "ONSET_RAW_INDEX"
        ]
        if len(constants) != 1:
            raise contract.ContractError("scenario onset definition missing/duplicated")
        for item in ast.walk(constants[0].value):
            if not isinstance(item, (ast.BinOp, ast.Constant, ast.Add, ast.Mult, ast.Load)):
                raise contract.ContractError("scenario onset is not a pure literal arithmetic expression")
        selected.insert(0, constants[0])
    allowed_names = set(_SAFE_BUILTIN_NAMES) | {
        "dataclass", "field", "CenterTypeCfg", "BudgetTier", "MainCfg", "BaseCenter",
        "simulate_centers", "_logit", "_sigmoid", "_physical_shift",
    } | set(expected)
    for node in selected:
        _audit_node(node, allowed_names)
    # Future imports are intentionally omitted and inheritance disabled at compile.
    # Dataclass annotations therefore resolve to actual types without registering
    # a fabricated project module in sys.modules.
    return ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))


def _namespace(name: str, np: Any, **extra: Any) -> dict[str, Any]:
    safe_builtins = {key: getattr(builtins, key) for key in _SAFE_BUILTIN_NAMES}
    # NumPy ndarray.mean/sum call the caller's builtin importer at the C level
    # for this exact internal helper, even when NumPy is already imported.
    # This is not added to AST allowed call names: explicit source imports and
    # explicit __import__ calls remain forbidden. Runtime import resolution is
    # also protected by the reviewed exact-file BoundImportGuard preflight.
    safe_builtins["__import__"] = _numpy_method_import
    return {
        "__name__": name,
        "__builtins__": safe_builtins,
        "np": np,
        "dataclass": dataclasses.dataclass,
        "field": dataclasses.field,
        "Any": Any, "Dict": Dict, "List": List, "Optional": Optional,
        "Sequence": Sequence, "Tuple": Tuple,
        **extra,
    }


def _numpy_method_import(name: str, globals: Any = None, locals: Any = None,
                         fromlist: Any = (), level: int = 0) -> Any:
    """Allow only the observed implicit ndarray reduction import request."""
    if name != "numpy._core._methods" or level != 0 or fromlist not in ((), [], None):
        raise contract.ContractError(f"forbidden implicit extracted import: {name}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def load_pure_runtime(repo: Path, source_pins: dict[str, str]) -> dict[str, Any]:
    """Only an authorized materialization caller may invoke this function."""
    if any(source_pins.get(key) != value for key, value in EXTRACTED_SOURCE_PINS.items()):
        raise contract.ContractError("root source pins disagree with reviewed extraction pins")
    units: dict[str, ast.Module] = {}
    for relative, digest in EXTRACTED_SOURCE_PINS.items():
        source = _inside(repo, relative).read_bytes()
        if hashlib.sha256(source).hexdigest() != digest:
            raise contract.ContractError(f"immutable extracted source SHA256 changed: {relative}")
        units[relative] = _selected_ast(source, relative)

    import numpy as np

    cfg = _namespace("paper3_civ_cfg_extracted", np)
    sim = _namespace("paper3_civ_sim_extracted", np)
    for relative, namespace in (
        ("imported/ravm_dt/main_cfg.py", cfg),
        ("imported/ravm_dt/sim.py", sim),
    ):
        exec(compile(units[relative], relative, "exec", dont_inherit=True), namespace)
    data = _namespace(
        "paper3_civ_data_extracted", np,
        MainCfg=cfg["MainCfg"], simulate_centers=sim["simulate_centers"],
    )
    exec(compile(units["core/data.py"], "core/data.py", "exec", dont_inherit=True), data)
    scene = _namespace(
        "paper3_civ_scenario_extracted", np,
        BaseCenter=data["BaseCenter"], _logit=data["_logit"],
        _sigmoid=data["_sigmoid"], _physical_shift=data["_physical_shift"],
    )
    exec(compile(units["core/p3_2_data.py"], "core/p3_2_data.py", "exec", dont_inherit=True), scene)
    if scene["ONSET_RAW_INDEX"] != ONSET_RAW_INDEX:
        raise contract.ContractError("scenario onset differs from reviewed contract")
    return {
        "np": np, "MainCfg": cfg["MainCfg"],
        "generate_base_centers": data["generate_base_centers"],
        "feature_matrix": data["feature_matrix"],
        "make_scenario_v2": scene["make_scenario_v2"],
        "extracted_source_sha256": dict(EXTRACTED_SOURCE_PINS),
    }


def _resolved_config(runtime: dict[str, Any]) -> dict[str, Any]:
    default = runtime["MainCfg"]()
    default_values = contract.jsonable(dataclasses.asdict(default))
    actual = runtime["MainCfg"]()
    actual.sim.seed = DATA_SEED
    actual.sim.n_history = N_HISTORY
    for kind in "ABC":
        getattr(actual.sim, f"type_{kind}").drift_prob = 0.0
    if tuple(actual.sim.type_ratio) != (3, 4, 3) or actual.sim.k_max != 12:
        raise contract.ContractError("reviewed MainCfg population defaults changed")
    return {
        "default_MainCfg": default_values,
        "resolved_MainCfg": contract.jsonable(dataclasses.asdict(actual)),
        "derived_sim_max_dt": int(actual.sim.max_dt),
        "data_seed": DATA_SEED, "n_history": N_HISTORY,
        "onset_raw_index": ONSET_RAW_INDEX,
        "feature_definition": "feature_matrix raw24 float32 + float32(dt/4), no normalization",
        "source_sha256": dict(EXTRACTED_SOURCE_PINS),
    }


def _deployment(bank: dict[str, Any], tier: str) -> dict[str, Any]:
    if tier not in bank["limits_by_tier"] or tier not in bank["feasibility"]:
        raise contract.ContractError(f"unknown deployment tier: {tier}")
    feasibility = bank["feasibility"][tier]
    result = {
        "limits": bank["limits_by_tier"][tier],
        "deployment_filter_hash": feasibility["deployment_filter_hash"],
        "bank_hash": bank["bank_hash"],
        "feasible_mask": feasibility["feasible_mask"],
        "feasible_ids": feasibility["feasible_ids"],
        "initial_candidate_ids": feasibility["initial_candidate_ids"],
    }
    if contract.canonical_hash(result["limits"]) != result["deployment_filter_hash"]:
        raise contract.ContractError("deployment limits/hash mismatch")
    return contract.jsonable(result)


def _fingerprint(kind: str, context: str, definition_digest: str, dependency_digest: str, payload: dict[str, Any]) -> str:
    return contract.canonical_hash({
        "schema": FINGERPRINT_SCHEMA, "kind": kind, "context": context,
        "definition_digest": definition_digest,
        "dependency_digest": dependency_digest,
        "payload": payload,
    })


def _base_contract(base: Any, expected_id: int, runtime: dict[str, Any]) -> None:
    np = runtime["np"]
    if type(base.center_id) is not int or base.center_id != expected_id:
        raise contract.ContractError("generator returned wrong center ID/order")
    if base.center_type not in {"A", "B", "C"} or base.budget_tier not in {"tight", "medium", "loose"}:
        raise contract.ContractError("unknown type/tier")
    if type(base.dt) is not int or base.dt not in getattr(runtime["MainCfg"]().sim, f"type_{base.center_type}").dt_choices:
        raise contract.ContractError("dt is not the frozen center-type choice")
    contract.check_shapes(base.x, base.y, base.ts)
    expected_ts = 8 + np.arange(N_HISTORY, dtype=np.int64) * base.dt
    if not np.array_equal(base.ts, expected_ts):
        raise contract.ContractError("timestamp mapping differs from 8 + raw_index*dt")
    if not bool(np.all((base.x[:, 12:] == 0) | (base.x[:, 12:] == 1))):
        raise contract.ContractError("base masks are not binary")
    if not bool(np.all((base.x >= 0) & (base.x <= 1))) or not bool(np.all((base.y >= 0) & (base.y <= 1))):
        raise contract.ContractError("base telemetry/target outside generator bounds")
    if base.metadata.get("center_type") != base.center_type or base.metadata.get("dt") != base.dt:
        raise contract.ContractError("base profile conflicts with generator metadata")
    contract.jsonable(base.metadata)  # validate complete metadata; omit nothing


def _write_arrays(writer: Any, prefix: str, x: Any, y: Any, ts: Any, feature_x: Any = None) -> dict[str, str]:
    arrays = {"x": x, "y": y, "ts": ts}
    if feature_x is not None:
        arrays["feature_x"] = feature_x
    files = {key: f"{prefix}/{key}.npy" for key in arrays}
    for key, value in arrays.items():
        writer.write_array(files[key], value)
    return files


def _segment_info(
    context: str, center: int, scenario: str, role: str, span: tuple[int, int],
    raw_x: Any, feature_x: Any, y: Any, ts: Any,
    definition_digest: str, dependency_digest: str,
    scene_fingerprint: str, source_files: dict[str, str],
    stage: int | None = None, update_end_ts: int | None = None,
    decision_ts: int | None = None,
) -> dict[str, Any]:
    a, b = span
    if not 0 <= a < b <= N_HISTORY or b - a <= WINDOW_LENGTH:
        raise contract.ContractError("invalid half-open role/reference span")
    rx, fx, sy, st = raw_x[a:b], feature_x[a:b], y[a:b], ts[a:b]
    contract.check_shapes(fx, sy, st, raw_features=25, n=b - a)
    arrays = contract.describe_arrays(fx, sy, st)
    payload: dict[str, Any] = {
        "center_id": center, "scenario": scenario, "role": role,
        "span": [a, b], "raw_count": b - a,
        "window_length": WINDOW_LENGTH, "window_count": b - a - WINDOW_LENGTH,
        "start_ts": int(st[0]), "end_ts": int(st[-1]),
        "arrays": arrays, "legacy_role_hash": arrays["legacy_array_digest"],
        "scenario_provenance_fingerprint": scene_fingerprint,
    }
    if stage is not None:
        payload.update({
            "stage": stage, "update_end_ts": update_end_ts,
            "decision_ts": decision_ts,
        })
    else:
        raw_arrays = contract.describe_arrays(rx, sy, st)
        payload.update({
            "raw_arrays": raw_arrays,
            "feature_arrays": arrays,
            "raw_legacy_array_digest": raw_arrays["legacy_array_digest"],
            "feature_legacy_array_digest": arrays["legacy_array_digest"],
        })
    fingerprint = _fingerprint("stage_role" if stage is not None else "reference", context, definition_digest, dependency_digest, payload)
    return {**payload, "provenance_fingerprint": fingerprint, "source_files": source_files}


def materialize_context(
    repo: Path, label: str, writer: Any, definition_digest: str,
    dependency_digest: str, bank: dict[str, Any],
    source_pins: dict[str, str],
) -> dict[str, Any]:
    """Generate only input arrays and input/resource digests after authorization.

    The caller supplies a collision-refusing writer rooted in a separately
    authorized verification run directory. This function never opens project
    output files for writing, reads checkpoints, imports models, computes loss,
    creates windows/optimizers or mutates an existing input bundle.
    """
    if label not in {"F1", "F2", "S1", "S2"}:
        raise contract.ContractError("replicate label must be F1/F2/S1/S2")
    for value in (definition_digest, dependency_digest):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise contract.ContractError("scientific digest is not a lowercase SHA256")
    context = label[0]
    root = Path(repo).resolve(strict=True)
    frozen_config_path = _inside(root, "configs/p3_mismatch_v2_frozen.json")
    if source_pins.get("configs/p3_mismatch_v2_frozen.json") != MISMATCH_CONFIG_PIN or contract.file_sha256(frozen_config_path) != MISMATCH_CONFIG_PIN:
        raise contract.ContractError("frozen scenario config changed")
    config = contract.read_json(frozen_config_path)
    if config.get("generator_revision") != "p3_mismatch_v2_r3" or tuple(config.get("scenarios", [])) != contract.SCENARIOS:
        raise contract.ContractError("scenario scientific contract changed")

    runtime = load_pure_runtime(root, source_pins)
    resolved = _resolved_config(runtime)
    order = list(contract.CENTERS) if label != "S2" else list(reversed(contract.CENTERS))
    if context == "F":
        generated = runtime["generate_base_centers"](order, data_seed=DATA_SEED, n_history=N_HISTORY)
        if len(generated) != 20:
            raise contract.ContractError("full-batch population is not twenty centers")
    else:
        generated = []
        for center in order:
            one = runtime["generate_base_centers"]([center], data_seed=DATA_SEED, n_history=N_HISTORY)
            if len(one) != 1:
                raise contract.ContractError("singleton generator returned wrong count")
            generated.extend(one)
    if [base.center_id for base in generated] != order:
        raise contract.ContractError("materialized ID coverage/order mismatch")
    if context == "F":
        counts = {kind: sum(base.center_type == kind for base in generated) for kind in "ABC"}
        if counts != {"A": 6, "B": 8, "C": 6}:
            raise contract.ContractError("full-batch type population violates frozen 3:4:3 blocks")

    result: dict[str, Any] = {
        "schema": "paper3-input-materialization-v1",
        "context": context, "replicate": label,
        "definition_digest": definition_digest,
        "dependency_digest": dependency_digest,
        "execution_call_order": order,
        "base": {}, "scenarios": {}, "roles": {}, "references": {},
        "reference_parity_checks": {},
        "resolved_config": resolved,
        "initial_state_verification": "NOT_VERIFIED / SEPARATE_AUTH_REQUIRED",
        "initial_state_verified": False,
    }
    for base in generated:
        center = base.center_id
        _base_contract(base, center, runtime)
        profile = contract.jsonable({
            "center_id": center, "center_type": base.center_type,
            "budget_tier": base.budget_tier, "dt": base.dt,
            "metadata": base.metadata,
        })
        deployment = _deployment(bank, base.budget_tier)
        arrays = contract.describe_arrays(base.x, base.y, base.ts)
        rng_context = {
            "n_centers": 20 if context == "F" else 1,
            "start_center_id": contract.CENTERS[0] if context == "F" else center,
            "seed_offset": (contract.CENTERS[0] if context == "F" else center) * 17,
            "global_initial_seed": DATA_SEED + (contract.CENTERS[0] if context == "F" else center) * 17,
            "local_slot": center - contract.CENTERS[0] if context == "F" else 0,
        }
        base_payload = {
            "center_id": center, "arrays": arrays,
            "legacy_array_digest": arrays["legacy_array_digest"],
            "profile": profile, "profile_digest": contract.canonical_hash(profile),
            "deployment": deployment, "rng_context": rng_context,
        }
        base_fingerprint = _fingerprint("base", context, definition_digest, dependency_digest, base_payload)
        base_files = _write_arrays(writer, f"inputs/{label}/center_{center}/base", base.x, base.y, base.ts)
        result["base"][str(center)] = {
            **base_payload, "provenance_fingerprint": base_fingerprint, "files": base_files,
        }
        writer.write_json(f"inputs/{label}/center_{center}/base/profile.json", profile)
        original_base_digest = arrays["legacy_array_digest"]
        original_profile_digest = base_payload["profile_digest"]
        for value in (base.x, base.y, base.ts):
            value.flags.writeable = False

        for scenario in contract.SCENARIOS:
            x, y, metadata = runtime["make_scenario_v2"](base, scenario, config)
            contract.check_shapes(x, y, base.ts)
            if (metadata.get("onset_raw_index") != ONSET_RAW_INDEX
                    or metadata.get("scenario") != scenario
                    or metadata.get("generator_revision") != "p3_mismatch_v2_r3"):
                raise contract.ContractError("scenario metadata/onset mismatch")
            feature_x = runtime["feature_matrix"](x, base.dt)
            contract.check_shapes(feature_x, y, base.ts, raw_features=25)
            scene_arrays = contract.describe_arrays(x, y, base.ts)
            feature_arrays = contract.describe_arrays(feature_x, y, base.ts)
            scene_payload = {
                "center_id": center, "scenario": scenario,
                "arrays": scene_arrays, "feature_arrays": feature_arrays,
                "legacy_scenario_hash": scene_arrays["legacy_array_digest"],
                "metadata": contract.jsonable(metadata),
                "base_provenance_fingerprint": base_fingerprint,
            }
            scene_fingerprint = _fingerprint("scenario", context, definition_digest, dependency_digest, scene_payload)
            scene_files = _write_arrays(
                writer, f"inputs/{label}/center_{center}/scenario_{scenario}",
                x, y, base.ts, feature_x,
            )
            result["scenarios"][f"{center}/{scenario}"] = {
                **scene_payload, "provenance_fingerprint": scene_fingerprint, "files": scene_files,
            }
            writer.write_json(f"inputs/{label}/center_{center}/scenario_{scenario}/metadata.json", metadata)
            for stage in range(1, 25):
                spans = contract.stage_spans(stage)
                update_end_ts = int(base.ts[spans[0][1] - 1])
                decision_ts = int(base.ts[spans[1][1] - 1])
                for role, span in zip(("update", "assessment", "service"), spans):
                    result["roles"][f"{center}/{scenario}/{stage}/{role}"] = _segment_info(
                        context, center, scenario, role, span, x, feature_x, y, base.ts,
                        definition_digest, dependency_digest, scene_fingerprint, scene_files,
                        stage, update_end_ts, decision_ts,
                    )
            for role, span in (("warmup", (0, 800)), ("reference", (800, 1000))):
                result["references"][f"{center}/{scenario}/{role}"] = _segment_info(
                    context, center, scenario, role, span, x, feature_x, y, base.ts,
                    definition_digest, dependency_digest, scene_fingerprint, scene_files,
                )
            # Pure helpers are not allowed to alter a base or its full metadata.
            if contract.legacy_array_digest(base.x, base.y, base.ts) != original_base_digest or contract.canonical_hash(contract.jsonable({
                "center_id": center, "center_type": base.center_type,
                "budget_tier": base.budget_tier, "dt": base.dt,
                "metadata": base.metadata,
            })) != original_profile_digest:
                raise contract.ContractError("scenario helper mutated shared base inputs/profile")

        for role in ("warmup", "reference"):
            entries = [result["references"][f"{center}/{scenario}/{role}"] for scenario in contract.SCENARIOS]
            for field in ("raw_legacy_array_digest", "feature_legacy_array_digest"):
                if len({entry[field] for entry in entries}) != 1:
                    raise contract.ContractError(f"pre-onset {role} inputs differ across scenarios: {center}/{field}")
            result["reference_parity_checks"][f"{center}/{role}"] = {
                "status": "EXACT", "scenarios": list(contract.SCENARIOS),
                "raw_legacy_array_digest": entries[0]["raw_legacy_array_digest"],
                "feature_legacy_array_digest": entries[0]["feature_legacy_array_digest"],
                "span": entries[0]["span"], "window_count": entries[0]["window_count"],
                "model_or_error_computation_executed": False,
            }

    if (len(result["base"]), len(result["scenarios"]), len(result["roles"]), len(result["references"])) != (20, 80, 5760, 160):
        raise contract.ContractError("materialization coverage incomplete")
    bundle_payload = {
        "context": context, "resolved_config": resolved,
        "bank_hash": bank["bank_hash"],
        "base": {key: value["provenance_fingerprint"] for key, value in result["base"].items()},
        "scenarios": {key: value["provenance_fingerprint"] for key, value in result["scenarios"].items()},
        "roles": {key: value["provenance_fingerprint"] for key, value in result["roles"].items()},
        "references": {key: value["provenance_fingerprint"] for key, value in result["references"].items()},
    }
    result["input_bundle_digest"] = _fingerprint("input_bundle", context, definition_digest, dependency_digest, bundle_payload)
    for kind, name in (
        ("base", "base_input_inventory"), ("scenarios", "scenario_input_inventory"),
        ("roles", "stage_role_inventory"), ("references", "reference_input_inventory"),
    ):
        writer.write_jsonl(f"inventories/{label}/{name}.jsonl", [
            {"entry_key": key, **value} for key, value in sorted(result[kind].items())
        ])
    writer.write_json(f"inventories/{label}/materialization_manifest.json", result)
    return result
