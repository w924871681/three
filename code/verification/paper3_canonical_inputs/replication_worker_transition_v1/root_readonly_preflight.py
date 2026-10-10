"""Read frozen bytes only; no science imports or process control."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
RESULT = REPO/'results/p7_7_integrity_replication_batch20_env_v3'
MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1 = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'

def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return value.hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(Path(__file__).resolve().parent) and not output.exists()
    started = datetime.now(timezone.utc).isoformat()
    path = RESULT/'provenance_manifest.json'
    manifest_sha = sha(path)
    manifest = json.loads(path.read_text(encoding='utf-8'))
    assert manifest['manifest_digest'] == MANIFEST and manifest['input_bundle_digest'] == F1
    assert canonical({k:v for k,v in manifest.items() if k != 'manifest_digest'}) == MANIFEST
    input_run = Path(manifest['paths']['input_run'])
    execution = REPO/'verification/paper3_canonical_inputs/execution_20261009'
    stage_b_paths = {
        'F1': input_run/'contexts/F1.json',
        'gate': execution/'stage_b_scientific_gate.json',
        'gate_helper': execution/'check_stage_b_gate.py',
        'outputs_inventory': input_run/'outputs_inventory.json',
        'receipt': input_run/'execution_receipt.json',
        'reviewed_environment': execution/'environment.reviewed.json',
        'run_manifest': input_run/'run_manifest.json',
        'source_environment': input_run/'source_environment_manifest.json',
    }
    stage_b_files = {str(path): manifest['stage_b_bindings'][alias] for alias, path in stage_b_paths.items()}
    stage_b_source = json.loads(stage_b_paths['source_environment'].read_text(encoding='utf-8'))
    assert canonical(stage_b_source['implementation']) == manifest['stage_b_bindings']['verifier_implementation_digest']
    groups = [
        ('critical', REPO, manifest['critical_files_sha256']),
        ('executor', Path(manifest['paths']['executor_root']), manifest['executor_sha256']),
        ('original_python', REPO, manifest['original_python_dependency_sha256']),
        ('original_protected', REPO, manifest['original_protected_snapshot']),
        ('F1_inputs', Path(manifest['paths']['input_run']), manifest['input_files_sha256']),
        ('stage_b_evidence', None, stage_b_files),
        ('stage_b_dependencies', None, manifest['stage_b_dependencies_sha256']),
        ('environment', None, manifest['environment']['bound_files_sha256']),
    ]
    observed, counts, errors = {}, {}, []
    for name, root, pins in groups:
        counts[name] = len(pins)
        for relative, expected in pins.items():
            target = root/relative if root is not None else Path(relative)
            try:
                for ancestor in (target, *target.parents):
                    assert not ancestor.is_symlink()
                    if ancestor.exists(): assert not getattr(ancestor.lstat(), 'st_file_attributes', 0)&0x400
                actual = observed.setdefault(str(target), sha(target))
                if actual != expected: errors.append({'group': name, 'path': str(target), 'expected': expected, 'actual': actual})
            except Exception as error:
                errors.append({'group': name, 'path': str(target), 'error': repr(error)})
        print(json.dumps({'group':name,'files':counts[name],'mismatches_so_far':len(errors)}), flush=True)
    assert sha(path) == manifest_sha
    git = subprocess.run(['git','-C',str(REPO),'status','--short','--untracked-files=no'],
        check=True, capture_output=True, text=True, env={**os.environ, 'GIT_OPTIONAL_LOCKS':'0'}).stdout
    record = {'schema':'paper3-worker-transition-root-readonly-preflight-v1',
        'status':'PASS' if not errors else 'FAIL', 'started_utc':started,
        'finished_utc':datetime.now(timezone.utc).isoformat(), 'repository':str(REPO),
        'manifest_digest':MANIFEST,'input_bundle_digest':F1,'manifest_file_sha256':manifest_sha,
        'group_file_counts':counts,'unique_files_checked':len(observed),
        'observed_sha256':observed,'mismatches':errors,'git_tracked_status':git,
        'models_generators_or_statistics_executed':False,'processes_modified':False,
        'root_handoff_sha256':sha(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md'),
        'implementation_sha256':sha(__file__), 'scope':'Byte verification only, not a numerical or historical-runtime equivalence claim.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(record,stream,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ('observed_sha256','mismatches')}))
    if errors: raise SystemExit(1)

if __name__ == '__main__': main()
