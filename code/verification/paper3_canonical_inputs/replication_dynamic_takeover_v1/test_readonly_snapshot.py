"""Explicit synthetic cutover fixtures; no model or generator imports."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent/'replication_dynamic_scheduler_v1/tests'))
import readonly_snapshot as module
from fixtures import tasks,saved_fixture,rng_fixture,expected
from queue_store import canonical,exclusive_json,sha,task_stem


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.task=tasks(1)[0];self.expect=expected(self.task)
        self.manifest={'manifest_digest':self.expect['manifest_digest'],
                       'input_bundle_digest':self.expect['input_bundle_digest'],
                       'environment_binding':self.expect['environment_binding'],
                       'critical_files_sha256':{},'executor_sha256':{},'input_files_sha256':{},
                       'paths':{'executor_root':str(self.root),'input_run':str(self.root)},
                       'stage_b_bindings':{}}
        for name in ('manifest.json','initial_state_manifest.json','F1.json'):
            exclusive_json(self.root,name,{})
        self.manifest['stage_b_bindings']['F1']=sha(self.root/'F1.json')
        (self.root/'raw').mkdir();(self.root/'attempts').mkdir()
        self.ref=SimpleNamespace(root=self.root,manifest=self.manifest,initial_sha=sha(self.root/'initial_state_manifest.json'),
            f1_path=self.root/'F1.json',initial={'scientific_runtime_signature':self.expect['scientific_runtime_signature'],'states':[]},
            expected=lambda task:expected(task))
        self.bindings={'manifest_digest':self.manifest['manifest_digest'],'input_bundle_digest':self.manifest['input_bundle_digest'],
            'environment_binding':self.manifest['environment_binding'],'initial_state_manifest_sha256':self.ref.initial_sha,
            'source_bindings_digest':canonical({}),'executor_bundle_digest':canonical({}),
            'scientific_runtime_signature':self.expect['scientific_runtime_signature']}
        self.request={'worker_id':'W1','attempt_id':'A_FULL_0002','manifest_digest':self.manifest['manifest_digest'],'tasks':[self.task]}
        exclusive_json(self.root,'request.json',self.request)
        self.contract={'manifest_path':str(self.root/'manifest.json'),'manifest_file_sha256':sha(self.root/'manifest.json'),
            'bindings':self.bindings,'protected_files_sha256':{},'snapshot_source_sha256':{},
            'requests':{'W1':{'path':str(self.root/'request.json'),'sha256':sha(self.root/'request.json')}}}
    def tearDown(self):self.tmp.cleanup()
    def run_snapshot(self):
        with patch.object(module,'FrozenReference',return_value=self.ref):return module.snapshot(self.contract)
    def pending(self):
        folder=self.root/f'attempts/{task_stem(self.task)}/A_FULL_0002/W1'
        folder.mkdir(parents=True,exist_ok=False)
        # Match original publisher's final directory shape; dynamic publisher
        # intentionally retains its own .pending hardlink as extra evidence.
        (folder/'rng_before.json').write_text(json.dumps(rng_fixture(self.expect)),encoding='utf-8')
        return folder
    def test_empty_before_rng_has_no_invented_retry(self):
        result=self.run_snapshot();self.assertEqual(result['pending'],[]);self.assertEqual(result['completed_count'],0)
    def test_real_fixture_rng_bytes_are_bound(self):
        folder=self.pending();result=self.run_snapshot()
        self.assertEqual(result['pending'][0]['rng_file_sha256'],sha(folder/'rng_before.json'))
        self.assertEqual(result['pending'][0]['task'],self.task)
    def test_partial_final_csv_rejected(self):
        (self.root/f'raw/{task_stem(self.task)}.csv').write_text('partial')
        with self.assertRaises(Exception):self.run_snapshot()
    def test_pending_attempt_csv_rejected(self):
        folder=self.pending();(folder/'trajectory.csv').write_text('partial')
        with self.assertRaises(Exception):self.run_snapshot()
    def test_pending_attempt_audit_rejected(self):
        folder=self.pending();exclusive_json(folder,'audit.json',{})
        with self.assertRaises(Exception):self.run_snapshot()
    def test_pending_partial_file_rejected(self):
        folder=self.pending();(folder/'rng_before.json.partial_1').write_text('partial')
        with self.assertRaises(Exception):self.run_snapshot()
    def test_wrong_request_sha_rejected(self):
        self.contract['requests']['W1']['sha256']='0'*64
        with self.assertRaises(Exception):self.run_snapshot()
    def test_unknown_worker_rejected(self):
        self.pending().rename(self.root/f'attempts/{task_stem(self.task)}/A_FULL_0002/W2')
        with self.assertRaises(Exception):self.run_snapshot()
    def test_saved_csv_and_all_links_validated(self):
        _,receipt=saved_fixture(self.root,self.task)
        exclusive_json(self.root/receipt['attempt_csv_relative'].rsplit('/',1)[0],'receipt.json',receipt)
        result=self.run_snapshot()
        self.assertEqual(result['completed_count'],1)
        self.assertEqual(result['saved_records'][task_stem(self.task)],sha(self.root/f'raw/{task_stem(self.task)}.integrity.json'))
    def test_original_protected_file_sha_mismatch_rejected(self):
        p=self.root/'protected.txt';p.write_text('SYNTHETIC')
        self.contract['protected_files_sha256'][str(p)]='0'*64
        with self.assertRaises(Exception):self.run_snapshot()


if __name__=='__main__':unittest.main()
