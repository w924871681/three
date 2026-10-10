"""Owned observer-host synthetic tests; no real collector/model is executed."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch
root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('recording_host_under_test', root / 'cold_background_entry.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HostTests(unittest.TestCase):
    def test_resources_return_exact_same_unmodified_object(self):
        value = {'free_commit_bytes': 12, 'minimum_free_commit_bytes': 99}
        class Base:
            def resources(self): return value
        with patch.object(m, 'emit') as emit:
            observer = m.observed_class(Base, root)()
            self.assertIs(observer.resources(), value)
            self.assertIs(observer.resources(), value)
        self.assertEqual(emit.call_count, 2)
        self.assertEqual(emit.call_args_list[0].args[0].name, 'resources_001.json')

    def test_readonly_never_calls_recovery(self):
        module = types.SimpleNamespace(ReadOnlyWindowsObserver=object,
                                       run_readonly=lambda *a, **k: {},
                                       run_recovery=lambda *a, **k: self.fail('Must not publish bridge'))
        result = m.collect(module, root, root, root, False)
        self.assertEqual(result['status'], 'READONLY_COLD_AUDIT_PASS')

    def test_explicit_authorization_only_passes_exact_collector_context(self):
        context = object()
        seen = []
        module = types.SimpleNamespace(ReadOnlyWindowsObserver=object,
                                       run_readonly=lambda *a, **k: context,
                                       run_recovery=lambda c, **k: (seen.append(c) or {'status': 'PASS'}))
        self.assertEqual(m.collect(module, root, root, root, True)['status'], 'PASS')
        self.assertEqual(seen, [context])

    def test_collector_failure_is_not_reinterpreted(self):
        def fail(*a, **k): raise RuntimeError('Synthetic resource rejection')
        module = types.SimpleNamespace(ReadOnlyWindowsObserver=object, run_readonly=fail)
        with self.assertRaisesRegex(RuntimeError, 'resource rejection'):
            m.collect(module, root, root, root, False)

    def test_scope_rejects_external_or_unexpected_paths(self):
        for path in (Path(r'C:\unrelated\output'), root / 'unexpected'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                m.scope(path, 'COLD_PREFLIGHT_002')


if __name__ == '__main__':
    unittest.main(verbosity=2)
