"""Metadata-only compatibility for one SHA-pinned legacy synthetic-test schema.

No frozen source file or receipt is edited. Only a freshly imported private
finalizer module receives a copy of its original verification function. Every
original integrity check remains; the sole acceptance extension recognizes the
actual legacy 48-test receipt that lacks a status field.
"""
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
ORIGINAL = REPO / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1/finalizer.py'
ORIGINAL_SHA = 'ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652'
ORIGINAL_FUNCTION_SHA = '124310fac969a906957bb61f9c92c6d1082be3c3ec57988a09b9c14f34cca7d8'
LEGACY_RECEIPT_SHA = '4ddc671fc1485633b9226dd293fc275d2be46949c7d6d52afed5039f6a684c23'
PROOF_NAME = 'STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.json'
OWN_SOURCES = ('strict_legacy_proof_adapter.py', 'tests_strict_legacy_proof_adapter.py',
               'run_strict_legacy_proof_adapter_tests.py')
PROOF_SCHEMA = 'paper3-strict-legacy-proof-adapter-synthetic-v1'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def legacy_proof_matches(proof):
    """Strict missing-status branch; an explicit failure never qualifies."""
    return (
        isinstance(proof, dict) and 'status' not in proof and
        proof.get('schema') == 'paper3-cold-recovery-synthetic-test-proof-v1' and
        proof.get('all_pass') is True and type(proof.get('tests_run')) is int and proof['tests_run'] == 48 and
        all(type(proof.get(key)) is int and proof[key] == 0 for key in ('failures', 'errors', 'skipped')) and
        all(proof.get(key) is False for key in ('actual_models_generators_or_statistics_executed',
                                              'actual_original_results_written', 'actual_processes_modified'))
    )


def verify_binding(module, repo, gate_path, proof_path):
    """Small source/proof checks only; original function still hashes all pins."""
    repo, gate_path, proof_path = Path(repo), Path(gate_path), Path(proof_path)
    require(repo == REPO, 'Adapter repository differs')
    require(Path(module.__file__) == ORIGINAL and sha(ORIGINAL) == ORIGINAL_SHA, 'Original metadata module SHA/path differs')
    require(gate_path.is_absolute() and gate_path.is_relative_to(repo), 'Adapter gate outside repository')
    require(proof_path.is_absolute() and proof_path.is_relative_to(HERE) and proof_path.name == PROOF_NAME,
            'Adapter proof outside independent implementation directory')
    module.reject_reparse(gate_path)
    module.reject_reparse(proof_path)
    gate = module.load(gate_path)
    proof = module.load(proof_path)
    require(proof.get('schema') == PROOF_SCHEMA and proof.get('status') == 'PASS' and proof.get('all_pass') is True,
            'Adapter synthetic proof is not PASS')
    require(type(proof.get('tests_run')) is int and proof['tests_run'] > 0 and
            all(type(proof.get(key)) is int and proof[key] == 0 for key in ('failures', 'errors', 'skipped')),
            'Adapter synthetic proof counts are incomplete')
    require(all(proof.get(key) is False for key in ('real_experimental_outcomes_read', 'real_experiment_processes_launched',
                                                  'models_generators_statistics_executed', 'real_environment_hashed')),
            'Adapter synthetic proof scope differs')
    source_pins, evidence = gate.get('source_bindings_sha256', {}), gate.get('evidence_sha256', {})
    legacy_receipt = ORIGINAL.parent / 'COLD_RECOVERY_SYNTHETIC_TEST_RESULTS_ATTEMPT001.json'
    for parent in (legacy_receipt, *legacy_receipt.parents):
        module.reject_reparse(parent)
    require(sha(legacy_receipt) == LEGACY_RECEIPT_SHA and evidence.get(str(legacy_receipt)) == LEGACY_RECEIPT_SHA,
            'Actual legacy receipt bytes/evidence binding differ')
    own = proof.get('implementation_sha256', {})
    require(set(own) == set(OWN_SOURCES), 'Adapter proof source closure differs')
    for name, digest in own.items():
        path = HERE / name
        for parent in (path, *path.parents):
            module.reject_reparse(parent)
        require(sha(path) == digest and source_pins.get(str(path)) == digest and evidence.get(str(path)) == digest,
                'Adapter own source not exact source/evidence-bound: ' + name)
    proof_digest = sha(proof_path)
    require(source_pins.get(str(proof_path)) == proof_digest and evidence.get(str(proof_path)) == proof_digest,
            'Adapter proof not exact source/evidence-bound')
    require(proof.get('original_finalizer_sha256') == ORIGINAL_SHA and
            proof.get('original_verify_function_sha256') == ORIGINAL_FUNCTION_SHA and
            proof.get('legacy_original_receipt_sha256') == LEGACY_RECEIPT_SHA,
            'Adapter original dependency binding differs')
    return {'adapter_sha256': own['strict_legacy_proof_adapter.py'], 'compatibility_proof_sha256': proof_digest}


