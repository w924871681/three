"""Fit-only P7.6B CUDA-2 process and thermal/resource supervisor.

This wrapper does not inspect scientific metrics or alter a trajectory. It owns
only the process tree it launches and preserves all complete receipts on stop.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.common import sha256_file  # noqa: E402
from scripts import run_p7_6b as runner  # noqa: E402

RESULTS = ROOT / "results/p7_6b"
CONFIG_SHA = "cb4141fda8284a7e98b64187609e5af893e665f960afeef8853a8307fe1e9da3"


def gpu_sample() -> dict:
    names = ("temperature_C", "power_W", "clock_MHz", "thermal_slowdown",
             "utilization_pct", "used_VRAM_MiB", "free_VRAM_MiB")
    query = "temperature.gpu,power.draw,clocks.sm,clocks_event_reasons.sw_thermal_slowdown,utilization.gpu,memory.used,memory.free"
    try:
        raw = subprocess.check_output(["nvidia-smi", f"--query-gpu={query}",
            "--format=csv,noheader,nounits"], text=True, timeout=5).strip().splitlines()[0]
        values = [x.strip() for x in raw.split(",")]
        if len(values) != len(names):
            raise ValueError("unexpected GPU telemetry field count")
        return dict(zip(names, values))
    except (OSError, subprocess.SubprocessError, IndexError, ValueError) as exc:
        return {"error": type(exc).__name__}


def verified_stop(process: subprocess.Popen, created_at: float) -> None:
    """Terminate only this exact launched P7.6B driver and its descendants."""
    try:
        parent = psutil.Process(process.pid)
        if abs(parent.create_time() - created_at) > 1:
            raise RuntimeError("driver PID was reused; refuse process-tree stop")
        command = " ".join(parent.cmdline()).lower()
        if "run_p7_6b.py" not in command or "--phase fit" not in command:
            raise RuntimeError("driver command changed; refuse process-tree stop")
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        gone, alive = psutil.wait_procs(children + [parent], timeout=10)
        for proc in alive:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)
    except psutil.NoSuchProcess:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--direct-start", action="store_true",
                        help="User-authorized direct start without host free-memory gate; thermal guards remain active")
    parser.add_argument("--ignore-thermal", action="store_true",
                        help="User-authorized continuation: keep GPU telemetry but do not stop on thermal thresholds")
    args = parser.parse_args()
    if not args.tag.replace("_", "").replace("-", "").isalnum():
        parser.error("tag must be alphanumeric, underscore or hyphen")
    config = runner.read_json(runner.EXECUTION_CONFIG)
    authorization = runner.require_execution_authorization("fit")
    runner.preflight(phase="fit")
    if not runner.git_bound(runner.EXECUTION_CONFIG) or sha256_file(runner.EXECUTION_CONFIG) != CONFIG_SHA:
        raise RuntimeError("formal CUDA-2 execution config not Git/hash bound")
    if (authorization.get("execution_config_sha256") != CONFIG_SHA or
        authorization.get("validation_authorized") is not False or
        authorization.get("authorized_phases") != ["fit"]):
        raise RuntimeError("Fit-only authorization/config binding invalid")
    if not (config["EXECUTION_DEVICE"] == "cuda" and config["EXECUTION_WORKERS"] == 2 and
            config["DTYPE"] == "float32" and config["MULTIPROCESSING_START_METHOD"] == "spawn" and
            config["TORCH_NUM_THREADS"] == config["OMP_NUM_THREADS"] == config["MKL_NUM_THREADS"] == 1):
        raise RuntimeError("unexpected Fit execution configuration")
    gpu = gpu_sample()
    if "error" in gpu or float(gpu["temperature_C"]) >= 75:
        raise RuntimeError(f"GPU not in safe launch state: {gpu}")
    if not args.direct_start and psutil.virtual_memory().available < 3.0 * 2**30:
        raise RuntimeError("less than 3.0 GiB host memory before Fit launch")
    RESULTS.mkdir(parents=True, exist_ok=True)
    stdout_path = RESULTS / f"fit_cuda2_{args.tag}_stdout.log"
    stderr_path = RESULTS / f"fit_cuda2_{args.tag}_stderr.log"
    monitor_path = RESULTS / f"fit_cuda2_{args.tag}_monitor.jsonl"
    status_path = RESULTS / f"fit_cuda2_{args.tag}_supervisor_status.json"
    if any(p.exists() for p in (stdout_path, stderr_path, monitor_path, status_path)):
        raise RuntimeError("refusing to overwrite Fit run evidence")
    environment = os.environ.copy()
    environment.update({"CUDA_VISIBLE_DEVICES": "0", "OMP_NUM_THREADS": "1",
                        "MKL_NUM_THREADS": "1", "CUBLAS_WORKSPACE_CONFIG": ":4096:8"})
    command = [sys.executable, "-u", "scripts/run_p7_6b.py", "--phase", "fit",
               "--workers", "2", "--device", "cuda", "--resume"]
    started = time.monotonic()
    stop_reason = None
    with stdout_path.open("x", encoding="utf-8") as stdout, \
         stderr_path.open("x", encoding="utf-8") as stderr, \
         monitor_path.open("x", encoding="utf-8") as monitor:
        process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                   stdout=stdout, stderr=stderr)
        driver = psutil.Process(process.pid)
        created_at = driver.create_time()
        atexit.register(verified_stop, process, created_at)
        runner.atomic_json(status_path, {"status": "RUNNING", "pid": process.pid,
            "command": command, "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "execution_config_sha256": CONFIG_SHA, "phase": "fit", "workers": 2,
            "user_authorized_direct_start": args.direct_start})
        low_memory = hot = lost_gpu = thermal_slowdown = 0
        last_completed, last_progress_at = 0, started
        while process.poll() is None:
            memory = psutil.virtual_memory()
            gpu = gpu_sample()
            elapsed = time.monotonic() - started
            try:
                workers = driver.children(recursive=True)
            except psutil.NoSuchProcess:
                workers = []
            child_records = []
            for child in workers:
                try:
                    info = child.memory_info()
                    child_records.append({"pid": child.pid, "name": child.name(),
                        "private_MiB": getattr(info, "private", info.rss) / 2**20,
                        "rss_MiB": info.rss / 2**20,
                        "cpu_seconds": sum(child.cpu_times()[:2])})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            progress_path = RESULTS / "fit_execution_status.json"
            try:
                progress = runner.read_json(progress_path) if progress_path.is_file() else {}
            except (OSError, ValueError):
                progress = {}
            completed = int(progress.get("completed", 0))
            if completed < last_completed:
                stop_reason = "Fit completion counter regressed"
                verified_stop(process, created_at)
                break
            rolling_rate = ((completed - last_completed) * 3600 / max(time.monotonic() - last_progress_at, 1e-9)
                            if completed > last_completed else None)
            if completed > last_completed:
                last_completed, last_progress_at = completed, time.monotonic()
            record = {"utc": datetime.now(timezone.utc).isoformat(), "driver_pid": process.pid,
                "elapsed_seconds": elapsed, "host_available_GiB": memory.available / 2**30,
                "gpu": gpu, "children": child_records, "completed_trajectories": completed,
                "total_trajectories": 432,
                "throughput_trajectories_per_hour": progress.get("throughput_trajectories_per_hour"),
                "rolling_trajectories_per_hour": rolling_rate, "eta_hours": progress.get("eta_hours")}
            monitor.write(json.dumps(record) + "\n"); monitor.flush()
            low_memory = (low_memory + 1 if memory.available < 1.5 * 2**30 else 0) if not args.direct_start else 0
            lost_gpu = lost_gpu + 1 if "error" in gpu else 0
            try:
                hot_now = float(gpu["temperature_C"]) >= 82
                slowdown_now = gpu["thermal_slowdown"].lower() == "active"
            except (KeyError, ValueError, TypeError):
                hot_now = slowdown_now = False
            hot = hot + 1 if hot_now else 0
            thermal_slowdown = thermal_slowdown + 1 if slowdown_now else 0
            if low_memory >= 2 or lost_gpu >= 2 or ((not args.ignore_thermal) and (hot >= 2 or thermal_slowdown >= 3)):
                stop_reason = ("host_memory_below_1.5GiB" if low_memory >= 2 else
                               "gpu_temperature_at_least_82C" if hot >= 2 else
                               "gpu_telemetry_lost" if lost_gpu >= 2 else
                               "repeated_gpu_thermal_throttle")
                verified_stop(process, created_at)
                break
            time.sleep(5)
        exit_code = process.wait()
    result = {"status": "COMPLETED" if exit_code == 0 and not stop_reason else "INTERRUPTED",
              "pid": process.pid, "exit_code": exit_code, "stop_reason": stop_reason,
              "elapsed_seconds": time.monotonic() - started,
              "stdout": str(stdout_path), "stderr": str(stderr_path), "monitor": str(monitor_path),
              "execution_config_sha256": CONFIG_SHA, "phase": "fit", "workers": 2,
              "user_authorized_direct_start": args.direct_start,
              "user_authorized_ignore_thermal": args.ignore_thermal,
              "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    runner.atomic_json(status_path, result)
    atexit.unregister(verified_stop)
    print(json.dumps(result), flush=True)
    if result["status"] != "COMPLETED":
        sys.exit(1)


if __name__ == "__main__":
    main()
