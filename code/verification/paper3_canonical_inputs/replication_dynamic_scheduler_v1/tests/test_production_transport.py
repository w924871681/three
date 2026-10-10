"""Exercise actual bridge TaskStream + actual process-backend message schemas.

Popen and method execution are explicit in-process test doubles. No model is
loaded. These tests specifically prevent separately passing interfaces from
disagreeing over production READY/DONE/STOP/finished fields.
"""
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from coordinator import DynamicCoordinator,FrozenProcessBackend,Worker
from dynamic_policy import GIB,PolicyConfig,ResourceSample,WorkerObservation
import frozen_bridge as bridge
from fixtures import tasks
from queue_store import QueueStore,canonical,read_json

class FakePopen:
    def __init__(self):self.returncode=None;self.pid=1
    def poll(self):return self.returncode

class ProductionTransportTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def harness(self,mode='FULL'):
        task=tasks(1)[0];worker_root=self.root/'workers/DW0001';worker_root.mkdir(parents=True)
        contract={'eligible_tasks':[task],'execution_mode':mode};digest='a'*64
        backend=FrozenProcessBackend(contract,self.root,None);process=FakePopen()
        backend.records['DW0001']={'root':worker_root,'process':process,'log':io.BytesIO(),'seq':0,'done':0,
            'ready':False,'exit':False,'actual_pid':1,'peaks':(0,0),'contract_sha256':digest}
        backend.observe=lambda worker_id,phase:WorkerObservation(worker_id,phase,1,1,1,1)
        backend.validate=lambda worker_id,claim,event:{'validated':True,'task_digest':claim['task_digest'],
            'receipt_sha256':event['receipt_sha256'],'output_hash':event['output_sha256']}
        ledger=QueueStore(self.root/'queue',[task],{'synthetic_only':True})
        coordinator=DynamicCoordinator(ledger,backend,PolicyConfig(max_workers=1))
        coordinator.workers['DW0001']=Worker('DW0001')
        bridge.publish(worker_root,'ready.json',{'pid':1,'contract_sha256':digest})
        stream=bridge.TaskStream(worker_root,'DW0001',contract,digest,
            lambda task:{'receipt_relative':'SYNTHETIC','receipt_sha256':'1'*64,'output_sha256':'2'*64})
        return coordinator,backend,process,stream,worker_root,task,digest
    def sample(self,now):return ResourceSample(now,16*GIB,32*GIB,8*GIB,16*GIB)
    def finish_schema(self,root,digest):bridge.publish(root,'finished.json',{
        'schema':'paper3-dynamic-worker-finished-v1','contract_sha256':digest,
        'original_trajectories_returned_after_full_checks':True})
    def test_real_done_stop_finished_schema_crosses_both_interfaces(self):
        coordinator,backend,process,stream,root,task,digest=self.harness()
        coordinator.tick(self.sample(0),now_ms=0)
        self.assertEqual(next(stream),task);self.assertFalse((root/'events/000001.done.json').exists())
        errors=[]
        def resume_after_original_method_publication():
            try:next(stream)
            except StopIteration:pass
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=resume_after_original_method_publication);thread.start()
        for _ in range(100):
            if (root/'events/000001.done.json').exists():break
            time.sleep(.005)
        try:
            coordinator.tick(self.sample(10_000),now_ms=10_000)
        finally:
            if not (root/'commands/000002.json').exists():backend.stop('DW0001')
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(read_json(root/'commands/000002.json')['action'],'STOP')
        self.finish_schema(root,digest);process.returncode=0
        status=coordinator.tick(self.sample(20_000),now_ms=20_000)
        self.assertTrue(status['all_finished']);self.assertEqual(coordinator.ledger.complete,1)
        exit_receipt=read_json(root/'actual_exit.json')
        self.assertEqual(exit_receipt['actual_exit_code'],0)
        self.assertTrue(exit_receipt['finished_validated'])
        self.assertEqual(exit_receipt['contract_sha256'],digest)
    def test_nonzero_owned_exit_is_preserved_and_not_accepted(self):
        coordinator,backend,process,stream,root,task,digest=self.harness()
        process.returncode=37
        events=backend.poll('DW0001')
        self.assertEqual(events[-1]['exit_code'],37)
        self.assertFalse(events[-1]['finished_validated'])
        self.assertEqual(read_json(root/'actual_exit.json')['actual_exit_code'],37)
    def test_one_task_smoke_done_and_exit_in_same_poll_is_valid(self):
        coordinator,backend,process,stream,root,task,digest=self.harness('BRIDGE_SMOKE')
        coordinator.tick(self.sample(0),now_ms=0);self.assertEqual(next(stream),task)
        with self.assertRaises(StopIteration):next(stream)
        self.finish_schema(root,digest);process.returncode=0
        status=coordinator.tick(self.sample(10_000),now_ms=10_000)
        self.assertTrue(status['all_finished']);self.assertEqual(coordinator.ledger.complete,1)
    def test_old_or_incomplete_finished_field_does_not_pass(self):
        coordinator,backend,process,stream,root,task,digest=self.harness()
        bridge.publish(root,'finished.json',{'contract_sha256':digest,'original_checks_completed':True})
        process.returncode=0
        events=backend.poll('DW0001')
        self.assertFalse(events[-1]['finished_validated'])
    def test_bridge_publication_complete_before_visible_and_no_overwrite(self):
        coordinator,backend,process,stream,root,task,digest=self.harness()
        value={'long':'x'*100000}
        bridge.publish(root,'complete.json',value)
        self.assertEqual(read_json(root/'complete.json'),value)
        with self.assertRaises(FileExistsError):bridge.publish(root,'complete.json',{})

if __name__=='__main__':unittest.main()
