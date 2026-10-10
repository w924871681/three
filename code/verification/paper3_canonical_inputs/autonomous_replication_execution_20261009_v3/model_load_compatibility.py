"""Authorized pre-experiment frozen model-load compatibility test.

No generator, warm-up, optimizer, parameter update or lifecycle evaluation.
All import origins are hash bound, all Python writes stay in an exclusive check
directory, and the original protected files are checked before and after.
This process is separate from model workers and does not select a protocol.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
EXECUTOR = REPO/"verification/paper3_canonical_inputs/replication_executor_batch20_env_v3"
RESULTS = REPO/"results/p7_7_integrity_replication_batch20_env_v3"
INPUT_RUN = REPO/"verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1/CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-runtime", type=Path, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()
    assert args.attempt >= 1
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    check = RESULTS/"stage_c_tests"/"model_load_compatibility"/f"attempt{args.attempt:03d}"
    assert not check.exists(), "exclusive compatibility attempt exists"
    expected_pycache = check/"_never_created_pycache"
    assert sys.pycache_prefix is not None and Path(sys.pycache_prefix).resolve() == expected_pycache.resolve() and not expected_pycache.exists(), "dedicated nonexistent compatibility bytecode prefix required"
    check.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    for name in ("TEMP", "TMP", "TORCH_HOME", "CUDA_CACHE_PATH"):
        value = check/"runtime_cache"/name.lower()
        value.mkdir(parents=True)
        os.environ[name] = str(value)
    package = types.ModuleType("paper3_compat_executor")
    package.__path__ = [str(EXECUTOR)]
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location(package.__name__+".provenance", EXECUTOR/"provenance.py")
    p = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = p
    spec.loader.exec_module(p)
    baseline = read(REPO/"verification/paper3_canonical_inputs/execution_20261009/original_protected_start_sha256.json")
    pre = p.check_original_snapshot(REPO, baseline)
    stage_b = p.verify_stage_b(REPO, INPUT_RUN)
    descriptor = read(args.model_runtime)
    environment = p.capture_model_environment(stage_b["source_environment"]["environment"], model_runtime=descriptor,
        progress=lambda value: print(json.dumps(value), flush=True))
    print(json.dumps({"phase":"model-load","step":"environment_and_F1_verified"}),flush=True)
    originals = {path.relative_to(REPO).as_posix():sha(path) for folder in ("core", "imported", "scripts") for path in (REPO/folder).rglob("*.py")}
    originals[Path(__file__).resolve().relative_to(REPO).as_posix()] = sha(__file__)
    manifest = {"paths":{"repo":str(REPO), "executor_root":str(EXECUTOR), "results_root":str(RESULTS),
                         "input_run":str(INPUT_RUN)},
                "environment":environment, "original_python_dependency_sha256":originals,
                "executor_sha256":{path.relative_to(EXECUTOR).as_posix():sha(path) for path in EXECUTOR.rglob("*.py")},
                "input_bundle_digest":stage_b["F1"]["input_bundle_digest"],
                "stage_b_source_environment_digest":p.canonical_hash(stage_b["source_environment"]),
                "original_protected_snapshot_digest":p.canonical_hash(baseline),
                "model_runtime_descriptor_sha256":sha(args.model_runtime)}
    manifest["manifest_digest"] = p.canonical_hash(manifest)
    def write_guard(event, values):
        def assert_output(value):
            if isinstance(value, int):
                if value in (1,2):
                    return
                value = p._descriptor_path(value)
            if os.fsdecode(value).casefold() in {"nul", "/dev/null"}:
                return
            target = p.regular_path(value, must_exist=False)
            assert target == check or check in target.parents, "compatibility write outside exclusive check: " + str(target)
            if target.is_file():
                assert target.stat().st_nlink <= 1, "multiply-linked compatibility output forbidden"
        if event == "open":
            value, mode, flags = values
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                assert_output(value)
        elif event in {"os.remove","os.rmdir","os.mkdir","os.chmod","os.utime","os.truncate"}:
            assert_output(values[0])
            if event in {"os.remove","os.rmdir","os.mkdir","os.chmod","os.utime"} and isinstance(values[-1], int):
                assert values[-1] == -1, "relative directory-FD mutation forbidden"
        elif event in {"os.rename","os.link"}:
            assert_output(values[0]); assert_output(values[1])
            if len(values) > 2:
                assert all(value is None or (type(value) is int and value == -1) for value in values[2:]), "relative directory-FD mutation forbidden"
        elif event in {"os.symlink","subprocess.Popen","os.system","os.exec","os.posix_spawn"}:
            raise RuntimeError("OS/subprocess operation forbidden in model-load compatibility process")
    sys.addaudithook(write_guard)
    # The executor's unchanged worker write guard and the tighter compatibility
    # guard intersect: this child can write only inside its exclusive check.
    p.install_write_guard(RESULTS)
    p.install_generator_guard(REPO)
    p.install_model_import_guard(manifest)
    sys.path.extend([str(REPO), environment["site_packages_root"]])
    adapter_spec = importlib.util.spec_from_file_location(package.__name__+".science_adapter", EXECUTOR/"science_adapter.py")
    adapter = importlib.util.module_from_spec(adapter_spec)
    sys.modules[adapter_spec.name] = adapter
    adapter_spec.loader.exec_module(adapter)
    adapter._check_sources(REPO, None)
    print(json.dumps({"phase":"model-load","step":"importing_frozen_runner"}),flush=True)
    import_token = p.begin_scientific_import_transition(manifest)
    runner = adapter._runner(REPO, None)
    import_transition = p.complete_scientific_import_transition(manifest, import_token)
    print(json.dumps({"phase":"model-load","step":"frozen_runner_imported"}),flush=True)
    assert runner.np.__version__ == "2.4.6" and str(runner.torch.__version__) == "2.5.1+cu121"
    # Import the real lazy dependencies needed by frozen SGD before provenance
    # publication. No optimizer is instantiated or called in this process.
    importlib.import_module("torch.optim")
    importlib.import_module("torch._dynamo")
    config = runner.read_json(REPO/"configs/p3_mismatch_v2_frozen.json")
    source = runner.read_json(REPO/config["source_training_manifest_path"])
    bank = runner.build_p3_2_identity_bank(source)
    assert len(bank) == 11
    assert [identity.to_dict() for identity in bank] == stage_b["bank"]["identities"]
    import core.models as models
    loaded = []
    for identity in bank:
        assert sha(REPO/identity.checkpoint) == identity.checkpoint_sha256
        model = models.load_identity(identity)
        assert all(bool(runner.torch.isfinite(tensor).all()) for tensor in model.state_dict().values())
        loaded.append({"identity_id":identity.identity_id, "checkpoint_sha256":identity.checkpoint_sha256,
                       "loaded_state_hash":models.state_hash(model), "parameters_loaded":True})
        del model
    print(json.dumps({"phase":"model-load","step":"eleven_source_models_loaded"}),flush=True)
    observer = runner.FrozenA1Observer()
    assert observer.model.training is False
    assert all(bool(runner.torch.isfinite(tensor).all()) for tensor in observer.model.state_dict().values())
    payload = runner.torch.load(REPO/"artifacts/p7_6b_A1_estimator.pt", weights_only=True, map_location="cpu")
    assert observer.multiplier == float(payload["target_multiplier"])
    a1_hash = models.state_hash(observer.model)
    operational = runner.FrozenA1DecisionEstimator()
    assert models.state_hash(operational.model) == a1_hash
    # The final run_one selects this original operational wrapper for baselines
    # (runner lines 261--263), rather than the older inactive P7 constructor.
    legacy_estimator = runner.FrozenOperationalEstimator()
    assert legacy_estimator.model.training is False
    assert all(bool(runner.torch.isfinite(tensor).all()) for tensor in legacy_estimator.model.state_dict().values())
    legacy_estimator_hash = models.state_hash(legacy_estimator.model)
    print(json.dumps({"phase":"model-load","step":"A1_and_original_baseline_estimator_loaded"}),flush=True)
    runtime = adapter.capture_scientific_runtime(runner.torch, runner.np)
    p._verify_current_environment(environment, check_files=False)
    origin_check = p.check_loaded_modules(manifest)
    post = p.check_original_snapshot(REPO, baseline)
    receipt = {"schema":"paper3-frozen-model-load-compatibility-v1", "status":"PASS", "started_utc":started,
               "finished_utc":datetime.now(timezone.utc).isoformat(), "model_runtime_descriptor_sha256":sha(args.model_runtime),
               "environment_binding":p.canonical_hash(environment), "environment_id":"P7_7_REPLICATION_MODEL_ENV_V1",
               "scientific_import_manifest_digest":manifest["manifest_digest"],
               "scientific_import_transition":import_transition,
               "scientific_runtime":runtime, "eleven_source_checkpoints_loaded":loaded,
               "loaded_module_origin_check":origin_check,
               "a1_checkpoint_sha256":sha(REPO/"artifacts/p7_6b_A1_estimator.pt"),
               "a1_scaler_sha256":sha(REPO/"artifacts/p7_6b_A1_scaler.json"), "a1_loaded_state_hash":a1_hash,
               "p6_frozen_estimator_checkpoint_sha256":sha(REPO/"artifacts/p6_recoverability_estimator.pt"),
               "p6_frozen_estimator_scaler_sha256":sha(REPO/"artifacts/p6_recoverability_scaler.json"),
               "p6_frozen_estimator_loaded_state_hash":legacy_estimator_hash,
               "p6_operational_estimator_class":"FrozenOperationalEstimator",
               "p6_operational_scientific_hashes":legacy_estimator.manifest_scientific_hashes,
               "p6_operational_requires_grad_flags":[bool(parameter.requires_grad) for parameter in legacy_estimator.model.parameters()],
               "fixed_F1_input_bundle_digest":stage_b["F1"]["input_bundle_digest"], "original_pre_check":pre,
               "original_post_check":post, "generation_performed":False, "warmup_performed":False,
               "optimizer_called":False, "lifecycle_executed":False, "statistics_performed":False,
               "optimizer_lazy_dependencies_imported":["torch.optim","torch._dynamo"],
               "never_created_pycache_prefix":str(expected_pycache),
               "protocol_selected_from_model_results":False, "historical_environment_reproduced":False,
               "implementation_sha256":sha(__file__)}
    with (check/"model_load_compatibility_receipt.json").open("x", encoding="utf-8") as f:
        json.dump(receipt,f,ensure_ascii=False,sort_keys=True,indent=2); f.write("\n")
    print(json.dumps({"status":"PASS", "source_models_loaded":len(loaded), "a1_loaded":True,
                      "no_warmup_or_optimizer":True, "receipt":str(check/"model_load_compatibility_receipt.json")}), flush=True)

if __name__ == "__main__":
    main()
