import copy
import json
from pathlib import Path
import tempfile
import unittest
from queue_store import QueueStore, IntegrityError, canonical, exclusive_json, read_json, sha, task_stem, verify_journal
from fixtures import tasks

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bindings={'manifest':'A','input':'F1'}
        self.queue=QueueStore(self.root/'queue',tasks(10),self.bindings)
    def tearDown(self):self.tmp.cleanup()
    def proof(self,claim):return {'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':'1'*64,'output_hash':'2'*64}
    def test_exclusive_controller(self):
        with self.assertRaises(FileExistsError):QueueStore(self.root/'queue',tasks(10),self.bindings)
    def test_all_claims_unique_across_three_workers(self):
        claimed=[]
        while self.queue.pending:
            batch=[(worker,self.queue.claim(worker)) for worker in ('DW0001','DW0002','DW0003')]
            for worker,claim in batch:
                if claim:claimed.append(claim['task_digest']);self.queue.finish(worker,claim['claim_id'],self.proof(claim))
        self.assertEqual(len(claimed),len(set(claimed)));self.assertEqual(verify_journal(self.queue.root)['complete'],10)
    def test_busy_worker_cannot_claim_again(self):
        self.queue.claim('DW0001')
        with self.assertRaises(IntegrityError):self.queue.claim('DW0001')
    def test_no_other_worker_can_finish_claim(self):
        claim=self.queue.claim('DW0001')
        with self.assertRaises(IntegrityError):self.queue.finish('DW0002',claim['claim_id'],self.proof(claim))
    def test_completion_cannot_use_another_task_digest(self):
        claim=self.queue.claim('DW0001');proof=self.proof(claim);proof['task_digest']='3'*64
        with self.assertRaises(IntegrityError):self.queue.finish('DW0001',claim['claim_id'],proof)
    def test_no_completion_on_csv_appearance_without_valid_proof(self):
        claim=self.queue.claim('DW0001');proof=self.proof(claim);proof['validated']=False
        with self.assertRaises(IntegrityError):self.queue.finish('DW0001',claim['claim_id'],proof)
    def test_retire_requires_boundary(self):
        claim=self.queue.claim('DW0001')
        with self.assertRaises(IntegrityError):self.queue.boundary_retire('DW0001')
        self.queue.finish('DW0001',claim['claim_id'],self.proof(claim));self.queue.boundary_retire('DW0001')
    def test_interrupted_claim_never_recycled(self):
        claim=self.queue.claim('DW0001');self.queue.stop('external disappearance',worker_id='DW0001',claim_id=claim['claim_id'])
        with self.assertRaises(IntegrityError):self.queue.claim('DW0002')
        self.assertEqual(self.queue.states[task_stem(claim['task'])],'CLAIMED')
        self.assertTrue(verify_journal(self.queue.root)['stopped'])
    def test_mutated_task_or_provenance_breaks_journal(self):
        self.queue.claim('DW0001');path=self.queue.root/'journal/000002.json'
        value=read_json(path);value['body']['task']['seed']=7312;path.write_text(json.dumps(value))
        with self.assertRaises(IntegrityError):verify_journal(self.queue.root)
    def test_wrong_historical_claim_id_rejected_on_replay(self):
        first=self.queue.claim('DW0001');self.queue.finish('DW0001',first['claim_id'],self.proof(first))
        second=self.queue.claim('DW0001');self.queue.finish('DW0001',second['claim_id'],self.proof(second))
        path=self.queue.root/'journal/000005.json';value=read_json(path);value['body']['claim_id']=first['claim_id'];path.write_text(json.dumps(value))
        with self.assertRaises(IntegrityError):verify_journal(self.queue.root)
    def test_existing_publication_never_overwritten(self):
        exclusive_json(self.root,'immutable.json',{'x':1})
        with self.assertRaises(IntegrityError):exclusive_json(self.root,'immutable.json',{'x':2})
        self.assertEqual(read_json(self.root/'immutable.json'),{'x':1})
    def test_path_escape_rejected(self):
        with self.assertRaises(IntegrityError):exclusive_json(self.root,'../escape.json',{})
    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for index,value in enumerate(('{"a":1,"a":2}','{"a":NaN}')):
            path=self.root/f'bad{index}.json';path.write_text(value)
            with self.assertRaises(IntegrityError):read_json(path)
    def test_method_configuration_mapping_frozen(self):
        task=tasks(1)[0];task['config_id']='B8_AlwaysOpen_ratio10'
        with self.assertRaises(IntegrityError):task_stem(task)
    def test_already_complete_never_dispatched(self):
        task=tasks(1)[0];queue=QueueStore(self.root/'other',tasks(1),self.bindings,already_complete=[task_stem(task)])
        self.assertIsNone(queue.claim('DW0001'));self.assertEqual(queue.complete,1)

if __name__=='__main__':unittest.main()
