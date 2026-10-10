"""Single-core P7.4B driver-crash recovery with own-tree resource watchdog."""
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
sys.path.insert(0, str(ROOT))
from scripts import run_p7_4b_gpu_supervisor as guard

RESULTS = ROOT / "results/p7_4b"
RUNNER = ROOT / "scripts/run_p7_4b_cpu_recovery.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "run"))
    parser.add_argument("--stop-c", type=int, default=75)
    parser.add_argument("--launch-memory-gib", type=float, default=2.3)
    parser.add_argument("--min-memory-gib", type=float, default=1.5)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-minutes", type=float, default=45.0)
    args = parser.parse_args()
    if not 50 <= args.stop_c <= 80 or not 0 < args.interval_seconds <= 2:
        parser.error("invalid temperature threshold or monitor interval")
    if args.timeout_minutes <= 0:
        parser.error("invalid hard timeout")
    for sample in range(2):
        if guard._gpu_temperature() >= args.stop_c:
            raise RuntimeError("GPU already above safety threshold")
        if psutil.virtual_memory().available / 2**30 < args.launch_memory_gib:
            raise RuntimeError("available memory below launch threshold")
        if sample == 0:
            time.sleep(10)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = RESULTS / f"cpu_recovery_{args.command}_{stamp}"
    stdout_path = Path(f"{prefix}_stdout.log")
    stderr_path = Path(f"{prefix}_stderr.log")
    monitor_path = Path(f"{prefix}_monitor.jsonl")
    job = guard._new_kill_on_close_job()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err, monitor_path.open("w", encoding="utf-8") as monitor:
        child = subprocess.Popen([sys.executable, "-u", str(RUNNER), args.command],
                                 cwd=ROOT, stdout=out, stderr=err)
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, child.pid)
            win32job.AssignProcessToJobObject(job, handle)
        except Exception:
            child.kill()
            child.wait(timeout=10)
            raise
        print(f"SUPERVISED_PID={child.pid}", flush=True)
        print(f"STDOUT={stdout_path} STDERR={stderr_path} MONITOR={monitor_path}", flush=True)
        start = time.monotonic()
        low_memory_samples = 0
        try:
            while child.poll() is None:
                try:
                    temperature = guard._gpu_temperature()
                except Exception as exc:
                    guard._stop_own_tree(child, job)
                    raise RuntimeError(f"fail-closed temperature sensor: {exc}") from exc
                available = psutil.virtual_memory().available / 2**30
                low_memory_samples = low_memory_samples + 1 if available < args.min_memory_gib else 0
                monitor.write(json.dumps({
                    "utc": datetime.now(timezone.utc).isoformat(),
                    "gpu_temperature_c": temperature,
                    "available_memory_gib": round(available, 3),
                    "pid": child.pid,
                }) + "\n")
                monitor.flush()
                if temperature >= args.stop_c:
                    guard._stop_own_tree(child, job)
                    raise RuntimeError(f"GPU temperature STOP: {temperature} C")
                if low_memory_samples >= 2:
                    guard._stop_own_tree(child, job)
                    raise RuntimeError("available-memory STOP")
                if time.monotonic() - start > args.timeout_minutes * 60:
                    guard._stop_own_tree(child, job)
                    raise RuntimeError("recovery hard timeout")
                time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            guard._stop_own_tree(child, job)
            raise
        result = child.wait()
    if result:
        raise RuntimeError(f"P7.4B CPU recovery exited {result}; inspect {stderr_path}")
    print(f"P7_4B_CPU_RECOVERY_{args.command.upper()}_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
