"""Synthetic producer fixtures and readonly real smoke; no actual publication."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import types

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import metadata_recovery as R
E = R.make_api('paper3_boundary_tests_original')
FIX = R.verified_module(R.OLD/'test_metadata_erratum.py', 'paper3_boundary_tests_frozen_fixture',
    '0cc55daa5c4a2334cf9ff83ef178b7374aa6a12d62804618bd7575d60895d29c')

def replace(path, key, value):
    obj = E.read(path); obj[key] = value
    Path(path).write_text(json.dumps(obj), encoding='utf-8')

class BoundaryTests(unittest.TestCase):
    def fixture(self, mutate=None, stop=True):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root=Path(folder)/'smoke'; contract, digest=FIX.fixture(root)
            if stop:
                directory=root/'workers/DW0001'
                backend=object.__new__(FIX.C.FrozenProcessBackend)
                backend.records={'DW0001':{'root':directory,'seq':1,'done':1,
                    'contract_sha256':E.sha(directory/'contract.json')}}
                backend.stop('DW0001')
            if mutate: mutate(root, contract)
            return E.inspect_smoke(root,contract,digest,active=lambda pid:False)
    def rejected(self, mutate):
        with self.assertRaises((E.ErratumError, FileNotFoundError)):
            self.fixture(mutate)
    def test_completed_task_then_stop_accepted(self):
        value=self.fixture()
        self.assertEqual((value['started_workers'],value['trajectory_workers'],value['trajectory_tasks']),(2,1,1))
    def test_original_no_stop_fixture_still_accepted(self):
        self.assertEqual(self.fixture(stop=False)['trajectory_tasks'],1)
    def test_original_predicate_reproduces_failure(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root=Path(folder)/'smoke'; c,h=FIX.fixture(root);d=root/'workers/DW0001'
            FIX.Q.exclusive_json(d/'commands','000002.json',{'action':'STOP',
                'reason':'validated trajectory boundary; no inflight termination','contract_sha256':E.sha(d/'contract.json')})
            with self.assertRaisesRegex(E.ErratumError,'coverage differs'):
                E.original_inspect_smoke(root,c,h,active=lambda pid:False)
    def test_unknown_stop_reason_rejected(self):
        self.rejected(lambda r,c:replace(r/'workers/DW0001/commands/000002.json','reason','kill busy'))
    def test_stop_contract_mismatch_rejected(self):
        self.rejected(lambda r,c:replace(r/'workers/DW0001/commands/000002.json','contract_sha256','0'*64))
    def test_extra_stop_rejected(self):
        def mutate(r,c):
            d=r/'workers/DW0001/commands';(d/'000003.json').write_bytes((d/'000002.json').read_bytes())
        self.rejected(mutate)
    def test_idle_stop_missing_rejected(self):
        self.rejected(lambda r,c:(r/'workers/DW0002/commands/000001.json').unlink())
    def test_sequence_gap_rejected(self):
        self.rejected(lambda r,c:(r/'workers/DW0001/commands/000002.json').rename(r/'workers/DW0001/commands/000003.json'))
    def test_done_absent_rejected(self):
        def mutate(r,c):
            next((r/'workers/DW0001/events').glob('*.done.json')).unlink()
        self.rejected(mutate)
    def test_nonzero_trajectory_exit_rejected(self):
        self.rejected(lambda r,c:replace(r/'workers/DW0001/actual_exit.json','actual_exit_code',7))
    def test_bool_exit_rejected(self):
        self.rejected(lambda r,c:replace(r/'workers/DW0001/actual_exit.json','actual_exit_code',False))
    def test_extra_idle_task_rejected(self):
        def mutate(r,c):
            d=r/'workers/DW0002/commands';v=E.read(r/'workers/DW0001/commands/000001.json')
            v['contract_sha256']=E.sha(r/'workers/DW0002/contract.json');v['worker_id']='DW0002'
            (d/'000001.json').write_text(json.dumps(v));FIX.Q.exclusive_json(d,'000002.json',
                {'action':'STOP','reason':'validated trajectory boundary; no inflight termination','contract_sha256':v['contract_sha256']})
        self.rejected(mutate)
    def test_finished_summary_mismatch_rejected(self):
        self.rejected(lambda r,c:replace(r/'workers/DW0001/finished.json','summary',{'assigned_tasks':2,'completed_tasks':1}))
    def test_only_exact_one_predicate_transformed(self):
        t=E.boundary_transform
        self.assertTrue(t['all_other_function_source_identical'])
        self.assertNotEqual(t['original_function_sha256'],t['adapted_function_sha256'])
        self.assertEqual(t['original_source_sha256'],R.OLD_SOURCE_SHA)
    def test_transformation_uses_same_verified_bytes_without_reread(self):
        fresh=R.verified_module(R.OLD_SOURCE,'paper3_boundary_no_second_read',R.OLD_SOURCE_SHA)
        with mock.patch.object(R,'verified_module',return_value=fresh), \
             mock.patch.object(Path,'read_bytes',side_effect=AssertionError('second unverified read')):
            fixed=R.make_api('unused_synthetic_module')
        self.assertEqual(fixed.boundary_transform,E.boundary_transform)
    def test_actual_known_external_interpreter_binding(self):
        path=HERE/'root_erratum_launch003.py'
        launcher=R.verified_module(path,'paper3_boundary_launcher_preflight',E.sha(path))
        self.assertEqual(launcher.preflight_interpreter(E),launcher.PYTHON.resolve())
    def test_real_boundary_metadata_readonly(self):
        R.check_real_smoke(E);R.check_failures(E)
        old=E.read(R.OLD_PLAN);v=E.read(old['v1_plan_path']);sm=E.read(v['smoke_certificate_path'])
        sc=E.read(sm['contract']['path'])
        out=E.inspect_smoke(R.SMOKE,sc,sm['contract']['sha256'],active=E.process_active)
        self.assertEqual((out['started_workers'],out['trajectory_workers'],out['trajectory_tasks']),(2,1,1))
        self.assertEqual([row['actual_exit_code'] for row in out['workers']],[0,0])
    def test_real_byte_pin_disallows_disappearing_stop(self):
        self.assertEqual(R.SMOKE_PINS['workers/DW0001/commands/000002.json'],
                         E.sha(R.SMOKE/'workers/DW0001/commands/000002.json'))
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            missing=Path(folder)/'missing.json'
            with self.assertRaises(E.ErratumError):E.bound(missing,R.SMOKE_PINS['workers/DW0001/commands/000002.json'])

def main():
    before=R.source_pins(E)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    after=R.source_pins(E)
    E.require(before==after,'recovery source changed during tests')
    proof={'schema':'paper3-boundary-stop-recovery-test-proof-v1','all_pass':result.wasSuccessful(),
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'source_sha256':before,'boundary_transform':E.boundary_transform,
        'models_statistics_real_publication_or_process_control':False,
        'real_smoke_metadata_readonly_pass':result.wasSuccessful(),'observed_utc':E.utc()}
    E.emit(R.PROOF,proof)
    print(json.dumps(proof,sort_keys=True),flush=True)
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    raise SystemExit(main())
