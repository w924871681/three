"""Explicit entry-point receipt for unchanged recovery functions with a legacy proof reader."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
HERE = Path(__file__).resolve().parent
ORIGINAL = REPO / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
ORIGINAL_SHA = {
    'continuation': 'b12760cb14ea47fe54a149daf50fbd0bac86582824fb9a4dda65f877fb5fdaef',
    'finalizer': 'ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value: raise RuntimeError(message)


def load_module(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(kind, entrypoint):
    require(kind in ORIGINAL_SHA, 'Unknown entry kind')
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    require(Path(entrypoint).resolve() == HERE / ('compat_' + kind + '.py') and
            Path(sys.argv[0]).resolve() == Path(entrypoint).resolve(), 'Unexpected actual entrypoint')
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--cold-gate', required=True)
    args, _ = parser.parse_known_args()
    require(Path(args.repo) == REPO, 'Wrong repository')
    gate = Path(args.cold_gate)
    require(gate == ORIGINAL / 'COLD_RECOVERY_METADATA_COMPAT_001/cold_recovery_gate.json', 'Wrong exclusive gate')
    value = json.loads(gate.read_text(encoding='utf-8'))
    # The launcher binds these bytes before import; the actual consumer checks
    # the complete evidence map again. No SHA method is mocked or disabled.
    for source in (HERE / 'compat_entry.py', HERE / ('compat_' + kind + '.py'),
                   HERE / 'strict_legacy_proof_adapter.py'):
        require(value['source_bindings_sha256'].get(str(source)) == sha(source), 'Entry source is not gate-bound')
    original_path = ORIGINAL / (kind + '.py')
    require(sha(original_path) == ORIGINAL_SHA[kind], 'Original helper source differs')
    module = load_module('original_recovery_' + kind, original_path)
    api = module.f if kind == 'continuation' else module
    adapter = load_module('strict_legacy_cold_proof_reader', HERE / 'strict_legacy_proof_adapter.py')
    metadata = adapter.install(api, REPO, gate, HERE / 'STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.json')
    receipt = {
        'schema': 'paper3-actual-compatibility-entrypoint-v1',
        'started_utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
        'entrypoint': str(entrypoint), 'entrypoint_sha256': sha(entrypoint),
        'actual_argv': sys.argv, 'original_module': str(original_path),
        'original_module_sha256': ORIGINAL_SHA[kind], 'cold_gate_sha256': sha(gate),
        'metadata_reader_compatibility': metadata,
        'about_to_invoke_original_helper_main': True, 'original_main_called_directly_by_OS': False,
        'scientific_algorithm_or_input_changed': False,
        'all_bound_SHA_checks_and_resource_gate_preserved': True,
        'model_workers_started_claimed': False,
    }
    target = gate.parent / ('ACTUAL_' + kind.upper() + '_ADAPTER_ENTRY_001.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'metadata_adapter_installed': True, 'kind': kind, 'pid': os.getpid()}), flush=True)
    module.main()
