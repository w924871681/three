import datetime, hashlib, json, os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
PYTHON = ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1' / 'Scripts' / 'python.exe'
COPY = ROOT / 'FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json'
if not COPY.is_file():
    raise RuntimeError('Full frozen package copy receipt required before checks')
checks = {
    'pip_check': [str(PYTHON), '-I', '-B', '-m', 'pip', 'check', '--disable-pip-version-check'],
    'native_compatibility': [str(PYTHON), '-I', '-S', '-B', str(ROOT / 'verify_runtime_compatibility.py'), '--attempt002'],
}
environment = dict(os.environ)
environment.pop('PYTHONPATH', None)
environment.pop('PYTHONHOME', None)
environment['PYTHONDONTWRITEBYTECODE'] = '1'
environment['MPLCONFIGDIR'] = str(ROOT / 'runtime_cache' / 'matplotlib')
environment['TORCH_HOME'] = str(ROOT / 'runtime_cache' / 'torch')
environment['XDG_CACHE_HOME'] = str(ROOT / 'runtime_cache')
receipt = {'checks': {}}
for name, command in checks.items():
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (ROOT / (name + '_attempt002.stdout.log')).open('x', encoding='utf-8') as out, (ROOT / (name + '_attempt002.stderr.log')).open('x', encoding='utf-8') as err:
        process = subprocess.run(command, stdout=out, stderr=err, env=environment, cwd=str(ROOT))
    result = {'command': command, 'started_utc': start, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'exit_code': process.returncode, 'stdout_sha256': hashlib.sha256((ROOT / (name + '_attempt002.stdout.log')).read_bytes()).hexdigest(), 'stderr_sha256': hashlib.sha256((ROOT / (name + '_attempt002.stderr.log')).read_bytes()).hexdigest()}
    receipt['checks'][name] = result
    print(f'{name} exit={process.returncode}', flush=True)
    if process.returncode:
        break
receipt['status'] = 'PASS' if len(receipt['checks']) == 2 and all(item['exit_code'] == 0 for item in receipt['checks'].values()) else 'FAIL'
with (ROOT / 'ENVIRONMENT_CHECKS_EXECUTION_RECEIPT_ATTEMPT002.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
sys.exit(0 if receipt['status'] == 'PASS' else 1)
