"""Audit adapters around the exact frozen P7.7 trajectory function.

Importing this module uses the standard library only. Real project/model calls
occur only when the separately gated replication driver invokes run_task or
initial_preflight. The frozen function's code object is reused unchanged;
exactly three globals supply fixed inputs and audit its original initialization.
No writer, generator, historical worker, statistics routine or manual seeding is
called here. All outputs are returned to the exclusive new-output driver.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import inspect
import json
import marshal
import stat
import sys
import types
from pathlib import Path
from typing import Any, Callable


CENTERS = tuple(range(33000, 33020))
SEEDS = (7311, 7312, 7313)
SCENARIOS = ("C0", "C1", "C3", "C4")
METHODS = (
    ("B0", "B0_Frozen_ratio10"), ("B1", "B1_AlwaysMaintainP50_ratio10"),
    ("B2", "B2_RAVM_ratio10"), ("B8", "B8_AlwaysOpen_ratio10"),
    ("P7.7", "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"),
)
IDENTITY_FIELDS = (
    "identity_id", "architecture_index", "architecture", "family", "source_initialization_id",
    "checkpoint", "checkpoint_sha256", "parameter_count", "operation_count",
)
SOURCE_PINS = {
    "scripts/run_p7_7_final.py": "ced000f213f8fc9b52a859e683fc6d27dd04a268641c3d6024500f56c1c158fe",
    "scripts/run_p7.py": "51dd05f494ae561858c8de804eb34a4ef0590f69480aae0cc5dbae2baff25494",
    "core/p7.py": "378f2b8644f97e87fa819661da694d1bfcb163e7d183d110edf5f08c9d6dfe3d",
    "core/p6.py": "7597861c7bddd8e32080a3f83eff0ab0bc0f55db6c6b11aec773794f33cc2b07",
    "core/models.py": "55028939faab38ea23736d191647f33f08ad48f14f204bbecf55bb3d76642e7e",
    "core/p3_2_models.py": "05aef843c99e3e4054c6b99a47063e85e6138c50bbb829c39183221a08765982",
    "core/protocol.py": "8468b32f245e91c9bcbbb95d93b2dea07b75087d951184fb429cc1f7201cc367",
    "core/p3_2_data.py": "0f5a5bff889a0ac866793dc49b21680f927af13c9e6fc3d5c3d75bbf4d9d5b27",
    "core/data.py": "6cd7e375d40c8ecf390fe37dee270d93890b3981f666e521e17441612f304d5e",
    "core/common.py": "10c8dcf936e60e6b9b992778310648e258ed5a105d290d09434ba0c968183aaa",
    "imported/msa_dti/space/models.py": "a6c73ffac8a0ccad3232f7ea8e75afccc6f0bb7ae5356ba0a02545c67d6e1017",
    "imported/msa_dti/space/profile.py": "d7abbbcebe5c4dde274aa193c20bdfc733c07b7efb16b00c00566c4aff154db3",
    "imported/msa_dti/space/enumerator.py": "d7509947a2534e23f37cf9150276eb32886fb975275268ee390c217ab3d793ee",
    "imported/msa_dti/space/types.py": "364016db8428ec5b3004bc290349ffef226feb4a0d776064415ed8f19f7e5e37",
    "imported/ravm_dt/main_cfg.py": "fea128a2649301017a2a8ad6cab3db30392e180c2f3aa1216e9a83fefcd5d005",
    "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json": "6339a9247b984b497d1543198b3a7b7c0cfdf9c7bcfd1c52b47b62e17d2fd0df",
    "configs/p3_mismatch_v2_frozen.json": "529655647c1359e2a164cddc3c5c8b534f5cdbad53e2ede29ada477910975646",
    "artifacts/p3_model_bank_manifest.json": "e607a65adfb05b91bf8d9ebac77052d6e13223dfd54e47e655167e20c92342c8",
    "artifacts/p3_2_source_bank/p3_mismatch_v2_r3/source_training_manifest.json": "84ab3d962e9a566303060fa98febcadef26eb1e5d472f81d32d986c35de3b940",
    "artifacts/p6_recoverability_estimator.pt": "2bbad97427506b0260d3ed9370bc88ed4c91a8879c34787a184e37b5185f6b9b",
    "artifacts/p6_recoverability_scaler.json": "1d4cb0b91206bb7defe8389aa8f27ff4776c2acc016662e952bc5f5dc3612f3b",
    "audits/P6_ESTIMATOR_FREEZE.json": "6c5286e3e470413a150b17d908bfd7c87931ce1fa55304ccf270d578fb57374f",
    "artifacts/p7_6b_A1_estimator.pt": "e8d047bda5a1e1d62cd9f089db1ade79c0c08750f9dfc878d6e71cc06d8c47cb",
    "artifacts/p7_6b_A1_scaler.json": "2c9da0a29b469b8bb92bdbbcb893769a8baa39a57b3dbd26247ba9b1c8564c38",
}
ALLOWED_GLOBAL_OVERRIDES = ("timeline_for_v2", "scenario_hash_v2", "initial_model")


class ScienceIntegrityError(RuntimeError):
    """A frozen scientific or execution-integrity condition did not hold."""


def _hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path(repo: Path, relative: str) -> Path:
    parts = relative.split("/")
    if any(part in ("", ".", "..") or ":" in part or "\\" in part for part in parts):
        raise ScienceIntegrityError("unsafe scientific dependency path")
    path = Path(repo).absolute().joinpath(*parts)
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ScienceIntegrityError("scientific dependency reparse path forbidden")
    if not path.resolve(strict=True).is_relative_to(Path(repo).resolve(strict=True)):
        raise ScienceIntegrityError("scientific dependency escaped target repository")
    return path.resolve(strict=True)


def _json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ScienceIntegrityError("duplicate scientific JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ScienceIntegrityError("non-finite scientific JSON value: " + value)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=unique, parse_constant=nonfinite)


def _check_sources(repo: Path, source_pins: dict | None) -> dict:
    pins = dict(SOURCE_PINS)
    if source_pins is not None:
        if any(source_pins.get(path) != digest for path, digest in pins.items()):
            raise ScienceIntegrityError("caller source pins differ from frozen method dependencies")
        pins = dict(source_pins)
    actual = {relative: _file_hash(_path(repo, relative)) for relative in sorted(pins)}
    if actual != pins:
        raise ScienceIntegrityError("frozen source/config/model bytes changed")
    return actual


def _check_cfg(repo: Path, cfg: dict) -> None:
    expected = _json(_path(repo, "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"))
    if cfg != expected:
        raise ScienceIntegrityError("replication must use the complete unchanged final configuration")
    population = cfg["final_population"]
    if (tuple(population["centers"]), tuple(population["seeds"]), tuple(population["scenarios"])) != (CENTERS, SEEDS, SCENARIOS):
        raise ScienceIntegrityError("frozen full population differs")
    if population["total_expected_trajectories"] != 1200 or population["method_count"] != 5:
        raise ScienceIntegrityError("frozen 1200-trajectory population differs")
    if tuple((item["method"], item["config_id"]) for item in cfg["comparators"]) != METHODS:
        raise ScienceIntegrityError("five frozen comparator definitions/order differ")


def _check_task(task: dict, cfg: dict) -> dict:
    if not isinstance(task, dict) or set(task) != {"center_id", "seed", "scenario", "method", "config_id"}:
        raise ScienceIntegrityError("task must be one exact frozen five-field tuple")
    if type(task["center_id"]) is not int or type(task["seed"]) is not int:
        raise ScienceIntegrityError("center and seed must be native integer IDs")
    if task["center_id"] not in CENTERS or task["seed"] not in SEEDS or task["scenario"] not in SCENARIOS:
        raise ScienceIntegrityError("task outside frozen full population")
    pairs = {method: config for method, config in METHODS}
    if pairs.get(task["method"]) != task["config_id"]:
        raise ScienceIntegrityError("method/config tuple differs from frozen population")
    return copy.deepcopy(next(item for item in cfg["comparators"] if item["method"] == task["method"]))


def _runner(repo: Path, supplied: types.ModuleType | None):
    path = _path(repo, "scripts/run_p7_7_final.py")
    if supplied is None:
        name = "paper3_replication_frozen_original_runner"
        if name in sys.modules:
            supplied = sys.modules[name]
        else:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ScienceIntegrityError("cannot bind frozen original runner")
            supplied = importlib.util.module_from_spec(spec)
            sys.modules[name] = supplied
            spec.loader.exec_module(supplied)
    if Path(supplied.__file__).resolve(strict=True) != path:
        raise ScienceIntegrityError("runner module does not come from exact target source")
    code = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
    expected = next(value for value in code.co_consts if isinstance(value, types.CodeType) and value.co_name == "run_one")
    if supplied.run_one.__code__ != expected or Path(supplied.run_one.__code__.co_filename).resolve(strict=True) != path:
        raise ScienceIntegrityError("frozen run_one code object changed")
    if Path(supplied.initial_model.__code__.co_filename).resolve(strict=True) != _path(repo, "core/p6.py"):
        raise ScienceIntegrityError("original initial_model provenance changed")
    initial_code = compile(_path(repo, "core/p6.py").read_bytes(), str(_path(repo, "core/p6.py")), "exec", dont_inherit=True)
    expected_initial = next(value for value in initial_code.co_consts if isinstance(value, types.CodeType) and value.co_name == "initial_model")
    if supplied.initial_model.__code__ != expected_initial:
        raise ScienceIntegrityError("original initial_model code object changed")
    return supplied


def capture_scientific_runtime(torch, numpy) -> dict:
    """Read actual initialized library/device defaults without changing them.

    CUDA metadata queries can initialize the CUDA runtime but perform no model,
    optimizer, generator or seed operation. The later RNG receipt is captured
    after this setup. An unavailable private driver-version query remains
    explicitly unavailable; no external command or guessed driver is used.
    """
    available = bool(torch.cuda.is_available())
    devices = []
    current_device = None
    if available:
        current_device = int(torch.cuda.current_device())
        for index in range(int(torch.cuda.device_count())):
            props = torch.cuda.get_device_properties(index)
            devices.append({"index": index, "name": str(torch.cuda.get_device_name(index)),
                            "capability": list(torch.cuda.get_device_capability(index)),
                            "total_memory_bytes": int(props.total_memory),
                            "multiprocessor_count": int(props.multi_processor_count),
                            "uuid": str(props.uuid) if getattr(props, "uuid", None) is not None else None})
    driver = {"status": "NOT_AVAILABLE", "api": None, "version": None}
    getter = getattr(getattr(torch, "_C", None), "_cuda_getDriverVersion", None)
    if available and callable(getter):
        driver["api"] = "torch._C._cuda_getDriverVersion"
        try:
            driver.update(status="VERIFIED_RUNTIME_QUERY", version=int(getter()))
        except Exception as error:
            driver.update(status="QUERY_FAILED", error_type=type(error).__name__)
    cudnn = torch.backends.cudnn
    matmul = torch.backends.cuda.matmul
    config = getattr(torch, "__config__", None)
    show = getattr(config, "show", None)
    original_models = sys.modules.get("core.models")
    return {"schema": "paper3-readonly-scientific-runtime-v1", "torch_version": str(torch.__version__),
            "torch_git_version": getattr(torch.version, "git_version", None),
            "torch_cuda_build_version": torch.version.cuda,
            "torch_build_configuration": str(show()) if callable(show) else None,
            "numpy_version": str(numpy.__version__),
            "numpy_git_revision": getattr(getattr(numpy, "version", None), "git_revision", None),
            "cuda_available": available, "cuda_current_device": current_device,
            "cuda_devices": devices, "cuda_driver": driver,
            "original_models_device": str(original_models.DEVICE) if original_models is not None else None,
            "torch_num_threads": int(torch.get_num_threads()),
            "torch_num_interop_threads": int(torch.get_num_interop_threads()),
            "cudnn_version": cudnn.version(), "cudnn_enabled": bool(cudnn.enabled),
            "cudnn_deterministic": bool(cudnn.deterministic), "cudnn_benchmark": bool(cudnn.benchmark),
            "cudnn_allow_tf32": bool(cudnn.allow_tf32), "cuda_matmul_allow_tf32": bool(matmul.allow_tf32),
            "deterministic_algorithms_enabled": bool(torch.are_deterministic_algorithms_enabled()),
            "default_dtype": str(torch.get_default_dtype()), "default_settings_modified_by_verifier": False,
            "model_or_optimizer_called": False, "manual_seed_called": False,
            "external_driver_binary_inventory_verified": False}


def runtime_preflight(repo: Path, input_run: Path, *, source_pins: dict | None = None,
                      original_runner=None) -> dict:
    """Authorized source-bound imports and runtime queries only; no warm-up."""
    from . import provenance
    manifest = provenance.require_authorized_execution(repo, input_run)
    sources = _check_sources(repo, source_pins)
    runner = _runner(repo, original_runner)
    runtime = capture_scientific_runtime(runner.torch, runner.np)
    return {"scientific_runtime": runtime, "scientific_runtime_signature": _hash_json(runtime),
            "source_bindings_digest": _hash_json(sources),
            "environment_binding": provenance.canonical_hash(manifest["environment"]),
            "generation_performed": False, "warmup_performed": False, "lifecycle_executed": False}


def isolated_frozen_call(original: types.FunctionType, callbacks: dict) -> types.FunctionType:
    """Keep original bytecode/globals untouched; audit exactly three overrides."""
    if set(callbacks) != set(ALLOWED_GLOBAL_OVERRIDES) or any(not callable(callback) for callback in callbacks.values()):
        raise ScienceIntegrityError("exactly three callable input/initial audit adapters required")
    original_globals = original.__globals__
    if any(name not in original_globals for name in callbacks):
        raise ScienceIntegrityError("frozen function global adapter surface changed")
    adapted_globals = dict(original_globals)
    adapted_globals.update(callbacks)
    changed = {name for name in original_globals if adapted_globals[name] is not original_globals[name]}
    if changed != set(ALLOWED_GLOBAL_OVERRIDES) or set(adapted_globals) != set(original_globals):
        raise ScienceIntegrityError("isolated frozen function globals changed beyond the three audited adapters")
    adapted = types.FunctionType(original.__code__, adapted_globals, original.__name__, original.__defaults__, original.__closure__)
    adapted.__kwdefaults__ = copy.copy(original.__kwdefaults__)
    if adapted.__code__ is not original.__code__:
        raise ScienceIntegrityError("frozen trajectory code object was not preserved")
    return adapted


def _bank_audit(repo: Path, identities: list, store, base, frozen: dict) -> dict:
    actual = [{field: item.to_dict()[field] for field in IDENTITY_FIELDS} for item in identities]
    if len(actual) != 11 or actual != store.bank["identities"] or _hash_json(actual) != store.bank["bank_hash"]:
        raise ScienceIntegrityError("actual ordered eleven-identity bank differs from fixed reference")
    checkpoint_hashes = {}
    for item in actual:
        path = _path(repo, item["checkpoint"])
        actual_hash = _file_hash(path)
        if actual_hash != item["checkpoint_sha256"]:
            raise ScienceIntegrityError("actual source checkpoint byte hash differs")
        checkpoint_hashes[item["checkpoint"]] = actual_hash
    expected_deployment = store.bundle["base"][str(base.center_id)]["deployment"]
    limits = frozen["deployment_limits"][base.budget_tier]
    mask = [item["parameter_count"] <= limits["parameters"] and item["operation_count"] <= limits["operations"] for item in actual]
    feasible_ids = [item["identity_id"] for item, allowed in zip(actual, mask) if allowed]
    initial_candidates = [identity for identity in feasible_ids if identity != "msa_a57_pt"]
    if (limits != expected_deployment["limits"] or _hash_json(limits) != expected_deployment["deployment_filter_hash"]
            or mask != expected_deployment["feasible_mask"] or feasible_ids != expected_deployment["feasible_ids"]
            or initial_candidates != expected_deployment["initial_candidate_ids"]):
        raise ScienceIntegrityError("actual deployment resource universe differs from canonical reference")
    return {"identities": actual, "bank_hash": _hash_json(actual), "checkpoint_file_sha256": checkpoint_hashes,
            "deployment_tier": base.budget_tier, "limits": limits,
            "deployment_filter_hash": _hash_json(limits), "feasible_mask": mask,
            "feasible_ids": feasible_ids, "initial_candidate_ids": initial_candidates}


def _initial_evidence(runner, model, incumbent, store, base, scenario: str, bank: dict) -> dict:
    warmup = store.bundle["references"][f"{base.center_id}/{scenario}/warmup"]
    reference = store.bundle["references"][f"{base.center_id}/{scenario}/reference"]
    return {"initial_state_hash": runner.state_hash(model), "incumbent": incumbent.to_dict(), "bank": bank,
            "center_id": base.center_id, "scenario": scenario, "center_type": base.center_type,
            "deployment_tier": base.budget_tier,
            "profile_digest": store.bundle["base"][str(base.center_id)]["profile_digest"],
            "scenario_fingerprint": store.bundle["scenarios"][f"{base.center_id}/{scenario}"]["provenance_fingerprint"],
            "warmup_raw_hash": warmup["raw_legacy_array_digest"], "warmup_feature_hash": warmup["feature_legacy_array_digest"],
            "warmup_span": [0, 800], "reference_raw_hash": reference["raw_legacy_array_digest"],
            "reference_feature_hash": reference["feature_legacy_array_digest"], "reference_span": [800, 1000],
            "warmup_steps": 50, "warmup_seed_rule": "seed+center_id", "original_initial_model_called": True}


def _rng_array(tensor) -> dict:
    raw = tensor.detach().cpu().contiguous().numpy().tobytes()
    return {"dtype": "uint8", "shape": list(tensor.shape), "byte_count": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "base64": base64.b64encode(raw).decode("ascii")}


def capture_rng_state(torch, bindings: dict) -> dict:
    """Capture actual existing execution RNG; do not seed or advance it."""
    cuda = []
    if torch.cuda.is_available():
        for index, tensor in enumerate(torch.cuda.get_rng_state_all()):
            cuda.append({"device_index": index, "device_name": torch.cuda.get_device_name(index), "state": _rng_array(tensor)})
    result = {"schema": "paper3-original-task-torch-rng-v1", "bindings": bindings,
              "torch_version": str(torch.__version__), "cuda_runtime": torch.version.cuda,
              "cpu": _rng_array(torch.get_rng_state()), "cuda": cuda,
              "manual_seed_called": False, "scope": "EXISTING_EXECUTION_RNG_PROVENANCE"}
    result["state_digest"] = _hash_json(result)
    return result


def _decode_rng(torch, value: dict):
    if value.get("dtype") != "uint8" or value.get("shape") != [value.get("byte_count")]:
        raise ScienceIntegrityError("RNG tensor dtype/shape invalid")
    raw = base64.b64decode(value["base64"], validate=True)
    if len(raw) != value["byte_count"] or hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise ScienceIntegrityError("recorded RNG state byte binding invalid")
    return torch.tensor(list(raw), dtype=torch.uint8)


def restore_failed_task_rng(torch, recorded: dict, bindings: dict) -> dict:
    """Exact failed-task replay only; never restore between different methods."""
    if recorded.get("failed_attempt_status") not in {"FAILED", "INTERRUPTED"} or recorded.get("completed_valid") is not False:
        raise ScienceIntegrityError("RNG restoration requires an incomplete/failed task receipt")
    receipt_sha = recorded.get("failed_attempt_receipt_sha256", "")
    if not isinstance(receipt_sha, str) or len(receipt_sha) != 64 or any(char not in "0123456789abcdef" for char in receipt_sha):
        raise ScienceIntegrityError("failed-attempt receipt binding required for RNG restoration")
    state = recorded["rng_state"]
    body = {key: value for key, value in state.items() if key != "state_digest"}
    if state.get("state_digest") != _hash_json(body) or state.get("bindings") != bindings:
        raise ScienceIntegrityError("retry RNG task/input/source/environment binding differs")
    if (state.get("schema") != "paper3-original-task-torch-rng-v1" or state.get("torch_version") != str(torch.__version__)
            or state.get("cuda_runtime") != torch.version.cuda or state.get("manual_seed_called") is not False):
        raise ScienceIntegrityError("retry RNG schema/runtime differs")
    actual_cuda_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    if len(state["cuda"]) != actual_cuda_count:
        raise ScienceIntegrityError("retry RNG CUDA device topology differs")
    cuda_states = []
    for index, item in enumerate(state["cuda"]):
        if item["device_index"] != index or item["device_name"] != torch.cuda.get_device_name(index):
            raise ScienceIntegrityError("retry RNG device identity differs")
        cuda_states.append(_decode_rng(torch, item["state"]))
    cpu_state = _decode_rng(torch, state["cpu"])
    torch.set_rng_state(cpu_state)
    if cuda_states:
        torch.cuda.set_rng_state_all(cuda_states)
    replay = capture_rng_state(torch, bindings)
    if replay["state_digest"] != state["state_digest"]:
        raise ScienceIntegrityError("exact recorded RNG restoration failed")
    return replay


def _fixed_store(repo: Path, input_run: Path, supplied=None):
    from .fixed_inputs import FixedInputStore
    if supplied is None:
        return FixedInputStore(repo, input_run)
    if (not isinstance(supplied, FixedInputStore) or supplied.repo != Path(repo).resolve(strict=True)
            or supplied.verification_run_root != Path(input_run).resolve(strict=True)):
        raise ScienceIntegrityError("cached fixed input store belongs to another repository/publication")
    return supplied


def initial_preflight(repo: Path, input_run: Path, center: int, seed: int, cfg: dict,
                      original_runner=None, source_pins: dict | None = None, input_store=None) -> dict:
    """Original 50-step initialization only; no estimator/service/lifecycle call.

    Driver runs this in separate processes from trajectory workers so these
    additional initial-state measurements do not shift their execution RNG.
    """
    if type(center) is not int or center not in CENTERS or type(seed) is not int or seed not in SEEDS:
        raise ScienceIntegrityError("initial-state preflight outside frozen center/seed pool")
    from . import provenance
    provenance.require_authorized_execution(repo, input_run)
    sources = _check_sources(repo, source_pins)
    _check_cfg(repo, cfg)
    store = _fixed_store(repo, input_run, input_store)
    base, timeline, metadata, scenario_hash = store.load(center, "C0")
    runner = _runner(repo, original_runner)
    runtime = capture_scientific_runtime(runner.torch, runner.np)
    frozen = runner.read_json(_path(repo, "configs/p3_mismatch_v2_frozen.json"))
    source = runner.read_json(_path(repo, frozen["source_training_manifest_path"]))
    identities = runner.build_p3_2_identity_bank(source)
    bank = _bank_audit(repo, identities, store, base, frozen)
    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    model = runner.initial_model(base, seed, incumbent, timeline)
    audit = _initial_evidence(runner, model, incumbent, store, base, "C0", bank)
    audit.update({"schema": "paper3-canonical-initial-state-preflight-v1", "seed": seed,
                  "warmup_seed": seed + center, "source_bindings_sha256": sources,
                  "input_bundle_digest": store.bundle["input_bundle_digest"],
                  "scientific_runtime": runtime, "scientific_runtime_signature": _hash_json(runtime),
                  "lifecycle_executed": False, "service_evaluated": False, "estimator_loaded": False,
                  "additional_preflight_is_not_historical_reproduction": True})
    if _check_sources(repo, source_pins) != sources:
        raise ScienceIntegrityError("frozen dependencies changed during initial-state preflight")
    _check_cfg(repo, cfg)
    return audit


def run_task(repo: Path, input_run: Path, task: dict, cfg: dict, *,
             expected_initial_state_hash: str, environment_binding: str,
             original_runner=None, source_pins: dict | None = None,
             retry_rng_state: dict | None = None,
             rng_capture_sink: Callable[[dict], None] | None = None,
             input_store=None):
    """Return frozen 24-stage DataFrame plus audit; write no result here."""
    if (len(expected_initial_state_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_initial_state_hash)
            or len(environment_binding) != 64 or any(c not in "0123456789abcdef" for c in environment_binding)):
        raise ScienceIntegrityError("authoritative initial/environment SHA256 bindings required")
    from . import provenance
    authorized = provenance.require_authorized_execution(repo, input_run)
    if environment_binding != provenance.canonical_hash(authorized["environment"]):
        raise ScienceIntegrityError("trajectory environment binding differs from authorized immutable manifest")
    sources = _check_sources(repo, source_pins)
    _check_cfg(repo, cfg)
    method_cfg = _check_task(task, cfg)
    store = _fixed_store(repo, input_run, input_store)
    base, timeline, metadata, scenario_digest = store.load(task["center_id"], task["scenario"])
    runner = _runner(repo, original_runner)
    runtime = capture_scientific_runtime(runner.torch, runner.np)
    frozen = _json(_path(repo, "configs/p3_mismatch_v2_frozen.json"))
    initial_audit: dict = {}

    def same_request(request_base, request_scenario, request_frozen):
        if request_base is not base or request_scenario != task["scenario"] or request_frozen != frozen:
            raise ScienceIntegrityError("frozen function requested an unbound input realization")

    def fixed_timeline(request_base, request_scenario, request_frozen):
        same_request(request_base, request_scenario, request_frozen)
        return timeline, copy.deepcopy(metadata)

    def fixed_scenario_hash(request_base, request_scenario, request_frozen):
        same_request(request_base, request_scenario, request_frozen)
        return scenario_digest

    def audited_initial(request_base, request_seed, incumbent, request_timeline):
        if request_base is not base or request_seed != task["seed"] or request_timeline is not timeline or incumbent.identity_id != "msa_a57_pt":
            raise ScienceIntegrityError("initialization request differs from fixed task")
        caller = inspect.currentframe().f_back
        try:
            if caller.f_code is not runner.run_one.__code__:
                raise ScienceIntegrityError("initialization audit called outside exact frozen run_one")
            bank = _bank_audit(repo, caller.f_locals["bank"], store, base, caller.f_locals["frozen"])
        finally:
            del caller
        model = runner.initial_model(request_base, request_seed, incumbent, request_timeline)
        actual = _initial_evidence(runner, model, incumbent, store, base, task["scenario"], bank)
        if actual["initial_state_hash"] != expected_initial_state_hash:
            raise ScienceIntegrityError("actual initial state differs before the first lifecycle decision")
        initial_audit.update(actual, seed=task["seed"], warmup_seed=task["seed"] + base.center_id,
                             authoritative_expected_initial_state_hash=expected_initial_state_hash,
                             before_first_decision_verified=True)
        return model

    adapted = isolated_frozen_call(runner.run_one, {
        "timeline_for_v2": fixed_timeline, "scenario_hash_v2": fixed_scenario_hash, "initial_model": audited_initial})
    rng_bindings = {"task": dict(task), "input_bundle_digest": store.bundle["input_bundle_digest"],
                    "source_bindings_digest": _hash_json(sources), "environment_binding": environment_binding,
                    "final_configuration_sha256": sources["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"],
                    "expected_initial_state_hash": expected_initial_state_hash}
    # All setup is complete. Capture/optional exact failed-task replay is the
    # final operation before calling the unchanged frozen trajectory body.
    rng_state = (restore_failed_task_rng(runner.torch, retry_rng_state, rng_bindings) if retry_rng_state is not None
                 else capture_rng_state(runner.torch, rng_bindings))
    if rng_capture_sink is not None:
        rng_capture_sink(copy.deepcopy(rng_state))
        if capture_rng_state(runner.torch, rng_bindings)["state_digest"] != rng_state["state_digest"]:
            raise ScienceIntegrityError("RNG provenance sink changed execution RNG before the frozen function")
    frame = adapted(base, task["seed"], task["scenario"], cfg, method_cfg, allow_final=True)
    if not initial_audit or len(frame) != 24 or list(frame["stage"]) != list(range(1, 25)):
        raise ScienceIntegrityError("initial audit or complete 24-stage lifecycle missing")
    row_audit = []
    for row in frame.to_dict(orient="records"):
        stage = int(row["stage"])
        role = store.bundle["roles"][f"{base.center_id}/{task['scenario']}/{stage}/update"]
        expected = {**task, "scenario_hash": scenario_digest, "scenario_role": metadata["definition"],
                    "center_type": base.center_type, "deployment_tier": base.budget_tier,
                    "initial_state_hash": expected_initial_state_hash, "bank_hash": store.bank["bank_hash"],
                    "deployment_filter_hash": initial_audit["bank"]["deployment_filter_hash"],
                    "update_end_ts": role["update_end_ts"], "decision_ts": role["decision_ts"]}
        for role_name, field in (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash")):
            expected[field] = store.bundle["roles"][f"{base.center_id}/{task['scenario']}/{stage}/{role_name}"]["legacy_role_hash"]
        if any(row.get(name) != value for name, value in expected.items()):
            raise ScienceIntegrityError("trajectory input/state/deployment binding differs from fixed task")
        for name in ("future_service_used_in_decision", "online_future_service_used"):
            if row.get(name) is not False:
                raise ScienceIntegrityError("frozen trajectory future-information flag is not false")
        if row.get("assessment_gradient_updates") != 0 or row.get("probe_updates") != 50 or row.get("ri_updates_per_candidate") != 50:
            raise ScienceIntegrityError("frozen gradient/adaptation budget changed")
        if task["method"] == "P7.7" and (row.get("gate_boundary") != 0.0 or row.get("gate_estimator") != "A1"):
            raise ScienceIntegrityError("P7.7 exact zero-boundary A1 admission changed")
        if row.get("cost_ratio") != 10 or row.get("source_adapt_seed_rule") != "seed+center+stage*1000+500+bank_index":
            raise ScienceIntegrityError("frozen action cost or source adaptation seed rule changed")
        if row["action"] == "ri" and row.get("gate_open") != 1:
            raise ScienceIntegrityError("identity transition occurred without open admission")
        row_audit.append({"stage": stage, "paired_input_fields_match": True,
                          "initial_state_hash": row["initial_state_hash"], "bank_hash": row["bank_hash"],
                          "deployment_filter_hash": row["deployment_filter_hash"],
                          "D_upd_hash": row["D_upd_hash"], "D_assess_hash": row["D_assess_hash"], "D_srv_hash": row["D_srv_hash"]})
    if frame.iloc[0]["identity_before"] != "msa_a57_pt":
        raise ScienceIntegrityError("stage-1 deployed identity differs from frozen incumbent")
    timeline_evidence = timeline.get_access_evidence()
    if (timeline_evidence.get("violation_count") != 0 or timeline_evidence.get("completed_stages") != 24
            or timeline_evidence.get("phase") != "SERVICED"):
        raise ScienceIntegrityError("audited timeline violation or incomplete sealed/service stage coverage")
    if _check_sources(repo, source_pins) != sources:
        raise ScienceIntegrityError("frozen source/model dependency changed during trajectory")
    _check_cfg(repo, cfg)
    return frame, {
        "schema": "paper3-exact-frozen-trajectory-adapter-audit-v1", "task": dict(task),
        "source_bindings_sha256": sources, "source_bindings_digest": _hash_json(sources),
        "original_run_one_code_sha256": hashlib.sha256(marshal.dumps(runner.run_one.__code__)).hexdigest(),
        "original_run_one_code_object_preserved": adapted.__code__ is runner.run_one.__code__,
        "globals_overridden": list(ALLOWED_GLOBAL_OVERRIDES), "original_globals_mutated": False,
        "input_bundle_digest": store.bundle["input_bundle_digest"], "environment_binding": environment_binding,
        "scientific_runtime": runtime, "scientific_runtime_signature": _hash_json(runtime),
        "initial_state": initial_audit, "input_stage_checks": row_audit, "timeline_access": timeline_evidence,
        "rng_state_before_original_run": rng_state, "retry_exact_failed_state_restored": retry_rng_state is not None,
        "new_seed_introduced": False, "original_bank_build_and_profiling_preserved": True,
        "original_offline_labels_and_call_order_preserved": True, "generator_called": False,
        "historical_outputs_modified": False, "model_output_worker_invariance_claimed": False,
        "global_torch_dropout_limitation": "Original adapt seed fixes NumPy minibatch sampling; MLP dropout uses actual recorded global Torch RNG.",
        "statistics_executed": False,
    }
