"""Continue explicit researcher-authorized phases through saved, actual gates.

Stdlib only. No outcome is examined to choose whether to continue. Scientific
checks remain in the frozen independent executors; errors stop this sequence
and retain all attempts for diagnosis rather than claiming experiment success.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
RESULTS = REPO/"results/p7_7_integrity_replication_batch20_env_v2"
RUNTIME = REPO/"verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/MODEL_RUNTIME_SPEC.json"
RUNTIME_SHA = "7e029514ff3d955f1c6046eb8c339580f6cef7f192f95df7456191c855e9b425"
F1 = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"

def utc(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(path.read_text(encoding="utf-8"))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def publish(path,value):
    with path.open("x",encoding="utf-8") as out:
        json.dump(value,out,sort_keys=True,ensure_ascii=False,indent=2);out.write("\n")

def model_gate(attempt):
    terminal = HERE/"phase_launches"/f"model-load_{attempt:03d}"/"finish.json"
    while not terminal.exists(): time.sleep(5)
    result = read(terminal)
    assert result["exit_code"] == 0, "model-load process did not pass"
    proof_path = HERE/"compatibility_checks"/f"attempt{attempt:03d}"/"model_load_compatibility_receipt.json"
    proof = read(proof_path)
    assert proof["status"] == "PASS" and proof["model_runtime_descriptor_sha256"] == RUNTIME_SHA
    assert proof["fixed_F1_input_bundle_digest"] == F1 and len(proof["eleven_source_checkpoints_loaded"]) == 11
    assert proof["loaded_module_origin_check"]["loaded_module_file_bindings_valid"] is True
    assert all(proof[name] is False for name in ("generation_performed","warmup_performed","optimizer_called","lifecycle_executed","statistics_performed"))
    assert proof["original_post_check"]["all_original_bytes_unchanged"] is True
    assert proof["implementation_sha256"] == sha(HERE/"model_load_compatibility.py")
    launch = read(terminal.parent/"start.json")
    for path,digest in launch["launch_source_sha256"].items():
        target = terminal.parent/"launcher_source_snapshot.py" if Path(path)==HERE/"phase_launcher.py" else Path(path)
        assert sha(target)==digest
    return {"receipt":str(proof_path),"sha256":sha(proof_path),"terminal_sha256":sha(terminal)}

def phase_gate(phase):
    manifest = read(RESULTS/"provenance_manifest.json")
    assert manifest["schema"] == "paper3-integrity-replication-provenance-v1"
    digest = manifest["manifest_digest"]
    if phase=="prepare":
        x=manifest
        assert x["input_bundle_digest"] == F1
        return {"manifest_digest":x["manifest_digest"]}
    if phase=="initial":
        x=read(RESULTS/"initial_state_manifest.json")
        assert x["schema"] == "paper3-batch20-initial-state-manifest-v1"
        assert x["completed_cases"] == 60 and len(x["states"]) == 60
    elif phase=="minimal":
        x=read(RESULTS/"stage_c_minimal_gate.json")
        assert x["stage_c_pass"] is True and x["completed_trajectories"] == 5
        assert x["performance_used_for_gate"] is False
    elif phase=="full":
        x=read(RESULTS/"full_experiment_integrity_gate.json")
        assert x["scientific_integrity_pass"] is True and x["trajectories"] == 1200 and x["paired_groups"] == 240
        assert x["all_inputs_F1"] is True and x["old_results_reused"] is False
    else:
        x=read(RESULTS/"statistics_batch20_env_v2"/"statistics_execution_receipt.json")
        assert x["schema"] == "paper3-statistics-execution-receipt-v1"
        assert x["status"] == "COMPLETED" and x["exit_code"] == 0
    assert (x["replication_manifest_digest"] if phase=="statistics" else x["manifest_digest"]) == digest
    return {"gate_checked":True,"phase":phase}

def main():
    sys.stdout.reconfigure(encoding="utf-8",errors="backslashreplace")
    ap=argparse.ArgumentParser()
    ap.add_argument("--sequence-attempt",type=int,required=True)
    ap.add_argument("--model-load-attempt",type=int,default=1)
    ap.add_argument("--workers",type=int,default=1)
    args=ap.parse_args()
    assert args.sequence_attempt>=1 and 1<=args.workers<=3
    record=HERE/f"authorized_sequence_{args.sequence_attempt:03d}"
    assert not record.exists()
    for path in (record,*record.parents):
        if path.exists() or path.is_symlink():
            assert not path.is_symlink() and not getattr(path.lstat(),"st_file_attributes",0)&0x400
    assert record.resolve().is_relative_to(HERE.resolve())
    record.mkdir()
    with (record/"sequence_source_snapshot.py").open("xb") as out:
        out.write(Path(__file__).read_bytes())
    publish(record/"start.json",{"started_utc":utc(),"implementation_sha256":sha(__file__),
        "workers":args.workers,"outcome_based_continuation":False,"no_source_or_environment_changes":True})
    current="model-load-gate"
    try:
        assert sha(RUNTIME)==RUNTIME_SHA
        publish(record/"model_load_gate.json",model_gate(args.model_load_attempt))
        for phase in ("prepare","initial","minimal","full","statistics"):
            current=phase
            prior=HERE/"phase_launches"/f"{phase}_001"
            assert not prior.exists(), "a prior phase launch requires independent resume review"
            command=[sys.executable,"-I","-S","-B",str(HERE/"phase_launcher.py"),
                "--phase",phase,"--model-runtime",str(RUNTIME),"--attempt","1","--test-attempt","3",
                "--workers",str(args.workers if phase in {"minimal","full"} else 1)]
            publish(record/(phase+"_start.json"),{"started_utc":utc(),"command":command})
            print(json.dumps({"phase":phase,"status":"STARTED"}),flush=True)
            code=subprocess.call(command,cwd=REPO)
            assert code==0, f"authorized phase exited unsuccessfully: {phase}, {code}"
            gate=phase_gate(phase)
            publish(record/(phase+"_passed.json"),{"finished_utc":utc(),"gate":gate,"exit_code":code})
            print(json.dumps({"phase":phase,"status":"PASSED"}),flush=True)
        publish(record/"finish.json",{"finished_utc":utc(),"status":"AUTHORIZED_PHASE_SEQUENCE_COMPLETED",
            "not_a_whole_manuscript_freeze":True,"final_independent_review_and_delivery_pending":True})
    except BaseException as error:
        publish(record/"stopped.json",{"finished_utc":utc(),"status":"STOPPED_FOR_DIAGNOSIS","phase":current,
            "exception_type":type(error).__name__,"message":str(error),"scientific_pass_claimed":False,
            "original_outputs_preserved":True})
        raise

if __name__=="__main__": main()
