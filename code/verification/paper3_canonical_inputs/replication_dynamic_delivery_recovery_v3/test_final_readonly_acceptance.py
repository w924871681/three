"""Synthetic negative tests for V3 metadata control acceptance; no production run."""
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
A = types.ModuleType('paper3_v3_acceptance_synthetic_test_subject')
A.__file__ = str(SOURCE)
sys.modules[A.__name__] = A
exec(compile(payload, str(SOURCE), 'exec'), A.__dict__)


class SyntheticAuditor:
    """An in-memory evidence binding fixture, never a production acceptance."""
    def __init__(self, objects, digests):
        self.objects, self.digests = objects, digests

    def bound(self, path, digest):
        path = Path(path)
        A.require(self.digests.get(str(path)) == digest, 'synthetic binding SHA mismatch')
        return path

    def bound_json(self, path, digest):
        self.bound(path, digest)
        return copy.deepcopy(self.objects[str(Path(path))])

    def binding_map(self, values):
        for name, digest in values.items():
            self.bound(name, digest)


class MetadataContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = A.read(A.OLD_ERRATUM_PLAN)
        cls.old_objects = {path: A.read(path) for path in A.OLD_FAILURES if Path(path).suffix == '.json'}
        # Only frozen source text and small metadata are read; no numerical outputs.
        cls.transform = A.boundary_transform_from_frozen_source(A.Auditor())
        cls.sources = {str(A.METADATA_RECOVERY / name): hashlib.sha256((A.METADATA_RECOVERY / name).read_bytes()).hexdigest()
            for name in A.METADATA_OWN}

    def setUp(self):
        self.proof_sha = 'd' * 64
        self.plan_sha = 'e' * 64
        recovery = {'schema': 'paper3-boundary-stop-metadata-recovery-v2',
            'original_plan_path': str(A.OLD_ERRATUM_PLAN), 'original_plan_sha256': A.OLD_ERRATUM_PLAN_SHA,
            'source_sha256': copy.deepcopy(self.sources), 'test_proof_path': str(A.RECOVERY_PROOF),
            'test_proof_sha256': self.proof_sha, 'boundary_transform': copy.deepcopy(self.transform),
            'old_failure_files_sha256': copy.deepcopy(A.OLD_FAILURES), 'real_smoke_files_sha256': copy.deepcopy(A.SMOKE_PINS),
            'old_supervisor_failure_preserved': True, 'models_or_statistics_restarted': False,
            'automatic_retry': False, 'DW0001_STOP_consumption_claimed': False, 'created_utc': 'synthetic'}
        self.ep = {**copy.deepcopy(self.original), 'record_root': str(A.ERRATUM_RECORD), 'metadata_recovery': recovery}
        self.proof = {'schema': 'paper3-boundary-stop-recovery-test-proof-v1', 'all_pass': True,
            'tests_run': 16, 'errors': 0, 'failures': 0, 'skipped': 0, 'source_sha256': copy.deepcopy(self.sources),
            'boundary_transform': copy.deepcopy(self.transform), 'models_statistics_real_publication_or_process_control': False,
            'real_smoke_metadata_readonly_pass': True}
        self.objects = {**copy.deepcopy(self.old_objects), str(A.OLD_ERRATUM_PLAN): copy.deepcopy(self.original),
            str(A.RECOVERY_PROOF): self.proof}
        digests = {**A.OLD_FAILURES, **A.ERRATUM_PINS, **self.sources,
            str(A.OLD_ERRATUM_PLAN): A.OLD_ERRATUM_PLAN_SHA, str(A.RECOVERY_PROOF): self.proof_sha,
            str(A.ERRATUM_PLAN): self.plan_sha}
        self.a = SyntheticAuditor(self.objects, digests)
        source_map = self.ep['metadata_recovery']['source_sha256']
        fields = {'plan_sha256': self.plan_sha, 'helper_sha256': source_map[str(A.METADATA_HELPER)],
            'test_proof_sha256': self.proof_sha,
            'launcher_sha256': source_map[str(A.METADATA_RECOVERY / 'root_erratum_launch003.py')],
            'automatic_retry': False, 'native_handle_retained_until_wait': True,
            'pid': 12345, 'creation_filetime': 134360000000000000, 'image': str(A.METADATA_PYTHON)}
        argv = [str(A.METADATA_PYTHON), '-I', '-S', '-B', str(A.METADATA_HELPER), 'execute', '--plan', str(A.ERRATUM_PLAN),
            '--plan-sha256', self.plan_sha]
        self.start_sha = 'c' * 64
        self.start = {**fields, 'schema': 'paper3-root-erratum-recovery-process-start-v1', 'producer': 'ROOT_OWNING_POPEN',
            'cmdargv': argv, 'command_line': subprocess.list2cmdline(argv)}
        self.exit = {**fields, 'schema': 'paper3-root-erratum-recovery-process-exit-v1', 'producer': 'OWN_ROOT_POPEN_WAIT',
            'actual_exit_code': 0, 'native_exit_code': 0, 'identity_unchanged': True, 'start_receipt_sha256': self.start_sha}

    def verify_plan(self):
        with patch.object(A, 'read', side_effect=lambda path: copy.deepcopy(self.objects[str(Path(path))])):
            return A.check_recovery_plan(self.a, self.ep, self.plan_sha)

    def verify_exit(self):
        return A.check_recovery_exit_contract(self.start, self.exit, self.start_sha, self.ep, self.plan_sha)

    def test_verified_scientific_functions_and_prefix_are_unchanged(self):
        result = A.check_scientific_auditor_preservation(A.Auditor())
        self.assertTrue(result['full_scientific_prefix_byte_identical'])

    def test_legitimate_recovery_plan_accepts_old_actual_one(self):
        self.assertEqual(self.verify_plan(), self.ep['metadata_recovery'])

    def test_missing_source_pin_rejected(self):
        self.ep['metadata_recovery']['source_sha256'].pop(str(A.METADATA_HELPER))
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_added_source_pin_rejected(self):
        self.ep['metadata_recovery']['source_sha256'][str(A.METADATA_RECOVERY / 'unexpected.py')] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_changed_original_plan_scientific_digest_rejected(self):
        self.ep['manifest_digest'] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_changed_original_plan_target_rejected(self):
        self.ep['target_relative'] = 'handoffs/another'
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_extra_original_plan_field_rejected(self):
        self.ep['new_scientific_exemption'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_changed_record_to_failed_attempt_rejected(self):
        self.ep['record_root'] = self.original['record_root']
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_proof_source_pin_mismatch_rejected(self):
        self.proof['source_sha256'][str(A.METADATA_HELPER)] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_proof_incomplete_tests_rejected(self):
        self.proof['tests_run'] = 11
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_proof_boolean_test_count_rejected(self):
        self.proof['tests_run'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_failed_proof_rejected(self):
        self.proof['failures'] = 1
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_statistics_restart_scope_rejected(self):
        self.ep['metadata_recovery']['models_or_statistics_restarted'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_stop_consumption_claim_rejected(self):
        self.ep['metadata_recovery']['DW0001_STOP_consumption_claimed'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_original_failed_exit_fabricated_zero_rejected(self):
        self.objects[str(A.CONTROL / 'ERRATUM_PROCESS_EXIT.json')]['actual_exit_code'] = 0
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_original_failed_exit_boolean_rejected(self):
        self.objects[str(A.CONTROL / 'ERRATUM_PROCESS_EXIT.json')]['actual_exit_code'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_old_failed_finish_fabrication_rejected(self):
        real_exists = Path.exists
        bad = A.CONTROL / 'finish.json'
        with patch.object(Path, 'exists', lambda path: True if path == bad else real_exists(path)):
            with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_real_smoke_fixed_sha_mismatch_rejected(self):
        self.ep['metadata_recovery']['real_smoke_files_sha256']['journal/000004.json'] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_boundary_transform_widening_rejected(self):
        self.ep['metadata_recovery']['boundary_transform']['new_predicate'] = 'True'
        with self.assertRaises(A.AcceptanceError): self.verify_plan()

    def test_legitimate_native_owning_exit_zero(self):
        self.assertEqual(self.verify_exit()['actual_exit_code'], 0)

    def test_native_failure_rejected(self):
        self.exit['native_exit_code'] = 1
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_owning_failure_rejected(self):
        self.exit['actual_exit_code'] = 1
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_boolean_zero_rejected(self):
        self.exit['actual_exit_code'] = False
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_wrong_pid_rejected(self):
        self.exit['pid'] += 1
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_boolean_pid_rejected(self):
        self.start['pid'] = self.exit['pid'] = True
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_changed_creation_filetime_rejected(self):
        self.exit['creation_filetime'] += 1
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_missing_retained_handle_rejected(self):
        self.exit['native_handle_retained_until_wait'] = False
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_wrong_native_image_rejected(self):
        self.exit['image'] = str(A.METADATA_PYTHON.with_name('another.exe'))
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_wrong_native_command_rejected(self):
        self.start['command_line'] += ' --unapproved'
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_changed_argv_rejected(self):
        self.start['cmdargv'][5] = 'create-plan'
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_wrong_exit_producer_rejected(self):
        self.exit['producer'] = 'INFERRED_FROM_FINISH'
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_start_receipt_sha_mismatch_rejected(self):
        self.exit['start_receipt_sha256'] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_helper_source_sha_mismatch_rejected(self):
        self.exit['helper_sha256'] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_exit()

    def test_plan_sha_mismatch_rejected(self):
        self.exit['plan_sha256'] = 'a' * 64
        with self.assertRaises(A.AcceptanceError): self.verify_exit()


def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('requires -I -S -B')
    output = HERE / 'FINAL_ACCEPTANCE_METADATA_SYNTHETIC_TEST_RESULTS_003.json'
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MetadataContracts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = hashlib.sha256(SOURCE.read_bytes()).hexdigest() == AUDITOR_SHA
    proof = {'schema': 'paper3-independent-final-acceptance-metadata-test-proof-v1',
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'all_pass': result.wasSuccessful() and unchanged,
        'source_sha256': {str(SOURCE): AUDITOR_SHA,
            str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'auditor_source_unchanged_during_tests': unchanged, 'original_scientific_functions_byte_identical': True,
        'full_scientific_scan_performed': False, 'actual_models_statistics_or_publication_executed': False,
        'scope': 'Synthetic metadata plan, source/proof and owning/native exit contracts; verified frozen source preservation only.'}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps({'proof_path': str(output), 'proof_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'all_pass': proof['all_pass'], 'tests_run': result.testsRun}), flush=True)
    return 0 if proof['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
