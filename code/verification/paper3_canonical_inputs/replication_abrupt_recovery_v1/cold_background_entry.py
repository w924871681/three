"""Stdlib-only logging host for the unchanged cold collector; no admission rule changes."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback
from datetime import datetime, timezone

HERE = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\replication_abrupt_recovery_v1')
RECOVER_SHA = '02e02a3aaa640494b8b668ef90c6d4cab1f1cbef16349542ac5dc7fa30748a54'


def emit(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def scope(path, expected_name):
    if not path.is_absolute() or path.parent != HERE or path.name != expected_name:
        raise ValueError('Only the specified exclusive owned path is allowed')
    for item in (path, *path.parents):
        if item.exists() and item.lstat().st_file_attributes & 0x400:
            raise ValueError('Reparse path is not permitted')


def observed_class(base, record):
    class RecordingObserver(base):
        counter = 0
        def resources(self):
            value = super().resources()
            self.counter += 1
            emit(record / ('resources_%03d.json' % self.counter), value)
            return value
    return RecordingObserver


def collect(module, execution, pins, record, authorized):
    observer = observed_class(module.ReadOnlyWindowsObserver, record)()
    context = module.run_readonly(execution, pins, observer=observer)
    if authorized:
        gate = module.run_recovery(context, observer=observer)
        return {'status': gate['status'], 'cold_gate': str(execution / 'cold_recovery_gate.json')}
    return {'status': 'READONLY_COLD_AUDIT_PASS', 'existing_result_paths_added': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--implementation-pins', required=True, type=Path)
    parser.add_argument('--authorize-cold-recovery', action='store_true')
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('Requires -I -S -B')
    if Path(__file__).resolve().parent != HERE:
        raise ValueError('Wrong source directory')
    execution = HERE / ('COLD_RECOVERY_001' if args.authorize_cold_recovery else 'COLD_PREFLIGHT_002')
    record_name = 'cold_background_recovery_001' if args.authorize_cold_recovery else 'cold_background_preflight_002'
    scope(args.record, record_name)
    scope(execution, execution.name)
    scope(args.implementation_pins, 'REVIEWED_RECOVERY_PINS_002.json')
    if args.record.exists() or execution.exists():
        raise FileExistsError('Existing records must be preserved')
    args.record.mkdir()
    emit(args.record / 'start.json', {'started_utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
                                    'parent_pid': os.getppid(), 'implementation_pins': str(args.implementation_pins),
                                    'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                    'authorize_cold_recovery': args.authorize_cold_recovery,
                                    'scientific_modules_executed': False})
    with (args.record / 'stdout.log').open('x', encoding='utf-8') as stdout, (args.record / 'stderr.log').open('x', encoding='utf-8') as stderr:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                pins = json.loads(args.implementation_pins.read_text(encoding='utf-8'))
                own_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                if pins['files_sha256'].get(str(Path(__file__))) != own_sha:
                    raise RuntimeError('Host source is not included in reviewed pins')
                helpers = {}
                for name in ('durable_supervisor.py', 'background_job_probe.py'):
                    path = HERE / name
                    if hashlib.sha256(path.read_bytes()).hexdigest() != pins['files_sha256'][str(path)]:
                        raise RuntimeError('Read-only hosting helper source differs')
                    helper_spec = importlib.util.spec_from_file_location('paper3_cold_host_' + path.stem, path)
                    helper = importlib.util.module_from_spec(helper_spec)
                    helper_spec.loader.exec_module(helper)
                    helpers[name] = helper
                host = helpers['durable_supervisor.py']
                job = helpers['background_job_probe.py'].job_snapshot()
                host.check_job(job)
                user, parent = host.current_user(), host.parent_identity()
                if user.casefold() != '92487':
                    raise RuntimeError('Wrong Windows user for cold background host')
                emit(args.record / 'hosting.json', {'windows_user': user, 'parent_identity': parent, 'job': job})
                source = HERE / 'recover.py'
                if hashlib.sha256(source.read_bytes()).hexdigest() != RECOVER_SHA:
                    raise RuntimeError('Unchanged reviewed collector SHA differs')
                spec = importlib.util.spec_from_file_location('paper3_recorded_cold_collector', source)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                result = collect(module, execution, args.implementation_pins, args.record, args.authorize_cold_recovery)
                emit(args.record / 'finish.json', {**result, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                                                 'models_generators_statistics_executed': False})
            except BaseException as error:
                traceback.print_exc()
                stderr.flush()
                emit(args.record / 'failure.json', {'status': 'ACTUAL_COLLECTOR_FAILURE', 'observed_utc': datetime.now(timezone.utc).isoformat(),
                                                    'exception_type': type(error).__name__, 'message': str(error),
                                                    'model_experiment_started': False, 'scientific_pass_claimed': False})
                raise


if __name__ == '__main__':
    main()
