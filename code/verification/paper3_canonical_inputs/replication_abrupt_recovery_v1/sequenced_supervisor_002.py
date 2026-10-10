"""Exclusive second metadata-helper launch after the first admission failed.

Imports only the SHA-pinned original standard-library launcher. It never kills,
retries or modifies an existing process or experimental record. Scientific
commands, admission checks and the model executor remain unchanged.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\replication_abrupt_recovery_v1')
OLD_SHA = '7c9fceabf4a2e3eaffd4e4422e66b4859f22665e67c0eceb8e562788b2217bc4'
MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1 = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
source = HERE / 'durable_supervisor.py'
if hashlib.sha256(source.read_bytes()).hexdigest() != OLD_SHA:
    raise RuntimeError('Reviewed durable helper SHA differs before import')
module_spec = importlib.util.spec_from_file_location('reviewed_paper3_durable_helper_002', source)
d = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(d)


def wait_admission(child, start_path, pause=time.sleep):
    """Same post-resource admission semantics; no model outcomes are inspected."""
    while True:
        code = child.poll()
        d.require(code is None, 'Continuation exited before post-resource admission: ' + str(code))
        if start_path.exists():
            d.no_reparse(start_path)
            try:
                value = json.loads(start_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                pause(1)
                continue
            command = value.get('command', [])
            d.require(value.get('outcome_based_continuation') is False and
                      '--phase' in command and command[command.index('--phase') + 1] == 'full' and
                      '--attempt' in command and command[command.index('--attempt') + 1] == '2' and
                      '--workers' in command and command[command.index('--workers') + 1] == '2',
                      'Unexpected post-admission full command')
            return value
        pause(5)


def native_pid_inactive(pid):
    """Query-only Windows check; numeric PID reuse conservatively blocks launch."""
    d.require(os.name == 'nt', 'Native Windows process admission required')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        d.require(ctypes.get_last_error() == 87, 'Prior process absence not verifiable: ' + str(pid))
        return True
    try:
        code = wintypes.DWORD()
        d.require(kernel.GetExitCodeProcess(handle, ctypes.byref(code)), 'Cannot query prior process status')
        return code.value != 259
    finally:
        kernel.CloseHandle(handle)


def no_prior_work_collision():
    relative_paths = (
        'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1/continuation_001',
        'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1/CONTINUATION_EXCLUSIVE_RUN_LOCK.json',
        'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1/attempt001',
        'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1/FINALIZER_EXCLUSIVE_RUN_LOCK.json',
        'verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/phase_launches/full_002',
        'results/p7_7_integrity_replication_batch20_env_v3/execution/full/A_FULL_0002',
    )
    for relative in relative_paths:
        path = d.REPO / relative
        d.no_reparse(path)
        d.require(not path.exists(), 'Unstarted continuation/full2 path already exists: ' + str(path))


def check_spec(launch, spec_path):
    """Independent strict 002 validation; never calls the hard-coded 001 checker."""
    d.require(spec_path.parent == HERE and spec_path.name == 'DURABLE_LAUNCH_SPEC_002.json', 'Wrong exclusive 002 launch spec')
    d.no_reparse(spec_path)
    d.require(launch.get('schema') == 'paper3-owned-durable-launch-spec-v1', 'Wrong launch schema')
    d.require(launch.get('scientific_changes_authorized') is False and launch.get('automatic_restart') is False,
              'No scientific changes/restarts are permitted')
    d.require(launch.get('repository') == str(d.REPO) and launch.get('python_executable') == str(d.PYTHON), 'Wrong repository/Python')
    d.require(launch.get('workers') == 2 and launch.get('finalizer_waits_for_post_resource_admission') is True,
              'Wrong worker count or admission sequence')
    d.require(launch.get('manifest_digest') == MANIFEST and launch.get('F1_digest') == F1, 'Wrong frozen input identity')
    gate, record = Path(launch['cold_gate']), Path(launch['record_directory'])
    d.require(gate == HERE / 'COLD_RECOVERY_BINDING_CORRECTION_001/cold_recovery_gate.json', 'Wrong corrected gate path')
    d.require(record == HERE / 'durable_launch_002', 'Wrong exclusive 002 record directory')
    d.no_reparse(gate)
    d.no_reparse(record)
    d.require(not record.exists(), 'Launcher 002 record already exists')
    pins = launch.get('files_sha256', {})
    required = {str(HERE / name) for name in (
        'sequenced_supervisor_002.py', 'durable_supervisor.py', 'background_job_probe.py',
        'continuation.py', 'finalizer.py', 'durable_launch_001/start.json',
        'durable_launch_001/continuation_launched.json', 'durable_launch_001/supervisor_error.json')}
    required |= {str(gate), str(d.PYTHON)}
    d.require(set(pins) >= required, 'Required launcher 002 pin absent')
    d.require(pins[str(HERE / 'durable_supervisor.py')] == OLD_SHA, 'Original helper binding differs')
    for name, digest in pins.items():
        path = Path(name)
        d.require(path.is_absolute() and (path.is_relative_to(HERE) or path == d.PYTHON), 'Unexpected launch source path')
        d.no_reparse(path)
        d.require(d.sha(path) == digest, 'Launcher 002 source/evidence SHA differs: ' + name)
    old_start = json.loads((HERE / 'durable_launch_001/start.json').read_text(encoding='utf-8'))
    old_child = json.loads((HERE / 'durable_launch_001/continuation_launched.json').read_text(encoding='utf-8'))
    old_error = json.loads((HERE / 'durable_launch_001/supervisor_error.json').read_text(encoding='utf-8'))
    d.require(old_start.get('pid') == 29376 and old_child.get('pid') == 22624,
              'Prior launcher/continuation identities differ')
    d.require(old_error.get('known_children') == {'continuation': 22624} and
              old_error.get('children_terminated_by_supervisor') is False and old_error.get('automatic_retry') is False,
              'Prior failure evidence differs')
    for pid in (29376, 22624):
        d.require(native_pid_inactive(pid), 'Prior launcher/continuation is still active: ' + str(pid))
    no_prior_work_collision()
    return gate, record, pins


def launch_children(gate, record, pins, *, popen=subprocess.Popen, pause=time.sleep):
    children, streams = {}, []
    try:
        for name, command in d.commands(gate).items():
            if name == 'finalizer':
                admitted = wait_admission(children['continuation'], HERE / 'continuation_001/full_start.json', pause=pause)
                d.emit(record / 'FINALIZER_ADMISSION_WAIT_PASSED.json',
                       {'observed_utc': d.utc(), 'actual_full_start': admitted, 'model_performance_used': False})
            for filename, digest in pins.items():
                d.require(d.sha(filename) == digest, 'Launch source/evidence SHA changed')
            out, err = (record / (name + '_stdout.log')).open('xb'), (record / (name + '_stderr.log')).open('xb')
            streams.extend((out, err))
            child = popen(command, cwd=d.REPO, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                          creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            children[name] = child
            d.emit(record / (name + '_launched.json'), {'started_utc': d.utc(), 'pid': child.pid,
                                                       'command': command, 'completion_claimed': False})
        return d.observe_children(record, children, pause=pause)
    except BaseException as error:
        d.emit(record / 'supervisor_error.json', {'observed_utc': d.utc(), 'exception_type': type(error).__name__,
                                                 'message': str(error), 'known_children': {k: v.pid for k, v in children.items()},
                                                 'children_terminated_by_supervisor': False, 'automatic_retry': False})
        raise
    finally:
        for stream in streams:
            stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch-spec', required=True, type=Path)
    args = parser.parse_args()
    d.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    d.require(Path(__file__).resolve().parent == HERE and Path(sys.executable) == d.PYTHON, 'Wrong runtime/source')
    launch = json.loads(args.launch_spec.read_text(encoding='utf-8-sig'))
    gate, record, pins = check_spec(launch, args.launch_spec)
    d.require(pins.get(str(Path(__file__))) == d.sha(__file__), 'Sequenced 002 host not separately SHA-bound')
    probe_spec = importlib.util.spec_from_file_location('owned_sequenced_job_probe_002', HERE / 'background_job_probe.py')
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    job = probe.job_snapshot()
    d.check_job(job)
    user, parent = d.current_user(), d.parent_identity()
    d.require(user.casefold() == '92487', 'Wrong Windows user')
    # Recheck absence/collisions immediately before exclusive launch journal.
    for pid in (29376, 22624):
        d.require(native_pid_inactive(pid), 'Prior process became active before launch: ' + str(pid))
    no_prior_work_collision()
    record.mkdir()
    d.emit(record / 'start.json', {'started_utc': d.utc(), 'pid': os.getpid(), 'parent_pid': os.getppid(),
                                 'parent_identity': parent, 'windows_user': user, 'job': job,
                                 'launch_spec_sha256': d.sha(args.launch_spec), 'source_sha256': d.sha(__file__),
                                 'commands': d.commands(gate), 'automatic_restart': False,
                                 'finalizer_waits_for_post_resource_admission': True,
                                 'prior_numeric_pids_verified_inactive': [29376, 22624],
                                 'models_generators_statistics_imported': False})
    return launch_children(gate, record, pins)


if __name__ == '__main__':
    sys.exit(main())
