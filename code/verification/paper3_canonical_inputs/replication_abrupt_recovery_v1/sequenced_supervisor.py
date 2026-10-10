"""Stagger metadata-helper admission; all model/statistics commands stay unchanged."""
import argparse
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
source = HERE / 'durable_supervisor.py'
if hashlib.sha256(source.read_bytes()).hexdigest() != OLD_SHA:
    raise RuntimeError('Reviewed durable helper SHA differs before import')
spec = importlib.util.spec_from_file_location('reviewed_paper3_durable_helper', source)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def wait_admission(child, start_path, pause=time.sleep):
    """Uses integrity admission receipt only; never reads model outcomes."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch-spec', required=True, type=Path)
    args = parser.parse_args()
    d.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    d.require(Path(__file__).resolve().parent == HERE and Path(sys.executable) == d.PYTHON, 'Wrong runtime/source')
    d.require(args.launch_spec.parent == HERE and args.launch_spec.name == 'DURABLE_LAUNCH_SPEC_001.json', 'Wrong launch spec')
    launch = json.loads(args.launch_spec.read_text(encoding='utf-8-sig'))
    gate, record, pins = d.check_spec(launch, args.launch_spec)
    d.require(pins.get(str(Path(__file__))) == d.sha(__file__), 'Sequenced host not separately SHA-bound')
    probe_spec = importlib.util.spec_from_file_location('owned_sequenced_job_probe', HERE / 'background_job_probe.py')
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    job = probe.job_snapshot()
    d.check_job(job)
    user, parent = d.current_user(), d.parent_identity()
    d.require(user.casefold() == '92487', 'Wrong Windows user')
    record.mkdir()
    d.emit(record / 'start.json', {'started_utc': d.utc(), 'pid': os.getpid(), 'parent_pid': os.getppid(),
                                 'parent_identity': parent, 'windows_user': user, 'job': job,
                                 'launch_spec_sha256': d.sha(args.launch_spec), 'source_sha256': d.sha(__file__),
                                 'commands': d.commands(gate), 'automatic_restart': False,
                                 'finalizer_waits_for_post_resource_admission': True,
                                 'models_generators_statistics_imported': False})
    children, streams = {}, []
    try:
        for name, command in d.commands(gate).items():
            if name == 'finalizer':
                admitted = wait_admission(children['continuation'], HERE / 'continuation_001/full_start.json')
                d.emit(record / 'FINALIZER_ADMISSION_WAIT_PASSED.json',
                       {'observed_utc': d.utc(), 'actual_full_start': admitted, 'model_performance_used': False})
            for filename, digest in pins.items():
                d.require(d.sha(filename) == digest, 'Launch source/evidence SHA changed')
            out, err = (record / (name + '_stdout.log')).open('xb'), (record / (name + '_stderr.log')).open('xb')
            streams.extend((out, err))
            child = subprocess.Popen(command, cwd=d.REPO, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            children[name] = child
            d.emit(record / (name + '_launched.json'), {'started_utc': d.utc(), 'pid': child.pid,
                                                       'command': command, 'completion_claimed': False})
        return d.observe_children(record, children)
    except BaseException as error:
        d.emit(record / 'supervisor_error.json', {'observed_utc': d.utc(), 'exception_type': type(error).__name__,
                                                 'message': str(error), 'known_children': {k: v.pid for k, v in children.items()},
                                                 'children_terminated_by_supervisor': False, 'automatic_retry': False})
        raise
    finally:
        for stream in streams:
            stream.close()


if __name__ == '__main__':
    sys.exit(main())
