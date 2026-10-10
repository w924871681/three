"""Execution realization: bind existing per-adaptation seeds to Torch Dropout."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import torch
import core.p7 as p7
import scripts.run_p7 as runner
from core.models import adapt as frozen_adapt, DEVICE
from core.common import sha256_file
from core.p7 import read_json, save_json

MANIFEST=ROOT/"audits/P7_EXECUTION_RNG_BINDING.json"


def seed_bound_adapt(parent,batch,steps,seed):
    devices=[torch.cuda.current_device()] if DEVICE.type=="cuda" else []
    with torch.random.fork_rng(devices=devices):
        torch.manual_seed(int(seed))
        return frozen_adapt(parent,batch,steps,seed)


def install_seed_binding():
    p7.adapt=seed_bound_adapt
    runner.adapt=seed_bound_adapt
    # initial_model's defining module has its own imported primitive.
    import core.p6 as p6
    p6.adapt=seed_bound_adapt


def verify_binding():
    runner.preflight()
    manifest=read_json(MANIFEST)
    assert manifest["original_pre_outcome_manifest_sha256"]==sha256_file(runner.PRE)
    for rel,expected in manifest["files"].items():
        assert sha256_file(ROOT/rel)==expected,"supplemental execution hash mismatch: "+rel
        payload=subprocess.check_output(["git","show",manifest["execution_binding_git_commit"]+":"+rel],cwd=ROOT)
        assert hashlib.sha256(payload).hexdigest()==expected


def extra_audit():
    result=subprocess.run([sys.executable,"-m","pytest","tests/test_p7_seed_binding.py","-q"],cwd=ROOT,text=True,capture_output=True)
    path=runner.RESULTS/"seed_binding_pytest_output.txt"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(result.stdout+result.stderr,encoding="utf-8",newline="\n")
    assert result.returncode==0,"Dropout pairing audit failed; STOP"


def finalize_with_binding():
    verify_binding()
    extra_audit()
    runner.finalize()
    paths=[MANIFEST,MANIFEST.with_suffix(".sha256"),runner.RESULTS/"seed_binding_pytest_output.txt",
           ROOT/"docs/P7_EXECUTION_RECOVERY.md",Path(__file__),ROOT/"tests/test_p7_seed_binding.py"]
    runner.git("add","--",*[p.relative_to(ROOT).as_posix() for p in paths])
    if runner.git("diff","--cached","--name-only"):
        runner.git("commit","-m","Bind supplemental P7 deterministic adaptation audit; preserve original freezes")


def bind():
    runner.preflight()
    assert not (runner.RESULTS/"raw").exists(),"cannot add execution binding after closed-loop outcomes"
    assert not MANIFEST.exists()
    commit=runner.git("rev-parse","HEAD")
    paths=[Path(__file__),ROOT/"docs/P7_EXECUTION_RECOVERY.md",ROOT/"tests/test_p7_seed_binding.py"]
    hashes={}
    for path in paths:
        rel=path.relative_to(ROOT).as_posix()
        payload=subprocess.check_output(["git","show",commit+":"+rel],cwd=ROOT)
        assert hashlib.sha256(payload).hexdigest()==sha256_file(path)
        hashes[rel]=sha256_file(path)
    save_json(MANIFEST,{"schema":"p7-execution-only-rng-binding-v1","bound_at_utc":datetime.now(timezone.utc).isoformat(),
                       "execution_binding_git_commit":commit,"original_pre_outcome_manifest_sha256":sha256_file(runner.PRE),
                       "closed_loop_outcomes_materialized":False,"estimator_modified":False,"protocol_grids_modified":False,
                       "change":"isolate Torch RNG with existing prespecified adaptation seed; original primitive unchanged","files":hashes})
    MANIFEST.with_suffix(".sha256").write_text(sha256_file(MANIFEST)+"\n",encoding="utf-8",newline="\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["bind","preflight","run","finalize"])
    parser.add_argument("--workers",type=int,default=1)
    args=parser.parse_args()
    if args.command=="bind":bind();return
    verify_binding()
    install_seed_binding()
    runner.ProcessPoolExecutor=partial(runner.ProcessPoolExecutor,initializer=install_seed_binding)
    if args.command=="preflight":print("P7 original + supplemental execution hashes PASS; no outcome materialization")
    elif args.command=="finalize":finalize_with_binding()
    else:
        try:
            runner.materialize(args.workers)
            finalize_with_binding()
        except Exception as exc:
            save_json(runner.RESULTS/"execution_status.json",{"status":"STOPPED_ERROR","error":repr(exc),
                       "updated_at_utc":datetime.now(timezone.utc).isoformat(),"heldout_accessed":False,"alibaba_accessed":False})
            raise


if __name__=="__main__":main()
