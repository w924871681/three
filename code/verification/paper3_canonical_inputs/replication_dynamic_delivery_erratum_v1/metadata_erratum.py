"""Post-completion smoke process-count erratum; saved statistics stay byte-identical.

This program never imports models/statistics or starts/stops any child process.
It preserves every canonical V1 report, package, source, receipt and ZIP.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
BASE=HERE.parent
RESULTS=REPO/'results/p7_7_integrity_replication_batch20_env_v3'
V1=BASE/'replication_dynamic_takeover_v1'
MANIFEST='7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1='ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
F50='f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8'
ORIGINAL_FINALIZER='ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652'
ORIGINAL_DELIVERY='159bab5bd92d7990cb553989fb83b591dbcb913782f97a833e026ad46b38e453'
ORIGINAL_DELIVERY_FIXTURE='639821781882565f02ad75ff42053c9c7d6e1085f7b45911e6a3a90ce4d5b183'
V1_PINS={'dynamic_sequence.py':'1126602603e0701fe8281eb66946d14d187a2c9fc470687aa9fa3b935868b736',
         'dynamic_statistics_route.py':'703926b16c59e5b95e1761f88d3224cd46d5cbd08651d79f524b918135bc94d3',
         'dynamic_delivery_route.py':'99d43c2873ce6699d4c2b4140e7825a22f555a30fed6c04c19eefaad0476c3a5',
         'test_dynamic_sequence.py':'40a5d556ad06d11333e931cc79972812b05a5c4d013b53a97b6647e279609ab2',
         'run_dynamic_sequence_tests.py':'422cbc20dabee7c3a7c7b4e3abf6a8d4464a9db862a05e61383cdfba6da0e39f'}
V1_PROOF='793f1757821d78d26fb5e2fe367c83105b8b7acf50751edfbb8365287b72fbfd'
OWN=('metadata_erratum.py','erratum_watch.py','test_metadata_erratum.py','run_erratum_tests.py')
REPORTS=('EXECUTION_SUMMARY.md','INPUT_PARITY_AUDIT.md','EXPERIMENT_INTEGRITY_AUDIT.md',
         'CORRECTED_FINAL_STATISTICS.md','ORIGINAL_VS_REPLICATION_COMPARISON.md','SCIENTIFIC_FREEZE_DECISION.md')
DRAFT='PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'
SMOKE_ATTEMPT='A_DYNAMIC_0001_BRIDGE_SMOKE'
CORRECTED_COUNT='2 started / 1 trajectory worker'
NOTE=('\n\n## Metadata erratum: smoke process count\n\n'
      'The bridge smoke started two worker processes (DW0001 and DW0002). DW0001 alone owned and completed the one predeclared B1 trajectory; '
      'DW0002 received no TASK claim and completed a boundary STOP with zero assigned trajectories. Both owning backend actual exit receipts report zero and validate the finished receipts. '
      'The earlier smoke phase worker_count=1 was inaccurate for the actual started process count; one worker performed the one trajectory. '
      'The corrected phase table states "2 started / 1 trajectory worker". All saved statistical bytes, scientific gates, trajectory receipts, canonical V1 reports, original V1 package and ZIP are preserved. '
      'This correction changes execution metadata only and asserts no scheduling-invariant or bitwise stochastic output equivalence.\n')

class ErratumError(RuntimeError):pass
def require(ok,message):
    if not ok:raise ErratumError(message)
def utc():return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def safe(path,root=REPO):
    lexical=Path(path).absolute();root=Path(root).resolve()
    for p in (lexical,*lexical.parents):
        require(not p.is_symlink(),'symlink rejected')
        if p.exists():require(not getattr(p.lstat(),'st_file_attributes',0)&0x400,'reparse path rejected')
        if p==root:break
    p=lexical.resolve();require(p.is_relative_to(root),'path outside authorized root');return p
def read(path):
    def unique(items):
        out={}
        for k,v in items:require(k not in out,'duplicate JSON key');out[k]=v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
        parse_constant=lambda x:(_ for _ in ()).throw(ErratumError('nonfinite JSON')))
def bound(path,digest,root=REPO):
    p=safe(path,root);require(p.is_file() and sha(p)==digest,'bound SHA differs: '+str(p));return p
def emit(path,value):
    path=safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:
        f.write((json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode());f.flush();os.fsync(f.fileno())
    return {'path':str(path),'sha256':sha(path)}
def load(path,name,expected):
    path=bound(path,expected);require(name not in sys.modules,'fresh private module required')
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    bound(path,expected);return m
def own_pins():return {str(HERE/n):sha(HERE/n) for n in OWN}
def scheduler_pins():return {str(p):sha(p) for p in sorted((BASE/'replication_dynamic_scheduler_v1').rglob('*.py'))}
def verify_proof(path,digest):
    p=bound(path,digest);require(p.parent==HERE,'proof outside independent helper')
    v=read(p);require(v.get('schema')=='paper3-smoke-count-erratum-synthetic-proof-v1' and v.get('all_pass') is True and
         type(v.get('tests_run')) is int and v['tests_run']>0 and all(type(v.get(k)) is int and v[k]==0 for k in ('failures','errors','skipped')),'erratum synthetic certification failed')
    require(v.get('implementation_sha256')==own_pins() and v.get('actual_models_statistics_publication_or_process_control') is False,'erratum source/scope differs')
    require(v.get('original_finalizer_sha256')==ORIGINAL_FINALIZER and v.get('original_delivery_sha256')==ORIGINAL_DELIVERY and v.get('v1_source_sha256')==V1_PINS,'trusted helper identities differ')
    require(v.get('scheduler_source_sha256')==scheduler_pins(),'synthetic producer source closure differs')
    require(v.get('original_delivery_fixture_sha256')==ORIGINAL_DELIVERY_FIXTURE,'original synthetic fixture source differs')
    for n,h in V1_PINS.items():bound(V1/n,h)
    bound(V1/'DYNAMIC_SEQUENCE_SYNTHETIC_TEST_RESULTS_ATTEMPT003.json',V1_PROOF)
    bound(BASE/'replication_abrupt_recovery_v1/finalizer.py',ORIGINAL_FINALIZER)
    bound(BASE/'replication_delivery_env_v3/delivery.py',ORIGINAL_DELIVERY)
    bound(BASE/'replication_delivery_env_v3/test_delivery.py',ORIGINAL_DELIVERY_FIXTURE)
    return v
def process_active(pid):
    require(os.name=='nt','actual publication requires Windows process verification')
    import ctypes
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=ctypes.c_void_p
    handle=k.OpenProcess(0x1000,False,int(pid))
    if not handle:require(ctypes.get_last_error()==87,'process state unavailable');return False
    try:
        code=ctypes.c_ulong();require(k.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code)),'process exit query failed');return code.value==259
    finally:k.CloseHandle(ctypes.c_void_p(handle))
def publication_file(path):
    p=Path(path)
    if p.suffix in ('.json','.log'):return
    m=re.fullmatch(r'(.+\.json)\.pending_[a-f0-9]{32}',p.name);require(m is not None,'unknown smoke metadata file')
    original=p.with_name(m.group(1));require(original.is_file() and os.path.samefile(p,original) and sha(p)==sha(original),'divergent/unpublished pending hardlink')

def inspect_smoke(root,contract,contract_sha, *, active):
    """Pure metadata inspection; original producers own every actual exit receipt."""
    root=Path(root);require(contract.get('execution_mode')=='BRIDGE_SMOKE' and contract.get('attempt_id')=='A_DYNAMIC_0001' and
                            len(contract.get('eligible_tasks',[]))==1,'predeclared one-task bridge smoke differs')
    task=contract['eligible_tasks'][0];require(task.get('method')=='B1','actual predeclared smoke method differs')
    events=[read(p) for p in sorted((root/'journal').glob('*.json'))]
    claims=[e['body'] for e in events if e.get('action')=='CLAIMED'];done=[e['body'] for e in events if e.get('action')=='COMPLETED']
    require(len(claims)==len(done)==1 and claims[0]['task']==done[0]['task']==task and claims[0]['claim_id']==done[0]['claim_id'] and
            claims[0]['worker_id']==done[0]['worker_id']=='DW0001','smoke must have one exact owned task on DW0001')
    claim=claims[0];rows=[];total=0
    dirs=sorted((root/'workers').iterdir());require({d.name for d in dirs}=={'DW0001','DW0002'} and all(d.is_dir() for d in dirs),'actual two-worker smoke inventory differs')
    for directory in dirs:
        require(not (directory/'failure.json').exists(),'failed smoke worker requires diagnosis')
        wc=read(directory/'contract.json');h=sha(directory/'contract.json')
        require(wc=={**contract,'worker_id':directory.name,'worker_root':str(directory)},'smoke worker contract differs')
        launch,ready,finish,exit=(read(directory/n) for n in ('launched.json','ready.json','finished.json','actual_exit.json'))
        require(ready.get('schema')=='paper3-dynamic-worker-ready-v1' and finish.get('schema')=='paper3-dynamic-worker-finished-v1' and
                exit.get('schema')=='paper3-dynamic-owned-worker-exit-v1','smoke terminal schema differs')
        require(all(v.get('contract_sha256')==h for v in (launch,ready,finish,exit)) and ready.get('worker_id')==finish.get('worker_id')==directory.name and
                ready.get('execution_mode')==finish.get('execution_mode')=='BRIDGE_SMOKE','smoke worker identity/source differs')
        require(type(launch.get('pid')) is int and launch['pid']>0 and type(ready.get('pid')) is int and ready['pid']>0 and
                exit.get('pid')==launch['pid'] and finish.get('pid')==ready['pid']==exit.get('actual_model_pid'),'smoke Popen/model PID binding differs')
        require(type(exit.get('actual_exit_code')) is int and exit['actual_exit_code']==0 and exit.get('finished_validated') is True and
                exit.get('producer')=='OWNING_FROZEN_PROCESS_BACKEND' and exit.get('automatic_retry') is False and
                not active(launch['pid']) and not active(ready['pid']),'actual smoke worker clean exit absent')
        require(finish.get('original_trajectories_returned_after_full_checks') is True and
                all(finish.get(k) is False for k in ('new_manual_seed_introduced','scientific_algorithm_modified','model_output_worker_invariance_claimed','statistics_executed')),'smoke scientific scope differs')
        commands=sorted((directory/'commands').glob('*.json'));task_commands=[];stop_commands=[]
        for index,path in enumerate(commands,1):
            v=read(path);require(path.name==f'{index:06d}.json' and v.get('contract_sha256')==h,'smoke command sequence/binding differs')
            if v.get('action')=='TASK':task_commands.append((path,v))
            elif v.get('action')=='STOP':
                require(v=={'action':'STOP','reason':'validated trajectory boundary; no inflight termination','contract_sha256':h} and path==commands[-1],'smoke boundary STOP differs');stop_commands.append(v)
            else:raise ErratumError('unknown smoke worker command')
        n=len(task_commands);event_files=sorted((directory/'events').glob('*.done.json'))
        require(n==(1 if directory.name=='DW0001' else 0) and len(event_files)==n and len(stop_commands)==(0 if n else 1),'smoke trajectory/idle worker coverage differs')
        summary=finish['summary'];require(summary.get('assigned_tasks')==n and summary.get('completed_tasks',0)+summary.get('skipped_valid_tasks',0)==n,'smoke finished summary coverage differs')
        if n:
            command_path,command=task_commands[0];event=read(event_files[0]);proof=done[0]['proof']
            require(command=={'action':'TASK',**claim,'contract_sha256':h} and event.get('schema')=='paper3-dynamic-task-done-v1' and
                    all(event.get(k)==claim[k] for k in ('task','task_digest','claim_id','worker_id')) and
                    event.get('command_sha256')==sha(command_path) and event.get('contract_sha256')==h and
                    event.get('receipt_sha256')==proof['receipt_sha256'] and event.get('output_sha256')==proof['output_hash'],'smoke DONE/journal/command differs')
        rows.append({'worker_id':directory.name,'started_processes':1,'trajectory_claims':n,'completed_or_valid_skipped':n,
                     'popen_pid':launch['pid'],'model_pid':ready['pid'],'actual_exit_code':exit['actual_exit_code'],
                     'launched_utc':launch['utc'],'finished_utc':finish['finished_utc'],'exit_observed_utc':exit['observed_utc'],
                     'contract_sha256':h,'finished_sha256':sha(directory/'finished.json'),'actual_exit_sha256':sha(directory/'actual_exit.json')})
        total+=n
    require(total==1,'smoke performed more than one trajectory')
    evidence={}
    for p in root.rglob('*'):
        if p.is_file() and not any(part in ('temp','torch','cuda') for part in p.relative_to(root).parts):publication_file(p);evidence[str(p)]=sha(p)
    return {'schema':'paper3-observed-smoke-process-count-v1','started_workers':2,'trajectory_workers':1,'trajectory_tasks':1,
            'corrected_worker_count_display':CORRECTED_COUNT,'workers':rows,'evidence_sha256':evidence,'smoke_contract_sha256':contract_sha}

def correct_report(payload,name,corrected_root=None):
    """Narrow column edit and append-only disclosure, with byte-exact inverse."""
    text=payload.decode('utf-8');lines=text.splitlines(keepends=True);changed=0;original_cells=[];index=None
    for i,line in enumerate(lines):
        if line.startswith('|'):
            cells=line.rstrip('\r\n').split('|')
            fields=[v.strip() for v in cells[1:-1]]
            if 'worker_count' in fields and 'attempt' in fields:index=fields.index('worker_count')+1
            if SMOKE_ATTEMPT in fields:
                require(index is not None and cells[index].strip()=='1','unexpected source smoke worker_count cell')
                require(fields.count(SMOKE_ATTEMPT)==1,'ambiguous smoke row');original_cells.append((i,line))
                cells[index]=cells[index].replace('1',CORRECTED_COUNT,1)
                ending='\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                lines[i]='|'.join(cells)+ending;changed+=1
    expected=1 if name in ('EXECUTION_SUMMARY.md',DRAFT) else 0
    require(changed==expected,'smoke row coverage differs in '+name)
    appendix=NOTE
    if corrected_root is not None:
        corrected_root=Path(corrected_root).resolve()
        appendix+='\n## Current corrected report file index\n\nUse these six independently corrected reports:\n\n'
        appendix+='\n'.join(f'- [{n}](<{(corrected_root/n).as_posix()}>) — `{corrected_root/n}`' for n in REPORTS)+'\n'
    corrected=(''.join(lines)+appendix).encode('utf-8')
    inverse=corrected.decode('utf-8')[:-len(appendix)].splitlines(keepends=True)
    for i,line in original_cells:inverse[i]=line
    require(''.join(inverse).encode('utf-8')==payload,'nonmetadata report bytes changed')
    return corrected,{'source_sha256':hashlib.sha256(payload).hexdigest(),'corrected_sha256':hashlib.sha256(corrected).hexdigest(),
                      'smoke_cells_changed':changed,'appendix_added':True,'all_other_report_bytes_preserved':True,
                      'corrected_report_entry_paths':[str(Path(corrected_root).resolve()/n) for n in REPORTS] if corrected_root is not None else []}

def verify_zip(path,package_inventory):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();require(len(names)==len(set(names)) and set(names)==set(package_inventory),'original ZIP inventory differs')
        for n,h in package_inventory.items():require(hashlib.sha256(z.read(n)).hexdigest()==h,'original ZIP payload differs')
def verify_plan(path,expected_sha):
    path=bound(path,expected_sha);require(path.parent==HERE,'erratum plan must be in independent helper directory');plan=read(path)
    require(plan.get('schema')=='paper3-smoke-count-erratum-plan-v1' and plan.get('manifest_digest')==MANIFEST and plan.get('input_bundle_digest')==F1,'erratum plan identity differs')
    verify_proof(plan['proof_path'],plan['proof_sha256']);require(plan.get('implementation_sha256')==own_pins(),'erratum plan source closure differs')
    v1path=bound(plan['v1_plan_path'],plan['v1_plan_sha256']);v=read(v1path)
    require(v.get('schema')=='paper3-dynamic-delivery-plan-v1' and v.get('manifest_digest')==MANIFEST and v.get('input_bundle_digest')==F1 and
            v.get('implementation_sha256')=={str(V1/n):h for n,h in V1_PINS.items()} and v.get('route_proof_sha256')==V1_PROOF,'V1 plan source/scientific identity differs')
    for n,h in v['activation_evidence_sha256'].items():bound(n,h)
    full=read(bound(v['contract_path'],v['contract_sha256']))
    require(full.get('execution_mode')=='FULL' and full.get('manifest_digest')==MANIFEST and full.get('input_bundle_digest')==F1,'V1 full contract differs')
    for n,h in full['sidecar_sources'].items():bound(n,h)
    require(full['sidecar_sources']==read(plan['proof_path'])['scheduler_source_sha256'],'actual scheduler differs from tested producer sources')
    bound(full['sourceproof_path'],full['sourceproof_sha256']);bound(full['activation_gate_path'],full['activation_gate_sha256'])
    old_paths=(safe(REPO/v['reviewed_handoff_relative']),safe(REPO/v['final_handoff_relative']),safe(REPO/v['zip_relative']))
    for key in ('target_relative','zip_relative'):
        target=safe(REPO/plan[key]);require(target.is_relative_to(REPO/'handoffs') and target!=REPO/'handoffs','erratum output outside independent handoffs')
        require(all(not target.is_relative_to(old) and not old.is_relative_to(target) for old in old_paths),'erratum output aliases or nests V1')
    require(not safe(REPO/plan['zip_relative']).is_relative_to(safe(REPO/plan['target_relative'])) and Path(plan['zip_relative']).suffix=='.zip','ZIP must be separate from package')
    require(safe(plan['record_root']).parent==HERE,'erratum record must be independent direct child');return plan,v,full

def verify_completed(plan,v,full,api,f, *, active=process_active,queue_name='paper3_erratum_original_queue'):
    record=Path(v['record_root']);require(not (record/'stopped.json').exists(),'V1 sequence stopped; this erratum cannot repair failed pipeline')
    finish=read(record/'finish.json');require(finish.get('status')=='DYNAMIC_STATISTICS_DELIVERY_COMPLETED','V1 legal finish absent')
    start=read(record/'start.json');require(not active(start['pid']),'V1 sequence still owns publication')
    require(start.get('plan_sha256')==plan['v1_plan_sha256'],'V1 sequence start plan differs')
    stats_exit=read(record/'STATISTICS_PROCESS_EXIT.json');require(type(stats_exit.get('actual_exit_code')) is int and stats_exit['actual_exit_code']==0 and stats_exit.get('automatic_retry') is False,'actual statistics clean exit absent')
    owned=read(v['coordinator_exit_path']);require(type(owned.get('actual_exit_code')) is int and owned['actual_exit_code']==0 and not active(owned['pid']),'actual FULL coordinator terminal absent')
    gate=read(full['activation_gate_path']);require(all(not active(p) for p in gate['old_process_ids']),'old producer is active')
    cert_path=record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json';cert=read(cert_path)
    require(cert.get('status')=='PASS' and cert.get('manifest_digest')==MANIFEST and cert.get('trajectories')==1200 and cert.get('paired_groups')==240 and
            cert.get('static_phase_success_fabricated') is False,'independent full integrity certificate absent')
    publication=read(record/'FULL_GATE_PUBLICATION.json');bound(cert_path,publication['certificate_sha256']);bound(RESULTS/'full_experiment_integrity_gate.json',publication['sha256'])
    for n,h in cert['evidence_sha256'].items():bound(n,h)
    inactive_pids={start['pid'],owned['pid'],*gate['old_process_ids']}
    for directory in (RESULTS/full['run_relative']/'workers').iterdir():
        exit=read(directory/'actual_exit.json');finished=read(directory/'finished.json')
        require(type(exit.get('actual_exit_code')) is int and exit['actual_exit_code']==0 and exit.get('finished_validated') is True and
                exit.get('producer')=='OWNING_FROZEN_PROCESS_BACKEND' and exit.get('contract_sha256')==finished.get('contract_sha256') and
                exit.get('actual_model_pid')==finished.get('pid') and not active(exit['pid']) and not active(exit['actual_model_pid']),'FULL worker terminal no longer verified')
        inactive_pids.update((exit['pid'],exit['actual_model_pid']))
    f.PACKAGE_REL=v['reviewed_handoff_relative'];delivery=f.verify_delivery(REPO)
    reviewed=REPO/v['reviewed_handoff_relative'];package=REPO/v['final_handoff_relative'];zipped=REPO/v['zip_relative']
    result=finish['result'];require(result.get('reviewed_package')==str(reviewed) and result.get('final_package')==str(package) and result.get('zip_path')==str(zipped),'V1 finish output identity differs')
    pm=read(package/'FINAL_PACKAGE_MANIFEST.json');require(pm.get('schema')=='paper3-dynamic-final-package-v1' and pm.get('status')=='COMPLETED' and
                 pm.get('previous_root_handoff_sha256')==F50 and pm.get('manifest_digest')==MANIFEST,'V1 final package status differs')
    f.verify_inventory(package,pm['package_files_sha256'],('FINAL_PACKAGE_MANIFEST.json',))
    inventory=f.inventory(package);bound(zipped,result['zip_sha256']);verify_zip(zipped,inventory)
    draft_sha=delivery['package_files_sha256'][DRAFT]
    require(result.get('root_handoff_sha256')==pm.get('root_handoff_sha256')==draft_sha and result.get('previous_root_handoff_sha256')==F50,'V1 saved draft/root linkage differs')
    bound(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md',draft_sha)
    bound(package/'root_publication/PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md',F50)
    publication_receipt=read(package/'root_publication/PUBLICATION_RECEIPT.json')
    require(publication_receipt.get('status')=='PUBLISHED_VERIFIED_SAVED_DRAFT' and publication_receipt.get('previous_sha256')==F50 and
            publication_receipt.get('new_sha256')==draft_sha and publication_receipt.get('all_prior_bytes_archived') is True,'original root archive/publication receipt differs')
    stats_root=RESULTS/'statistics_batch20_env_v3'
    manifest=read(RESULTS/'provenance_manifest.json');fullgate=read(RESULTS/'full_experiment_integrity_gate.json');initial=read(RESULTS/'initial_state_manifest.json')
    stats=read(stats_root/'statistics_manifest.json');receipt=read(stats_root/'statistics_execution_receipt.json')
    api.validate_gate_objects(manifest,fullgate,initial,stats,receipt,MANIFEST)
    bound(stats_root/'statistics_manifest.json',receipt['statistics_manifest_sha256'])
    scientific_bindings=dict(stats['input_bindings_sha256'])
    for path in (RESULTS/'provenance_manifest.json',RESULTS/'full_experiment_integrity_gate.json',RESULTS/'initial_state_manifest.json',
                 stats_root/'statistics_manifest.json',stats_root/'statistics_execution_receipt.json',cert_path,record/'finish.json',record/'STATISTICS_PROCESS_EXIT.json'):
        scientific_bindings[str(path)]=sha(path)
    for n,h in stats['input_bindings_sha256'].items():api.bound_bytes(n,h)
    for n,h in manifest['original_protected_snapshot'].items():bound(REPO/n,h)
    for n,h in manifest['critical_files_sha256'].items():bound(REPO/n,h)
    scientific_bindings.update({str(REPO/n):h for n,h in manifest['original_protected_snapshot'].items()})
    scientific_bindings.update({str(REPO/n):h for n,h in manifest['critical_files_sha256'].items()})
    for n,h in stats['outputs_sha256'].items():bound(stats_root/n,h)
    api.validate_saved_tables({n:api.read_csv_strings(stats_root/n) for n in api.SUMMARY_NAMES})
    smoke=read(bound(v['smoke_certificate_path'],v['smoke_certificate_sha256']));sc=read(bound(smoke['contract']['path'],smoke['contract']['sha256']))
    require(smoke.get('schema')=='paper3-dynamic-real-model-bridge-smoke-v1' and smoke.get('status')=='PASS' and smoke.get('actual_model_execution') is True and
            smoke.get('frozen_algorithm_modified') is False and smoke.get('model_worker_bitwise_invariance_claimed') is False and
            smoke.get('all_24_stage_f1_initial_deployment_and_causal_fields_verified') is True and
            sc.get('manifest_digest')==MANIFEST and sc.get('input_bundle_digest')==F1 and sc.get('sidecar_sources')==full['sidecar_sources'] and
            sc.get('eligible_tasks')==[smoke['task']],'smoke source/scientific identity differs')
    smoke_exit=read(bound(smoke['actual_coordinator_exit']['path'],smoke['actual_coordinator_exit']['sha256']))
    smoke_start_path=Path(smoke['actual_coordinator_exit']['path']).with_name('smoke_coordinator_start.json');smoke_start=read(smoke_start_path)
    require(smoke_exit.get('schema')=='paper3-dynamic-owned-coordinator-exit-v1' and smoke_start.get('schema')=='paper3-dynamic-owned-coordinator-start-v1' and
            smoke_exit.get('pid')==smoke_start.get('pid') and smoke_exit.get('contract_sha256')==smoke_start.get('contract_sha256')==smoke['contract']['sha256'] and
            smoke_exit.get('start_receipt_sha256')==sha(smoke_start_path) and type(smoke_exit.get('actual_exit_code')) is int and smoke_exit['actual_exit_code']==0 and
            smoke_exit.get('automatic_retry') is False and not active(smoke_exit['pid']),'actual smoke coordinator exit linkage differs')
    inactive_pids.add(smoke_exit['pid'])
    qpath=BASE/'replication_dynamic_scheduler_v1/queue_store.py';q=load(qpath,queue_name,sc['sidecar_sources'][str(qpath)])
    smoke_root=RESULTS/sc['run_relative'];journal=q.verify_journal(smoke_root)
    require(journal['complete']==1 and journal['pending']==0 and not journal['active_claims'] and not journal['stopped'] and
            journal['bindings']=={'manifest_digest':MANIFEST,'input_bundle_digest':F1,'sidecar_digest':sc['sidecar_digest'],'contract_sha256':smoke['contract']['sha256']},'smoke journal incomplete/mixed')
    observed=inspect_smoke(smoke_root,sc,smoke['contract']['sha256'],active=active)
    for row in observed['workers']:inactive_pids.update((row['popen_pid'],row['model_pid']))
    sequence_exit='NOT_VERIFIED; legal finish and publication verified; process inactive'
    if plan.get('v1_native_exit_observation'):
        ref=plan['v1_native_exit_observation'];obs=read(bound(ref['path'],ref['sha256']))
        require(obs.get('schema')=='paper3-erratum-sequence-native-exit-observation-v1' and obs.get('producer')=='PINNED_NATIVE_QUERY_HANDLE' and
                obs.get('pid')==start['pid'] and obs.get('v1_plan_sha256')==plan['v1_plan_sha256'] and
                type(obs.get('actual_exit_code')) is int and obs['actual_exit_code']==0 and obs.get('identity_unchanged') is True,
                'actual native V1 sequence exit observation differs')
        scientific_bindings[ref['path']]=ref['sha256'];sequence_exit='0; PINNED_NATIVE_QUERY_HANDLE; external actual observation'
    return {'finish':finish,'delivery':delivery,'package_inventory':inventory,'observed_smoke':observed,'expected_old_root_sha256':draft_sha,
            'statistics_sha256':{str(stats_root/n):h for n,h in stats['outputs_sha256'].items()},
            'scientific_evidence_sha256':scientific_bindings,'inactive_process_ids':sorted(inactive_pids),
            'statistics_manifest_sha256':sha(stats_root/'statistics_manifest.json'),'statistics_receipt_sha256':sha(stats_root/'statistics_execution_receipt.json'),
            'v1_sequence_actual_exit_code':sequence_exit}

def create_plan(v1_plan,expected_v1_sha,proof,proof_sha,target,zip_relative,record_root,output,native_exit=None,prepublication_gates=None):
    verify_proof(proof,proof_sha);bound(v1_plan,expected_v1_sha);require(safe(output).parent==HERE,'plan output outside independent helper directory')
    plan={'schema':'paper3-smoke-count-erratum-plan-v1','manifest_digest':MANIFEST,'input_bundle_digest':F1,
          'v1_plan_path':str(safe(v1_plan)),'v1_plan_sha256':expected_v1_sha,'proof_path':str(safe(proof)),'proof_sha256':proof_sha,
          'implementation_sha256':own_pins(),'target_relative':target,'zip_relative':zip_relative,'record_root':str(safe(record_root)),
          'root_metadata_erratum_publication_authorized':True,'automatic_statistics_or_model_retry':False,'created_utc':utc()}
    if native_exit:bound(native_exit['path'],native_exit['sha256']);plan['v1_native_exit_observation']=native_exit
    if prepublication_gates:bound(prepublication_gates['path'],prepublication_gates['sha256']);plan['prepublication_completion_gates']=prepublication_gates
    ref=emit(output,plan);verify_plan(ref['path'],ref['sha256']);return ref
def execute(plan_path,plan_sha):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    plan,v,full=verify_plan(plan_path,plan_sha);record=safe(plan['record_root'])
    require(not record.exists() and not safe(REPO/plan['target_relative']).exists() and not safe(REPO/plan['zip_relative']).exists(),'exclusive erratum outputs already exist')
    record.mkdir(parents=True)
    emit(record/'start.json',{'schema':'paper3-smoke-count-erratum-start-v1','pid':os.getpid(),'plan_sha256':plan_sha,'started_utc':utc(),'models_statistics_executed':False})
    try:
        api=load(BASE/'replication_delivery_env_v3/delivery.py','paper3_erratum_original_delivery',ORIGINAL_DELIVERY)
        f=load(BASE/'replication_abrupt_recovery_v1/finalizer.py','paper3_erratum_original_publication',ORIGINAL_FINALIZER)
        evidence=verify_completed(plan,v,full,api,f)
        target=safe(REPO/plan['target_relative']);require(not target.exists(),'erratum package exists');target.mkdir(parents=True)
        original=REPO/v['final_handoff_relative'];reviewed=REPO/v['reviewed_handoff_relative']
        for n,h in evidence['package_inventory'].items():f.copy_verified(original/n,target/'original_v1_final_package'/n,h)
        f.copy_verified(REPO/v['zip_relative'],target/'original_v1_archive'/Path(v['zip_relative']).name,evidence['finish']['result']['zip_sha256'])
        changes={}
        for name in (*REPORTS,DRAFT):
            source=bound(reviewed/name,evidence['delivery']['package_files_sha256'][name]);payload,change=correct_report(source.read_bytes(),name,target/'corrected_reports')
            api.exclusive_bytes(target/'corrected_reports'/name,payload);changes[name]=change
        emit(target/'SMOKE_PROCESS_COUNT_EVIDENCE.json',evidence['observed_smoke'])
        for index,(n,h) in enumerate(sorted(evidence['observed_smoke']['evidence_sha256'].items()),1):
            source=Path(n);relative=source.relative_to(RESULTS/'execution/dynamic/A_DYNAMIC_0001')
            f.copy_verified(source,target/'smoke_execution_evidence'/relative,h)
        for n,h in own_pins().items():f.copy_verified(n,target/'erratum_source'/Path(n).name,h)
        f.copy_verified(plan['proof_path'],target/'erratum_source'/Path(plan['proof_path']).name,plan['proof_sha256'])
        f.copy_verified(plan_path,target/'erratum_source'/'ERRATUM_PLAN.json',plan_sha)
        erratum={'schema':'paper3-smoke-count-metadata-erratum-v1','status':'CERTIFIED_METADATA_ONLY','supersedes':str(original),
                 'original_package_inventory':evidence['package_inventory'],'original_zip_sha256':evidence['finish']['result']['zip_sha256'],
                 'started_smoke_workers':2,'trajectory_smoke_workers':1,'trajectory_tasks':1,'changed_reports':changes,
                 'statistics_files_sha256':evidence['statistics_sha256'],'statistics_manifest_sha256':evidence['statistics_manifest_sha256'],
                 'statistics_receipt_sha256':evidence['statistics_receipt_sha256'],'all_statistics_bytes_preserved':True,
                 'canonical_v1_reports_preserved':True,'v1_sources_plans_proofs_and_receipts_preserved':True,
                 'v1_sequence_actual_exit_code':evidence['v1_sequence_actual_exit_code'],'models_or_statistics_executed_by_erratum':False}
        emit(target/'ERRATUM.json',erratum)
        publication=target/'root_publication';publication.mkdir()
        def precommit():
            verify_plan(plan_path,plan_sha)
            for n,h in evidence['statistics_sha256'].items():bound(n,h)
            for n,h in evidence['scientific_evidence_sha256'].items():bound(n,h)
            for n,h in evidence['observed_smoke']['evidence_sha256'].items():bound(n,h)
            f.verify_delivery(REPO);f.verify_inventory(original,evidence['package_inventory'])
            bound(REPO/v['zip_relative'],evidence['finish']['result']['zip_sha256'])
            require(not process_active(read(Path(v['record_root'])/'start.json')['pid']),'V1 publication owner became active')
            require(all(not process_active(pid) for pid in read(full['activation_gate_path'])['old_process_ids']),'old producer became active')
            require(all(not process_active(pid) for pid in evidence['inactive_process_ids']),'a completed producer became active')
        require(plan.get('root_metadata_erratum_publication_authorized') is True,'metadata root publication not authorized')
        newdraft=target/'corrected_reports'/DRAFT
        root_sha=f.publish_root(REPO,publication,evidence['expected_old_root_sha256'],newdraft,sha(newdraft),precommit=precommit)
        manifest={'schema':'paper3-superseding-metadata-erratum-package-v1','status':'COMPLETED','manifest_digest':MANIFEST,'input_bundle_digest':F1,
                  'supersedes_final_package':str(original),'supersedes_zip_sha256':evidence['finish']['result']['zip_sha256'],
                  'previous_root_handoff_sha256':evidence['expected_old_root_sha256'],'root_handoff_sha256':root_sha,
                  'earliest_archived_root_handoff_sha256':F50,'statistics_bytes_unchanged':True,'canonical_v1_results_reports_modified':False,
                  'package_files_sha256':f.inventory(target),'manifest_self_and_sidecar_excluded':True,'created_utc':utc()}
        emit(target/'ERRATUM_MANIFEST.json',manifest)
        api.exclusive_bytes(target/'ERRATUM_MANIFEST.json.sha256',(sha(target/'ERRATUM_MANIFEST.json')+'  ERRATUM_MANIFEST.json\n').encode())
        f.verify_inventory(target,manifest['package_files_sha256'],('ERRATUM_MANIFEST.json','ERRATUM_MANIFEST.json.sha256'))
        zip_path=safe(REPO/plan['zip_relative']);zip_sha=f.make_zip(target,zip_path)
        result={'status':'SMOKE_COUNT_METADATA_ERRATUM_COMPLETED','package':str(target),'zip':str(zip_path),'zip_sha256':zip_sha,
                'root_handoff_sha256':root_sha,'previous_root_handoff_sha256':evidence['expected_old_root_sha256'],'statistics_bytes_unchanged':True}
        emit(record/'finish.json',result);return result
    except BaseException as error:
        emit(record/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,'message':str(error),'automatic_retry':False,'observed_utc':utc()});raise
def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    a=sub.add_parser('create-plan')
    for n in ('v1-plan','v1-plan-sha256','proof','proof-sha256','target-relative','zip-relative','record-root','output'):a.add_argument('--'+n,required=True)
    for name in ('verify-plan','execute'):
        a=sub.add_parser(name);a.add_argument('--plan',required=True);a.add_argument('--plan-sha256',required=True)
    args=ap.parse_args()
    if args.action=='create-plan':result=create_plan(args.v1_plan,args.v1_plan_sha256,args.proof,args.proof_sha256,args.target_relative,args.zip_relative,args.record_root,args.output)
    elif args.action=='verify-plan':result=verify_plan(args.plan,args.plan_sha256)[0]
    else:result=execute(args.plan,args.plan_sha256)
    print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__':main()
