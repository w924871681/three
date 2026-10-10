"""Synthetic cold-recovery fixtures only: no real inputs/models/process control."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path,PureWindowsPath
from subprocess import list2cmdline
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location('cold_synthetic_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module
r=load('cold_audit');c=load('recover')
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
             'states':[{'center_id':c,'seed':s,'initial_state_hash':initial_hashes[f'{c}_{s}'],'path':f'initial/{c}_{s}.json','sha256':h((c,s,'initial-file')),'receipt_path':f'initial/{c}_{s}.receipt.json','receipt_sha256':h((c,s,'initial-receipt'))} for c in range(33000,33020) for s in (7311,7312,7313)],
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
    for task in matrix[:123]:
        initial_hash=initial_hashes[f"{task['center_id']}_{task['seed']}"];name=r.stem(task);expected=r.expected_inputs(bundle,task,initial_hash)
        prefix=f'attempts/{name}/'+('A_MINIMAL_0001' if task in matrix[:5] else 'A_FULL_0001')+'/W1';csvsha=h((name,'csv'))
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
    task=matrix[123]
    tensor={'dtype':'uint8','shape':[4],'byte_count':4,'sha256':r.sha_bytes(b'test'),'base64':b64(b'test')}
    rng={'schema':'paper3-original-task-torch-rng-v1','manual_seed_called':False,'scope':'EXISTING_EXECUTION_RNG_PROVENANCE','torch_version':runtime['torch_version'],
         'cuda_runtime':runtime['torch_cuda_build_version'],'cpu':tensor,'cuda':[{'device_index':0,'device_name':'SYNTHETIC_GPU','state':copy.deepcopy(tensor)}],
         'bindings':{'task':task,'input_bundle_digest':r.F1_DIGEST,'source_bindings_digest':r.digest(critical),'environment_binding':manifest['environment_binding'],
                     'final_configuration_sha256':critical['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'],'expected_initial_state_hash':initial_hashes[f"{task['center_id']}_{task['seed']}"]}}
    rng['state_digest']=r.digest(rng);rng_data=payload(rng)
    snapshot['pending']=[{'task':task,'artifacts':{'rng_before.json':{'relative_path':f'attempts/{r.stem(task)}/A_FULL_0001/W1/rng_before.json','file_sha256':r.sha_bytes(rng_data),'payload_base64':b64(rng_data)}}}]
    snapshot.update(schema='paper3-abrupt-recovery-snapshot-v1',request_sha256=request_sha,
        process_absence=[{'pid':pid,'expected_creation_filetime':None,'old_exit_code':None,'observation':'OPEN_PROCESS_INVALID_PARAMETER','winerror':87,'observed_creation_filetime':None,'original_identity_absent':True,'observed_utc':snapshot['captured_utc']} for pid in r.EXPECTED_PIDS],
        active_target_processes=[],native_processes_modified=False,worker_exception_observed=False,termination_actor='NOT_VERIFIED',
        stable_file_inventory=True,initial60_accepted_records_verified=True,root_handoff_sha256=r.ROOT_SHA,
        model_or_generator_or_statistics_executed=False,performance_values_used=False,
        phase_started_utc='2026-10-09T09:47:15+00:00',old_terminal_records={k:False for k in ('sequence_stopped','finalizer_stopped','phase_launcher_finished','phase_completion','phase_failure','worker_completion','pending_failure')})
    snapshot['resources']={'sampled_utc':snapshot['captured_utc'],'free_commit_bytes':9*r.GIB,'historical_worker_private_bytes':7*r.GIB//2,
        'private_bytes_source':'CONSERVATIVE_BOUND_NOT_CURRENT_MEASUREMENT','requested_worker_count':2,'minimum_free_commit_bytes':8*r.GIB}
    evidence={r.REPO+'\\PAPER3_FINAL_REPLICATION_HANDOFF.md':r.ROOT_SHA}
    initials={}
    for item in initial['states']:
        for pk,hk in (('path','sha256'),('receipt_path','receipt_sha256')):
            path=str(PureWindowsPath(r.RESULTS)/item[pk]);initials[path]=item[hk];evidence[path]=item[hk]
    for entry in snapshot['raw_entries']:
        evidence[str(PureWindowsPath(r.RESULTS)/entry['csv_relative'])]=entry['csv_sha256']
        evidence[str(PureWindowsPath(r.RESULTS)/entry['receipt_relative'])]=entry['receipt_file_sha256']
        evidence.update({str(PureWindowsPath(r.RESULTS)/path):value for path,value in entry['bound_artifacts'].items()})
    evidence[str(PureWindowsPath(r.RESULTS)/snapshot['pending'][0]['artifacts']['rng_before.json']['relative_path'])]=snapshot['pending'][0]['artifacts']['rng_before.json']['file_sha256']
    snapshot['evidence_bindings']={'expected':evidence,'observed':copy.deepcopy(evidence)}
    snapshot['initial_file_bindings']={'expected':initials,'observed':copy.deepcopy(initials)}
    snapshot.pop('worker')
    return snapshot,manifest_id,initial_sha

class ColdAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original,cls.manifest_id,cls.initial_sha=fixture()
    def setUp(self):
        self.s=copy.deepcopy(self.original)
        self.context=patch.multiple(r,MANIFEST_DIGEST=self.manifest_id,INITIAL_MANIFEST_SHA256=self.initial_sha)
        self.context.start();self.addCleanup(self.context.stop)
    def reject(self,edit):
        edit(self.s)
        with self.assertRaises((r.ColdAuditError,ValueError)):r.audit_snapshot(self.s)
    def test_valid_exact123(self):
        out=r.audit_snapshot(self.s)
        self.assertEqual(out['completed_trajectories'],123);self.assertEqual(out['complete_paired_groups'],24)
        self.assertEqual(out['minimum_free_commit_bytes'],8*r.GIB)
    def test_missing_rng(self):self.reject(lambda s:s['pending'].clear())
    def test_extra_partial_body(self):self.reject(lambda s:s['pending'][0]['artifacts'].update({'trajectory.csv':{}}))
    def test_unpublished_completed_receipt(self):self.reject(lambda s:s['unknown_artifacts'].append('pending/receipt.json'))
    def test_wrong_pending_task(self):self.reject(lambda s:s['pending'][0]['task'].update(seed=7312))
    def test_wrong_source(self):self.reject(lambda s:s['source_bindings']['observed'].update({next(iter(s['source_bindings']['observed'])):'0'*64}))
    def test_wrong_f1(self):self.reject(lambda s:s['input_files']['observed'].update({next(iter(s['input_files']['observed'])):'0'*64}))
    def test_wrong_environment(self):
        self.reject(lambda s:s['context']['manifest'].update(environment_binding='0'*64))
    def test_rng_byte_sha(self):
        rebind_rng(self.s,lambda rng:rng['cpu'].update(sha256='0'*64))
        with self.assertRaises(r.ColdAuditError):r.audit_snapshot(self.s)
    def test_rng_invalid_base64(self):
        rebind_rng(self.s,lambda rng:rng['cpu'].update(base64='!invalid!'))
        with self.assertRaises((r.ColdAuditError,ValueError)):r.audit_snapshot(self.s)
    def test_rng_bad_state_digest(self):
        item=self.s['pending'][0]['artifacts']['rng_before.json'];rng=json.loads(base64.b64decode(item['payload_base64']))
        rng['state_digest']='0'*64;raw=payload(rng);item.update(file_sha256=r.sha_bytes(raw),payload_base64=b64(raw))
        with self.assertRaises(r.ColdAuditError):r.audit_snapshot(self.s)
    def test_rng_cuda_device(self):
        rebind_rng(self.s,lambda rng:rng['cuda'][0].update(device_name='WRONG'))
        with self.assertRaises(r.ColdAuditError):r.audit_snapshot(self.s)
    def test_rng_wrong_configuration(self):
        rebind_rng(self.s,lambda rng:rng['bindings'].update(final_configuration_sha256='0'*64))
        with self.assertRaises(r.ColdAuditError):r.audit_snapshot(self.s)
    def test_rng_new_draw_forbidden(self):
        rebind_rng(self.s,lambda rng:rng.update(manual_seed_called=True))
        with self.assertRaises(r.ColdAuditError):r.audit_snapshot(self.s)
    def test_original_process_alive(self):self.reject(lambda s:s['process_absence'][0].update(original_identity_absent=False))
    def test_access_denied_not_absence(self):self.reject(lambda s:s['process_absence'][0].update(winerror=5))
    def test_invented_exitcode(self):self.reject(lambda s:s['process_absence'][0].update(old_exit_code=1))
    def test_active_other_target_process(self):self.reject(lambda s:s['active_target_processes'].append({'ProcessId':1234}))
    def test_old_completion_conflict(self):self.reject(lambda s:s['old_terminal_records'].update(phase_completion=True))
    def test_fake_old_stopped(self):self.reject(lambda s:s['old_terminal_records'].update(sequence_stopped=True))
    def test_duplicate_completed_task(self):self.reject(lambda s:s['raw_entries'].__setitem__(1,copy.deepcopy(s['raw_entries'][0])))
    def test_changed_saved_csv_sha(self):self.reject(lambda s:s['raw_entries'][0].update(csv_sha256_rechecked='0'*64))
    def test_not123_eligible(self):self.reject(lambda s:s['raw_entries'].pop())
    def test_future_access_flag(self):self.reject(lambda s:s['raw_entries'][0]['input_projection'][0].update(online_future_service_used='True'))
    def test_wrong_stage_span(self):self.reject(lambda s:s['raw_entries'][0]['input_projection'].pop())
    def test_wrong_initial_hash(self):self.reject(lambda s:s['context']['initial_hashes'].update({'33000_7311':'0'*64}))
    def test_initial60_byte_evidence_missing(self):self.reject(lambda s:s['initial_file_bindings']['observed'].pop(next(iter(s['initial_file_bindings']['observed']))))
    def test_wrong_root_handoff(self):self.reject(lambda s:s.update(root_handoff_sha256='0'*64))
    def test_insufficient_commit(self):self.reject(lambda s:s['resources'].update(free_commit_bytes=8*r.GIB-1))
    def test_weakened_resource_threshold(self):self.reject(lambda s:s['resources'].update(minimum_free_commit_bytes=7*r.GIB))
    def test_resource_stale(self):self.reject(lambda s:s['resources'].update(sampled_utc='2026-10-09T10:00:00+00:00'))
    def test_process_absence_stale(self):self.reject(lambda s:s['process_absence'][0].update(observed_utc='2026-10-09T10:00:00+00:00'))
    def test_known_pid_reuse_passes_without_old_exitcode(self):
        self.s['process_absence'][0].update(observation='PID_REUSED',expected_creation_filetime=123,
            observed_creation_filetime=456,winerror=None)
        self.assertTrue(r.audit_snapshot(self.s)['all_old_processes_absent'])
    def test_unknown_old_pid_can_be_reused_after_verified_absence(self):
        prior='2026-10-09T11:59:00+00:00';delta=datetime.fromisoformat(prior)-datetime(1601,1,1,tzinfo=timezone.utc)
        ticks=(delta.days*86400+delta.seconds)*10_000_000+delta.microseconds*10
        self.s['process_absence'][0].update(observation='PID_REUSED',expected_creation_filetime=None,
            observed_creation_filetime=ticks+1,earlier_absence_observed_utc=prior,winerror=None)
        self.assertTrue(r.audit_snapshot(self.s)['all_old_processes_absent'])
    def test_unknown_unproved_pid_reuse_blocks(self):
        self.reject(lambda s:s['process_absence'][0].update(observation='PID_REUSED',expected_creation_filetime=None,
            observed_creation_filetime=456,winerror=None))
    def test_fake_term_actor(self):self.reject(lambda s:s.update(termination_actor='CodexDefinitelyKilledIt'))
    def test_misrepresented_native_control(self):self.reject(lambda s:s.update(native_processes_modified=True))
    def test_partial_file_inventory_changed(self):self.reject(lambda s:s.update(stable_file_inventory=False))
    def test_truthful_receipt_unknown_exit(self):
        a=r.audit_snapshot(self.s);task,phase=r.failure_receipts(self.s,a,'1'*64,'2026-10-09T12:01:00+00:00')
        self.assertEqual(task['producer'],'external-cold-recovery-observer');self.assertIsNone(task['exit_code'])
        self.assertIsNone(phase['exit_code']);self.assertIsNone(phase['child_exit_code'])
        self.assertFalse(task['worker_exception_observed']);self.assertNotIn('traceback',task)
        self.assertEqual(task['error_type'],'UnexpectedProcessDisappearance')
        self.assertFalse(phase['original_driver_terminal_record'])
    def test_failure_unaudited_cannot_publish(self):
        a=r.audit_snapshot(self.s);a['completed_trajectories']=124
        with self.assertRaises(r.ColdAuditError):r.failure_receipts(self.s,a,'1'*64,'2026-10-09T12:01:00+00:00')
    def test_duplicate_json_keys(self):
        with self.assertRaises(r.ColdAuditError):r.decoded_json(b64(b'{"x":1,"x":2}'),r.sha_bytes(b'{"x":1,"x":2}'))

class PublicationTests(unittest.TestCase):
    def test_exclusive_receipt_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root=Path(temporary);target=root/'old_failure.json';target.write_bytes(b'OLD')
            with self.assertRaises(c.RecoveryError):c.publish_new_receipt(root,'new.json',target,{'producer':'test'})
            self.assertEqual(target.read_bytes(),b'OLD')
    def test_atomic_new_hardlink_receipt(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            root=Path(temporary);out=c.publish_new_receipt(root,'new.json',root/'added.json',{'exit_code':None})
            self.assertEqual(out['sha256'],c.sha(root/'new.json'))
            self.assertEqual(c.read(root/'added.json'),{'exit_code':None})
    def test_reject_path_escape(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            with self.assertRaises(c.RecoveryError):c.checked(Path(temporary),'../existing',exists=False)
    def test_read_duplicate_keys_failclosed(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            file=Path(temporary)/'fixture.json';file.write_text('{"x":1,"x":2}')
            with self.assertRaises(c.RecoveryError):c.read(file)
    def test_no_process_control_api_in_observer(self):
        import inspect
        text=inspect.getsource(c.ReadOnlyWindowsObserver)
        for name in ('TerminateProcess','NtSuspendProcess','NtResumeProcess','CreateProcess'):
            self.assertNotIn(name,text)
    def test_import_driver_refuses_wrong_sha_before_execution(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            file=Path(temporary)/'fake.py';file.write_text('raise AssertionError("MUST_NOT_IMPORT")')
            with self.assertRaises(c.RecoveryError):c.load_checked(file,'must_not_import','0'*64)
    def test_verifier_proof_must_be_reviewed(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            path=Path(temporary)/'pins.json';path.write_text('{}')
            with self.assertRaises(c.RecoveryError):c.verify_implementation_pins(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof-output',type=Path);args=parser.parse_args()
    own=('cold_audit.py','recover.py','tests_cold_recovery.py')
    before={str(HERE/name):hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in own}
    started=datetime.now(timezone.utc).isoformat();suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    after={str(HERE/name):hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in own}
    assert before==after
    if args.proof_output:
        out=args.proof_output.resolve();assert out.parent==HERE and not out.exists()
        proof={'schema':'paper3-cold-recovery-synthetic-test-proof-v1','all_pass':result.wasSuccessful() and not result.skipped,
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'implementation_sha256':after,
            'actual_models_generators_or_statistics_executed':False,'actual_processes_modified':False,'actual_original_results_written':False}
        with out.open('x',encoding='utf-8',newline='\n') as stream:json.dump(proof,stream,sort_keys=True,indent=2);stream.write('\n')
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
if __name__=='__main__':main()
