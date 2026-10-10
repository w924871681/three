"""Preserve exact evidence of the V1 non-scientific bootstrap failure."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
PRIOR = REPO / "verification/paper3_canonical_inputs/autonomous_replication_execution_20261009"
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v1"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    assert not (RESULTS / "raw").exists()
    assert not (RESULTS / "initial_states").exists()
    failure = RESULTS / "execution/initial/A_INITIAL_0001/W1.log"
    text = failure.read_text(encoding="utf-8")
    assert 'provenance.verify_frozen' in text
    assert 'platform.platform()' in text and 'subprocess/OS execution forbidden inside scientific worker' in text
    files = set(RESULTS.rglob("*")) | set(PRIOR.rglob("*"))
    files |= set((REPO / "verification/paper3_canonical_inputs/replication_executor_batch20_env_v1").glob("*.py"))
    files = sorted(path for path in files if path.is_file())
    bindings = {str(path):sha(path) for path in files}
    value = {
        "schema":"paper3-prior-nonscientific-runtime-evidence-v1",
        "recorded_utc":datetime.now(timezone.utc).isoformat(),
        "status":"V1_INITIAL_BOOTSTRAP_FAILED_BEFORE_SCIENTIFIC_IMPORTS",
        "scientific_trajectories_completed":0,
        "initial_state_certificates_published":0,
        "new_model_generation_or_warmup_performed_by_this_recorder":False,
        "performance_used_for_version_selection":False,
        "prior_source_manifest":read(RESULTS / "provenance_manifest.json")["manifest_digest"],
        "prior_prepare_terminal":read(PRIOR / "phase_launches/prepare_001/finish.json"),
        "prior_initial_terminal":read(PRIOR / "phase_launches/initial_001/finish.json"),
        "verified_failure":"Windows stdlib platform.platform invokes VER via subprocess after the scientific-worker prohibition was installed",
        "evidence_trace":"executor_worker.py _prepare:84 fails in verify_frozen; scientific package/model imports start only at later _prepare lines and _initial is never reached",
        "original_results_overwritten":False,
        "prior_evidence_sha256":bindings,
        "implementation_sha256":sha(__file__),
        "next_run_rule":"new exclusive V2 source/output identity; same approved environment, immutable F1, science algorithm and result-blind gates"
    }
    with (HERE / "V1_BOOTSTRAP_FAILURE_PROVENANCE.json").open("x",encoding="utf-8") as out:
        json.dump(value,out,ensure_ascii=False,sort_keys=True,indent=2)
        out.write("\n")
    print(json.dumps({"status":value["status"],"prior_bound_files":len(bindings)}))

if __name__ == "__main__":
    main()
