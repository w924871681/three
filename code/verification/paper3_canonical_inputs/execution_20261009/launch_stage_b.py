"""Authorized launcher: exact verifier command, exclusive logs, no project imports."""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

REPO=Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE=Path(__file__).resolve().parent
RUN_ID="CIV_INPUT_V1_AUTHORIZED_20261009_RUN001"
root=REPO/"verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1"/RUN_ID
if root.exists():raise RuntimeError("Stage B run collision; no overwrite")
results=json.loads((HERE/"stage_a_attempt_03_results.json").read_text())
if not results["all_42_pass"] or results["tests_run"]!=42:raise RuntimeError("Stage A not passed")
command=[sys.executable,"-I","-S","-B","-X",f"pycache_prefix={root/'_never_created_pycache'}",
    str(REPO/"verification/paper3_canonical_inputs/verifier_v1/verify_inputs.py"),"--repo",str(REPO),
    "--authorization-file",str(HERE/"stage_b_execution_authorization.reviewed.json"),"--run-id",RUN_ID]
def publish(name,value):
    with (HERE/name).open("xb") as handle:handle.write((json.dumps(value,indent=2,ensure_ascii=False)+"\n").encode())
publish("stage_b_command_start.json",{"command":command,"started_utc":datetime.now(timezone.utc).isoformat(),
    "scope":"AUTHORIZED_STAGE_B_INPUT_ONLY","generators_authorized":True,"models_authorized":False,"statistics_authorized":False})
with (HERE/"stage_b_execution.log").open("xb") as log:
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    publish("stage_b_process.json",{"pid":child.pid,"started_utc":datetime.now(timezone.utc).isoformat()})
    result=child.wait()
publish("stage_b_command_finish.json",{"exit_code":result,"finished_utc":datetime.now(timezone.utc).isoformat(),"run_root":str(root)})
print(json.dumps({"stage_b_exit_code":result,"run_root":str(root)},ensure_ascii=False))
raise SystemExit(result)
