"""Owned WMI-launched supervisor; schedules only already authorized fixed commands.

No model, generator, optimizer, statistics library, or experimental algorithm is
imported here. Child exit codes are observed, never invented. A child failure is
recorded and never repaired or restarted automatically by this supervisor.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
HERE = REPO / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
PYTHON = Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def no_reparse(path):
    for item in (Path(path), *Path(path).parents):
        if item.exists():
            require(not item.lstat().st_file_attributes & 0x400, 'Reparse path rejected: ' + str(item))


def emit(path, value):
    no_reparse(path)
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def utc():
    return datetime.now(timezone.utc).isoformat()


def commands(gate):
    common = [str(PYTHON), '-I', '-S', '-B']
    return {
        'continuation': common + [str(HERE / 'continuation.py'), '--repo', str(REPO), '--cold-gate', str(gate)],
        'finalizer': common + [str(HERE / 'finalizer.py'), '--repo', str(REPO), '--cold-gate', str(gate),
                               '--attempt', '1', '--poll-seconds', '30'],
    }


def check_job(job):
    if not job['is_in_any_job']:
        return
    require('limits_error' not in job and 'process_list_error' not in job, 'Cannot establish background job limits')
    limits = job['limits']
    # Limit flags: active-process0x8, process/jobtime0x2/0x4,
    # process/jobmemory0x100/0x200, kill-on-job-close0x2000.
    require(not limits['flags'] & (0x8 | 0x2 | 0x4 | 0x100 | 0x200 | 0x2000),
            'Background process retains incompatible job quota or kill-on-close')


def check_spec(spec, spec_path):
    require(spec.get('schema') == 'paper3-owned-durable-launch-spec-v1', 'Wrong launch spec')
    require(spec.get('scientific_changes_authorized') is False and spec.get('automatic_restart') is False,
            'No scientific changes/restarts are permitted')
    require(spec.get('repository') == str(REPO) and spec.get('python_executable') == str(PYTHON), 'Wrong repository/Python')
    gate, record = Path(spec['cold_gate']), Path(spec['record_directory'])
    require(gate.is_absolute() and gate.parent.parent == HERE and gate.name == 'cold_recovery_gate.json', 'Wrong cold gate path')
    require(record.is_absolute() and record.parent == HERE and record.name == 'durable_launch_001', 'Wrong exclusive launcher directory')
    require(not record.exists(), 'Launcher record already exists')
    pins = spec.get('files_sha256', {})
    required = {str(HERE / name) for name in ('durable_supervisor.py', 'background_job_probe.py',
                                            'continuation.py', 'finalizer.py')} | {str(gate), str(PYTHON)}
    require(set(pins) >= required, 'Required launcher pin absent')
    for name, digest in pins.items():
        path = Path(name)
        require(path.is_absolute() and (path.is_relative_to(HERE) or path == PYTHON), 'Unexpected launch source path')
        no_reparse(path)
        require(sha(path) == digest, 'Launcher source/evidence SHA differs: ' + name)
    no_reparse(spec_path)
    no_reparse(record)
    return gate, record, pins


def parent_identity():
    # The SYSTEM-owned WMI provider does not grant this user OpenProcess access.
    # Read its public name/PID through the normal permitted CIM interface;
    # do not elevate, change an ACL, or read its protected executable path.
    pid = int(os.getppid())
    command = ("$p=Get-CimInstance -ClassName Win32_Process -Filter 'ProcessId=" + str(pid) +
               "'; if($null -eq $p){exit 3}; $p | Select-Object ProcessId,Name | ConvertTo-Json -Compress")
    result = subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                             '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
                            check=False)
    require(result.returncode == 0, 'Cannot identify WMI parent through permitted CIM query')
    value = json.loads(result.stdout.decode('utf-8-sig'))
    require(value.get('ProcessId') == pid and value.get('Name', '').casefold() == 'wmiprvse.exe',
            'Durable launcher parent is not the observed WMI provider')
    return value


def current_user():
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.GetUserNameW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetUserNameW.restype = wintypes.BOOL
    buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
    require(advapi.GetUserNameW(buf, ctypes.byref(size)), 'Cannot verify current Windows user')
    return buf.value


def observe_children(record, children, pause=time.sleep):
    finished = {}
    while len(finished) < len(children):
        for name, child in children.items():
            if name in finished:
                continue
            code = child.poll()
            if code is not None:
                finished[name] = int(code)
                emit(record / (name + '_exit.json'), {'finished_utc': utc(), 'actual_exit_code': int(code),
                                                      'pid': child.pid, 'automatic_retry': False})
        if len(finished) < len(children):
            pause(5)
    passed = all(code == 0 for code in finished.values())
    emit(record / ('finish.json' if passed else 'failure.json'),
         {'finished_utc': utc(), 'status': 'CHILD_COMMANDS_COMPLETED' if passed else 'CHILD_COMMAND_FAILURE',
          'actual_child_exit_codes': finished, 'scientific_integrity_pass_claimed': False,
          'automatic_retry': False, 'outputs_preserved': True})
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch-spec', required=True, type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    require(Path(__file__).resolve().parent == HERE and Path(sys.executable) == PYTHON, 'Wrong launcher runtime/source')
    require(args.launch_spec.parent == HERE and args.launch_spec.name == 'DURABLE_LAUNCH_SPEC_001.json', 'Wrong launch spec location')
    spec = json.loads(args.launch_spec.read_text(encoding='utf-8-sig'))
    gate, record, pins = check_spec(spec, args.launch_spec)
    probe_spec = importlib.util.spec_from_file_location('owned_paper3_job_probe', HERE / 'background_job_probe.py')
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    job = probe.job_snapshot()
    check_job(job)
    user, parent = current_user(), parent_identity()
    require(user.casefold() == '92487', 'Wrong Windows user for durable launch')
    record.mkdir()
    emit(record / 'start.json', {'started_utc': utc(), 'pid': os.getpid(), 'parent_pid': os.getppid(),
                                'parent_identity': parent, 'windows_user': user, 'job': job,
                                'launch_spec_sha256': sha(args.launch_spec), 'source_sha256': sha(__file__),
                                'commands': commands(gate), 'automatic_restart': False,
                                'no_scientific_modules_imported': True})
    children, streams = {}, []
    try:
        for name, command in commands(gate).items():
            for filename, digest in pins.items():
                require(sha(filename) == digest, 'Launcher pin changed before child spawn')
            out = (record / (name + '_stdout.log')).open('xb')
            err = (record / (name + '_stderr.log')).open('xb')
            streams.extend((out, err))
            child = subprocess.Popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            children[name] = child
            emit(record / (name + '_launched.json'), {'started_utc': utc(), 'pid': child.pid, 'command': command,
                                                    'actual_exit_code': None, 'completion_claimed': False})
        return observe_children(record, children)
    except BaseException as error:
        emit(record / 'supervisor_error.json', {'observed_utc': utc(), 'exception_type': type(error).__name__,
                                               'message': str(error), 'known_children': {k: v.pid for k, v in children.items()},
                                               'children_terminated_by_supervisor': False, 'automatic_retry': False})
        raise
    finally:
        for stream in streams:
            stream.close()


if __name__ == '__main__':
    sys.exit(main())
