"""Synthetic supervisor tests. No real experiment/control/science child."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

SOURCE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('supervisor_test_subject', SOURCE/'transition_supervisor.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

def state(**changes):
    value = {'old_full_complete':False, 'old_failure':False, 'old_worker_alive':True,
        'existing_private_bytes':3*1024**3, 'free_commit_bytes':5*1024**3}
    value.update(changes);return value

class WaitTests(unittest.TestCase):
    def run_wait(self, values):
        observed=[];checks=[];sleeps=[];values=iter(values)
        result=s.resource_wait(lambda:next(values),observed.append,lambda:checks.append(True),sleeps.append)
        return result,observed,checks,sleeps
    def test_three_consecutive_samples(self):
        result,observed,checks,sleeps=self.run_wait([state()]*3)
        self.assertEqual(result,'RESOURCE_ADMISSION_READY');self.assertEqual(len(checks),3);self.assertEqual(len(sleeps),2)
    def test_low_memory_resets_counter(self):
        result,observed,_,_=self.run_wait([state(),state(free_commit_bytes=0),state(),state(),state()])
        self.assertEqual(len(observed),5);self.assertEqual(result,'RESOURCE_ADMISSION_READY')
    def test_old_completion_never_switches(self):
        self.assertEqual(self.run_wait([state(old_full_complete=True)])[0],'NOT_NEEDED_OLD_FULL_COMPLETED')
    def test_old_failure_blocks(self):
        with self.assertRaises(RuntimeError):self.run_wait([state(old_failure=True)])
    def test_disappeared_worker_blocks(self):
        with self.assertRaises(RuntimeError):self.run_wait([state(old_worker_alive=False)])
    def test_invalid_private_memory_blocks(self):
        with self.assertRaises(RuntimeError):self.run_wait([state(existing_private_bytes=0)])
    def test_source_change_blocks_before_sampling(self):
        def fail():raise RuntimeError('mutated')
        with self.assertRaises(RuntimeError):s.resource_wait(lambda:self.fail('sampled after mutation'),lambda x:None,fail)
    def test_large_worker_increases_budget(self):
        v=state(existing_private_bytes=5*1024**3,free_commit_bytes=5*1024**3)
        self.assertEqual(self.run_wait([v,state(old_full_complete=True)])[0],'NOT_NEEDED_OLD_FULL_COMPLETED')
    def test_policy_requires_three_samples(self):
        with self.assertRaises(RuntimeError):s.resource_wait(lambda:state(),lambda x:None,lambda:None,stable_samples=2)

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.root=SOURCE/'supervisor_synthetic_scratch'/uuid.uuid4().hex;self.root.mkdir(parents=True)
        self.record=self.root/'record';self.record.mkdir()
        self.transition=self.root/'transition_001';self.transition.mkdir()
        self.here=patch.object(s,'HERE',self.root);self.here.start()
        self.repo=patch.object(s,'REPO',self.root);self.repo.start()
        self.commands={k:[k,'synthetic-only'] for k in ('controller','continuation','finalizer')}
        self.launched=[]
    def tearDown(self):self.here.stop();self.repo.stop()
    def popen(self,command,**kwargs):
        kind=command[0];self.launched.append(kind)
        fixture=self
        class Child:
            pid=9000+len(fixture.launched)
            def poll(self):return None
            def wait(self):
                if kind=='controller':
                    (fixture.transition/'transition_gate.json').write_text(json.dumps({'status':'PASS','worker_count':2,'manifest_digest':s.MANIFEST}))
                elif kind=='finalizer':
                    path=fixture.root/'attempt001';path.mkdir();(path/'finish.json').write_text('{"status":"COMPLETED"}')
                return 0
        if kind=='continuation':
            path=self.root/'continuation_001';path.mkdir();(path/'start.json').write_text('{}')
        return Child()
    def test_flow_exactly_one_controller_continuation_finalizer(self):
        result=s.run_flow(self.commands,self.record,self.transition,lambda:None,popen=self.popen,sleep=lambda x:None)
        self.assertEqual(result,'AUTHORIZED_CONTINUATION_AND_DELIVERY_COMPLETED')
        self.assertEqual(self.launched,['controller','continuation','finalizer'])
    def test_failed_controller_never_launches_replacement(self):
        class Failed:
            pid=1
            def wait(self):return 1
        def spawn(command,**kwargs):self.launched.append(command[0]);return Failed()
        with self.assertRaises(RuntimeError):s.run_flow(self.commands,self.record,self.transition,lambda:None,popen=spawn)
        self.assertEqual(self.launched,['controller'])
    def test_missing_real_gate_blocks_continuation(self):
        class Empty:
            pid=1
            def wait(self):return 0
        with self.assertRaises(FileNotFoundError):s.run_flow(self.commands,self.record,self.transition,lambda:None,popen=lambda *a,**k:Empty())
        self.assertFalse((self.record/'continuation_launch.json').exists())
    def test_source_mutation_blocks_launch(self):
        with self.assertRaises(RuntimeError):s.run_flow(self.commands,self.record,self.transition,
            lambda:(_ for _ in ()).throw(RuntimeError('changed')),popen=lambda *a,**k:self.fail('child started'))
    def test_commands_keep_frozen_launcher_indirect(self):
        commands=s.commands('python311',self.root/'pins.json',self.transition)
        self.assertIn('--authorize-native-transition',commands['controller'])
        self.assertEqual(commands['continuation'][1:4],['-I','-S','-B'])
        self.assertFalse(any('run_p7_7_final.py' in token for cmd in commands.values() for token in cmd))
    def test_exclusive_journal_never_overwrites(self):
        path=self.record/'immutable.json';s.emit(path,{'old':True})
        with self.assertRaises(FileExistsError):s.emit(path,{'new':True})
        self.assertEqual(json.loads(path.read_text()),{'old':True})

def main():
    require=sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    assert require
    proof_path=SOURCE/s.PROOF_NAME;assert not proof_path.exists()
    names=('transition_supervisor.py','test_transition_supervisor.py')
    before={str(SOURCE/name):s.sha(SOURCE/name) for name in names}
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    after={str(SOURCE/name):s.sha(SOURCE/name) for name in names};assert before==after
    proof={'schema':'paper3-worker-transition-supervisor-synthetic-tests-v1',
        'status':'PASS' if result.wasSuccessful() else 'FAIL','all_pass':result.wasSuccessful(),
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'implementation_sha256':after,'finished_utc':s.utc(),'real_experiment_processes_controlled':False,
        'models_generators_or_statistics_executed':False,'synthetic_children_are_fake':True}
    with proof_path.open('x',encoding='utf-8') as stream:json.dump(proof,stream,indent=2);stream.write('\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
