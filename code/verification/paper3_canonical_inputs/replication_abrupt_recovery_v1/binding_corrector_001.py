"""Append-only correction of three evidence/source classification omissions.

No experiment or generator imports, no original file writes. The unchanged
consumer performs all environmental and scientific SHA checks before launch.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
HERE = ROOT / 'verification/paper3_canonical_inputs/replication_abrupt_recovery_v1'
OLD_SHA = '013e3aaa7f7bfbd99130a908c04431d75116d9ce875c3510c0569d5de50c183c'
ADDITIONS = {
    'verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/authorized_sequence.py': 'fcb4758e014da9f23be58ab61c46cb2969872842aca1224f73d25ce0c8cb7db8',
    'verification/paper3_canonical_inputs/autonomous_replication_execution_20261009_v3/phase_launcher.py': 'caf196ccc9f08264d0e39df758ccae9b5c063069fff0540dc872ff06f57e4b40',
    'verification/paper3_canonical_inputs/replication_finalizer_env_v3/finalizer.py': '1f20aca49b9dbe5ac5eabc9b2c7dbecd42309b870ce91ce6282a7770380dc23a',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def no_reparse(path):
    for item in (Path(path), *Path(path).parents):
        if item.exists():
            require(not item.is_symlink() and not getattr(item.lstat(), 'st_file_attributes', 0) & 0x400,
                    'Reparse path rejected: ' + str(item))


def corrected(old, root=ROOT, hash_file=sha):
    body = copy.deepcopy(old)
    digest = body.pop('gate_digest', None)
    require(digest == canonical(body), 'Original gate canonical digest differs')
    require(old.get('schema') == 'paper3-abrupt-recovery-gate-v1' and old.get('status') == 'PASS', 'Wrong gate')
    new = copy.deepcopy(old)
    for relative, expected in ADDITIONS.items():
        path = root / relative
        no_reparse(path)
        require(str(path) not in old['source_bindings_sha256'], 'Correction already present')
        require(old['evidence_sha256'].get(str(path)) == expected, 'Existing evidence SHA differs')
        require(hash_file(path) == expected, 'Actual source SHA differs: ' + relative)
        new['source_bindings_sha256'][str(path)] = expected
    new.pop('gate_digest')
    new['gate_digest'] = canonical(new)
    expected_body = copy.deepcopy(old)
    expected_body.pop('gate_digest')
    expected_body['source_bindings_sha256'].update({str(root / p): h for p, h in ADDITIONS.items()})
    require({k: v for k, v in new.items() if k != 'gate_digest'} == expected_body, 'Unexpected gate difference')
    return new


def emit(path, value):
    no_reparse(path)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    original = HERE / 'COLD_RECOVERY_001/cold_recovery_gate.json'
    target = HERE / 'COLD_RECOVERY_BINDING_CORRECTION_001'
    no_reparse(original)
    no_reparse(target)
    require(sha(original) == OLD_SHA, 'Original gate bytes differ')
    require(not target.exists(), 'Append-only target already exists')
    value = corrected(json.loads(original.read_text(encoding='utf-8')))
    target.mkdir()
    output = target / 'cold_recovery_gate.json'
    emit(output, value)
    require(sha(original) == OLD_SHA, 'Original gate changed during correction')
    emit(target / 'BINDING_CORRECTION_RECEIPT.json', {
        'schema': 'paper3-evidence-source-classification-correction-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'original_gate_path': str(original), 'original_gate_sha256': OLD_SHA,
        'corrected_gate_path': str(output), 'corrected_gate_sha256': sha(output),
        'implementation_sha256': sha(__file__), 'source_additions': {str(ROOT / p): h for p, h in ADDITIONS.items()},
        'only_changes': ['three existing evidence hashes also classified as source bindings', 'gate_digest recomputed'],
        'original_gate_preserved': True, 'scientific_fields_changed': False,
        'models_generators_or_statistics_executed': False,
        'full_evidence_revalidation_claimed': False,
        'next_requirement': 'unchanged consumer must revalidate every bound byte and resource admission',
    })
    print(json.dumps({'corrected_gate': str(output), 'sha256': sha(output), 'source_additions': 3}))


if __name__ == '__main__':
    main()
