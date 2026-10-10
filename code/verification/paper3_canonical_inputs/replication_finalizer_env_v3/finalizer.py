"""Wait for actual authorized gates; deliver saved outcomes and archive/publish.

Standard library only. This module never imports science code or calculates
statistics. Its only child is the independently tested saved-result delivery.
The root handoff is the sole existing file this tool is authorized to replace.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import zipfile

MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1 = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
PREFIX = 'verification/paper3_canonical_inputs/'
SEQUENCE_REL = PREFIX+'autonomous_replication_execution_20261009_v3'
RESULT_REL = 'results/p7_7_integrity_replication_batch20_env_v3'
DELIVERY_REL = PREFIX+'replication_delivery_env_v3'
SELF_REL = PREFIX+'replication_finalizer_env_v3'
ENV_REL = PREFIX+'model_env_recovery_v1_20261009/P7_7_REPLICATION_MODEL_ENV_V1/Scripts/python.exe'
PACKAGE_REL = 'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_COMPLETED_001'
ROOT_NAME = 'PAPER3_FINAL_REPLICATION_HANDOFF.md'
REPORTS = ('EXECUTION_SUMMARY.md','INPUT_PARITY_AUDIT.md','EXPERIMENT_INTEGRITY_AUDIT.md',
           'CORRECTED_FINAL_STATISTICS.md','ORIGINAL_VS_REPLICATION_COMPARISON.md','SCIENTIFIC_FREEZE_DECISION.md')
METHODS = {'B0','B1','B2','B8','P7.7'}

class FinalizerError(RuntimeError): pass
def require(condition, message):
    if not condition: raise FinalizerError(message)
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): value.update(block)
    return value.hexdigest()
def bytes_sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value):
    return bytes_sha(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
def parse_payload(payload):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'duplicate JSON key'); result[key]=value
        return result
    return json.loads(payload.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(FinalizerError('nonfinite JSON')))
def load(path): return parse_payload(Path(path).read_bytes())
def reject_reparse(path):
    path=Path(path)
    require(not path.is_symlink(),'symlink rejected: '+str(path))
    if path.exists(): require(not getattr(path.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400),'reparse point rejected: '+str(path))
def safe(root, relative):
    root=Path(root); relative=Path(relative)
    require(root.is_absolute(),'root must be absolute')
    require(not relative.is_absolute() and '..' not in relative.parts and relative.parts,'unsafe relative path')
    path=root/relative
    for parent in (path,*path.parents): reject_reparse(parent)
    require(path.resolve().is_relative_to(root.resolve()),'path escapes root')
    return path
def bound(path, digest):
    reject_reparse(path); require(Path(path).is_file(),'bound file missing: '+str(path))
    require(sha(path)==digest,'bound SHA differs: '+str(path)); return Path(path)
def exclusive(path,data):
    path=Path(path)
    for parent in (path,*path.parents): reject_reparse(parent)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
def emit(path,value): exclusive(path,(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode())
def copy_verified(source,target,expected):
    payload=bound(source,expected).read_bytes()
    require(bytes_sha(payload)==expected,'copy source changed between hash/read')
    exclusive(target,payload);bound(target,expected)
    return expected
def inventory(root):
    result={}
    for path in sorted(Path(root).rglob('*')):
        reject_reparse(path)
        if path.is_file(): result[path.relative_to(root).as_posix()]=sha(path)
    return result
def verify_inventory(root, expected, exclusions=()):
    actual=inventory(root)
    for name in exclusions: actual.pop(name,None)
    require(actual==expected,'package file set/SHA differs')
    return actual
def py_inventory(root):
    root=Path(root); require(root.is_dir(),'source directory missing')
    result={}
    for path in sorted(root.rglob('*.py')):
        reject_reparse(path); result[str(path)]=sha(path)
    require(result,'empty source inventory'); return result
def finalizer_static_inventory(root):
    root=Path(root);result={}
    for path in root.iterdir():
        reject_reparse(path)
        if path.is_file() and path.name!='FINALIZER_EXCLUSIVE_RUN_LOCK.json':result[str(path)]=sha(path)
    audit=root/'PUBLICATION_BINDING_FIX_AUDIT_001'
    if audit.exists():
        for relative,digest in inventory(audit).items():result[str(safe(audit,relative))]=digest
    return result
def recheck(pins):
    for path,digest in pins.items(): bound(path,digest)

def verify_test_proof(source_root, receipt, finalizer=False):
    source_root=Path(source_root); receipt=Path(receipt)
    require(receipt.parent==source_root,'test receipt outside implementation root')
    proof=load(receipt)
    require(proof.get('all_pass') is True and proof.get('exit_code')==0,'synthetic tests not successful')
    expected={Path(p).relative_to(source_root).as_posix():h for p,h in py_inventory(source_root).items()}
    require(proof.get('implementation_sha256')==expected,'source changed since tests')
    if finalizer:
        require(proof.get('real_delivery_published') is False and proof.get('real_outcomes_read') is False,'synthetic scope differs')
        require(proof.get('tests_run',0)>=63 and proof.get('tests_skipped')==0,'finalizer required regressions not all executed')
    else:
        require(all(proof.get(key) is False for key in ('real_outcomes_read','models_generators_or_statistics_executed','real_delivery_published')),'delivery test scope differs')
    return sha(receipt)

def phase_terminal(repo,phase,attempt):
    root=safe(repo,SEQUENCE_REL+f'/phase_launches/{phase}_{attempt:03d}')
    terminal=load(root/'finish.json'); start=load(root/'start.json')
    require(terminal.get('phase')==phase and terminal.get('attempt')==attempt,'phase identity differs')
    require(terminal.get('exit_code')==0 and terminal.get('child_exit_code')==0,'phase did not exit successfully')
    require(terminal.get('launch_source_bindings_unchanged') is True and terminal.get('changed_source_paths')==[],'phase source changed')
    pins=start.get('launch_source_sha256',{});require(pins,'launch source binding absent')
    for name,digest in pins.items():
        source=Path(name);require(source.resolve().is_relative_to(Path(repo).resolve()),'phase source outside repository')
        bound(safe(repo,source.relative_to(repo)),digest)
    launcher=safe(repo,SEQUENCE_REL+'/phase_launcher.py')
    bound(root/'launcher_source_snapshot.py',pins[str(launcher)])
    command=start.get('command',[])
    require(command==terminal.get('command') and command[:4]==[str(safe(repo,ENV_REL)),'-I','-S','-B'],'phase command differs')
    scripts=[Path(item) for item in command if item.endswith('.py')]
    require(len(scripts)==1 and str(scripts[0]) in pins,'phase invoked source not bound')
    bound(root/'invoked_script_source_snapshot.py',pins[str(scripts[0])])
    return {str(root/'finish.json'):sha(root/'finish.json'),str(root/'start.json'):sha(root/'start.json')}

def verify_completed(repo):
    repo=Path(repo);seq=safe(repo,SEQUENCE_REL+'/authorized_sequence_003');results=safe(repo,RESULT_REL)
    require(not (seq/'stopped.json').exists(),'authorized sequence stopped')
    finish=load(seq/'finish.json')
    require(finish.get('status')=='AUTHORIZED_PHASE_SEQUENCE_COMPLETED','sequence is not terminal completed')
    start=load(seq/'start.json');require(start.get('outcome_based_continuation') is False,'outcome selection prohibition absent')
    sequence_script=safe(repo,SEQUENCE_REL+'/authorized_sequence.py')
    bound(sequence_script,start['implementation_sha256']);bound(seq/'sequence_source_snapshot.py',start['implementation_sha256'])
    evidence={str(seq/'finish.json'):sha(seq/'finish.json'),str(seq/'start.json'):sha(seq/'start.json')}
    for phase,attempt in (('prepare',2),('initial',1),('minimal',1),('full',1),('statistics',1)):
        passed=load(seq/(phase+'_passed.json'));require(passed.get('exit_code')==0,'sequence gate did not pass '+phase)
        if phase=='prepare': require(passed.get('gate',{}).get('manifest_digest')==MANIFEST,'prepare digest differs')
        else: require(passed.get('gate')=={'gate_checked':True,'phase':phase},'sequence gate differs '+phase)
        evidence[str(seq/(phase+'_passed.json'))]=sha(seq/(phase+'_passed.json'))
        evidence.update(phase_terminal(repo,phase,attempt))
    evidence.update(phase_terminal(repo,'model-load',2))
    model_gate=load(seq/'model_load_gate.json');model=safe(repo,RESULT_REL+'/stage_c_tests/model_load_compatibility/attempt002/model_load_compatibility_receipt.json')
    require(Path(model_gate.get('receipt',''))==model,'model proof path differs');bound(model,model_gate['sha256'])
    require(load(model).get('status')=='PASS','model load proof not PASS')
    bound(safe(repo,SEQUENCE_REL+'/phase_launches/model-load_002/finish.json'),model_gate['terminal_sha256'])
    manifest=load(results/'provenance_manifest.json');unsigned=dict(manifest);unsigned.pop('manifest_digest',None)
    require(manifest.get('manifest_digest')==MANIFEST and canonical(unsigned)==MANIFEST,'manifest digest differs')
    require(manifest.get('input_bundle_digest')==F1,'F1 input differs')
    require(manifest.get('historical_environment_reproduced') is False,'historical environment claim differs')
    require(len(manifest.get('original_protected_snapshot',{}))==2535,'original file inventory differs')
    initial=load(results/'initial_state_manifest.json')
    require(initial.get('manifest_digest')==MANIFEST and initial.get('input_bundle_digest')==F1,'initial provenance differs')
    states=initial.get('states',[])
    expected_states={(c,s) for c in range(33000,33020) for s in (7311,7312,7313)}
    require(initial.get('completed_cases')==60 and len(states)==60 and {(x['center_id'],x['seed']) for x in states}==expected_states,'sixty initial states not complete')
    minimal=load(results/'stage_c_minimal_gate.json')
    require(minimal.get('manifest_digest')==MANIFEST and minimal.get('stage_c_pass') is True and minimal.get('completed_trajectories')==5 and minimal.get('performance_used_for_gate') is False,'minimal gate not complete')
    full=load(results/'full_experiment_integrity_gate.json')
    require(full.get('manifest_digest')==MANIFEST and full.get('scientific_integrity_pass') is True,'full integrity gate absent')
    require(full.get('trajectories')==1200 and full.get('paired_groups')==240,'actual full counts incomplete')
    require(full.get('all_inputs_F1') is True and full.get('old_results_reused') is False,'F1/source population proof differs')
    expected_groups={f'{c}/{s}/{scene}' for c in range(33000,33020) for s in (7311,7312,7313) for scene in ('C0','C1','C3','C4')}
    groups=full.get('groups',{});require(set(groups)==expected_groups,'group coverage differs')
    for group in groups.values():
        require(group.get('five_methods') is True and group.get('all_24_stage_input_fields_equal') is True and set(group.get('receipt_sha256',{}))==METHODS,'five-method group parity absent')
    stats=results/'statistics_batch20_env_v3';receipt=load(stats/'statistics_execution_receipt.json')
    require(receipt.get('schema')=='paper3-statistics-execution-receipt-v1' and receipt.get('status')=='COMPLETED' and receipt.get('exit_code')==0 and receipt.get('replication_manifest_digest')==MANIFEST,'actual statistics not complete')
    require(receipt.get('originals_unchanged') is True and receipt.get('joint_resampling_verified') is True and receipt.get('models_or_generators_executed') is False,'statistics integrity proof differs')
    bound(stats/'statistics_manifest.json',receipt['statistics_manifest_sha256'])
    for relative,digest in receipt['outputs_sha256'].items(): bound(safe(stats,relative),digest)
    for path in (results/'provenance_manifest.json',results/'initial_state_manifest.json',results/'stage_c_minimal_gate.json',results/'full_experiment_integrity_gate.json',stats/'statistics_execution_receipt.json',stats/'statistics_manifest.json',model): evidence[str(path)]=sha(path)
    return evidence

def wait_terminal(repo, poll_seconds, sleep=time.sleep):
    require(0<poll_seconds<=60,'poll must be bounded to <=60 seconds')
    sequence=safe(repo,SEQUENCE_REL+'/authorized_sequence_003')
    while True:
        if (sequence/'stopped.json').exists():
            stopped=load(sequence/'stopped.json')
            raise FinalizerError('sequence STOPPED; no delivery/publication: '+json.dumps(stopped,sort_keys=True))
        if (sequence/'finish.json').exists(): return
        sleep(poll_seconds)

def verify_delivery(repo):
    results=safe(repo,RESULT_REL);package=safe(repo,PACKAGE_REL)
    require(package.is_dir(),'delivery package missing')
    payload=(package/'DELIVERY_MANIFEST.json').read_bytes();delivery=parse_payload(payload)
    require(delivery.get('schema')=='paper3-saved-results-delivery-v1' and delivery.get('status')=='COMPLETED' and delivery.get('replication_manifest_digest')==MANIFEST,'delivery did not pass')
    require(Path(delivery.get('package_root',''))==package,'delivery package identity differs')
    require(delivery.get('root_handoff_modified') is False and delivery.get('original_protected_files_unchanged')==2535,'delivery preservation differs')
    require((results/'DELIVERY_MANIFEST.json').read_bytes()==payload,'result and package delivery manifests differ')
    for root in (results,package):
        require((root/'DELIVERY_MANIFEST.json.sha256').read_text().split()[0]==bytes_sha(payload),'delivery manifest sidecar differs')
    verify_inventory(package,delivery['package_files_sha256'],('DELIVERY_MANIFEST.json','DELIVERY_MANIFEST.json.sha256'))
    for name,digest in delivery['results_report_files_sha256'].items():
        require(Path(name).parent==results,'report outside new results');bound(name,digest)
    for name in (*REPORTS,'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'):
        require(name in delivery['package_files_sha256'],'necessary report absent');bound(package/name,delivery['package_files_sha256'][name])
    delivery['_verified_manifest_sha256']=bytes_sha(payload)
    sidecar=(package/'DELIVERY_MANIFEST.json.sha256').read_bytes()
    require(sidecar.decode().split()[0]==bytes_sha(payload),'delivery sidecar changed during read')
    delivery['_verified_sidecar_sha256']=bytes_sha(sidecar)
    return delivery

def delivery_command(repo):
    return [str(safe(repo,ENV_REL)),'-I','-S','-B',str(safe(repo,DELIVERY_REL+'/delivery.py')),
            '--repo',str(repo),'--expected-manifest-digest',MANIFEST,
            '--synthetic-test-receipt',str(safe(repo,DELIVERY_REL+'/SYNTHETIC_TEST_RESULTS_ATTEMPT003.json')),
            '--handoff-relative',PACKAGE_REL]

def history_index(repo):
    """Index every small provenance/source/log file in all known harness attempts.

    No outcome fields are inspected for selection; metadata files are inventoried
    regardless of pass/fail. Raw trajectories, weights and arrays are excluded.
    """
    repo=Path(repo);base=safe(repo,PREFIX.rstrip('/'));roots=[]
    for name in ('autonomous_replication_execution_20261009','autonomous_replication_execution_20261009_v2','autonomous_replication_execution_20261009_v3'):
        roots.append(base/name)
    roots.extend((base/'execution_20261009',base/'replication_executor_batch20_env_v2/TOY_READ_SCOPE_CLARIFICATION.json'))
    for name in ('p7_7_integrity_replication_batch20_v1','p7_7_integrity_replication_environment_review_20261009_v2','p7_7_integrity_replication_batch20_env_v1','p7_7_integrity_replication_batch20_env_v2','p7_7_integrity_replication_batch20_env_v3'):
        root=safe(repo,'results/'+name)
        for part in ('stage_c_tests','execution','failures','attempts','workers'): roots.append(root/part)
        if root.exists():roots.extend(path for path in root.iterdir() if path.is_file())
    index={};suffixes={'.json','.log','.md','.patch','.py','.before','.sha256','.txt'}
    for root in roots:
        if not root.exists(): continue
        for path in ([root] if root.is_file() else sorted(root.rglob('*'))):
            reject_reparse(path)
            if path.is_file() and path.suffix.lower() in suffixes:
                index[str(path)]={'sha256':sha(path),'bytes':path.stat().st_size,'copied':False}
    require(index,'empty harness provenance inventory')
    return index

@contextmanager
def locked_root(path):
    """Windows kernel denies concurrent writers/deleters during publication.

    Synthetic tests replace this context with isolated temporary descriptors.
    No weaker non-Windows publication fallback is supplied.
    """
    require(os.name=='nt','actual root publication requires Windows deny-write handle')
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateFileW(str(path),0x80000000|0x40000000,0x1,None,3,0x80,None)
    require(handle!=wintypes.HANDLE(-1).value,'root handoff busy/unavailable; WinError '+str(ctypes.get_last_error()))
    try: fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle);raise
    with os.fdopen(fd,'r+b') as stream: yield stream

def publish_root(repo, publication, expected_old_sha, draft, expected_draft_sha, lock=locked_root, precommit=lambda:None):
    repo=Path(repo);publication=Path(publication);root=safe(repo,ROOT_NAME)
    require(publication.is_dir(),'exclusive publication directory missing')
    draft=Path(draft);reject_reparse(draft);data=draft.read_bytes();new_sha=bytes_sha(data)
    require(new_sha==expected_draft_sha,'saved draft bytes differ from authoritative delivery manifest')
    with lock(root) as stream:
        prior=stream.read();require(bytes_sha(prior)==expected_old_sha,'root handoff changed since finalizer launch; publication refused')
        precommit()
        exclusive(publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md',prior)
        exclusive(publication/ROOT_NAME,data)
        bound(publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md',expected_old_sha)
        bound(publication/ROOT_NAME,expected_draft_sha)
        emit(publication/'PUBLICATION_PRECOMMIT.json',{'previous_sha256':expected_old_sha,'new_sha256':new_sha,'draft_path':str(draft),'started_utc':utc(),'authorized_existing_file':str(root),'concurrent_writes_denied':True})
        stream.seek(0);stream.write(data);stream.truncate();stream.flush();os.fsync(stream.fileno())
        stream.seek(0);require(bytes_sha(stream.read())==new_sha,'published root byte verification failed')
        emit(publication/'PUBLICATION_RECEIPT.json',{'status':'PUBLISHED_VERIFIED_SAVED_DRAFT','previous_sha256':expected_old_sha,'new_sha256':new_sha,'published_utc':utc(),'all_prior_bytes_archived':True})
    return new_sha

def make_zip(package, target):
    package=Path(package);target=Path(target);before=inventory(package)
    require(not target.exists(),'ZIP target already exists')
    with target.open('xb') as raw:
        with zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
            for relative,digest in before.items():
                path=bound(safe(package,relative),digest);archive.write(path,relative)
        raw.flush();os.fsync(raw.fileno())
    require(inventory(package)==before,'package changed while archiving')
    with zipfile.ZipFile(target) as archive:
        names=archive.namelist();require(len(names)==len(set(names)) and set(names)==set(before),'ZIP file inventory differs')
        for name,digest in before.items(): require(bytes_sha(archive.read(name))==digest,'ZIP payload SHA differs')
    return sha(target)

def package_final(repo, record, evidence, delivery, old_root_sha, source_pins):
    repo=Path(repo);record=Path(record);target=safe(repo,'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_FINAL_PACKAGE_001')
    require(not target.exists() and not target.with_suffix('.zip').exists(),'final independent package/ZIP exists');target.mkdir()
    source=safe(repo,PACKAGE_REL)
    # Preserve original reviewed package and all its manifest-bound files unchanged.
    expected=dict(delivery['package_files_sha256'])
    expected['DELIVERY_MANIFEST.json']=delivery['_verified_manifest_sha256']
    expected['DELIVERY_MANIFEST.json.sha256']=delivery['_verified_sidecar_sha256']
    verify_inventory(source,expected)
    for relative,digest in expected.items():copy_verified(safe(source,relative),safe(target,'reviewed_delivery/'+relative),digest)
    verify_inventory(target/'reviewed_delivery',expected)
    harness=history_index(repo)
    emit(target/'supplements/HARNESS_ATTEMPT_HISTORY.json',{'schema':'paper3-harness-history-index-v1','created_utc':utc(),'inventory_sha256':canonical(harness),'files':harness,'all_attempts_indexed_regardless_of_outcome':True,'no_prior_trajectory_reused':True,'scientific_counts_are_only_actual_V3_gate_counts':True})
    emit(target/'supplements/ACTUAL_FINAL_GATES.json',{'manifest_digest':MANIFEST,'F1_digest':F1,'counts':{'initial_states':60,'trajectories':1200,'paired_groups':240},'evidence_sha256':evidence,'delivery_manifest_sha256':sha(source/'DELIVERY_MANIFEST.json')})
    text='''# Independent finalizer provenance supplement

The reviewed six reports and DELIVERY_MANIFEST are unmodified. All listed V1/V2/V3 harness attempts, successful and unsuccessful, are indexed independently by complete path and SHA. Earlier pre-import, generated Torch namespace, inactive estimator-class, metadata, strict runtime-map and missing authorization-record failures are execution provenance; they are never reused as successful scientific trajectories.

The earlier V2 post-import environment map was not saved: its exact first writer remains INFERRED. The actual V3 model-load attempt001 separately records the threadpoolctl first-writer rejection. V3 attempt002 observes the frozen threadpoolctl line48 and sklearn line60 default writers, binds their source SHA, and succeeds without verifier-written environment variables. The actual source fix and synthetic tests are indexed in THREADPOOL_IMPORT_FIX_001 and FINAL_THREADPOOL_IMPORT_REVIEW.md. These are import-provenance facts, not proof of numerical neutrality.

The retained V2 toy receipt's broad source_checkpoints_read=false wording is qualified by the separately indexed TOY_READ_SCOPE_CLARIFICATION.json: checkpoint bytes were read for SHA verification, without deserialization, project-model execution, F1-array access or scientific parameter updates. The V3 toy records this distinction explicitly. Actual RNN contiguous-weight runtime warnings are preserved as runtime observations; no flatten_parameters call or frozen algorithm modification is introduced to remove them.

The independent Python3.11 runtime retains scientific Torch/NumPy versions and the authorized River0.23.0/pandas2.x compatibility adjustment. Historical psutil version and exact historical environment remain NOT_VERIFIED. Approved dependency choices were fixed before observing replication performance. New-vs-old changes cannot be uniquely attributed to inputs, runtime or stochastic paths. This is a post-observation integrity-correction evaluation, not a never-seen heldout evaluation. No whole-manuscript freeze or submission is authorized by completion alone.

No independent human scientific review is claimed by these software gates. Root publication uses a Windows deny-write/delete handle and a prior fsynced byte archive, but the in-place root update is not transactional or atomic against power/process failure. A failure preserves the archive, partial package and permanent finalizer lock for independent diagnosis; the tool never retries publication automatically.

Actual terminal counts and saved statistics are checked before delivery. This finalizer computes no performance statistics or Bootstrap and chooses no protocol based on outcomes. No raw1200 trajectory payload, arrays, model checkpoint or environment binary is copied into this final package. Their saved paths and SHA indexes remain in the reviewed delivery.
'''
    exclusive(target/'supplements/PROVENANCE_AND_LIMITATIONS.md',text.encode())
    for name in ('start.json','source_pins.json'):
        item=record/name;copy_verified(item,target/'finalizer_evidence'/name,sha(item))
    own_root=Path(__file__).parent
    for name,digest in source_pins.items():
        path=Path(name)
        if path.is_relative_to(own_root):copy_verified(path,safe(target/'finalizer_source',path.relative_to(own_root)),digest)
    publication=target/'root_publication';publication.mkdir()
    def precommit():
        recheck(source_pins);recheck(evidence)
        verify_inventory(source,expected);verify_inventory(target/'reviewed_delivery',expected)
    new_sha=publish_root(repo,publication,old_root_sha,source/'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md',expected['PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'],precommit=precommit)
    files=inventory(target)
    emit(target/'FINAL_PACKAGE_MANIFEST.json',{'schema':'paper3-finalizer-package-v1','status':'COMPLETED','created_utc':utc(),'replication_manifest_digest':MANIFEST,'root_handoff_sha256':new_sha,'previous_root_handoff_sha256':old_root_sha,'files_sha256':files,'self_excluded':True,'reports_and_original_delivery_unchanged':True})
    verify_inventory(target,files,('FINAL_PACKAGE_MANIFEST.json',))
    zipped=target.with_suffix('.zip');zip_sha=make_zip(target,zipped)
    return {'package_root':str(target),'zip_path':str(zipped),'zip_sha256':zip_sha,'final_package_manifest_sha256':sha(target/'FINAL_PACKAGE_MANIFEST.json'),'root_handoff_sha256':new_sha,'previous_root_handoff_sha256':old_root_sha}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True);parser.add_argument('--attempt',type=int,required=True)
    parser.add_argument('--poll-seconds',type=int,default=30)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    require(args.attempt>0 and 0<args.poll_seconds<=60,'invalid attempt/poll')
    repo=Path(args.repo);require(repo.is_absolute() and repo==Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION'),'only the explicitly authorized repository is allowed')
    source=safe(repo,SELF_REL);require(Path(__file__).resolve().parent==source.resolve(),'unexpected finalizer source root')
    verify_test_proof(source,source/'SYNTHETIC_TEST_RESULTS_ATTEMPT001.json',True)
    delivery_root=safe(repo,DELIVERY_REL);proof=delivery_root/'SYNTHETIC_TEST_RESULTS_ATTEMPT003.json'
    verify_test_proof(delivery_root,proof)
    record=safe(source,f'attempt{args.attempt:03d}');require(not record.exists(),'finalizer attempt exists');record.mkdir()
    current='preflight'
    try:
        # Permanent exclusive lock prevents two independent finalizers publishing.
        exclusive(source/'FINALIZER_EXCLUSIVE_RUN_LOCK.json',(json.dumps({'attempt':args.attempt,'pid':os.getpid(),'created_utc':utc()})+'\n').encode())
        pins={}
        for rel in (SELF_REL,DELIVERY_REL,PREFIX+'replication_executor_batch20_env_v3',PREFIX+'replication_statistics_batch20_env_v3'):
            pins.update(py_inventory(safe(repo,rel)))
        pins.update(finalizer_static_inventory(source))
        for rel in (SEQUENCE_REL+'/authorized_sequence.py',SEQUENCE_REL+'/phase_launcher.py',SEQUENCE_REL+'/model_load_compatibility.py',SELF_REL+'/SYNTHETIC_TEST_RESULTS_ATTEMPT001.json',DELIVERY_REL+'/SYNTHETIC_TEST_RESULTS_ATTEMPT003.json',ENV_REL):
            path=safe(repo,rel);pins[str(path)]=sha(path)
        old_sha=sha(safe(repo,ROOT_NAME));emit(record/'source_pins.json',pins)
        emit(record/'start.json',{'started_utc':utc(),'pid':os.getpid(),'expected_manifest_digest':MANIFEST,'expected_F1_digest':F1,'previous_root_handoff_sha256':old_sha,'source_pins_digest':canonical(pins),'science_or_statistics_executed':False,'delivery_command':delivery_command(repo),'waits_for_actual_terminal_gates':True})
        require(not safe(repo,PACKAGE_REL).exists(),'reviewed delivery package already exists')
        require(not safe(repo,'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_FINAL_PACKAGE_001').exists(),'final package already exists')
        require(not safe(repo,'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_FINAL_PACKAGE_001.zip').exists(),'final ZIP already exists')
        current='waiting_for_actual_sequence';wait_terminal(repo,args.poll_seconds)
        current='verifying_actual_gates';recheck(pins);evidence=verify_completed(repo)
        emit(record/'ACTUAL_GATE_VERIFICATION.json',{'status':'PASS','evidence_sha256':evidence,'verified_utc':utc()})
        recheck(pins);verify_test_proof(delivery_root,proof)
        require(sha(safe(repo,ROOT_NAME))==old_sha,'root handoff changed while waiting; no delivery/publication')
        current='reviewed_saved_result_delivery'
        with (record/'delivery_stdout.log').open('xb') as out,(record/'delivery_stderr.log').open('xb') as err:
            code=subprocess.call(delivery_command(repo),cwd=repo,stdout=out,stderr=err)
        emit(record/'DELIVERY_PROCESS_FINISH.json',{'exit_code':code,'finished_utc':utc()})
        require(code==0,'saved-result delivery failed; outputs preserved')
        recheck(pins);recheck(evidence);delivery=verify_delivery(repo)
        current='supplement_archive_publish_zip';package=package_final(repo,record,evidence,delivery,old_sha,pins)
        recheck(pins);recheck(evidence);verify_delivery(repo)
        emit(record/'finish.json',{'status':'COMPLETED','finished_utc':utc(),'counts':{'initial_states':60,'trajectories':1200,'paired_groups':240},'no_new_models_generators_or_statistics_executed':True,'final_delivery':package,'original_reports_and_data_not_modified':True,'not_whole_manuscript_freeze':True})
        print(json.dumps({'status':'COMPLETED','final_delivery':package},indent=2))
    except BaseException as error:
        emit(record/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','phase':current,'finished_utc':utc(),'exception_type':type(error).__name__,'message':str(error),'scientific_pass_claimed':False,'all_partial_outputs_preserved':True})
        raise

if __name__=='__main__': main()
