"""Synthetic adapter and original consumer regressions; no scientific execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent / 'replication_abrupt_recovery_v1'
spec = importlib.util.spec_from_file_location('owned_strict_legacy_adapter_tests', HERE / 'strict_legacy_proof_adapter.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
reg_spec = importlib.util.spec_from_file_location('owned_original_consumer_regressions', RECOVERY / 'test_continuation.py')
reg = importlib.util.module_from_spec(reg_spec)
reg_spec.loader.exec_module(reg)
# The regression fixture's synthetic guard is explicitly mocked. Production
# installation and its real binding guard are tested separately below.
a.compile_into_private_module(reg.f, lambda repo, gate: None)
reg.c.f = reg.f


def fresh_module():
    spec = importlib.util.spec_from_file_location('owned_fresh_private_original_finalizer', a.ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy():
    path = RECOVERY / 'COLD_RECOVERY_SYNTHETIC_TEST_RESULTS_ATTEMPT001.json'
    assert a.sha(path) == a.LEGACY_RECEIPT_SHA
    return json.loads(path.read_text(encoding='utf-8'))


class PredicateTests(unittest.TestCase):
    def test_actual_legacy_metadata_qualifies(self):
        self.assertTrue(a.legacy_proof_matches(legacy()))

    def test_explicit_fail_never_qualifies(self):
        proof = legacy(); proof['status'] = 'FAIL'
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_status_null_does_not_qualify(self):
        proof = legacy(); proof['status'] = None
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_missing_schema_rejected(self):
        proof = legacy(); proof.pop('schema')
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_wrong_test_count_rejected(self):
        proof = legacy(); proof['tests_run'] = 47
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_boolean_count_rejected(self):
        proof = legacy(); proof['failures'] = False
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_missing_scope_rejected(self):
        proof = legacy(); proof.pop('actual_processes_modified')
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_executed_scientific_scope_rejected(self):
        proof = legacy(); proof['actual_models_generators_or_statistics_executed'] = True
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_nonzero_failure_rejected(self):
        proof = legacy(); proof['errors'] = 1
        self.assertFalse(a.legacy_proof_matches(proof))

    def test_false_all_pass_rejected(self):
        proof = legacy(); proof['all_pass'] = False
        self.assertFalse(a.legacy_proof_matches(proof))


class LegacyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reg.FinalizerTests(methodName='test_cold_exact_ratio10_config_admitted')
        self.fixture.setUp()
        self.proof_path = self.fixture.repo / reg.f.SELF_REL / reg.f.COLD_PROOF
        old = reg.f.load(self.proof_path)
        proof = legacy()
        proof['implementation_sha256'] = old['implementation_sha256']
        reg.put(self.proof_path, proof)
        self.rebind()

    def tearDown(self):
        self.fixture.tearDown()

    def rebind(self):
        reg.alter(self.fixture.gate_path, lambda gate: gate['evidence_sha256'].update({str(self.proof_path): reg.f.sha(self.proof_path)}))

    def test_full_synthetic_consumer_accepts_strict_legacy_schema(self):
        self.assertTrue(reg.f.verify_transition_gate(self.fixture.repo, self.fixture.gate_path, admission=True, check_resource=True))

    def test_full_consumer_still_rejects_true_failure(self):
        reg.alter(self.proof_path, lambda proof: proof.update(failures=1))
        self.rebind()
        with self.assertRaises(reg.f.FinalizerError):
            reg.f.verify_transition_gate(self.fixture.repo, self.fixture.gate_path)

    def test_full_consumer_still_rejects_missing_scope(self):
        reg.alter(self.proof_path, lambda proof: proof.pop('actual_original_results_written'))
        self.rebind()
        with self.assertRaises(reg.f.FinalizerError):
            reg.f.verify_transition_gate(self.fixture.repo, self.fixture.gate_path)

    def test_full_consumer_still_rejects_changed_input_manifest(self):
        reg.alter(self.fixture.gate_path, lambda gate: gate.update(input_bundle_digest='0' * 64))
        with self.assertRaises(reg.f.FinalizerError):
            reg.f.verify_transition_gate(self.fixture.repo, self.fixture.gate_path)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE, prefix='owned_adapter_binding_synthetic_')
        self.folder = Path(self.temp.name)
        self.module = fresh_module()
        self.proof_path = self.folder / a.PROOF_NAME
        self.gate_path = self.folder / 'synthetic_gate.json'
        own = {name: a.sha(HERE / name) for name in a.OWN_SOURCES}
        self.proof = {'schema': a.PROOF_SCHEMA, 'status': 'PASS', 'all_pass': True,
                      'tests_run': 1, 'failures': 0, 'errors': 0, 'skipped': 0,
                      'real_experimental_outcomes_read': False, 'real_experiment_processes_launched': False,
                      'models_generators_statistics_executed': False, 'real_environment_hashed': False,
                      'implementation_sha256': own, 'original_finalizer_sha256': a.ORIGINAL_SHA,
                      'original_verify_function_sha256': a.ORIGINAL_FUNCTION_SHA,
                      'legacy_original_receipt_sha256': a.LEGACY_RECEIPT_SHA,
                      'synthetic_fixture_only': True}
        reg.put(self.proof_path, self.proof)
        pins = {str(HERE / name): digest for name, digest in own.items()}
        pins[str(self.proof_path)] = a.sha(self.proof_path)
        self.gate = {'source_bindings_sha256': dict(pins), 'evidence_sha256': dict(pins), 'synthetic_fixture_only': True}
        self.gate['evidence_sha256'][str(a.ORIGINAL.parent / 'COLD_RECOVERY_SYNTHETIC_TEST_RESULTS_ATTEMPT001.json')] = a.LEGACY_RECEIPT_SHA
        reg.put(self.gate_path, self.gate)

    def tearDown(self):
        self.temp.cleanup()

    def test_production_install_preserves_module_file_and_globals(self):
        original_file = self.module.__file__
        old_sha_function = self.module.sha
        record = a.install(self.module, a.REPO, self.gate_path, self.proof_path)
        self.assertEqual(self.module.__file__, original_file)
        self.assertIs(self.module.sha, old_sha_function)
        self.assertIs(self.module.verify_transition_gate.__globals__, self.module.__dict__)
        self.assertTrue(record['full_pin_hash_checks_retained'])
        self.assertEqual(record['original_finalizer_sha256'], a.ORIGINAL_SHA)

    def test_self_source_missing_from_source_map_rejected(self):
        self.gate['source_bindings_sha256'].pop(str(HERE / 'strict_legacy_proof_adapter.py'))
        reg.put(self.gate_path, self.gate)
        with self.assertRaisesRegex(RuntimeError, 'source not exact'):
            a.install(self.module, a.REPO, self.gate_path, self.proof_path)

    def test_proof_missing_from_evidence_map_rejected(self):
        self.gate['evidence_sha256'].pop(str(self.proof_path))
        reg.put(self.gate_path, self.gate)
        with self.assertRaisesRegex(RuntimeError, 'proof not exact'):
            a.install(self.module, a.REPO, self.gate_path, self.proof_path)

    def test_failed_adapter_test_receipt_rejected(self):
        self.proof['status'] = 'FAIL'
        reg.put(self.proof_path, self.proof)
        with self.assertRaisesRegex(RuntimeError, 'not PASS'):
            a.install(self.module, a.REPO, self.gate_path, self.proof_path)

    def test_gate_switch_after_install_rejected_before_original_checks(self):
        a.install(self.module, a.REPO, self.gate_path, self.proof_path)
        with self.assertRaisesRegex(RuntimeError, 'gate/repository changed'):
            self.module.verify_transition_gate(a.REPO, self.folder / 'other_gate.json')

    def test_source_pin_change_after_install_rejected_each_call(self):
        a.install(self.module, a.REPO, self.gate_path, self.proof_path)
        self.gate['source_bindings_sha256'][str(HERE / 'strict_legacy_proof_adapter.py')] = '0' * 64
        reg.put(self.gate_path, self.gate)
        with self.assertRaisesRegex(RuntimeError, 'source not exact'):
            self.module.verify_transition_gate(a.REPO, self.gate_path)

    def test_double_install_rejected(self):
        a.install(self.module, a.REPO, self.gate_path, self.proof_path)
        with self.assertRaisesRegex(RuntimeError, 'already installed'):
            a.install(self.module, a.REPO, self.gate_path, self.proof_path)

    def test_actual_legacy_receipt_binding_cannot_change(self):
        self.gate['evidence_sha256'][str(a.ORIGINAL.parent / 'COLD_RECOVERY_SYNTHETIC_TEST_RESULTS_ATTEMPT001.json')] = '0' * 64
        reg.put(self.gate_path, self.gate)
        with self.assertRaisesRegex(RuntimeError, 'Actual legacy receipt'):
            a.install(self.module, a.REPO, self.gate_path, self.proof_path)


def suite():
    result = unittest.TestSuite()
    result.addTests(unittest.defaultTestLoader.loadTestsFromModule(reg))
    for case in (PredicateTests, LegacyIntegrationTests, BindingTests):
        result.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    return result
