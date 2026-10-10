"""Record exclusive synthetic proof; never run scientific phases or processes."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import dynamic_sequence as s
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,required=True);args=ap.parse_args()
    s.require(args.attempt>0,'positive exclusive attempt required')
    before={str(s.BASE/n):s.sha(s.BASE/n) for n in s.ORIGINAL}
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_dynamic_sequence.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    after={str(s.BASE/n):s.sha(s.BASE/n) for n in s.ORIGINAL}
    passed=result.wasSuccessful() and not result.skipped and before==after
    proof={'schema':'paper3-dynamic-delivery-synthetic-proof-v1','all_pass':passed,'tests_run':result.testsRun,
           'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
           'implementation_sha256':s.source_pins(),'original_source_sha256':after,'original_sources_unchanged':before==after,
           'models_statistics_delivery_executed':False,'actual_models_executed':False,'actual_processes_started_or_stopped':False,
           'real_outcomes_read':False,'actual_original_full_scientific_gate_executed':False,
           'synthetic_original_publisher_and_archive_zip_exercised':True,'production_backend_stop_poll_taskstream_schema_exercised':True,
           'python_executable':sys.executable,'recorded_utc':s.utc()}
    path=HERE/f'DYNAMIC_SEQUENCE_SYNTHETIC_TEST_RESULTS_ATTEMPT{args.attempt:03d}.json'
    s.emit(path,proof);print(json.dumps({'proof_path':str(path),'sha256':s.sha(path),'all_pass':passed,'tests_run':result.testsRun}),flush=True)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
