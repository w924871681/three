"""Build source-pinned activation plan; READ ONLY process identity collection.

This builder never suspends, terminates, launches a model or applies a scheduler.
"""
import argparse
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'replication_dynamic_scheduler_v1'))
from activation import REPO,RESULTS,DYNAMIC,population,old_owner_inventory
from controlled_quiesce import NativeWindowsBackend
from frozen_reference import FrozenReference
from queue_store import read_json,sha,canonical,exclusive_json,utc
from integrity import require


ROLES=((12988,'durable_supervisor',None,'compat_supervisor_003.py'),
       (14356,'delivery_successor',None,'successor.py'),(15824,'finalizer',None,'compat_finalizer.py'),
       (28384,'continuation',None,'compat_continuation.py'),
       (6260,'phase_wrapper',None,'phase_launcher.py'),(35784,'phase_base',None,'phase_launcher.py'),
       (28852,'driver_wrapper',None,'executor_driver.py'),(10852,'driver_base',None,'executor_driver.py'),
       (9788,'worker_wrapper','W1','executor_worker.py'),(30232,'worker_base','W1','executor_worker.py'),
       (25432,'worker_wrapper','W2','executor_worker.py'),(8292,'worker_base','W2','executor_worker.py'))


def ref(path):return {'path':str(Path(path).resolve(strict=True)),'sha256':sha(path)}


def check_synthetic(path,expected_sources=None):
    item=read_json(path)
    require(item.get('all_pass') is True and type(item.get('tests_run')) is int and item['tests_run']>0,
            'true positive executed synthetic test proof required')
    require(all(type(item.get(k)) is int and item[k]==0 for k in ('failures','errors','skipped')),
            'synthetic test failures/errors/skips')
    require(item.get('actual_model_execution') is False,'synthetic proof has wrong model scope')
    sources=item['implementation_sha256']
    require(all(sha(p)==v for p,v in sources.items()),'test source proof no longer matches actual source')
    if expected_sources is not None:require(sources==expected_sources,'joint test source closure differs')
    return item


