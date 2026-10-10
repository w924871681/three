"""Exclusive synthetic proof recorder; no real model/statistics/publication."""
import argparse
import json
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import metadata_erratum as e
def pins():
    out={str(e.V1/n):e.sha(e.V1/n) for n in e.V1_PINS}
    out[str(e.BASE/'replication_abrupt_recovery_v1/finalizer.py')]=e.sha(e.BASE/'replication_abrupt_recovery_v1/finalizer.py')
    out[str(e.BASE/'replication_delivery_env_v3/delivery.py')]=e.sha(e.BASE/'replication_delivery_env_v3/delivery.py');return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,required=True);a=ap.parse_args();e.require(a.attempt>0,'positive proof attempt required')
    fixture=e.BASE/'replication_delivery_env_v3/test_delivery.py'
    before={**pins(),**e.scheduler_pins(),**e.own_pins(),str(fixture):e.sha(fixture)};suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_metadata_erratum.py');result=unittest.TextTestRunner(verbosity=2).run(suite);after={**pins(),**e.scheduler_pins(),**e.own_pins(),str(fixture):e.sha(fixture)}
    passed=result.wasSuccessful() and not result.skipped and before==after
    proof={'schema':'paper3-smoke-count-erratum-synthetic-proof-v1','all_pass':passed,'tests_run':result.testsRun,'failures':len(result.failures),
           'errors':len(result.errors),'skipped':len(result.skipped),'implementation_sha256':e.own_pins(),
           'original_finalizer_sha256':e.ORIGINAL_FINALIZER,'original_delivery_sha256':e.ORIGINAL_DELIVERY,'v1_source_sha256':e.V1_PINS,
           'scheduler_source_sha256':e.scheduler_pins(),
           'original_delivery_fixture_sha256':e.sha(fixture),
           'original_and_v1_sources_unchanged':before==after,'actual_models_statistics_publication_or_process_control':False,
           'real_outcomes_read':False,'actual_smoke_receipts_read_by_tests':False,'synthetic_original_repack_archive_zip_exercised':True,
           'synthetic_original_backend_poll_stop_and_taskstream_exercised':True,'recorded_utc':e.utc(),'python_executable':sys.executable}
    path=HERE/f'SMOKE_COUNT_ERRATUM_SYNTHETIC_TEST_RESULTS_ATTEMPT{a.attempt:03d}.json';e.emit(path,proof)
    print(json.dumps({'all_pass':passed,'tests_run':result.testsRun,'proof_path':str(path),'sha256':e.sha(path)}),flush=True);return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
