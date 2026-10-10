"""Explicit authorized cutover, one real RNG replay smoke, then owned scheduler.

Scientific files, F1 population and the original numerical functions stay frozen.
Only this new directory and new exclusive V3 execution attempts are published.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
DYNAMIC=HERE.parent/'replication_dynamic_scheduler_v1'
RESULTS=REPO/'results/p7_7_integrity_replication_batch20_env_v3'
BASE=Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
sys.path.insert(0,str(HERE));sys.path.insert(0,str(DYNAMIC))
from queue_store import read_json,exclusive_json,sha,canonical,task_stem
from frozen_reference import FrozenReference
from integrity import require,validate_completion,paired_groups
from native_resources import process_active


def utc():return datetime.now(timezone.utc).isoformat()


def population():
    methods=(('B0','B0_Frozen_ratio10'),('B1','B1_AlwaysMaintainP50_ratio10'),
             ('B2','B2_RAVM_ratio10'),('B8','B8_AlwaysOpen_ratio10'),
             ('P7.7','P7_7_RECOVERABILITY_GUIDED_ratio10_grid33'))
    return [{'center_id':c,'seed':s,'scenario':q,'method':m,'config_id':i}
            for c in range(33000,33020) for s in (7311,7312,7313)
            for q in ('C0','C1','C3','C4') for m,i in methods]


def old_owner_inventory():
    """Actual read-only process command inventory, including unexpected producers."""
    import json
    script=("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=json.loads(result.stdout.decode('utf-8-sig')) if result.stdout.strip() else []
    if isinstance(rows,dict):rows=[rows]
    return producer_inventory(rows,os.getpid())


def producer_inventory(rows, caller_pid):
    """Fail closed for any unknown Python command in this scientific scope."""
    names=('compat_supervisor_003.py','compat_continuation.py','compat_finalizer.py','successor.py',
           'phase_launcher.py','executor_driver.py','executor_worker.py','coordinator.py','frozen_bridge.py')
    science_names=('run_p7_7_final.py','run_p7_7_parallel.py')
    owners=[]
    for row in rows:
        pid=int(row['ProcessId'])
        if pid==caller_pid:continue
        command=row.get('CommandLine')
        require(command is not None,'inaccessible Python command prevents producer inventory')
        folded=command.casefold().replace('/','\\')
        scoped=(str(REPO).casefold() in folded or str(RESULTS).casefold() in folded
                or any(name in folded for name in science_names))
        if not scoped:continue
        require(any(name in folded for name in names),'unknown scoped Python producer: PID '+str(pid))
        owners.append(pid)
    return sorted(owners)


def verify_pins(pins):
    require(pins and all(sha(path)==digest for path,digest in pins.items()),'new source/evidence SHA changed')


def saved_inventory(reference):
    records={};proofs=[]
    for path in sorted((reference.root/'raw').glob('*.integrity.json')):
        item=read_json(path);task=item['task'];name=task_stem(task)
        proof=validate_completion(reference.root,task,reference.expected(task))
        require(name not in records,'duplicate preserved task')
        records[name]=proof['receipt_sha256'];proofs.append(proof)
    require({p.stem for p in (reference.root/'raw').glob('*.csv')}==set(records),'partial raw publication')
    return records,proofs


def contract_and_gate(plan, directory, reference, quiescence, *, mode, tasks, complete, retries, smoke=None):
    sources=plan['scheduler_sources']
    old_ids=[p['pid'] for p in plan['cutover_contract']['processes']]
    require(not any(process_active(pid) for pid in old_ids),'old scientific ownership remains active')
    verify_pins(sources)
    certificate=plan['delivery_route_certificate']
    require(sha(certificate['path'])==certificate['sha256'],'delivery certificate changed')
    gate={'schema':'paper3-dynamic-takeover-gate-v1','status':'PASS',
          'old_owners_quiescent':True,'old_process_ids':old_ids,'delivery_route_certified':True,
          'manifest_digest':reference.manifest['manifest_digest'],
          'input_bundle_digest':reference.manifest['input_bundle_digest'],
          'initial_manifest_sha256':reference.initial_sha,'sidecar_digest':canonical(sources),
          'source_extension_scope':'ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256',
          'saved_record_inventory_sha256':canonical(complete),
          'quiescence_certificate':{'path':str(directory/'quiescence/quiescence_complete.json'),
                                    'sha256':sha(directory/'quiescence/quiescence_complete.json')},
          'delivery_route_certificate':certificate,'created_utc':utc(),
          'real_model_bridge_smoke_passed':smoke is not None,
          'scientific_integrity_pass':False,'performance_based_continuation':False}
    if mode=='BRIDGE_SMOKE':
        gate.update(scope='ONE_PREDECLARED_PENDING_TASK',smoke_task_digest=canonical(tasks[0]))
    else:
        require(smoke is not None,'full must follow actual model bridge smoke')
        gate['real_model_bridge_smoke_certificate']=smoke
    name='smoke' if mode=='BRIDGE_SMOKE' else 'full'
    gate_ref=exclusive_json(directory,name+'_activation_gate.json',gate)
    attempt='A_DYNAMIC_0001' if mode=='BRIDGE_SMOKE' else 'A_DYNAMIC_0002'
    require(not (RESULTS/'execution/dynamic'/attempt).exists(),'dynamic attempt path already used')
    contract={'schema':'paper3-dynamic-run-contract-v1','execution_mode':mode,
              'manifest_path':str(RESULTS/'provenance_manifest.json'),
              'manifest_digest':reference.manifest['manifest_digest'],
              'input_bundle_digest':reference.manifest['input_bundle_digest'],
              'initial_manifest_sha256':reference.initial_sha,'initial_state_manifest':'initial_state_manifest.json',
              'original_executor_root':reference.manifest['paths']['executor_root'],
              'python_executable':reference.manifest['environment']['python_executable'],
              'source_extension_scope':gate['source_extension_scope'],
              'sidecar_sources':sources,'sidecar_digest':canonical(sources),
              'sourceproof_path':plan['scheduler_test_proof']['path'],
              'sourceproof_sha256':plan['scheduler_test_proof']['sha256'],
              'activation_gate_path':gate_ref['path'],'activation_gate_sha256':gate_ref['sha256'],
              'attempt_id':attempt,'run_relative':f'execution/dynamic/{attempt}',
              'eligible_tasks':tasks,'already_complete':complete,'retries':retries,
              'performance_based_continuation':False,'scientific_algorithm_modified':False}
    return exclusive_json(directory,name+'_contract.json',contract)


def owned_run(contract_ref, directory, name):
    contract=read_json(contract_ref['path'])
    command=[str(BASE),'-I','-S','-B',str(DYNAMIC/'coordinator.py'),'--contract',contract_ref['path']]
    with (directory/(name+'_coordinator.log')).open('xb') as log:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        start=exclusive_json(directory,name+'_coordinator_start.json',{
            'schema':'paper3-dynamic-owned-coordinator-start-v1','pid':child.pid,'command':command,
            'contract_sha256':contract_ref['sha256'],'contract_path':contract_ref['path'],'started_utc':utc()})
        code=child.wait()
        end=exclusive_json(directory,name+'_coordinator_exit.json',{
            'schema':'paper3-dynamic-owned-coordinator-exit-v1','pid':child.pid,
            'actual_exit_code':code,'contract_sha256':contract_ref['sha256'],
            'start_receipt_sha256':start['sha256'],'finished_utc':utc(),'automatic_retry':False})
    require(code==0,'actual dynamic '+name+' failed: '+str(code))
    marker=RESULTS/contract['run_relative']/'DYNAMIC_EXECUTION_COMPLETED.json'
    value=read_json(marker)
    require(value['status']=='DYNAMIC_TASKS_COMPLETED','missing actual dynamic terminal')
    return start,end,marker


def run(plan_path):
    plan=read_json(plan_path)
    require(plan['schema']=='paper3-dynamic-authorized-activation-plan-v1','activation plan schema')
    verify_pins(plan['files_sha256'])
    directory=Path(plan['directory'])
    require(directory.parent==HERE and not directory.exists(),'exclusive activation directory required')
    directory.mkdir()
    exclusive_json(directory,'started.json',{'utc':utc(),'pid':os.getpid(),'plan_path':str(plan_path),'plan_sha256':sha(plan_path)})
    try:
        from controlled_quiesce import run_quiescence,NativeWindowsBackend
        from readonly_snapshot import snapshot
        reference=FrozenReference(RESULTS/'provenance_manifest.json')
        cutover=run_quiescence(plan['cutover_contract'],directory/'quiescence',
                              NativeWindowsBackend(old_owner_inventory),snapshot)
        frozen=read_json(cutover['snapshot']['path'])
        complete,proofs=saved_inventory(reference)
        require(complete==frozen['saved_records'],'preserved inventory changed after quiescence')
        retry={task_stem(v['task']):{'failed_receipt_relative':str(Path(v['path']).relative_to(RESULTS)).replace('\\','/'),
                                   'failed_receipt_sha256':v['sha256']}
               for v in cutover['pending_interruption_receipts']}
        tasks=population();missing=[t for t in tasks if task_stem(t) not in complete]
        require(missing,'no missing task needs a scheduler takeover')
        # Predeclared outcome-blind choice: first frozen-matrix interrupted task.
        smoke_task=next((t for t in missing if task_stem(t) in retry),missing[0])
        smoke_retry={task_stem(smoke_task):retry[task_stem(smoke_task)]} if task_stem(smoke_task) in retry else {}
        smoke_contract=contract_and_gate(plan,directory,reference,cutover,mode='BRIDGE_SMOKE',
            tasks=[smoke_task],complete={},retries=smoke_retry)
        _,exit_ref,marker=owned_run(smoke_contract,directory,'smoke')
        proof=validate_completion(RESULTS,smoke_task,reference.expected(smoke_task))
        receipt=read_json(RESULTS/proof['receipt_relative']);audit=read_json(RESULTS/receipt['audit_relative'])
        if smoke_retry:
            old_pending=next(p for p in frozen['pending'] if p['task']==smoke_task)
            require(audit.get('retry_exact_failed_state_restored') is True and
                    proof['rng_state_digest']==old_pending['rng_state_digest'],'actual CPU/CUDA RNG replay differs')
        smoke=exclusive_json(directory,'real_model_bridge_smoke_certificate.json',{
            'schema':'paper3-dynamic-real-model-bridge-smoke-v1','status':'PASS','task':smoke_task,
            'contract':smoke_contract,'actual_coordinator_exit':exit_ref,'completion_marker_sha256':sha(marker),
            'completion_proof':proof,'exact_failed_rng_replay_required':bool(smoke_retry),
            'exact_failed_rng_replay_verified':True if smoke_retry else 'NOT_APPLICABLE',
            'all_24_stage_f1_initial_deployment_and_causal_fields_verified':True,
            'actual_model_execution':True,'frozen_algorithm_modified':False,'model_worker_bitwise_invariance_claimed':False,
            'completed_utc':utc()})
        complete,proofs=saved_inventory(reference)
        retry={k:v for k,v in retry.items() if k not in complete}
        full_contract=contract_and_gate(plan,directory,reference,cutover,mode='FULL',tasks=tasks,
            complete=complete,retries=retry,smoke=smoke)
        exclusive_json(directory,'full_admitted.json',{'utc':utc(),'contract':full_contract,
                       'preserved_valid':len(complete),'remaining':1200-len(complete),
                       'resource_policy_max_workers':3,'automatic_scaling_enabled_on_owned_launch':True})
        # A separate source-pinned finalizer reads the owned FULL start and exit.
        # It starts before FULL and waits; no scientific stage is inferred from PID existence.
        from dynamic_sequence import plan_for_activation, launch_owned_sequence
        route=plan_for_activation(plan,directory,full_contract,smoke)
        launch_owned_sequence(route,directory)
        owned_run(full_contract,directory,'full')
        exclusive_json(directory,'tasks_finished.json',{'utc':utc(),'status':'DYNAMIC_FULL_PROCESS_EXITED_ZERO',
                       'statistics_and_delivery_remain_owned_by_sequence':True})
    except BaseException as error:
        exclusive_json(directory,'stopped.json',{'utc':utc(),'error_type':type(error).__name__,'message':str(error),
                       'automatic_restart':False,'source_or_result_overwrite':False})
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    run(args.plan)


if __name__=='__main__':main()
