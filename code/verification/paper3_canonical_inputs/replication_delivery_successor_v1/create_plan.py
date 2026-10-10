"""Write once the exact metadata-successor launch plan; never launch anything."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('metadata_successor_plan', ROOT / 'successor.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
ADAPTER_PROOF = 'SYNTHETIC_TEST_RESULTS_ATTEMPT004.json'
ADAPTER_PROOF_SHA = 'c2129c565cde21c0237938b79e6e6a9e576cbad2b6c4d4c76c68ea817864d5f4'


def main():
    s.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'requires -I -S -B')
    s.require(ROOT == s.safe(s.REPO, s.SELF_REL) and Path(sys.executable) == s.PYTHON,
              'wrong authorized plan runtime/source')
    s.verify_own_proof(ROOT)
    relatives = [s.SELF_REL + '/' + name for name in (*s.OWN_NAMES, s.PROOF_NAME)]
    relatives += [s.RECOVERY_REL + '/' + name for name in
                  ('finalizer.py', 'continuation.py', 'durable_supervisor.py', 'sequenced_supervisor_002.py',
                   'SYNTHETIC_CONTINUATION_TEST_RESULTS_ATTEMPT001.json')]
    relatives += [s.ORIGINAL_DELIVERY_REL + '/' + name for name in
                  ('delivery.py', 'SYNTHETIC_TEST_RESULTS_ATTEMPT003.json')]
    relatives += [s.DURABLE_REL + '/start.json', s.DURABLE_REL + '/continuation_launched.json',
                  s.DURABLE_REL + '/finalizer_launched.json', s.GATE_REL]
    relatives += [s.COMPAT_REL + '/' + name for name in s.COMPAT_NAMES]
    relatives += [s.GATE_DIR_REL + '/' + name for name in s.ENTRY_NAMES]
    s.bound(s.safe(s.REPO, s.COMPAT_REL + '/strict_legacy_proof_adapter.py'), s.STRICT_ADAPTER_SHA)
    s.bound(s.safe(s.REPO, s.COMPAT_REL + '/' + s.STRICT_PROOF_NAME), s.STRICT_PROOF_SHA)
    wrapper_proof = s.load(s.safe(s.REPO, s.COMPAT_REL + '/WRAPPER_TEST_RESULTS_001.json'))
    s.require(wrapper_proof.get('all_pass') is True and wrapper_proof.get('exit_code') == 0 and
              wrapper_proof.get('tests_run', 0) >= 10 and
              all(wrapper_proof.get(name) == 0 for name in ('failures', 'errors', 'skipped')) and
              wrapper_proof.get('models_generators_or_statistics_executed') is False and
              wrapper_proof.get('real_processes_launched') is False,
              'compatibility wrapper synthetic proof is not complete')
    for name, digest in wrapper_proof['implementation_sha256'].items():
        s.bound(s.safe(s.REPO, s.COMPAT_REL + '/' + name), digest)
    adapter_root = s.safe(s.REPO, s.ADAPTER_REL)
    proof_path = s.bound(adapter_root / ADAPTER_PROOF, ADAPTER_PROOF_SHA)
    adapter_proof = s.load(proof_path)
    s.require(adapter_proof.get('all_pass') is True and adapter_proof.get('exit_code') == 0 and
              all(adapter_proof.get(name) is False for name in
                  ('real_phase_receipts_read_by_tests', 'real_outcomes_read',
                   'models_generators_or_statistics_executed', 'real_delivery_published', 'running_finalizer_modified')),
              'adapter synthetic proof scope differs')
    source_hashes = adapter_proof.get('implementation_sha256', {})
    s.require(set(source_hashes) == {'observer_adapter.py', 'test_observer_adapter.py', 'run_synthetic_tests.py'},
              'adapter reviewed source closure differs')
    for name, digest in source_hashes.items():
        s.bound(adapter_root / name, digest)
        relatives.append(s.ADAPTER_REL + '/' + name)
    relatives += [s.ADAPTER_REL + '/' + ADAPTER_PROOF, s.ADAPTER_REL + '/OBSERVER_METADATA_ADAPTER_REVIEW.md']
    pins = {str(s.safe(s.REPO, relative)): s.sha(s.safe(s.REPO, relative)) for relative in relatives}
    pins[str(s.PYTHON)] = s.sha(s.PYTHON)
    s.require(pins[str(s.safe(s.REPO, s.RECOVERY_REL + '/finalizer.py'))] == s.FINALIZER_SHA and
              pins[str(s.safe(s.REPO, s.ORIGINAL_DELIVERY_REL + '/delivery.py'))] == s.DELIVERY_SHA and
             pins[str(s.safe(s.REPO, s.GATE_REL))] == s.GATE_SHA, 'original authority SHA differs')
    s.require(s.sha(s.safe(s.REPO, 'PAPER3_FINAL_REPLICATION_HANDOFF.md')) == s.ROOT_SHA,
              'original f50 root handoff changed')
    value = {'schema': 'paper3-delivery-successor-plan-v1', 'created_utc': s.utc(),
             'repository': str(s.REPO), 'python_executable': str(s.PYTHON),
             'manifest_digest': s.MANIFEST, 'F1_digest': s.F1,
             'adapter_proof_name': ADAPTER_PROOF, 'files_sha256': pins,
             'scientific_commands_authorized': False, 'automatic_scientific_retry': False,
             'original_finalizer_must_naturally_stop': True,
             'root_publication_authorized_only_after_all_original_gates': True,
             'no_original_source_or_receipt_replacement': True,
             'retained_actual_exit_receipts_required': True,
             'exclusive_successor_record_relative': s.SELF_REL + '/attempt001',
             'exclusive_successor_lock_relative': s.SELF_REL + '/SUCCESSOR_EXCLUSIVE_RUN_LOCK.json'}
    value['adapter_command'] = s.adapter_command(s.REPO, value)
    plan_path = ROOT / s.PLAN_NAME
    s.emit(plan_path, value)
    s.verify_plan(s.REPO, plan_path)
    print(str(plan_path))
    print('plan_sha256=' + s.sha(plan_path))
    print('NO_PROCESS_STARTED; NO_DELIVERY_PUBLISHED; NO_SCIENTIFIC_OUTPUT_READ')


if __name__ == '__main__':
    main()
