"""Independent metadata-only delivery adapter, never an automatic continuation.

The original delivery API supplies its unchanged path, byte-binding and JSON
guards. This module reads phase receipts only. It does not import scientific
code or calculate elapsed duration from an external observation timestamp.
The CLI may publish only after the unchanged original finalizer has naturally
stopped at the old delivery timestamp bug. It does not publish the root handoff
or create the final archive; a separately certified successor must do those.
"""
from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path

EXTERNAL_SCHEMA = 'paper3-external-cold-observer-phase-failure-v1'
EXTERNAL_PRODUCER = 'external-cold-recovery-observer'
UNKNOWN = 'NOT_VERIFIED'
ROOT = Path(__file__).resolve().parent
DELIVERY_REL = 'verification/paper3_canonical_inputs/replication_delivery_env_v3/delivery.py'
FINALIZER_REL = 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
TRUSTED_DELIVERY_SHA256 = '159bab5bd92d7990cb553989fb83b591dbcb913782f97a833e026ad46b38e453'
TRUSTED_FINALIZER_SHA256 = 'ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652'


def timestamp(value, require, label):
    require(isinstance(value, str) and bool(value), label + ' absent')
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        require(False, label + ' malformed')
    require(parsed.tzinfo is not None, label + ' offset absent')
    return parsed


def normalize_receipt(value, identity, source_path, source_sha256, require):
    """Return a report row without rewriting or augmenting the source receipt.

    `finish` is a legacy report-column name. For an external record it is
    NOT_VERIFIED, never the external observer's `finished` timestamp.
    """
    require(value.get('phase') == identity[0] and value.get('attempt_id') == identity[1],
            'phase attempt receipt identity differs')
    external = (value.get('schema') == EXTERNAL_SCHEMA or
                value.get('producer') == EXTERNAL_PRODUCER or
                value.get('external_observer') is True)
    if external:
        require(value.get('schema') == EXTERNAL_SCHEMA and
                value.get('producer') == EXTERNAL_PRODUCER and
                value.get('external_observer') is True,
                'external observer schema/producer/flag differs')
        require(value.get('status') == 'INTERRUPTED' and value.get('success', False) is False,
                'external observation cannot certify successful completion')
        require(value.get('original_driver_terminal_record') is False and
                value.get('worker_exception_observed') is False,
                'external observation cannot substitute original terminal/exception evidence')
        require('exit_code' in value and value['exit_code'] is None and
                'child_exit_code' in value and value['child_exit_code'] is None and
                value.get('termination_actor') == UNKNOWN,
                'external observation cannot assert exit code or termination actor')
        require('start' not in value and 'finish' not in value,
                'ambiguous external timestamp aliases rejected')
        start = value.get('started')
        observed = value.get('finished')
        start_time = timestamp(start, require, 'external actual start')
        observation_time = timestamp(observed, require, 'external observation')
        timestamp(value.get('created_utc'), require, 'external record creation')
        require(observed == value['created_utc'], 'external observation/creation cutoff differs')
        require(start_time <= observation_time, 'external observation precedes actual start')
        require(re.fullmatch(r'[0-9a-f]{64}', value.get('observer_snapshot_sha256', '')) is not None,
                'external observer snapshot reference malformed')
        finish = UNKNOWN
        record_type = 'EXTERNAL_INTERRUPTION_OBSERVATION'
        finish_meaning = 'actual phase end NOT_VERIFIED'
        actor = UNKNOWN
        exit_code = UNKNOWN
        worker_exception = False
    else:
        start, finish = value.get('start'), value.get('finish')
        start_time = timestamp(start, require, 'original phase start')
        finish_time = timestamp(finish, require, 'original phase finish')
        require(start_time <= finish_time, 'original phase finish precedes start')
        observed = 'NOT_APPLICABLE'
        record_type = 'ORIGINAL_PHASE_TERMINAL_RECORD'
        finish_meaning = 'recorded phase finish; OS exit time not separately established'
        actor = value.get('termination_actor', UNKNOWN)
        exit_code = value.get('exit_code', 'NOT_RECORDED')
        worker_exception = value.get('worker_exception_observed', 'NOT_RECORDED')
    return {
        'phase': value['phase'], 'attempt': value['attempt_id'],
        'start': start, 'finish': finish,
        'record_type': record_type,
        'finish_meaning': finish_meaning,
        'external_observation_utc': observed,
        'actual_OS_exit_time': UNKNOWN,
        'termination_actor': actor, 'exit_code': exit_code,
        'worker_exception_observed': worker_exception,
        'worker_count': value.get('worker_count', 'NOT_RECORDED_FOR_FAILURE'),
        'success': value.get('success', False), 'failure': value.get('error', ''),
        'source_path': str(source_path), 'sha256': source_sha256,
    }


