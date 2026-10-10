"""Exclusive third launcher with explicit, separately certified legacy-reader entries."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
HERE = Path(__file__).resolve().parent
OLD = REPO / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
PYTHON = Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
OLD_D_SHA = '7c9fceabf4a2e3eaffd4e4422e66b4859f22665e67c0eceb8e562788b2217bc4'
OLD_S_SHA = '7a38c91022f081f1620e7bb23659bdb24be3e4bfba9fac5a195e0c7646684b02'


def trusted(name, filename, digest):
    source = OLD / filename
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Reviewed helper differs: ' + filename)
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d = trusted('original_durable_003', 'durable_supervisor.py', OLD_D_SHA)
s = trusted('original_sequencing_003', 'sequenced_supervisor_002.py', OLD_S_SHA)


def commands(gate):
    common = [str(PYTHON), '-I', '-S', '-B']
    return {
        'continuation': common + [str(HERE / 'compat_continuation.py'), '--repo', str(REPO), '--cold-gate', str(gate)],
        'finalizer': common + [str(HERE / 'compat_finalizer.py'), '--repo', str(REPO), '--cold-gate', str(gate),
                               '--attempt', '1', '--poll-seconds', '30'],
    }


def check_wrapper_proof(proof):
    d.require(proof.get('all_pass') is True and proof.get('exit_code') == 0 and
              proof.get('tests_run', 0) >= 8 and all(proof.get(k) == 0 for k in ('failures', 'errors', 'skipped')),
              'Wrapper synthetic proof is not complete PASS')
    d.require(proof.get('models_generators_or_statistics_executed') is False and
              proof.get('real_processes_launched') is False, 'Wrapper test scope differs')
    names = ('compat_entry.py', 'compat_continuation.py', 'compat_finalizer.py',
             'compat_supervisor_003.py', 'tests_compat_wrappers.py')
    actual = {name: d.sha(HERE / name) for name in names}
    d.require(proof.get('implementation_sha256') == actual, 'Wrapper sources differ from actual tests')


def check_spec(value, path):
    d.require(path == HERE / 'DURABLE_LAUNCH_SPEC_003.json', 'Wrong launch spec')
    d.require(value.get('schema') == 'paper3-owned-metadata-compat-launch-v1' and
              value.get('repository') == str(REPO) and value.get('python_executable') == str(PYTHON), 'Wrong runtime identity')
    d.require(value.get('workers') == 2 and value.get('automatic_restart') is False and
              value.get('scientific_changes_authorized') is False, 'Wrong scheduling or scientific scope')
    gate = Path(value['cold_gate'])
    record = Path(value['record_directory'])
    d.require(gate == OLD / 'COLD_RECOVERY_METADATA_COMPAT_001/cold_recovery_gate.json', 'Wrong gate')
    d.require(record == HERE / 'durable_launch_003' and not record.exists(), 'Exclusive launch record exists or differs')
    pins = value['files_sha256']
    required = {str(HERE / name) for name in ('compat_supervisor_003.py', 'compat_entry.py',
                'compat_continuation.py', 'compat_finalizer.py', 'strict_legacy_proof_adapter.py',
                'STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.json', 'WRAPPER_TEST_RESULTS_001.json')}
    required |= {str(OLD / name) for name in ('durable_supervisor.py', 'sequenced_supervisor_002.py',
                 'background_job_probe.py', 'continuation.py', 'finalizer.py',
                 'durable_launch_002/supervisor_error.json', 'durable_launch_002/continuation_stderr.log')}
    required |= {str(gate), str(PYTHON)}
    d.require(set(pins) >= required, 'Required launch byte pin missing')
    for name, digest in pins.items():
        item = Path(name)
        d.require(item.is_absolute() and (item.is_relative_to(HERE) or item.is_relative_to(OLD) or item == PYTHON),
                  'Unexpected launch binding path')
        d.no_reparse(item)
        d.require(d.sha(item) == digest, 'Launch source or evidence changed: ' + name)
    check_wrapper_proof(json.loads((HERE / 'WRAPPER_TEST_RESULTS_001.json').read_text(encoding='utf-8')))
    for pid in (29376, 22624, 5504, 28904):
        d.require(s.native_pid_inactive(pid), 'An earlier actual launcher/continuation is active')
    s.no_prior_work_collision()
    d.no_reparse(record)
    return gate, record, pins


def launch(gate, record, pins, popen=subprocess.Popen):
    children, streams = {}, []
    try:
        for name, command in commands(gate).items():
            if name == 'finalizer':
                admitted = s.wait_admission(children['continuation'], OLD / 'continuation_001/full_start.json')
                d.emit(record / 'FINALIZER_ADMISSION_WAIT_PASSED.json', {'observed_utc': d.utc(),
                       'actual_full_start': admitted, 'model_performance_used': False})
            for filename, digest in pins.items():
                d.require(d.sha(filename) == digest, 'Launch binding changed before child spawn')
            out = (record / (name + '_stdout.log')).open('xb')
            err = (record / (name + '_stderr.log')).open('xb')
            streams.extend((out, err))
            child = popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                          creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            children[name] = child
            d.emit(record / (name + '_launched.json'), {'started_utc': d.utc(), 'pid': child.pid,
                   'command': command, 'model_worker_start_claimed': False})
        return d.observe_children(record, children)
    except BaseException as error:
        d.emit(record / 'supervisor_error.json', {'observed_utc': d.utc(), 'message': str(error),
               'exception_type': type(error).__name__, 'known_children': {k: v.pid for k, v in children.items()},
               'children_terminated_by_supervisor': False, 'automatic_retry': False})
        raise
    finally:
        for stream in streams: stream.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launch-spec', required=True, type=Path)
    args = parser.parse_args()
    d.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    d.require(HERE == REPO / 'verification/paper3_canonical_inputs/recovery_compat_v1' and Path(sys.executable) == PYTHON,
              'Wrong launcher source/runtime')
    value = json.loads(args.launch_spec.read_text(encoding='utf-8'))
    gate, record, pins = check_spec(value, args.launch_spec)
    probe = trusted('original_job_probe_003', 'background_job_probe.py', pins[str(OLD / 'background_job_probe.py')])
    job = probe.job_snapshot(); d.check_job(job)
    user, parent = d.current_user(), d.parent_identity()
    d.require(user.casefold() == '92487', 'Wrong user')
    s.no_prior_work_collision()
    record.mkdir()
    d.emit(record / 'start.json', {'started_utc': d.utc(), 'pid': os.getpid(), 'parent_pid': os.getppid(),
           'parent_identity': parent, 'job': job, 'windows_user': user, 'commands': commands(gate),
           'source_sha256': d.sha(__file__), 'launch_spec_sha256': d.sha(args.launch_spec),
           'actual_entrypoints_are_compatibility_wrappers': True, 'automatic_restart': False,
           'model_workers_started_claimed': False})
    return launch(gate, record, pins)


if __name__ == '__main__': sys.exit(main())
