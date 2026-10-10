import copy
from pathlib import Path
import tempfile
import unittest
from fixtures import expected,rng_fixture,saved_fixture,tasks
from integrity import validate_completion,rng_identity,retry_identity,paired_groups,PAIR_FIELDS
from queue_store import IntegrityError,canonical,exclusive_json,sha,task_stem

class IntegrityTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.task=tasks(1)[0]
    def tearDown(self):self.tmp.cleanup()
    def test_valid_synthetic_receipt_and_all_24_stages(self):
        exp,_=saved_fixture(self.root,self.task);proof=validate_completion(self.root,self.task,exp)
        self.assertEqual(len(proof['rows']),24);self.assertFalse(proof['loss_values_used'])
    def test_csv_byte_change_rejected(self):
        exp,_=saved_fixture(self.root,self.task);path=self.root/f'raw/{task_stem(self.task)}.csv';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaises(IntegrityError):validate_completion(self.root,self.task,exp)
    def test_common_but_wrong_f1_fields_rejected(self):
        for index,field in enumerate(PAIR_FIELDS):
            root=self.root/f'case{index}';root.mkdir()
            exp,_=saved_fixture(root,self.task,mutate_rows=lambda rows:[row.update({field:'WRONG'}) for row in rows])
            with self.subTest(field=field),self.assertRaises(IntegrityError):validate_completion(root,self.task,exp)
    def test_stage_shift_rejected(self):
        exp,_=saved_fixture(self.root,self.task,mutate_rows=lambda rows:rows[0].update(stage='0'))
        with self.assertRaises(IntegrityError):validate_completion(self.root,self.task,exp)
    def test_future_service_access_rejected(self):
        exp,_=saved_fixture(self.root,self.task,mutate_rows=lambda rows:rows[0].update(online_future_service_used='True'))
        with self.assertRaises(IntegrityError):validate_completion(self.root,self.task,exp)
    def test_initial_identity_rejected(self):
        exp,_=saved_fixture(self.root,self.task,mutate_rows=lambda rows:rows[0].update(identity_before='OTHER'))
        with self.assertRaises(IntegrityError):validate_completion(self.root,self.task,exp)
    def test_runtime_environment_source_and_audit_settings_rejected(self):
        cases=[('runtime',lambda v:v.update(environment_binding='WRONG')),
               ('runtime',lambda v:v.update(source_bindings_digest='WRONG')),
               ('audit',lambda v:v.update(scientific_runtime={'WRONG':True}))]
        for index,(kind,mutation) in enumerate(cases):
            root=self.root/f'case{index}';root.mkdir();kwargs={'mutate_'+kind:mutation}
            exp,_=saved_fixture(root,self.task,**kwargs)
            with self.subTest(kind=kind,index=index),self.assertRaises(IntegrityError):validate_completion(root,self.task,exp)
    def test_causal_audit_violation_rejected(self):
        exp,_=saved_fixture(self.root,self.task,mutate_audit=lambda v:v['timeline_access'].update(violation_count=1))
        with self.assertRaises(IntegrityError):validate_completion(self.root,self.task,exp)
    def test_receipt_manifest_or_deployment_rejected(self):
        for index,key in enumerate(('manifest_digest','input_bundle_digest','deployment_tier','bank_hash','deployment_filter_hash')):
            root=self.root/f'case{index}';root.mkdir();exp,_=saved_fixture(root,self.task,mutate_receipt=lambda v:v.update({key:'WRONG'}))
            with self.subTest(key=key),self.assertRaises(IntegrityError):validate_completion(root,self.task,exp)
    def test_valid_rng_metadata_without_running_torch(self):
        exp=expected(self.task);value=rng_fixture(exp)
        self.assertEqual(rng_identity(value,exp['rng_bindings'],exp['scientific_runtime']),value['state_digest'])
    def test_rng_scope_versions_devices_and_zero_bytes_rejected(self):
        exp=expected(self.task)
        mutations=[lambda v:v.update(scope='WRONG'),lambda v:v.update(torch_version='WRONG'),
            lambda v:v.update(cuda_runtime='WRONG'),lambda v:v.update(cuda=[]),
            lambda v:v['cuda'][0].update(device_index=True),lambda v:v['cuda'][0].update(device_name='WRONG'),
            lambda v:v['cpu'].update(base64='',shape=[0],byte_count=0,sha256=__import__('hashlib').sha256(b'').hexdigest()),
            lambda v:v.update(manual_seed_called=True),lambda v:v['bindings'].update(expected_initial_state_hash='WRONG')]
        for mutation in mutations:
            value=rng_fixture(exp);mutation(value);value['state_digest']=canonical({k:x for k,x in value.items() if k!='state_digest'})
            with self.subTest(value=value),self.assertRaises(IntegrityError):rng_identity(value,exp['rng_bindings'],exp['scientific_runtime'])
    def test_exact_failure_rng_reuse_identity(self):
        exp=expected(self.task);rng=rng_fixture(exp);exclusive_json(self.root,'failed/rng.json',rng)
        failure={'task':self.task,'status':'INTERRUPTED','completed_valid':False,
            **{k:exp[k] for k in ('manifest_digest','input_bundle_digest','environment_binding')},
            'rng_relative':'failed/rng.json','rng_file_sha256':sha(self.root/'failed/rng.json')}
        exclusive_json(self.root,'failed/failure.json',failure)
        proof=retry_identity(self.root,self.task,{'failed_receipt_relative':'failed/failure.json',
            'failed_receipt_sha256':sha(self.root/'failed/failure.json')},exp)
        self.assertEqual(proof['exact_failed_state_digest'],rng['state_digest']);self.assertFalse(proof['new_random_draw'])
    def test_no_rng_failure_requires_certified_pre_run_boundary(self):
        exp=expected(self.task);failure={'task':self.task,'status':'FAILED','completed_valid':False,
            **{k:exp[k] for k in ('manifest_digest','input_bundle_digest','environment_binding')},'rng_relative':None}
        exclusive_json(self.root,'failure.json',failure)
        with self.assertRaises(IntegrityError):retry_identity(self.root,self.task,{'failed_receipt_relative':'failure.json',
            'failed_receipt_sha256':sha(self.root/'failure.json')},exp)
    def test_five_method_parity_passes_only_complete_matching_group(self):
        proofs=[]
        for index,task in enumerate(tasks(5)):
            root=self.root/f'm{index}';root.mkdir();exp,_=saved_fixture(root,task);proofs.append(validate_completion(root,task,exp))
        self.assertEqual(paired_groups(proofs[:4])['complete_paired_groups'],0)
        self.assertEqual(paired_groups(proofs)['complete_paired_groups'],1)
        proofs[-1]['rows'][7]['deployment_tier']='WRONG'
        with self.assertRaises(IntegrityError):paired_groups(proofs)
    def test_duplicate_method_rejected(self):
        exp,_=saved_fixture(self.root,self.task);proof=validate_completion(self.root,self.task,exp)
        with self.assertRaises(IntegrityError):paired_groups([proof,proof])

if __name__=='__main__':unittest.main()
