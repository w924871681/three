"""Fail-closed thermal/memory supervisor for P7.4B's GPU-only finalizer.

The Windows Job Object kills the spawned experiment tree if this supervisor
exits unexpectedly.  No unrelated process is inspected for termination.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import win32api
import win32con
import win32job


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/p7_4b"
RUNNER = ROOT / "scripts/run_p7_4b_gpu_finalize.py"


def _gpu_temperature() -> int:
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        text=True, capture_output=True, timeout=5, check=False,
    )
    if query.returncode:
        raise RuntimeError(f"GPU temperature query failed: {query.stderr[-500:]}")
    lines = query.stdout.strip().splitlines()
    if len(lines) != 1:
        raise RuntimeError("expected exactly one GPU temperature reading")
    return int(lines[0].strip())


def _new_kill_on_close_job():
    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    return job


def _stop_own_tree(child: subprocess.Popen, job) -> None:
    if child.poll() is None:
        win32job.TerminateJobObject(job, 1)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Terminate only the known process tree as a fallback.
            descendants = psutil.Process(child.pid).children(recursive=True)
            for process in reversed(descendants):
                process.kill()
            psutil.Process(child.pid).kill()
            child.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "run"))
    parser.add_argument("--gpu-python", type=Path, required=True)
    parser.add_argument("--stop-c", type=int, default=75)
    parser.add_argument("--launch-memory-gib", type=float, default=2.3)
    parser.add_argument("--min-memory-gib", type=float, default=1.5)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 50 <= args.stop_c <= 80:
        parser.error("thermal stop threshold must be between 50 and 80 C")
    if args.interval_seconds > 2.0 or args.interval_seconds <= 0:
        parser.error("thermal polling interval must be in (0, 2] seconds")
    if not args.gpu_python.is_file():
        parser.error("GPU Python runtime does not exist")
    for sample in range(2):
        if _gpu_temperature() >= args.stop_c:
            raise RuntimeError("GPU is already at or above the stop temperature")
        if psutil.virtual_memory().available / 2**30 < args.launch_memory_gib:
            raise RuntimeError("available memory is below the launch boundary")
        if sample == 0:
            time.sleep(10)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout_path = RESULTS / f"gpu_finalize_{args.command}_{stamp}_stdout.log"
    stderr_path = RESULTS / f"gpu_finalize_{args.command}_{stamp}_stderr.log"
    monitor_path = RESULTS / f"gpu_finalize_{args.command}_{stamp}_monitor.jsonl"
    command = [
        sys.executable, "-u", str(RUNNER), args.command,
        "--gpu-python", str(args.gpu_python),
    ]
    job = _new_kill_on_close_job()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err, monitor_path.open("w", encoding="utf-8") as monitor:
        child = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=err)
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, child.pid)
            win32job.AssignProcessToJobObject(job, handle)
        except Exception:
            child.kill()
            child.wait(timeout=10)
            raise
        print(f"SUPERVISED_PID={child.pid} COMMAND={' '.join(command)}", flush=True)
        print(f"STDOUT={stdout_path} STDERR={stderr_path} MONITOR={monitor_path}", flush=True)
        low_memory_samples = 0
        try:
            while child.poll() is None:
                try:
                    temperature = _gpu_temperature()
                except Exception as exc:
                    _stop_own_tree(child, job)
                    raise RuntimeError(f"fail-closed GPU temperature monitor: {exc}") from exc
                available = psutil.virtual_memory().available / 2**30
                low_memory_samples = low_memory_samples + 1 if available < args.min_memory_gib else 0
                observation = {
                    "utc": datetime.now(timezone.utc).isoformat(),
                    "gpu_temperature_c": temperature,
                    "available_memory_gib": round(available, 3),
                    "pid": child.pid,
                }
                monitor.write(json.dumps(observation) + "\n")
                monitor.flush()
                if temperature >= args.stop_c:
                    _stop_own_tree(child, job)
                    raise RuntimeError(f"GPU thermal STOP: {temperature} C >= {args.stop_c} C")
                if low_memory_samples >= 2:
                    _stop_own_tree(child, job)
                    raise RuntimeError(f"memory STOP: two samples below {args.min_memory_gib} GiB")
                time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            _stop_own_tree(child, job)
            raise
        result = child.wait()
    if result:
        raise RuntimeError(f"P7.4B GPU finalizer exited {result}; inspect {stderr_path}")
    print(f"P7_4B_GPU_{args.command.upper()}_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
