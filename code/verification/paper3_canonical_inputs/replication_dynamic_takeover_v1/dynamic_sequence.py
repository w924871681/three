"""Independent dynamic terminal -> original integrity -> frozen statistics -> delivery.

Never launches/restarts models, fabricates a static phase terminal, or overwrites
evidence. Only --execute may start the one statistics child after actual gates.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASE = REPO / 'verification/paper3_canonical_inputs'
RESULTS = REPO / 'results/p7_7_integrity_replication_batch20_env_v3'
MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1 = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
F50 = 'f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8'
METADATA_PYTHON = r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe'
OWN = ('dynamic_sequence.py','dynamic_statistics_route.py','dynamic_delivery_route.py',
       'test_dynamic_sequence.py','run_dynamic_sequence_tests.py')
ORIGINAL = {
 'replication_abrupt_recovery_v1/finalizer.py':'ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652',
 'replication_delivery_env_v3/delivery.py':'159bab5bd92d7990cb553989fb83b591dbcb913782f97a833e026ad46b38e453',
 'replication_statistics_batch20_env_v3/statistics.py':'5ccda537c83bf88f7531eeee7c9b4b82a55b23f4ba81b3c031b978ac8375e33c',
 'replication_statistics_batch20_env_v3/runtime_guard.py':'42a7fff9b32493904537e89737d5b4ed7adc2f32ab155915d3c5dfdbcc40bcb8',
 'replication_statistics_batch20_env_v3/run_statistics.py':'0346c5cdecfc595bab20f4f98b53547d215103931fd6d4aff7eb7783296e96bc',
 'replication_statistics_batch20_env_v3/test_statistics.py':'06ee1a6e1e15808bab2f8aa82b1b2aa0cea2bd94e318ceb1252a2d41edabdc86',
 'replication_executor_batch20_env_v3/provenance.py':'6eca27e3bc1c79a21a1a1643611adbb8e95e16acdd3d848d10a93914be899823',
 'replication_executor_batch20_env_v3/executor_driver.py':'33f687c4b4a9ecd25b2b7e4c891ed4a859c75e3a44a2eca9e8e31f765ad3d0c2'}

class RouteError(RuntimeError): pass
def require(ok, message):
    if not ok: raise RouteError(message)
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()
def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def read(path):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'duplicate JSON key'); out[k]=v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
                      parse_constant=lambda x:(_ for _ in ()).throw(RouteError('nonfinite JSON')))
def safe(path, root=REPO):
    lexical=Path(path).absolute(); root=Path(root).resolve()
    for part in (lexical,*lexical.parents):
        require(not part.is_symlink(),'symlink rejected')
        if part.exists(): require(not getattr(part.lstat(),'st_file_attributes',0)&0x400,'reparse path rejected')
        if part==root: break
    p=lexical.resolve(); require(p.is_relative_to(root),'path outside authorized repository')
    return p
def bound(path,digest):
    p=safe(path); require(p.is_file() and sha(p)==digest,'SHA binding differs: '+str(p)); return p
def emit(path,value):
    p=safe(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:
        f.write((json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()); f.flush(); os.fsync(f.fileno())
    return {'path':str(p),'sha256':sha(p)}
def load_module(path,name,expected=None):
    path=Path(path)
    if expected: bound(path,expected)
    require(name not in sys.modules,'private module already loaded: '+name)
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m; spec.loader.exec_module(m)
    if expected: bound(path,expected)
    return m
def package(name,root):
    require(name not in sys.modules,'fresh process/module namespace required')
    m=types.ModuleType(name); m.__path__=[str(root)]; sys.modules[name]=m
def original_modules():
    root=BASE/'replication_executor_batch20_env_v3'; name='paper3_dynamic_route_executor'
    package(name,root)
    p=load_module(root/'provenance.py',name+'.provenance',ORIGINAL['replication_executor_batch20_env_v3/provenance.py'])
    d=load_module(root/'executor_driver.py',name+'.executor_driver',ORIGINAL['replication_executor_batch20_env_v3/executor_driver.py'])
    return p,d
def source_pins(): return {str(HERE/n):sha(HERE/n) for n in OWN}
def verify_proof(path):
    p=safe(path); require(p.parent==HERE,'route proof must be in independent route directory')
    value=read(p)
    require(value.get('schema')=='paper3-dynamic-delivery-synthetic-proof-v1' and value.get('all_pass') is True,
            'dynamic delivery synthetic certification absent')
    require(type(value.get('tests_run')) is int and value['tests_run']>0 and
            all(type(value.get(k)) is int and value[k]==0 for k in ('failures','errors','skipped')),'synthetic failures/errors/skips')
    require(value.get('implementation_sha256')==source_pins(),'route source/proof closure differs')
    require(value.get('models_statistics_delivery_executed') is False,'synthetic scope differs')
    require(value.get('original_source_sha256')=={str(BASE/k):v for k,v in ORIGINAL.items()},'original source certification differs')
    for k,v in ORIGINAL.items(): bound(BASE/k,v)
    return value
def verify_plan(path):
    path=safe(path); plan=read(path)
    require(plan.get('schema')=='paper3-dynamic-delivery-plan-v1','delivery plan schema differs')
    require(plan.get('manifest_digest')==MANIFEST and plan.get('input_bundle_digest')==F1 and plan.get('expected_root_sha256')==F50,'plan frozen identities differ')
    proof=bound(plan['route_proof_path'],plan['route_proof_sha256']); verify_proof(proof)
    require(plan.get('implementation_sha256')==source_pins(),'plan source pins differ')
    cpath=bound(plan['contract_path'],plan['contract_sha256']); c=read(cpath)
    require(c.get('schema')=='paper3-dynamic-run-contract-v1' and c.get('execution_mode')=='FULL','FULL dynamic contract required')
    require(c.get('manifest_digest')==MANIFEST and c.get('input_bundle_digest')==F1,'contract science identity differs')
    require(re.fullmatch(r'A_DYNAMIC_[0-9]{4}',c.get('attempt_id','')) is not None and
            c.get('run_relative')=='execution/dynamic/'+c['attempt_id'],'dynamic attempt identity differs')
    require(canonical(c['sidecar_sources'])==c['sidecar_digest'],'scheduler sidecar digest differs')
    for n,h in c['sidecar_sources'].items(): bound(n,h)
    proof=read(bound(c['sourceproof_path'],c['sourceproof_sha256']))
    require(proof.get('schema')=='paper3-dynamic-synthetic-test-proof-v1' and proof.get('all_pass') is True and
            proof.get('actual_model_execution') is False and proof.get('model_runtime_verification')=='NOT_EXECUTED' and
            type(proof.get('tests_run')) is int and proof['tests_run']>0 and proof.get('implementation_sha256')==c['sidecar_sources'] and
            all(type(proof.get(k)) is int and proof[k]==0 for k in ('failures','errors','skipped')),'scheduler certified source closure differs')
    gate=read(bound(c['activation_gate_path'],c['activation_gate_sha256']))
    require(gate.get('schema')=='paper3-dynamic-takeover-gate-v1' and gate.get('status')=='PASS' and
            gate.get('old_owners_quiescent') is True and gate.get('delivery_route_certified') is True and
            gate.get('real_model_bridge_smoke_passed') is True,'actual takeover admission absent')
    require(gate.get('saved_record_inventory_sha256')==canonical(c['already_complete']),'retained record inventory differs')
    for k in ('manifest_digest','input_bundle_digest','sidecar_digest'): require(gate.get(k)==c[k],'gate binding differs: '+k)
    require(gate.get('source_extension_scope')=='ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256','model import extension scope differs')
    evidence=plan['activation_evidence_sha256']; require(evidence,'actual activation certificates required')
    for n,h in evidence.items(): bound(n,h)
    require(evidence.get(str(safe(c['activation_gate_path'])))==c['activation_gate_sha256'],'activation gate must be in plan evidence')
    require(evidence.get(str(safe(plan['quiescence_path'])))==plan['quiescence_sha256'],'owned quiescence certificate must be bound')
    require(evidence.get(str(safe(plan['smoke_certificate_path'])))==plan['smoke_certificate_sha256'],'real smoke certificate must be bound')
    require(read(plan['quiescence_path']).get('status')=='OLD_OWNERS_INTENTIONALLY_QUIESCED','controlled quiescence incomplete')
    smoke=read(plan['smoke_certificate_path'])
    require(smoke.get('schema')=='paper3-dynamic-real-model-bridge-smoke-v1' and smoke.get('status')=='PASS' and
            smoke.get('actual_model_execution') is True and smoke.get('all_24_stage_f1_initial_deployment_and_causal_fields_verified') is True and
            smoke.get('frozen_algorithm_modified') is False and smoke.get('model_worker_bitwise_invariance_claimed') is False,'real model smoke certificate incomplete')
    for key,path_key,sha_key in [('quiescence_certificate','quiescence_path','quiescence_sha256'),
                                 ('real_model_bridge_smoke_certificate','smoke_certificate_path','smoke_certificate_sha256'),
                                 ('delivery_route_certificate','route_proof_path','route_proof_sha256')]:
        require(gate.get(key)=={'path':plan[path_key],'sha256':plan[sha_key]},'activation certificate binding differs: '+key)
    for key in ('coordinator_start_path','coordinator_exit_path','record_root','reviewed_handoff_relative','final_handoff_relative','zip_relative'):
        p=safe(REPO/plan[key] if key.endswith('_relative') else plan[key])
        if key.endswith('_relative'): require(p.is_relative_to(REPO/'handoffs'),'output must be independent handoff child')
    return plan,c

def process_active(pid):
    require(os.name=='nt','actual route requires Windows process evidence')
    import ctypes
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.restype=ctypes.c_void_p
    h=k.OpenProcess(0x1000,False,int(pid))
    if not h:
        require(ctypes.get_last_error()==87,'process state unavailable'); return False
    try:
        code=ctypes.c_ulong(); require(k.GetExitCodeProcess(ctypes.c_void_p(h),ctypes.byref(code)),'process exit query failed')
        return code.value==259
    finally: k.CloseHandle(ctypes.c_void_p(h))
def validate_owner(start,end,contract_sha, *, active):
    require(start.get('schema')=='paper3-dynamic-owned-coordinator-start-v1' and
            end.get('schema')=='paper3-dynamic-owned-coordinator-exit-v1','owning coordinator receipt schema differs')
    require(type(start.get('pid')) is int and start['pid']>0 and end.get('pid')==start['pid'],'coordinator PID differs')
    require(start.get('contract_sha256')==end.get('contract_sha256')==contract_sha,'coordinator contract differs')
    require(type(end.get('actual_exit_code')) is int and end['actual_exit_code']==0 and
            end.get('automatic_retry') is False and not active(start['pid']),'actual coordinator clean exit unavailable')
    require(start.get('started_utc') and end.get('finished_utc'),'actual coordinator timestamps absent')
    for value in (start['started_utc'],end['finished_utc']):require(datetime.fromisoformat(value).tzinfo is not None,'coordinator timestamp timezone absent')

def validate_worker(worker,contract,worker_sha, *, active,expected_task_count):
    launch,ready,finish,exit=worker['launch'],worker['ready'],worker['finish'],worker['exit']
    require(ready.get('schema')=='paper3-dynamic-worker-ready-v1' and finish.get('schema')=='paper3-dynamic-worker-finished-v1' and
            exit.get('schema')=='paper3-dynamic-owned-worker-exit-v1','worker terminal schema differs')
    require(all(x.get('contract_sha256')==worker_sha for x in (launch,ready,finish,exit)),'worker contract binding differs')
    require(ready.get('worker_id')==finish.get('worker_id')==contract['worker_id'] and
            ready.get('execution_mode')==finish.get('execution_mode')=='FULL','worker identity/mode differs')
    require(type(launch.get('pid')) is int and launch['pid']>0 and exit.get('pid')==launch['pid'] and
            type(ready.get('pid')) is int and ready['pid']>0 and finish.get('pid')==ready['pid']==exit.get('actual_model_pid'),'worker Popen/model PID differs')
    require(type(exit.get('actual_exit_code')) is int and exit['actual_exit_code']==0 and exit.get('finished_validated') is True and
            exit.get('producer')=='OWNING_FROZEN_PROCESS_BACKEND' and exit.get('automatic_retry') is False,'actual owning worker exit unavailable')
    require(not active(launch['pid']) and not active(ready['pid']),'worker still active')
    require(finish.get('original_trajectories_returned_after_full_checks') is True and
            all(finish.get(k) is False for k in ('new_manual_seed_introduced','scientific_algorithm_modified','model_output_worker_invariance_claimed','statistics_executed')),'worker scientific scope differs')
    summary=finish['summary']
    require(summary.get('assigned_tasks')==expected_task_count and
            summary.get('completed_tasks',0)+summary.get('skipped_valid_tasks',0)==expected_task_count,'worker completion coverage differs')
def terminal_file(path):
    path=Path(path)
    if path.suffix in ('.json','.log'):return True
    match=re.fullmatch(r'(.+\.json)\.pending_([a-f0-9]{32})',path.name)
    require(match is not None,'unexpected dynamic terminal evidence file')
    canonical_path=path.with_name(match.group(1))
    require(canonical_path.is_file() and sha(canonical_path)==sha(path),'unpublished or divergent pending hardlink')
    require(os.path.samefile(path,canonical_path),'pending publication is not its retained hardlink')
    return True
def verify_admission_terminal(plan,c,gate, *, active):
    q=read(bound(plan['quiescence_path'],plan['quiescence_sha256']))
    require(q.get('schema')=='paper3-controlled-quiescence-result-v1' and q.get('status')=='OLD_OWNERS_INTENTIONALLY_QUIESCED' and
            q.get('statistics_executed') is False and q.get('scientific_integrity_pass') is False,'controlled quiescence semantics differ')
    ref=q['termination_evidence'];native=read(bound(ref['path'],ref['sha256']));outcomes=native.get('outcomes',[])
    require(native.get('schema')=='paper3-intentional-cutover-native-termination-v1' and native.get('all_twelve_old_owners_dead') is True and
            native.get('normal_completion_claimed') is False and native.get('worker_exception_invented') is False and
            len(outcomes)==len(gate['old_process_ids'])==12 and {v['pid'] for v in outcomes}==set(gate['old_process_ids']) and
            all(v.get('observed_dead') is True and type(v.get('exit_code')) is int and v['exit_code']!=259 for v in outcomes),
            'native terminal evidence does not close all prior owner identities')
    smoke=read(bound(plan['smoke_certificate_path'],plan['smoke_certificate_sha256']))
    require(smoke.get('schema')=='paper3-dynamic-real-model-bridge-smoke-v1' and smoke.get('status')=='PASS' and
            smoke.get('actual_model_execution') is True and smoke.get('all_24_stage_f1_initial_deployment_and_causal_fields_verified') is True and
            smoke.get('frozen_algorithm_modified') is False and smoke.get('model_worker_bitwise_invariance_claimed') is False,'real smoke certificate semantics differ')
    exit_ref=smoke['actual_coordinator_exit'];end=read(bound(exit_ref['path'],exit_ref['sha256']))
    start_path=Path(exit_ref['path']).with_name('smoke_coordinator_start.json');start=read(start_path)
    require(end.get('start_receipt_sha256')==sha(start_path),'actual smoke owning start differs')
    validate_owner(start,end,smoke['contract']['sha256'],active=active)
    require(q.get('completed_count')+1==len(c['already_complete']),'retained inventory does not include exactly the one smoke completion')
    return smoke

def verify_dynamic_terminal(plan,c,driver,manifest, *, active=process_active):
    """No saved outcome value is read here: only receipts, task identity and SHA."""
    require(c['eligible_tasks']==driver.tasks() and len(c['eligible_tasks'])==1200,'frozen complete ordered matrix differs')
    start=read(plan['coordinator_start_path']); end=read(plan['coordinator_exit_path'])
    validate_owner(start,end,plan['contract_sha256'],active=active)
    expected_command=[METADATA_PYTHON,'-I','-S','-B',str(BASE/'replication_dynamic_scheduler_v1/coordinator.py'),'--contract',str(safe(plan['contract_path']))]
    require(start.get('command')==expected_command and start.get('contract_path')==str(safe(plan['contract_path'])) and
            end.get('start_receipt_sha256')==sha(plan['coordinator_start_path']),'actual coordinator command/start binding differs')
    gate=read(c['activation_gate_path']); pids=gate.get('old_process_ids')
    require(isinstance(pids,list) and len(pids)>=8 and len(set(pids))==len(pids) and all(type(p) is int and p>0 and not active(p) for p in pids),'old owner inactivity evidence incomplete')
    smoke=verify_admission_terminal(plan,c,gate,active=active)
    run=safe(RESULTS/c['run_relative']); marker=read(run/'DYNAMIC_EXECUTION_COMPLETED.json')
    require(marker.get('status')=='DYNAMIC_TASKS_COMPLETED' and marker.get('completed')==1200 and
            marker.get('pairing',{}).get('complete_paired_groups')==240 and marker.get('scientific_integrity_pass') is False and
            marker.get('statistics_executed') is False and marker.get('original_pipeline_final_gate_still_required') is True,'dynamic complete marker differs')
    qpath=BASE/'replication_dynamic_scheduler_v1/queue_store.py'
    q=load_module(qpath,'paper3_dynamic_route_queue',c['sidecar_sources'][str(qpath)])
    journal=q.verify_journal(run)
    bindings={'manifest_digest':MANIFEST,'input_bundle_digest':F1,'sidecar_digest':c['sidecar_digest'],'contract_sha256':plan['contract_sha256']}
    require(journal['bindings']==bindings and journal['complete']==1200 and journal['pending']==0 and not journal['active_claims'] and journal['stopped'] is False,'dynamic journal not clean complete')
    events=[read(x) for x in sorted((run/'journal').glob('*.json'))]
    require(events[0]['body']=={'ordered_tasks':[driver.stem(t) for t in driver.tasks()],'already_complete':sorted(c['already_complete'])},'retained/frozen journal population differs')
    completed={e['body']['claim_id']:e['body'] for e in events if e['action']=='COMPLETED'}
    claimed={e['body']['claim_id']:e['body'] for e in events if e['action']=='CLAIMED'}
    require(set(completed)==set(claimed),'unfinished dynamic claim remains')
    records=driver.accepted_records(manifest,require_complete=True); groups=driver.paired_groups(records)
    require(len(records)==1200 and len(groups)==240,'original full record/pairing gates failed')
    bystem={driver.stem(e['task']):e for e in records.values()}
    lineage={}
    for name in c['already_complete']:
        identity=bystem[name]['receipt']['attempt_id'];lineage[identity]=lineage.get(identity,0)+1
    require(lineage.get('A_MINIMAL_0001',0)+lineage.get('A_FULL_0001',0)==123 and
            lineage.get('A_DYNAMIC_0001',0)==1 and set(lineage)<={'A_MINIMAL_0001','A_FULL_0001','A_FULL_0002','A_DYNAMIC_0001'},'retained original/static/smoke lineage differs')
    for name,h in c['already_complete'].items(): require(sha(RESULTS/'raw'/f'{name}.integrity.json')==h,'retained receipt changed')
    smoke_name=driver.stem(smoke['task']);smoke_proof=smoke['completion_proof']
    require(smoke_name in c['already_complete'] and smoke_proof.get('validated') is True and
            smoke_proof.get('receipt_sha256')==c['already_complete'][smoke_name] and
            smoke_proof.get('output_hash')==sha(RESULTS/'raw'/f'{smoke_name}.csv'),'retained actual smoke artifact differs')
    for item in completed.values():
        name=driver.stem(item['task']); proof=item['proof']
        require(name in bystem and proof['receipt_sha256']==sha(RESULTS/'raw'/f'{name}.integrity.json') and
                proof['output_hash']==sha(RESULTS/'raw'/f'{name}.csv'),'dynamic completion differs from actual accepted artifact')
    worker_dirs=sorted((run/'workers').iterdir()) if (run/'workers').exists() else []
    require({x.name for x in worker_dirs}>={i['worker_id'] for i in claimed.values()},'claimed worker absent')
    observed_claims=set()
    for directory in worker_dirs:
        require(directory.is_dir() and re.fullmatch(r'DW[0-9]{4,8}',directory.name),'unexpected dynamic worker directory')
        require(not (directory/'failure.json').exists(),'worker failure preserved; independent diagnosis required')
        wc=read(directory/'contract.json'); wh=sha(directory/'contract.json')
        require(wc=={**c,'worker_id':directory.name,'worker_root':str(directory)},'worker contract source differs')
        commands=sorted((directory/'commands').glob('*.json')); dones=sorted((directory/'events').glob('*.done.json'))
        require(commands and len(dones)==len(commands)-1,'commands/DONE/STOP coverage differs')
        for index,path in enumerate(commands,1): require(path.name==f'{index:06d}.json','command sequence missing')
        require(read(commands[-1])=={'action':'STOP','reason':'validated trajectory boundary; no inflight termination','contract_sha256':wh},'worker boundary STOP absent')
        for index,(command_path,done_path) in enumerate(zip(commands[:-1],dones),1):
            command,done=read(command_path),read(done_path)
            require(done_path.name==f'{index:06d}.done.json' and command.get('action')=='TASK','task/DONE sequence differs')
            claim=claimed.get(command.get('claim_id')); require(claim is not None and command=={'action':'TASK',**claim,'contract_sha256':wh},'worker command differs from journal ownership')
            require(claim['worker_id']==directory.name and claim['claim_id'] not in observed_claims,'worker duplicate/mixed claim')
            proof=completed[claim['claim_id']]['proof']
            require(done.get('contract_sha256')==wh and done.get('command_sha256')==sha(command_path) and
                    all(done.get(k)==claim[k] for k in ('claim_id','task','task_digest','worker_id')) and
                    done.get('receipt_sha256')==proof['receipt_sha256'] and done.get('output_sha256')==proof['output_hash'],'DONE receipt/command differs')
            observed_claims.add(claim['claim_id'])
        w={k:read(directory/n) for k,n in [('launch','launched.json'),('ready','ready.json'),('finish','finished.json'),('exit','actual_exit.json')]}
        validate_worker(w,wc,wh,active=active,expected_task_count=len(dones))
        expected_worker_command=[c['python_executable'],'-I','-S','-B','-X',f'pycache_prefix={RESULTS/("_dynamic_never_pycache_"+directory.name)}',
                                 str(BASE/'replication_dynamic_scheduler_v1/frozen_bridge.py'),'--contract',str(directory/'contract.json'),
                                 '--worker-id',directory.name,'--worker-root',str(directory)]
        require(w['launch'].get('command')==expected_worker_command,'worker launch command differs')
        bootstrap=read(directory/'bootstrap_request.json')
        require(w['ready'].get('bootstrap_request_sha256')==sha(directory/'bootstrap_request.json') and
                bootstrap.get('schema')=='paper3-replication-worker-request-v1' and bootstrap.get('worker_count')==3 and
                bootstrap.get('mode')=='trajectory' and bootstrap.get('retries')==c.get('retries',{}) and
                bootstrap.get('sidecar_digest')==c['sidecar_digest'] and
                bootstrap.get('tasks')==c['eligible_tasks'] and bootstrap.get('manifest_digest')==MANIFEST and
                bootstrap.get('worker_id')==directory.name and bootstrap.get('attempt_id')==c['attempt_id'] and
                bootstrap.get('dynamic_eligible_population_only') is True and bootstrap.get('performance_based_continuation') is False,'bootstrap eligible domain differs')
        for value in (w['ready'],w['finish']):
            bound(RESULTS/value['runtime_receipt_path'],value['runtime_receipt_sha256'])
    require(observed_claims==set(claimed),'journal/task command coverage differs')
    evidence={str(safe(plan[k])):sha(plan[k]) for k in ('contract_path','coordinator_start_path','coordinator_exit_path','route_proof_path')}
    evidence.update(plan['activation_evidence_sha256']); evidence.update(source_pins()); evidence.update(c['sidecar_sources'])
    evidence[str(safe(c['sourceproof_path']))]=c['sourceproof_sha256']
    for path in run.rglob('*'):
        if path.is_file() and not any(n in path.relative_to(run).parts for n in ('temp','torch','cuda')):
            terminal_file(path); evidence[str(safe(path))]=sha(path)
    return {'records':records,'groups':groups,'evidence_sha256':evidence,'journal':journal,
            'completed_dynamic_tasks':len(completed),'retained_tasks':len(c['already_complete']),
            'worker_count':len(worker_dirs),'coordinator_start':start,'coordinator_exit':end,'retained_lineage':lineage}

def closure(p,manifest):
    return p.verify_frozen(manifest,REPO,Path(manifest['paths']['input_run']),RESULTS,verify_environment=True,full=True,check_inputs=True)
def gate_value(groups):
    return {'scientific_integrity_pass':True,'manifest_digest':MANIFEST,'trajectories':1200,'paired_groups':240,'groups':groups,
            'old_results_reused':False,'all_inputs_F1':True,'future_flags_false':True,'outcomes_used_to_select_protocol':False,
            'point_estimates_or_bootstrap_not_yet_computed':True,'not_unseen_heldout':True}
def publish_full_gate(p,manifest,terminal,record):
    end=closure(p,manifest)
    require(all(end.get(k) is True for k in ('critical_scientific_bytes_unchanged','environment_file_bytes_checked','original_full_snapshot_checked','all_F1_inputs_checked')),'full frozen SHA closure failed')
    path=RESULTS/'full_experiment_integrity_gate.json'; require(not path.exists(),'canonical full gate already exists; no automatic replay')
    certificate={'schema':'paper3-dynamic-full-integrity-certificate-v1','status':'PASS','manifest_digest':MANIFEST,
                 'input_bundle_digest':F1,'dynamic_attempt_id':terminal['attempt_id'],'scientific_integrity':end,
                 'evidence_sha256':terminal['evidence_sha256'],'retained_tasks':terminal['retained_tasks'],
                 'completed_dynamic_tasks':terminal['completed_dynamic_tasks'],'trajectories':1200,'paired_groups':240,
                 'retained_lineage':terminal['retained_lineage'],
                 'static_phase_success_fabricated':False,'created_utc':utc()}
    emit(record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json',certificate)
    p.publish_json(RESULTS,'full_experiment_integrity_gate.json',gate_value(terminal['groups']))
    emit(record/'FULL_GATE_PUBLICATION.json',{'path':str(path),'sha256':sha(path),'certificate_sha256':sha(record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json')})

def full_history(plan,c,p,bindings,manifest,expected_tasks,certificate):
    """Preserve static successes/failures/unfinished controlled cuts explicitly."""
    cert=read(certificate)
    require(cert.get('schema')=='paper3-dynamic-full-integrity-certificate-v1' and cert.get('status')=='PASS' and
            cert.get('dynamic_attempt_id')==c['attempt_id'],'independent dynamic full certificate absent')
    for n,h in cert['evidence_sha256'].items(): bound(n,h); bindings[n]=h
    for path in (Path(certificate),Path(plan['_plan_path']),RESULTS/'full_experiment_integrity_gate.json'):
        bindings[str(path)]=sha(path)
    publication=read(Path(certificate).parent/'FULL_GATE_PUBLICATION.json')
    bound(certificate,publication['certificate_sha256']); bound(RESULTS/'full_experiment_integrity_gate.json',publication['sha256'])
    bindings[str(Path(certificate).parent/'FULL_GATE_PUBLICATION.json')]=sha(Path(certificate).parent/'FULL_GATE_PUBLICATION.json')
    expected={canonical(t) for t in expected_tasks}; seen=set(); attempts=[]
    for directory in sorted((RESULTS/'execution/full').iterdir()):
        require(directory.is_dir() and re.fullmatch(r'A_FULL_[0-9]{4}',directory.name),'static full history identity differs')
        for path in directory.rglob('*'):
            if path.is_file(): bindings[str(p.regular_path(path))]=p.file_sha256(path)
        tasks=[]
        for path in sorted(directory.glob('W*_request.json')):
            request=read(path); require(request.get('manifest_digest')==MANIFEST and request.get('attempt_id')==directory.name and
                    request.get('mode')=='trajectory' and request.get('performance_based_continuation') is False,'static full request binding differs')
            tasks.extend(request['tasks'])
        names=[canonical(t) for t in tasks]; require(tasks and len(names)==len(set(names)) and set(names)<=expected,'static requested population differs')
        seen.update(names); completion=directory/'completion.json'; failure=directory/'failure.json'
        require(not(completion.exists() and failure.exists()),'static terminal ambiguous')
        status='INTERRUPTED_BY_CERTIFIED_DYNAMIC_TAKEOVER'
        if completion.exists() or failure.exists():
            value=read(completion if completion.exists() else failure)
            require(value.get('manifest_digest')==MANIFEST and value.get('attempt_id')==directory.name and value.get('phase')=='full','static terminal identity differs')
            status='ORIGINAL_STATIC_COMPLETION_PRESERVED' if completion.exists() else 'ORIGINAL_STATIC_FAILURE_PRESERVED'
        attempts.append({'attempt_id':directory.name,'requested_tasks':len(tasks),'status':status,'claimed_dynamic_success':False})
    require(seen==expected,'preserved static full requests did not cover original 1195-task domain')
    return {'phase':'full','attempt_count':len(attempts)+1,'preserved_static_attempts':attempts,
            'last_attempt_id':c['attempt_id'],'phase_complete':True,'terminal_schema':'paper3-dynamic-full-integrity-certificate-v1',
            'unique_predeclared_tasks':len(expected),'retained_tasks':cert['retained_tasks'],'completed_dynamic_tasks':cert['completed_dynamic_tasks'],
            'end_integrity_pass':True,'old_static_success_fabricated':False}

def create_plan(args):
    proof=safe(args.proof); verify_proof(proof); cpath=safe(args.contract); c=read(cpath)
    evidence=read(args.activation_evidence)
    plan={'schema':'paper3-dynamic-delivery-plan-v1','manifest_digest':MANIFEST,'input_bundle_digest':F1,'expected_root_sha256':F50,
          'contract_path':str(cpath),'contract_sha256':sha(cpath),'route_proof_path':str(proof),'route_proof_sha256':sha(proof),
          'implementation_sha256':source_pins(),'activation_evidence_sha256':evidence,
          'coordinator_start_path':str(safe(args.coordinator_start)),'coordinator_exit_path':str(safe(args.coordinator_exit)),
          'quiescence_path':str(safe(args.quiescence)),'quiescence_sha256':sha(args.quiescence),
          'smoke_certificate_path':str(safe(args.smoke_certificate)),'smoke_certificate_sha256':sha(args.smoke_certificate),
          'record_root':str(safe(args.record_root)),'reviewed_handoff_relative':args.reviewed_handoff_relative,
          'final_handoff_relative':args.final_handoff_relative,'zip_relative':args.zip_relative,'created_utc':utc(),
          'automatic_model_retry':False,'automatic_statistics_retry':False,'root_publication_authorized':True}
    emit(args.plan,plan); verify_plan(args.plan); return plan
def collect_refs(value,evidence):
    if isinstance(value,dict):
        if set(('path','sha256'))<=value.keys():
            p=bound(value['path'],value['sha256']); evidence[str(p)]=value['sha256']
            if p.suffix=='.json' and str(p) not in evidence.get('_visited',[]):
                visited=evidence.setdefault('_visited',[]);visited.append(str(p));collect_refs(read(p),evidence)
        for item in value.values(): collect_refs(item,evidence)
    elif isinstance(value,list):
        for item in value: collect_refs(item,evidence)
def plan_for_activation(activation_plan,directory,full_contract_ref,smoke_ref):
    """Called by new activation after real smoke; never touches old lineage."""
    directory=safe(directory); cpath=bound(full_contract_ref['path'],full_contract_ref['sha256']); c=read(cpath)
    gate=read(bound(c['activation_gate_path'],c['activation_gate_sha256'])); route=gate['delivery_route_certificate']; verify_proof(bound(route['path'],route['sha256']))
    evidence={str(bound(n,h)):h for n,h in activation_plan['files_sha256'].items()}
    collect_refs(gate,evidence); collect_refs(smoke_ref,evidence)
    evidence.pop('_visited',None)
    for item in directory.rglob('*'):
        if item.is_file():terminal_file(item);evidence[str(safe(item))]=sha(item)
    launch_root=BASE/'autonomous_replication_execution_20261009_v3/phase_launches/full_002'
    for item in launch_root.iterdir():
        if item.is_file():evidence[str(safe(item))]=sha(item)
    evidence[str(safe(c['activation_gate_path']))]=c['activation_gate_sha256']
    q=gate['quiescence_certificate']; smoke=gate['real_model_bridge_smoke_certificate']
    prefix='handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_'+c['attempt_id']
    plan={'schema':'paper3-dynamic-delivery-plan-v1','manifest_digest':MANIFEST,'input_bundle_digest':F1,'expected_root_sha256':F50,
          'contract_path':str(cpath),'contract_sha256':full_contract_ref['sha256'],'route_proof_path':route['path'],'route_proof_sha256':route['sha256'],
          'implementation_sha256':source_pins(),'activation_evidence_sha256':evidence,
          'coordinator_start_path':str(directory/'full_coordinator_start.json'),'coordinator_exit_path':str(directory/'full_coordinator_exit.json'),
          'quiescence_path':q['path'],'quiescence_sha256':q['sha256'],'smoke_certificate_path':smoke['path'],'smoke_certificate_sha256':smoke['sha256'],
          'record_root':str(directory/'delivery_sequence001'),'reviewed_handoff_relative':prefix+'_REVIEWED_001',
          'final_handoff_relative':prefix+'_FINAL_001','zip_relative':prefix+'_FINAL_001.zip','created_utc':utc(),
          'automatic_model_retry':False,'automatic_statistics_retry':False,'root_publication_authorized':True}
    ref=emit(directory/'dynamic_delivery_plan.json',plan); verify_plan(ref['path']); return ref
def launch_owned_sequence(route,directory):
    """Authorized activation's metadata finalizer child; no scientific launch."""
    path=bound(route['path'],route['sha256']); verify_plan(path); directory=safe(directory)
    command=[METADATA_PYTHON,'-I','-S','-B',str(HERE/'dynamic_sequence.py'),'execute','--plan',str(path)]
    log=(directory/'delivery_sequence.log').open('xb')
    try: child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    finally: log.close()
    emit(directory/'delivery_sequence_launched.json',{'pid':child.pid,'command':command,'plan_sha256':route['sha256'],'started_utc':utc(),'automatic_retry':False})
    return child
