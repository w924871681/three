"""Authorized metadata compatibility recovery; frozen scientific code is reused.

The existing full gate is preserved and independently revalidated, never
republished. Only the legacy full-phase metadata callback is adapted. Model,
generator and numerical statistics implementation bytes remain unchanged.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
REPO=BASE.parents[1]
V1=BASE/'replication_dynamic_takeover_v1'
R1=BASE/'replication_dynamic_delivery_recovery_v1'
RESULTS=REPO/'results/p7_7_integrity_replication_batch20_env_v3'
OLD_PLAN=R1/'RECOVERY_DELIVERY_PLAN_001.json'
OLD_SHA='4b0af114a1d3512192dbe278d5ad49172bab685e8bf749890b58198a731617ac'
CERT=R1/'sequence001/DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json'
CERT_SHA='027cce63906b5879d69c35f9d95eddd5e3776189a2b4a1f60628733e773bff58'
GATE_SHA='a33555e7f6083229aff520fe6e0a8f6ad11b2ef468cda3f8929be4cbe9240a97'
S_SHA='1126602603e0701fe8281eb66946d14d187a2c9fc470687aa9fa3b935868b736'
R_SHA='a3873cd620545d2bd951a976328cbb36a5674a7a90b142d65f6daa65599e7a95'
PLAN=HERE/'RECOVERY_DELIVERY_PLAN_002.json'
PREPARED=HERE/'PREPARED_METADATA_PLAN_002.json'
RECORD=HERE/'sequence002'
CONTROL=HERE/'supervisor002'
CACHE=RESULTS/'_dynamic_delivery_recovery002_cache'
STATS_CACHE=RESULTS/'_dynamic_statistics_recovery002_cache'
OWN=('pipeline.py','history_compat.py','test_history_compat.py')


def sequence():
    path=V1/'dynamic_sequence.py'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=S_SHA:raise RuntimeError('frozen sequence changed')
    name='paper3_dynamic_sequence_api'
    spec=importlib.util.spec_from_file_location(name,path)
    s=importlib.util.module_from_spec(spec);sys.modules[name]=s;spec.loader.exec_module(s)
    return s


def environment_builder(s):
    # Deliberately lazy: this metadata helper must not enter the statistics child.
    return s.load_module(R1/'recovery.py','paper3_v2_environment_builder',R_SHA).build_env


def own_pins(s):return {str(HERE/n):s.sha(HERE/n) for n in OWN}


def history_module(s,plan):
    path=HERE/'history_compat.py'
    return s.load_module(path,'paper3_v2_legacy_metadata',plan['activation_evidence_sha256'][str(path)])


def configure_statistics(s,plan,c):
    route=s.load_module(V1/'dynamic_statistics_route.py','paper3_v2_original_statistics_route',
                        plan['implementation_sha256'][str(V1/'dynamic_statistics_route.py')])
    stats=route.configure(plan,c);h=history_module(s,plan);original=stats._phase_evidence
    def phase(p,bindings,manifest,phase,expected_tasks):
        if phase!='full':return original(p,bindings,manifest,phase,expected_tasks)
        result=h.full_history(s,plan,c,p,bindings,manifest,expected_tasks,
                              Path(plan['record_root'])/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json')
        for n,value in plan['activation_evidence_sha256'].items():s.bound(n,value);bindings[n]=value
        for path in (Path(plan['_plan_path']),CERT,Path(plan['record_root'])/'FULL_GATE_REUSE_RECEIPT.json'):
            bindings[str(path)]=s.sha(path)
        return result
    stats._phase_evidence=phase
    guard=sys.modules[stats.__package__+'.runtime_guard']
    allowed={str(V1/n):plan['implementation_sha256'][str(V1/n)]
             for n in ('dynamic_sequence.py','dynamic_statistics_route.py')}
    q=BASE/'replication_dynamic_scheduler_v1/queue_store.py';allowed[str(q)]=c['sidecar_sources'][str(q)]
    for n in ('pipeline.py','history_compat.py'):
        allowed[str(HERE/n)]=plan['activation_evidence_sha256'][str(HERE/n)]
    route.install_origin_extension(guard,allowed)
    return stats


def copy_gate(s,record):
    s.bound(CERT,CERT_SHA);s.bound(RESULTS/'full_experiment_integrity_gate.json',GATE_SHA)
    source=R1/'sequence001/FULL_GATE_PUBLICATION.json';publication=s.read(source)
    s.require(publication['certificate_sha256']==CERT_SHA and publication['sha256']==GATE_SHA,'existing gate publication differs')
    for origin,target in ((CERT,record/CERT.name),(source,record/source.name)):
        with target.open('xb') as stream:stream.write(origin.read_bytes())
        s.require(s.sha(target)==s.sha(origin),'gate byte copy differs')
    return s.emit(record/'FULL_GATE_REUSE_RECEIPT.json',{
        'status':'REUSED_EXISTING_FULL_GATE_NOT_REPUBLISHED','source_certificate':{'path':str(CERT),'sha256':CERT_SHA},
        'source_publication':{'path':str(source),'sha256':s.sha(source)},'copied_certificate_sha256':CERT_SHA,
        'canonical_gate_sha256':GATE_SHA,'observed_utc':s.utc(),'new_scientific_success_fabricated':False})


def prepare_metadata():
    s=sequence();s.bound(OLD_PLAN,OLD_SHA);old,c=s.verify_plan(OLD_PLAN)
    s.require(s.read(R1/'sequence001/STATISTICS_PROCESS_EXIT.json')['actual_exit_code']==1 and
              s.read(R1/'sequence001/stopped.json')['status']=='STOPPED_FOR_DIAGNOSIS','prior statistics failure differs')
    s.require(not s.process_active(s.read(R1/'sequence001/start.json')['pid']),'prior sequence still active')
    for path in (PLAN,PREPARED,RECORD,CONTROL,CACHE,STATS_CACHE,RESULTS/'statistics_batch20_env_v3'):
        s.require(not path.exists(),'recovery output already exists: '+str(path))
    s.require(s.sha(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md')==s.F50,'root already published')
    pins=own_pins(s)
    tests=subprocess.run([s.METADATA_PYTHON,'-I','-S','-B',str(HERE/'test_history_compat.py')],capture_output=True,text=True,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    s.require(tests.returncode==0,'legacy metadata tests failed: '+tests.stderr)
    s.require(pins==own_pins(s),'new source changed during tests')
    proof=s.emit(HERE/'LEGACY_METADATA_COMPATIBILITY_TEST_PROOF_002.json',{
        'status':'PASS','unit_test_actual_exit_code':tests.returncode,'unit_test_log':tests.stdout+tests.stderr,
        'implementation_sha256':pins,'models_generators_statistics_executed':False,'created_utc':s.utc()})
    plan=dict(old);plan['activation_evidence_sha256']=dict(old['activation_evidence_sha256'])
    additional=[OLD_PLAN,CERT,R1/'sequence001/FULL_GATE_PUBLICATION.json',R1/'sequence001/STATISTICS_PROCESS_START.json',
                R1/'sequence001/STATISTICS_PROCESS_EXIT.json',R1/'sequence001/statistics_process.log',R1/'sequence001/stopped.json',
                R1/'native_observer002/SEQUENCE_NATIVE_EXIT.json',R1/'native_observer002/stopped.json',
                *(HERE/n for n in OWN),Path(proof['path'])]
    for path in additional:plan['activation_evidence_sha256'][str(path)]=s.sha(path)
    prefix='handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_RECOVERY_002'
    plan.update(record_root=str(RECORD),reviewed_handoff_relative=prefix+'_REVIEWED_001',
                final_handoff_relative=prefix+'_FINAL_001',zip_relative=prefix+'_FINAL_001.zip',created_utc=s.utc(),
                legacy_metadata_compatibility={'original_worker_missing_field_semantics_preserved':True,
                    'historical_requests_modified':False,'original_numerical_statistics_modified':False,
                    'existing_full_certificate':{'path':str(CERT),'sha256':CERT_SHA},'proof':proof})
    for key in ('reviewed_handoff_relative','final_handoff_relative','zip_relative'):
        s.require(not (REPO/plan[key]).exists(),'handoff output collision')
    for path in (BASE/'replication_dynamic_delivery_erratum_v1/ERRATUM_RECOVERY_PLAN_002.json',
                 BASE/'replication_dynamic_delivery_erratum_v1/erratum_recovery002',
                 REPO/'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001',
                 REPO/'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001.zip'):
        s.require(not path.exists(),'erratum output collision')
    for cache in (CACHE,STATS_CACHE):
        cache.mkdir()
        for name in ('temp','torch','cuda'):(cache/name).mkdir()
    return s.emit(PREPARED,plan)


def metadata_preflight():
    """Actual original metadata consumers, before any full hash scan/numerics."""
    s=sequence();plan=s.read(PREPARED);s.verify_plan(PREPARED);plan['_plan_path']=str(PREPARED)
    c=s.read(plan['contract_path']);p,driver=s.original_modules();manifest=p.read_json(RESULTS/'provenance_manifest.json')
    # A separate preview record truthfully reuses the already certified bytes.
    preview=HERE/'metadata_preflight002';s.require(not preview.exists(),'preflight already exists');preview.mkdir()
    copy_gate(s,preview)
    effective=dict(plan);effective['record_root']=str(preview)
    stats=configure_statistics(s,effective,c);bindings={}
    population=[{'center_id':center,'seed':seed} for center in stats.CENTERS for seed in stats.SEEDS]
    history=[]
    for phase,tasks in (('initial',population),('minimal',driver.tasks()[:5]),('full',driver.tasks()[5:])):
        result=stats._phase_evidence(p,bindings,manifest,phase,tasks)
        history.append(result)
    forbidden=[n for n in sys.modules if n.split('.')[0] in {'numpy','torch','scipy','sklearn','river','core','imported'}]
    s.require(not forbidden,'scientific dependency loaded in metadata-only preflight')
    return s.emit(HERE/'REAL_THREE_PHASE_METADATA_PREFLIGHT_002.json',{
        'status':'PASS','phase_history':history,'bound_file_count':len(bindings),
        'input_bindings_sha256':bindings,'models_generators_statistics_executed':False,
        'scientific_modules_imported':forbidden,'created_utc':s.utc()})


def finalize_plan():
    s=sequence();plan=s.read(PREPARED);proof=HERE/'REAL_THREE_PHASE_METADATA_PREFLIGHT_002.json'
    s.require(s.read(proof)['status']=='PASS','real metadata preflight absent')
    guard_proof=HERE/'REAL_STATISTICS_IMPORT_GUARD_PREFLIGHT_002.json'
    s.require(s.read(guard_proof)['status']=='PASS','actual clean-process import guard preflight absent')
    plan['activation_evidence_sha256'][str(PREPARED)]=s.sha(PREPARED)
    plan['activation_evidence_sha256'][str(proof)]=s.sha(proof)
    plan['activation_evidence_sha256'][str(guard_proof)]=s.sha(guard_proof)
    ref=s.emit(PLAN,plan);s.verify_plan(PLAN);return ref


def guard_preflight():
    """Exercise the real import/read guard in a fresh frozen process, no numerics."""
    s=sequence();plan,c=s.verify_plan(PREPARED);plan['_plan_path']=str(PREPARED)
    plan['record_root']=str(HERE/'metadata_preflight002')
    p,_=s.original_modules();manifest=p.read_json(RESULTS/'provenance_manifest.json')
    p._verify_current_environment(manifest['environment'],check_files=False)
    p.require_isolation(RESULTS)
    stats=configure_statistics(s,plan,c)
    proof=HERE/'REAL_THREE_PHASE_METADATA_PREFLIGHT_002.json';metadata=s.read(proof)
    s.require(metadata['status']=='PASS','metadata preflight absent')
    bindings=dict(metadata['input_bindings_sha256']);bindings[str(proof)]=s.sha(proof)
    for path in Path(stats.__file__).parent.rglob('*.py'):bindings[str(path)]=s.sha(path)
    guard=sys.modules[stats.__package__+'.runtime_guard']
    observed=guard.install_statistics_import_guard(manifest,bindings,p)
    forbidden=[n for n in sys.modules if n.split('.')[0] in {'numpy','torch','scipy','sklearn','river','core','imported'}]
    s.require(not forbidden,'scientific dependency loaded in import-guard preflight')
    loaded={str(Path(m.__file__).resolve()):s.sha(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and not m.__file__.startswith('<')
            and Path(m.__file__).resolve().is_relative_to(REPO)
            and not Path(m.__file__).resolve().is_relative_to(Path(manifest['environment']['site_packages_root']).parent)}
    return s.emit(HERE/'REAL_STATISTICS_IMPORT_GUARD_PREFLIGHT_002.json',{
        'status':'PASS','original_guard_actually_installed':True,'guard_proof':observed,
        'sys_executable':sys.executable,'isolated':bool(sys.flags.isolated),'no_site':bool(sys.flags.no_site),
        'no_bytecode':sys.dont_write_bytecode,'loaded_project_sources_sha256':loaded,
        'models_generators_statistics_executed':False,
        'scientific_modules_imported':forbidden,'created_utc':s.utc()})


def statistics(path):
    s=sequence();plan,c=s.verify_plan(path);plan['_plan_path']=str(path)
    stats=configure_statistics(s,plan,c)
    return stats.run_statistics(REPO,RESULTS,expected_manifest_digest=s.MANIFEST)


def execute(path,expected_sha):
    s=sequence();s.bound(path,expected_sha);plan,c=s.verify_plan(path);plan['_plan_path']=str(path)
    s.require(path==PLAN and not RECORD.exists(),'exclusive new sequence exists');RECORD.mkdir()
    s.emit(RECORD/'start.json',{'schema':'paper3-dynamic-delivery-sequence-start-v1','producer':'AUTHORIZED_LEGACY_METADATA_RECOVERY_V2',
        'pid':os.getpid(),'plan_sha256':expected_sha,'started_utc':s.utc(),'automatic_retry':False,'models_restarted':False})
    try:
        copy_gate(s,RECORD)
        p,driver=s.original_modules();manifest=p.read_json(RESULTS/'provenance_manifest.json')
        terminal=s.verify_dynamic_terminal(plan,c,driver,manifest);terminal['attempt_id']=c['attempt_id']
        terminal['evidence_sha256'][str(path)]=expected_sha
        end=s.closure(p,manifest)
        s.require(s.read(RESULTS/'full_experiment_integrity_gate.json')['groups']==terminal['groups'],'accepted pairing differs from saved gate')
        s.emit(RECORD/'FULL_GATE_REVALIDATION.json',{'status':'PASS','scientific_integrity':end,
            'trajectories':len(terminal['records']),'paired_groups':len(terminal['groups']),
            'existing_gate_sha256':GATE_SHA,'certificate_republished':False,'created_utc':s.utc()})
        env=environment_builder(s)(manifest['environment'],STATS_CACHE)
        command=[manifest['environment']['python_executable'],'-I','-S','-B','-X',
                 'pycache_prefix='+str(STATS_CACHE/'never_pycache'),str(HERE/'pipeline.py'),'statistics','--plan',str(path)]
        with (RECORD/'statistics_process.log').open('xb') as log:
            child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(RECORD/'STATISTICS_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':s.utc(),'plan_sha256':expected_sha})
            code=child.wait()
        s.emit(RECORD/'STATISTICS_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,'producer':'OWNING_POPEN_WAIT',
                                                   'observed_utc':s.utc(),'automatic_retry':False})
        s.require(code==0,'frozen statistics with metadata compatibility failed; no retry')
        route=s.load_module(V1/'dynamic_delivery_route.py','paper3_v2_original_delivery_route',
                            plan['implementation_sha256'][str(V1/'dynamic_delivery_route.py')])
        result=route.publish(plan,c,p,manifest,terminal)
        return s.emit(RECORD/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED','result':result,'finished_utc':s.utc()})
    except BaseException as error:
        s.emit(RECORD/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,
               'message':str(error),'observed_utc':s.utc(),'automatic_retry':False});raise


def supervise(path,expected_sha):
    s=sequence();s.bound(path,expected_sha);plan,c=s.verify_plan(path)
    s.require(not CONTROL.exists(),'supervisor exists');CONTROL.mkdir()
    r=s.load_module(R1/'recovery.py','paper3_v2_metadata_supervisor',R_SHA)
    watch=s.load_module(r.ERRATUM/'erratum_watch.py','paper3_v2_frozen_native_observer',r.WATCH_SHA)
    observer=watch.NativeObserver();handle=None
    s.emit(CONTROL/'start.json',{'pid':os.getpid(),'plan_sha256':expected_sha,'started_utc':s.utc(),'automatic_retry':False})
    try:
        manifest=s.read(RESULTS/'provenance_manifest.json');env=r.build_env(manifest['environment'],CACHE)
        command=[manifest['environment']['python_executable'],'-I','-S','-B','-X',
            'pycache_prefix='+str(CACHE/'never_pycache'),str(HERE/'pipeline.py'),'execute','--plan',str(path),'--plan-sha256',expected_sha]
        with (CONTROL/'sequence_process.log').open('xb') as log:
            child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(CONTROL/'SEQUENCE_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':s.utc(),'automatic_retry':False})
            deadline=time.monotonic()+60
            while not (RECORD/'start.json').exists():
                s.require(child.poll() is None and time.monotonic()<deadline,'new sequence start absent');time.sleep(.2)
            start=s.read(RECORD/'start.json');s.require(start['plan_sha256']==expected_sha,'new sequence start plan differs')
            handle=observer.open(start['pid']);identity=observer.identity(handle,start['pid'])
            base=Path(manifest['environment']['model_runtime_descriptor']['base_prefix'])/'python.exe'
            allowed={subprocess.list2cmdline(command),subprocess.list2cmdline([str(base),*command[1:]]),
                     '"'+str(base)+'" '+subprocess.list2cmdline(command[1:])}
            s.require(identity['command_line'] in allowed and Path(identity['image']).resolve() in
                {Path(command[0]).resolve(),base.resolve()} and observer.exit_code(handle)==259,'exact new sequence native identity differs')
            s.emit(CONTROL/'SEQUENCE_NATIVE_IDENTITY.json',{'identity':identity,'popen_pid':child.pid,'captured_utc':s.utc(),
                                                        'query_synchronize_handle_retained':True})
            code=child.wait()
        owning=s.emit(CONTROL/'SEQUENCE_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,'producer':'OWNING_POPEN_WAIT',
                                                         'observed_utc':s.utc(),'automatic_retry':False})
        s.require(observer.wait(handle,0),'native sequence still active after wrapper exit')
        native_code=observer.exit_code(handle)
        native=s.emit(CONTROL/'SEQUENCE_NATIVE_EXIT.json',{'schema':'paper3-erratum-sequence-native-exit-observation-v1',
            'producer':'PINNED_NATIVE_QUERY_HANDLE','pid':start['pid'],'actual_exit_code':native_code,'v1_plan_sha256':expected_sha,
            'identity':identity,'identity_unchanged':True,'observed_utc':s.utc(),'owning_popen_exit_claimed':False})
        observer.close(handle);handle=None
        s.require(code==native_code==0,'new sequence actual exit nonzero; no retry')
        finish=s.read(RECORD/'finish.json');s.require(finish['status']=='DYNAMIC_STATISTICS_DELIVERY_COMPLETED','legal finish absent')
        gates=s.emit(CONTROL/'ERRATUM_PREPUBLICATION_GATES.json',{'status':'PASS','owning_exit':owning,'native_exit':native,
                 'sequence_finish_sha256':s.sha(RECORD/'finish.json'),'old_failures_preserved':True,'observed_utc':s.utc()})
        e=s.load_module(r.ERRATUM/'metadata_erratum.py','paper3_v2_frozen_metadata_erratum',r.ERRATUM_SHA)
        prefix='handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
        ep=e.create_plan(path,expected_sha,r.ERRATUM_PROOF,r.ERRATUM_PROOF_SHA,prefix,prefix+'.zip',
                         r.ERRATUM/'erratum_recovery002',r.ERRATUM/'ERRATUM_RECOVERY_PLAN_002.json',native_exit=native,prepublication_gates=gates)
        command=[s.METADATA_PYTHON,'-I','-S','-B',str(r.ERRATUM/'metadata_erratum.py'),'execute','--plan',ep['path'],'--plan-sha256',ep['sha256']]
        with (CONTROL/'erratum_process.log').open('xb') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(CONTROL/'ERRATUM_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':s.utc()});code=child.wait()
        s.emit(CONTROL/'ERRATUM_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,'producer':'OWNING_POPEN_WAIT','observed_utc':s.utc()})
        s.require(code==0,'metadata erratum failed; no retry')
        return s.emit(CONTROL/'finish.json',{'status':'RECOVERY_SEQUENCE_AND_METADATA_ERRATUM_COMPLETED',
            'sequence_finish':finish,'erratum_finish':s.read(r.ERRATUM/'erratum_recovery002/finish.json'),'finished_utc':s.utc()})
    except BaseException as error:
        s.emit(CONTROL/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,
               'message':str(error),'observed_utc':s.utc(),'automatic_retry':False});raise
    finally:
        if handle is not None:observer.close(handle)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('prepare-metadata','metadata-preflight','guard-preflight','finalize-plan','statistics','execute','supervise'))
    ap.add_argument('--plan',type=Path);ap.add_argument('--plan-sha256');a=ap.parse_args()
    if a.action=='supervise':
        with (HERE/'supervisor_process.log').open('x',encoding='utf-8',buffering=1) as log:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):print(json.dumps(supervise(a.plan,a.plan_sha256)),flush=True)
    else:
        value=prepare_metadata() if a.action=='prepare-metadata' else metadata_preflight() if a.action=='metadata-preflight' else \
              guard_preflight() if a.action=='guard-preflight' else finalize_plan() if a.action=='finalize-plan' else \
              statistics(a.plan) if a.action=='statistics' else execute(a.plan,a.plan_sha256)
        print(json.dumps(value,sort_keys=True),flush=True)


if __name__=='__main__':main()
