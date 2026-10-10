import concurrent.futures, datetime, hashlib, json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
WHEELS = ROOT / 'wheelhouse'
METADATA = ROOT / 'official_metadata'
WHEELS.mkdir(exist_ok=False)
METADATA.mkdir(exist_ok=False)
REQ = pathlib.Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\configs\requirements_frozen.txt')
pins = {}
for line in REQ.read_text().splitlines():
    if '==' in line:
        name, version = line.strip().split('==')
        if name not in {'torch', 'torchaudio', 'torchvision', 'pandas'}:
            pins[name] = version
pins.update({'pandas': '2.3.3', 'river': '0.23.0', 'psutil': '7.2.2', 'pytz': '2025.2'})

def fetch(url):
    errors = []
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                return response.read(), errors
        except Exception as error:
            errors.append({'attempt': attempt, 'error': repr(error)})
            time.sleep(attempt)
    raise RuntimeError(f'Cannot retrieve {url}: {errors}')

def prepare(item):
    name, version = item
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    data, retries = fetch(url)
    payload = json.loads(data)
    if payload['info']['version'] != version:
        raise RuntimeError(f'Unexpected version {name}')
    metadata_file = METADATA / (name.replace('-', '_') + '_' + version + '.json')
    with metadata_file.open('xb') as handle:
        handle.write(data)
    candidates = [f for f in payload['urls'] if f['packagetype'] == 'bdist_wheel' and not f['yanked'] and (('win_amd64' in f['filename'] and ('cp311-cp311' in f['filename'] or 'abi3' in f['filename'])) or 'none-any.whl' in f['filename'])]
    if len(candidates) != 1:
        raise RuntimeError(f'Need exactly one cp311 Windows/pure wheel {name}: {[f["filename"] for f in candidates]}')
    chosen = candidates[0]
    if not chosen['url'].startswith('https://files.pythonhosted.org/'):
        raise RuntimeError('Untrusted wheel host')
    wheel_bytes, wheel_retries = fetch(chosen['url'])
    actual = hashlib.sha256(wheel_bytes).hexdigest()
    if actual != chosen['digests']['sha256'] or len(wheel_bytes) != chosen['size']:
        raise RuntimeError(f'Wheel integrity mismatch {name}')
    target = WHEELS / chosen['filename']
    with target.open('xb') as handle:
        handle.write(wheel_bytes)
    print(f'VERIFIED {name}=={version} {actual}', flush=True)
    return {'name': name, 'version': version, 'metadata_url': url, 'metadata_path': str(metadata_file), 'metadata_sha256': hashlib.sha256(data).hexdigest(), 'wheel_url': chosen['url'], 'wheel_path': str(target), 'wheel_sha256': actual, 'wheel_size': len(wheel_bytes), 'metadata_retry_errors': retries, 'wheel_retry_errors': wheel_retries, 'requires_dist': payload['info'].get('requires_dist'), 'retrieved_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}

results, errors = [], []
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(prepare, item): item for item in pins.items()}
    for future in concurrent.futures.as_completed(futures):
        try:
            results.append(future.result())
        except Exception as error:
            errors.append({'package': futures[future], 'error': repr(error)})
            print(f'FAIL {futures[future]}: {error}', flush=True)
inventory = {'selected_before_model_outcomes': True, 'pins': pins, 'results': sorted(results, key=lambda x: x['name']), 'errors': errors, 'frozen_requirements_sha256': hashlib.sha256(REQ.read_bytes()).hexdigest()}
with (ROOT / 'WHEELHOUSE_SOURCE_MANIFEST.json').open('x', encoding='utf-8') as handle:
    json.dump(inventory, handle, indent=2)
if not errors:
    with (ROOT / 'requirements_replication_env_v1.lock.txt').open('x', encoding='utf-8') as handle:
        for result in sorted(results, key=lambda x: x['name']):
            handle.write(f'{result["name"]}=={result["version"]} --hash=sha256:{result["wheel_sha256"]}\n')
sys.exit(1 if errors else 0)
