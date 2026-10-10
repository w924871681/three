"""Append-only binding additions; preserve original JSON timestamp strings exactly."""
import copy
import hashlib
import json
import os
from pathlib import Path

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
HERE = Path(__file__).resolve().parent
OLD = REPO / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
SOURCE = OLD / 'COLD_RECOVERY_BINDING_CORRECTION_001/cold_recovery_gate.json'
TARGET = OLD / 'COLD_RECOVERY_METADATA_COMPAT_001/cold_recovery_gate.json'
EXPECTED = '49a9ad1db6bc6c6e138ad1844836a69fc19ff94921c630aa1fb4e8b8b37e528b'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert sha(SOURCE) == EXPECTED
    assert not TARGET.exists()
    original = json.loads(SOURCE.read_bytes())
    value = copy.deepcopy(original)
    value.pop('gate_digest')
    sources = list(HERE.glob('*.py')) + [HERE / name for name in
               ('STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.json', 'WRAPPER_TEST_RESULTS_001.json')]
    for path in sources:
        for parent in (path, *path.parents):
            assert not parent.is_symlink() and not getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400
        digest = sha(path)
        value['source_bindings_sha256'][str(path)] = digest
        value['evidence_sha256'][str(path)] = digest
    for name in ('durable_launch_001/supervisor_error.json', 'durable_launch_002/supervisor_error.json',
                 'durable_launch_002/continuation_stderr.log', 'COLD_RECOVERY_001/cold_recovery_gate.json',
                 'COLD_RECOVERY_BINDING_CORRECTION_001/cold_recovery_gate.json'):
        path = OLD / name
        value['evidence_sha256'][str(path)] = sha(path)
    omit = {'gate_digest', 'source_bindings_sha256', 'evidence_sha256'}
    assert {k: v for k, v in original.items() if k not in omit} == {k: v for k, v in value.items() if k not in omit}
    for field in ('source_bindings_sha256', 'evidence_sha256'):
        assert all(value[field].get(k) == v for k, v in original[field].items())
    value['gate_digest'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                                   ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    with TARGET.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    assert sha(SOURCE) == EXPECTED
    print(json.dumps({'path': str(TARGET), 'sha256': sha(TARGET), 'scientific_fields_unchanged': True,
                      'source_bindings': len(value['source_bindings_sha256']), 'evidence_bindings': len(value['evidence_sha256'])}))


if __name__ == '__main__': main()
