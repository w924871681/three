"""Synthetic receipts only; original reader import has no execution side effects."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import observer_adapter as A

spec = importlib.util.spec_from_file_location(
    'frozen_delivery_for_synthetic_guards', ROOT.parent / 'replication_delivery_env_v3/delivery.py')
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
DIGEST = '0' * 64

fixture_spec = importlib.util.spec_from_file_location(
    'frozen_delivery_synthetic_fixtures', ROOT.parent / 'replication_delivery_env_v3/test_delivery.py')
F = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(F)


def original(phase, attempt):
    return {'manifest_digest': DIGEST, 'phase': phase, 'attempt_id': attempt,
            'start': '2026-01-01T00:00:00+00:00',
            'finish': '2026-01-01T01:00:00+00:00',
            'worker_count': 1, 'success': True}


def observer():
    return {'schema': A.EXTERNAL_SCHEMA, 'producer': A.EXTERNAL_PRODUCER,
            'manifest_digest': DIGEST, 'phase': 'full', 'attempt_id': 'A_FULL_0001',
            'external_observer': True, 'status': 'INTERRUPTED',
            'original_driver_terminal_record': False, 'worker_exception_observed': False,
            'termination_actor': A.UNKNOWN, 'exit_code': None, 'child_exit_code': None,
            'started': '2026-01-01T02:00:00+00:00',
            'finished': '2026-01-01T03:00:00+00:00',
            'created_utc': '2026-01-01T03:00:00+00:00',
            'observer_snapshot_sha256': '1' * 64, 'error': 'SYNTHETIC disappearance'}


class AdapterTests(unittest.TestCase):
    def normalize(self, value):
        return A.normalize_receipt(value, ('full', 'A_FULL_0001'),
                                   'SYNTHETIC/failure.json', '2' * 64, D.require)

    def test_observer_end_never_becomes_actual_finish(self):
        value = observer()
        unchanged = copy.deepcopy(value)
        row = self.normalize(value)
        self.assertEqual(value, unchanged)
        self.assertEqual(row['start'], value['started'])
        self.assertEqual(row['finish'], A.UNKNOWN)
        self.assertEqual(row['external_observation_utc'], value['finished'])
        self.assertEqual(row['actual_OS_exit_time'], A.UNKNOWN)
        self.assertEqual(row['exit_code'], A.UNKNOWN)
        self.assertEqual(row['termination_actor'], A.UNKNOWN)
        self.assertIs(row['success'], False)
        self.assertIs(row['worker_exception_observed'], False)
        self.assertIn('observer cutoff', A.REPORT_NOTE)
        self.assertIn('NOT_VERIFIED', A.REPORT_NOTE)

    def test_rejects_false_native_or_success_claims(self):
        for field, replacement in (
                ('producer', 'worker'), ('schema', 'unknown'), ('external_observer', False),
                ('status', 'COMPLETED'), ('success', True),
                ('original_driver_terminal_record', True), ('worker_exception_observed', True),
                ('exit_code', 0), ('child_exit_code', 0), ('termination_actor', 'Codex'),
                ('start', '2026-01-01T02:00:00+00:00'),
                ('finish', '2026-01-01T03:00:00+00:00'),
                ('observer_snapshot_sha256', 'malformed')):
            with self.subTest(field=field):
                value = observer(); value[field] = replacement
                with self.assertRaises(D.DeliveryIntegrityError): self.normalize(value)

    def test_timestamp_guards(self):
        for field, replacement in (
                ('started', 'bad'), ('finished', '2026-01-01T03:00:00'),
                ('created_utc', '2026-01-01T04:00:00+00:00'),
                ('started', '2026-01-01T04:00:00+00:00')):
            with self.subTest(field=field):
                value = observer(); value[field] = replacement
                with self.assertRaises(D.DeliveryIntegrityError): self.normalize(value)

    def write(self, root, phase, attempt, filename, value):
        path = root / 'execution' / phase / attempt / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return str(path), D.digest_file(path)

    def bindings(self, root):
        result = {}
        for phase, attempt in [('initial', 'A_INITIAL_0001'),
                               ('minimal', 'A_MINIMAL_0001'), ('full', 'A_FULL_0002')]:
            name, digest = self.write(root, phase, attempt, 'completion.json', original(phase, attempt))
            result[name] = digest
        name, digest = self.write(root, 'full', 'A_FULL_0001', 'failure.json', observer())
        result[name] = digest
        return result

    def test_original_bug_reproduced_and_proposed_adapter_accepts(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            root = Path(temp)
            bindings = self.bindings(root)
            before = {name: Path(name).read_bytes() for name in bindings}
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'phase real timestamps absent'):
                D.read_phase_history(root, bindings, DIGEST)
            rows = A.read_phase_history(D, root, bindings, DIGEST)
            self.assertEqual(len(rows), 4)
            interrupted = next(row for row in rows if row['attempt'] == 'A_FULL_0001')
            self.assertEqual(interrupted['finish'], A.UNKNOWN)
            self.assertEqual({row['phase'] for row in rows if row['success']},
                             {'initial', 'minimal', 'full'})
            self.assertEqual(before, {name: Path(name).read_bytes() for name in bindings})
            # Existing renderer may render these columns; no fabricated actual finish.
            rendered = D.markdown_table(rows)
            self.assertIn('external_observation_utc', rendered)
            self.assertIn('actual phase end NOT_VERIFIED', rendered)

    def test_observer_cannot_replace_successful_full_receipt(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            root = Path(temp); bindings = self.bindings(root)
            bindings = {name: digest for name, digest in bindings.items() if 'A_FULL_0002' not in name}
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'successful phase completion receipt absent'):
                A.read_phase_history(D, root, bindings, DIGEST)

    def test_byte_binding_and_manifest_identity_still_required(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            root = Path(temp); bindings = self.bindings(root)
            name = next(name for name in bindings if 'A_FULL_0001' in name)
            Path(name).write_text(json.dumps({**observer(), 'manifest_digest': '3' * 64}), encoding='utf-8')
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'SHA mismatch'):
                A.read_phase_history(D, root, bindings, DIGEST)
            bindings[name] = D.digest_file(name)
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'phase provenance differs'):
                A.read_phase_history(D, root, bindings, DIGEST)

    def test_external_record_cannot_be_completion_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            root = Path(temp); bindings = self.bindings(root)
            name, digest = self.write(root, 'full', 'A_FULL_0003', 'completion.json',
                                      {**observer(), 'attempt_id': 'A_FULL_0003'})
            bindings[name] = digest
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'not a completion receipt'):
                A.read_phase_history(D, root, bindings, DIGEST)

    def test_original_timestamps_retained(self):
        value = original('full', 'A_FULL_0001')
        row = self.normalize(value)
        self.assertEqual(row['start'], value['start'])
        self.assertEqual(row['finish'], value['finish'])
        self.assertEqual(row['external_observation_utc'], 'NOT_APPLICABLE')
        self.assertEqual(row['actual_OS_exit_time'], A.UNKNOWN)

    def test_load_frozen_source_requires_exact_sha(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            repo = Path(temp); source = repo / A.DELIVERY_REL
            source.parent.mkdir(parents=True)
            original_source = ROOT.parent / 'replication_delivery_env_v3/delivery.py'
            source.write_bytes(original_source.read_bytes())
            self.assertEqual(A.digest_file(source), A.TRUSTED_DELIVERY_SHA256)
            module = A.load_frozen_delivery(repo)
            self.assertEqual(module.F1_DIGEST, D.F1_DIGEST)
            source.write_bytes(source.read_bytes() + b'\n# synthetic tamper\n')
            with self.assertRaisesRegex(RuntimeError, 'trusted original delivery SHA differs'):
                A.load_frozen_delivery(repo)

    def make_stop(self, repo):
        root = repo / A.FINALIZER_REL; record = root / 'attempt001'
        record.mkdir(parents=True)
        finalizer = root / 'finalizer.py'
        finalizer.write_bytes((ROOT.parent / 'replication_abrupt_recovery_v1/finalizer.py').read_bytes())
        stop = record / 'stopped.json'
        stop.write_text(json.dumps({'status': 'STOPPED_FOR_DIAGNOSIS',
            'phase': 'reviewed_saved_result_delivery',
            'message': 'saved-result delivery failed; outputs preserved'}), encoding='utf-8')
        (record / 'DELIVERY_PROCESS_FINISH.json').write_text(json.dumps({'exit_code': 1}), encoding='utf-8')
        (record / 'delivery_stderr.log').write_text('DeliveryIntegrityError: phase real timestamps absent\n', encoding='utf-8')
        evidence = record / 'SYNTHETIC_GATE_BINDING.json'; evidence.write_text('{}', encoding='utf-8')
        (record / 'ACTUAL_GATE_VERIFICATION.json').write_text(json.dumps({
            'status': 'PASS', 'evidence_sha256': {str(evidence): D.digest_file(evidence)}}), encoding='utf-8')
        (record / 'source_pins.json').write_text(json.dumps({
            str(repo / A.DELIVERY_REL): A.TRUSTED_DELIVERY_SHA256,
            str(finalizer): A.TRUSTED_FINALIZER_SHA256}), encoding='utf-8')
        return stop

    def test_natural_stop_and_actual_gate_binding_required(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            repo = Path(temp); stop = self.make_stop(repo)
            bindings = A.verify_natural_stop(D, repo, stop)
            self.assertEqual(len(bindings), 5)
            gate_binding = stop.parent / 'SYNTHETIC_GATE_BINDING.json'
            gate_binding.write_text('{"tampered": true}', encoding='utf-8')
            with self.assertRaisesRegex(D.DeliveryIntegrityError, 'SHA mismatch'):
                A.verify_natural_stop(D, repo, stop)

    def test_success_or_other_failure_cannot_trigger_adapter(self):
        for kind in ('success', 'other_error', 'no_stop'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
                repo = Path(temp); stop = self.make_stop(repo)
                if kind == 'success':
                    (stop.parent / 'DELIVERY_PROCESS_FINISH.json').write_text('{"exit_code": 0}', encoding='utf-8')
                elif kind == 'other_error':
                    (stop.parent / 'delivery_stderr.log').write_text('other error', encoding='utf-8')
                else:
                    stop.write_text('{"status": "COMPLETED"}', encoding='utf-8')
                with self.assertRaises(D.DeliveryIntegrityError): A.verify_natural_stop(D, repo, stop)

    def test_own_source_proof_prevents_post_test_change(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            root = Path(temp); (root / 'synthetic_source.py').write_text('# synthetic', encoding='utf-8')
            before = {str(root.parent / 'replication_delivery_env_v3/delivery.py'): A.TRUSTED_DELIVERY_SHA256,
                      str(root.parent / 'replication_abrupt_recovery_v1/finalizer.py'): A.TRUSTED_FINALIZER_SHA256}
            proof = {key: True for key in ('all_pass', 'original_guard_sources_unchanged')}
            proof.update({key: False for key in ('real_phase_receipts_read_by_tests', 'real_outcomes_read',
                'models_generators_or_statistics_executed', 'real_delivery_published', 'running_finalizer_modified')})
            proof.update({'exit_code': 0, 'implementation_sha256': {'synthetic_source.py': A.digest_file(root / 'synthetic_source.py')},
                          'original_guard_source_sha256_before': before, 'original_guard_source_sha256_after': before})
            proof_path = root / 'proof.json'; proof_path.write_text(json.dumps(proof), encoding='utf-8')
            with mock.patch.object(A, 'ROOT', root):
                self.assertEqual(A.verify_own_proof(D, proof_path), proof)
                (root / 'synthetic_source.py').write_text('# synthetic tamper', encoding='utf-8')
                with self.assertRaisesRegex(D.DeliveryIntegrityError, 'implementation changed'):
                    A.verify_own_proof(D, proof_path)

    def test_private_adapter_publication_has_source_proof_and_truthful_report(self):
        # Full publisher exercised against a temporary, explicitly synthetic bundle.
        # The scientific gate is tested by the unchanged original suite; this
        # fixture isolates the new metadata path and final package inventory.
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='synthetic_') as temp:
            repo = Path(temp); results = repo / D.RESULT_RELATIVE
            statistics_root = results / D.STATS_RELATIVE
            statistics_root.mkdir(parents=True)
            binding_files = self.bindings(results)
            original_source = repo / A.DELIVERY_REL
            original_source.parent.mkdir(parents=True)
            original_source.write_bytes((ROOT.parent / 'replication_delivery_env_v3/delivery.py').read_bytes())
            api = A.load_frozen_delivery(repo)
            metadata = {'schema': 'SYNTHETIC_ADAPTER_METADATA', 'source': 'SYNTHETIC'}
            source_payloads = {'source/delivery_observer_adapter/SYNTHETIC_SOURCE.py': '# synthetic adapter source\n',
                               'source/delivery_observer_adapter/SYNTHETIC_PROOF.json': '{"synthetic":true}\n'}
            A.configure_private_delivery(api, source_payloads, metadata)
            manifest, *_ = F.objects()
            synthetic_source = repo / 'synthetic_source.py'
            synthetic_source.write_text('# synthetic frozen source\n', encoding='utf-8')
            manifest.update({'candidate_id': 'SYNTHETIC', 'input_protocol': 'SYNTHETIC',
                'input_definition_digest': DIGEST, 'input_dependency_digest': DIGEST,
                'stage_b_bindings': {}, 'input_files_sha256': {}, 'environment_binding': {},
                'environment': {}, 'critical_files_sha256': {'synthetic_source.py': D.digest_file(synthetic_source)},
                'original_protected_snapshot': {'synthetic_source.py': D.digest_file(synthetic_source)},
                'paths': {'executor_root': str(repo / 'SYNTHETIC_EXECUTOR')}, 'executor_sha256': {}})
            core = [results / name for name in ('provenance_manifest.json', 'full_experiment_integrity_gate.json',
                                               'initial_state_manifest.json')]
            core += [statistics_root / name for name in ('statistics_manifest.json', 'statistics_execution_receipt.json')]
            for path in core: path.write_text('{}', encoding='utf-8')
            bundle = {'repo': repo, 'results': results, 'statistics_root': statistics_root,
                'manifest': manifest, 'tables': F.tables(),
                'phases': api.read_phase_history(results, binding_files, DIGEST),
                'failed_attempts': {name: sha for name, sha in binding_files.items() if 'A_FULL_0001' in name},
                'outputs': {}, 'statistics': {'outputs_sha256': {}, 'implementation_files_sha256': {}},
                'read_proofs_sha256': {str(path): D.digest_file(path) for path in core},
                'binding_files': binding_files,
                'raw_index': [{'path': 'SYNTHETIC_RAW', 'sha256': DIGEST, 'copied': False}]}
            api.audit_saved_evidence = lambda *args: bundle
            delivery = api.publish_delivery(repo, DIGEST, 'handoffs/SYNTHETIC_PACKAGE')
            package = Path(delivery['package_root'])
            self.assertEqual(delivery['status'], 'COMPLETED')
            for name, text in source_payloads.items():
                self.assertEqual((package / name).read_text(encoding='utf-8'), text)
                self.assertEqual(delivery['package_files_sha256'][name], D.digest_file(package / name))
            self.assertIn('source/delivery_observer_adapter/ADAPTER_METADATA.json', delivery['package_files_sha256'])
            report = (package / 'EXECUTION_SUMMARY.md').read_text(encoding='utf-8')
            self.assertIn('actual phase end NOT_VERIFIED', report)
            self.assertIn(A.REPORT_NOTE, report)
            self.assertNotIn('## Recorded actual phase attempts', report)
            copied_receipt = package / 'phase_evidence/execution/full/A_FULL_0001/failure.json'
            source_receipt = results / 'execution/full/A_FULL_0001/failure.json'
            self.assertEqual(copied_receipt.read_bytes(), source_receipt.read_bytes())
            saved_numbers = (package / 'CORRECTED_FINAL_STATISTICS.md').read_text(encoding='utf-8')
            for row in bundle['tables']['final_paired_contrasts.csv']:
                self.assertIn(row['mean_difference'], saved_numbers)
            self.assertFalse(delivery['root_handoff_modified'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
