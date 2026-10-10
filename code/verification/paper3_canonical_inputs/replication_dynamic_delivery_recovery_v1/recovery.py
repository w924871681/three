"""Authorized delivery-only recovery; every scientific implementation stays frozen.

Launch the original sequence in its manifest-bound venv. No model task, input
generation, environment installation, source replacement or automatic retry.
"""
from __future__ import annotations
import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
V1 = BASE / 'replication_dynamic_takeover_v1'
RESULTS = REPO / 'results/p7_7_integrity_replication_batch20_env_v3'
OLD_PLAN = V1 / 'activation001/dynamic_delivery_plan.json'
OLD_SHA = '5b180c931a12781925538e876bebbcf416cd32a219ea5710a17ad29b9fd9e3b0'
SEQUENCE_SHA = '1126602603e0701fe8281eb66946d14d187a2c9fc470687aa9fa3b935868b736'
ERRATUM = BASE / 'replication_dynamic_delivery_erratum_v1'
ERRATUM_SHA = '3461322dd57af084d46a98d6cdb66abca473d006902fb90e37694013d92bebce'
WATCH_SHA = 'cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2'
ERRATUM_PROOF = ERRATUM / 'SMOKE_COUNT_ERRATUM_SYNTHETIC_TEST_RESULTS_ATTEMPT004.json'
ERRATUM_PROOF_SHA = '8c7ffcf50294c0f894be3412beeafe132562857ca7abf23893d82e246e34f9c6'
CACHE = RESULTS / '_dynamic_delivery_recovery001_cache'
PLAN = HERE / 'RECOVERY_DELIVERY_PLAN_001.json'
CONTROL = HERE / 'supervisor001'


def load_sequence():
    path = V1 / 'dynamic_sequence.py'
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest() != SEQUENCE_SHA:
        raise RuntimeError('frozen sequence source changed')
    name = 'paper3_recovery_frozen_sequence'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_env(environment, cache_root, parent=None):
    env = dict(os.environ if parent is None else parent)
    controls = dict(environment['thread_environment'])
    for key, value in environment['model_runtime_environment'].items():
        if key in controls and controls[key] != value:
            raise ValueError('conflicting frozen environment controls')
        controls[key] = value
    for key, value in controls.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    cache_root = Path(cache_root)
    env.update(TEMP=str(cache_root/'temp'), TMP=str(cache_root/'temp'),
               TORCH_HOME=str(cache_root/'torch'), CUDA_CACHE_PATH=str(cache_root/'cuda'))
    return env


def build_command(environment, plan_path, cache_root):
    return [environment['python_executable'], '-I', '-S', '-B', '-X',
            'pycache_prefix='+str(Path(cache_root)/'never_pycache'),
            str(V1/'dynamic_sequence.py'), 'execute', '--plan', str(plan_path)]


def identity_probe():
    """Actual original environment predicate, no model/statistics imports or writes."""
    s = load_sequence()
    p, _ = s.original_modules()
    manifest = s.read(RESULTS/'provenance_manifest.json')
    p._verify_current_environment(manifest['environment'], check_files=False)
    p.require_isolation(RESULTS)
    forbidden = [n for n in sys.modules if n.split('.')[0] in
                 {'torch','numpy','scipy','sklearn','river','core','imported'}]
    s.require(not forbidden, 'scientific module imported during identity probe')
    return {'status':'PASS', 'sys_executable':sys.executable,
            'base_prefix':sys.base_prefix, 'isolated':bool(sys.flags.isolated),
            'no_site':bool(sys.flags.no_site), 'no_bytecode':sys.dont_write_bytecode,
            'original_environment_predicate_executed':True,
            'environment_file_inventory_not_yet_fully_hashed':True,
            'model_statistics_modules_imported':forbidden}


