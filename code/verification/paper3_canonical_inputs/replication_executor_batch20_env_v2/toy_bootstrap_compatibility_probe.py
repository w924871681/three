"""Authorized synthetic tensor/SGD probe of the new bootstrap/import guard.

No project model, source checkpoint, estimator, canonical array, generator,
warm-up or trajectory is imported/read/executed. This is not scientific output.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RESULTS = REPO/"results/p7_7_integrity_replication_batch20_env_v2"
V1_METADATA = REPO/"results/p7_7_integrity_replication_batch20_env_v1/provenance_manifest.json"


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--attempt",type=int,required=True)
    args=parser.parse_args()
    assert args.attempt>=1 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    output=RESULTS/"stage_c_tests/toy_bootstrap"/f"attempt{args.attempt:03d}"
    assert not output.exists(),"exclusive toy probe already exists"
    assert sys.pycache_prefix is not None and Path(sys.pycache_prefix)==output/"_never_created_pycache" and not Path(sys.pycache_prefix).exists()
    for path in (output,*output.parents):
        if path.exists() or path.is_symlink():
            assert not path.is_symlink() and not getattr(path.lstat(),"st_file_attributes",0)&0x400
    output.mkdir(parents=True)
    for name in ("TEMP","TMP","TORCH_HOME","CUDA_CACHE_PATH"):
        folder=output/"runtime_cache"/name.lower();folder.mkdir(parents=True)
        os.environ[name]=str(folder)
    started=datetime.now(timezone.utc).isoformat()
    package=types.ModuleType("paper3_bootstrap_toy")
    package.__path__=[str(ROOT)]
    sys.modules[package.__name__]=package
    spec=importlib.util.spec_from_file_location(package.__name__+".provenance",ROOT/"provenance.py")
    p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
    # Read only the already approved current environment binding. Do not follow
    # any input/checkpoint path or import the original runner/adapter.
    with V1_METADATA.open(encoding="utf-8") as stream:environment=json.load(stream)["environment"]
    sources={path.relative_to(ROOT).as_posix():sha(path) for path in ROOT.rglob("*.py")}
    manifest={"paths":{"repo":str(REPO),"executor_root":str(ROOT),"results_root":str(RESULTS)},
              "environment":environment,"original_python_dependency_sha256":{},"executor_sha256":sources}
    baseline=p.read_json(REPO/"verification/paper3_canonical_inputs/execution_20261009/original_protected_start_sha256.json")
    original_before=p.check_original_snapshot(REPO,baseline)
    print("TOY_BOOTSTRAP_PLATFORM_STARTED",flush=True)
    platform_values=dict(p.bootstrap_platform_metadata())
    p.install_write_guard(RESULTS)
    print("TOY_GUARD_ENVIRONMENT_START",flush=True)
    p._verify_current_environment(environment,check_files=True)
    p.install_generator_guard(REPO)
    p.install_model_import_guard(manifest)
    sys.path.append(environment["site_packages_root"])
    print("TOY_REAL_TORCH_IMPORT_STARTED",flush=True)
    import torch
    import torch.optim
    import torch._dynamo
    assert str(torch.__version__)=="2.5.1+cu121"
    # Literal CPU-only synthetic tensor; no RNG/seed, data population or source
    # model is involved. The optimizer is real and remains subprocess guarded.
    parameter=torch.tensor([2.0],dtype=torch.float32,device="cpu",requires_grad=True)
    optimizer=torch.optim.SGD([parameter],lr=0.1)
    optimizer.zero_grad();(parameter.square().sum()).backward();optimizer.step()
    assert torch.allclose(parameter.detach(),torch.tensor([1.6],dtype=torch.float32),atol=1e-6,rtol=0)
    assert torch.isfinite(parameter).all()
    subprocess_denied=False
    try:sys.audit("subprocess.Popen","not-executed-synthetic-check",[],None,None)
    except p.ProvenanceError:subprocess_denied=True
    assert subprocess_denied
    assert dict(p.bootstrap_platform_metadata())==platform_values
    origins=p.check_loaded_modules(manifest)
    print("TOY_POST_ENVIRONMENT_START",flush=True)
    p._verify_current_environment(environment,check_files=True)
    assert {path.relative_to(ROOT).as_posix():sha(path) for path in ROOT.rglob("*.py")}==sources
    original_after=p.check_original_snapshot(REPO,baseline)
    assert not any(name.partition(".")[0] in {"core","scripts","imported"} for name in sys.modules)
    receipt={"schema":"paper3-synthetic-toy-bootstrap-compatibility-v1","status":"PASS",
        "started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),"attempt":args.attempt,
        "environment_binding":p.canonical_hash(environment),"approved_environment_manifest_sha256":sha(V1_METADATA),
        "implementation_sha256":sources,"platform_values":platform_values,
        "same_platform_as_frozen_environment":platform_values["platform"]==environment["platform"],
        "write_and_subprocess_guard_installed":True,"post_guard_subprocess_denied":subprocess_denied,
        "loaded_module_origin_check":origins,"real_synthetic_cpu_tensor_and_SGD_step_passed":True,
        "torch_optimizer_lazy_dependencies_imported":["torch.optim","torch._dynamo"],
        "project_models_or_estimators_loaded":False,"canonical_inputs_read":False,"source_checkpoints_read":False,
        "warmup_or_trajectory_executed":False,"statistics_executed":False,"random_seed_set":False,
        "original_before_check":original_before,"original_after_check":original_after,
        "scientific_experiment_certification":False,"probe_selected_from_model_performance":False}
    published=p.publish_json(RESULTS,output.relative_to(RESULTS).as_posix()+"/TOY_BOOTSTRAP_COMPATIBILITY_RECEIPT.json",receipt)
    print(json.dumps({"status":"PASS","receipt":published}),flush=True)


if __name__=="__main__":main()
