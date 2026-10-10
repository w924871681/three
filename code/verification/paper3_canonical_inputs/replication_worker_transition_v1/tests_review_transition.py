"""Pure synthetic metadata fixtures only; never reads actual project results."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PureWindowsPath
from subprocess import list2cmdline
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('standalone_transition_reviewer',HERE/'review_transition.py')
r=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(r)

def h(value):return hashlib.sha256(str(value).encode()).hexdigest()
def payload(value):return json.dumps(value,sort_keys=True,indent=2).encode()
def b64(value):return base64.b64encode(value).decode()
def rebind_receipt(entry):
    data=payload(entry['receipt']);entry.update(receipt_payload_base64=b64(data),receipt_file_sha256=r.sha_bytes(data),receipt_file_sha256_rechecked=r.sha_bytes(data))
def rebind_rng(snapshot,edit):
    item=snapshot['pending'][0]['artifacts']['rng_before.json'];value=json.loads(base64.b64decode(item['payload_base64']))
    edit(value);value.pop('state_digest',None);value['state_digest']=r.digest(value);data=payload(value)
    item.update(file_sha256=r.sha_bytes(data),payload_base64=b64(data))

def fixture():
    critical={'scripts/run_p7_7_final.py':h('runner'),'core/p7.py':h('method'),'configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json':h('config')}
    critical.update({f'core/synthetic_{i}.py':h(i) for i in range(91)})
    executor={f'synthetic_{i}.py':h(('executor',i)) for i in range(18)}
    initial_hashes={f'{c}_{seed}':h((c,seed,'initial')) for c in range(33000,33020) for seed in (7311,7312,7313)}
    runtime={'torch_version':'SYNTHETIC_NO_TORCH','torch_cuda_build_version':'SYNTHETIC_NO_CUDA','cuda_devices':[{'name':'SYNTHETIC_GPU'}]}
    bundle={'context':'F','replicate':'F1','input_bundle_digest':r.F1_DIGEST,'base':{},'scenarios':{},'roles':{}}
    for c in range(33000,33020):
        bundle['base'][str(c)]={'profile':{'center_type':'A','budget_tier':'medium'},'deployment':{'bank_hash':h('bank'),'deployment_filter_hash':h((c,'filter'))}}
        for q in ('C0','C1','C3','C4'):
            bundle['scenarios'][f'{c}/{q}']={'legacy_scenario_hash':h((c,q,'scenario')),'metadata':{'definition':'SYNTHETIC_'+q}}
            for stage in range(1,25):
                for role in ('update','assessment','service'):
                    bundle['roles'][f'{c}/{q}/{stage}/{role}']={'legacy_role_hash':h((c,q,stage,role)),'update_end_ts':str(stage*100),'decision_ts':str(stage*100+1)}
    f1_data=payload(bundle);base_python=r'C:\SYNTHETIC_PYTHON_BASE\python.exe'
    manifest={'paths':{'repo':r.REPO,'results_root':r.RESULTS,'executor_root':r.EXECUTOR,'input_run':r.REPO+r'\verification\SYNTHETIC_INPUT_ONLY'},
              'input_bundle_digest':r.F1_DIGEST,'original_records_mixed_into_new_results':False,'historical_environment_reproduced':False,
              'critical_files_sha256':critical,'executor_sha256':executor,'input_files_sha256':{'synthetic.npy':h('NOT_AN_ARRAY')},
              'stage_b_bindings':{'F1':r.sha_bytes(f1_data)},'environment_binding':h('synthetic_env'),
              'environment':{'base_prefix':r'C:\SYNTHETIC_PYTHON_BASE','bound_files_sha256':{base_python:h('synthetic_executable')}}}
    manifest_id=r.digest(manifest);manifest['manifest_digest']=manifest_id
    initial={'manifest_digest':manifest_id,'input_bundle_digest':r.F1_DIGEST,'completed_cases':60,
             'states':[{'center_id':c,'seed':s,'initial_state_hash':initial_hashes[f'{c}_{s}']} for c in range(33000,33020) for s in (7311,7312,7313)],
             'scientific_runtime_signature':r.digest(runtime)}
    initial_data=payload(initial);initial_sha=r.sha_bytes(initial_data)
    matrix=r.tasks();request={'schema':'paper3-replication-worker-request-v1','manifest_digest':manifest_id,'mode':'trajectory','worker_count':1,
             'worker_id':'W1','attempt_id':'A_FULL_0001','retries':{},'initial_state_manifest':'initial_state_manifest.json','tasks':matrix[5:]}
    request_data=payload(request);request_sha=r.sha_bytes(request_data)
    request_path=str(PureWindowsPath(r.RESULTS)/'execution/full/A_FULL_0001/W1_request.json')
    command=[r.PYTHON,'-I','-S','-B','-X',f'pycache_prefix={r.RESULTS}\\_never_created_pycache_full_A_FULL_0001_W1',r.EXECUTOR+'\\executor_worker.py',
             '--manifest',r.RESULTS+'\\provenance_manifest.json','--mode','trajectory','--request-file',request_path,'--worker-id','W1','--attempt-id','A_FULL_0001']
    identity={'pid':r.BASE_PID,'creation_filetime':r.BASE_FILETIME,'creation_time_utc':'2026-10-09T09:48:15.556295+00:00','executable':base_python,
              'command':command,'request_path':request_path,'request_sha256':request_sha,'worker_id':'W1','attempt_id':'A_FULL_0001'}
    wrapper={'pid':r.WRAPPER_PID,'creation_filetime':r.WRAPPER_FILETIME,'executable':r.PYTHON,'command':command,'scientific_child_pid':r.BASE_PID}
    native=[{'pid':r.BASE_PID,'creation_filetime':r.BASE_FILETIME,'image':base_python,'command_line':'"'+base_python+'" '+list2cmdline(command[1:]),'exit_code':259,'private_bytes':r.GIB,'parent_pid':r.WRAPPER_PID},
            {'pid':r.WRAPPER_PID,'creation_filetime':r.WRAPPER_FILETIME,'image':r.PYTHON,'command_line':list2cmdline(command),'exit_code':259,'private_bytes':1048576,'parent_pid':88888}]
    source_expected={str(PureWindowsPath(r.REPO)/name):value for name,value in critical.items()}
    source_expected.update({str(PureWindowsPath(r.EXECUTOR)/name):value for name,value in executor.items()})
    input_expected={str(PureWindowsPath(manifest['paths']['input_run'])/name):value for name,value in manifest['input_files_sha256'].items()}
    snapshot={'schema':'paper3-worker-transition-snapshot-v1','captured_utc':'2026-10-09T12:00:00+00:00',
        'context':{'manifest':manifest,'initial_manifest_payload_base64':b64(initial_data),'f1_context_payload_base64':b64(f1_data),'initial_hashes':initial_hashes,'scientific_runtime':runtime},
        'source_bindings':{'expected':source_expected,'observed':copy.deepcopy(source_expected)},'input_files':{'expected':input_expected,'observed':copy.deepcopy(input_expected)},
        'worker':{'expected_identity':identity,'observed_identity':copy.deepcopy(identity),'wrapper_identity':{'expected':wrapper,'observed':copy.deepcopy(wrapper)},
                  'native_processes':native,'suspended':True,'suspension_verified':True,'snapshot_stable':True,'active_scientific_worker_pids':[r.BASE_PID]},
        'request':request,'request_binding':{'payload_base64':b64(request_data),'observed_sha256_before':request_sha,'observed_sha256_after':request_sha},
        'raw_entries':[],'pending':[],'unknown_artifacts':[],
        'resources':{'sampled_utc':'2026-10-09T11:59:59+00:00','free_commit_bytes':6*r.GIB,'existing_worker_private_bytes':r.GIB,'reserved_extra_worker_count':1,'requested_minimum_free_commit_bytes':int(4.5*r.GIB)}}
    for task in matrix[:5]:
        initial_hash=initial_hashes[f"{task['center_id']}_{task['seed']}"];name=r.stem(task);expected=r.expected_inputs(bundle,task,initial_hash)
        prefix=f'attempts/{name}/A_MINIMAL_0001/W1';csvsha=h((name,'csv'))
        receipt={'schema':'paper3-batch20-replication-trajectory-receipt-v1','valid':True,'task':task,'trajectory_rows':24,'manifest_digest':manifest_id,
             'input_bundle_digest':r.F1_DIGEST,'environment_binding':manifest['environment_binding'],'initial_state_hash':initial_hash,
             'initial_state_manifest_sha256':initial_sha,'source_bindings_digest':r.digest(critical),'executor_bundle_digest':r.digest(executor),
             'scientific_runtime_signature':r.digest(runtime),'runner_hash':critical['scripts/run_p7_7_final.py'],'implementation_hash':critical['core/p7.py'],
             'protocol_hash':critical['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'],'full_24_stage_input_parity_checked':True,'future_online_access_violation_count':0,
             'performance_based_continuation':False,'statistics_executed':False,'output_hash':csvsha,'audit_relative':prefix+'/audit.json','audit_hash':h((name,'audit')),
             'rng_relative':prefix+'/rng_before.json','rng_file_sha256':h((name,'rng')),'attempt_csv_relative':prefix+'/trajectory.csv','attempt_csv_hash':csvsha,
             'runtime_receipt_path':'workers/W1_A_MINIMAL_0001_trajectory.runtime.json','runtime_receipt_sha256':h('runtime_receipt'),
             'stage_input_hashes':[{'stage':row['stage'],**{k:row[k] for k in ('D_upd_hash','D_assess_hash','D_srv_hash')}} for row in expected],
             **{k:expected[0][k] for k in ('deployment_tier','deployment_filter_hash','bank_hash')}}
        rows=[{**{k:str(v) for k,v in task.items()},**{k:str(v) for k,v in row.items()},'identity_before':'msa_a57_pt','future_service_used_in_decision':'False','online_future_service_used':'False'} for row in expected]
        artifacts={receipt['audit_relative']:receipt['audit_hash'],receipt['rng_relative']:receipt['rng_file_sha256'],receipt['attempt_csv_relative']:receipt['attempt_csv_hash'],receipt['runtime_receipt_path']:receipt['runtime_receipt_sha256']}
        entry={'receipt':receipt,'csv_relative':'raw/'+name+'.csv','receipt_relative':'raw/'+name+'.integrity.json','csv_sha256':csvsha,'csv_sha256_rechecked':csvsha,
               'bound_artifacts':artifacts,'input_projection':rows,'expected_stage_inputs':expected};rebind_receipt(entry);snapshot['raw_entries'].append(entry)
    task=matrix[5]
    tensor={'dtype':'uint8','shape':[4],'byte_count':4,'sha256':r.sha_bytes(b'test'),'base64':b64(b'test')}
    rng={'schema':'paper3-original-task-torch-rng-v1','manual_seed_called':False,'scope':'EXISTING_EXECUTION_RNG_PROVENANCE','torch_version':runtime['torch_version'],
         'cuda_runtime':runtime['torch_cuda_build_version'],'cpu':tensor,'cuda':[{'device_index':0,'device_name':'SYNTHETIC_GPU','state':copy.deepcopy(tensor)}],
         'bindings':{'task':task,'input_bundle_digest':r.F1_DIGEST,'source_bindings_digest':r.digest(critical),'environment_binding':manifest['environment_binding'],
                     'final_configuration_sha256':critical['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'],'expected_initial_state_hash':initial_hashes[f"{task['center_id']}_{task['seed']}"]}}
    rng['state_digest']=r.digest(rng);rng_data=payload(rng)
    snapshot['pending']=[{'task':task,'artifacts':{'rng_before.json':{'relative_path':f'attempts/{r.stem(task)}/A_FULL_0001/W1/rng_before.json','file_sha256':r.sha_bytes(rng_data),'payload_base64':b64(rng_data)}}}]
    return snapshot,manifest_id,initial_sha

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.saved,cls.manifest_id,cls.initial_sha=fixture()
    def setUp(self):
        self.s=copy.deepcopy(self.saved)
        self.patchers=[patch.object(r,'MANIFEST_DIGEST',self.manifest_id),patch.object(r,'INITIAL_MANIFEST_SHA256',self.initial_sha)]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
    def rejected(self,edit):
        edit(self.s)
        with self.assertRaises(r.TransitionAuditError):r.audit_snapshot(self.s)
    def test_synthetic_complete_pass(self):
        result=r.audit_snapshot(self.s);self.assertTrue(result['eligible_to_terminate']);self.assertEqual(result['completed_trajectories'],5)
        self.assertFalse(result['independent_runtime_authenticity_certified']);self.assertFalse(result['new_unstarted_task_rng_equals_old_serial_path'])
    def test_source_changed(self):self.rejected(lambda s:s['source_bindings']['observed'].update({next(iter(s['source_bindings']['observed'])):h('changed')}))
    def test_mandatory_source_removed_from_both_maps(self):
        def edit(s):
            key=next(iter(s['source_bindings']['expected']));s['source_bindings']['expected'].pop(key);s['source_bindings']['observed'].pop(key)
        self.rejected(edit)
    def test_input_changed(self):self.rejected(lambda s:s['input_files']['observed'].update({next(iter(s['input_files']['observed'])):h('changed')}))
    def test_manifest_tamper(self):self.rejected(lambda s:s['context']['manifest'].update(historical_environment_reproduced=True))
    def test_initial_bytes_tamper(self):self.rejected(lambda s:s['context'].update(initial_manifest_payload_base64=b64(b'{}')))
    def test_initial_map_tamper(self):self.rejected(lambda s:s['context']['initial_hashes'].update({'33000_7311':h('wrong')}))
    def test_runtime_tamper(self):self.rejected(lambda s:s['context']['scientific_runtime'].update(torch_version='wrong'))
    def test_F1_bytes_tamper(self):self.rejected(lambda s:s['context'].update(f1_context_payload_base64=b64(b'{}')))
    def test_reused_base_pid(self):self.rejected(lambda s:s['worker']['observed_identity'].update(creation_filetime=r.BASE_FILETIME+1))
    def test_wrong_base_pid_even_both_claim_same(self):
        self.rejected(lambda s:[s['worker'][k].update(pid=1) for k in ('expected_identity','observed_identity')])
    def test_wrong_wrapper_identity(self):self.rejected(lambda s:s['worker']['wrapper_identity']['observed'].update(pid=1))
    def test_wrong_native_parent(self):self.rejected(lambda s:s['worker']['native_processes'][0].update(parent_pid=1))
    def test_native_actual_command_appended(self):self.rejected(lambda s:s['worker']['native_processes'][0].update(command_line=s['worker']['native_processes'][0]['command_line']+' --wrong'))
    def test_native_image_wrong(self):self.rejected(lambda s:s['worker']['native_processes'][0].update(image=r'C:\wrong.exe'))
    def test_native_exited(self):self.rejected(lambda s:s['worker']['native_processes'][0].update(exit_code=0))
    def test_not_suspended(self):self.rejected(lambda s:s['worker'].update(suspended=False))
    def test_suspension_not_verified(self):self.rejected(lambda s:s['worker'].update(suspension_verified=False))
    def test_two_active_workers(self):self.rejected(lambda s:s['worker'].update(active_scientific_worker_pids=[r.BASE_PID,2]))
    def test_unstable_snapshot(self):self.rejected(lambda s:s['worker'].update(snapshot_stable=False))
    def test_request_bytes_wrong(self):self.rejected(lambda s:s['request_binding'].update(payload_base64=b64(b'{}')))
    def test_request_changed_after_read(self):self.rejected(lambda s:s['request_binding'].update(observed_sha256_after=h('wrong')))
    def test_csv_hash_wrong(self):self.rejected(lambda s:s['raw_entries'][0].update(csv_sha256_rechecked=h('wrong')))
    def test_receipt_payload_changed(self):self.rejected(lambda s:s['raw_entries'][0].update(receipt_payload_base64=b64(b'{}')))
    def test_receipt_actual_invalid(self):
        def edit(s):s['raw_entries'][0]['receipt']['valid']=False;rebind_receipt(s['raw_entries'][0])
        self.rejected(edit)
    def test_receipt_wrong_manifest(self):
        def edit(s):s['raw_entries'][0]['receipt']['manifest_digest']=h('wrong');rebind_receipt(s['raw_entries'][0])
        self.rejected(edit)
    def test_receipt_wrong_initial(self):
        def edit(s):s['raw_entries'][0]['receipt']['initial_state_hash']=h('wrong');rebind_receipt(s['raw_entries'][0])
        self.rejected(edit)
    def test_receipt_boolean_is_not_integer(self):
        def edit(s):s['raw_entries'][0]['receipt']['future_online_access_violation_count']=False;rebind_receipt(s['raw_entries'][0])
        self.rejected(edit)
    def test_audit_artifact_hash_wrong(self):self.rejected(lambda s:s['raw_entries'][0]['bound_artifacts'].update({next(iter(s['raw_entries'][0]['bound_artifacts'])):h('wrong')}))
    def test_23_stages(self):self.rejected(lambda s:s['raw_entries'][0]['input_projection'].pop())
    def test_stage_order_wrong(self):self.rejected(lambda s:s['raw_entries'][0]['input_projection'].reverse())
    def test_stage_field_wrong(self):self.rejected(lambda s:s['raw_entries'][0]['input_projection'][0].update(D_srv_hash=h('wrong')))
    def test_self_reference_not_F1(self):
        def edit(s):
            s['raw_entries'][0]['input_projection'][0]['D_srv_hash']=h('wrong');s['raw_entries'][0]['expected_stage_inputs'][0]['D_srv_hash']=h('wrong')
        self.rejected(edit)
    def test_future_access(self):self.rejected(lambda s:s['raw_entries'][0]['input_projection'][0].update(online_future_service_used='True'))
    def test_initial_identity_wrong(self):self.rejected(lambda s:s['raw_entries'][0]['input_projection'][0].update(identity_before='wrong'))
    def test_duplicate_completed_task(self):self.rejected(lambda s:s['raw_entries'].append(copy.deepcopy(s['raw_entries'][0])))
    def test_incomplete_preexisting_raw(self):self.rejected(lambda s:s['raw_entries'].pop())
    def test_unknown_artifact(self):self.rejected(lambda s:s['unknown_artifacts'].append('raw/unreceipted.csv'))
    def test_partial_artifact(self):self.rejected(lambda s:s['unknown_artifacts'].append('attempts/current/rng_before.json.partial_123'))
    def test_two_pending_tasks(self):self.rejected(lambda s:s['pending'].append(copy.deepcopy(s['pending'][0])))
    def test_no_pending_rng_boundary_rejected(self):self.rejected(lambda s:s['pending'].clear())
    def test_pending_csv_rejected(self):self.rejected(lambda s:s['pending'][0]['artifacts'].update({'trajectory.csv':{}}))
    def test_pending_audit_rejected(self):self.rejected(lambda s:s['pending'][0]['artifacts'].update({'audit.json':{}}))
    def test_pending_receipt_rejected(self):self.rejected(lambda s:s['pending'][0]['artifacts'].update({'receipt.json':{}}))
    def test_wrong_pending_task(self):self.rejected(lambda s:s['pending'][0].update(task=r.tasks()[6]))
    def test_rng_bytes_corrupt(self):self.rejected(lambda s:s['pending'][0]['artifacts']['rng_before.json'].update(payload_base64=b64(b'{}')))
    def test_rng_source_binding_wrong(self):self.rejected(lambda s:rebind_rng(s,lambda x:x['bindings'].update(source_bindings_digest=h('wrong'))))
    def test_rng_task_wrong(self):self.rejected(lambda s:rebind_rng(s,lambda x:x['bindings'].update(task=r.tasks()[6])))
    def test_rng_manual_seed_claim(self):self.rejected(lambda s:rebind_rng(s,lambda x:x.update(manual_seed_called=True)))
    def test_rng_cpu_byte_hash_wrong(self):self.rejected(lambda s:rebind_rng(s,lambda x:x['cpu'].update(sha256=h('wrong'))))
    def test_rng_device_wrong(self):self.rejected(lambda s:rebind_rng(s,lambda x:x['cuda'][0].update(device_name='wrong')))
    def test_rng_device_count_wrong(self):self.rejected(lambda s:rebind_rng(s,lambda x:x['cuda'].clear()))
    def test_resource_too_low(self):self.rejected(lambda s:s['resources'].update(free_commit_bytes=2*r.GIB-1,requested_minimum_free_commit_bytes=2*r.GIB))
    def test_resource_threshold_too_low(self):self.rejected(lambda s:s['resources'].update(requested_minimum_free_commit_bytes=2*r.GIB-1))
    def test_resource_private_not_actual(self):self.rejected(lambda s:s['resources'].update(existing_worker_private_bytes=2*r.GIB))
    def test_resource_stale(self):self.rejected(lambda s:s['resources'].update(sampled_utc='2026-10-09T11:58:00+00:00'))
    def test_resource_future(self):self.rejected(lambda s:s['resources'].update(sampled_utc='2026-10-09T12:00:01+00:00'))
    def external(self):
        audited=r.audit_snapshot(self.s);termination={'pid':r.BASE_PID,'creation_time_utc':self.s['worker']['expected_identity']['creation_time_utc'],'creation_filetime':r.BASE_FILETIME,
            'method':'TerminateProcess','confirmed_dead':True,'exit_code':23,'worker_exception_observed':False,'terminated_utc':'2026-10-09T12:00:01+00:00'}
        record={'schema':'paper3-external-worker-termination-journal-v1','snapshot':self.s,'snapshot_audit':audited,'termination':termination}
        data=payload(record);journal={'file_sha256':r.sha_bytes(data),'payload_base64':b64(data)};task=audited['pending_task']
        receipt={'schema':'paper3-batch20-failed-task-receipt-v1','status':'INTERRUPTED','completed_valid':False,'task':task,'manifest_digest':self.manifest_id,
            'input_bundle_digest':r.F1_DIGEST,'environment_binding':self.s['context']['manifest']['environment_binding'],
            'initial_state_hash':self.s['context']['initial_hashes'][f"{task['center_id']}_{task['seed']}"],'worker_id':'W1','attempt_id':'A_FULL_0001',
            'rng_relative':audited['pending_rng_relative'],'rng_file_sha256':audited['pending_rng_file_sha256'],'failed_before_rng_capture':False,
            'producer':'external-migration-controller','worker_exception_observed':False,'error_type':'ExternalControlledInterruption',
            'external_termination_journal_sha256':journal['file_sha256'],'automatic_new_draw_retry':False,'originals_overwritten':False,
            'message':'Actual external controller termination; no worker exception observed.','created_utc':'2026-10-09T12:00:02+00:00'}
        return receipt,journal
    def test_honest_external_termination_pass(self):
        receipt,journal=self.external();self.assertEqual(r.audit_external_interruption(receipt,journal)['status'],'EXTERNAL_INTERRUPTION_EVIDENCE_CONSISTENT')
    def test_fake_worker_traceback_rejected(self):
        receipt,journal=self.external();receipt['traceback']='not a real worker exception'
        with self.assertRaises(r.TransitionAuditError):r.audit_external_interruption(receipt,journal)
    def test_external_producer_mislabeled(self):
        receipt,journal=self.external();receipt['producer']='worker'
        with self.assertRaises(r.TransitionAuditError):r.audit_external_interruption(receipt,journal)
    def test_external_journal_hash_wrong(self):
        receipt,journal=self.external();receipt['external_termination_journal_sha256']=h('wrong')
        with self.assertRaises(r.TransitionAuditError):r.audit_external_interruption(receipt,journal)
    def test_external_unconfirmed_death_rejected(self):
        receipt,journal=self.external();record=json.loads(base64.b64decode(journal['payload_base64']));record['termination']['confirmed_dead']=False
        data=payload(record);journal={'file_sha256':r.sha_bytes(data),'payload_base64':b64(data)};receipt['external_termination_journal_sha256']=journal['file_sha256']
        with self.assertRaises(r.TransitionAuditError):r.audit_external_interruption(receipt,journal)
    def test_json_duplicates_rejected(self):
        with self.assertRaises(r.TransitionAuditError):r.decoded_json(b64(b'{"a":1,"a":2}'),r.sha_bytes(b'{"a":1,"a":2}'))
    def test_json_nan_rejected(self):
        with self.assertRaises(r.TransitionAuditError):r.decoded_json(b64(b'{"a":NaN}'),r.sha_bytes(b'{"a":NaN}'))

    def test_actual_controller_build_snapshot_review_bridge_external_integration(self):
        """Actual builder/bridge functions, synthetic files and fake kernel evidence."""
        spec=importlib.util.spec_from_file_location('synthetic_controller_integration',HERE/'migration_controller.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='paper3_pure_review_synthetic_') as temp:
            repo=Path(temp)/'repo';results=repo/'results';executor=repo/'executor'
            for path in (repo,results,executor):path.mkdir(parents=True,exist_ok=True)
            changes={'REPO':str(repo),'RESULTS':str(results),'EXECUTOR':str(executor),'PYTHON':str(repo/'venv/Scripts/python.exe')}
            with patch.multiple(r,**changes):
                s,_,_=fixture();manifest=s['context']['manifest'];bundle=json.loads(base64.b64decode(s['context']['f1_context_payload_base64']))
                def write(path,data):
                    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return r.sha_bytes(data)
                for rel in manifest['critical_files_sha256']:manifest['critical_files_sha256'][rel]=write(repo/rel,b'# synthetic critical '+rel.encode())
                for rel in manifest['executor_sha256']:manifest['executor_sha256'][rel]=write(executor/rel,b'# synthetic executor '+rel.encode())
                input_run=Path(manifest['paths']['input_run']);input_run.mkdir(parents=True)
                for rel in manifest['input_files_sha256']:manifest['input_files_sha256'][rel]=write(input_run/rel,b'synthetic input metadata only')
                write(input_run/'contexts/F1.json',payload(bundle))
                manifest.pop('manifest_digest');manifest_id=r.digest(manifest);manifest['manifest_digest']=manifest_id
                initial=json.loads(base64.b64decode(s['context']['initial_manifest_payload_base64']))
                initial.update(manifest_digest=manifest_id,runtime_receipt_path='workers/initial.runtime.json')
                initial_data=payload(initial);initial_sha=write(results/'initial_state_manifest.json',initial_data)
                runtime_data=payload({'scientific_runtime':s['context']['scientific_runtime']})
                write(results/initial['runtime_receipt_path'],runtime_data)
                request=s['request'];request['manifest_digest']=manifest_id;request_data=payload(request)
                request_path=results/'execution/full/A_FULL_0001/W1_request.json';request_sha=write(request_path,request_data)
                write(request_path.parent/'W1_process.json',payload({'pid':r.WRAPPER_PID,'command':s['worker']['expected_identity']['command'],'request_sha256':request_sha}))
                entries={}
                for entry in s['raw_entries']:
                    receipt=entry['receipt'];name=r.stem(receipt['task']);csv_data=b'SYNTHETIC no performance values '+name.encode()
                    receipt.update(manifest_digest=manifest_id,initial_state_manifest_sha256=initial_sha,
                        source_bindings_digest=r.digest(manifest['critical_files_sha256']),executor_bundle_digest=r.digest(manifest['executor_sha256']),
                        runner_hash=manifest['critical_files_sha256']['scripts/run_p7_7_final.py'],implementation_hash=manifest['critical_files_sha256']['core/p7.py'],
                        protocol_hash=manifest['critical_files_sha256']['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'])
                    receipt['output_hash']=write(results/entry['csv_relative'],csv_data)
                    receipt['attempt_csv_hash']=write(results/receipt['attempt_csv_relative'],csv_data)
                    receipt['audit_hash']=write(results/receipt['audit_relative'],b'synthetic audit only')
                    receipt['rng_file_sha256']=write(results/receipt['rng_relative'],b'synthetic completed RNG artifact only')
                    receipt['runtime_receipt_sha256']=write(results/receipt['runtime_receipt_path'],runtime_data)
                    receipt_data=payload(receipt);receipt_sha=write(results/entry['receipt_relative'],receipt_data)
                    write(results/Path(receipt['rng_relative']).parent/'receipt.json',receipt_data)
                    entries[name]={'task':receipt['task'],'receipt':receipt,'receipt_sha256':receipt_sha,'csv_sha256':receipt['output_hash'],'rows':entry['input_projection']}
                def update_pending(value):
                    value['bindings'].update(source_bindings_digest=r.digest(manifest['critical_files_sha256']),final_configuration_sha256=manifest['critical_files_sha256']['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'])
                rebind_rng(s,update_pending);rng=s['pending'][0]['artifacts']['rng_before.json'];write(results/rng['relative_path'],base64.b64decode(rng['payload_base64']))
                expected=copy.deepcopy(m.EXPECTED_PROCESSES)
                expected[0]['image']=s['worker']['expected_identity']['executable'];expected[1]['image']=r.PYTHON
                fake_driver=types.SimpleNamespace(accepted_records=lambda unused:entries,stem=r.stem)
                processes=s['worker']['native_processes'];resources={'captured_utc':m.utc(),'free_commit_bytes':9*r.GIB}
                with patch.multiple(m,REPO=repo,RESULTS=results,EXECUTOR=executor,MANIFEST_DIGEST=manifest_id,EXPECTED_PROCESSES=expected),patch.object(r,'MANIFEST_DIGEST',manifest_id),patch.object(r,'INITIAL_MANIFEST_SHA256',initial_sha):
                    built=m.build_snapshot(manifest,fake_driver,processes,resources,native_suspension_observed=True,process_inventory=[{'ProcessId':r.BASE_PID},{'ProcessId':r.WRAPPER_PID}])
                    built['worker']['snapshot_stable']=True;audited=r.audit_snapshot(built)
                    self.assertEqual(audited['completed_trajectories'],5)
                    outcome={'pid':r.BASE_PID,'creation_filetime':r.BASE_FILETIME,'observed_terminated':True,'exit_code':23,'observed_utc':m.utc()}
                    termination={'stopped_processes':[outcome]};termref={'path':str(repo/'synthetic_termination.json'),'sha256':h('synthetic_termination')}
                    record={'schema':'paper3-external-worker-termination-journal-v1','snapshot':built,'snapshot_audit':audited,
                        'termination':{'pid':r.BASE_PID,'creation_time_utc':expected[0]['created_utc'],'creation_filetime':r.BASE_FILETIME,'method':'TerminateProcess','confirmed_dead':True,'exit_code':23,'worker_exception_observed':False,'terminated_utc':outcome['observed_utc']}}
                    data=payload(record);journal={'file_sha256':r.sha_bytes(data),'payload_base64':b64(data)};journalref={'path':str(repo/'synthetic_journal.json'),'sha256':journal['file_sha256']}
                    failure=m.bridge_failure(built,termination,termref,repo,journalref)
                    self.assertEqual(r.audit_external_interruption(failure,journal)['status'],'EXTERNAL_INTERRUPTION_EVIDENCE_CONSISTENT')

if __name__=='__main__':unittest.main()