def prepare():
    s = load_sequence()
    s.bound(OLD_PLAN, OLD_SHA)
    old, contract = s.verify_plan(OLD_PLAN)
    manifest = s.read(RESULTS/'provenance_manifest.json')
    s.require(manifest['manifest_digest']==s.MANIFEST, 'manifest identity differs')
    s.require(s.sha(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md')==s.F50, 'root already published')
    old_record = Path(old['record_root'])
    stop = s.read(old_record/'stopped.json')
    s.require(stop['status']=='STOPPED_FOR_DIAGNOSIS' and stop['error']=='ProvenanceError'
              and stop['message']=='model interpreter changed', 'unexpected original failure')
    for path in (old_record, ERRATUM/'watch001'):
        s.require(not s.process_active(s.read(path/'start.json')['pid']), 'old owner still active')
    s.require(not (old_record/'finish.json').exists(), 'original legal finish already exists')
    s.require(s.read(old['coordinator_exit_path'])['actual_exit_code']==0, 'FULL coordinator failed')
    marker = s.read(RESULTS/contract['run_relative']/'DYNAMIC_EXECUTION_COMPLETED.json')
    s.require(marker['completed']==1200 and marker['pairing']['complete_paired_groups']==240,
              'dynamic terminal incomplete')
    for relative in ('full_experiment_integrity_gate.json','statistics_batch20_env_v3',
                     '_dynamic_statistics_A_DYNAMIC_0002'):
        s.require(not (RESULTS/relative).exists(), 'downstream already exists: '+relative)
    s.require(not PLAN.exists() and not CACHE.exists() and not CONTROL.exists(), 'recovery attempt exists')
    prefix = 'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_RECOVERY_001'
    erratum_prefix = 'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
    for target in (HERE/'sequence001', REPO/(prefix+'_REVIEWED_001'), REPO/(prefix+'_FINAL_001'),
                   REPO/(prefix+'_FINAL_001.zip'), REPO/erratum_prefix, REPO/(erratum_prefix+'.zip'),
                   ERRATUM/'erratum_recovery001',ERRATUM/'ERRATUM_RECOVERY_PLAN_001.json'):
        s.require(not target.exists(),'recovery output collision: '+str(target))
    before={str(HERE/n):s.sha(HERE/n) for n in ('recovery.py','test_recovery.py')}
    CACHE.mkdir()
    for name in ('temp','torch','cuda'):
        (CACHE/name).mkdir()
    env = build_env(manifest['environment'], CACHE)
    probe_results = {}
    for role, interpreter in [('rejected_metadata',s.METADATA_PYTHON),
                              ('accepted_frozen_venv',manifest['environment']['python_executable'])]:
        command = [interpreter,'-I','-S','-B','-X','pycache_prefix='+str(CACHE/'never_pycache'),
                   str(HERE/'recovery.py'),'identity-probe']
        child = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        probe_results[role] = {'command':command,'actual_exit_code':child.returncode,
                               'stdout':child.stdout,'stderr':child.stderr}
        if role=='rejected_metadata':
            s.require(child.returncode!=0 and 'model interpreter changed' in child.stderr,
                      'actual wrong-interpreter regression did not reject')
        else:
            s.require(child.returncode==0 and json.loads(child.stdout)['status']=='PASS',
                      'actual frozen environment probe failed')
    tests = subprocess.run([s.METADATA_PYTHON,'-I','-S','-B',str(HERE/'test_recovery.py')],
                           capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    s.require(tests.returncode==0, 'recovery unit tests failed: '+tests.stderr)
    s.require(before=={n:s.sha(n) for n in before}, 'recovery source changed during tests/probes')
    proof = {'schema':'paper3-delivery-recovery-real-boundary-proof-v1','status':'PASS',
             'created_utc':s.utc(),'actual_environment_probes':probe_results,
             'unit_test_exit_code':tests.returncode,'unit_test_log':tests.stdout+tests.stderr,
             'implementation_sha256':before,
             'no_models_statistics_or_publication_executed':True,
             'frozen_environment_controls':{**manifest['environment']['thread_environment'],
                                             **manifest['environment']['model_runtime_environment']}}
    proof_ref = s.emit(HERE/'REAL_ENVIRONMENT_BOUNDARY_PROOF_001.json',proof)
    plan = dict(old)
    plan['activation_evidence_sha256'] = dict(old['activation_evidence_sha256'])
    additional = [OLD_PLAN, old_record/'start.json',old_record/'stopped.json',
                  old_record.parent/'delivery_sequence.log',old_record.parent/'delivery_sequence_launched.json',
                  ERRATUM/'watch001/start.json',ERRATUM/'watch001/stopped.json',
                  HERE/'recovery.py',HERE/'test_recovery.py',Path(proof_ref['path'])]
    for path in additional:
        plan['activation_evidence_sha256'][str(path)] = s.sha(path)
    plan.update(record_root=str(HERE/'sequence001'), reviewed_handoff_relative=prefix+'_REVIEWED_001',
                final_handoff_relative=prefix+'_FINAL_001',zip_relative=prefix+'_FINAL_001.zip',
                created_utc=s.utc(), delivery_recovery={
                    'authorized_by_researcher':True,'superseded_failed_plan_sha256':OLD_SHA,
                    'failure_preserved':True,'original_source_modified':False,
                    'model_tasks_restarted':False,'environment_guard_weakened':False,
                    'real_environment_boundary_proof':proof_ref})
    for key in ('record_root','reviewed_handoff_relative','final_handoff_relative','zip_relative'):
        target=Path(plan[key]) if key=='record_root' else REPO/plan[key]
        s.require(not target.exists(),'new output already exists')
    result=s.emit(PLAN,plan)
    s.verify_plan(PLAN)
    return result


def run(plan_path, expected_sha):
    s = load_sequence()
    s.bound(plan_path, expected_sha)
    plan, _ = s.verify_plan(plan_path)
    s.require(plan_path==PLAN, 'unexpected recovery plan')
    manifest=s.read(RESULTS/'provenance_manifest.json')
    s.require(not CONTROL.exists(), 'supervisor already exists')
    CONTROL.mkdir()
    s.emit(CONTROL/'start.json',{'schema':'paper3-delivery-recovery-supervisor-start-v1',
          'pid':os.getpid(),'plan_sha256':expected_sha,'started_utc':s.utc(),'automatic_retry':False})
    observer=None
    handle=None
    try:
        watch=s.load_module(ERRATUM/'erratum_watch.py','paper3_recovery_frozen_native_observer',WATCH_SHA)
        observer=watch.NativeObserver()
        env=build_env(manifest['environment'],CACHE)
        command=build_command(manifest['environment'],plan_path,CACHE)
        with (CONTROL/'sequence_process.log').open('xb') as log:
            child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(CONTROL/'SEQUENCE_PROCESS_START.json',{'pid':child.pid,'command':command,
                   'started_utc':s.utc(),'plan_sha256':expected_sha,'automatic_retry':False,
                   'frozen_controls':{k:env.get(k) for k in set(manifest['environment']['thread_environment'])|
                                      set(manifest['environment']['model_runtime_environment'])}})
            start_path=Path(plan['record_root'])/'start.json'
            deadline=time.monotonic()+60
            while not start_path.exists():
                s.require(child.poll() is None and time.monotonic()<deadline,'sequence did not publish its start')
                time.sleep(0.2)
            start=s.read(start_path)
            s.require(start['plan_sha256']==expected_sha,'actual sequence start plan differs')
            handle=observer.open(start['pid'])
            identity=observer.identity(handle,start['pid'])
            base_exe=Path(manifest['environment']['model_runtime_descriptor']['base_prefix'])/'python.exe'
            allowed_commands={subprocess.list2cmdline(command),subprocess.list2cmdline([str(base_exe),*command[1:]])}
            s.require(identity['command_line'] in allowed_commands and
                      Path(identity['image']).resolve() in {Path(command[0]).resolve(),base_exe.resolve()} and
                      observer.exit_code(handle)==259,'actual sequence native identity differs')
            s.emit(CONTROL/'SEQUENCE_NATIVE_IDENTITY.json',{'identity':identity,'popen_pid':child.pid,
                   'sequence_start_sha256':s.sha(start_path),'query_synchronize_handle_retained':True,'captured_utc':s.utc()})
            code=child.wait()
        exit_ref=s.emit(CONTROL/'SEQUENCE_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,
                   'observed_utc':s.utc(),'producer':'OWNING_POPEN_WAIT','automatic_retry':False})
        s.require(code==0,'recovery sequence failed; outputs preserved, no automatic retry')
        s.require(observer.wait(handle,0),'actual sequence still running after wrapper exit')
        native_code=observer.exit_code(handle)
        s.require(native_code==0,'actual sequence native exit was nonzero')
        native=s.emit(CONTROL/'SEQUENCE_NATIVE_EXIT.json',{'schema':'paper3-erratum-sequence-native-exit-observation-v1',
                'producer':'PINNED_NATIVE_QUERY_HANDLE','pid':start['pid'],'actual_exit_code':native_code,
                'v1_plan_sha256':expected_sha,'identity':identity,'identity_unchanged':True,
                'observed_utc':s.utc(),'automatic_retry':False,'owning_popen_exit_claimed':False})
        observer.close(handle)
        handle=None
        finish=s.read(Path(plan['record_root'])/'finish.json')
        s.require(finish['status']=='DYNAMIC_STATISTICS_DELIVERY_COMPLETED','legal sequence finish absent')
        e=s.load_module(ERRATUM/'metadata_erratum.py','paper3_recovery_frozen_erratum',ERRATUM_SHA)
        prefix='handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
        gates=s.emit(CONTROL/'ERRATUM_PREPUBLICATION_GATES.json',{'schema':'paper3-recovery-erratum-prepublication-gates-v1',
                'status':'PASS','owning_sequence_actual_exit':exit_ref,'sequence_finish_sha256':s.sha(Path(plan['record_root'])/'finish.json'),
                'original_failed_sequence_preserved':True,'observed_utc':s.utc()})
        erratum=e.create_plan(plan_path,expected_sha,ERRATUM_PROOF,ERRATUM_PROOF_SHA,prefix,prefix+'.zip',
                            ERRATUM/'erratum_recovery001',ERRATUM/'ERRATUM_RECOVERY_PLAN_001.json',native_exit=native,prepublication_gates=gates)
        command=[s.METADATA_PYTHON,'-I','-S','-B',str(ERRATUM/'metadata_erratum.py'),'execute',
                 '--plan',erratum['path'],'--plan-sha256',erratum['sha256']]
        with (CONTROL/'erratum_process.log').open('xb') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(CONTROL/'ERRATUM_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':s.utc(),'automatic_retry':False})
            code=child.wait()
        s.emit(CONTROL/'ERRATUM_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':code,'observed_utc':s.utc(),
                                                  'producer':'OWNING_POPEN_WAIT','automatic_retry':False})
        s.require(code==0,'metadata erratum failed; outputs preserved, no automatic retry')
        corrected=s.read(ERRATUM/'erratum_recovery001/finish.json')
        return s.emit(CONTROL/'finish.json',{'status':'RECOVERY_SEQUENCE_AND_METADATA_ERRATUM_COMPLETED',
                      'sequence_finish':finish,'erratum_finish':corrected,'finished_utc':s.utc()})
    except BaseException as error:
        s.emit(CONTROL/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,
               'message':str(error),'observed_utc':s.utc(),'automatic_retry':False})
        raise
    finally:
        if handle is not None:
            observer.close(handle)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('prepare','identity-probe','run'))
    ap.add_argument('--plan',type=Path)
    ap.add_argument('--plan-sha256')
    args=ap.parse_args()
    if args.action=='run':
        with (HERE/'supervisor_process.log').open('x',encoding='utf-8',buffering=1) as log:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                print(json.dumps(run(args.plan,args.plan_sha256),sort_keys=True),flush=True)
    else:
        value=prepare() if args.action=='prepare' else identity_probe()
        print(json.dumps(value,sort_keys=True),flush=True)


if __name__=='__main__':
    main()
