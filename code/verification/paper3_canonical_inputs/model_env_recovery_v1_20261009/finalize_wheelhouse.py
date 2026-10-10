import datetime, hashlib, json, pathlib, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
prior = json.loads((ROOT / 'WHEELHOUSE_SOURCE_MANIFEST.json').read_text())
if prior['errors'] != [{'package': ['fonttools', '4.63.0'], 'error': "RuntimeError(\"Need exactly one cp311 Windows/pure wheel fonttools: ['fonttools-4.63.0-cp311-cp311-win_amd64.whl', 'fonttools-4.63.0-py3-none-any.whl']\")"}]:
    raise RuntimeError(f'Unexpected download errors: {prior["errors"]}')
metadata = ROOT / 'official_metadata' / 'fonttools_4.63.0.json'
payload = json.loads(metadata.read_text(encoding='utf-8'))
chosen = [f for f in payload['urls'] if f['filename'] == 'fonttools-4.63.0-cp311-cp311-win_amd64.whl' and not f['yanked']]
if len(chosen) != 1:
    raise RuntimeError('Need precise original native ABI choice')
chosen = chosen[0]
with urllib.request.urlopen(chosen['url'], timeout=180) as response:
    data = response.read()
actual = hashlib.sha256(data).hexdigest()
if actual != chosen['digests']['sha256']:
    raise RuntimeError('Wheel hash mismatch')
target = ROOT / 'wheelhouse' / chosen['filename']
with target.open('xb') as handle:
    handle.write(data)
results = prior['results'] + [{'name': 'fonttools', 'version': '4.63.0', 'metadata_url': 'https://pypi.org/pypi/fonttools/4.63.0/json', 'metadata_path': str(metadata), 'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest(), 'wheel_url': chosen['url'], 'wheel_path': str(target), 'wheel_sha256': actual, 'wheel_size': len(data), 'requires_dist': payload['info'].get('requires_dist'), 'retrieved_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'selection_resolution': 'Choose exact cp311 Windows native wheel, matching original compiled package ABI; pure wheel not selected'}]
receipt = {'pins': prior['pins'], 'results': sorted(results, key=lambda x: x['name']), 'all_official_wheel_hashes_verified': True, 'prior_attempt_manifest_sha256': hashlib.sha256((ROOT / 'WHEELHOUSE_SOURCE_MANIFEST.json').read_bytes()).hexdigest(), 'selection_fixed_before_model_outcomes': True}
with (ROOT / 'OFFICIAL_WHEELHOUSE_VERIFIED_V1.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
with (ROOT / 'requirements_replication_env_v1.lock.txt').open('x', encoding='utf-8') as handle:
    for result in sorted(results, key=lambda x: x['name']):
        handle.write(f'{result["name"]}=={result["version"]} --hash=sha256:{result["wheel_sha256"]}\n')
print('PASS verified official wheelhouse', len(results))
