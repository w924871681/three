"""Synthetic post-admission scheduling tests; no real child or model launched."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sequenced_under_test', root / 'sequenced_supervisor.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Child:
    def __init__(self, code=None): self.code = code
    def poll(self): return self.code


class SchedulingTests(unittest.TestCase):
    def test_actual_integrity_admission_receipt_releases_finalizer(self):
        with tempfile.TemporaryDirectory(dir=root, prefix='owned_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            value = {'outcome_based_continuation': False,
                     'command': ['--phase', 'full', '--attempt', '2', '--workers', '2']}
            path.write_text(json.dumps(value), encoding='utf-8')
            self.assertEqual(m.wait_admission(Child(), path), value)

    def test_continuation_exit_before_admission_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'exited before'):
            m.wait_admission(Child(1), root / 'synthetic_absent_no_write')

    def test_wrong_worker_admission_rejected(self):
        with tempfile.TemporaryDirectory(dir=root, prefix='owned_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            path.write_text(json.dumps({'outcome_based_continuation': False,
                                      'command': ['--phase', 'full', '--attempt', '2', '--workers', '1']}), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
                m.wait_admission(Child(), path)

    def test_normal_partial_receipt_waits_without_admitting(self):
        with tempfile.TemporaryDirectory(dir=root, prefix='owned_synthetic_') as temp:
            path = Path(temp) / 'full_start.json'
            path.write_text('{', encoding='utf-8')
            seen = []
            def pause(seconds):
                seen.append(seconds)
                path.write_text(json.dumps({'outcome_based_continuation': False,
                                          'command': ['--phase', 'full', '--attempt', '2', '--workers', '2']}), encoding='utf-8')
            m.wait_admission(Child(), path, pause=pause)
            self.assertEqual(seen, [1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