def read_phase_history(delivery_api, root, bindings, digest):
    """Proposed replacement reader with unchanged binding/success/identity gates.

    The caller must be a separately authorized NEW delivery implementation.
    Passing the frozen module here does not modify that module or its files.
    """
    from pathlib import Path

    rows = []
    require = delivery_api.require
    for name, expected in sorted(bindings.items()):
        path = Path(name)
        identity = delivery_api.phase_artifact(root, path)
        if identity and path.name in {'completion.json', 'failure.json'}:
            delivery_api.bound_bytes(path, expected)
            value = delivery_api.load_json(path)
            require(value.get('manifest_digest') == digest, 'phase provenance differs')
            is_external = (value.get('schema') == EXTERNAL_SCHEMA or
                           value.get('producer') == EXTERNAL_PRODUCER or
                           value.get('external_observer') is True)
            require(not is_external or path.name == 'failure.json',
                    'external observation is not a completion receipt')
            require(path.name != 'completion.json' or value.get('success') is True,
                    'phase success flag missing')
            rows.append(normalize_receipt(value, identity, path, expected, require))
    for phase in ('initial', 'minimal', 'full'):
        require(any(row['phase'] == phase and row['success'] is True for row in rows),
                'successful phase completion receipt absent')
    require(len({(row['phase'], row['attempt']) for row in rows}) == len(rows),
            'ambiguous phase terminal proof')
    return rows


REPORT_NOTE = (
    'External interruption rows are later observer evidence, not original worker '
    'exceptions or orderly driver shutdown records. Their start is the saved '
    'actual phase start. Their external_observation_utc is the observer cutoff; '
    'it is not an actual phase end or OS process exit time. Actual end, OS exit '
    'time, termination actor and exit code remain NOT_VERIFIED. No elapsed '
    'execution duration is inferred from that cutoff. Successful original '
    'completion receipts remain separately required for initial, minimal and '
    'full phases. The adapter does not independently verify the snapshot '
    'referenced inside an observer receipt; the recovery gate must bind it.'
)