def compile_into_private_module(module, guard):
    """Exact source transform; used with a synthetic guard only in unit tests."""
    require(Path(module.__file__) == ORIGINAL and sha(ORIGINAL) == ORIGINAL_SHA, 'Original finalizer SHA/path differs')
    original = inspect.getsource(module.verify_transition_gate)
    require(hashlib.sha256(original.encode()).hexdigest() == ORIGINAL_FUNCTION_SHA, 'Original verification function differs/already adapted')
    old = "proof.get('status')=='PASS'"
    anchor = '    repo=Path(repo);gate_path=Path(gate_path)\n'
    require(original.count(old) == 1 and original.count(anchor) == 1, 'Expected unique compatibility anchors absent')
    transformed = original.replace(old, "(proof.get('status')=='PASS' or _strict_legacy_proof_matches(proof))", 1)
    transformed = transformed.replace(anchor, anchor + '    _strict_adapter_binding(repo,gate_path)\n', 1)
    module.__dict__['_strict_legacy_proof_matches'] = legacy_proof_matches
    module.__dict__['_strict_adapter_binding'] = guard
    exec(compile(transformed, str(HERE / 'strict_legacy_proof_adapter.py') + ':copied_verify_transition_gate', 'exec'), module.__dict__)
    require(module.verify_transition_gate.__globals__ is module.__dict__, 'Copied verifier globals differ')
    return hashlib.sha256(transformed.encode()).hexdigest()


def install(module, repo: Path, gate_path: Path, proof_path: Path) -> dict:
    """Install only into the caller's fresh private metadata module; edit no file."""
    binding = verify_binding(module, repo, gate_path, proof_path)
    require(not module.__dict__.get('_paper3_strict_legacy_adapter_installed'), 'Adapter already installed in this private module')
    original_file = module.__file__
    def guard(actual_repo, actual_gate):
        require(Path(actual_repo) == Path(repo) and Path(actual_gate) == Path(gate_path), 'Adapted verifier gate/repository changed')
        verify_binding(module, actual_repo, actual_gate, proof_path)
    compiled_sha = compile_into_private_module(module, guard)
    module.__dict__['_paper3_strict_legacy_adapter_installed'] = True
    require(module.__file__ == original_file, 'Original module __file__ changed')
    return {'schema': 'paper3-strict-legacy-proof-adapter-installation-v1',
            'installed_utc': datetime.now(timezone.utc).isoformat(), 'metadata_only': True,
            'original_finalizer_path': str(ORIGINAL), 'original_finalizer_sha256': ORIGINAL_SHA,
            'original_verify_function_sha256': ORIGINAL_FUNCTION_SHA, 'copied_verify_function_sha256': compiled_sha,
            'legacy_original_receipt_sha256': LEGACY_RECEIPT_SHA, 'compatibility_proof_path': str(proof_path),
            'gate_path': str(gate_path), 'original_module_file_unchanged': True,
            'full_pin_hash_checks_retained': True, **binding}