def build(test_path,delivery_path,directory):
    require(not directory.exists() and directory.parent==HERE,'exclusive activation path already used')
    new_sources={str(p.resolve()):sha(p) for p in HERE.glob('*.py')}
    test=check_synthetic(test_path,new_sources)
    scheduler_path=DYNAMIC/'synthetic_tests/attempt004/results.json'
    scheduler=check_synthetic(scheduler_path)
    scheduler_sources=scheduler['implementation_sha256']
    actual_scheduler={str(p.resolve()):sha(p) for p in DYNAMIC.rglob('*.py')
                      if 'synthetic_tests' not in p.relative_to(DYNAMIC).parts}
    require(scheduler_sources==actual_scheduler,'scheduler source closure differs')
    # Delivery proof has its own strict schema. It is additionally covered by
    # the full new-directory joint test proof, never a hand-set runtime PASS.
    from dynamic_sequence import verify_proof
    delivery=verify_proof(delivery_path)
    preflight_path=HERE/'preflight/attempt001/passed.json'
    preflight=read_json(preflight_path)
    require(preflight['status']=='PASS' and preflight['scope']=='ORIGINAL_FULL_SOURCE_ENVIRONMENT_INPUT_VERIFY_FROZEN',
            'original full frozen preflight did not pass')
    reference=FrozenReference(RESULTS/'provenance_manifest.json');m=reference.manifest
    require(preflight['manifest_sha256']==sha(RESULTS/'provenance_manifest.json'),'manifest changed since full preflight')
    bindings={'manifest_digest':m['manifest_digest'],'input_bundle_digest':m['input_bundle_digest'],
        'environment_binding':m['environment_binding'],'initial_state_manifest_sha256':reference.initial_sha,
        'source_bindings_digest':canonical(m['critical_files_sha256']),
        'executor_bundle_digest':canonical(m['executor_sha256']),
        'scientific_runtime_signature':reference.initial['scientific_runtime_signature']}
    all_sources={**scheduler_sources,**new_sources}
    backend=NativeWindowsBackend(old_owner_inventory)
    require(set(backend.inventory())=={v[0] for v in ROLES},'current old-owner inventory changed')
    owners=[]
    for pid,role,worker,script in ROLES:
        handle=backend.open(pid)
        try:item=backend.info(handle,pid)
        finally:backend.close(handle)
        require(item['exit_code']==259 and script in item['command_line'] and str(REPO) in item['command_line'],
                'known producer is not the exact expected live script')
        if worker:require('--worker-id '+worker in item['command_line'] and 'A_FULL_0002' in item['command_line'],
                          'known worker command differs')
        owners.append({k:item[k] for k in ('pid','creation_filetime','image','command_line','parent_pid')})
        owners[-1]['role']=role
        if worker:owners[-1]['worker_id']=worker
    protected={str(REPO/k):v for k,v in read_json(HERE.parent/'execution_20261009/original_protected_start_sha256.json').items()}
    protected[str(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md')]='f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8'
    require(all(sha(p)==v for p,v in protected.items()),'protected old records changed')
    evidence=HERE/'activation_plan_evidence001'
    evidence.mkdir(exist_ok=False)
    certification=exclusive_json(evidence,'pre_stop_certification.json',{
        'schema':'paper3-dynamic-pre-stop-certification-v1','status':'STATIC_AND_SYNTHETIC_ROUTE_CERTIFIED',
        'manifest_digest':m['manifest_digest'],'input_bundle_digest':m['input_bundle_digest'],
        'source_bindings_digest':canonical(all_sources),'guard_extension_certified':True,
        'statistics_provenance_adapter_certified':True,'delivery_route_certified':True,
        'quiesce_synthetic_tests_passed':True,'real_model_smoke_before_full_required':True,
        'scheduler_synthetic_test_proof':ref(scheduler_path),'joint_route_test_proof':ref(test_path),
        'downstream_route_test_proof':ref(delivery_path),'full_original_preflight':ref(preflight_path),
        'actual_process_control_or_real_model_smoke_executed':False,'created_utc':utc()})
    requests={}
    for worker in ('W1','W2'):
        requests[worker]=ref(RESULTS/f'execution/full/A_FULL_0002/{worker}_request.json')
    cutover={'schema':'paper3-controlled-dynamic-cutover-contract-v1','repository':str(REPO),'results_root':str(RESULTS),
             'manifest_path':str(RESULTS/'provenance_manifest.json'),'manifest_file_sha256':sha(RESULTS/'provenance_manifest.json'),
             'old_attempt_id':'A_FULL_0002','intentional_inflight_interruption_authorized':True,
             'performance_used_for_cutover':False,'bindings':bindings,'scientific_runtime':reference.runtime,
             'snapshot_source_sha256':all_sources,'pre_stop_certification':certification,
             'requests':requests,'processes':owners,'protected_files_sha256':protected}
    files={**all_sources,str(test_path):sha(test_path),str(delivery_path):sha(delivery_path),
           str(scheduler_path):sha(scheduler_path),str(preflight_path):sha(preflight_path),
           certification['path']:certification['sha256']}
    plan={'schema':'paper3-dynamic-authorized-activation-plan-v1','created_utc':utc(),
          'directory':str(directory),'files_sha256':files,'cutover_contract':cutover,
          'scheduler_sources':scheduler_sources,'scheduler_test_proof':ref(scheduler_path),
          'delivery_route_certificate':ref(delivery_path),'new_route_test_proof':ref(test_path),
          'frozen_population':population(),'algorithm_or_input_changes_authorized':False,
          'old_trajectory_outputs_reused_only_if_integrity_valid':True,'performance_based_continuation':False}
    return exclusive_json(HERE,'AUTHORIZED_DYNAMIC_ACTIVATION_PLAN_001.json',plan)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--test-proof',type=Path,required=True)
    parser.add_argument('--delivery-proof',type=Path,required=True)
    args=parser.parse_args()
    print(build(args.test_proof,args.delivery_proof,HERE/'activation001'))


if __name__=='__main__':main()
