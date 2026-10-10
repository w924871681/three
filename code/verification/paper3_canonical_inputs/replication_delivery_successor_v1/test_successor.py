"""All fixtures are synthetic. No real experiment/output/process is inspected."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('metadata_successor_under_test', Path(__file__).with_name('successor.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SuccessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='paper3_successor_synthetic_')
        self.repo = Path(self.temp.name)
        self.old = s.safe(self.repo, s.OLD_RECORD_REL)
        self.durable = s.safe(self.repo, s.DURABLE_REL)
        self.record = s.safe(self.repo, s.SELF_REL + '/attempt001')
        self.record.mkdir(parents=True)
        pins = {str(s.safe(self.repo, s.RECOVERY_REL + '/finalizer.py')): s.FINALIZER_SHA,
                str(s.safe(self.repo, s.ORIGINAL_DELIVERY_REL + '/delivery.py')): s.DELIVERY_SHA}
        commands = {kind: ['synthetic', '-I', '-S', '-B',
                          str(s.safe(self.repo, s.COMPAT_REL + '/compat_' + kind + '.py')), '--repo', str(self.repo)]
                    for kind in ('continuation', 'finalizer')}
        self.write(self.durable / 'start.json', {'commands': commands})
        self.write(self.durable / 'continuation_launched.json', {'pid': 1001, 'command': commands['continuation']})
        self.write(self.durable / 'finalizer_launched.json', {'pid': 1002, 'command': commands['finalizer']})
        self.write(self.durable / 'continuation_exit.json', {'pid': 1001, 'actual_exit_code': 0, 'automatic_retry': False})
        self.write(self.durable / 'finalizer_exit.json', {'pid': 1002, 'actual_exit_code': 1, 'automatic_retry': False})
        self.write(self.durable / 'failure.json', {'status': 'CHILD_COMMAND_FAILURE',
                   'actual_child_exit_codes': {'continuation': 0, 'finalizer': 1},
                   'scientific_integrity_pass_claimed': False, 'automatic_retry': False, 'outputs_preserved': True})
        self.write(self.old / 'source_pins.json', pins)
        self.write(self.old / 'start.json', {'pid': 1002, 'previous_root_handoff_sha256': s.ROOT_SHA,
                   'expected_manifest_digest': s.MANIFEST, 'expected_F1_digest': s.F1,
                   'source_pins_digest': s.canonical(pins), 'science_or_statistics_executed': False})
        self.write(self.old / 'stopped.json', {'status': 'STOPPED_FOR_DIAGNOSIS',
                   'phase': 'reviewed_saved_result_delivery', 'exception_type': 'FinalizerError',
                   'message': s.EXPECTED_STOP_MESSAGE, 'scientific_pass_claimed': False,
                   'all_partial_outputs_preserved': True})
        self.write(self.old / 'DELIVERY_PROCESS_FINISH.json', {'exit_code': 1})
        self.write(self.old / 'ACTUAL_GATE_VERIFICATION.json', {'status': 'PASS', 'evidence_sha256': {'synthetic': 'a'*64}})
        self.old.joinpath('delivery_stderr.log').write_text('Traceback (synthetic)\n' + s.EXPECTED_DELIVERY_ERROR + '\n', encoding='utf-8')
        self.old.joinpath('delivery_stdout.log').write_text('', encoding='utf-8')
        for kind, pid in (('continuation', 1001), ('finalizer', 1002)):
            wrapper = s.safe(self.repo, s.COMPAT_REL + '/compat_' + kind + '.py')
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            wrapper.write_text('synthetic wrapper only', encoding='utf-8')
            self.write(s.safe(self.repo, s.GATE_DIR_REL + '/ACTUAL_' + kind.upper() + '_ADAPTER_ENTRY_001.json'),
                {'schema': 'paper3-actual-compatibility-entrypoint-v1', 'pid': pid,
                 'entrypoint': str(wrapper), 'entrypoint_sha256': s.sha(wrapper),
                 'actual_argv': commands[kind][4:], 'cold_gate_sha256': s.GATE_SHA,
                 'original_module': str(s.safe(self.repo, s.RECOVERY_REL + '/' + kind + '.py')),
                 'original_module_sha256': s.CONTINUATION_SHA if kind == 'continuation' else s.FINALIZER_SHA,
                 'about_to_invoke_original_helper_main': True, 'original_main_called_directly_by_OS': False,
                 'scientific_algorithm_or_input_changed': False, 'model_workers_started_claimed': False,
                 'all_bound_SHA_checks_and_resource_gate_preserved': True,
                 'metadata_reader_compatibility': {
                     'schema': 'paper3-strict-legacy-proof-adapter-installation-v1', 'metadata_only': True,
                     'original_finalizer_sha256': s.FINALIZER_SHA, 'adapter_sha256': s.STRICT_ADAPTER_SHA,
                     'compatibility_proof_sha256': s.STRICT_PROOF_SHA,
                     'legacy_original_receipt_sha256': s.LEGACY_PROOF_SHA,
                     'original_verify_function_sha256': s.ORIGINAL_VERIFY_FUNCTION_SHA,
                     'copied_verify_function_sha256': s.COPIED_VERIFY_FUNCTION_SHA,
                     'compatibility_proof_path': str(s.safe(self.repo, s.COMPAT_REL + '/' + s.STRICT_PROOF_NAME)),
                     'gate_path': str(s.safe(self.repo, s.GATE_REL)),
                     'original_module_file_unchanged': True, 'full_pin_hash_checks_retained': True}})
        self.plan = {'adapter_proof_name': 'SYNTHETIC_TEST_RESULTS_ATTEMPT004.json', 'files_sha256': {}}
        self.write(s.safe(self.repo, s.SELF_REL + '/' + s.PLAN_NAME), self.plan)
        self.plan['_verified_plan_sha256'] = s.sha(s.safe(self.repo, s.SELF_REL + '/' + s.PLAN_NAME))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def mutate(self, path, **values):
        value = s.load(path)
        value.update(values)
        self.write(path, value)

    def ready(self):
        return s.predecessor_ready(self.repo, inactive=lambda _: True)

    def rejects(self):
        with self.assertRaises(s.SuccessorError):
            self.ready()

    def test_valid_terminal_metadata_is_ready(self):
        self.assertTrue(self.ready())

    def test_no_stop_waits(self):
        (self.old / 'stopped.json').unlink()
        self.assertFalse(self.ready())

    def test_missing_actual_exit_waits(self):
        (self.durable / 'finalizer_exit.json').unlink()
        self.assertFalse(self.ready())

    def test_live_numeric_pid_blocks(self):
        self.assertFalse(s.predecessor_ready(self.repo, inactive=lambda _: False))

    def test_supervisor_error_rejects(self):
        self.write(self.durable / 'supervisor_error.json', {})
        self.rejects()

    def test_continuation_stop_rejects(self):
        self.write(s.safe(self.repo, s.RECOVERY_REL + '/continuation_001/stopped.json'), {})
        self.rejects()

    def test_original_completion_rejects(self):
        self.write(self.old / 'finish.json', {})
        self.rejects()

    def test_wrong_stop_phase_rejects(self):
        self.mutate(self.old / 'stopped.json', phase='verifying_actual_gates')
        self.rejects()

    def test_wrong_stop_message_rejects(self):
        self.mutate(self.old / 'stopped.json', message='other error')
        self.rejects()

    def test_wrong_stop_exception_rejects(self):
        self.mutate(self.old / 'stopped.json', exception_type='KeyError')
        self.rejects()

    def test_stop_cannot_claim_scientific_success(self):
        self.mutate(self.old / 'stopped.json', scientific_pass_claimed=True)
        self.rejects()

    def test_failed_continuation_rejects(self):
        self.mutate(self.durable / 'continuation_exit.json', actual_exit_code=1)
        self.rejects()

    def test_boolean_exit_rejects(self):
        self.mutate(self.durable / 'continuation_exit.json', actual_exit_code=False)
        self.rejects()

    def test_successful_finalizer_rejects(self):
        self.mutate(self.durable / 'finalizer_exit.json', actual_exit_code=0)
        self.rejects()

    def test_automatic_retry_rejects(self):
        self.mutate(self.durable / 'finalizer_exit.json', automatic_retry=True)
        self.rejects()

    def test_aggregate_exit_mismatch_rejects(self):
        self.mutate(self.durable / 'failure.json', actual_child_exit_codes={'continuation': 0, 'finalizer': 2})
        self.rejects()

    def test_pid_lineage_mismatch_rejects(self):
        self.mutate(self.durable / 'finalizer_launched.json', pid=999)
        self.rejects()

    def test_command_lineage_mismatch_rejects(self):
        self.mutate(self.durable / 'finalizer_launched.json', command=['different'])
        self.rejects()

    def test_root_identity_mismatch_rejects(self):
        self.mutate(self.old / 'start.json', previous_root_handoff_sha256='b'*64)
        self.rejects()

    def test_successful_delivery_rejects(self):
        self.mutate(self.old / 'DELIVERY_PROCESS_FINISH.json', exit_code=0)
        self.rejects()

    def test_unrelated_delivery_error_rejects(self):
        (self.old / 'delivery_stderr.log').write_text('KeyError: start\n', encoding='utf-8')
        self.rejects()

    def test_embedded_expected_error_is_not_sufficient(self):
        (self.old / 'delivery_stderr.log').write_text(s.EXPECTED_DELIVERY_ERROR + '\nOtherError: failure\n', encoding='utf-8')
        self.rejects()

    def test_gate_not_pass_rejects(self):
        self.mutate(self.old / 'ACTUAL_GATE_VERIFICATION.json', status='FAIL')
        self.rejects()

    def test_source_pin_digest_mismatch_rejects(self):
        self.mutate(self.old / 'start.json', source_pins_digest='c'*64)
        self.rejects()

    def test_frozen_source_pin_tamper_rejects(self):
        pins = s.load(self.old / 'source_pins.json')
        pins[str(s.safe(self.repo, s.RECOVERY_REL + '/finalizer.py'))] = 'd'*64
        self.write(self.old / 'source_pins.json', pins)
        self.mutate(self.old / 'start.json', source_pins_digest=s.canonical(pins))
        self.rejects()

    def test_poll_is_bounded(self):
        for value in (0, -1, 61, True):
            with self.assertRaises(s.SuccessorError):
                s.wait_predecessor(self.repo, value)

    def test_wait_never_launches(self):
        values = iter((False, False, True))
        pauses = []
        s.wait_predecessor(self.repo, 30, pause=pauses.append, ready=lambda _: next(values))
        self.assertEqual(pauses, [30, 30])

    def test_duplicate_json_rejected(self):
        target = self.repo / 'duplicate.json'
        target.write_text('{"a":1,"a":2}', encoding='utf-8')
        with self.assertRaises(s.SuccessorError):
            s.load(target)

    def test_nonfinite_json_rejected(self):
        target = self.repo / 'nonfinite.json'
        target.write_text('{"a":NaN}', encoding='utf-8')
        with self.assertRaises(s.SuccessorError):
            s.load(target)

    def test_path_escape_rejected(self):
        with self.assertRaises(s.SuccessorError):
            s.safe(self.repo, '../outside')

    def test_missing_reviewed_finalizer_rejected_before_import(self):
        with self.assertRaises(s.SuccessorError):
            s.load_original(self.repo)

    def test_metadata_read_rejects_reparse_before_read(self):
        with patch.object(s.Path, 'is_symlink', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.load(self.old / 'start.json')

    def test_hash_rejects_reparse_before_read(self):
        with patch.object(s.Path, 'is_symlink', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.sha(self.old / 'start.json')

    def test_actual_entrypoint_wrong_argv_rejected(self):
        self.mutate(s.safe(self.repo, s.GATE_DIR_REL + '/' + s.ENTRY_NAMES[0]), actual_argv=['wrong.py'])
        self.rejects()

    def test_actual_entrypoint_worker_claim_rejected(self):
        self.mutate(s.safe(self.repo, s.GATE_DIR_REL + '/' + s.ENTRY_NAMES[0]), model_workers_started_claimed=True)
        self.rejects()

    def test_actual_entrypoint_wrong_gate_rejected(self):
        self.mutate(s.safe(self.repo, s.GATE_DIR_REL + '/' + s.ENTRY_NAMES[1]), cold_gate_sha256='wrong')
        self.rejects()

    def test_actual_entrypoint_wrong_legacy_adapter_rejected(self):
        path = s.safe(self.repo, s.GATE_DIR_REL + '/' + s.ENTRY_NAMES[1])
        entry = s.load(path)
        entry['metadata_reader_compatibility']['adapter_sha256'] = '0'*64
        self.write(path, entry)
        self.rejects()

    def test_exclusive_records_cannot_overwrite(self):
        target = self.repo / 'exclusive.json'
        s.emit(target, {'value': 1})
        with self.assertRaises(FileExistsError):
            s.emit(target, {'value': 2})
        self.assertEqual(s.load(target), {'value': 1})

    def test_exact_adapter_only_command(self):
        command = s.adapter_command(self.repo, self.plan)
        self.assertEqual(command[:4], [str(s.PYTHON), '-I', '-S', '-B'])
        self.assertEqual(command[4], str(s.safe(self.repo, s.ADAPTER_REL + '/observer_adapter.py')))
        self.assertEqual(command[-2:], ['--original-finalizer-stop', str(self.old / 'stopped.json')])
        self.assertNotIn('--phase', command)

    def fake_finalizer(self, calls, evidence=None):
        def recheck(value):
            calls.append('recheck')
        def completed(*_):
            calls.append('verify_completed')
            return dict({'synthetic': 'a'*64} if evidence is None else evidence)
        def delivered(*_):
            calls.append('verify_delivery')
            return {'synthetic_delivery': True}
        def packaged(*args):
            calls.append('package_final')
            self.assertEqual(args[1], self.record)
            self.assertEqual(args[4], s.ROOT_SHA)
            self.assertIn(str(self.old / 'stopped.json'), args[2])
            return {'synthetic_final_package': True}
        return SimpleNamespace(ROOT_NAME='PAPER3_FINAL_REPLICATION_HANDOFF.md', HELPER_PROOF='proof.json',
                 recheck=recheck, verify_test_proof=lambda *_: calls.append('verify_test_proof'),
                 verify_completed=completed, sha=lambda _: s.ROOT_SHA, emit=s.emit,
                 verify_delivery=delivered, package_final=packaged)

    def test_complete_path_calls_original_gates_delivery_and_publication(self):
        calls = []
        f = self.fake_finalizer(calls)
        def child(command, **kwargs):
            calls.append('adapter')
            self.assertEqual(command, s.adapter_command(self.repo, self.plan))
            self.assertEqual(kwargs['cwd'], self.repo)
            return 0
        with patch.object(s, 'predecessor_ready', return_value=True):
            result = s.execute(self.repo, self.record, self.plan, f, call=child)
        self.assertTrue(result['synthetic_final_package'])
        self.assertLess(calls.index('verify_completed'), calls.index('adapter'))
        self.assertLess(calls.index('adapter'), calls.index('verify_delivery'))
        self.assertLess(calls.index('verify_delivery'), calls.index('package_final'))
        self.assertEqual(calls.count('adapter'), 1)

    def test_changed_gate_evidence_blocks_child_and_publication(self):
        calls = []
        with patch.object(s, 'predecessor_ready', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.execute(self.repo, self.record, self.plan, self.fake_finalizer(calls, {'other': 'a'*64}),
                          call=lambda *_a, **_k: self.fail('child must not run'))
        self.assertNotIn('package_final', calls)

    def test_adapter_failure_has_no_retry_or_publication(self):
        calls, children = [], []
        def child(*_args, **_kwargs):
            children.append(1)
            return 7
        with patch.object(s, 'predecessor_ready', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.execute(self.repo, self.record, self.plan, self.fake_finalizer(calls), call=child)
        self.assertEqual(children, [1])
        self.assertNotIn('verify_delivery', calls)
        self.assertNotIn('package_final', calls)

    def test_existing_delivery_output_blocks_no_overwrite(self):
        s.safe(self.repo, s.PACKAGE_REL).mkdir(parents=True)
        with patch.object(s, 'predecessor_ready', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.execute(self.repo, self.record, self.plan, self.fake_finalizer([]),
                          call=lambda *_a, **_k: self.fail('child must not run'))

    def test_launch_plan_changed_while_waiting_blocks_execution(self):
        self.write(s.safe(self.repo, s.SELF_REL + '/' + s.PLAN_NAME), {'tampered': True})
        with patch.object(s, 'predecessor_ready', return_value=True):
            with self.assertRaises(s.SuccessorError):
                s.execute(self.repo, self.record, self.plan, self.fake_finalizer([]),
                          call=lambda *_a, **_k: self.fail('child must not run'))

    def test_predecessor_must_remain_terminal_at_execution(self):
        with patch.object(s, 'predecessor_ready', return_value=False):
            with self.assertRaises(s.SuccessorError):
                s.execute(self.repo, self.record, self.plan, self.fake_finalizer([]),
                          call=lambda *_a, **_k: self.fail('child must not run'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
