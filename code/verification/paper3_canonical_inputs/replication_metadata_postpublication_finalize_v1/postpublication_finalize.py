"""Read only already published metadata artifacts; never reconstruct an old exit."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import types
import time
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
BASE=HERE.parent
RECOVERY=BASE/'replication_dynamic_delivery_erratum_recovery_v2'
OLD=BASE/'replication_dynamic_delivery_erratum_v1'
PACKAGE=REPO/'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
ZIP=PACKAGE.with_suffix('.zip')
ROOT=REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md'
STATS=REPO/'results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3'
RECORD=HERE/'finalize001'
PLAN=HERE/'POSTPUBLICATION_FINALIZATION_PLAN_001.json'
PROOF=HERE/'POSTPUBLICATION_FINALIZATION_TEST_RESULTS_001.json'
OWN=('postpublication_finalize.py','root_finalize_launch.py','test_postpublication_finalize.py')
SCOPE='ARTIFACT_FINALIZATION_AFTER_EXIT_OBSERVER_FAILURE'
H1='c7b539bef23e3f43e1d663bc9240ab80cd325d2f1f7dd501e0b22cd18e3b8a3d'
H2='2a522ae64713ffc6e3cbe1389a7faac15d267dd123675590f5f813d50cf33368'
FROZEN={
 RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json':'44cb35e0df7b584e45944956e64c12d9706eb1aa7acceb28b2302a4e97f15dff',
 RECOVERY/'BOUNDARY_STOP_RECOVERY_TEST_RESULTS_005.json':'5e488c9dea6a775a4f5bbafab359a942a0f6d61825f873c47d664f468aa9b1af',
 RECOVERY/'ROOT_ERRATUM_RECOVERY_PROCESS_START_004.json':'29e4c8004066be28dc76d8697f379ce82789b8f7ae8bd26cf9c18381ecb59421',
 RECOVERY/'erratum_recovery004/finish.json':'1bc8dba3a9f06c998ab786d0a9ab5300dba93338fb8e86de6c478db970268e03',
 RECOVERY/'ROOT_EXIT_OBSERVER_FAILURE_004.json':'92de2eec50b9be2200eb02296b64e45ff927452d6eb4911ec577e24ebfa4f5c7',
 OLD/'metadata_erratum.py':'3461322dd57af084d46a98d6cdb66abca473d006902fb90e37694013d92bebce',
 OLD/'erratum_watch.py':'cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2',
 PACKAGE/'ERRATUM_MANIFEST.json':'2ada566465c1fe4f2bf4b6db0da22d8404cd6a0bdf8c7870820bb27e4df88bd8',
 ZIP:'b6e5ba6660b1c256be7775823b75074342a9b8cf0a1f1336ec0cde735fbf7df8',
 ROOT:H2,
 STATS/'statistics_manifest.json':'a2cd080532db281ca60ae89ee9edf5e272552689f8be9220eaf7c7857b3f1468',
 STATS/'statistics_execution_receipt.json':'82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec'}

def require(ok,message):
    if not ok: raise RuntimeError(message)
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def safe(path,root=REPO):
    p=Path(path).absolute();root=Path(root).resolve()
    require(p.is_relative_to(root),'path outside authorized root')
    for ancestor in (p,*p.parents):
        require(not ancestor.is_symlink(),'symlink rejected')
        if ancestor.exists(): require(not getattr(ancestor.lstat(),'st_file_attributes',0)&0x400,'reparse rejected')
        if ancestor==root: break
    return p
def read(path):
    def unique(items):
        out={}
        for k,v in items: require(k not in out,'duplicate JSON key');out[k]=v
        return out
    return json.loads(safe(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(RuntimeError('nonfinite JSON')))
def bound(path,digest,root=REPO):
    p=safe(path,root);require(p.is_file() and sha(p)==digest,'bound SHA differs: '+str(p));return p
def emit(path,value):
    p=safe(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:
        f.write((json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode());f.flush();os.fsync(f.fileno())
    return {'path':str(p),'sha256':sha(p)}
def module(path,name,digest):
    payload=bound(path,digest).read_bytes();require(hashlib.sha256(payload).hexdigest()==digest,'source raced')
    m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m
    exec(compile(payload,str(path),'exec'),m.__dict__);return m
def own_pins(): return {str(HERE/n):sha(HERE/n) for n in OWN}
def verify_history(start,failure,finish):
    require(start.get('pid')==10108 and start.get('producer')=='ROOT_OWNING_POPEN' and
        start.get('plan_sha256')==FROZEN[RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json'],'old launch differs')
    require(failure.get('original_metadata_producer_pid')==10108 and
        failure.get('original_metadata_producer_actual_exit_code')=='NOT_OBSERVED' and
        type(failure.get('actual_tool_exit_code')) is int and failure['actual_tool_exit_code']==1 and
        failure.get('actual_exit_zero_reconstructed') is False and failure.get('old_exit_receipt_written') is False,'old unknown exit must remain unknown')
    require(finish.get('status')=='SMOKE_COUNT_METADATA_ERRATUM_COMPLETED' and finish.get('statistics_bytes_unchanged') is True and
        finish.get('root_handoff_sha256')==H2 and finish.get('zip_sha256')==FROZEN[ZIP] and
        finish.get('package')==str(PACKAGE) and finish.get('zip')==str(ZIP),'producer legal finish differs')
def inventory(root):
    out={}
    for p in sorted(Path(root).rglob('*')):
        safe(p)
        if p.is_file():out[p.relative_to(root).as_posix()]=sha(p)
        else:require(p.is_dir(),'nonregular artifact')
    return out
def verify_inventory(actual,expected): require(actual==expected,'package inventory/hash differs')
def verify_zip(path,expected):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();require(len(names)==len(set(names)) and set(names)==set(expected),'ZIP inventory/duplicate differs')
        for n,h in expected.items():require(hashlib.sha256(z.read(n)).hexdigest()==h,'ZIP member SHA differs: '+n)
def verify_publication(value):
    require(value.get('status')=='PUBLISHED_VERIFIED_SAVED_DRAFT' and value.get('previous_sha256')==H1 and
        value.get('new_sha256')==H2 and value.get('all_prior_bytes_archived') is True,'root publication chain differs')
def verify_proof(plan):
    proof=read(bound(plan['test_proof_path'],plan['test_proof_sha256']))
    require(proof.get('all_pass') is True and type(proof.get('tests_run')) is int and proof['tests_run']>0 and
        all(type(proof.get(k)) is int and proof[k]==0 for k in ('errors','failures','skipped')) and
        proof.get('implementation_sha256')==own_pins(),'new finalizer proof/source differs')
def verify_plan(path,digest):
    plan=read(bound(path,digest))
    require(plan.get('schema')=='paper3-metadata-postpublication-plan-v1' and plan.get('scope')==SCOPE and
        plan.get('source_sha256')==own_pins() and plan.get('bound_files_sha256')=={str(p):h for p,h in FROZEN.items()} and
        plan.get('original_metadata_producer_actual_exit_code')=='NOT_OBSERVED' and plan.get('record_root')==str(RECORD) and
        plan.get('models_statistics_or_root_publication_executed') is False,'postpublication scope/binding differs')
    verify_proof(plan);return plan
def validate_artifacts():
    for p,h in FROZEN.items():bound(p,h)
    oldplan=read(RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json')
    for group in (oldplan['implementation_sha256'],oldplan['metadata_recovery']['source_sha256'],oldplan['metadata_recovery']['old_failure_files_sha256']):
        for p,h in group.items():bound(p,h)
    require(not (RECOVERY/'ROOT_ERRATUM_RECOVERY_PROCESS_EXIT_004.json').exists(),'historical exit was not observed; do not fill it')
    require(not (RECOVERY/'erratum_recovery004/stopped.json').exists(),'producer stopped evidence exists')
    verify_history(read(RECOVERY/'ROOT_ERRATUM_RECOVERY_PROCESS_START_004.json'),read(RECOVERY/'ROOT_EXIT_OBSERVER_FAILURE_004.json'),read(RECOVERY/'erratum_recovery004/finish.json'))
    manifest=read(PACKAGE/'ERRATUM_MANIFEST.json')
    require(manifest.get('status')=='COMPLETED' and manifest.get('manifest_self_and_sidecar_excluded') is True,'package manifest differs')
    actual=inventory(PACKAGE);expected=dict(manifest['package_files_sha256'])
    require((PACKAGE/'ERRATUM_MANIFEST.json.sha256').read_bytes()==(FROZEN[PACKAGE/'ERRATUM_MANIFEST.json']+'  ERRATUM_MANIFEST.json\n').encode(),'manifest sidecar differs')
    expected['ERRATUM_MANIFEST.json']=FROZEN[PACKAGE/'ERRATUM_MANIFEST.json']
    expected['ERRATUM_MANIFEST.json.sha256']=sha(PACKAGE/'ERRATUM_MANIFEST.json.sha256')
    verify_inventory(actual,expected);verify_zip(ZIP,expected)
    verify_publication(read(PACKAGE/'root_publication/PUBLICATION_RECEIPT.json'))
    bound(PACKAGE/'root_publication/PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md',H1)
    e=module(OLD/'metadata_erratum.py','postpublication_original_report_api',FROZEN[OLD/'metadata_erratum.py'])
    original=PACKAGE/'original_v1_final_package/reviewed_delivery'
    metadata=read(PACKAGE/'ERRATUM.json')
    for name in (*e.REPORTS,e.DRAFT):
        corrected,info=e.correct_report((original/name).read_bytes(),name,PACKAGE/'corrected_reports')
        require(corrected==(PACKAGE/'corrected_reports'/name).read_bytes() and info==metadata['changed_reports'][name],'report inverse metadata-only bytes differ: '+name)
    stats_manifest=read(STATS/'statistics_manifest.json')
    outputs={str(STATS/n):h for n,h in stats_manifest['outputs_sha256'].items()}
    require(len(outputs)==16 and metadata.get('statistics_files_sha256')==outputs and metadata.get('all_statistics_bytes_preserved') is True,'saved statistics map differs')
    for p,h in outputs.items():bound(p,h)
    require(metadata.get('statistics_manifest_sha256')==FROZEN[STATS/'statistics_manifest.json'] and metadata.get('statistics_receipt_sha256')==FROZEN[STATS/'statistics_execution_receipt.json'],'saved statistics manifest/receipt binding differs')
    # A new readonly finalization certifies artifacts only. Full scientific audit follows independently.
    return {'package':str(PACKAGE),'package_manifest_sha256':FROZEN[PACKAGE/'ERRATUM_MANIFEST.json'],
        'package_file_count':len(actual),'package_files_sha256':actual,'zip':str(ZIP),'zip_sha256':FROZEN[ZIP],
        'root_handoff_sha256':H2,'statistics_files_sha256':outputs,
        'statistics_manifest_sha256':FROZEN[STATS/'statistics_manifest.json'],
        'statistics_execution_receipt_sha256':FROZEN[STATS/'statistics_execution_receipt.json'],
        'statistics_bytes_unchanged':True,'reports_inverse_bytes_preserved':True,
        'producer_plan_sha256':FROZEN[RECOVERY/'ERRATUM_RECOVERY_PLAN_005.json'],
        'producer_finish_sha256':FROZEN[RECOVERY/'erratum_recovery004/finish.json'],
        'observer_failure_sha256':FROZEN[RECOVERY/'ROOT_EXIT_OBSERVER_FAILURE_004.json']}
def create_plan():
    require(not PLAN.exists(),'exclusive new plan required')
    plan={'schema':'paper3-metadata-postpublication-plan-v1','scope':SCOPE,'source_sha256':own_pins(),
        'test_proof_path':str(PROOF),'test_proof_sha256':sha(PROOF),'bound_files_sha256':{str(p):h for p,h in FROZEN.items()},
        'record_root':str(RECORD),'original_metadata_producer_pid':10108,'original_metadata_producer_actual_exit_code':'NOT_OBSERVED',
        'models_statistics_or_root_publication_executed':False,'created_utc':utc()}
    verify_proof(plan)
    for p,h in FROZEN.items():bound(p,h)
    return emit(PLAN,plan)
def execute(path,digest):
    plan=verify_plan(path,digest);require(not RECORD.exists(),'exclusive readonly finalization required')
    deadline=time.monotonic()+15
    while not (HERE/'POSTPUBLICATION_PROCESS_START_001.json').exists() and time.monotonic()<deadline:time.sleep(.02)
    launch=read(HERE/'POSTPUBLICATION_PROCESS_START_001.json')
    require(launch.get('pid')==os.getpid() and launch.get('plan_sha256')==digest and launch.get('producer')=='ROOT_OWNING_POPEN','root launch identity must precede certification')
    emit(RECORD/'start.json',{'schema':'paper3-postpublication-finalization-start-v1','plan_sha256':digest,'pid':os.getpid(),'started_utc':utc()})
    try:
        evidence=validate_artifacts();verify_plan(path,digest)
        # Final fixed-boundary files, no full environment/model/raw rescan here.
        for p,h in FROZEN.items():bound(p,h)
        return emit(RECORD/'finish.json',{'schema':'paper3-metadata-postpublication-artifact-finalization-v1','status':'COMPLETED',
            'scope':SCOPE,'plan_sha256':digest,'pid':os.getpid(),'source_sha256':plan['source_sha256'],
            'original_metadata_producer_pid':10108,'original_metadata_producer_actual_exit_code':'NOT_OBSERVED',
            'root_exit_observer_failed':True,'original_observer_tool_actual_exit_code':1,
            'history_all_process_exits_verified':False,'original_exit_zero_contract_satisfied':False,
            'scientific_acceptance':'NOT_PERFORMED_BY_THIS_METADATA_FINALIZER',
            'models_statistics_or_root_publication_executed':False,'finished_utc':utc(),**evidence})
    except BaseException as exc:
        emit(RECORD/'stopped.json',{'status':'STOPPED','plan_sha256':digest,'pid':os.getpid(),'error':repr(exc),'utc':utc()});raise
def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('create-plan','execute'))
    ap.add_argument('--plan');ap.add_argument('--plan-sha256');args=ap.parse_args()
    result=create_plan() if args.action=='create-plan' else execute(args.plan,args.plan_sha256)
    print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__': main()
