"""Attach to the already-running legal delivery; never restart its computation.

Windows' venv redirector quotes the base argv0 even without spaces. Accept only
that exact representation in addition to subprocess.list2cmdline. Retain a
query/synchronize handle through actual native exit before metadata correction.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
RECOVERY_SHA='a3873cd620545d2bd951a976328cbb36a5674a7a90b142d65f6daa65599e7a95'
PLAN_SHA='4b0af114a1d3512192dbe278d5ad49172bab685e8bf749890b58198a731617ac'
OBSERVER_PLAN=HERE/'NATIVE_OBSERVER_PLAN_001.json'
RECORD=HERE/'native_observer001'


def allowed_commands(command,base_exe):
    base=str(base_exe)
    return {subprocess.list2cmdline(command),
            subprocess.list2cmdline([base,*command[1:]]),
            '"'+base+'" '+subprocess.list2cmdline(command[1:])}


def modules():
    import hashlib
    path=HERE/'recovery.py'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=RECOVERY_SHA:
        raise RuntimeError('frozen recovery source differs')
    spec=importlib.util.spec_from_file_location('paper3_native_observer_recovery',path)
    r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r;spec.loader.exec_module(r)
    s=r.load_sequence()
    w=s.load_module(r.ERRATUM/'erratum_watch.py','paper3_native_observer_frozen_api',r.WATCH_SHA)
    return r,s,w


def prepare():
    r,s,w=modules()
    s.bound(r.PLAN,PLAN_SHA);plan,_=s.verify_plan(r.PLAN)
    start_path=Path(plan['record_root'])/'start.json';start=s.read(start_path)
    s.require(start['pid']==19684 and start['plan_sha256']==PLAN_SHA,'already-running sequence differs')
    launch=s.read(r.CONTROL/'SEQUENCE_PROCESS_START.json')
    stop=s.read(r.CONTROL/'stopped.json')
    s.require(launch['pid']==9856 and launch['plan_sha256']==PLAN_SHA and
              stop['message']=='actual sequence native identity differs','first observer failure differs')
    s.require(not OBSERVER_PLAN.exists() and not RECORD.exists(),'observer attempt exists')
    own={str(HERE/n):s.sha(HERE/n) for n in ('native_observer.py','test_native_observer.py')}
    tests=subprocess.run([s.METADATA_PYTHON,'-I','-S','-B',str(HERE/'test_native_observer.py')],capture_output=True,text=True,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    s.require(tests.returncode==0,'exact command representation tests failed: '+tests.stderr)
    s.require(own=={n:s.sha(n) for n in own},'observer source changed during tests')
    observer=w.NativeObserver();handle=observer.open(start['pid'])
    try:
        identity=observer.identity(handle,start['pid'])
        manifest=s.read(r.RESULTS/'provenance_manifest.json')
        base=Path(manifest['environment']['model_runtime_descriptor']['base_prefix'])/'python.exe'
        s.require(identity['command_line'] in allowed_commands(launch['command'],base) and
                  Path(identity['image']).resolve()==base.resolve() and observer.exit_code(handle)==259,
                  'exact live native identity differs')
    finally:observer.close(handle)
    proof=s.emit(HERE/'EXACT_NATIVE_COMMAND_TEST_PROOF_001.json',{
        'status':'PASS','unit_test_actual_exit_code':tests.returncode,'unit_test_log':tests.stdout+tests.stderr,
        'implementation_sha256':own,'actual_native_identity':identity,'observed_utc':s.utc(),
        'only_argv0_quote_representation_added':True,'models_statistics_restarted':False})
    return s.emit(OBSERVER_PLAN,{'schema':'paper3-existing-delivery-native-observer-plan-v1',
        'sequence_plan_path':str(r.PLAN),'sequence_plan_sha256':PLAN_SHA,
        'sequence_start_path':str(start_path),'sequence_start_sha256':s.sha(start_path),
        'expected_native_identity':identity,'implementation_sha256':own,'proof':proof,
        'first_observer_failure':{'path':str(r.CONTROL/'stopped.json'),'sha256':s.sha(r.CONTROL/'stopped.json')},
        'record_root':str(RECORD),'created_utc':s.utc(),'automatic_retry':False,
        'model_or_statistics_launch_permitted':False})


def execute(path,expected_sha):
    r,s,w=modules();s.bound(path,expected_sha);p=s.read(path)
    s.require(path==OBSERVER_PLAN and p['sequence_plan_sha256']==PLAN_SHA,'observer plan differs')
    for n,h in p['implementation_sha256'].items():s.bound(n,h)
    for key in ('proof','first_observer_failure'):s.bound(p[key]['path'],p[key]['sha256'])
    s.bound(p['sequence_start_path'],p['sequence_start_sha256'])
    s.bound(r.PLAN,PLAN_SHA);v,_=s.verify_plan(r.PLAN)
    s.require(not RECORD.exists(),'observer already exists');RECORD.mkdir()
    s.emit(RECORD/'start.json',{'pid':os.getpid(),'observer_plan_sha256':expected_sha,'started_utc':s.utc(),
                             'models_statistics_restarted':False})
    observer=w.NativeObserver();handle=None
    try:
        pid=p['expected_native_identity']['pid'];handle=observer.open(pid)
        identity=observer.identity(handle,pid)
        s.require(identity==p['expected_native_identity'] and observer.exit_code(handle)==259,
                  'actual PID/FILETIME/image/command differs or already exited')
        s.emit(RECORD/'NATIVE_HANDLE_CAPTURED.json',{'identity':identity,'query_synchronize_only':True,
                                                 'captured_utc':s.utc()})
        while not observer.wait(handle,15000):
            s.require(observer.exit_code(handle)==259,'unexpected native running state')
        code=observer.exit_code(handle)
        native=s.emit(RECORD/'SEQUENCE_NATIVE_EXIT.json',{
            'schema':'paper3-erratum-sequence-native-exit-observation-v1','producer':'PINNED_NATIVE_QUERY_HANDLE',
            'pid':pid,'v1_plan_sha256':PLAN_SHA,'actual_exit_code':code,'identity':identity,
            'identity_unchanged':True,'observed_utc':s.utc(),'owning_popen_exit_claimed':False,'automatic_retry':False})
        observer.close(handle);handle=None
        s.require(code==0,'existing sequence native exit nonzero; no retry')
        finish_path=Path(v['record_root'])/'finish.json';finish=s.read(finish_path)
        s.require(finish['status']=='DYNAMIC_STATISTICS_DELIVERY_COMPLETED','legal sequence finish absent')
        gates=s.emit(RECORD/'ERRATUM_PREPUBLICATION_GATES.json',{
            'status':'PASS','observer_plan':{'path':str(path),'sha256':expected_sha},
            'sequence_finish_sha256':s.sha(finish_path),'native_exit':native,
            'old_failures_preserved':True,'models_statistics_restarted':False,'observed_utc':s.utc()})
        e=s.load_module(r.ERRATUM/'metadata_erratum.py','paper3_native_observer_frozen_erratum',r.ERRATUM_SHA)
        prefix='handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
        erratum=e.create_plan(r.PLAN,PLAN_SHA,r.ERRATUM_PROOF,r.ERRATUM_PROOF_SHA,prefix,prefix+'.zip',
                             r.ERRATUM/'erratum_recovery001',r.ERRATUM/'ERRATUM_RECOVERY_PLAN_001.json',
                             native_exit=native,prepublication_gates=gates)
        command=[s.METADATA_PYTHON,'-I','-S','-B',str(r.ERRATUM/'metadata_erratum.py'),'execute',
                 '--plan',erratum['path'],'--plan-sha256',erratum['sha256']]
        with (RECORD/'erratum_process.log').open('xb') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            s.emit(RECORD/'ERRATUM_PROCESS_START.json',{'pid':child.pid,'command':command,'started_utc':s.utc()})
            exit_code=child.wait()
        s.emit(RECORD/'ERRATUM_PROCESS_EXIT.json',{'pid':child.pid,'actual_exit_code':exit_code,
               'producer':'OWNING_POPEN_WAIT','observed_utc':s.utc(),'automatic_retry':False})
        s.require(exit_code==0,'metadata erratum failed; no retry')
        corrected=s.read(r.ERRATUM/'erratum_recovery001/finish.json')
        return s.emit(RECORD/'finish.json',{'status':'RECOVERY_NATIVE_SEQUENCE_AND_METADATA_ERRATUM_COMPLETED',
                    'sequence_finish':finish,'erratum_finish':corrected,'finished_utc':s.utc()})
    except BaseException as error:
        s.emit(RECORD/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,
               'message':str(error),'observed_utc':s.utc(),'automatic_retry':False});raise
    finally:
        if handle is not None:observer.close(handle)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','execute'))
    ap.add_argument('--plan',type=Path);ap.add_argument('--plan-sha256');args=ap.parse_args()
    if args.action=='prepare':print(json.dumps(prepare(),sort_keys=True),flush=True)
    else:
        import contextlib
        with (HERE/'native_observer_process.log').open('x',encoding='utf-8',buffering=1) as log:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                print(json.dumps(execute(args.plan,args.plan_sha256),sort_keys=True),flush=True)


if __name__=='__main__':main()
