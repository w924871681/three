"""Actual original full-source/environment/input audit, with no model imports."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DYNAMIC = HERE.parent/'replication_dynamic_scheduler_v1'
sys.path.insert(0, str(DYNAMIC))
from queue_store import read_json, sha, exclusive_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('requires -I -S -B')
    folder = HERE/f'preflight/attempt{args.attempt:03d}'
    folder.mkdir(parents=True, exist_ok=False)
    manifest_path = REPO/'results/p7_7_integrity_replication_batch20_env_v3/provenance_manifest.json'
    manifest = read_json(manifest_path)
    executor = Path(manifest['paths']['executor_root'])
    source = executor/'provenance.py'
    if sha(source) != manifest['executor_sha256']['provenance.py']:
        raise RuntimeError('original provenance changed')
    spec = importlib.util.spec_from_file_location('paper3_dynamic_preflight_original_provenance', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    started = datetime.now(timezone.utc).isoformat()
    exclusive_json(folder,'started.json',{'utc':started,'manifest_sha256':sha(manifest_path),
                   'original_provenance_sha256':sha(source),'model_imports_allowed':False})
    proof = module.verify_frozen(manifest, verify_environment=True, full=True, check_inputs=True)
    imported = sorted(name for name in sys.modules if name in ('torch','numpy','pandas','core') or name.startswith('core.'))
    if imported:
        raise RuntimeError('unexpected model import: '+str(imported))
    receipt = {'status':'PASS','scope':'ORIGINAL_FULL_SOURCE_ENVIRONMENT_INPUT_VERIFY_FROZEN',
               'original_verifier_result':proof, 'manifest_digest':manifest['manifest_digest'],
               'input_bundle_digest':manifest['input_bundle_digest'],
               'manifest_sha256':sha(manifest_path), 'preflight_source_sha256':sha(__file__),
               'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),
               'model_modules_imported':imported,'model_or_generator_executed':False}
    exclusive_json(folder,'passed.json',receipt)
    print(json.dumps({'status':'PASS','path':str(folder/'passed.json'),'sha256':sha(folder/'passed.json')}),flush=True)


if __name__ == '__main__':
    main()
