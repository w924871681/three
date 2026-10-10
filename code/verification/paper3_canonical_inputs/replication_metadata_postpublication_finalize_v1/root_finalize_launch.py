"""One owned readonly finalization. Persist actual exits before further reads."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time
import hashlib
import types
import json

HERE=Path(__file__).resolve().parent
PYTHON=Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
PYTHON_SHA='0562f573871cb16a2fb8de16e3d486e3dfd74bb83c7e87db265561917d05ad1a'
def load(path,digest):
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=digest:raise RuntimeError('launcher helper SHA differs')
    m=types.ModuleType('root_postpublication_api');m.__file__=str(path);sys.modules[m.__name__]=m
    exec(compile(payload,str(path),'exec'),m.__dict__);return m
def creation_filetime(observer,handle):
    creation,exit_time,kernel,user=(wintypes.FILETIME() for _ in range(4))
    if not observer.k.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel),ctypes.byref(user)):
        raise RuntimeError('retained creation query failed')
    return (creation.dwHighDateTime<<32)|creation.dwLowDateTime
def exit_observation(actual,native,before,after):
    if type(actual) is not int or type(native) is not int or actual!=native or before!=after:
        raise RuntimeError('owning/native exit or retained creation differs')
    return {'actual_exit_code':actual,'native_exit_code':native,'identity_unchanged':True}
def main():
    if not(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise RuntimeError('requires -I -S -B')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',required=True);ap.add_argument('--plan-sha256',required=True)
    args=ap.parse_args();plan_path=Path(args.plan).resolve();payload=plan_path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=args.plan_sha256:raise RuntimeError('plan SHA differs')
    plan=json.loads(payload);helper=HERE/'postpublication_finalize.py';e=load(helper,plan['source_sha256'][str(helper)])
    e.verify_plan(plan_path,args.plan_sha256);e.bound(PYTHON,PYTHON_SHA,root=PYTHON.parent)
    watch=e.module(e.OLD/'erratum_watch.py','new_postpublication_native_observer',e.FROZEN[e.OLD/'erratum_watch.py'])
    observer=watch.NativeObserver()
    start=HERE/'POSTPUBLICATION_PROCESS_START_001.json';ex=HERE/'POSTPUBLICATION_PROCESS_EXIT_001.json';log=HERE/'POSTPUBLICATION_PROCESS_001.log'
    e.require(not any(p.exists() for p in (start,ex,log,e.RECORD)),'exclusive finalizer launch required')
    argv=[str(PYTHON),'-I','-S','-B',str(helper),'execute','--plan',str(plan_path),'--plan-sha256',args.plan_sha256]
    common={'plan_path':str(plan_path),'plan_sha256':args.plan_sha256,'source_sha256':plan['source_sha256'],
        'cmdargv':argv,'automatic_retry':False,'models_statistics_or_root_publication_executed':False,
        'query_handle_retained':True,'helper_path':str(helper),'helper_sha256':e.sha(helper)}
    began=time.perf_counter()
    with log.open('xb') as out:
        p=subprocess.Popen(argv,cwd=str(e.REPO),stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,creationflags=0x08000000)
        handle=observer.open(p.pid)
        try:
            identity=observer.identity(handle,p.pid)
            e.require(identity['command_line']==subprocess.list2cmdline(argv) and Path(identity['image']).resolve()==PYTHON.resolve(),'native launch command/image differs')
            s=e.emit(start,{**common,**identity,'schema':'paper3-postpublication-process-start-v1','producer':'ROOT_OWNING_POPEN','started_utc':e.utc()})
            print(json.dumps({'phase':'READONLY_ARTIFACT_FINALIZATION_STARTED','pid':p.pid}),flush=True)
            while not observer.wait(handle,10000):print(json.dumps({'phase':'READONLY_ARTIFACT_FINALIZATION_RUNNING','pid':p.pid,'elapsed_seconds':round(time.perf_counter()-began,1)}),flush=True)
            actual=p.wait();native=observer.exit_code(handle)
            # Capture exit values durably FIRST; no post-exit image or command query.
            raw=e.emit(HERE/'POSTPUBLICATION_NATIVE_EXIT_OBSERVATION_001.json',{**identity,
                'schema':'paper3-postpublication-native-exit-observation-v1','producer':'ROOT_OWNING_POPEN_WAIT',
                'actual_exit_code':actual,'native_exit_code':native,'plan_sha256':args.plan_sha256,'observed_utc':e.utc()})
            terminal=exit_observation(actual,native,identity['creation_filetime'],creation_filetime(observer,handle))
            receipt={**common,**identity,**terminal,'schema':'paper3-postpublication-process-exit-v1','producer':'ROOT_OWNING_POPEN_WAIT',
                'start_receipt_sha256':s['sha256'],'native_observation_sha256':raw['sha256'],
                'finished_utc':e.utc(),'elapsed_seconds':round(time.perf_counter()-began,3),'log_path':str(log),'log_sha256':e.sha(log)}
            if actual==0:
                f=e.RECORD/'finish.json';e.require(not(e.RECORD/'stopped.json').exists() and e.read(f)['status']=='COMPLETED','actual zero without artifact certificate')
                receipt.update(finish_path=str(f),finish_sha256=e.sha(f))
            e.emit(ex,receipt);print(json.dumps(receipt,sort_keys=True),flush=True)
            return 0 if actual==0 else 1
        finally:observer.close(handle)
if __name__=='__main__':raise SystemExit(main())