def digest_file(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_frozen_delivery(repo):
    """Import only the byte-pinned stdlib delivery helper, never project science."""
    import importlib.util
    path = Path(repo).resolve() / DELIVERY_REL
    ensure(path.is_file() and not path.is_symlink(), 'frozen delivery source unavailable')
    ensure(digest_file(path) == TRUSTED_DELIVERY_SHA256, 'trusted original delivery SHA differs')
    spec = importlib.util.spec_from_file_location('observer_adapter_private_delivery', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ensure(digest_file(path) == TRUSTED_DELIVERY_SHA256, 'original delivery changed during import')
    return module


def verify_own_proof(delivery_api, proof_path):
    proof_path = Path(proof_path).resolve()
    delivery_api.require(proof_path.parent == ROOT,
                         'adapter proof must be in its independent implementation root')
    proof = delivery_api.load_json(proof_path)
    expected = {'all_pass': True, 'exit_code': 0,
                'real_phase_receipts_read_by_tests': False, 'real_outcomes_read': False,
                'models_generators_or_statistics_executed': False,
                'real_delivery_published': False, 'running_finalizer_modified': False,
                'original_guard_sources_unchanged': True}
    delivery_api.require(delivery_api.exact_fields(proof, expected),
                         'independent adapter synthetic proof failed or scope differs')
    actual = {path.name: digest_file(path) for path in ROOT.glob('*.py')}
    delivery_api.require(proof.get('implementation_sha256') == actual,
                         'adapter implementation changed after its synthetic proof')
    delivery_api.require(proof.get('original_guard_source_sha256_before') ==
                         proof.get('original_guard_source_sha256_after'),
                         'original helper preservation proof differs')
    delivery_api.require(proof['original_guard_source_sha256_after'].get(
        str(ROOT.parent / 'replication_delivery_env_v3/delivery.py')) == TRUSTED_DELIVERY_SHA256,
        'synthetic proof did not test the trusted original delivery')
    delivery_api.require(proof['original_guard_source_sha256_after'].get(
        str(ROOT.parent / 'replication_abrupt_recovery_v1/finalizer.py')) == TRUSTED_FINALIZER_SHA256,
        'synthetic proof did not bind the trusted original finalizer')
    return proof


def verify_natural_stop(delivery_api, repo, stop_path):
    """Require the actual old finalizer failure; never manufacture or bypass it."""
    repo = Path(repo).resolve()
    root = repo / FINALIZER_REL
    stop_path = Path(stop_path).resolve()
    delivery_api.require(stop_path.name == 'stopped.json' and stop_path.parent.parent == root and
                         re.fullmatch(r'attempt[0-9]{3}', stop_path.parent.name) is not None,
                         'original stop must name its actual independent finalizer attempt')
    stopped = delivery_api.load_json(stop_path)
    delivery_api.require(stopped.get('status') == 'STOPPED_FOR_DIAGNOSIS' and
                         stopped.get('phase') == 'reviewed_saved_result_delivery' and
                         stopped.get('message') == 'saved-result delivery failed; outputs preserved',
                         'original finalizer did not stop at saved-result delivery')
    finish = delivery_api.load_json(stop_path.parent / 'DELIVERY_PROCESS_FINISH.json')
    delivery_api.require(type(finish.get('exit_code')) is int and finish['exit_code'] != 0,
                         'original delivery failure exit code absent')
    delivery_api.require(not (stop_path.parent / 'finish.json').exists(),
                         'original finalizer already completed')
    stderr_path = stop_path.parent / 'delivery_stderr.log'
    error = stderr_path.read_text(encoding='utf-8')
    delivery_api.require('DeliveryIntegrityError: phase real timestamps absent' in error,
                         'original delivery did not fail at the confirmed timestamp interface')
    gate_path = stop_path.parent / 'ACTUAL_GATE_VERIFICATION.json'
    gate = delivery_api.load_json(gate_path)
    delivery_api.require(gate.get('status') == 'PASS' and gate.get('evidence_sha256'),
                         'original actual gate verification absent')
    pins_path = stop_path.parent / 'source_pins.json'
    pins = delivery_api.load_json(pins_path)
    delivery_api.require(pins.get(str(repo / DELIVERY_REL)) == TRUSTED_DELIVERY_SHA256,
                         'stopped finalizer did not pin the trusted original delivery')
    finalizer = root / 'finalizer.py'
    delivery_api.require(pins.get(str(finalizer)) == TRUSTED_FINALIZER_SHA256 and
                         digest_file(finalizer) == TRUSTED_FINALIZER_SHA256,
                         'stopped finalizer source is not the reviewed original')
    # Every actual gate binding remains verified; no result is inferred from STOP.
    for name, expected in gate['evidence_sha256'].items():
        delivery_api.bound_bytes(name, expected)
    return {str(path): digest_file(path) for path in
            (stop_path, stop_path.parent / 'DELIVERY_PROCESS_FINISH.json',
             stderr_path, gate_path, pins_path)}


def configure_private_delivery(delivery_api, source_payloads, adapter_metadata):
    """Adapt only a fresh, private module instance in this separate process.

    Nothing changes the original source bytes or another Python process.
    All scientific/statistics validation and saved-table rendering stay in the
    byte-pinned original helper. The adapter's source/proof/declaration are
    additional manifest-bound package files.
    """
    import json
    original_renderer = delivery_api.render_reports
    delivery_api.read_phase_history = lambda root, bindings, digest: read_phase_history(
        delivery_api, root, bindings, digest)

    def render(bundle):
        reports = original_renderer(bundle)
        for name in ('EXECUTION_SUMMARY.md', 'EXPERIMENT_INTEGRITY_AUDIT.md',
                     'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'):
            reports[name] = reports[name].replace(
                '## Recorded actual phase attempts', '## Recorded phase attempts and external observations')
            reports[name] += '\n## External observer timestamp semantics\n\n' + REPORT_NOTE + '\n'
        reports.update(source_payloads)
        reports['source/delivery_observer_adapter/ADAPTER_METADATA.json'] = (
            json.dumps(adapter_metadata, indent=2, allow_nan=False) + '\n')
        return reports

    delivery_api.render_reports = render
    return delivery_api


def main():
    import argparse
    from datetime import timezone
    import json
    import sys
    ensure(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
           'adapter CLI requires -I -S -B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--expected-manifest-digest', required=True)
    parser.add_argument('--handoff-relative', required=True)
    parser.add_argument('--synthetic-test-receipt', required=True)
    parser.add_argument('--original-finalizer-stop', required=True)
    args = parser.parse_args()
    repo = Path(args.repo)
    ensure(repo.is_absolute() and repo == Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION'),
           'only the explicitly authorized repository is allowed')
    api = load_frozen_delivery(repo)
    proof_path = Path(args.synthetic_test_receipt).resolve()
    proof = verify_own_proof(api, proof_path)
    stop_bindings = verify_natural_stop(api, repo, args.original_finalizer_stop)
    source_hashes = dict(proof['implementation_sha256'])
    payloads = {'source/delivery_observer_adapter/' + name:
                (ROOT / name).read_bytes().decode('utf-8') for name in source_hashes}
    payloads['source/delivery_observer_adapter/' + proof_path.name] = proof_path.read_bytes().decode('utf-8')
    metadata = {'schema': 'paper3-delivery-observer-adapter-metadata-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'trusted_original_delivery_path': str(repo / DELIVERY_REL),
                'trusted_original_delivery_sha256': TRUSTED_DELIVERY_SHA256,
                'adapter_implementation_sha256': source_hashes,
                'adapter_synthetic_proof_sha256': digest_file(proof_path),
                'original_finalizer_natural_stop_evidence_sha256': stop_bindings,
                'in_memory_metadata_reader_and_report_note_adapted_in_new_process': True,
                'original_delivery_file_modified': False, 'original_receipts_modified': False,
                'scientific_or_statistics_algorithms_modified': False,
                'actual_interruption_exit_time_actor_code': UNKNOWN,
                'root_handoff_modified_by_adapter': False,
                'whole_pipeline_or_final_package_completion_claimed': False,
                'timestamp_semantics': REPORT_NOTE}
    configure_private_delivery(api, payloads, metadata)
    delivery = api.publish_delivery(repo, args.expected_manifest_digest, args.handoff_relative)
    for name, expected in source_hashes.items():
        api.require(digest_file(ROOT / name) == expected, 'adapter source changed during delivery')
    api.require(digest_file(repo / DELIVERY_REL) == TRUSTED_DELIVERY_SHA256,
                'original delivery changed during adapter publication')
    for name, expected in stop_bindings.items(): api.bound_bytes(name, expected)
    print(json.dumps({'status': delivery['status'], 'package_root': delivery['package_root'],
                      'adapter': 'replication_delivery_observer_adapter_v1',
                      'root_handoff_published': False, 'final_package_created': False}, indent=2))


if __name__ == '__main__': main()
