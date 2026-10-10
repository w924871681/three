"""Bounded monitor for one test-only P7.6B qualification process."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/p7_6b_qualification"


def gpu_sample() -> dict:
    fields = "temperature.gpu,temperature.memory,power.draw,clocks.sm,clocks_event_reasons.sw_thermal_slowdown,utilization.gpu,memory.used,memory.free"
    try:
        raw = subprocess.check_output(["nvidia-smi", f"--query-gpu={fields}",
            "--format=csv,noheader,nounits"], text=True, timeout=5).strip().splitlines()[0]
        values = [x.strip() for x in raw.split(",")]
        return dict(zip(("temperature_C", "hotspot_or_memory_temperature_C", "power_W",
            "clock_MHz", "thermal_throttle", "utilization_pct", "used_VRAM_MiB",
            "free_VRAM_MiB"), values))
    except (OSError, subprocess.SubprocessError, IndexError):
        return {"error": "nvidia-smi unavailable"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--center-id", type=int, required=True)
    parser.add_argument("--seed", type=int, default=7311)
    parser.add_argument("--scenario", choices=("C0", "C1", "C3", "C4"), default="C0")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    if not 90000 <= args.center_id <= 90005:
        parser.error("test-only IDs 90000--90005 only")
    import psutil
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"{args.tag}_stdout.log"
    err = OUT / f"{args.tag}_stderr.log"
    mon = OUT / f"{args.tag}_monitor.jsonl"
    for path in (log, err, mon):
        if path.exists():
            parser.error(f"refusing to overwrite existing qualification file {path}")
    command = [args.python, "-u", "scripts/p7_6b_full_trajectory_qualification.py",
        "--device", args.device, "--center-id", str(args.center_id), "--seed", str(args.seed),
        "--scenario", args.scenario, "--tag", args.tag, "--threads", str(args.threads)]
    with log.open("x", encoding="utf-8") as stdout, err.open("x", encoding="utf-8") as stderr, mon.open("x", encoding="utf-8") as monitor:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        child = psutil.Process(process.pid)
        started = time.monotonic()
        low_memory_samples = hot_samples = 0
        reason = None
        while process.poll() is None:
            memory = psutil.virtual_memory()
            try:
                info = child.memory_info()
                cpu = child.cpu_times()
                rss = info.rss / 2**20
                private = getattr(info, "private", None)
                cpu_s = cpu.user + cpu.system
            except psutil.NoSuchProcess:
                rss = private = cpu_s = None
            gpu = gpu_sample()
            elapsed = time.monotonic() - started
            record = {"utc": datetime.now(timezone.utc).isoformat(), "pid": process.pid,
                "elapsed_s": elapsed, "rss_MiB": rss,
                "private_MiB": private / 2**20 if private is not None else None,
                "cpu_seconds": cpu_s, "host_available_GiB": memory.available / 2**30,
                "gpu": gpu}
            monitor.write(json.dumps(record) + "\n"); monitor.flush()
            print(json.dumps({"elapsed_s": round(elapsed, 1),
                "host_available_GiB": round(memory.available / 2**30, 2), "gpu": gpu}), flush=True)
            low_memory_samples = low_memory_samples + 1 if memory.available < 1.5 * 2**30 else 0
            try:
                hot = float(gpu["temperature_C"]) >= 82
            except (KeyError, ValueError, TypeError):
                hot = False
            hot_samples = hot_samples + 1 if hot else 0
            if low_memory_samples >= 2 or hot_samples >= 2 or elapsed > args.timeout_seconds:
                reason = ("host_memory_below_1.5GiB" if low_memory_samples >= 2 else
                          "gpu_temperature_at_least_82C" if hot_samples >= 2 else "hard_timeout")
                process.terminate()  # only this verified test-only child
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(2)
        exit_code = process.wait()
    print(json.dumps({"tag": args.tag, "pid": process.pid, "exit_code": exit_code,
                      "stop_reason": reason, "stdout": str(log), "stderr": str(err),
                      "monitor": str(mon)}), flush=True)
    if exit_code != 0 or reason:
        sys.exit(1)


if __name__ == "__main__":
    main()
