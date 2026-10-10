"""Records actual independent supervisor synthetic tests; no science is executed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parent
proof = root / 'DURABLE_SUPERVISOR_TEST_RESULTS_002.json'
log = root / 'DURABLE_SUPERVISOR_TEST_RESULTS_002.log'
if proof.exists() or log.exists():
    raise FileExistsError('Independent proof already exists')
command = [sys.executable, '-I', '-S', '-B', str(root / 'tests_durable_supervisor.py')]
with log.open('xb') as out:
    result = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, check=False)
payload = log.read_text(encoding='utf-8')
passed = result.returncode == 0 and 'Ran 10 tests' in payload and '\nOK\n' in payload.replace('\r\n', '\n')
value = {'schema': 'paper3-durable-supervisor-synthetic-proof-v1',
         'status': 'PASS' if passed else 'FAIL', 'all_pass': passed,
         'tests_run': 10 if passed else None, 'actual_exit_code': result.returncode,
         'verified_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
         'models_generators_or_statistics_executed': False,
         'implementation_sha256': {str(root / name): hashlib.sha256((root / name).read_bytes()).hexdigest()
                                    for name in ('durable_supervisor.py', 'background_job_probe.py',
                                                 'tests_durable_supervisor.py', 'run_durable_tests.py')},
         'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
with proof.open('x', encoding='utf-8') as out:
    json.dump(value, out, indent=2)
    out.write('\n')
    out.flush()
    os.fsync(out.fileno())
print(json.dumps({'status': value['status'], 'tests_run': value['tests_run'], 'proof': str(proof)}))
sys.exit(0 if passed else 1)
