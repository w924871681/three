"""Controlled post-transition continuation only; never stops existing processes.

Requires a separate certified native transition gate. Runs only the unchanged
phase launcher: full attempt002/two workers, then authorized statistics attempt1.
No frozen algorithm/source/configuration is edited and no performance is used
to choose the transition, continuation, task population or statistical rules.
"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paper3_transition_finalizer_common',HERE/'finalizer_continuation.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def phase_command(repo,phase):
    return [str(f.safe(repo,f.ENV_REL)),'-I','-S','-B',str(f.safe(repo,f.SEQUENCE_REL+'/phase_launcher.py')),
            '--phase',phase,'--model-runtime',str(f.safe(repo,f.PREFIX+'model_env_recovery_v1_20261009/MODEL_RUNTIME_SPEC.json')),
            '--attempt','2' if phase=='full' else '1','--test-attempt','4','--workers','2' if phase=='full' else '1']

def phase_gate(repo,phase):
    results=f.safe(repo,f.RESULT_REL)
    if phase=='full':
        gate=f.load(results/'full_experiment_integrity_gate.json')
        f.require(gate.get('manifest_digest')==f.MANIFEST and gate.get('scientific_integrity_pass') is True and gate.get('trajectories')==1200 and gate.get('paired_groups')==240 and gate.get('all_inputs_F1') is True and gate.get('old_results_reused') is False,'actual full1200/240 gate is incomplete')
    elif phase=='statistics':
        gate=f.load(results/'statistics_batch20_env_v3/statistics_execution_receipt.json')
        f.require(gate.get('schema')=='paper3-statistics-execution-receipt-v1' and gate.get('status')=='COMPLETED' and gate.get('exit_code')==0 and gate.get('replication_manifest_digest')==f.MANIFEST,'actual statistics receipt is incomplete')
    else:raise f.FinalizerError('unexpected continuation phase')
    return {'gate_checked':True,'phase':phase}

def run_phases(repo,record,gate_path,pins,call=subprocess.call):
    current='pre-full2-admission'
    for phase in ('full','statistics'):
        current=phase
        f.recheck(pins)
        if phase=='full':f.verify_transition_gate(repo,gate_path,check_resource=True,admission=True)
        attempt=2 if phase=='full' else 1
        f.require(not f.safe(repo,f.SEQUENCE_REL+f'/phase_launches/{phase}_{attempt:03d}').exists(),'continuation phase launch path already exists')
        command=phase_command(repo,phase)
        f.emit(record/(phase+'_start.json'),{'started_utc':f.utc(),'command':command,'outcome_based_continuation':False})
        print(__import__('json').dumps({'phase':phase,'status':'STARTED','workers':2 if phase=='full' else 0}),flush=True)
        code=call(command,cwd=repo)
        f.require(code==0,f'controlled continuation phase failed: {phase}, {code}')
        f.phase_terminal(repo,phase,attempt)
        actual=phase_gate(repo,phase)
        f.recheck(pins)
        f.emit(record/(phase+'_passed.json'),{'finished_utc':f.utc(),'exit_code':code,'gate':actual})
        print(__import__('json').dumps({'phase':phase,'status':'PASSED'}),flush=True)
    return current

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True);parser.add_argument('--transition-gate',required=True)
    args=parser.parse_args()
    f.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    repo=Path(args.repo);f.require(repo==Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION'),'wrong authorized repository')
    f.require(HERE==f.safe(repo,f.SELF_REL),'wrong continuation source directory')
    f.verify_test_proof(HERE,HERE/f.HELPER_PROOF,True)
    gate_path=Path(args.transition_gate)
    transition=f.verify_transition_gate(repo,gate_path,check_resource=True,admission=True)
    record=f.safe(repo,f.CONTINUATION_REL);f.require(not record.exists(),'continuation record already exists');record.mkdir()
    current='preflight'
    try:
        f.exclusive(HERE/'CONTINUATION_EXCLUSIVE_RUN_LOCK.json',(__import__('json').dumps({'pid':__import__('os').getpid(),'created_utc':f.utc()})+'\n').encode())
        pins=dict(transition['evidence_sha256'])
        for rel in (f.SELF_REL,f.PREFIX+'replication_executor_batch20_env_v3',f.PREFIX+'replication_statistics_batch20_env_v3',f.DELIVERY_REL):pins.update(f.py_inventory(f.safe(repo,rel)))
        for rel in (f.SEQUENCE_REL+'/phase_launcher.py',f.SEQUENCE_REL+'/authorized_sequence.py',f.SELF_REL+'/'+f.HELPER_PROOF):
            path=f.safe(repo,rel);pins[str(path)]=f.sha(path)
        f.emit(record/'source_pins.json',pins)
        f.exclusive(record/'sequence_source_snapshot.py',Path(__file__).read_bytes())
        f.emit(record/'start.json',{'started_utc':f.utc(),'implementation_sha256':f.sha(__file__),'transition_gate_path':str(gate_path),'transition_gate_sha256':transition['gate_sha256'],'manifest_digest':f.MANIFEST,'input_bundle_digest':f.F1,'workers':2,'outcome_based_continuation':False,'same_V3_manifest_successful_records_retained':True,'no_original_experiment_records_reused':True})
        current=run_phases(repo,record,gate_path,pins)
        f.emit(record/'finish.json',{'schema':'paper3-worker-transition-continuation-completed-v1','status':'AUTHORIZED_CONTINUATION_COMPLETED','manifest_digest':f.MANIFEST,'finished_utc':f.utc(),'workers':2,'not_a_whole_manuscript_freeze':True,'saved_results_delivery_pending':True})
    except BaseException as error:
        if (record/'statistics_start.json').exists():current='statistics'
        elif (record/'full_start.json').exists():current='full'
        f.emit(record/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','phase':current,'finished_utc':f.utc(),'exception_type':type(error).__name__,'message':str(error),'scientific_pass_claimed':False,'all_prior_attempts_and_outputs_preserved':True})
        raise

if __name__=='__main__':main()
