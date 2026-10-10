"""Root-owned single V4 scientific/artifact acceptance; no statistical recompute."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
BASE=HERE.parent
PYTHON=Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
AUDITOR=HERE/'final_readonly_acceptance.py'
POST=BASE/'replication_metadata_postpublication_finalize_v1'
PLAN=POST/'POSTPUBLICATION_FINALIZATION_PLAN_001.json'
PLAN_SHA='07d20299854c910ba26cfae1977c80b04ff40cde0c0662b3596897bd558729ef'
EXIT=POST/'POSTPUBLICATION_PROCESS_EXIT_001.json'
EXIT_SHA='8e584d5929534d0eb299fcad65490c31f3ca8ade4fe41a1efc83dc67f4a250d8'
OLDPLAN=BASE/'replication_dynamic_delivery_erratum_recovery_v2/ERRATUM_RECOVERY_PLAN_005.json'
OLDPLAN_SHA='44cb35e0df7b584e45944956e64c12d9706eb1aa7acceb28b2302a4e97f15dff'
def require(ok,message):
    if not ok:raise RuntimeError(message)
def utc():return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def emit(path,value):
    with Path(path).open('xb') as f:
        f.write((json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode());f.flush();os.fsync(f.fileno())
def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--auditor-sha256',required=True)
    ap.add_argument('--proof',required=True);ap.add_argument('--proof-sha256',required=True);args=ap.parse_args()
    proof_path=Path(args.proof).resolve()
    require(proof_path.parent==HERE,'proof outside independent auditor')
    for p,h in ((PYTHON,'0562f573871cb16a2fb8de16e3d486e3dfd74bb83c7e87db265561917d05ad1a'),
                (AUDITOR,args.auditor_sha256),(proof_path,args.proof_sha256),(PLAN,PLAN_SHA),(EXIT,EXIT_SHA),(OLDPLAN,OLDPLAN_SHA)):
        require(sha(p)==h,'final audit prerequisite SHA differs: '+str(p))
    proof=read(proof_path)
    require(proof['all_pass'] is True and type(proof['tests_run']) is int and proof['tests_run']>0 and
        proof['errors']==proof['failures']==proof['skipped']==0,'auditor synthetic controls failed')
    upstream=read(EXIT)
    require(type(upstream['actual_exit_code']) is int and upstream['actual_exit_code']==0 and
        type(upstream['native_exit_code']) is int and upstream['native_exit_code']==0 and upstream['identity_unchanged'] is True and
        upstream['plan_sha256']==PLAN_SHA and sha(upstream['finish_path'])==upstream['finish_sha256'],'actual finalizer exit/cert differs')
    cert=read(upstream['finish_path'])
    require(cert['status']=='COMPLETED' and cert['original_metadata_producer_actual_exit_code']=='NOT_OBSERVED' and
        cert['original_exit_zero_contract_satisfied'] is False,'historical unknown exit must remain disclosed')
    result_path=HERE/'FINAL_READONLY_ACCEPTANCE_004.json';stderr=HERE/'FINAL_READONLY_ACCEPTANCE_004.stderr.log'
    start=HERE/'FINAL_READONLY_ACCEPTANCE_PROCESS_START_004.json';exit_path=HERE/'FINAL_READONLY_ACCEPTANCE_PROCESS_004.json'
    require(not any(p.exists() for p in (result_path,stderr,start,exit_path)),'exclusive single full audit required')
    argv=[str(PYTHON),'-I','-S','-B',str(AUDITOR),'--recovery-plan-sha256',OLDPLAN_SHA,
        '--finalization-plan-sha256',PLAN_SHA,'--finalization-exit-observation',str(EXIT),'--finalization-exit-sha256',EXIT_SHA]
    common={'auditor_path':str(AUDITOR),'auditor_sha256':args.auditor_sha256,'test_proof_path':str(proof_path),
        'test_proof_sha256':args.proof_sha256,'finalization_plan_sha256':PLAN_SHA,'finalization_exit_sha256':EXIT_SHA,
        'metadata_recovery_plan_sha256':OLDPLAN_SHA,'runner_sha256':sha(Path(__file__)),
        'models_generators_statistics_or_root_publication_launched':False,'automatic_retry':False,'cmdargv':argv}
    began=time.perf_counter()
    with result_path.open('xb') as out,stderr.open('xb') as err:
        process=subprocess.Popen(argv,cwd=str(REPO),stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=0x08000000)
        emit(start,{**common,'schema':'paper3-final-readonly-acceptance-process-start-v1','producer':'ROOT_OWNING_POPEN','pid':process.pid,'started_utc':utc()})
        print(json.dumps({'phase':'FINAL_SCIENTIFIC_ARTIFACT_ACCEPTANCE_STARTED','pid':process.pid}),flush=True)
        while True:
            try:actual=process.wait(timeout=10);break
            except subprocess.TimeoutExpired:
                print(json.dumps({'phase':'FINAL_SCIENTIFIC_ARTIFACT_ACCEPTANCE_RUNNING','pid':process.pid,'elapsed_seconds':round(time.perf_counter()-began,1)}),flush=True)
    # Persist the real OS exit even when stdout is not parseable.
    raw=HERE/'FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json'
    emit(raw,{**common,'schema':'paper3-final-readonly-actual-exit-v1','producer':'ROOT_OWNING_POPEN_WAIT',
        'pid':process.pid,'actual_exit_code':actual,'observed_utc':utc(),'start_receipt_sha256':sha(start)})
    result=read(result_path)
    for p,h in ((AUDITOR,args.auditor_sha256),(PLAN,PLAN_SHA),(EXIT,EXIT_SHA),(OLDPLAN,OLDPLAN_SHA)):
        require(sha(p)==h,'fixed final audit boundary binding changed')
    passed=actual==0 and result.get('status')=='PASS' and result.get('scientific_and_artifact_acceptance')=='PASS'
    receipt={**common,'schema':'paper3-final-readonly-acceptance-process-exit-v1','producer':'ROOT_OWNING_POPEN_WAIT',
        'pid':process.pid,'actual_exit_code':actual,'finished_utc':utc(),'elapsed_seconds':round(time.perf_counter()-began,3),
        'start_receipt_sha256':sha(start),'actual_exit_observation_sha256':sha(raw),'result_path':str(result_path),'result_sha256':sha(result_path),
        'stderr_path':str(stderr),'stderr_sha256':sha(stderr),'result_status':result.get('status'),'final_acceptance_completed':passed,
        'scientific_and_artifact_acceptance':result.get('scientific_and_artifact_acceptance'),
        'history_all_process_exits_verified':False,'old_metadata_producer_actual_exit_code':'NOT_OBSERVED'}
    emit(exit_path,receipt);print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
