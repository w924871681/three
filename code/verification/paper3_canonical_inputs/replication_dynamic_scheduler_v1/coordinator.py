"""Real queue orchestration: admission, exclusive claims, drain, and retirement.

Production execution is fail-closed behind a separately certified takeover gate.
The CLI never attaches to, terminates, or steals from the running static attempt.
Synthetic tests exercise this SAME coordinator with persistent subprocesses.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
import os
import re
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from dynamic_policy import PolicyConfig, PolicyState, decide
from queue_store import QueueStore, IntegrityError, canonical, exclusive_json, label, read_json, safe, sha, task_stem, utc
from integrity import validate_completion, paired_groups, require


@dataclass
class Worker:
    worker_id: str
    phase: str = 'STARTING'
    claim: dict | None = None
    stop_sent: bool = False


class DynamicCoordinator:
    """Backend injection changes transport/testing, never task/scientific policy."""
    def __init__(self, ledger, backend, config=None):
        self.ledger, self.backend = ledger, backend
        self.config = config or PolicyConfig()
        self.state = PolicyState()
        self.workers = {}
        self.generation = 0
        self.samples = 0
        self.history = []
        self.proofs = []

    def _retire(self, worker):
        require(worker.phase == 'IDLE' and worker.claim is None, 'retire requires a validated trajectory boundary')
        self.ledger.boundary_retire(worker.worker_id)
        self.backend.stop(worker.worker_id)
        worker.stop_sent = True
        worker.phase = 'DRAINING'

    def tick(self, sample, *, now_ms):
        """One real observation step; never sends a stop command to an active claim."""
        require(not self.ledger.stopped, 'coordinator is stopped for independent diagnosis')
        try:
            for worker_id, worker in list(self.workers.items()):
                for event in self.backend.poll(worker_id):
                    kind = event['type']
                    if kind == 'READY':
                        require(worker.phase == 'STARTING', 'duplicate/late READY')
                        worker.phase = 'IDLE'
                    elif kind == 'DONE':
                        require(worker.claim is not None and worker.phase in ('BUSY','DRAINING'), 'DONE without owned claim')
                        require(event['claim_id'] == worker.claim['claim_id'], 'DONE claim identity differs')
                        proof = self.backend.validate(worker_id, worker.claim, event)
                        self.ledger.finish(worker_id, worker.claim['claim_id'], proof)
                        self.proofs.append(proof)
                        worker.claim = None
                        worker.phase = 'IDLE'
                    elif kind == 'FAILURE':
                        raise IntegrityError('worker failure: ' + str(event.get('reason')))
                    elif kind == 'EXIT':
                        expected_smoke=(event.get('smoke_scope_complete') is True and self.ledger.pending==0
                                        and self.ledger.complete==1)
                        require(event.get('exit_code') == 0 and (worker.stop_sent or expected_smoke) and worker.claim is None
                                and event.get('finished_validated') is True, 'unexpected/unverified worker exit')
                        del self.workers[worker_id]
                    else:
                        raise IntegrityError('unknown backend event')
            observations = [self.backend.observe(w.worker_id, w.phase) for w in self.workers.values()]
            decision = decide(self.config,self.state,sample,observations,
                              now_monotonic_ms=now_ms,unclaimed_tasks=self.ledger.pending)
            self.state = decision.next_state
            self.samples += 1
            evidence = {'sample':asdict(sample),'decision':asdict(decision),'utc':utc(),
                        'claims_complete':self.ledger.complete,'unclaimed_tasks':self.ledger.pending}
            exclusive_json(self.ledger.root,f'resource_decisions/{self.samples:06d}.json',evidence)
            self.history.append({'action':decision.action,'worker_count':len(self.workers)})
            if decision.admit_count:
                require(decision.admit_count == 1 and len(self.workers) < self.config.max_workers,
                        'one-at-a-time authorized admission required')
                self.generation += 1
                identity = f'DW{self.generation:04d}'
                self.backend.start(identity)
                self.workers[identity] = Worker(identity)
            if decision.retire_worker_id:
                self._retire(self.workers[decision.retire_worker_id])
            if decision.drain_worker_id:
                worker = self.workers[decision.drain_worker_id]
                require(worker.claim is not None or worker.phase in ('STARTING','DRAINING'), 'invalid drain target')
                if worker.claim is not None:
                    worker.phase = 'DRAINING'
            for worker in list(self.workers.values()):
                if worker.phase != 'IDLE' or worker.stop_sent:
                    continue
                # A pending drain remains binding even if memory recovers.
                if self.state.draining_worker_id == worker.worker_id:
                    self._retire(worker)
                elif self.ledger.pending == 0:
                    self._retire(worker)
                elif decision.dispatch_allowed and worker.worker_id not in (decision.drain_worker_id,decision.retire_worker_id):
                    claim = self.ledger.claim(worker.worker_id)
                    if claim is not None:
                        worker.claim = claim
                        worker.phase = 'BUSY'
                        self.backend.assign(worker.worker_id,claim)
            return {'all_finished':self.ledger.pending == 0 and not self.ledger.active and not self.workers,
                    'validated_complete':self.ledger.complete,'active_workers':len(self.workers),
                    'resource_action':decision.action,'scientific_integrity_pass':False}
        except BaseException as error:
            self.ledger.stop(f'{type(error).__name__}: {error}')
            # No process termination. In-flight computations may finish and keep
            # their original receipts; no new claims are dispatched after STOP.
            raise


def validate_activation(contract, *, active_process):
    """No synthetic test receipt is a substitute for true production admission."""
    require(contract.get('schema') == 'paper3-dynamic-run-contract-v1', 'run contract schema differs')
    require(contract.get('execution_mode','FULL') in ('FULL','BRIDGE_SMOKE'), 'unknown execution mode')
    gate_path = Path(contract['activation_gate_path'])
    require(sha(gate_path) == contract['activation_gate_sha256'], 'activation gate changed')
    gate = read_json(gate_path)
    require(gate.get('schema') == 'paper3-dynamic-takeover-gate-v1' and gate.get('status') == 'PASS', 'takeover gate incomplete')
    require(gate.get('old_owners_quiescent') is True and gate.get('delivery_route_certified') is True,
            'current producer ownership or final delivery route unresolved')
    require(isinstance(gate.get('old_process_ids'),list) and len(gate['old_process_ids']) >= 8
            and len(set(gate['old_process_ids'])) == len(gate['old_process_ids']), 'complete old owner inventory required')
    require(not any(active_process(pid) for pid in gate['old_process_ids']), 'an old static producer/continuation/finalizer still owns this experiment')
    for key in ('manifest_digest','input_bundle_digest','sidecar_digest'):
        require(gate.get(key) == contract[key], 'activation binding differs: ' + key)
    require(gate.get('source_extension_scope') == 'ORIGINAL_IMPORT_BINDINGS_PLUS_EXACT_DYNAMIC_SIDECAR_SHA256',
            'source extension was not independently certified')
    require(canonical(contract['sidecar_sources']) == contract['sidecar_digest'], 'sidecar digest differs')
    require(all(sha(path) == digest for path,digest in contract['sidecar_sources'].items()), 'sidecar source bytes changed')
    proof_path = Path(contract['sourceproof_path'])
    require(sha(proof_path) == contract['sourceproof_sha256'], 'synthetic proof changed')
    proof = read_json(proof_path)
    require(proof.get('schema') == 'paper3-dynamic-synthetic-test-proof-v1' and proof.get('all_pass') is True
            and proof.get('actual_model_execution') is False
            and proof.get('model_runtime_verification') == 'NOT_EXECUTED'
            and type(proof.get('tests_run')) is int and proof['tests_run'] > 0
            and all(type(proof.get(key)) is int and proof[key] == 0 for key in ('failures','errors','skipped'))
            and proof.get('implementation_sha256') == contract['sidecar_sources'], 'source-pinned independent synthetic proof required')
    if contract.get('execution_mode','FULL') == 'FULL':
        require(gate.get('real_model_bridge_smoke_passed') is True, 'real bridge smoke validation remains unexecuted')
    else:
        require(len(contract['eligible_tasks']) == 1 and gate.get('scope') == 'ONE_PREDECLARED_PENDING_TASK'
                and gate.get('smoke_task_digest') == canonical(contract['eligible_tasks'][0]), 'smoke must be one predeclared pending task')
    return gate


class FrozenProcessBackend:
    """Persistent OS workers; no signals, source changes, or model reimplementation."""
    def __init__(self, contract, run_root, reference):
        self.contract, self.root, self.reference = contract,Path(run_root),reference
        self.records = {}

    def start(self, worker_id):
        label(worker_id)
        require(worker_id not in self.records,'worker identity must never be reused')
        directory = safe(self.root,f'workers/{worker_id}')
        directory.mkdir(parents=True,exist_ok=False)
        for name in ('temp','torch','cuda'):
            (directory/name).mkdir(exist_ok=False)
        worker_contract={**self.contract,'worker_id':worker_id,'worker_root':str(directory)}
        publication=exclusive_json(self.root,f'workers/{worker_id}/contract.json',worker_contract)
        bootstrap={'schema':'paper3-replication-worker-request-v1','manifest_digest':self.contract['manifest_digest'],
                   'mode':'trajectory','worker_id':worker_id,'attempt_id':self.contract['attempt_id'],
                   'worker_count':3,'tasks':self.contract['eligible_tasks'],'retries':self.contract.get('retries',{}),
                   'initial_state_manifest':'initial_state_manifest.json','performance_based_continuation':False,
                   'dynamic_eligible_population_only':True,'sidecar_digest':self.contract['sidecar_digest']}
        exclusive_json(self.root,f'workers/{worker_id}/bootstrap_request.json',bootstrap)
        results=self.reference.root
        command=[self.contract['python_executable'],'-I','-S','-B','-X',
                 f'pycache_prefix={results / ("_dynamic_never_pycache_"+worker_id)}',str(HERE/'frozen_bridge.py'),
                 '--contract',publication['path'],'--worker-id',worker_id,'--worker-root',str(directory)]
        env=dict(os.environ)
        env.update(TEMP=str(directory/'temp'),TMP=str(directory/'temp'),TORCH_HOME=str(directory/'torch'),CUDA_CACHE_PATH=str(directory/'cuda'))
        log=(directory/'process.log').open('xb')
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                 env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.records[worker_id]={'root':directory,'process':process,'log':log,'seq':0,'done':0,
                                 'ready':False,'exit':False,'actual_pid':process.pid,'peaks':(0,0),
                                 'contract_sha256':publication['sha256']}
        exclusive_json(self.root,f'workers/{worker_id}/launched.json',{'pid':process.pid,'command':command,'utc':utc(),
                       'contract_sha256':publication['sha256'],'scientific_worker_ready':False})

    def _command(self, worker_id, value):
        item=self.records[worker_id]; item['seq']+=1
        return exclusive_json(item['root'],f"commands/{item['seq']:06d}.json",
                              {**value,'contract_sha256':item['contract_sha256']})

    def assign(self, worker_id, claim):
        item=self.records[worker_id]
        require(item['ready'] and item['seq']==item['done'],'worker has an unfinished command')
        publication=self._command(worker_id,{'action':'TASK',**claim})
        item['command_sha256']=publication['sha256']

    def stop(self, worker_id):
        item=self.records[worker_id]
        require(item['seq']==item['done'],'cannot send STOP inside an active trajectory')
        self._command(worker_id,{'action':'STOP','reason':'validated trajectory boundary; no inflight termination'})

    def poll(self, worker_id):
        item=self.records[worker_id]; directory=item['root']; events=[]
        if (directory/'failure.json').exists():
            return [{'type':'FAILURE','reason':read_json(directory/'failure.json')}]
        ready=directory/'ready.json'
        if ready.exists() and not item['ready']:
            value=read_json(ready)
            require(value.get('contract_sha256')==item['contract_sha256'],'worker READY contract differs')
            item['actual_pid']=value['pid']; item['ready']=True
            events.append({'type':'READY'})
        done=directory/f"events/{item['done']+1:06d}.done.json"
        if done.exists():
            value=read_json(done)
            require(value['contract_sha256']==item['contract_sha256'],'worker DONE contract differs')
            item['done']+=1
            events.append({'type':'DONE',**value})
        code=item['process'].poll()
        if code is not None and not item['exit']:
            item['exit']=True
            finished=directory/'finished.json'
            verified=False
            if finished.exists():
                value=read_json(finished)
                verified=(value.get('contract_sha256')==item['contract_sha256']
                          and value.get('original_trajectories_returned_after_full_checks') is True)
            exclusive_json(directory,'actual_exit.json',{
                'schema':'paper3-dynamic-owned-worker-exit-v1',
                'pid':item['process'].pid,'actual_model_pid':item['actual_pid'],
                'actual_exit_code':code,'observed_utc':utc(),
                'contract_sha256':item['contract_sha256'],
                'finished_validated':verified,'producer':'OWNING_FROZEN_PROCESS_BACKEND',
                'automatic_retry':False})
            events.append({'type':'EXIT','exit_code':code,'finished_validated':verified,
                           'smoke_scope_complete':self.contract.get('execution_mode')=='BRIDGE_SMOKE' and item['done']==1})
            item['log'].close()
        return events

    def observe(self, worker_id, phase):
        from native_resources import worker_observation
        item=self.records[worker_id]
        observation=worker_observation(worker_id,phase,item['actual_pid'],item['peaks'])
        item['peaks']=(observation.peak_private_bytes,observation.peak_working_set_bytes)
        return observation

    def validate(self, worker_id, claim, event):
        item=self.records[worker_id]
        require(event['task']==claim['task'] and event['task_digest']==claim['task_digest']
                and event['command_sha256']==item['command_sha256'],'worker DONE identity/command differs')
        proof=validate_completion(self.reference.root,claim['task'],self.reference.expected(claim['task']))
        require(proof['receipt_sha256']==event['receipt_sha256'] and proof['output_hash']==event['output_sha256'],
                'worker completion does not identify actual immutable artifacts')
        return proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    args=parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    contract=read_json(args.contract)
    from native_resources import process_active,resource_sample
    validate_activation(contract,active_process=process_active)  # BEFORE any output/process creation.
    from frozen_reference import FrozenReference
    reference=FrozenReference(contract['manifest_path'])
    require(reference.manifest['manifest_digest']==contract['manifest_digest']
            and reference.manifest['input_bundle_digest']==contract['input_bundle_digest']
            and reference.initial_sha==contract['initial_manifest_sha256'],'frozen scientific reference differs')
    require(Path(contract['original_executor_root']).resolve()==Path(reference.manifest['paths']['executor_root']).resolve(),
            'original executor identity differs')
    require(contract['python_executable']==reference.manifest['environment']['python_executable'],'Python environment differs')
    mode=contract.get('execution_mode','FULL')
    population=contract['eligible_tasks']
    require(len(population)==(1200 if mode=='FULL' else 1),'full population cannot be filtered')
    method_configs=(('B0','B0_Frozen_ratio10'),('B1','B1_AlwaysMaintainP50_ratio10'),('B2','B2_RAVM_ratio10'),
                    ('B8','B8_AlwaysOpen_ratio10'),('P7.7','P7_7_RECOVERABILITY_GUIDED_ratio10_grid33'))
    frozen_matrix=[{'center_id':c,'seed':s,'scenario':q,'method':m,'config_id':i}
                   for c in range(33000,33020) for s in (7311,7312,7313)
                   for q in ('C0','C1','C3','C4') for m,i in method_configs]
    require(mode!='FULL' or population==frozen_matrix,'population/order must equal frozen complete matrix')
    require(re.fullmatch(r'A_DYNAMIC_[0-9]{4}',contract['attempt_id']) is not None
            and contract['run_relative']==f"execution/dynamic/{contract['attempt_id']}", 'dynamic output ownership path differs')
    # The production contract must inventory every original successful V3 result
    # and any incomplete RNG claim via a separately certified takeover, not infer
    # that an absent process or CSV means a task may be redrawn.
    gate=read_json(contract['activation_gate_path'])
    require(gate.get('saved_record_inventory_sha256')==canonical(contract['already_complete']),
            'saved-record reuse inventory is not independently bound')
    complete=[]; initial_proofs=[]
    for task in population:
        name=task_stem(task)
        if name in contract['already_complete']:
            proof=validate_completion(reference.root,task,reference.expected(task))
            require(proof['receipt_sha256']==contract['already_complete'][name],'retained V3 record bytes differ')
            complete.append(name); initial_proofs.append(proof)
    require(set(complete)==set(contract['already_complete']),'invalid retained inventory')
    expected_names={task_stem(task) for task in population}
    raw=reference.root/'raw'
    observed_receipts={path.name.removesuffix('.integrity.json') for path in raw.glob('*.integrity.json')}
    observed_csv={path.stem for path in raw.glob('*.csv')}
    if mode=='FULL':
        require(observed_receipts==observed_csv==set(complete),'unreceipted/uninventoried result; independent recovery required')
    retries=contract.get('retries',{})
    require(set(retries)<=expected_names-set(complete),'retry map includes complete/unknown task')
    from integrity import retry_identity
    for task in population:
        name=task_stem(task)
        if name in complete:continue
        attempted=reference.root/'attempts'/name
        if attempted.exists() and any(attempted.rglob('rng_before.json')):
            require(name in retries,'incomplete old claim has RNG but no certified same-task recovery')
        if name in retries:retry_identity(reference.root,task,retries[name],reference.expected(task))
    run_root=safe(reference.root,contract['run_relative'])
    ledger=QueueStore(run_root,population,{'manifest_digest':contract['manifest_digest'],
                       'input_bundle_digest':contract['input_bundle_digest'],'sidecar_digest':contract['sidecar_digest'],
                       'contract_sha256':sha(args.contract)},already_complete=complete)
    backend=FrozenProcessBackend(contract,run_root,reference)
    coordinator=DynamicCoordinator(ledger,backend,PolicyConfig())
    coordinator.proofs.extend(initial_proofs)
    while True:
        sample=resource_sample()
        status=coordinator.tick(sample,now_ms=sample.sampled_monotonic_ms)
        if status['all_finished']:
            paired=paired_groups(coordinator.proofs)
            require(mode=='BRIDGE_SMOKE' or (ledger.complete==1200 and paired['complete_paired_groups']==240),
                    'full input/initial/deployment parity incomplete')
            exclusive_json(run_root,'DYNAMIC_EXECUTION_COMPLETED.json',{'status':'DYNAMIC_TASKS_COMPLETED',
                'completed':ledger.complete,'pairing':paired,'scientific_integrity_pass':False,
                'statistics_executed':False,'original_pipeline_final_gate_still_required':True})
            break
        time.sleep(10)


if __name__=='__main__':
    main()
