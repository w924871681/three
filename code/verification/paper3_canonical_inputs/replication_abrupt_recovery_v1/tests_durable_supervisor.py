"""Synthetic tests only; never launches an experimental command."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('durable_under_test', HERE / 'durable_supervisor.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DurableTests(unittest.TestCase):
    def test_no_job_allowed(self):
        d.check_job({'is_in_any_job': False})

    def test_observed_global_job_allowed(self):
        d.check_job({'is_in_any_job': True, 'limits': {'flags': 6144}})

    def test_caller_kill_close_job_rejected(self):
        with self.assertRaises(RuntimeError):
            d.check_job({'is_in_any_job': True, 'limits': {'flags': 10240}})

    def test_each_scientifically_incompatible_quota_rejected(self):
        for flag in (2, 4, 8, 256, 512):
            with self.subTest(flag=flag), self.assertRaises(RuntimeError):
                d.check_job({'is_in_any_job': True, 'limits': {'flags': flag}})

    def test_inaccessible_job_rejected(self):
        with self.assertRaises(RuntimeError):
            d.check_job({'is_in_any_job': True, 'limits_error': 5})

    def test_commands_fixed_no_shell_or_direct_science(self):
        gate = HERE / 'COLD_RECOVERY_001/cold_recovery_gate.json'
        commands = d.commands(gate)
        self.assertEqual(set(commands), {'continuation', 'finalizer'})
        for name, value in commands.items():
            self.assertEqual(value[:4], [str(d.PYTHON), '-I', '-S', '-B'])
            self.assertIn(str(gate), value)
            self.assertTrue(value[4].endswith(name + '.py'))
            self.assertNotIn('shell', value)

    def test_wrong_protocol_spec_rejected(self):
        with self.assertRaises(RuntimeError):
            d.check_spec({}, HERE / 'DURABLE_LAUNCH_SPEC_001.json')

    def test_restart_authorization_rejected(self):
        with self.assertRaises(RuntimeError):
            d.check_spec({'schema': 'paper3-owned-durable-launch-spec-v1',
                          'scientific_changes_authorized': False, 'automatic_restart': True},
                         HERE / 'DURABLE_LAUNCH_SPEC_001.json')

    def test_actual_child_codes_observed_without_retry_or_kill(self):
        class Child:
            pid = 12345
            def __init__(self, code): self.code = code
            def poll(self): return self.code
        records = []
        with patch.object(d, 'emit', side_effect=lambda p, v: records.append((p.name, v))):
            code = d.observe_children(HERE, {'continuation': Child(7), 'finalizer': Child(0)},
                                      pause=lambda n: self.fail('No sleeping for completed fake children'))
        self.assertEqual(code, 1)
        self.assertEqual(records[-1][0], 'failure.json')
        self.assertEqual(records[-1][1]['actual_child_exit_codes'], {'continuation': 7, 'finalizer': 0})
        self.assertFalse(records[-1][1]['scientific_integrity_pass_claimed'])

    def test_both_actual_success_not_scientific_pass(self):
        class Child:
            pid = 1
            def poll(self): return 0
        records = []
        with patch.object(d, 'emit', side_effect=lambda p, v: records.append((p.name, v))):
            self.assertEqual(d.observe_children(HERE, {'continuation': Child(), 'finalizer': Child()}), 0)
        self.assertEqual(records[-1][0], 'finish.json')
        self.assertFalse(records[-1][1]['scientific_integrity_pass_claimed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
