"""Synthetic-only proof recorder. The child runs unittest in temporary fixtures."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('metadata_successor_test_recorder', ROOT / 'successor.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def main():
    s.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'requires -I -S -B')
    s.require(ROOT == s.safe(s.REPO, s.SELF_REL) and Path(sys.executable) == s.PYTHON,
              'wrong synthetic harness runtime/source')
    source_pins = {name: s.sha(ROOT / name) for name in s.OWN_NAMES}
    before = {str(s.safe(s.REPO, rel)): s.sha(s.safe(s.REPO, rel)) for rel in
              (s.RECOVERY_REL + '/finalizer.py', s.RECOVERY_REL + '/continuation.py',
               s.ORIGINAL_DELIVERY_REL + '/delivery.py')}
    started = s.utc()
    command = [str(s.PYTHON), '-I', '-S', '-B', str(ROOT / 'test_successor.py')]
    out_path, err_path = ROOT / 'SYNTHETIC_STDOUT_ATTEMPT002.log', ROOT / 'SYNTHETIC_STDERR_ATTEMPT002.log'
    with out_path.open('xb') as out, err_path.open('xb') as err:
        code = subprocess.call(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    after = {name: s.sha(name) for name in before}
    test_spec = importlib.util.spec_from_file_location('metadata_successor_test_count', ROOT / 'test_successor.py')
    test_module = importlib.util.module_from_spec(test_spec)
    test_spec.loader.exec_module(test_module)
    count = unittest.defaultTestLoader.loadTestsFromModule(test_module).countTestCases()
    text = err_path.read_text(encoding='utf-8')
    passed = code == 0 and before == after and source_pins == {name: s.sha(ROOT / name) for name in s.OWN_NAMES}
    value = {'schema': 'paper3-delivery-successor-synthetic-tests-v1', 'status': 'PASS' if passed else 'FAIL',
             'all_pass': passed, 'exit_code': code, 'tests_run': count,
             'failures': 0 if passed else None, 'errors': 0 if passed else None,
             'skipped': 0 if 'skipped=' not in text else None,
             'started_utc': started, 'finished_utc': s.utc(), 'command': command,
             'implementation_sha256': source_pins, 'original_source_sha256_before': before,
             'original_source_sha256_after': after, 'real_outcomes_read': False,
             'real_delivery_published': False, 'models_generators_or_statistics_executed': False,
             'real_processes_stopped_or_started': False,
             'stdout_sha256': s.sha(out_path), 'stderr_sha256': s.sha(err_path)}
    s.emit(ROOT / s.PROOF_NAME, value)
    print('synthetic_tests=' + str(count) + '; all_pass=' + str(passed))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
