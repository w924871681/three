"""Run synthetic-only 002 launcher tests and save an exclusive receipt."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
names = ('sequenced_supervisor_002.py', 'tests_sequenced_supervisor_002.py', 'run_sequenced_002_tests.py', 'durable_supervisor.py')
pins = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names}
spec = importlib.util.spec_from_file_location('owned_test_sequenced_002', HERE / 'tests_sequenced_supervisor_002.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
log = HERE / 'SEQUENCED_SUPERVISOR_002_TEST_RESULTS_001.log'
with log.open('x', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
unchanged = all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest for name, digest in pins.items())
passed = result.wasSuccessful() and not result.skipped and unchanged
record = {'schema': 'paper3-sequenced-supervisor-002-synthetic-test-receipt-v1',
          'finished_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS' if passed else 'FAIL',
          'all_pass': passed, 'tests_run': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'skipped': len(result.skipped), 'exit_code': 0 if passed else 1,
          'source_sha256': pins, 'sources_unchanged_during_tests': unchanged,
          'test_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
          'real_processes_launched': False, 'scientific_modules_imported': False,
          'models_generators_statistics_executed': False, 'real_environment_hashed': False,
          'scope': 'Synthetic files, mocked Windows process inactivity and mocked Popen only; no experimental process launch.'}
receipt = HERE / 'SEQUENCED_SUPERVISOR_002_TEST_RESULTS_001.json'
with receipt.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps(record))
sys.exit(record['exit_code'])
