"""V4 synthetic control checks; no full science scan or actual publication."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'final_readonly_acceptance.py'
payload = SOURCE.read_bytes()
AUDITOR_SHA = hashlib.sha256(payload).hexdigest()
A = types.ModuleType('paper3_v4_acceptance_synthetic_test_subject')
A.__file__ = str(SOURCE)
sys.modules[A.__name__] = A
exec(compile(payload, str(SOURCE), 'exec'), A.__dict__)


class SyntheticAuditor:
    def __init__(self, objects, digests):
        self.objects, self.digests = objects, digests

    def bound(self, path, digest):
        path = Path(path)
        A.require(self.digests.get(str(path)) == digest, 'synthetic binding SHA mismatch')
        return path

    def bound_json(self, path, digest):
        self.bound(path, digest)
        return copy.deepcopy(self.objects[str(Path(path))])

    def sha(self, path):
        return self.digests[str(Path(path))]

    def binding_map(self, values):
        for name, digest in values.items(): self.bound(name, digest)


class PreservedHistoricalMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ep = A.read(A.ERRATUM_PLAN)
        cls.actual = {str(path): A.read(path) for path in
            (A.ROOT_RECOVERY_START, A.OLD_ROOT_OBSERVER_FAILURE, A.ERRATUM_RECORD / 'finish.json',
             A.ERRATUM_RECORD / 'start.json')}

    def setUp(self):
        self.objects = copy.deepcopy(self.actual)
        digests = {str(A.ROOT_RECOVERY_START): A.OLD_METADATA_START_SHA,
            str(A.OLD_ROOT_OBSERVER_FAILURE): A.OLD_ROOT_OBSERVER_FAILURE_SHA,
            str(A.ERRATUM_RECORD / 'finish.json'): A.OLD_METADATA_FINISH_SHA,
            str(A.ERRATUM_RECORD / 'start.json'): 'a' * 64}
        self.a = SyntheticAuditor(self.objects, digests)

    def inspect(self):
        with patch.object(A, 'read', side_effect=lambda path: copy.deepcopy(self.objects[str(Path(path))])):
            return A.check_original_metadata_observer_failure(self.a, self.ep)

    def test_all_frozen_v3_scientific_artifact_checks_unchanged(self):
        result = A.check_frozen_v3_acceptance_preservation(A.Auditor())
        self.assertTrue(result['full_scientific_and_published_artifact_prefix_byte_identical'])

    def test_unknown_historical_exit_is_preserved(self):
        value = self.inspect()
        self.assertFalse(value['history_all_process_exits_verified'])
        self.assertFalse(value['old_metadata_process_exit_zero_verified'])
        self.assertEqual(value['metadata_original_producer_exit'], 'NOT_OBSERVED; ROOT_EXIT_OBSERVER_FAILED')

    def test_historical_zero_fabrication_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['original_metadata_producer_actual_exit_code'] = 0
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_exit_reconstruction_claim_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['actual_exit_zero_reconstructed'] = True
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_observer_actual_one_changed_to_zero_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['actual_tool_exit_code'] = 0
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_observer_actual_one_boolean_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['actual_tool_exit_code'] = True
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_missing_published_finish_binding_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['producer_finish_sha256'] = 'b' * 64
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_changed_h2_root_rejected(self):
        self.objects[str(A.ERRATUM_RECORD / 'finish.json')]['root_handoff_sha256'] = 'b' * 64
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_changed_erratum_zip_rejected(self):
        self.objects[str(A.ERRATUM_RECORD / 'finish.json')]['zip_sha256'] = 'b' * 64
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_published_finish_not_success_rejected(self):
        self.objects[str(A.ERRATUM_RECORD / 'finish.json')]['status'] = 'FAILED'
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_original_pid_changed_rejected(self):
        self.objects[str(A.ROOT_RECOVERY_START)]['pid'] += 1
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_original_creation_identity_changed_rejected(self):
        self.objects[str(A.ROOT_RECOVERY_START)]['creation_filetime'] += 1
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_original_command_changed_rejected(self):
        self.objects[str(A.ROOT_RECOVERY_START)]['command_line'] += ' --fake'
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_original_source_pin_changed_rejected(self):
        self.objects[str(A.OLD_ROOT_OBSERVER_FAILURE)]['observer_source_sha256'] = 'b' * 64
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_old_exit_receipt_retroactively_created_rejected(self):
        original_exists = Path.exists
        with patch.object(Path, 'exists', lambda path: True if path == A.ROOT_RECOVERY_EXIT else original_exists(path)):
            with self.assertRaises(A.AcceptanceError): self.inspect()


class NewPostpublicationTerminal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = A.read(A.POST_PLAN)
        cls.proof = A.read(A.POST_PROOF)

    def setUp(self):
        self.plan, self.proof = copy.deepcopy(self.plan), copy.deepcopy(self.proof)
        helper = A.POST_FINALIZATION / 'postpublication_finalize.py'
        argv = [str(A.METADATA_PYTHON), '-I', '-S', '-B', str(helper), 'execute', '--plan',
            str(A.POST_PLAN), '--plan-sha256', A.POST_PLAN_SHA]
        self.identity = {'pid': 99999, 'creation_filetime': 134361000000000000,
            'image': str(A.METADATA_PYTHON), 'command_line': subprocess.list2cmdline(argv)}
        common = {'plan_path': str(A.POST_PLAN), 'plan_sha256': A.POST_PLAN_SHA,
            'source_sha256': copy.deepcopy(A.POST_SOURCE_PINS), 'automatic_retry': False,
            'models_statistics_or_root_publication_executed': False, 'query_handle_retained': True,
            'helper_path': str(helper), 'helper_sha256': A.POST_SOURCE_PINS[str(helper)],
            'cmdargv': argv, **self.identity}
        self.start = {**common, 'schema': 'paper3-postpublication-process-start-v1', 'producer': 'ROOT_OWNING_POPEN'}
        self.observation = {**common, 'schema': 'paper3-postpublication-process-exit-v1',
            'producer': 'ROOT_OWNING_POPEN_WAIT', 'actual_exit_code': 0, 'native_exit_code': 0,
            'identity_unchanged': True, 'start_receipt_sha256': 'a' * 64, 'native_observation_sha256': 'b' * 64,
            'finish_path': str(A.POST_RECORD / 'finish.json'), 'finish_sha256': 'c' * 64,
            'log_path': str(A.POST_FINALIZATION / 'POSTPUBLICATION_PROCESS_001.log')}
        self.native = {**self.identity, 'schema': 'paper3-postpublication-native-exit-observation-v1',
            'producer': 'ROOT_OWNING_POPEN_WAIT', 'plan_sha256': A.POST_PLAN_SHA,
            'actual_exit_code': 0, 'native_exit_code': 0}
        self.producer_start = {'schema': 'paper3-postpublication-finalization-start-v1',
            'pid': self.identity['pid'], 'plan_sha256': A.POST_PLAN_SHA}
        self.certificate = {'schema': 'paper3-metadata-postpublication-artifact-finalization-v1',
            'status': 'COMPLETED', 'scope': A.POST_SCOPE, 'plan_sha256': A.POST_PLAN_SHA,
            'pid': self.identity['pid'], 'source_sha256': copy.deepcopy(A.POST_SOURCE_PINS),
            'original_metadata_producer_pid': 10108, 'original_metadata_producer_actual_exit_code': 'NOT_OBSERVED',
            'root_exit_observer_failed': True, 'original_observer_tool_actual_exit_code': 1,
            'history_all_process_exits_verified': False, 'original_exit_zero_contract_satisfied': False,
            'scientific_acceptance': 'NOT_PERFORMED_BY_THIS_METADATA_FINALIZER',
            'models_statistics_or_root_publication_executed': False,
            'producer_plan_sha256': A.OLD_METADATA_PLAN_SHA, 'producer_finish_sha256': A.OLD_METADATA_FINISH_SHA,
            'observer_failure_sha256': A.OLD_ROOT_OBSERVER_FAILURE_SHA,
            'package': str(A.POST_PACKAGE), 'package_manifest_sha256': A.PUBLISHED_ERRATUM_MANIFEST_SHA,
            'zip': str(A.POST_PACKAGE.with_suffix('.zip')), 'zip_sha256': A.PUBLISHED_ERRATUM_ZIP_SHA,
            'root_handoff_sha256': A.PUBLISHED_H2, 'statistics_manifest_sha256': A.PUBLISHED_STATISTICS_MANIFEST_SHA,
            'statistics_execution_receipt_sha256': A.PUBLISHED_STATISTICS_RECEIPT_SHA,
            'statistics_bytes_unchanged': True, 'reports_inverse_bytes_preserved': True}

    def inspect(self):
        return A.check_postpublication_exit_contract(self.start, self.observation, self.native,
            self.certificate, self.producer_start, 'a' * 64, 'c' * 64, 'b' * 64, A.POST_PLAN_SHA)

    def test_controlled_real_plan_and_proof(self):
        self.assertEqual(hashlib.sha256(A.POST_PLAN.read_bytes()).hexdigest(), A.POST_PLAN_SHA)
        self.assertEqual(hashlib.sha256(A.POST_PROOF.read_bytes()).hexdigest(), A.POST_PROOF_SHA)
        A.check_postpublication_plan_contract(self.plan, self.proof)

    def test_proof_contract_negative_controls(self):
        for key, bad in [('schema', 'arbitrary'), ('tests_run', True), ('tests_run', 10),
                ('all_pass', False), ('errors', True), ('failures', 1), ('skipped', 1),
                ('implementation_sha256', {}), ('actual_models_statistics_publication_or_process_control', True)]:
            with self.subTest(key=key, bad=bad):
                proof = copy.deepcopy(self.proof); proof[key] = bad
                with self.assertRaises(A.AcceptanceError): A.check_postpublication_plan_contract(self.plan, proof)

    def test_plan_contract_negative_controls(self):
        for key, bad in [('scope', 'all_history'), ('source_sha256', {}), ('bound_files_sha256', {}),
                ('test_proof_sha256', 'd' * 64), ('record_root', str(A.ERRATUM_RECORD)),
                ('original_metadata_producer_actual_exit_code', 0), ('models_statistics_or_root_publication_executed', True)]:
            with self.subTest(key=key):
                plan = copy.deepcopy(self.plan); plan[key] = bad
                with self.assertRaises(A.AcceptanceError): A.check_postpublication_plan_contract(plan, self.proof)

    def test_new_native_and_owning_zero_without_old_zero(self):
        result = self.inspect()
        self.assertEqual(result['actual_exit_code'], 0)
        self.assertFalse(result['history_all_process_exits_verified'])
        self.assertFalse(result['old_metadata_process_exit_zero_verified'])

    def test_owning_and_native_exit_negative_controls(self):
        for target in ('observation', 'native'):
            for key, bad in [('actual_exit_code', 1), ('native_exit_code', 1),
                    ('actual_exit_code', False), ('native_exit_code', False), ('producer', 'SYNTHETIC')]:
                with self.subTest(target=target, key=key, bad=bad):
                    item = getattr(self, target); original = item[key]; item[key] = bad
                    try:
                        with self.assertRaises(A.AcceptanceError): self.inspect()
                    finally: item[key] = original

    def test_receipt_binding_negative_controls(self):
        for key, bad in [('start_receipt_sha256', 'd' * 64), ('finish_sha256', 'd' * 64),
                ('native_observation_sha256', 'd' * 64), ('query_handle_retained', False),
                ('identity_unchanged', False), ('automatic_retry', True), ('source_sha256', {}),
                ('finish_path', str(A.ERRATUM_RECORD / 'finish.json'))]:
            with self.subTest(key=key):
                original = self.observation[key]; self.observation[key] = bad
                try:
                    with self.assertRaises(A.AcceptanceError): self.inspect()
                finally: self.observation[key] = original

    def test_native_identity_negative_controls(self):
        for target in ('start', 'observation', 'native'):
            for key, bad in [('pid', 1), ('pid', True), ('creation_filetime', 1),
                    ('creation_filetime', True), ('image', str(A.ROOT_RECOVERY_START)), ('command_line', '--fake')]:
                with self.subTest(target=target, key=key, bad=bad):
                    item = getattr(self, target); original = item[key]; item[key] = bad
                    try:
                        with self.assertRaises(A.AcceptanceError): self.inspect()
                    finally: item[key] = original

    def test_certificate_does_not_reconstruct_old_exit_or_waive_science(self):
        for key, bad in [('original_metadata_producer_actual_exit_code', 0),
                ('history_all_process_exits_verified', True), ('original_exit_zero_contract_satisfied', True),
                ('scientific_acceptance', 'PASS'), ('original_observer_tool_actual_exit_code', 0),
                ('root_exit_observer_failed', False), ('source_sha256', {}), ('pid', 10108), ('status', 'FAILED')]:
            with self.subTest(key=key):
                original = self.certificate[key]; self.certificate[key] = bad
                try:
                    with self.assertRaises(A.AcceptanceError): self.inspect()
                finally: self.certificate[key] = original

    def test_certificate_artifact_binding_negative_controls(self):
        for key in ('producer_plan_sha256', 'producer_finish_sha256', 'observer_failure_sha256',
                'package_manifest_sha256', 'zip_sha256', 'root_handoff_sha256',
                'statistics_manifest_sha256', 'statistics_execution_receipt_sha256'):
            with self.subTest(key=key):
                original = self.certificate[key]; self.certificate[key] = 'd' * 64
                try:
                    with self.assertRaises(A.AcceptanceError): self.inspect()
                finally: self.certificate[key] = original

    def test_finalizer_cannot_claim_statistics_or_publication(self):
        self.certificate['models_statistics_or_root_publication_executed'] = True
        with self.assertRaises(A.AcceptanceError): self.inspect()

    def test_finalizer_changed_reports_or_statistics_rejected(self):
        for key in ('statistics_bytes_unchanged', 'reports_inverse_bytes_preserved'):
            original = self.certificate[key]; self.certificate[key] = False
            try:
                with self.assertRaises(A.AcceptanceError): self.inspect()
            finally: self.certificate[key] = original

    def test_wrong_producer_start_rejected(self):
        self.producer_start['pid'] = 10108
        with self.assertRaises(A.AcceptanceError): self.inspect()


def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode): raise RuntimeError('requires -I -S -B')
    output = HERE / 'FINAL_ACCEPTANCE_METADATA_SYNTHETIC_TEST_RESULTS_001.json'
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = hashlib.sha256(SOURCE.read_bytes()).hexdigest() == AUDITOR_SHA
    proof = {'schema': 'paper3-independent-final-acceptance-v4-metadata-test-proof-v1',
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'all_pass': result.wasSuccessful() and unchanged,
        'source_sha256': {str(SOURCE): AUDITOR_SHA, str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'auditor_source_unchanged_during_tests': unchanged, 'frozen_v3_scientific_artifact_checks_byte_identical': True,
        'full_scientific_scan_performed': False, 'actual_models_statistics_or_publication_executed': False,
        'original_metadata_OS_exit_reconstructed': False,
        'scope': 'Synthetic new control contracts and preservation of unobserved old metadata exit; frozen scientific/artifact source comparison.'}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps({'proof_path': str(output), 'proof_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'all_pass': proof['all_pass'], 'tests_run': result.testsRun}), flush=True)
    return 0 if proof['all_pass'] else 1


if __name__ == '__main__': raise SystemExit(main())
