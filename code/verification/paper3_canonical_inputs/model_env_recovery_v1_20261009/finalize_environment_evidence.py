import datetime, hashlib, importlib.metadata, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent
PREFIX = ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1'
BASE = pathlib.Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311')
SITE = PREFIX / 'Lib' / 'site-packages'
def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()
checks = json.loads((ROOT / 'ENVIRONMENT_CHECKS_EXECUTION_RECEIPT_ATTEMPT002.json').read_text(encoding='utf-8'))
native = json.loads((ROOT / 'NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json').read_text(encoding='utf-8'))
if checks['status'] != 'PASS' or native['status'] != 'PASS':
    raise RuntimeError('All environment checks must PASS')
inventory = {}
for path in sorted(PREFIX.rglob('*')):
    if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
        if path.is_symlink() or not path.resolve().is_relative_to(PREFIX.resolve()):
            raise RuntimeError(f'Unsafe environment file {path}')
        inventory[str(path.relative_to(PREFIX)).replace('\\', '/')] = {'sha256': sha(path), 'size': path.stat().st_size}
distributions = []
for dist in sorted(importlib.metadata.distributions(path=[str(SITE)]), key=lambda d: d.metadata['Name'].lower()):
    distributions.append({'name': dist.metadata['Name'], 'version': dist.version, 'requires': dist.requires})
fingerprint_data = json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode('utf-8')
environment_inventory = {'environment_id': 'P7_7_REPLICATION_MODEL_ENV_V1', 'prefix': str(PREFIX), 'files': inventory, 'file_count': len(inventory), 'fingerprint_sha256': hashlib.sha256(fingerprint_data).hexdigest(), 'distributions': distributions, 'ordinary_startup_pth_files': [{'path': str(path), 'sha256': sha(path), 'executed_in_model_runtime': False} for path in SITE.glob('*.pth')], 'excluded_bytecode': 'All verification imports use -B; excluded CPython postinstall cache not scientific source/native', 'historical_environment_equivalence': 'NOT_VERIFIED'}
with (ROOT / 'MODEL_ENVIRONMENT_FILE_INVENTORY.json').open('x', encoding='utf-8') as handle:
    json.dump(environment_inventory, handle, indent=2)
evidence_names = ['OFFICIAL_WHEELHOUSE_VERIFIED_V1.json', 'requirements_replication_env_v1.lock.txt', 'PIP_INSTALL_RECEIPT.json', 'FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json', 'COPY_ATTEMPT_01_FAILURE_RECORD.json', 'ENVIRONMENT_CHECKS_EXECUTION_RECEIPT.json', 'NATIVE_COMPATIBILITY_TEST_RECEIPT.json', 'ENVIRONMENT_CHECKS_EXECUTION_RECEIPT_ATTEMPT002.json', 'NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json', 'MODEL_ENVIRONMENT_FILE_INVENTORY.json']
bindings = {str(ROOT / name): sha(ROOT / name) for name in evidence_names}
runtime = {'schema': 'paper3-reviewed-independent-model-runtime-v1', 'environment_id': 'P7_7_REPLICATION_MODEL_ENV_V1', 'prefix': str(PREFIX), 'base_prefix': str(BASE), 'python_executable': str(PREFIX / 'Scripts' / 'python.exe'), 'site_packages_root': str(SITE), 'stdlib_root': str(BASE / 'Lib'), 'expected_versions': native['exact_versions'], 'installation_evidence_files_sha256': bindings, 'historical_environment_equivalence': 'NOT_VERIFIED; independent replication runtime, approved pandas2.3.3 instead of frozen3.0.5, added fixed psutil7.2.2 and River0.23.0; NumPy and Torch source/native bytes unchanged', 'model_runtime_startup_policy': 'Interpreter -I -S -B; explicitly add only new independent site; do not process .pth/editable'}
with (ROOT / 'MODEL_RUNTIME_SPEC.json').open('x', encoding='utf-8') as handle:
    json.dump(runtime, handle, indent=2)
receipt = {'environment_status': 'ENVIRONMENT_READY', 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'runtime_spec_path': str(ROOT / 'MODEL_RUNTIME_SPEC.json'), 'runtime_spec_sha256': sha(ROOT / 'MODEL_RUNTIME_SPEC.json'), 'environment_fingerprint_sha256': environment_inventory['fingerprint_sha256'], 'pip_check': 'PASS', 'native_compatibility': 'PASS', 'stage_b_numpy_file_parity': native['stage_b_numpy_file_parity'], 'historical_environment_equivalence': 'NOT_VERIFIED', 'model_checkpoint_loading': 'NOT_EXECUTED_BY_ENVIRONMENT_RECOVERY_AGENT; root agent authorization stage required', 'experiment_execution': 'NOT_EXECUTED_BY_ENVIRONMENT_RECOVERY_AGENT', 'installation_evidence_files_sha256': bindings, 'source_recovery_scripts_sha256': {str(path): sha(path) for path in sorted(ROOT.glob('*.py'))}}
with (ROOT / 'MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
with (ROOT / 'requirements_runtime_exact_freeze.txt').open('x', encoding='utf-8') as handle:
    for dist in distributions:
        handle.write(f'{dist["name"]}=={dist["version"]}\n')
print(json.dumps({'status': receipt['environment_status'], 'runtime_spec_path': receipt['runtime_spec_path'], 'runtime_spec_sha256': receipt['runtime_spec_sha256'], 'environment_fingerprint_sha256': receipt['environment_fingerprint_sha256'], 'file_count': len(inventory)}, indent=2))
