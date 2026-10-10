from dataclasses import asdict
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import time
import unittest
from coordinator import DynamicCoordinator,validate_activation
from dynamic_policy import GIB,PolicyConfig,ResourceSample,WorkerObservation
from fixtures import tasks
from queue_store import QueueStore,IntegrityError,canonical,exclusive_json,read_json,sha,verify_journal


class SandboxBackend:
    """Real persistent subprocess transport; all calculations are TEST hash fixtures."""
    def __init__(self,root,delay=.12):self.root=root;self.delay=delay;self.items={};self.stops=[];self.assignments=[]
    def start(self,identity):
        directory=self.root/identity;directory.mkdir();contract='a'*64
        process=subprocess.Popen([sys.executable,'-I','-S','-B',str(Path(__file__).with_name('synthetic_process.py')),
            str(directory),str(self.delay),contract],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.items[identity]={'root':directory,'process':process,'seq':0,'done':0,'ready':False,'exit':False,'contract':contract}
    def _command(self,identity,value):
        item=self.items[identity];item['seq']+=1
        exclusive_json(item['root'],f"commands/{item['seq']:06d}.json",{**value,'contract_sha256':item['contract']})
    def assign(self,identity,claim):self.assignments.append((identity,claim));self._command(identity,{'action':'TASK',**claim})
    def stop(self,identity):
        item=self.items[identity]
        if item['seq']!=item['done']:raise AssertionError('attempted to stop an in-flight fixture')
        self.stops.append(identity);self._command(identity,{'action':'STOP'})
    def poll(self,identity):
        item=self.items[identity];events=[];root=item['root']
        if (root/'ready.json').exists() and not item['ready']:item['ready']=True;events.append({'type':'READY'})
        path=root/f"events/{item['done']+1:06d}.done.json"
        if path.exists():item['done']+=1;events.append({'type':'DONE',**read_json(path)})
        code=item['process'].poll()
        if code is not None and not item['exit']:
            item['exit']=True;finished=root/'finished.json'
            valid=finished.exists() and read_json(finished).get('finished_at_idle_boundary') is True
            events.append({'type':'EXIT','exit_code':code,'finished_validated':valid})
            item['process'].communicate(timeout=2)
        return events
    def observe(self,identity,phase):return WorkerObservation(identity,phase,100*1024**2,150*1024**2,80*1024**2,90*1024**2)
    def validate(self,identity,claim,event):
        expected=hashlib.sha256(claim['task_digest'].encode()).hexdigest()
        if event['task_digest']!=claim['task_digest'] or event['receipt_sha256']!=expected:raise IntegrityError('fixture bytes differ')
        return {'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':expected,'output_hash':expected}
    def drain_fixtures_for_test_cleanup(self):
        # Only TEST subprocesses. No terminate/kill and no project process access.
        for identity,item in self.items.items():
            if item['process'].poll() is None:
                self._command(identity,{'action':'STOP'})
        for item in self.items.values():
            if item['process'].poll() is None:item['process'].communicate(timeout=15)


class MemoryBackend:
    def __init__(self):self.events={};self.started=[];self.stopped=[];self.assigned=[]
    def start(self,identity):self.started.append(identity);self.events[identity]=[{'type':'READY'}]
    def stop(self,identity):self.stopped.append(identity)
    def assign(self,identity,claim):self.assigned.append((identity,claim))
    def observe(self,identity,phase):return WorkerObservation(identity,phase,1,1,1,1)
    def poll(self,identity):result=self.events[identity];self.events[identity]=[];return result
    def validate(self,identity,claim,event):return {'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':'1'*64,'output_hash':'2'*64}


class CoordinatorTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def sample(self,tick,free=16*GIB):return ResourceSample(tick,free,32*GIB,free if free<16*GIB else 8*GIB,16*GIB)
    def test_real_persistent_processes_automatically_grow_and_retire(self):
        backend=SandboxBackend(self.root);ledger=QueueStore(self.root/'queue',tasks(45),{'synthetic_only':True})
        coordinator=DynamicCoordinator(ledger,backend);now=0;counts=[];saw_three=False;saw_retirement_to_one=False
        try:
            for step in range(1800):
                now+=10_000
                count=len(coordinator.workers)
                if count>=3:saw_three=True
                if saw_three and count==1:saw_retirement_to_one=True
                free=16*GIB if not saw_three else (2*GIB if saw_retirement_to_one else GIB//2)
                status=coordinator.tick(self.sample(now,free),now_ms=now);counts.append(status['active_workers'])
                if status['all_finished']:break
                time.sleep(.01)
            self.assertTrue(status['all_finished']);self.assertTrue(saw_three);self.assertTrue(saw_retirement_to_one)
            self.assertEqual(ledger.complete,45);self.assertEqual(len({c['task_digest'] for _,c in backend.assignments}),45)
            self.assertGreaterEqual(len(backend.stops),3)
            self.assertTrue(all(item['process'].returncode==0 for item in backend.items.values()))
            self.assertEqual(verify_journal(ledger.root)['complete'],45)
            exclusive_json(ledger.root,'REAL_SYNTHETIC_SUBPROCESS_LIFECYCLE.json',{'synthetic_only':True,
                'observed_worker_counts':counts,'task_count':45,'dynamic_growth_to_three':saw_three,
                'dynamic_retirement_to_one':saw_retirement_to_one,'model_executed':False})
            artifact_root=getattr(sys,'_paper3_dynamic_test_artifact_root',None)
            if artifact_root is not None:
                shutil.copytree(self.root,Path(artifact_root)/'real_synthetic_process_lifecycle')
        finally:backend.drain_fixtures_for_test_cleanup()
    def test_pressure_does_not_kill_busy_worker(self):
        backend=MemoryBackend();ledger=QueueStore(self.root/'queue',tasks(2),{});coordinator=DynamicCoordinator(ledger,backend)
        for now in (0,10_000,20_000,30_000):coordinator.tick(self.sample(now),now_ms=now)
        self.assertEqual(len(backend.assigned),1)
        for now in (40_000,50_000,60_000,80_000,90_000):coordinator.tick(self.sample(now,GIB//2),now_ms=now)
        self.assertEqual(backend.stopped,[]);self.assertEqual(len(backend.assigned),1)
    def test_unexpected_exit_stops_dispatch_without_requeue(self):
        backend=MemoryBackend();ledger=QueueStore(self.root/'queue',tasks(2),{});coordinator=DynamicCoordinator(ledger,backend)
        for now in (0,10_000,20_000,30_000):coordinator.tick(self.sample(now),now_ms=now)
        backend.events['DW0001']=[{'type':'EXIT','exit_code':1,'finished_validated':False}]
        with self.assertRaises(IntegrityError):coordinator.tick(self.sample(40_000),now_ms=40_000)
        self.assertTrue(ledger.stopped);self.assertEqual(len(ledger.active),1);self.assertEqual(backend.stopped,[])
    def test_wrong_done_claim_stops_coordinator(self):
        backend=MemoryBackend();ledger=QueueStore(self.root/'queue',tasks(2),{});coordinator=DynamicCoordinator(ledger,backend)
        for now in (0,10_000,20_000,30_000):coordinator.tick(self.sample(now),now_ms=now)
        backend.events['DW0001']=[{'type':'DONE','claim_id':'WRONG'}]
        with self.assertRaises(IntegrityError):coordinator.tick(self.sample(40_000),now_ms=40_000)
        self.assertTrue(ledger.stopped)
    def test_missing_takeover_gate_fails_before_backend_creation(self):
        contract={'schema':'paper3-dynamic-run-contract-v1','activation_gate_path':str(self.root/'MISSING.json'),
                  'activation_gate_sha256':'a'*64}
        with self.assertRaises(FileNotFoundError):validate_activation(contract,active_process=lambda pid:True)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_live_original_producer_prevents_activation(self):
        gate={'schema':'paper3-dynamic-takeover-gate-v1','status':'PASS','old_owners_quiescent':True,
              'delivery_route_certified':True,'old_process_ids':list(range(1,9))}
        exclusive_json(self.root,'gate.json',gate)
        contract={'schema':'paper3-dynamic-run-contract-v1','activation_gate_path':str(self.root/'gate.json'),
                  'activation_gate_sha256':sha(self.root/'gate.json')}
        with self.assertRaises(IntegrityError):validate_activation(contract,active_process=lambda pid:True)
    def test_synthetic_proof_cannot_replace_real_model_smoke(self):
        source=self.root/'source.py';source.write_text('# SYNTHETIC')
        sources={str(source):sha(source)}
        proof={'schema':'paper3-dynamic-synthetic-test-proof-v1','all_pass':True,'actual_model_execution':False,
               'model_runtime_verification':'NOT_EXECUTED','tests_run':1,'failures':0,'errors':0,'skipped':0,
               'implementation_sha256':sources}
        exclusive_json(self.root,'proof.json',proof)
        gate={'schema':'paper3-dynamic-takeover-gate-v1','status':'PASS','old_owners_quiescent':True,
              'delivery_route_certified':True,'old_process_ids':list(range(1,9)),
              'manifest_digest':'m','input_bundle_digest':'f1','sidecar_digest':canonical(sources),
              'source_extension_scope':'ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256'}
        exclusive_json(self.root,'gate.json',gate)
        contract={'schema':'paper3-dynamic-run-contract-v1','execution_mode':'FULL',
                  'activation_gate_path':str(self.root/'gate.json'),'activation_gate_sha256':sha(self.root/'gate.json'),
                  'sourceproof_path':str(self.root/'proof.json'),'sourceproof_sha256':sha(self.root/'proof.json'),
                  'manifest_digest':'m','input_bundle_digest':'f1','sidecar_sources':sources,'sidecar_digest':canonical(sources)}
        with self.assertRaisesRegex(IntegrityError,'real bridge smoke'):validate_activation(contract,active_process=lambda pid:False)

if __name__=='__main__':unittest.main()
