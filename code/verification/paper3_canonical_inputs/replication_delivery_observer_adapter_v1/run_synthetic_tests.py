"""Exclusive NEW synthetic proof; no real receipt is read by child tests."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('requires -I -S -B')
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=int, default=2)
    args = parser.parse_args()
    if args.attempt <= 0: raise RuntimeError('positive synthetic attempt required')
    proof = ROOT / f'SYNTHETIC_TEST_RESULTS_ATTEMPT{args.attempt:03d}.json'
    if proof.exists(): raise RuntimeError('exclusive synthetic proof already exists')
    originals = [ROOT.parent / 'replication_delivery_env_v3/delivery.py',
                 ROOT.parent / 'replication_abrupt_recovery_v1/finalizer.py']
    before = {str(path): sha(path) for path in originals}
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-I', '-S', '-B', str(ROOT / 'test_observer_adapter.py')]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    after = {str(path): sha(path) for path in originals}
    for name, payload in [(f'synthetic_attempt{args.attempt:03d}_stdout.log', result.stdout),
                          (f'synthetic_attempt{args.attempt:03d}_stderr.log', result.stderr)]:
        with (ROOT / name).open('xb') as stream: stream.write(payload)
    receipt = {
        'schema': 'paper3-delivery-observer-adapter-synthetic-proof-v1',
        'status': 'SYNTHETIC_ONLY_NOT_INTEGRATED',
        'all_pass': result.returncode == 0 and before == after,
        'exit_code': result.returncode, 'command': command,
        'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
        'real_phase_receipts_read_by_tests': False, 'real_outcomes_read': False,
        'models_generators_or_statistics_executed': False, 'real_delivery_published': False,
        'running_finalizer_modified': False,
        'implementation_sha256': {path.name: sha(path) for path in ROOT.glob('*.py')},
        'original_guard_source_sha256_before': before,
        'original_guard_source_sha256_after': after,
        'original_guard_sources_unchanged': before == after,
        'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
        'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
    }
    with proof.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'all_pass': receipt['all_pass'], 'exit_code': result.returncode,
                      'proof': str(proof)}, indent=2))
    if not receipt['all_pass']: raise SystemExit(1)


if __name__ == '__main__': main()
