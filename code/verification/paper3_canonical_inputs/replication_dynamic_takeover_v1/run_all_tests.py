"""Run all NEW cutover/route tests with synthetic fixtures; never model code."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'replication_dynamic_scheduler_v1'))
from queue_store import sha,exclusive_json,utc


def inventory():
    return {str(p.resolve()):sha(p) for p in HERE.glob('*.py')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,required=True)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise RuntimeError('requires -I -S -B')
    root=HERE/f'all_tests/attempt{args.attempt:03d}';root.mkdir(parents=True,exist_ok=False)
    fixtures=root/'fixtures';fixtures.mkdir();tempfile.tempdir=str(fixtures)
    before=inventory();start=utc();clock=time.monotonic()
    suite=unittest.TestLoader().discover(str(HERE),pattern='test_*.py')
    with (root/'test.log').open('x',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    imported=[name for name in sys.modules if name in ('torch','numpy','pandas','core') or name.startswith('core.')]
    after=inventory();ok=result.wasSuccessful() and not result.skipped and not imported and before==after
    receipt={'schema':'paper3-dynamic-cutover-route-synthetic-proof-v1','all_pass':ok,
             'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'started_utc':start,'finished_utc':utc(),'elapsed_seconds':time.monotonic()-clock,
             'actual_model_execution':False,'actual_generator_execution':False,'actual_process_control':False,
             'bootstrap_execution':False,'implementation_sha256':after,'source_inventory_unchanged':before==after,
             'forbidden_modules_imported':imported,'log_sha256':sha(root/'test.log')}
    exclusive_json(root,'results.json',receipt)
    print({'all_pass':ok,'tests_run':result.testsRun,'receipt':str(root/'results.json')})
    if not ok:
        print((root/'test.log').read_text(encoding='utf-8')[-18000:]);raise SystemExit(1)


if __name__=='__main__':main()
