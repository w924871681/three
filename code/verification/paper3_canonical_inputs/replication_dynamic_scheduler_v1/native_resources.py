"""Read-only Windows commit/physical/process counters; no environment changes."""
from __future__ import annotations
import ctypes
import os
import time
from dynamic_policy import ResourceSample, WorkerObservation


class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_ulong)] + [(key, ctypes.c_size_t) for key in
        ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
         'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')] + [
        ('HandleCount',ctypes.c_ulong),('ProcessCount',ctypes.c_ulong),('ThreadCount',ctypes.c_ulong)]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)] + [(key,ctypes.c_size_t) for key in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


def _windows():
    if os.name != 'nt':
        raise RuntimeError('Production native resource sampling is Windows-only')
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    psapi = ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel, psapi


def resource_sample():
    _, psapi = _windows()
    data = PERFORMANCE_INFORMATION(); data.cb = ctypes.sizeof(data)
    psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(PERFORMANCE_INFORMATION),ctypes.c_ulong]
    if not psapi.GetPerformanceInfo(ctypes.byref(data),data.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return ResourceSample(int(time.monotonic()*1000),
        int((data.CommitLimit-data.CommitTotal)*data.PageSize),int(data.CommitLimit*data.PageSize),
        int(data.PhysicalAvailable*data.PageSize),int(data.PhysicalTotal*data.PageSize))


def process_active(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid process identity')
    kernel,_ = _windows()
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        error=ctypes.get_last_error()
        if error in (87,1168): return False
        raise ctypes.WinError(error)
    try:
        code=ctypes.c_ulong()
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value==259
    finally: kernel.CloseHandle(handle)


def worker_observation(worker_id, phase, actual_pid, previous_peaks=(0,0)):
    kernel,psapi = _windows()
    handle=kernel.OpenProcess(0x1000|0x0010,False,actual_pid)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    try:
        data=PROCESS_MEMORY_COUNTERS_EX(); data.cb=ctypes.sizeof(data)
        psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),ctypes.c_ulong]
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(data),data.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return WorkerObservation(worker_id,phase,int(data.PrivateUsage),
            max(previous_peaks[0],int(data.PrivateUsage),int(data.PeakPagefileUsage)),
            int(data.WorkingSetSize),max(previous_peaks[1],int(data.PeakWorkingSetSize)))
    finally: kernel.CloseHandle(handle)
