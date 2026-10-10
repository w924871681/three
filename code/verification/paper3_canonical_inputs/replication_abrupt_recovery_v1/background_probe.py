"""Harmless stdlib-only test of a WMI-created process outside Codex jobs."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

def emit(path, value):
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, indent=2);out.write('\n');out.flush();os.fsync(out.fileno())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    assert args.output.parent.resolve()==root and args.output.is_dir()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype=wintypes.BOOL
    value=wintypes.BOOL()
    assert kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(value))
    record={'pid':os.getpid(),'parent_pid':os.getppid(),'created_utc':datetime.now(timezone.utc).isoformat(),
        'is_in_any_job':bool(value.value),'models_generators_statistics_imported_or_executed':False,
        'scope':'Owned harmless process; no experiment or user process control.'}
    emit(args.output/'started.json',record)
    time.sleep(30)
    emit(args.output/'finished.json',{**record,'finished_utc':datetime.now(timezone.utc).isoformat()})

if __name__=='__main__':main()
