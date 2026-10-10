"""Exclusive, timestamped launch records for explicitly authorized phases.

No scientific logic is implemented here. Commands target only the new executor,
new environment, fixed existing F1, and new outputs. Prior attempts are retained.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
ENV = REPO/"verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/P7_7_REPLICATION_MODEL_ENV_V1"
EXECUTOR = REPO/"verification/paper3_canonical_inputs/replication_executor_batch20_env_v1"
STATS = REPO/"verification/paper3_canonical_inputs/replication_statistics_batch20_env_v1"
RESULTS = REPO/"results/p7_7_integrity_replication_batch20_env_v1"

def utc():
    return datetime.now(timezone.utc).isoformat()

def publish(path, obj):
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,sort_keys=True,indent=2);f.write("\n")

def snapshot_sources(record, invoked_script):
    files = {"launcher":Path(__file__).resolve(), "invoked_script":Path(invoked_script).resolve()}
    bindings = {}
    for name,path in files.items():
        payload = path.read_bytes()
        target = record/(name+"_source_snapshot.py")
        with target.open("xb") as handle:
            handle.write(payload)
        bindings[str(path)] = hashlib.sha256(payload).hexdigest()
    for directory in (EXECUTOR, STATS):
        for path in sorted(directory.rglob("*.py")):
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    publish(record/"launch_source_sha256.json",bindings)
    return bindings

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("model-load","prepare","initial","minimal","full","statistics"), required=True)
    parser.add_argument("--model-runtime", type=Path, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--test-attempt", type=int, default=2)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    assert args.attempt >= 1 and 1 <= args.workers <= 3
    record = HERE/"phase_launches"/f"{args.phase}_{args.attempt:03d}"
    for path in (record,*record.parents):
        if path.exists() or path.is_symlink():
            info = path.lstat()
            assert not path.is_symlink() and not getattr(info,"st_file_attributes",0)&0x400, "phase path reparse point forbidden"
    assert record.resolve().is_relative_to(HERE.resolve()), "phase record escaped parent execution directory"
    assert not record.exists(), "exclusive phase launch already exists"
    record.mkdir(parents=True)
    command = [str(ENV/"Scripts/python.exe"),"-I","-S","-B","-X",f"pycache_prefix={RESULTS/'_never_created_driver_pycache'}"]
    if args.phase == "model-load":
        command[-1] = f"pycache_prefix={HERE/'compatibility_checks'/f'attempt{args.attempt:03d}'/'_never_created_pycache'}"
        command += [str(HERE/"model_load_compatibility.py"),"--model-runtime",str(args.model_runtime),"--attempt",str(args.attempt)]
    elif args.phase == "statistics":
        manifest = json.loads((RESULTS/"provenance_manifest.json").read_text(encoding="utf-8"))
        command += [str(STATS/"run_statistics.py"),"--expected-manifest-digest",manifest["manifest_digest"]]
    else:
        command += [str(EXECUTOR/"executor_driver.py"),"--phase",args.phase,"--workers",str(args.workers),"--test-attempt",str(args.test_attempt)]
        if args.phase == "prepare":
            command += ["--model-runtime",str(args.model_runtime)]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    source_bindings = snapshot_sources(record, command[6])
    # Numerical variables are inherited unchanged. Only cache paths and console
    # encoding are isolated; neither changes model computation or random seeds.
    if args.phase == "statistics":
        for name in ("TEMP","TMP","TORCH_HOME","CUDA_CACHE_PATH"):
            target = RESULTS/"runtime_cache"/f"STATISTICS_{args.attempt:03d}"/name.lower()
            target.mkdir(parents=True,exist_ok=False)
            env[name] = str(target)
    start = {"phase":args.phase,"attempt":args.attempt,"started_utc":utc(),"command":command,"cwd":str(REPO),
             "model_runtime_descriptor":str(args.model_runtime),"workers":args.workers if args.phase in {"minimal","full"} else (1 if args.phase=="initial" else 0),
             "logging_environment_overrides":{"PYTHONIOENCODING":"utf-8"},
             "launch_source_sha256":source_bindings,
             "model_runtime_descriptor_sha256":hashlib.sha256(args.model_runtime.read_bytes()).hexdigest(),
             "ordinary_failure_recovery_authorized":True,"performance_based_continuation":False,"original_results_reused":False}
    publish(record/"start.json",start)
    with (record/"stdout.log").open("xb") as out, (record/"stderr.log").open("xb") as err:
        process = subprocess.Popen(command,cwd=REPO,env=env,stdout=out,stderr=err)
        publish(record/"process.json",{"pid":process.pid,"launcher_pid":os.getpid(),"started_utc":utc()})
        print(json.dumps({"phase":args.phase,"pid":process.pid,"records":str(record)}),flush=True)
        code = process.wait()
    finish = {"phase":args.phase,"attempt":args.attempt,"finished_utc":utc(),"exit_code":code,"command":command,
              "outputs_and_failure_logs_preserved":True,"scientific_protocol_changed":False}
    changed = [path for path,digest in source_bindings.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest]
    finish["launch_source_bindings_unchanged"] = not changed
    finish["changed_source_paths"] = changed
    finish["child_exit_code"] = code
    if changed:
        code = 1
        finish["exit_code"] = code
    publish(record/"finish.json",finish)
    print(json.dumps(finish),flush=True)
    if code:
        print((record/"stderr.log").read_text(encoding="utf-8",errors="replace")[-12000:],flush=True)
    else:
        print((record/"stdout.log").read_text(encoding="utf-8",errors="replace")[-4000:],flush=True)
    raise SystemExit(code)

if __name__ == "__main__":
    main()