def execute(path):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    plan,c=verify_plan(path); plan['_plan_path']=str(safe(path)); record=safe(plan['record_root'])
    require(not record.exists(),'exclusive sequence attempt already exists'); record.mkdir(parents=True,exist_ok=False)
    emit(record/'start.json',{'schema':'paper3-dynamic-delivery-sequence-start-v1','pid':os.getpid(),'plan_sha256':sha(path),'started_utc':utc(),'automatic_retry':False})
    try:
        while not Path(plan['coordinator_exit_path']).exists():
            require(not (Path(plan['coordinator_exit_path']).parent/'stopped.json').exists(),'owning activation stopped before FULL terminal')
            verify_plan(path); time.sleep(15)
        p,driver=original_modules(); manifest=p.read_json(RESULTS/'provenance_manifest.json')
        terminal=verify_dynamic_terminal(plan,c,driver,manifest); terminal['attempt_id']=c['attempt_id']
        terminal['evidence_sha256'][str(safe(path))]=sha(path)
        publish_full_gate(p,manifest,terminal,record)
        require(not (RESULTS/'statistics_batch20_env_v3').exists(),'statistics already exists; no replay permitted')
        cache=RESULTS/('_dynamic_statistics_'+c['attempt_id']); cache.mkdir(exist_ok=False)
        for n in ('temp','torch','cuda'): (cache/n).mkdir(exist_ok=False)
        env=dict(os.environ); env.update(TEMP=str(cache/'temp'),TMP=str(cache/'temp'),TORCH_HOME=str(cache/'torch'),CUDA_CACHE_PATH=str(cache/'cuda'))
        command=[c['python_executable'],'-I','-S','-B','-X',f'pycache_prefix={cache/"never_pycache"}',str(HERE/'dynamic_statistics_route.py'),'--plan',str(safe(path))]
        with (record/'statistics_process.log').open('xb') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            emit(record/'STATISTICS_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':utc(),'plan_sha256':sha(path)})
            code=child.wait()
        emit(record/'STATISTICS_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,'observed_utc':utc(),'automatic_retry':False})
        require(code==0,'frozen statistics child failed; preserved outputs require diagnosis')
        verify_plan(path)
        delivery=load_module(HERE/'dynamic_delivery_route.py','paper3_dynamic_delivery_route',plan['implementation_sha256'][str(HERE/'dynamic_delivery_route.py')])
        result=delivery.publish(plan,c,p,manifest,terminal)
        emit(record/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED','result':result,'finished_utc':utc()})
        return result
    except BaseException as error:
        emit(record/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,'message':str(error),'observed_utc':utc(),'automatic_retry':False})
        raise
def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='action',required=True)
    a=sub.add_parser('create-plan')
    for n in ('plan','proof','contract','activation-evidence','coordinator-start','coordinator-exit','quiescence','smoke-certificate','record-root','reviewed-handoff-relative','final-handoff-relative','zip-relative'): a.add_argument('--'+n,required=True)
    a=sub.add_parser('verify-plan'); a.add_argument('--plan',required=True)
    a=sub.add_parser('execute'); a.add_argument('--plan',required=True)
    args=ap.parse_args()
    result=create_plan(args) if args.action=='create-plan' else verify_plan(args.plan)[0] if args.action=='verify-plan' else execute(args.plan)
    print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__': main()
