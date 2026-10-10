"""Negative controls for history, inventory, ZIP, scope and native exit handling."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
HERE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
e=load('postpublication_test_api','postpublication_finalize.py')
l=load('postpublication_test_launcher','root_finalize_launch.py')
class Controls(unittest.TestCase):
    def history(self):
        return ({'pid':10108,'producer':'ROOT_OWNING_POPEN','plan_sha256':e.FROZEN[e.RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json']},
        {'original_metadata_producer_pid':10108,'original_metadata_producer_actual_exit_code':'NOT_OBSERVED','actual_tool_exit_code':1,'actual_exit_zero_reconstructed':False,'old_exit_receipt_written':False},
        {'status':'SMOKE_COUNT_METADATA_ERRATUM_COMPLETED','statistics_bytes_unchanged':True,'root_handoff_sha256':e.H2,'zip_sha256':e.FROZEN[e.ZIP],'package':str(e.PACKAGE),'zip':str(e.ZIP)})
    def test_unknown_history_pass(self):e.verify_history(*self.history())
    def test_history_mutations_rejected(self):
        for index,key,value in ((0,'pid',1),(0,'producer','FAKE'),(0,'plan_sha256','0'*64),(1,'original_metadata_producer_actual_exit_code',0),(1,'actual_tool_exit_code',0),(1,'actual_tool_exit_code',True),(1,'actual_exit_zero_reconstructed',True),(1,'old_exit_receipt_written',True),(2,'statistics_bytes_unchanged',False),(2,'root_handoff_sha256',e.H1),(2,'zip_sha256','0'*64)):
            with self.subTest(key=key):
                values=copy.deepcopy(self.history());values[index][key]=value
                with self.assertRaises(RuntimeError):e.verify_history(*values)
    def test_inventory_exact(self):e.verify_inventory({'a':'b'},{'a':'b'})
    def test_inventory_extra(self):
        with self.assertRaises(RuntimeError):e.verify_inventory({'a':'b','x':'y'},{'a':'b'})
    def test_inventory_mutation(self):
        with self.assertRaises(RuntimeError):e.verify_inventory({'a':'c'},{'a':'b'})
    def test_zip_negative_controls(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.zip';h=__import__('hashlib').sha256(b'ok').hexdigest()
            with zipfile.ZipFile(p,'w') as z:z.writestr('a',b'ok')
            e.verify_zip(p,{'a':h})
            for expected in ({'a':'0'*64},{'a':h,'extra':h},{}):
                with self.assertRaises(RuntimeError):e.verify_zip(p,expected)
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('a',b'ok');z.writestr('a',b'ok')
            with self.assertRaises(RuntimeError):e.verify_zip(p,{'a':h})
    def test_publication_chain(self):
        v={'status':'PUBLISHED_VERIFIED_SAVED_DRAFT','previous_sha256':e.H1,'new_sha256':e.H2,'all_prior_bytes_archived':True};e.verify_publication(v)
        for key,value in (('previous_sha256',e.H2),('new_sha256',e.H1),('all_prior_bytes_archived',False)):
            with self.assertRaises(RuntimeError):e.verify_publication({**v,key:value})
    def test_native_exit_types_identity(self):
        self.assertEqual(l.exit_observation(0,0,5,5)['actual_exit_code'],0)
        for values in ((True,0,5,5),(0,True,5,5),(0,1,5,5),(0,0,5,6)):
            with self.assertRaises(RuntimeError):l.exit_observation(*values)
    def test_post_exit_never_image_query(self):
        source=(HERE/'root_finalize_launch.py').read_text();tail=source[source.index('actual=p.wait()'):]
        self.assertNotIn('observer.identity(',tail);self.assertNotIn('QueryFullProcessImageNameW',tail)
    def test_raw_exit_saved_first(self):
        source=(HERE/'root_finalize_launch.py').read_text();self.assertLess(source.index('raw=e.emit('),source.index('terminal=exit_observation('))
    def test_metadata_has_no_process_or_science(self):
        source=(HERE/'postpublication_finalize.py').read_text();self.assertNotIn('subprocess',source);self.assertNotIn('import torch',source);self.assertNotIn('import numpy',source)
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    proof={'schema':'paper3-postpublication-synthetic-proof-v1','all_pass':result.wasSuccessful(),'tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'implementation_sha256':e.own_pins(),
        'actual_models_statistics_publication_or_process_control':False,'created_utc':e.utc()}
    e.emit(e.PROOF,proof);raise SystemExit(0 if result.wasSuccessful() else 1)
