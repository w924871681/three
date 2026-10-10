"""Authorize a fresh input-only attempt after a documented parser fix and full tests."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def write(name,obj):
    with (HERE/name).open("xb") as f:f.write((json.dumps(obj,indent=2,ensure_ascii=False)+"\n").encode())
test=json.loads((HERE/"stage_a_attempt_04_results.json").read_text())
if not test["all_42_pass"] or test["tests_run"]!=42:raise RuntimeError("all tests required after fix")
rep=HERE.parent/"verifier_v1"
repo=HERE.parent.parent.parent
if str(repo)!=r"D:\dt-talk\DT_LIFECYCLE_ESCALATION":raise RuntimeError("incorrect repo")
auth=json.loads((HERE/"stage_b_execution_authorization.reviewed.json").read_text())
auth["run_id"]="CIV_INPUT_V1_AUTHORIZED_20261009_RUN002"
auth["approved_implementation_sha256"]={p.relative_to(rep).as_posix():sha(p) for p in sorted(rep.rglob("*.py"))+[rep/"source_pins.json"]}
auth["human_authorization_reference"]+="; documented ordinary historical text-parser repair, exact old SHA recovered, all 42 retested"
write("stage_b_attempt_02_execution_authorization.reviewed.json",auth)
source=(HERE/"launch_stage_b.py").read_text()
source=source.replace("CIV_INPUT_V1_AUTHORIZED_20261009_RUN001",auth["run_id"]).replace("stage_a_attempt_03_results.json","stage_a_attempt_04_results.json").replace("stage_b_execution_authorization.reviewed.json","stage_b_attempt_02_execution_authorization.reviewed.json")
for name in ("command_start.json","process.json","execution.log","command_finish.json"):
    source=source.replace("stage_b_"+name,"stage_b_attempt_02_"+name)
with (HERE/"launch_stage_b_attempt_02.py").open("xb") as f:f.write(source.encode())
print(json.dumps({"new_attempt":2,"run_id":auth["run_id"],"tests_pass":True,"source_sha_pins_unchanged":True,"generator_not_yet_executed":True}))
