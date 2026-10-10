"""Interrupt and resume one CUDA test-only trajectory using P7.6B receipts."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from p7_6b_qualification_monitor import gpu_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/p7_6b_qualification"
PYTHON = Path(sys.executable)
sys.path.insert(0, str(ROOT))
from scripts import run_p7_6b as runner  # noqa: E402


def main() -> None:
    task = runner.Task(90000, 7311, "C0", "test-only-protocol", "test-only-generator", "test-only-behavior")
    runtime_sha = runner.sha256_file(ROOT / "scripts/p7_6b_full_trajectory_qualification.py")
    resume_root = OUT / "resume_receipts"
    runner.RESULTS = resume_root
    if resume_root.exists() or (OUT / "cuda_resume_90000_C0").exists():
        raise RuntimeError("refusing to overwrite test-only resume artifacts")
    if runner.validate_receipt("fit", task, runtime_sha):
        raise RuntimeError("unexpected completed receipt")
    command = [str(PYTHON), "-u", "scripts/p7_6b_full_trajectory_qualification.py",
               "--device", "cuda", "--center-id", "90000", "--seed", "7311",
               "--scenario", "C0", "--threads", "1", "--tag", "cuda_interrupted_90000_C0"]
    interrupted_stdout = OUT / "cuda_interrupted_90000_C0_stdout.log"
    interrupted_stderr = OUT / "cuda_interrupted_90000_C0_stderr.log"
    if interrupted_stdout.exists() or interrupted_stderr.exists():
        raise RuntimeError("refusing to overwrite interruption logs")
    interrupted_stage = None
    with interrupted_stdout.open("x", encoding="utf-8") as so, interrupted_stderr.open("x", encoding="utf-8") as se:
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=se,
                                   text=True, bufsize=1)
        start = time.monotonic()
        try:
            for line in process.stdout:
                so.write(line); so.flush()
                event = json.loads(line)
                gpu = gpu_sample()
                if "error" in gpu or float(gpu["temperature_C"]) >= 78:
                    raise RuntimeError(f"unsafe GPU telemetry during interruption: {gpu}")
                if event.get("event") == "stage_decision" and event.get("stage", 0) >= 4:
                    interrupted_stage = event["stage"]
                    break
                if time.monotonic() - start > 120:
                    raise RuntimeError("interruption point not reached within 120 seconds")
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
    if interrupted_stage is None or runner.validate_receipt("fit", task, runtime_sha):
        raise RuntimeError("intentional interruption did not leave task incomplete")
    clean = json.loads((OUT / "cuda_tfgpu_trial3_90000_C0/summary.json").read_text())
    resume_command = [str(PYTHON), "-u", "scripts/p7_6b_qualification_monitor.py",
                      "--python", str(PYTHON), "--device", "cuda", "--center-id", "90000",
                      "--seed", "7311", "--scenario", "C0", "--tag", "cuda_resume_90000_C0",
                      "--threads", "1", "--timeout-seconds", "120"]
    completed = subprocess.run(resume_command, cwd=ROOT, capture_output=True, text=True, timeout=145)
    if completed.returncode:
        raise RuntimeError(f"test-only resumed CUDA trajectory failed: {completed.stdout[-1000:]} {completed.stderr[-1000:]}")
    resumed_dir = OUT / "cuda_resume_90000_C0"
    resumed = json.loads((resumed_dir / "summary.json").read_text())
    scientific = ("candidate_diagnostics.json", "scales.csv", "stagewise.json", "state_vectors.npz")
    exact_science = {name: clean["files_sha256"][name] == resumed["files_sha256"][name]
                     for name in scientific}
    if not all(exact_science.values()) or clean["action_sequence"] != resumed["action_sequence"]:
        raise RuntimeError("resumed CUDA science differs from clean uninterrupted run")
    csv, scales, receipt, _ = runner.output_paths("fit", task)
    runner.atomic_bytes(csv, (resumed_dir / "trajectory.csv").read_bytes())
    runner.atomic_bytes(scales, (resumed_dir / "scales.csv").read_bytes())
    value = {"schema": "p7.6b-paired-trajectory-integrity-v1", "trajectory_id": task.key,
             "center_id": task.center_id, "model_seed": task.model_seed, "scenario": task.scenario,
             "protocol_sha256": task.protocol_sha256, "generator_sha256": task.generator_sha256,
             "behavior_sha256": task.behavior_sha256, "runtime_config_sha256": runtime_sha,
             "status": "COMPLETE", "rows": 24, "all_stage_path_matches": True,
             "trajectory_sha256": runner.sha256_file(csv), "scales_sha256": runner.sha256_file(scales)}
    runner.atomic_json(receipt, value)
    if not runner.validate_receipt("fit", task, runtime_sha):
        raise RuntimeError("completed CUDA receipt rejected")
    before = (runner.sha256_file(csv), runner.sha256_file(scales), runner.sha256_file(receipt))
    # The resumed scheduler's completed-task branch: no child is launched.
    skipped = runner.validate_receipt("fit", task, runtime_sha)
    after = (runner.sha256_file(csv), runner.sha256_file(scales), runner.sha256_file(receipt))
    if not skipped or before != after:
        raise RuntimeError("completed CUDA task was not skipped without mutation")
    audit = {"schema": "p7.6b-test-only-cuda-resume-v1", "test_only": True,
             "center_id": 90000, "interrupted_after_stage": interrupted_stage,
             "incomplete_receipt_before_resume": True, "clean_scientific_sha256_equal": exact_science,
             "completed_receipt_valid": True, "completed_task_skipped": skipped,
             "receipt_sha256_unchanged_on_skip": before == after,
             "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False}
    runner.atomic_json(OUT / "resume_test_audit.json", audit)
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
