"""Read-only verification of the archived payload; stdlib only, no experiments."""
import hashlib
import json
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = root / 'BACKUP_MANIFEST.json'
    expected = (root / 'BACKUP_MANIFEST.json.sha256').read_text().split()[0]
    if sha256(manifest) != expected:
        raise SystemExit('FAIL: BACKUP_MANIFEST.json hash mismatch')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    failures = []
    for relative, record in data['files'].items():
        p = root / relative
        if not p.is_file() or p.stat().st_size != record['bytes'] or sha256(p) != record['sha256']:
            failures.append(relative)
    if failures:
        print(json.dumps({'status': 'FAIL', 'files': failures}, indent=2))
        raise SystemExit(1)
    print(json.dumps({'status': 'PASS', 'verified_files': len(data['files']),
                      'verified_bytes': sum(v['bytes'] for v in data['files'].values()),
                      'scope': 'Archived file identity only; no scientific recomputation'}, indent=2))


if __name__ == '__main__':
    main()
