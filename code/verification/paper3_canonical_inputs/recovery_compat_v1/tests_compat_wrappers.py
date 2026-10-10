"""Synthetic entry/supervisor tests; never invokes real child or model code."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('compat_launcher_under_test', HERE / 'compat_supervisor_003.py')
l = importlib.util.module_from_spec(spec); spec.loader.exec_module(l)
spec = importlib.util.spec_from_file_location('compat_entry_under_test', HERE / 'compat_entry.py')
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


class Child:
    pid = 123
    def poll(self): return None


class WrapperTests(unittest.TestCase):
    def test_fixed_wrapper_commands(self):
        gate = l.OLD / 'COLD_RECOVERY_METADATA_COMPAT_001/cold_recovery_gate.json'
        commands = l.commands(gate)
        self.assertEqual(set(commands), {'continuation', 'finalizer'})
        for name, command in commands.items():
            self.assertEqual(command[:4], [str(l.PYTHON), '-I', '-S', '-B'])
            self.assertEqual(command[4], str(HERE / ('compat_' + name + '.py')))
            self.assertEqual(command[command.index('--cold-gate') + 1], str(gate))
        self.assertEqual(commands['finalizer'][-4:], ['--attempt', '1', '--poll-seconds', '30'])

    def test_no_finalizer_without_actual_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            with patch.object(l.s, 'wait_admission', side_effect=RuntimeError('not admitted')):
                with self.assertRaises(RuntimeError):
                    l.launch(Path('fakegate'), Path(folder), {}, popen=lambda *a, **kw: calls.append(a[0]) or Child())
            self.assertEqual(len(calls), 1)
            self.assertIn('compat_continuation.py', calls[0][4])
            self.assertTrue((Path(folder) / 'supervisor_error.json').exists())

    def test_finalizer_only_after_actual_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            events = []
            def admit(*args): events.append('admit'); return {'valid_synthetic': True}
            def spawn(command, **kwargs): events.append(Path(command[4]).name); return Child()
            with patch.object(l.s, 'wait_admission', side_effect=admit), patch.object(l.d, 'observe_children', return_value=0):
                self.assertEqual(l.launch(Path('fakegate'), Path(folder), {}, popen=spawn), 0)
            self.assertEqual(events, ['compat_continuation.py', 'admit', 'compat_finalizer.py'])

    def test_pin_change_stops_before_spawn(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'; source.write_bytes(b'actual')
            with self.assertRaises(RuntimeError), patch('subprocess.Popen') as spawn:
                l.launch(Path('fakegate'), Path(folder), {str(source): 'wrong'}, popen=spawn)
            spawn.assert_not_called()

    def test_journal_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'receipt.json'
            l.d.emit(target, {'original': True})
            before = target.read_bytes()
            with self.assertRaises(FileExistsError): l.d.emit(target, {'replace': True})
            self.assertEqual(target.read_bytes(), before)

    def test_entry_rejects_unknown_kind_before_import(self):
        with self.assertRaises(RuntimeError), patch.object(e, 'load_module') as load:
            e.run('unknown', HERE / 'unknown.py')
        load.assert_not_called()

    def test_entry_rejects_wrong_actual_entry(self):
        with self.assertRaises(RuntimeError), patch.object(e, 'load_module') as load:
            e.run('continuation', HERE / 'different.py')
        load.assert_not_called()

    def test_original_sources_still_exact(self):
        for kind, expected in e.ORIGINAL_SHA.items():
            self.assertEqual(e.sha(e.ORIGINAL / (kind + '.py')), expected)

    def test_wrapper_proof_rejects_incomplete_tests(self):
        with self.assertRaises(RuntimeError): l.check_wrapper_proof({'all_pass': True})

    def test_wrapper_proof_rejects_source_change(self):
        value = {'all_pass': True, 'exit_code': 0, 'tests_run': 8, 'failures': 0, 'errors': 0,
                 'skipped': 0, 'models_generators_or_statistics_executed': False,
                 'real_processes_launched': False, 'implementation_sha256': {}}
        with self.assertRaises(RuntimeError): l.check_wrapper_proof(value)


if __name__ == '__main__': unittest.main(verbosity=2)
