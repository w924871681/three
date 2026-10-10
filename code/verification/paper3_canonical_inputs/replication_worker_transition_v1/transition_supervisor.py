"""Wait for memory, then run one explicitly authorized worker transition.

Only reads while waiting. Never closes user apps, changes pagefiles, regenerates
inputs, or signals experiment processes itself. The separately tested controller
is the only process-control authority. The unchanged scientific launcher and
statistics are invoked by the separately tested continuation after its gate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
RESULTS = REPO/'results/p7_7_integrity_replication_batch20_env_v3'
MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
ROOT_SHA = 'f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8'
PROOF_NAME = 'SUPERVISOR_SYNTHETIC_TEST_RESULTS_001.json'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def utc(): return datetime.now(timezone.utc).isoformat()
def require(value, message):
    if not value: raise RuntimeError(message)

def emit(path, value):
    path = Path(path)
    require(path.resolve().is_relative_to(HERE), 'Supervisor output escaped its new directory')
    require(not any(p.is_symlink() or (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0)&0x400)
                    for p in (path, *path.parents)), 'Supervisor reparse path rejected')
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())

def load_local(name):
    path = HERE/(name+'.py')
    spec = importlib.util.spec_from_file_location('paper3_supervisor_'+name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

def recheck(pins):
    for path, digest in pins.items(): require(sha(path) == digest, 'Supervisor source/evidence changed: '+path)

def resource_wait(sample, record, recheck_sources, sleep=time.sleep, *, stable_samples=3, interval=10):
    """Pure loop orchestration; returns without any process control on old end."""
    require(stable_samples >= 3 and 0 < interval <= 60, 'Unsafe resource observation policy')
    consecutive = 0
    while True:
        recheck_sources()
        state = sample()
        record(state)
        if state['old_full_complete']: return 'NOT_NEEDED_OLD_FULL_COMPLETED'
        require(not state['old_failure'], 'Old scientific run failed naturally; no scheduling change')
        require(state['old_worker_alive'], 'Old worker disappeared; no scheduling change')
        require(state['existing_private_bytes'] > 0, 'Unusable old worker memory sample')
        minimum = max(int(4.5*1024**3), state['existing_private_bytes']+1024**3)
        consecutive = consecutive+1 if state['free_commit_bytes'] >= minimum else 0
        if consecutive >= stable_samples: return 'RESOURCE_ADMISSION_READY'
        sleep(interval)

def commands(executable, pins_path, transition_dir):
    common = [str(executable), '-I', '-S', '-B']
    gate = transition_dir/'transition_gate.json'
    return {
        'controller': common+[str(HERE/'migration_controller.py'), '--execution-dir', str(transition_dir),
            '--implementation-pins', str(pins_path), '--authorize-native-transition'],
        'continuation': common+[str(HERE/'continuation.py'), '--repo', str(REPO), '--transition-gate', str(gate)],
        'finalizer': common+[str(HERE/'finalizer_continuation.py'), '--repo', str(REPO), '--transition-gate', str(gate),
            '--attempt', '1', '--poll-seconds', '30'],
    }

def run_flow(command_map, record_dir, transition_dir, recheck_sources,
             *, popen=subprocess.Popen, sleep=time.sleep):
    """Run exactly one controller, then continuation and saved-outcome waiter."""
    recheck_sources()
    handles = []
    def launch(name):
        stream = (record_dir/(name+'.log')).open('xb'); handles.append(stream)
        command = command_map[name]
        child = popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=stream,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        emit(record_dir/(name+'_launch.json'), {'created_utc':utc(), 'pid':child.pid, 'command':command})
        return child
    try:
        controller = launch('controller'); code = controller.wait()
        emit(record_dir/'controller_exit.json', {'created_utc':utc(), 'exit_code':code})
        require(code == 0, 'Transition controller stopped; no replacement launched')
        gate = read(transition_dir/'transition_gate.json')
        require(gate.get('status') == 'PASS' and gate.get('worker_count') == 2
                and gate.get('manifest_digest') == MANIFEST, 'No actual certified transition gate')
        recheck_sources()
        continuation = launch('continuation')
        for _ in range(60):
            if (HERE/'continuation_001/start.json').is_file(): break
            require(continuation.poll() is None, 'Continuation admission failed; no finalizer launched')
            sleep(1)
        else: raise RuntimeError('Continuation start not observed; existing child retained for diagnosis')
        finalizer = launch('finalizer')
        code = continuation.wait()
        emit(record_dir/'continuation_exit.json', {'created_utc':utc(), 'exit_code':code})
        require(code == 0, 'Continuation stopped; scientific completion is not claimed')
        code = finalizer.wait()
        emit(record_dir/'finalizer_exit.json', {'created_utc':utc(), 'exit_code':code})
        require(code == 0 and read(HERE/'attempt001/finish.json').get('status') == 'COMPLETED',
                'Finalizer did not actually complete')
        return 'AUTHORIZED_CONTINUATION_AND_DELIVERY_COMPLETED'
    finally:
        for stream in handles: stream.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--implementation-pins', required=True, type=Path)
    parser.add_argument('--record-dir', required=True, type=Path)
    parser.add_argument('--transition-dir', required=True, type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'Requires -I -S -B')
    require(HERE == REPO/'verification/paper3_canonical_inputs/replication_worker_transition_v1', 'Wrong repository helper')
    for path in (args.record_dir, args.transition_dir):
        require(path.parent.resolve() == HERE and not path.exists(), 'New exclusive direct child directory required')
    proof = read(HERE/PROOF_NAME)
    require(proof.get('all_pass') is True and proof.get('failures') == proof.get('errors') == proof.get('skipped') == 0,
        'Supervisor synthetic tests not successful')
    require(proof['implementation_sha256'] == {str(HERE/name):sha(HERE/name) for name in ('transition_supervisor.py','test_transition_supervisor.py')},
        'Supervisor source changed since tests')
    reviewed = read(args.implementation_pins)
    pins = {**reviewed['files_sha256'], **reviewed['evidence_sha256'], str(args.implementation_pins):sha(args.implementation_pins)}
    recheck(pins)
    controller = load_local('migration_controller')
    controller.verify_implementation_proofs(reviewed)
    args.record_dir.mkdir(exist_ok=False)
    emit(args.record_dir/'start.json', {'created_utc':utc(), 'pid':os.getpid(), 'command':sys.argv,
        'status':'WAITING_FOR_RESOURCE_ADMISSION', 'workers_before':1, 'workers_requested':2,
        'manifest_digest':MANIFEST, 'source_sha256':pins, 'performance_used_for_scheduling':False,
        'existing_scientific_run_continues_while_waiting':True})
    stage = 'resource-wait'
    try:
        def sample():
            complete = (RESULTS/'execution/full/A_FULL_0001/completion.json').is_file()
            failed = (RESULTS/'execution/full/A_FULL_0001/failure.json').is_file()
            value = {'sampled_utc':utc(), 'old_full_complete':complete, 'old_failure':failed,
                'old_worker_alive':False, 'free_commit_bytes':0, 'existing_private_bytes':0}
            if complete or failed: return value
            backend = controller.NativeBackend()
            try:
                handle = backend.open(36468); info = backend.info(handle, 36468)
                controller.verify_identity(info, controller.EXPECTED_PROCESSES[0], RESULTS/'execution/full/A_FULL_0001/W1_request.json')
                value.update(old_worker_alive=True, free_commit_bytes=backend.resources()['free_commit_bytes'], existing_private_bytes=info['private_bytes'])
                return value
            finally: backend.close()
        def observe(value):
            # This append-only log is never used as scientific success evidence.
            with (args.record_dir/'resource_observations.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(value,sort_keys=True)+'\n');stream.flush()
        outcome = resource_wait(sample, observe, lambda:recheck(pins))
        if outcome == 'RESOURCE_ADMISSION_READY':
            stage = 'controlled-transition-and-continuation'
            require(sha(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md') == ROOT_SHA, 'Root handoff changed')
            outcome = run_flow(commands(sys.executable,args.implementation_pins,args.transition_dir),
                args.record_dir,args.transition_dir,lambda:recheck(pins))
        emit(args.record_dir/'finish.json', {'finished_utc':utc(), 'status':outcome,
            'not_a_whole_manuscript_freeze':True})
    except BaseException as error:
        emit(args.record_dir/'stopped.json', {'finished_utc':utc(), 'status':'STOPPED_FOR_DIAGNOSIS',
            'stage':stage,'error_type':type(error).__name__,'message':str(error),
            'automatic_retry_or_protocol_change':False,'completion_claimed':False,
            'existing_children_and_outputs_preserved':True})
        raise

if __name__ == '__main__': main()
