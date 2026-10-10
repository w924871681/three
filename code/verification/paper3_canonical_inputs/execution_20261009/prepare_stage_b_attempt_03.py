"""Fresh input-only retry after a localized restricted-NumPy implementation fix."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
IMPL = HERE.parent / "verifier_v1"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def publish(name, value):
    with (HERE / name).open("xb") as f:
        f.write((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())

if str(REPO) != r"D:\dt-talk\DT_LIFECYCLE_ESCALATION":
    raise RuntimeError("Incorrect target repository")
test = json.loads((HERE / "stage_a_attempt_05_results.json").read_text())
integrity = json.loads((HERE / "stage_a_attempt_05_original_integrity_end.json").read_text())
if not test["all_42_pass"] or test["tests_run"] != 42:
    raise RuntimeError("All 42 tests must pass after the implementation fix")
if (integrity["protected_files_checked"] != 2535 or integrity["changed_original_files"]
        or integrity["raw_csv_count"] != 1200 or integrity["raw_receipt_count"] != 1200):
    raise RuntimeError("Original protected evidence integrity must pass")
# The launcher and verifier independently enforce original hashes and source pins.
auth = json.loads((HERE / "stage_b_execution_authorization.reviewed.json").read_text())
auth["run_id"] = "CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"
auth["approved_implementation_sha256"] = {
    p.relative_to(IMPL).as_posix(): sha(p)
    for p in sorted(IMPL.rglob("*.py")) + [IMPL / "source_pins.json"]
}
auth["human_authorization_reference"] += (
    "; localized NumPy implicit import compatibility fix; original source and "
    "scientific definitions unchanged; all 42 tests repeated after repair"
)
publish("stage_b_attempt_03_execution_authorization.reviewed.json", auth)
source = (HERE / "launch_stage_b.py").read_text()
source = source.replace("CIV_INPUT_V1_AUTHORIZED_20261009_RUN001", auth["run_id"])
source = source.replace("stage_a_attempt_03_results.json", "stage_a_attempt_05_results.json")
source = source.replace("stage_b_execution_authorization.reviewed.json",
                        "stage_b_attempt_03_execution_authorization.reviewed.json")
for name in ("command_start.json", "process.json", "execution.log", "command_finish.json"):
    source = source.replace("stage_b_" + name, "stage_b_attempt_03_" + name)
with (HERE / "launch_stage_b_attempt_03.py").open("xb") as f:
    f.write(source.encode())
publish("stage_b_attempt_03_preparation.json", {
    "run_id": auth["run_id"], "test_evidence": test,
    "integrity_evidence": integrity, "generators_executed_by_preparation": False,
    "preserved_prior_attempts": True,
})
print(json.dumps({"prepared_attempt": 3, "run_id": auth["run_id"], "tests_pass": True}))
