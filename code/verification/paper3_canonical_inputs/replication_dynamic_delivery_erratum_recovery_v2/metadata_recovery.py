"""Source-bound metadata-only recovery for a legal post-TASK boundary STOP.

The frozen erratum source and all old failed records remain unchanged. Its entire
execute, scientific validation and publication precommit are reused. Only the
inspect_smoke command-count predicate accepts the already completed DW0001's
optional legal final STOP; every other predicate is byte-identical.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
OLD = BASE / 'replication_dynamic_delivery_erratum_v1'
V2 = BASE / 'replication_dynamic_delivery_recovery_v2'
SMOKE = REPO / 'results/p7_7_integrity_replication_batch20_env_v3/execution/dynamic/A_DYNAMIC_0001'
OLD_SOURCE = OLD / 'metadata_erratum.py'
OLD_SOURCE_SHA = '3461322dd57af084d46a98d6cdb66abca473d006902fb90e37694013d92bebce'
OLD_PLAN = OLD / 'ERRATUM_RECOVERY_PLAN_002.json'
OLD_PLAN_SHA = '04f22e5a01ea11199ed8847593d796142ecf5dfbcd1b06d2ca7e0fa9445a440c'
H1 = 'c7b539bef23e3f43e1d663bc9240ab80cd325d2f1f7dd501e0b22cd18e3b8a3d'
OWN = ('metadata_recovery.py', 'test_metadata_recovery.py', 'root_erratum_launch003.py')
PROOF = HERE / 'BOUNDARY_STOP_RECOVERY_TEST_RESULTS_005.json'
PLAN = HERE / 'ERRATUM_RECOVERY_PLAN_005.json'
RECORD = HERE / 'erratum_recovery004'
PREDICATE_OLD = 'len(stop_commands)==(0 if n else 1)'
PREDICATE_NEW = 'len(stop_commands) in ((0,1) if n else (1,))'
FAILURES = {
    str(V2/'supervisor002/stopped.json'): '3d71c8823b88c50d5e633e4572ba0d780b1ece779a13b8e796d36bdca758563d',
    str(V2/'supervisor002/ERRATUM_PROCESS_EXIT.json'): 'ff0b511468e4f1c606f7e273f941f7e3f1f6f82f2a44b74ab28915381b21138e',
    str(V2/'ROOT_SUPERVISOR_NATIVE_EXIT_002.json'): 'db00563f0cd9c8f332b088431b2e41cc6949a5b2c4480a3b7fcdb845f1487f33',
    str(OLD/'erratum_recovery002/stopped.json'): '1625d90fa972c31e8abcf77ee952446f9e5649ad42dc5af70047257677f8c89d',
    str(V2/'supervisor002/erratum_process.log'): '95a820574312dab257324d7e2ef3516ec95a8d8dda2a62b068b607af68c88986',
    str(OLD/'erratum_recovery002/start.json'): 'b7d26f5d8ec6b03a7d02ce57397fa9b4794160e22292f311003b5db353103d6f',
}
SMOKE_PINS = {
    'journal/000004.json': '5cc9bced5a307086b992608a22abd0fd978838a1a17ee5c0feb4e87cc896e00b',
    'journal/000005.json': '5c7da86fd04a3b331b362e96491b56159c4ca24b4d96446736be3fdd2d03e77d',
    'workers/DW0001/commands/000002.json': 'e982fc0b94769e2edcdd14ef8ffff02b154e52de857c84bb6fe7e95cbbf9d1f2',
    'workers/DW0002/commands/000001.json': '0b7d2b3db4b5d4353b0f72c8935d59748d298676a1bb83a49c834d68ddc493cc',
    'workers/DW0001/finished.json': '7c6648b219b939f7261d43798e73851fa5952ddb3e8c8c5037f9bc9ed44b208f',
    'workers/DW0002/finished.json': '34efcc10f600bb4ea86375e67a39c57267dab10738665635ff5300b8077387c3',
    'workers/DW0001/actual_exit.json': 'bac5eecd8adfa2431603d0337c6a88641e71e34339d64e5876be245812bef98e',
    'workers/DW0002/actual_exit.json': '818f15fbb95139ad565a102cebd2983fa2cae9a187f1fe6bd6eac001b2c2851b',
}

def verified_module(path, name, expected):
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError('frozen source differs: '+str(path))
    if name in sys.modules:
        raise RuntimeError('private module name already loaded')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(payload, str(path), 'exec'), module.__dict__)
    module.__verified_source_payload__ = payload
    return module

def make_api(name='paper3_boundary_stop_recovery_original'):
    e = verified_module(OLD_SOURCE, name, OLD_SOURCE_SHA)
    payload = e.__verified_source_payload__.decode('utf-8')
    tree = ast.parse(payload)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'inspect_smoke']
    e.require(len(nodes) == 1, 'original inspect_smoke function differs')
    node = nodes[0]
    original = '\n'.join(payload.splitlines()[node.lineno-1:node.end_lineno])
    e.require(original.count(PREDICATE_OLD) == 1 and PREDICATE_NEW not in original,
              'exact original boundary predicate absent/ambiguous')
    fixed = original.replace(PREDICATE_OLD, PREDICATE_NEW)
    namespace = dict(e.__dict__)
    exec(compile(fixed, str(HERE/'metadata_recovery.py')+':inspect_smoke_only', 'exec'), namespace)
    e.original_inspect_smoke = e.inspect_smoke
    e.inspect_smoke = namespace['inspect_smoke']
    e.boundary_transform = {'function': 'inspect_smoke', 'original_source_sha256': OLD_SOURCE_SHA,
        'old_predicate': PREDICATE_OLD, 'new_predicate': PREDICATE_NEW,
        'all_other_function_source_identical': True,
        'original_function_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'adapted_function_sha256': hashlib.sha256(fixed.encode()).hexdigest()}
    return e

def source_pins(e):
    return {str(HERE/n): e.sha(HERE/n) for n in OWN}

def check_failures(e):
    for path, digest in FAILURES.items():
        e.bound(path, digest)
    stopped = e.read(OLD/'erratum_recovery002/stopped.json')
    e.require(stopped.get('error') == 'ErratumError' and stopped.get('message') ==
              'smoke trajectory/idle worker coverage differs' and stopped.get('automatic_retry') is False,
              'old erratum failure cause differs')
    for path in (V2/'supervisor002/ERRATUM_PROCESS_EXIT.json', V2/'ROOT_SUPERVISOR_NATIVE_EXIT_002.json'):
        value = e.read(path)
        e.require(type(value.get('actual_exit_code')) is int and value['actual_exit_code'] == 1,
                  'old failure exit must stay actual one')
    e.require(not (V2/'supervisor002/finish.json').exists() and not (OLD/'erratum_recovery002/finish.json').exists(),
              'old failed attempt cannot be relabeled successful')

def check_real_smoke(e):
    for relative, digest in SMOKE_PINS.items():
        e.bound(SMOKE/relative, digest)
    for index, worker in ((4, 'DW0001'), (5, 'DW0002')):
        event = e.read(SMOKE/f'journal/{index:06d}.json')
        e.require(event.get('action') == 'RETIRED_AT_BOUNDARY' and event.get('body') ==
                  {'worker_id': worker, 'inflight_killed': False}, 'real boundary retirement differs')
    e.require([p.name for p in sorted((SMOKE/'workers/DW0001/commands').glob('*.json'))] ==
              ['000001.json', '000002.json'] and
              [p.name for p in sorted((SMOKE/'workers/DW0002/commands').glob('*.json'))] == ['000001.json'],
              'real task/STOP inventory differs')
    e.require(e.read(SMOKE/'journal/000003.json')['action'] == 'COMPLETED',
              'real TASK must be complete before DW1 retirement')
    return {'real_smoke_pins': SMOKE_PINS, 'two_retired_at_boundary': True,
            'busy_process_killed': False, 'DW0001_STOP_issued_after_completed_task': True,
            'DW0001_STOP_consumption_claimed': False}

def verify_recovery_proof(e, path, digest):
    path = e.bound(path, digest)
    e.require(path == PROOF, 'recovery proof path differs')
    proof = e.read(path)
    e.require(proof.get('schema') == 'paper3-boundary-stop-recovery-test-proof-v1' and
              proof.get('all_pass') is True and type(proof.get('tests_run')) is int and proof['tests_run'] >= 12 and
              all(type(proof.get(k)) is int and proof[k] == 0 for k in ('errors', 'failures', 'skipped')),
              'recovery tests failed/incomplete')
    e.require(proof.get('source_sha256') == source_pins(e) and proof.get('boundary_transform') == e.boundary_transform and
              proof.get('models_statistics_real_publication_or_process_control') is False and
              proof.get('real_smoke_metadata_readonly_pass') is True,
              'recovery test scope/source differs')
    return proof

def verify_plan(e, path, expected_sha):
    path = e.bound(path, expected_sha)
    e.require(path == PLAN, 'recovery plan path differs')
    plan = e.read(path)
    original, v, full = e.original_verify_plan(OLD_PLAN, OLD_PLAN_SHA)
    recovery = plan.get('metadata_recovery')
    e.require(isinstance(recovery, dict), 'recovery certification absent')
    e.require(recovery.get('schema') == 'paper3-boundary-stop-metadata-recovery-v2' and
              recovery.get('original_plan_path') == str(OLD_PLAN) and recovery.get('original_plan_sha256') == OLD_PLAN_SHA and
              recovery.get('source_sha256') == source_pins(e) and recovery.get('boundary_transform') == e.boundary_transform and
              recovery.get('old_failure_files_sha256') == FAILURES and recovery.get('real_smoke_files_sha256') == SMOKE_PINS and
              recovery.get('old_supervisor_failure_preserved') is True and recovery.get('models_or_statistics_restarted') is False and
              recovery.get('automatic_retry') is False and recovery.get('DW0001_STOP_consumption_claimed') is False,
              'metadata recovery scope/source/evidence differs')
    verify_recovery_proof(e, recovery['test_proof_path'], recovery['test_proof_sha256'])
    expected = {**original, 'record_root': str(RECORD), 'metadata_recovery': recovery}
    e.require(plan == expected, 'non-recovery original plan fields changed')
    e.require(e.safe(RECORD).parent == HERE and e.safe(HERE).parent == BASE,
              'recovery record not independent')
    check_failures(e)
    check_real_smoke(e)
    return plan, v, full

def configure(e):
    e.original_verify_plan = e.verify_plan
    e.verify_plan = lambda path, digest: verify_plan(e, path, digest)
    old_emit = e.emit
    emitted = []
    def emit(path, value):
        path = Path(path)
        if path.name == 'ERRATUM.json':
            e.require(not emitted, 'only one recovery publication permitted')
            p = e.read(PLAN)
            recovery = p['metadata_recovery']
            e.verify_plan(PLAN, e.sha(PLAN))
            f = sys.modules['paper3_erratum_original_publication']
            for source, digest in recovery['source_sha256'].items():
                f.copy_verified(source, path.parent/'metadata_recovery_source'/Path(source).name, digest)
            f.copy_verified(PROOF, path.parent/'metadata_recovery_source'/PROOF.name, recovery['test_proof_sha256'])
            f.copy_verified(OLD_PLAN, path.parent/'metadata_recovery_source'/'ORIGINAL_FAILED_PLAN_002.json', OLD_PLAN_SHA)
            for index, (source, digest) in enumerate(sorted(FAILURES.items()), 1):
                f.copy_verified(source, path.parent/'preserved_failure_evidence'/f'{index:02d}_{Path(source).name}', digest)
            value = {**value, 'metadata_recovery': recovery,
                     'old_erratum_and_supervisor_actual_exit_code': 1,
                     'old_failed_attempt_success_fabricated': False}
            emitted.append(str(path))
        return old_emit(path, value)
    e.emit = emit
    return e

def create_plan(e):
    original, _, _ = e.original_verify_plan(OLD_PLAN, OLD_PLAN_SHA)
    check_failures(e)
    check_real_smoke(e)
    proof_sha = e.sha(PROOF)
    verify_recovery_proof(e, PROOF, proof_sha)
    e.bound(REPO/'PAPER3_FINAL_REPLICATION_HANDOFF.md', H1)
    for path in (RECORD, REPO/original['target_relative'], REPO/original['zip_relative']):
        e.require(not path.exists(), 'exclusive recovery output already exists')
    recovery = {'schema': 'paper3-boundary-stop-metadata-recovery-v2',
        'original_plan_path': str(OLD_PLAN), 'original_plan_sha256': OLD_PLAN_SHA,
        'source_sha256': source_pins(e), 'test_proof_path': str(PROOF), 'test_proof_sha256': proof_sha,
        'boundary_transform': e.boundary_transform, 'old_failure_files_sha256': FAILURES,
        'real_smoke_files_sha256': SMOKE_PINS, 'old_supervisor_failure_preserved': True,
        'models_or_statistics_restarted': False, 'automatic_retry': False,
        'DW0001_STOP_consumption_claimed': False, 'created_utc': e.utc()}
    plan = {**original, 'record_root': str(RECORD), 'metadata_recovery': recovery}
    ref = e.emit(PLAN, plan)
    e.verify_plan(ref['path'], ref['sha256'])
    return ref

def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('requires -I -S -B')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('create-plan', 'verify-plan', 'execute'))
    ap.add_argument('--plan', default=str(PLAN))
    ap.add_argument('--plan-sha256')
    args = ap.parse_args()
    e = configure(make_api())
    if args.action == 'create-plan':
        result = create_plan(e)
    else:
        e.require(bool(args.plan_sha256), 'explicit plan SHA required')
        if args.action == 'verify-plan':
            result = e.verify_plan(args.plan, args.plan_sha256)[0]
        else:
            print(json.dumps({'phase':'FROZEN_METADATA_VALIDATION_AND_PUBLICATION', 'utc': e.utc(),
                              'models_statistics_restarted': False}), flush=True)
            result = e.execute(args.plan, args.plan_sha256)
    print(json.dumps(result, sort_keys=True), flush=True)

if __name__ == '__main__':
    main()
