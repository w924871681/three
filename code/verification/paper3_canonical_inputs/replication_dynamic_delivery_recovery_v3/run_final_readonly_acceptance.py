"""One root-owned final readonly audit; no model or statistics process is launched."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RECOVERY = HERE.parent/'replication_dynamic_delivery_erratum_recovery_v2'
PYTHON = Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
AUDITOR = HERE/'final_readonly_acceptance.py'
AUDITOR_SHA = 'b0c0a2cc07a438067e8eb450ff748ca7467df2d8ffe1c299367e6acaec9ad734'
PROOF = HERE/'FINAL_ACCEPTANCE_METADATA_SYNTHETIC_TEST_RESULTS_003.json'
PROOF_SHA = 'ce898c76a21cf6fe7789e8cf7b0e29ed1cc3a826e176c6b98172a07d0e3eef11'
PLAN = RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json'
PLAN_SHA = '44cb35e0df7b584e45944956e64c12d9706eb1aa7acceb28b2302a4e97f15dff'
EXIT = RECOVERY/'ROOT_ERRATUM_RECOVERY_PROCESS_EXIT_004.json'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def require(ok,message):
    if not ok:raise RuntimeError(message)
def utc():return datetime.now(timezone.utc).isoformat()
def emit(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush()

def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recovery-exit-sha256',required=True)
    args=ap.parse_args()
    for p,h in ((PYTHON,'0562f573871cb16a2fb8de16e3d486e3dfd74bb83c7e87db265561917d05ad1a'),
                (AUDITOR,AUDITOR_SHA),(PROOF,PROOF_SHA),(PLAN,PLAN_SHA),(EXIT,args.recovery_exit_sha256)):
        require(sha(p)==h,'final audit prerequisite SHA differs: '+str(p))
    proof=json.loads(PROOF.read_text())
    require(proof['all_pass'] is True and proof['tests_run']==34 and
            proof['errors']==proof['failures']==proof['skipped']==0,'auditor control tests not passed')
    upstream=json.loads(EXIT.read_text())
    require(type(upstream.get('actual_exit_code')) is int and upstream['actual_exit_code']==0 and
            type(upstream.get('native_exit_code')) is int and upstream['native_exit_code']==0 and
            upstream['plan_sha256']==PLAN_SHA and upstream['identity_unchanged'] is True,'upstream actual clean exit absent')
    require(sha(upstream['finish_path'])==upstream['finish_sha256'],'upstream legal finish SHA differs')
    output=HERE/'FINAL_READONLY_ACCEPTANCE_003.json'
    stderr=HERE/'FINAL_READONLY_ACCEPTANCE_003.stderr.log'
    start=HERE/'FINAL_READONLY_ACCEPTANCE_PROCESS_START_003.json'
    finish=HERE/'FINAL_READONLY_ACCEPTANCE_PROCESS_003.json'
    require(not any(p.exists() for p in (output,stderr,start,finish)),'one exclusive final audit required')
    argv=[str(PYTHON),'-I','-S','-B',str(AUDITOR),'--recovery-plan-sha256',PLAN_SHA,
          '--recovery-exit-observation',str(EXIT),'--recovery-exit-sha256',args.recovery_exit_sha256]
    common={'auditor_path':str(AUDITOR),'auditor_sha256':AUDITOR_SHA,'metadata_test_proof_sha256':PROOF_SHA,
        'recovery_plan_sha256':PLAN_SHA,'recovery_exit_sha256':args.recovery_exit_sha256,
        'cmdargv':argv,'runner_sha256':sha(Path(__file__)),'automatic_retry':False,
        'models_generators_or_statistics_launched':False}
    began=time.perf_counter()
    with output.open('xb') as out,stderr.open('xb') as err:
        p=subprocess.Popen(argv,cwd=str(REPO),stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                           creationflags=0x08000000)
        emit(start,{**common,'schema':'paper3-final-readonly-acceptance-process-start-v1',
                    'producer':'ROOT_OWNING_POPEN','pid':p.pid,'started_utc':utc()})
        print(json.dumps({'phase':'FINAL_READONLY_ACCEPTANCE_STARTED','pid':p.pid,'started_utc':utc()}),flush=True)
        while True:
            try:actual=p.wait(timeout=10);break
            except subprocess.TimeoutExpired:
                print(json.dumps({'phase':'FINAL_READONLY_ACCEPTANCE_RUNNING','pid':p.pid,
                                  'elapsed_seconds':round(time.perf_counter()-began,1)}),flush=True)
    result=json.loads(output.read_text(encoding='utf-8'))
    require(sha(AUDITOR)==AUDITOR_SHA and sha(PLAN)==PLAN_SHA and sha(EXIT)==args.recovery_exit_sha256,
            'final auditor or control bindings changed during execution')
    receipt={**common,'schema':'paper3-final-readonly-acceptance-process-exit-v1','producer':'ROOT_OWNING_POPEN_WAIT',
        'pid':p.pid,'actual_exit_code':actual,'finished_utc':utc(),'elapsed_seconds':round(time.perf_counter()-began,3),
        'start_receipt_sha256':sha(start),'result_path':str(output),'result_sha256':sha(output),
        'stderr_path':str(stderr),'stderr_sha256':sha(stderr),'result_status':result['status'],
        'final_acceptance_completed':actual==0 and result['status']=='PASS'}
    emit(finish,receipt)
    print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if receipt['final_acceptance_completed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
