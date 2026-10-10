import datetime, hashlib, json, os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
PYTHON = ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1' / 'Scripts' / 'python.exe'
LOCK = ROOT / 'requirements_replication_env_v1.lock.txt'
manifest = json.loads((ROOT / 'OFFICIAL_WHEELHOUSE_VERIFIED_V1.json').read_text(encoding='utf-8'))
for item in manifest['results']:
    path = pathlib.Path(item['wheel_path']).resolve()
    if not path.is_relative_to(ROOT / 'wheelhouse') or hashlib.sha256(path.read_bytes()).hexdigest() != item['wheel_sha256']:
        raise RuntimeError(f'Wheelhouse changed {path}')
command = [str(PYTHON), '-I', '-B', '-m', 'pip', 'install', '--isolated', '--disable-pip-version-check', '--no-cache-dir', '--no-compile', '--require-hashes', '--no-index', '--find-links', str(ROOT / 'wheelhouse'), '-r', str(LOCK)]
environment = dict(os.environ)
environment.pop('PYTHONPATH', None)
environment.pop('PYTHONHOME', None)
environment['PYTHONDONTWRITEBYTECODE'] = '1'
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (ROOT / 'pip_install.stdout.log').open('x', encoding='utf-8') as out, (ROOT / 'pip_install.stderr.log').open('x', encoding='utf-8') as err:
    result = subprocess.run(command, env=environment, stdout=out, stderr=err, cwd=str(ROOT))
receipt = {'command': command, 'started_utc': started, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'exit_code': result.returncode, 'requirements_lock_sha256': hashlib.sha256(LOCK.read_bytes()).hexdigest(), 'only_official_verified_local_wheels': True, 'resolver_enabled_no_dependency_ignoring': True, 'original_environment_unchanged': 'Source directories only read; destination independent prefix', 'stdout_sha256': hashlib.sha256((ROOT / 'pip_install.stdout.log').read_bytes()).hexdigest(), 'stderr_sha256': hashlib.sha256((ROOT / 'pip_install.stderr.log').read_bytes()).hexdigest()}
with (ROOT / 'PIP_INSTALL_RECEIPT.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
print(json.dumps(receipt, indent=2))
sys.exit(result.returncode)
