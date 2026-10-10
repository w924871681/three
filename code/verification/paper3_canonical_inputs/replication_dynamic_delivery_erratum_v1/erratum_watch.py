"""Read-only native-handle waiter, then one separately gated metadata erratum.

No model/statistics imports, Popen, WMI, stop, signal, or retry exist in this file.
Only root may launch this source-pinned watcher after its independent review.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paper3_erratum_watch_metadata_api',HERE/'metadata_erratum.py')
e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
V1_PLAN_SHA='5b180c931a12781925538e876bebbcf416cd32a219ea5710a17ad29b9fd9e3b0'
V1_SEQUENCE_PID=15508
V1_CREATION_FILETIME=134360441221259883

class NativeObserver:
    """Retain query+synchronize rights only; never acquire mutation rights."""
    def __init__(self):
        e.require(sys.platform=='win32','native observer requires Windows')
        self.k=ctypes.WinDLL('kernel32',use_last_error=True);self.nt=ctypes.WinDLL('ntdll')
        self.k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];self.k.OpenProcess.restype=wintypes.HANDLE
        self.k.CloseHandle.argtypes=[wintypes.HANDLE];self.k.CloseHandle.restype=wintypes.BOOL
        self.k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];self.k.WaitForSingleObject.restype=wintypes.DWORD
        self.k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];self.k.GetExitCodeProcess.restype=wintypes.BOOL
        self.k.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];self.k.GetProcessTimes.restype=wintypes.BOOL
        self.k.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)];self.k.QueryFullProcessImageNameW.restype=wintypes.BOOL
        self.nt.NtQueryInformationProcess.argtypes=[wintypes.HANDLE,wintypes.ULONG,ctypes.c_void_p,wintypes.ULONG,ctypes.POINTER(wintypes.ULONG)];self.nt.NtQueryInformationProcess.restype=ctypes.c_long
    def open(self,pid):
        handle=self.k.OpenProcess(0x1000|0x00100000,False,pid)
        e.require(handle,'cannot open exact native sequence query handle');return handle
    def close(self,handle):e.require(self.k.CloseHandle(handle),'native sequence handle close failed')
    def wait(self,handle,milliseconds):
        e.require(type(milliseconds) is int and 0<=milliseconds<=15000,'native wait bound differs')
        result=int(self.k.WaitForSingleObject(handle,milliseconds))
        e.require(result in (0,0x102),'native process wait failed');return result==0
    def exit_code(self,handle):
        code=wintypes.DWORD();e.require(self.k.GetExitCodeProcess(handle,ctypes.byref(code)),'native sequence exit query failed');return int(code.value)
    def identity(self,handle,pid):
        creation,exit,kernel,user=(wintypes.FILETIME() for _ in range(4))
        e.require(self.k.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit),ctypes.byref(kernel),ctypes.byref(user)),'native creation FILETIME query failed')
        capacity=wintypes.DWORD(32768);image=ctypes.create_unicode_buffer(capacity.value)
        e.require(self.k.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(capacity)),'native image query failed')
        needed=wintypes.ULONG();self.nt.NtQueryInformationProcess(handle,60,None,0,ctypes.byref(needed))
        e.require(0<needed.value<=1048576,'native command size unavailable')
        buffer=ctypes.create_string_buffer(needed.value)
        status=self.nt.NtQueryInformationProcess(handle,60,buffer,len(buffer),ctypes.byref(needed))
        e.require(status==0,'native command query failed')
        class UnicodeString(ctypes.Structure):_fields_=[('length',wintypes.USHORT),('maximum_length',wintypes.USHORT),('buffer',ctypes.c_void_p)]
        value=UnicodeString.from_buffer(buffer);address=ctypes.addressof(buffer)
        e.require(value.length%2==0 and address<=value.buffer and value.buffer+value.length<=address+len(buffer),'native command buffer outside returned allocation')
        command=ctypes.wstring_at(value.buffer,value.length//2)
        return {'pid':pid,'creation_filetime':(creation.dwHighDateTime<<32)|creation.dwLowDateTime,
                'image':str(Path(image.value).resolve()),'command_line':command}

def verify_identity(actual,expected):
    e.require(actual==expected and type(actual.get('creation_filetime')) is int and actual['creation_filetime']>0,'PID/FILETIME/image/command identity differs')
def expected_sequence(v1_plan):
    path=e.bound(v1_plan,V1_PLAN_SHA);v=e.read(path);launch=e.read(path.parent/'delivery_sequence_launched.json')
    expected=[r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe','-I','-S','-B',str(e.V1/'dynamic_sequence.py'),'execute','--plan',str(path)]
    e.require(launch.get('pid')==V1_SEQUENCE_PID and launch.get('command')==expected and launch.get('plan_sha256')==V1_PLAN_SHA,'actual V1 sequence launch differs')
    return v,launch,expected
def verify_watch_plan(path,digest):
    path=e.bound(path,digest);e.require(path.parent==HERE,'watch plan outside independent helper directory');p=e.read(path)
    e.require(p.get('schema')=='paper3-smoke-count-erratum-watch-plan-v1' and p.get('v1_plan_sha256')==V1_PLAN_SHA and p.get('v1_sequence_pid')==V1_SEQUENCE_PID,'watch plan identity differs')
    e.verify_proof(p['proof_path'],p['proof_sha256']);e.require(p.get('implementation_sha256')==e.own_pins(),'watch source closure differs')
    v,launch,command=expected_sequence(p['v1_plan_path'])
    identity=p['expected_native_identity'];e.require(identity.get('pid')==V1_SEQUENCE_PID and identity.get('creation_filetime')==V1_CREATION_FILETIME and identity.get('command_line')==subprocess.list2cmdline(command) and
            Path(identity.get('image','')).resolve()==Path(command[0]).resolve(),'watch native identity does not identify exact authorized command')
    e.bound(p['sequence_launch_path'],p['sequence_launch_sha256'])
    for key in ('watch_record_root','erratum_record_root'):
        e.require(e.safe(p[key]).parent==HERE,'watch/erratum record outside independent helper')
    e.require(e.safe(p['erratum_plan_path']).parent==HERE,'real erratum plan outside independent helper')
    for key in ('target_relative','zip_relative'):
        value=e.safe(e.REPO/p[key]);e.require(value.is_relative_to(e.REPO/'handoffs') and value!=e.REPO/'handoffs','watch outputs outside independent handoffs')
    e.require(e.safe(e.REPO/p['target_relative'])!=e.safe(e.REPO/p['zip_relative']) and not e.safe(e.REPO/p['zip_relative']).is_relative_to(e.safe(e.REPO/p['target_relative'])),'watch ZIP/package collide')
    return p,v
def create_watch_plan(v1_plan,proof,proof_sha,target,zipped,watch_record,erratum_record,erratum_plan,output, *, observer=None):
    e.verify_proof(proof,proof_sha);v,launch,command=expected_sequence(v1_plan)
    backend=observer or NativeObserver();handle=backend.open(V1_SEQUENCE_PID)
    try:
        e.require(backend.exit_code(handle)==259,'V1 sequence already exited before identity capture')
        identity=backend.identity(handle,V1_SEQUENCE_PID)
        e.require(identity['creation_filetime']==V1_CREATION_FILETIME and identity['command_line']==subprocess.list2cmdline(command) and Path(identity['image']).resolve()==Path(command[0]).resolve(),'actual native sequence FILETIME/command/image differs')
    finally:backend.close(handle)
    plan={'schema':'paper3-smoke-count-erratum-watch-plan-v1','v1_plan_path':str(e.safe(v1_plan)),'v1_plan_sha256':V1_PLAN_SHA,'v1_sequence_pid':V1_SEQUENCE_PID,
          'expected_native_identity':identity,'sequence_launch_path':str(Path(v1_plan).parent/'delivery_sequence_launched.json'),
          'sequence_launch_sha256':e.sha(Path(v1_plan).parent/'delivery_sequence_launched.json'),'proof_path':str(e.safe(proof)),'proof_sha256':proof_sha,
          'implementation_sha256':e.own_pins(),'watch_record_root':str(e.safe(watch_record)),'erratum_record_root':str(e.safe(erratum_record)),
          'erratum_plan_path':str(e.safe(erratum_plan)),'target_relative':target,'zip_relative':zipped,
          'process_access':'PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE','automatic_retry':False,'created_utc':e.utc()}
    e.require(e.safe(output).parent==HERE,'watch plan output outside independent helper');ref=e.emit(output,plan);verify_watch_plan(ref['path'],ref['sha256']);return ref
def run(path,digest, *, observer=None,pause=time.sleep):
    e.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    plan,v=verify_watch_plan(path,digest);record=e.safe(plan['watch_record_root']);e.require(not record.exists(),'exclusive watcher attempt already exists');record.mkdir()
    e.emit(record/'start.json',{'schema':'paper3-smoke-count-erratum-watch-start-v1','pid':__import__('os').getpid(),'watch_plan_sha256':digest,'started_utc':e.utc(),'model_statistics_process_control':False})
    backend=observer or NativeObserver();handle=None
    try:
        handle=backend.open(V1_SEQUENCE_PID);verify_identity(backend.identity(handle,V1_SEQUENCE_PID),plan['expected_native_identity'])
        sequence=Path(v['record_root'])
        while True:
            verify_watch_plan(path,digest)
            e.require(not (sequence/'stopped.json').exists(),'V1 sequence stopped; no automatic repair/retry')
            if backend.wait(handle,15000):
                code=backend.exit_code(handle)
                e.require(type(code) is int,'native exit code must be an actual integer')
                e.require(code==0 and (sequence/'finish.json').exists(),'V1 native exit is nonzero or legal finish absent')
                break
            pause(0)
        observation=e.emit(record/'V1_SEQUENCE_NATIVE_EXIT.json',{'schema':'paper3-erratum-sequence-native-exit-observation-v1',
            'producer':'PINNED_NATIVE_QUERY_HANDLE','pid':V1_SEQUENCE_PID,'actual_exit_code':code,'v1_plan_sha256':V1_PLAN_SHA,
            'identity':plan['expected_native_identity'],'identity_unchanged':True,'observed_utc':e.utc(),'automatic_retry':False,
            'owning_popen_exit_claimed':False})
        api=e.load(e.BASE/'replication_delivery_env_v3/delivery.py','paper3_erratum_watch_original_delivery',e.ORIGINAL_DELIVERY)
        f=e.load(e.BASE/'replication_abrupt_recovery_v1/finalizer.py','paper3_erratum_watch_original_publication',e.ORIGINAL_FINALIZER)
        provisional={'v1_plan_sha256':V1_PLAN_SHA,'v1_native_exit_observation':observation}
        full=e.read(e.bound(v['contract_path'],v['contract_sha256']))
        gates=e.verify_completed(provisional,v,full,api,f,queue_name='paper3_erratum_watch_original_queue')
        proof=e.emit(record/'PREPUBLICATION_COMPLETION_GATES.json',{'schema':'paper3-erratum-prepublication-completion-gates-v1','status':'PASS',
            'v1_plan_sha256':V1_PLAN_SHA,'native_exit_observation':observation,'expected_old_root_sha256':gates['expected_old_root_sha256'],
            'statistics_manifest_sha256':gates['statistics_manifest_sha256'],'statistics_receipt_sha256':gates['statistics_receipt_sha256'],
            'all_statistics_files_sha256':gates['statistics_sha256'],'observed_smoke':gates['observed_smoke'],'scientific_evidence_sha256':gates['scientific_evidence_sha256'],
            'models_statistics_executed':False,'checked_utc':e.utc()})
        ref=e.create_plan(plan['v1_plan_path'],V1_PLAN_SHA,plan['proof_path'],plan['proof_sha256'],plan['target_relative'],plan['zip_relative'],
                          plan['erratum_record_root'],plan['erratum_plan_path'],native_exit=observation,prepublication_gates=proof)
        result=e.execute(ref['path'],ref['sha256']);e.emit(record/'finish.json',{'status':'WATCHED_METADATA_ERRATUM_COMPLETED','result':result,'finished_utc':e.utc()});return result
    except BaseException as error:
        e.emit(record/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','error':type(error).__name__,'message':str(error),'observed_utc':e.utc(),'automatic_retry':False});raise
    finally:
        if handle is not None:backend.close(handle)
def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    a=sub.add_parser('create-plan')
    for n in ('v1-plan','proof','proof-sha256','target-relative','zip-relative','watch-record-root','erratum-record-root','erratum-plan','output'):a.add_argument('--'+n,required=True)
    for name in ('verify-plan','run'):
        a=sub.add_parser(name);a.add_argument('--plan',required=True);a.add_argument('--plan-sha256',required=True)
    args=ap.parse_args()
    if args.action=='create-plan':result=create_watch_plan(args.v1_plan,args.proof,args.proof_sha256,args.target_relative,args.zip_relative,args.watch_record_root,args.erratum_record_root,args.erratum_plan,args.output)
    elif args.action=='verify-plan':result=verify_watch_plan(args.plan,args.plan_sha256)[0]
    else:result=run(args.plan,args.plan_sha256)
    print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__':main()
