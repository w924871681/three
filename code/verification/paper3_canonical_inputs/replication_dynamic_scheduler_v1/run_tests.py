"""Execute ONLY independent synthetic tests; publish truthful exclusive evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE/'tests'))
from queue_store import exclusive_json,sha,utc

def inventory():
    return {str(path.resolve()):sha(path) for path in sorted(HERE.rglob('*.py'))
            if 'synthetic_tests' not in path.relative_to(HERE).parts}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',type=int,required=True)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('test launcher requires -I -S -B')
    if args.attempt<1:raise RuntimeError('positive exclusive attempt required')
    root=HERE/f'synthetic_tests/attempt{args.attempt:03d}';root.mkdir(parents=True,exist_ok=False)
    fixtures=root/'temporary_fixtures';fixtures.mkdir();tempfile.tempdir=str(fixtures)
    sys._paper3_dynamic_test_artifact_root=str(root)
    before=inventory();started=utc();clock=time.monotonic()
    suite=unittest.TestLoader().discover(str(HERE/'tests'),pattern='test_*.py')
    with (root/'test.log').open('x',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    after=inventory()
    forbidden=[name for name in sys.modules if name=='torch' or name=='numpy' or name=='pandas' or name.startswith('core.')]
    all_pass=result.wasSuccessful() and not result.skipped and not forbidden and before==after
    proof={'schema':'paper3-dynamic-synthetic-test-proof-v1','all_pass':all_pass,
           'started_utc':started,'finished_utc':utc(),'elapsed_seconds':time.monotonic()-clock,
           'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
           'failure_details':[(str(t),error) for t,error in result.failures],
           'error_details':[(str(t),error) for t,error in result.errors],
           'skip_details':[(str(t),reason) for t,reason in result.skipped],
           'actual_model_execution':False,'actual_generator_execution':False,'bootstrap_execution':False,
           'model_runtime_verification':'NOT_EXECUTED','production_activation':'NOT_EXECUTED',
           'forbidden_modules_imported':forbidden,'implementation_sha256':after,'source_inventory_unchanged':before==after,
           'test_log_sha256':sha(root/'test.log'),'real_subprocesses_are_synthetic_fixtures_only':True,
           'real_process_sample_time_is_virtual_in_tests':True}
    exclusive_json(root,'results.json',proof)
    print(json.dumps({'all_pass':all_pass,'tests_run':result.testsRun,'failures':len(result.failures),
          'errors':len(result.errors),'skips':len(result.skipped),'receipt':str(root/'results.json')}))
    if not all_pass:
        print((root/'test.log').read_text(encoding='utf-8')[-14000:]);sys.exit(1)

if __name__=='__main__':main()
