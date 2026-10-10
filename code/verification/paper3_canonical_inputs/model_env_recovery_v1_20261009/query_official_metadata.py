import datetime, hashlib, json, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
queries = {
    'river': '0.23.0', 'pandas': '2.3.3', 'psutil': None,
    'numpy': '2.4.6', 'scipy': '1.17.1', 'scikit-learn': '1.9.0',
    'torch': '2.5.1', 'typing-extensions': '4.16.0', 'filelock': '3.32.0',
}
summary = {}
for name, version in queries.items():
    url = f'https://pypi.org/pypi/{name}/' + (f'{version}/' if version else '') + 'json'
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        payload = json.loads(data)
        target = ROOT / (name.replace('-', '_') + '_official_metadata.json')
        with target.open('xb') as handle:
            handle.write(data)
        files = [f for f in payload['urls'] if f['packagetype'] == 'bdist_wheel' and (('win_amd64' in f['filename'] and ('cp311' in f['filename'] or 'abi3' in f['filename'])) or 'none-any' in f['filename'])]
        summary[name] = {'url': url, 'retrieved_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'json_sha256': hashlib.sha256(data).hexdigest(), 'version': payload['info']['version'], 'requires_python': payload['info'].get('requires_python'), 'requires_dist': payload['info'].get('requires_dist'), 'compatible_wheel_candidates': files}
    except Exception as error:
        summary[name] = {'url': url, 'error': str(error), 'historical_pin_available_from_official_current_index': False}
with (ROOT / 'OFFICIAL_METADATA_QUERY_SUMMARY.json').open('x', encoding='utf-8') as handle:
    json.dump(summary, handle, indent=2)
print(json.dumps(summary, indent=2))
