"""Bounded two-process CUDA test-only full-trajectory benchmark."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from p7_6b_qualification_monitor import gpu_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/p7_6b_qualification"
PYTHON = Path(sys.executable)
TASKS = ((90000, "C0", "cuda2_90000_C0"), (90001, "C3", "cuda2_90001_C3"))


def main() -> None:
    if not PYTHON.is_file():
        raise RuntimeError("CUDA qualification Python unavailable")
    gpu = gpu_sample()
    if "error" in gpu or float(gpu["temperature_C"]) >= 70 or float(gpu["free_VRAM_MiB"]) < 2500:
        raise RuntimeError(f"unsafe CUDA-2 preflight: {gpu}")
    if psutil.virtual_memory().available < 3.0 * 2**30:
        raise RuntimeError("less than 3 GiB host memory before CUDA-2")
    log_path = OUT / "cuda2_benchmark_monitor.jsonl"
    if log_path.exists():
        raise RuntimeError(f"refusing to overwrite {log_path}")
    handles = []
    processes = []
    start = time.monotonic()
    stop_reason = None
    try:
        for center, scenario, tag in TASKS:
            stdout = OUT / f"{tag}_stdout.log"
            stderr = OUT / f"{tag}_stderr.log"
            if any(p.exists() for p in (stdout, stderr, OUT / tag)):
                raise RuntimeError(f"refusing to overwrite {tag}")
            so, se = stdout.open("x", encoding="utf-8"), stderr.open("x", encoding="utf-8")
            handles += [so, se]
            command = [str(PYTHON), "-u", "scripts/p7_6b_full_trajectory_qualification.py",
                       "--device", "cuda", "--center-id", str(center), "--scenario", scenario,
                       "--seed", "7311", "--tag", tag, "--threads", "1"]
            p = subprocess.Popen(command, cwd=ROOT, stdout=so, stderr=se)
            processes.append((p, tag))
        hot_count = low_count = 0
        with log_path.open("x", encoding="utf-8") as log:
            while any(p.poll() is None for p, _ in processes):
                gpu = gpu_sample()
                memory = psutil.virtual_memory()
                elapsed = time.monotonic() - start
                proc_stats = []
                for p, tag in processes:
                    try:
                        proc = psutil.Process(p.pid)
                        info = proc.memory_info()
                        proc_stats.append({"tag": tag, "pid": p.pid, "exit_code": p.poll(),
                                           "rss_MiB": info.rss / 2**20,
                                           "private_MiB": getattr(info, "private", 0) / 2**20,
                                           "cpu_seconds": sum(proc.cpu_times()[:2])})
                    except psutil.NoSuchProcess:
                        proc_stats.append({"tag": tag, "pid": p.pid, "exit_code": p.poll()})
                record = {"utc": datetime.now(timezone.utc).isoformat(), "elapsed_s": elapsed,
                          "gpu": gpu, "host_available_GiB": memory.available / 2**30,
                          "processes": proc_stats}
                log.write(json.dumps(record) + "\n"); log.flush()
                if "error" in gpu:
                    stop_reason = "lost GPU thermal telemetry"
                    break
                hot_count = hot_count + 1 if float(gpu["temperature_C"]) >= 78 else 0
                low_count = low_count + 1 if memory.available < 1.5 * 2**30 else 0
                if hot_count >= 2 or low_count >= 2 or elapsed > 180:
                    stop_reason = ("GPU at least 78 C" if hot_count >= 2 else
                                   "host memory below 1.5 GiB" if low_count >= 2 else "timeout")
                    break
                time.sleep(2)
        if stop_reason:
            for p, _ in processes:
                if p.poll() is None:
                    p.terminate()
            for p, _ in processes:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait()
        codes = {tag: p.wait() for p, tag in processes}
        output = {"wall_seconds": time.monotonic() - start, "exit_codes": codes,
                  "stop_reason": stop_reason, "monitor": str(log_path)}
        print(json.dumps(output), flush=True)
        if stop_reason or any(code != 0 for code in codes.values()):
            sys.exit(1)
    finally:
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
