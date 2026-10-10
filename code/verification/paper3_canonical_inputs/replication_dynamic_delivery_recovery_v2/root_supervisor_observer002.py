"""Read-only held native handle observer of the one authorized metadata supervisor."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WATCH_SHA='cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);a=ap.parse_args()
    path=BASE/'replication_dynamic_delivery_erratum_v1/erratum_watch.py'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=WATCH_SHA:raise RuntimeError('frozen observer changed')
    spec=importlib.util.spec_from_file_location('paper3_root_native_observer',path)
    watch=importlib.util.module_from_spec(spec);sys.modules[spec.name]=watch;spec.loader.exec_module(watch)
    e=watch.e
    plan=HERE/'RECOVERY_DELIVERY_PLAN_002.json'
    launch=HERE/'durable_launch002/launch_spec.json';creation=HERE/'durable_launch002/creation.json'
    config=e.read(launch);created=e.read(creation)
    e.require(created['pid']==a.pid and created['return_value']==0,'durable launch identity differs')
    e.require(e.sha(plan)==config['plan_sha256'],'supervisor plan changed')
    backend=watch.NativeObserver();handle=backend.open(a.pid)
    try:
        e.require(backend.exit_code(handle)==259,'supervisor exited before exact handle capture')
        identity=backend.identity(handle,a.pid)
        e.require(identity['command_line']==config['command_line'] and
                  Path(identity['image']).resolve()==Path(config['interpreter']).resolve(),
                  'supervisor FILETIME/image/full command differs')
        e.emit(HERE/'ROOT_SUPERVISOR_NATIVE_IDENTITY_002.json',{
            'schema':'paper3-root-supervisor-native-identity-v1','observer_pid':os.getpid(),
            'pid':a.pid,'identity':identity,'plan_sha256':config['plan_sha256'],
            'launch_spec_sha256':e.sha(launch),'creation_receipt_sha256':e.sha(creation),
            'query_synchronize_handle_retained':True,'observed_utc':e.utc()})
        while not backend.wait(handle,15000):pass
        code=backend.exit_code(handle)
        e.emit(HERE/'ROOT_SUPERVISOR_NATIVE_EXIT_002.json',{
            'schema':'paper3-root-supervisor-native-exit-v1','producer':'PINNED_NATIVE_QUERY_HANDLE',
            'pid':a.pid,'identity':identity,'identity_unchanged':True,'actual_exit_code':code,
            'plan_sha256':config['plan_sha256'],'launch_spec_sha256':e.sha(launch),
            'creation_receipt_sha256':e.sha(creation),'owning_popen_exit_claimed':False,
            'observed_utc':e.utc()})
        e.require(code==0,'metadata supervisor native exit nonzero; no retry')
        e.require(e.read(HERE/'supervisor002/finish.json')['status']==
                  'RECOVERY_SEQUENCE_AND_METADATA_ERRATUM_COMPLETED','supervisor legal finish absent')
        print('ROOT_SUPERVISOR_NATIVE_EXIT_ZERO_AND_FINISH_VERIFIED',flush=True)
    finally:backend.close(handle)

if __name__=='__main__':main()
