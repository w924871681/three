"""Read-only inventory used while the exact old producer tree is suspended.

No project scientific module, generator, model, optimizer or statistics import.
All scientific admission is delegated to the existing source-pinned validator.
"""
from pathlib import Path
import sys
from datetime import datetime, timezone

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
SCHEDULER = REPO / 'verification/paper3_canonical_inputs/replication_dynamic_scheduler_v1'
if str(SCHEDULER) not in sys.path:
    sys.path.insert(0, str(SCHEDULER))
from frozen_reference import FrozenReference
from integrity import validate_completion, paired_groups, rng_identity, require
from queue_store import read_json, sha, canonical, task_stem


def snapshot(contract):
    ref = FrozenReference(contract['manifest_path'])
    manifest, root = ref.manifest, ref.root
    bindings = {
        'manifest_digest': manifest['manifest_digest'],
        'input_bundle_digest': manifest['input_bundle_digest'],
        'environment_binding': manifest['environment_binding'],
        'initial_state_manifest_sha256': ref.initial_sha,
        'source_bindings_digest': canonical(manifest['critical_files_sha256']),
        'executor_bundle_digest': canonical(manifest['executor_sha256']),
        'scientific_runtime_signature': ref.initial['scientific_runtime_signature'],
    }
    require(bindings == contract['bindings'], 'cutover scientific bindings changed')
    saved, artifacts, proofs, unknown = {}, {}, [], []

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        value = sha(path)
        require(expected is None or value == expected, 'inventory SHA differs: ' + str(path))
        require(str(path) not in artifacts or artifacts[str(path)] == value, 'artifact changed during inventory')
        artifacts[str(path)] = value
        return value

    raw_csv = {p.stem for p in (root/'raw').glob('*.csv')}
    raw_receipts = {p.name.removesuffix('.integrity.json') for p in (root/'raw').glob('*.integrity.json')}
    require(raw_csv == raw_receipts, 'partial final publication; resume old owners without terminating')
    for name in sorted(raw_receipts):
        receipt_path = root / f'raw/{name}.integrity.json'
        receipt = read_json(receipt_path)
        task = receipt['task']
        require(task_stem(task) == name, 'raw filename/task mismatch')
        proof = validate_completion(root, task, ref.expected(task))
        proofs.append(proof)
        saved[name] = bind(receipt_path, proof['receipt_sha256'])
        bind(root/f'raw/{name}.csv', receipt['output_hash'])
        for field, digest in (('audit_relative','audit_hash'), ('rng_relative','rng_file_sha256'),
                              ('attempt_csv_relative','attempt_csv_hash'), ('runtime_receipt_path','runtime_receipt_sha256')):
            bind(root/receipt[field], receipt[digest])
        attempt_receipt = root/receipt['attempt_csv_relative']
        attempt_receipt = attempt_receipt.parent/'receipt.json'
        require(read_json(attempt_receipt) == receipt, 'attempt/canonical receipts differ')
        bind(attempt_receipt)
    pairs = paired_groups(proofs)['complete_paired_groups']
    bind(Path(contract['manifest_path']), contract['manifest_file_sha256'])
    bind(root/'initial_state_manifest.json', ref.initial_sha)
    bind(ref.f1_path, manifest['stage_b_bindings']['F1'])
    for relative, digest in manifest['critical_files_sha256'].items():
        bind(REPO/relative, digest)
    for relative, digest in manifest['executor_sha256'].items():
        bind(Path(manifest['paths']['executor_root'])/relative, digest)
    for relative, digest in manifest['input_files_sha256'].items():
        bind(Path(manifest['paths']['input_run'])/relative, digest)
    for item in ref.initial['states']:
        bind(root/item['path'], item['sha256'])
        bind(root/item['receipt_path'], item['receipt_sha256'])
    for path, digest in contract.get('protected_files_sha256', {}).items():
        bind(path, digest)
    for path, digest in contract['snapshot_source_sha256'].items():
        bind(path, digest)

    pending = []
    for worker, descriptor in contract['requests'].items():
        bind(descriptor['path'], descriptor['sha256'])
        request = read_json(descriptor['path'])
        require(request['worker_id'] == worker and request['attempt_id'] == 'A_FULL_0002', 'old request identity differs')
        require(request['manifest_digest'] == manifest['manifest_digest'], 'old request manifest differs')
        seen = []
        for task in request['tasks']:
            name = task_stem(task)
            folder = root / f'attempts/{name}/A_FULL_0002/{worker}'
            if not folder.exists() or name in saved:
                continue
            files = list(folder.rglob('*'))
            require(all(p.is_file() for p in files), 'unexpected pending subdirectory')
            require({p.name for p in files} == {'rng_before.json'},
                    'pending attempt is not RNG-only; preserve, resume and stop: ' + name)
            rng_path = folder/'rng_before.json'
            rng = read_json(rng_path)
            expected = ref.expected(task)
            state = rng_identity(rng, expected['rng_bindings'], expected['scientific_runtime'])
            digest = bind(rng_path)
            seen.append({'task':task, 'worker_id':worker, 'attempt_id':'A_FULL_0002',
                         'rng_relative':rng_path.relative_to(root).as_posix(),
                         'rng_file_sha256':digest, 'rng_state_digest':state,
                         'initial_state_hash':expected['initial_state_hash']})
        require(len(seen) <= 1, 'more than one pending task for one old worker')
        # A source-audit/setup interval with no captured task can be stopped;
        # no run_one body is then eligible for any invented RNG retry.
        pending.extend(seen)
    for path in (root/'attempts').glob('*/A_FULL_0002/*'):
        if path.is_dir():
            require(path.name in contract['requests'], 'unknown old worker attempt directory')
            require(path.parent.parent.name in saved or any(
                p['rng_relative'].startswith(path.relative_to(root).as_posix()+'/') for p in pending),
                'unknown old attempt cannot be redrawn: ' + str(path))
    return {'schema':'paper3-dynamic-cutover-snapshot-v1', 'bindings':bindings,
            'saved_records':saved, 'saved_artifacts':artifacts,
            'completed_count':len(saved), 'paired_count':pairs, 'pending':pending,
            'unknown_artifacts':unknown,
            'validation_scope':'FROZEN_REFERENCE_VALIDATE_COMPLETION_ALL_SAVED_24_STAGES',
            'captured_utc':datetime.now(timezone.utc).isoformat()}
