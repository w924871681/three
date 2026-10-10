"""Small explicit SYNTHETIC fixtures. They are never scientific result records."""
import base64
import copy
import csv
import hashlib
import io
from queue_store import canonical, exclusive_json, sha
from integrity import PAIR_FIELDS

METHOD_CONFIGS=(('B0','B0_Frozen_ratio10'),('B1','B1_AlwaysMaintainP50_ratio10'),('B2','B2_RAVM_ratio10'),
                ('B8','B8_AlwaysOpen_ratio10'),('P7.7','P7_7_RECOVERABILITY_GUIDED_ratio10_grid33'))

def tasks(count=20):
    all_tasks=[{'center_id':c,'seed':s,'scenario':q,'method':m,'config_id':i}
        for c in range(33000,33020) for s in (7311,7312,7313) for q in ('C0','C1','C3','C4') for m,i in METHOD_CONFIGS]
    return all_tasks[:count]

def expected(task):
    runtime={'torch_version':'SYNTHETIC_TORCH','torch_cuda_build_version':'SYNTHETIC_CUDA',
             'cuda_devices':[{'index':0,'name':'SYNTHETIC_DEVICE'}]}
    critical={'scripts/run_p7_7_final.py':'1'*64,'core/p7.py':'2'*64,'configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json':'3'*64}
    values={'manifest_digest':'4'*64,'input_bundle_digest':'5'*64,'environment_binding':'6'*64,
            'initial_state_hash':'7'*64,'initial_state_manifest_sha256':'8'*64,'scientific_runtime_signature':canonical(runtime),
            'runner_hash':'1'*64,'implementation_hash':'2'*64,'protocol_hash':'3'*64,
            'critical_files_sha256':critical,'source_bindings_digest':canonical(critical),
            'executor_bundle_digest':'9'*64,'scientific_runtime':runtime}
    values['rng_bindings']={'task':task,'input_bundle_digest':values['input_bundle_digest'],
        'source_bindings_digest':values['source_bindings_digest'],'environment_binding':values['environment_binding'],
        'final_configuration_sha256':values['protocol_hash'],'expected_initial_state_hash':values['initial_state_hash']}
    values['reference_rows']=[{key:('medium' if key=='deployment_tier' else 'SYNTHETIC_'+key+'_'+str(stage))
         for key in PAIR_FIELDS} for stage in range(1,25)]
    for row in values['reference_rows']:row['initial_state_hash']=values['initial_state_hash']
    return values

def rng_fixture(expect):
    def state(raw):return {'dtype':'uint8','shape':[len(raw)],'byte_count':len(raw),
        'base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}
    result={'schema':'paper3-original-task-torch-rng-v1','scope':'EXISTING_EXECUTION_RNG_PROVENANCE',
            'torch_version':expect['scientific_runtime']['torch_version'],
            'cuda_runtime':expect['scientific_runtime']['torch_cuda_build_version'],'manual_seed_called':False,
            'bindings':copy.deepcopy(expect['rng_bindings']),'cpu':state(b'SYNTHETIC_CPU'),
            'cuda':[{'device_index':0,'device_name':'SYNTHETIC_DEVICE','state':state(b'SYNTHETIC_GPU')}]}
    result['state_digest']=canonical(result)
    return result

def saved_fixture(root,task,mutate_rows=None,mutate_receipt=None,mutate_audit=None,mutate_runtime=None):
    from queue_store import task_stem
    expect=expected(task); stem=task_stem(task); prefix=f'attempts/{stem}/A_SYNTHETIC/DW0001'
    rows=[dict(row,stage=str(index),**{key:str(value) for key,value in task.items()},
          future_service_used_in_decision='False',online_future_service_used='False',identity_before='msa_a57_pt')
          for index,row in enumerate(expect['reference_rows'],1)]
    if mutate_rows:mutate_rows(rows)
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    payload=stream.getvalue().encode()
    for relative in (f'raw/{stem}.csv',f'{prefix}/trajectory.csv'):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
    rng=rng_fixture(expect);exclusive_json(root,f'{prefix}/rng_before.json',rng)
    runtime={'manifest_digest':expect['manifest_digest'],'environment_binding':expect['environment_binding'],
             'source_bindings_digest':expect['source_bindings_digest'],
             'scientific_runtime_signature':expect['scientific_runtime_signature'],
             'scientific_runtime':copy.deepcopy(expect['scientific_runtime'])}
    if mutate_runtime:mutate_runtime(runtime)
    exclusive_json(root,f'{prefix}/runtime.json',runtime)
    audit={'task':task,'original_run_one_code_object_preserved':True,'original_globals_mutated':False,
           'globals_overridden':['timeline_for_v2','scenario_hash_v2','initial_model'],'generator_called':False,
           'source_bindings_sha256':expect['critical_files_sha256'],'input_bundle_digest':expect['input_bundle_digest'],
           'environment_binding':expect['environment_binding'],'scientific_runtime_signature':expect['scientific_runtime_signature'],
           'scientific_runtime':copy.deepcopy(expect['scientific_runtime']),
           'timeline_access':{'violation_count':0,'completed_stages':24,'phase':'SERVICED'},
           'initial_state':{'initial_state_hash':expect['initial_state_hash'],'before_first_decision_verified':True},
           'rng_state_before_original_run':rng}
    if mutate_audit:mutate_audit(audit)
    exclusive_json(root,f'{prefix}/audit.json',audit)
    receipt={key:expect[key] for key in ('manifest_digest','input_bundle_digest','environment_binding','initial_state_hash',
        'initial_state_manifest_sha256','scientific_runtime_signature','runner_hash','implementation_hash','protocol_hash',
        'source_bindings_digest','executor_bundle_digest')}
    receipt.update(schema='paper3-batch20-replication-trajectory-receipt-v1',valid=True,task=task,trajectory_rows=24,
        full_24_stage_input_parity_checked=True,future_online_access_violation_count=0,statistics_executed=False,
        performance_based_continuation=False,output_hash=hashlib.sha256(payload).hexdigest(),
        audit_relative=f'{prefix}/audit.json',audit_hash=sha(root/f'{prefix}/audit.json'),
        rng_relative=f'{prefix}/rng_before.json',rng_file_sha256=sha(root/f'{prefix}/rng_before.json'),
        attempt_csv_relative=f'{prefix}/trajectory.csv',attempt_csv_hash=hashlib.sha256(payload).hexdigest(),
        runtime_receipt_path=f'{prefix}/runtime.json',runtime_receipt_sha256=sha(root/f'{prefix}/runtime.json'),
        stage_input_hashes=[{'stage':i,**{key:row[key] for key in ('D_upd_hash','D_assess_hash','D_srv_hash')}}
                           for i,row in enumerate(expect['reference_rows'],1)])
    for key in ('deployment_tier','deployment_filter_hash','bank_hash'):receipt[key]=expect['reference_rows'][0][key]
    receipt.update(audit_path=receipt['audit_relative'],audit_sha256=receipt['audit_hash'],
                   rng_before_path=receipt['rng_relative'],rng_before_sha256=receipt['rng_file_sha256'])
    if mutate_receipt:mutate_receipt(receipt)
    exclusive_json(root,f'raw/{stem}.integrity.json',receipt)
    return expect,receipt
