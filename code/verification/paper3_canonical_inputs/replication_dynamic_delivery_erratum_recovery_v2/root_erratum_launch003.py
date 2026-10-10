"""Root-owned single metadata recovery, with retained native/Popen actual exits."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent
PYTHON = Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
PYTHON_SHA = '0562f573871cb16a2fb8de16e3d486e3dfd74bb83c7e87db265561917d05ad1a'

def preflight_interpreter(e):
    return e.bound(PYTHON, PYTHON_SHA, root=PYTHON.parent)

def load_source(path, name, digest):
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise RuntimeError('bound launcher source differs')
    m = types.ModuleType(name); m.__file__ = str(path)
    sys.modules[name] = m
    exec(compile(payload, str(path), 'exec'), m.__dict__)
    return m

def kernel_identity(observer, handle, pid):
    creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not observer.k.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                     ctypes.byref(kernel), ctypes.byref(user)):
        raise RuntimeError('retained native creation time query failed')
    size = wintypes.DWORD(32768); image = ctypes.create_unicode_buffer(size.value)
    if not observer.k.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
        raise RuntimeError('retained native image query failed')
    return {'pid': pid, 'creation_filetime': (creation.dwHighDateTime << 32) | creation.dwLowDateTime,
            'image': str(Path(image.value).resolve())}

def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('launcher requires -I -S -B')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', required=True); ap.add_argument('--plan-sha256', required=True)
    args = ap.parse_args()
    plan_path = Path(args.plan).resolve()
    payload = plan_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != args.plan_sha256:
        raise RuntimeError('launcher plan SHA differs')
    plan = json.loads(payload)
    scope = plan['metadata_recovery']; helper_path = HERE/'metadata_recovery.py'
    helper_sha = scope['source_sha256'][str(helper_path)]
    r = load_source(helper_path, 'paper3_root_metadata_recovery_launcher', helper_sha)
    e = r.configure(r.make_api())
    e.verify_plan(plan_path, args.plan_sha256)
    preflight_interpreter(e)
    launcher_sha = scope['source_sha256'][str(Path(__file__).resolve())]
    e.bound(Path(__file__), launcher_sha)
    start_path = HERE/'ROOT_ERRATUM_RECOVERY_PROCESS_START_004.json'
    exit_path = HERE/'ROOT_ERRATUM_RECOVERY_PROCESS_EXIT_004.json'
    log_path = HERE/'ROOT_ERRATUM_RECOVERY_PROCESS_004.log'
    e.require(not any(p.exists() for p in (start_path, exit_path, log_path, r.RECORD)), 'one exclusive launch required')
    w = r.verified_module(e.HERE/'erratum_watch.py', 'paper3_root_metadata_native_observer',
                          'cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2')
    observer = w.NativeObserver()
    argv = [str(PYTHON), '-I', '-S', '-B', str(helper_path), 'execute', '--plan', str(plan_path),
            '--plan-sha256', args.plan_sha256]
    common = {'plan_path': str(plan_path), 'plan_sha256': args.plan_sha256,
        'helper_path': str(helper_path), 'helper_sha256': helper_sha,
        'test_proof_path': scope['test_proof_path'], 'test_proof_sha256': scope['test_proof_sha256'],
        'launcher_path': str(Path(__file__).resolve()), 'launcher_sha256': launcher_sha,
        'automatic_retry': False, 'native_handle_retained_until_wait': True,
        'models_or_statistics_restarted': False}
    began = time.perf_counter()
    with log_path.open('xb') as log:
        process = subprocess.Popen(argv, cwd=str(r.REPO), stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, creationflags=0x08000000)
        handle = observer.open(process.pid)
        try:
            identity = observer.identity(handle, process.pid)
            e.require(identity['command_line'] == subprocess.list2cmdline(argv) and
                      Path(identity['image']).resolve() == PYTHON.resolve(), 'actual native launch command/image differs')
            start = e.emit(start_path, {**common, **identity, 'schema':'paper3-root-erratum-recovery-process-start-v1',
                'producer':'ROOT_OWNING_POPEN', 'cmdargv':argv, 'started_utc':e.utc()})
            print(json.dumps({'phase':'METADATA_RECOVERY_STARTED', 'pid':process.pid,
                              'start_sha256':start['sha256'], 'started_utc':e.utc()}), flush=True)
            while not observer.wait(handle, 10000):
                print(json.dumps({'phase':'METADATA_RECOVERY_RUNNING', 'pid':process.pid,
                                  'elapsed_seconds':round(time.perf_counter()-began, 1)}), flush=True)
            actual = process.wait()
            native = observer.exit_code(handle)
            after = kernel_identity(observer, handle, process.pid)
            unchanged = after == {k:identity[k] for k in ('pid','creation_filetime','image')}
            e.require(unchanged and type(actual) is int and actual == native, 'owning/native exit or retained identity differs')
            receipt = {**common, **identity, 'schema':'paper3-root-erratum-recovery-process-exit-v1',
                'producer':'OWN_ROOT_POPEN_WAIT', 'cmdargv':argv, 'actual_exit_code':actual,
                'native_exit_code':native, 'identity_unchanged':unchanged,
                'start_receipt_sha256':start['sha256'], 'finished_utc':e.utc(),
                'elapsed_seconds':round(time.perf_counter()-began, 3),
                'log_path':str(log_path), 'log_sha256':e.sha(log_path)}
            if actual == 0:
                finish = r.RECORD/'finish.json'
                e.require(not (r.RECORD/'stopped.json').exists() and
                          e.read(finish)['status']=='SMOKE_COUNT_METADATA_ERRATUM_COMPLETED', 'actual zero without legal finish')
                receipt['finish_path'] = str(finish); receipt['finish_sha256'] = e.sha(finish)
            e.emit(exit_path, receipt)
            print(json.dumps(receipt, sort_keys=True), flush=True)
            return 0 if actual == 0 else 1
        finally:
            observer.close(handle)

if __name__ == '__main__':
    raise SystemExit(main())
