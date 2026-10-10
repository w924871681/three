"""Record actual synthetic consumer regression counts; launch no experiments."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

HERE = Path(__file__).resolve().parent
OWN = ('strict_legacy_proof_adapter.py', 'tests_strict_legacy_proof_adapter.py', 'run_strict_legacy_proof_adapter_tests.py')
pins = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in OWN}
started = datetime.now(timezone.utc).isoformat()
spec = importlib.util.spec_from_file_location('owned_strict_legacy_adapter_test_suite', HERE / 'tests_strict_legacy_proof_adapter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_temp = tempfile.TemporaryDirectory
scratch = HERE / 'synthetic_scratch'
scratch.mkdir(exist_ok=True)
def owned_temp(*args, **kwargs):
    # Redirect original regression temporary fixtures into this new directory.
    if 'dir' in kwargs and Path(kwargs['dir']) == module.RECOVERY / 'continuation_synthetic_scratch':
        kwargs['dir'] = scratch
    return original_temp(*args, **kwargs)
log = HERE / 'STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.log'
with patch.object(tempfile, 'TemporaryDirectory', side_effect=owned_temp), log.open('x', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(module.suite())
unchanged = all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest for name, digest in pins.items())
passed = result.wasSuccessful() and not result.skipped and unchanged
record = {'schema': module.a.PROOF_SCHEMA, 'status': 'PASS' if passed else 'FAIL', 'all_pass': passed,
          'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'exit_code': 0 if passed else 1,
          'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
          'implementation_sha256': pins, 'sources_unchanged_during_tests': unchanged,
          'original_finalizer_sha256': module.a.ORIGINAL_SHA,
          'original_verify_function_sha256': module.a.ORIGINAL_FUNCTION_SHA,
          'legacy_original_receipt_sha256': module.a.LEGACY_RECEIPT_SHA,
          'original_regression_test_source_sha256': module.a.sha(module.RECOVERY / 'test_continuation.py'),
          'test_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
          'real_experimental_outcomes_read': False, 'real_experiment_processes_launched': False,
          'models_generators_statistics_executed': False, 'real_environment_hashed': False,
          'regression_binding_guard': 'explicit synthetic fixture mock only; production binding tested separately',
          'scope': 'Original metadata consumer tests with adapted private module plus strict legacy/binding cases; synthetic filesystem fixtures only.'}
with (HERE / module.a.PROOF_NAME).open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps(record))
sys.exit(record['exit_code'])
