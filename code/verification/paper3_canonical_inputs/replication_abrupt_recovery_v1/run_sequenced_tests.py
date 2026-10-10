"""Persists actual synthetic scheduling test evidence; no experimental work."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
root = Path(__file__).resolve().parent
proof, log = root / 'SEQUENCED_SUPERVISOR_TEST_RESULTS_001.json', root / 'SEQUENCED_SUPERVISOR_TEST_RESULTS_001.log'
if proof.exists() or log.exists():
    raise FileExistsError('Existing evidence is preserved')
command = [sys.executable, '-I', '-S', '-B', str(root / 'tests_sequenced_supervisor.py')]
with log.open('xb') as stream:
    result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
text = log.read_text(encoding='utf-8').replace('\r\n', '\n')
passed = result.returncode == 0 and 'Ran 4 tests' in text and '\nOK\n' in text
value = {'schema': 'paper3-sequenced-supervisor-synthetic-proof-v1', 'status': 'PASS' if passed else 'FAIL',
         'all_pass': passed, 'tests_run': 4 if passed else None, 'actual_exit_code': result.returncode,
         'verified_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
         'models_generators_statistics_or_real_children_executed': False,
         'files_sha256': {str(root / name): hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in ('sequenced_supervisor.py', 'tests_sequenced_supervisor.py',
                                       'run_sequenced_tests.py', 'durable_supervisor.py')},
         'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
with proof.open('x', encoding='utf-8') as stream:
    json.dump(value, stream, indent=2)
    stream.write('\n')
print(json.dumps({'status': value['status'], 'tests_run': value['tests_run'], 'proof': str(proof)}))
sys.exit(0 if passed else 1)
