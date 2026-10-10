"""Non-scientific scheduler/CPU/GPU microbenchmark; never opens P7.6B centers."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import ctypes
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_IDS = tuple(range(90000, 90024))  # disjoint from every frozen study ID


def memory_mib() -> tuple[float, float]:
    """Current-process working set and host available memory on Windows."""
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return counters.PeakWorkingSetSize / 2**20, status.ullAvailPhys / 2**20


def _init(device: str, threads: int) -> None:
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import torch
    torch.set_num_threads(threads)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)


def _fixture(center_id: int, device: str) -> tuple[int, dict, float, float]:
    import numpy as np
    import torch
    rng = np.random.RandomState(center_id)
    observations = rng.standard_normal((128, 16)).astype(np.float32)
    labels = rng.randint(0, 2, 128).astype(np.int8)
    current = torch.tensor(observations, device=device)
    weights = torch.tensor(rng.standard_normal((16, 16)).astype(np.float32), device=device)
    for _ in range(16):
        current = torch.relu(current @ weights)
        current = torch.clamp(current, -1000, 1000)
    if device == "cuda":
        torch.cuda.synchronize()
        peak_vram = torch.cuda.max_memory_allocated() / 2**20
    else:
        peak_vram = 0.0
    # This is a synthetic serialization fixture, not a scientific trajectory.
    state = {"observations": hashlib.sha256(observations.tobytes()).hexdigest(),
             "labels": hashlib.sha256(labels.tobytes()).hexdigest(),
             "parent_hash": hashlib.sha256(current.cpu().numpy().tobytes()).hexdigest(),
             "action": "test-only", "post_action_identity": "test-only",
             "A0_response": float(observations.mean()),
             "A1_response": float(observations.mean() / max(float(np.median(observations ** 2)), 1e-12)),
             "S_m": float(max(float(np.median(observations ** 2)), 1e-12))}
    state["path_hash"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    rss, _ = memory_mib()
    return center_id, state, rss, peak_vram


def gpu_snapshot() -> dict:
    try:
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], text=True, timeout=5).strip().splitlines()[0]
        temp, util, used, total = [float(x.strip()) for x in result.split(",")]
        return {"temperature_C": temp, "utilization_pct": util,
                "used_MiB": used, "total_MiB": total}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return {"temperature_C": None, "utilization_pct": None,
                "used_MiB": None, "total_MiB": None}


def run_benchmark(workers: int, device: str, threads: int = 1) -> dict:
    if workers not in (1, 2, 4, 6, 8) or device not in ("cpu", "cuda"):
        raise ValueError("unsupported non-scientific benchmark configuration")
    if device == "cuda" and workers != 1:
        raise ValueError("CUDA multi-process benchmark disabled pending VRAM/equivalence proof")
    before = gpu_snapshot()
    if device == "cuda" and before["temperature_C"] is not None and before["temperature_C"] >= 80:
        raise RuntimeError("GPU too hot to benchmark")
    start = time.perf_counter()
    results = {}
    max_rss = max_vram = 0.0
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(device, threads)) as executor:
        futures = [executor.submit(_fixture, center, device) for center in FIXTURE_IDS]
        for future in as_completed(futures):
            center, state, rss, vram = future.result()
            results[center] = state
            max_rss, max_vram = max(max_rss, rss), max(max_vram, vram)
    elapsed = time.perf_counter() - start
    after = gpu_snapshot()
    canonical = json.dumps([results[x] for x in FIXTURE_IDS], sort_keys=True, allow_nan=False).encode()
    value = {"mode": f"{device.upper()}-{workers}", "device": device, "workers": workers,
             "threads_per_worker": threads, "trajectories": len(FIXTURE_IDS),
             "fixture_type": "synthetic scheduler/matrix microfixture; NOT scientific trajectories",
             "wall_time_seconds": elapsed, "trajectories_per_hour": 3600 * len(FIXTURE_IDS) / elapsed,
             "seconds_per_trajectory": elapsed / len(FIXTURE_IDS),
             "peak_worker_RSS_MiB": max_rss, "estimated_worker_RAM_MiB": workers * max_rss,
             "peak_worker_VRAM_MiB": max_vram, "host_available_after_MiB": memory_mib()[1],
             "gpu_before": before, "gpu_after": after,
             "output_sha256": hashlib.sha256(canonical).hexdigest(),
             "failures": 0, "retries": 0}
    print(json.dumps(value, sort_keys=True), flush=True)
    return value
