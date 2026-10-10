"""Read-only Windows job inventory using stdlib; no scientific imports or process control."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                ('flags', wintypes.DWORD), ('min_working_set', ctypes.c_size_t),
                ('max_working_set', ctypes.c_size_t), ('active_process_limit', wintypes.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                ('scheduling', wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_ulonglong * 6),
                ('process_memory_limit', ctypes.c_size_t), ('job_memory_limit', ctypes.c_size_t),
                ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


def job_snapshot():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    joined = wintypes.BOOL()
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(joined)):
        raise ctypes.WinError(ctypes.get_last_error())
    out = {'is_in_any_job': bool(joined.value)}
    if not joined.value:
        return out
    returned = wintypes.DWORD()
    buf = ctypes.create_string_buffer(65536)
    if kernel.QueryInformationJobObject(None, 3, buf, len(buf), ctypes.byref(returned)):
        assigned, listed = (ctypes.c_uint32 * 2).from_buffer(buf)
        if listed > (len(buf) - 8) // ctypes.sizeof(ctypes.c_size_t):
            raise ValueError('Invalid Windows job process list length')
        pids = (ctypes.c_size_t * listed).from_buffer(buf, 8)
        out.update(job_assigned_processes=int(assigned), job_listed_processes=int(listed),
                   innermost_job_pids=list(pids))
    else:
        out['process_list_error'] = ctypes.get_last_error()
    limits = ExtendedLimits()
    if kernel.QueryInformationJobObject(None, 9, ctypes.byref(limits), ctypes.sizeof(limits),
                                        ctypes.byref(returned)):
        out['limits'] = {'flags': int(limits.basic.flags),
                         'active_process_limit': int(limits.basic.active_process_limit),
                         'process_memory_limit': int(limits.process_memory_limit),
                         'job_memory_limit': int(limits.job_memory_limit),
                         'process_user_time_limit': int(limits.basic.process_time),
                         'job_user_time_limit': int(limits.basic.job_time),
                         'basic_structure_bytes': ctypes.sizeof(BasicLimits),
                         'extended_structure_bytes': ctypes.sizeof(ExtendedLimits)}
    else:
        out['limits_error'] = ctypes.get_last_error()
    return out


def emit(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.output.parent.resolve() != root or not args.output.is_dir() or not 1 <= args.seconds <= 60:
        raise ValueError('Owned output directory and bounded probe duration required')
    record = {'pid': os.getpid(), 'parent_pid': os.getppid(),
              'created_utc': datetime.now(timezone.utc).isoformat(), 'job': job_snapshot(),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Owned stdlib-only process: no models, generators, statistics, or process control.'}
    emit(args.output / 'started.json', record)
    time.sleep(args.seconds)
    emit(args.output / 'finished.json', {**record, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                                         'job_at_finish': job_snapshot()})


if __name__ == '__main__':
    main()
