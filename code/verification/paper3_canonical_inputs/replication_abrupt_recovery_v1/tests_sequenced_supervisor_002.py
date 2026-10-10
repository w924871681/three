"""Synthetic-only 002 launcher checks: no real subprocesses or scientific reads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('owned_sequenced_002_under_test', ROOT / 'sequenced_supervisor_002.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Child:
    def __init__(self, codes=(None,), pid=123456):
        self.codes = list(codes)
        self.pid = pid
    def poll(self):
        if len(self.codes) > 1:
            return self.codes.pop(0)
        return self.codes[0]


def admitted(workers='2'):
    return {'outcome_based_continuation': False,
            'command': ['--phase', 'full', '--attempt', '2', '--workers', workers]}


class AdmissionTests(unittest.TestCase):
    def test_exact_integrity_receipt_admits(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            value = admitted()
            path.write_text(json.dumps(value), encoding='utf-8')
            self.assertEqual(m.wait_admission(Child(), path), value)

    def test_child_failure_is_not_admission(self):
        with self.assertRaisesRegex(RuntimeError, 'exited before'):
            m.wait_admission(Child((1,)), ROOT / 'synthetic002_absent')

    def test_child_normal_exit_without_admission_also_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'exited before'):
            m.wait_admission(Child((0,)), ROOT / 'synthetic002_absent')

    def test_wrong_worker_count_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            path.write_text(json.dumps(admitted('1')), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
                m.wait_admission(Child(), path)

    def test_partial_json_is_waited_for(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            path.write_text('{', encoding='utf-8')
            seen = []
            def pause(seconds):
                seen.append(seconds)
                path.write_text(json.dumps(admitted()), encoding='utf-8')
            m.wait_admission(Child(), path, pause=pause)
            self.assertEqual(seen, [1])

    def test_original_commands_are_unchanged(self):
        gate = ROOT / 'COLD_RECOVERY_BINDING_CORRECTION_001/cold_recovery_gate.json'
        commands = m.d.commands(gate)
        common = [str(m.d.PYTHON), '-I', '-S', '-B']
        self.assertEqual(commands['continuation'], common + [str(ROOT / 'continuation.py'), '--repo', str(m.d.REPO), '--cold-gate', str(gate)])
        self.assertEqual(commands['finalizer'], common + [str(ROOT / 'finalizer.py'), '--repo', str(m.d.REPO), '--cold-gate', str(gate), '--attempt', '1', '--poll-seconds', '30'])

    def test_failure_never_launches_finalizer_or_retries(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_synthetic_') as temp:
            record = Path(temp)
            calls = []
            def fake_popen(command, **kwargs):
                calls.append(command)
                return Child((1,))
            with self.assertRaisesRegex(RuntimeError, 'exited before'):
                m.launch_children(ROOT / 'synthetic_gate.json', record, {}, popen=fake_popen, pause=lambda _: None)
            self.assertEqual(len(calls), 1)
            error = json.loads((record / 'supervisor_error.json').read_text())
            self.assertFalse(error['children_terminated_by_supervisor'])
            self.assertFalse(error['automatic_retry'])
            self.assertFalse((record / 'finalizer_launched.json').exists())

    def test_success_uses_two_owned_children_in_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_synthetic_') as temp:
            record = Path(temp) / 'record'
            record.mkdir()
            calls = []
            def fake_popen(command, **kwargs):
                calls.append(command)
                return Child((None, 0), 123456) if len(calls) == 1 else Child((0,), 123457)
            with patch.object(m, 'wait_admission', return_value=admitted()) as wait:
                self.assertEqual(m.launch_children(ROOT / 'synthetic_gate.json', record, {}, popen=fake_popen, pause=lambda _: None), 0)
            self.assertEqual(len(calls), 2)
            self.assertEqual(Path(calls[0][4]).name, 'continuation.py')
            self.assertEqual(Path(calls[1][4]).name, 'finalizer.py')
            wait.assert_called_once()
            self.assertEqual(json.loads((record / 'finish.json').read_text())['actual_child_exit_codes'], {'continuation': 0, 'finalizer': 0})


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix='owned002_spec_synthetic_')
        self.repo = Path(self.temp.name)
        self.here = self.repo / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
        self.here.mkdir(parents=True)
        self.python = self.repo / 'synthetic_python.exe'
        self.python.write_bytes(b'not executable; synthetic fixture only')
        for name in ('sequenced_supervisor_002.py', 'background_job_probe.py', 'continuation.py', 'finalizer.py'):
            (self.here / name).write_bytes(b'synthetic standard-library source fixture')
        (self.here / 'durable_supervisor.py').write_bytes((ROOT / 'durable_supervisor.py').read_bytes())
        old = self.here / 'durable_launch_001'
        old.mkdir()
        for name, value in (
            ('start.json', {'pid': 29376}),
            ('continuation_launched.json', {'pid': 22624}),
            ('supervisor_error.json', {'known_children': {'continuation': 22624}, 'children_terminated_by_supervisor': False, 'automatic_retry': False}),
        ):
            (old / name).write_text(json.dumps(value), encoding='utf-8')
        self.gate = self.here / 'COLD_RECOVERY_BINDING_CORRECTION_001/cold_recovery_gate.json'
        self.gate.parent.mkdir()
        self.gate.write_bytes(b'{}')
        files = list(self.here.rglob('*')) + [self.python]
        pins = {str(p): m.d.sha(p) for p in files if p.is_file()}
        self.launch = {'schema': 'paper3-owned-durable-launch-spec-v1', 'repository': str(self.repo),
                       'python_executable': str(self.python), 'cold_gate': str(self.gate),
                       'record_directory': str(self.here / 'durable_launch_002'), 'files_sha256': pins,
                       'scientific_changes_authorized': False, 'automatic_restart': False, 'workers': 2,
                       'finalizer_waits_for_post_resource_admission': True, 'manifest_digest': m.MANIFEST, 'F1_digest': m.F1}
        self.spec_path = self.here / 'DURABLE_LAUNCH_SPEC_002.json'
        self.patches = [patch.object(m, 'HERE', self.here), patch.object(m.d, 'REPO', self.repo),
                        patch.object(m.d, 'PYTHON', self.python), patch.object(m, 'native_pid_inactive', return_value=True)]
        for value in self.patches:
            value.start()

    def tearDown(self):
        for value in reversed(self.patches):
            value.stop()
        self.temp.cleanup()

    def check(self):
        return m.check_spec(self.launch, self.spec_path)

    def test_valid_exclusive_002_spec(self):
        gate, record, pins = self.check()
        self.assertEqual(gate, self.gate)
        self.assertEqual(record.name, 'durable_launch_002')
        self.assertEqual(pins, self.launch['files_sha256'])

    def test_001_spec_name_rejected(self):
        self.spec_path = self.here / 'DURABLE_LAUNCH_SPEC_001.json'
        with self.assertRaisesRegex(RuntimeError, '002 launch spec'):
            self.check()

    def test_001_record_rejected(self):
        self.launch['record_directory'] = str(self.here / 'durable_launch_001')
        with self.assertRaisesRegex(RuntimeError, '002 record'):
            self.check()

    def test_existing_002_record_rejected(self):
        (self.here / 'durable_launch_002').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.check()

    def test_original_gate_rejected(self):
        self.launch['cold_gate'] = str(self.here / 'COLD_RECOVERY_001/cold_recovery_gate.json')
        with self.assertRaisesRegex(RuntimeError, 'corrected gate'):
            self.check()

    def test_missing_source_pin_rejected(self):
        del self.launch['files_sha256'][str(self.here / 'continuation.py')]
        with self.assertRaisesRegex(RuntimeError, 'pin absent'):
            self.check()

    def test_changed_source_bytes_rejected(self):
        (self.here / 'continuation.py').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'SHA differs'):
            self.check()

    def test_helper_binding_cannot_be_changed(self):
        self.launch['files_sha256'][str(self.here / 'durable_supervisor.py')] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'helper binding'):
            self.check()

    def test_external_pin_rejected(self):
        self.launch['files_sha256'][str(self.repo / 'unapproved.bin')] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'Unexpected launch source'):
            self.check()

    def test_active_old_process_rejected(self):
        with patch.object(m, 'native_pid_inactive', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'still active'):
                self.check()

    def test_old_pid_identity_change_rejected(self):
        path = self.here / 'durable_launch_001/continuation_launched.json'
        path.write_text(json.dumps({'pid': 9999}), encoding='utf-8')
        self.launch['files_sha256'][str(path)] = m.d.sha(path)
        with self.assertRaisesRegex(RuntimeError, 'identities differ'):
            self.check()

    def test_existing_continuation_record_rejected(self):
        (self.here / 'continuation_001').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.check()

    def test_existing_continuation_lock_rejected(self):
        (self.here / 'CONTINUATION_EXCLUSIVE_RUN_LOCK.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.check()

    def test_existing_full2_launch_rejected(self):
        path = self.repo / 'verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/phase_launches/full_002'
        path.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.check()

    def test_existing_full2_execution_rejected(self):
        path = self.repo / 'results/p7_7_integrity_replication_batch20_env_v3/execution/full/A_FULL_0002'
        path.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.check()

    def test_wrong_population_rejected(self):
        self.launch['F1_digest'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'input identity'):
            self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
