"""One metadata-only successor after the original finalizer's known delivery STOP.

Only a separately certified adapter may be spawned. The unchanged reviewed
finalizer verifies all scientific/statistical gates, verifies delivery, and
archives/publishes/zips. There is no scientific command, retry, process control,
source replacement, or alternate publication implementation in this module.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

REPO = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
PREFIX = 'verification/paper3_canonical_inputs/'
SELF_REL = PREFIX + 'replication_delivery_successor_v1'
RECOVERY_REL = PREFIX + 'replication_abrupt_recovery_v1'
COMPAT_REL = PREFIX + 'recovery_compat_v1'
ADAPTER_REL = PREFIX + 'replication_delivery_observer_adapter_v1'
ORIGINAL_DELIVERY_REL = PREFIX + 'replication_delivery_env_v3'
GATE_DIR_REL = RECOVERY_REL + '/COLD_RECOVERY_METADATA_COMPAT_001'
GATE_REL = GATE_DIR_REL + '/cold_recovery_gate.json'
OLD_RECORD_REL = RECOVERY_REL + '/attempt001'
DURABLE_REL = COMPAT_REL + '/durable_launch_003'
PACKAGE_REL = 'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_COMPLETED_001'
FINAL_PACKAGE_REL = 'handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_BATCH20_ENV_V3_FINAL_PACKAGE_001'
PYTHON = Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe')
FINALIZER_SHA = 'ec398d926dad5af5b1e28835479c503fd333d6119579342dc215fee0b6638652'
DELIVERY_SHA = '159bab5bd92d7990cb553989fb83b591dbcb913782f97a833e026ad46b38e453'
GATE_SHA = '296ab0bf92b9b19237d52c99013c7aab21afa68326731c5b288c0dd20ba837ad'
LAUNCH_SPEC_SHA = '1b878bc53a7c6cd29d2792538afdcd0a7a87f5558609653330ec80b786aa295a'
CONTINUATION_SHA = 'b12760cb14ea47fe54a149daf50fbd0bac86582824fb9a4dda65f877fb5fdaef'
STRICT_ADAPTER_SHA = '6059b194bb48fe44b9c7027c9d6e8149d6cc6414734f2816c27601dc631028fd'
STRICT_PROOF_NAME = 'STRICT_LEGACY_PROOF_ADAPTER_TEST_RESULTS_001.json'
STRICT_PROOF_SHA = 'ddd0118f5cc23b33fec6d4e87cd21d913225d9c9d42aa48bbac5bd86925880b9'
LEGACY_PROOF_SHA = '4ddc671fc1485633b9226dd293fc275d2be46949c7d6d52afed5039f6a684c23'
ORIGINAL_VERIFY_FUNCTION_SHA = '124310fac969a906957bb61f9c92c6d1082be3c3ec57988a09b9c14f34cca7d8'
COPIED_VERIFY_FUNCTION_SHA = '9687f71a9745b162751a900c9e787ad4936c90859a70db3e2cb79108476e73c9'
COMPAT_NAMES = ('compat_entry.py', 'compat_continuation.py', 'compat_finalizer.py',
                'compat_supervisor_003.py', 'tests_compat_wrappers.py', 'WRAPPER_TEST_RESULTS_001.json',
                'strict_legacy_proof_adapter.py', 'tests_strict_legacy_proof_adapter.py',
                'run_strict_legacy_proof_adapter_tests.py', STRICT_PROOF_NAME, 'DURABLE_LAUNCH_SPEC_003.json',
                'WMI_DURABLE_SUPERVISOR_CREATION_003.json')
ENTRY_NAMES = ('ACTUAL_CONTINUATION_ADAPTER_ENTRY_001.json', 'ACTUAL_FINALIZER_ADAPTER_ENTRY_001.json')
ROOT_SHA = 'f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8'
MANIFEST = '7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea'
F1 = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
OWN_NAMES = ('successor.py', 'test_successor.py', 'run_tests.py', 'create_plan.py')
PROOF_NAME = 'SYNTHETIC_TEST_RESULTS_ATTEMPT002.json'
PLAN_NAME = 'SUCCESSOR_LAUNCH_PLAN_002.json'
EXPECTED_STOP_MESSAGE = 'saved-result delivery failed; outputs preserved'
EXPECTED_DELIVERY_ERROR = 'DeliveryIntegrityError: phase real timestamps absent'


class SuccessorError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise SuccessorError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    no_reparse(path)
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def load(path):
    no_reparse(path)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(SuccessorError('nonfinite JSON')))


def no_reparse(path):
    path = Path(path)
    for item in (path, *path.parents):
        require(not item.is_symlink(), 'symlink rejected: ' + str(item))
        if item.exists():
            require(not getattr(item.lstat(), 'st_file_attributes', 0) &
                    getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
                    'reparse point rejected: ' + str(item))


def safe(repo, relative):
    repo, relative = Path(repo), Path(relative)
    require(repo.is_absolute() and not relative.is_absolute() and relative.parts and
            '..' not in relative.parts, 'unsafe path')
    result = repo / relative
    no_reparse(result)
    require(result.resolve().is_relative_to(repo.resolve()), 'path escaped repository')
    return result


def bound(path, digest):
    no_reparse(path)
    require(Path(path).is_file() and sha(path) == digest, 'bound SHA differs: ' + str(path))
    return Path(path)


def emit(path, value):
    path = Path(path)
    no_reparse(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def verify_own_proof(root):
    root = Path(root)
    proof = load(root / PROOF_NAME)
    require(proof.get('schema') == 'paper3-delivery-successor-synthetic-tests-v1' and
            proof.get('all_pass') is True and proof.get('exit_code') == 0 and
            proof.get('tests_run', 0) >= 25 and
            all(proof.get(key) == 0 for key in ('failures', 'errors', 'skipped')),
            'successor synthetic proof is incomplete')
    require(all(proof.get(key) is False for key in
                ('real_outcomes_read', 'real_delivery_published',
                 'models_generators_or_statistics_executed', 'real_processes_stopped_or_started')),
            'successor synthetic scope differs')
    require(proof.get('implementation_sha256') == {name: sha(root / name) for name in OWN_NAMES},
            'successor implementation changed since tests')
    return sha(root / PROOF_NAME)


def load_original(repo):
    source = bound(safe(repo, RECOVERY_REL + '/finalizer.py'), FINALIZER_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_original_delivery_successor_finalizer', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bound(source, FINALIZER_SHA)
    bound(source, FINALIZER_SHA)
    require(module.MANIFEST == MANIFEST and module.F1 == F1 and
            module.FIXED_ROOT_SHA == ROOT_SHA and module.PACKAGE_REL == PACKAGE_REL,
            'reviewed finalizer constants differ')
    adapter_source = bound(safe(repo, COMPAT_REL + '/strict_legacy_proof_adapter.py'), STRICT_ADAPTER_SHA)
    proof_path = bound(safe(repo, COMPAT_REL + '/' + STRICT_PROOF_NAME), STRICT_PROOF_SHA)
    adapter_spec = importlib.util.spec_from_file_location('reviewed_successor_strict_legacy_proof_adapter', adapter_source)
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)
    bound(adapter_source, STRICT_ADAPTER_SHA)
    module._successor_legacy_reader_installation = adapter.install(module, Path(repo), safe(repo, GATE_REL), proof_path)
    return module


def adapter_command(repo, plan):
    return [str(PYTHON), '-I', '-S', '-B', str(safe(repo, ADAPTER_REL + '/observer_adapter.py')),
            '--repo', str(repo), '--expected-manifest-digest', MANIFEST,
            '--handoff-relative', PACKAGE_REL,
            '--synthetic-test-receipt', str(safe(repo, ADAPTER_REL + '/' + plan['adapter_proof_name'])),
            '--original-finalizer-stop', str(safe(repo, OLD_RECORD_REL + '/stopped.json'))]


def predecessor_commands(repo):
    common = [str(PYTHON), '-I', '-S', '-B']
    return {kind: common + [str(safe(repo, COMPAT_REL + '/compat_' + kind + '.py')),
                           '--repo', str(repo), '--cold-gate', str(safe(repo, GATE_REL))] +
                  (['--attempt', '1', '--poll-seconds', '30'] if kind == 'finalizer' else [])
            for kind in ('continuation', 'finalizer')}


def verify_plan(repo, plan_path):
    require(Path(plan_path) == safe(repo, SELF_REL + '/' + PLAN_NAME), 'wrong successor plan path')
    value = load(plan_path)
    require(value.get('schema') == 'paper3-delivery-successor-plan-v1' and
            value.get('repository') == str(repo) and value.get('python_executable') == str(PYTHON),
            'wrong successor plan identity')
    require(value.get('manifest_digest') == MANIFEST and value.get('F1_digest') == F1,
            'successor plan scientific identity differs')
    require(value.get('scientific_commands_authorized') is False and
            value.get('automatic_scientific_retry') is False and
            value.get('original_finalizer_must_naturally_stop') is True and
            value.get('root_publication_authorized_only_after_all_original_gates') is True,
            'successor plan authority differs')
    adapter_proof = value.get('adapter_proof_name', '')
    require(Path(adapter_proof).name == adapter_proof and adapter_proof.startswith('SYNTHETIC_TEST_RESULTS_ATTEMPT')
            and adapter_proof.endswith('.json'), 'unsafe adapter proof name')
    pins = value.get('files_sha256', {})
    required = {str(safe(repo, SELF_REL + '/' + name)) for name in (*OWN_NAMES, PROOF_NAME)}
    required |= {str(safe(repo, relative)) for relative in
                 (RECOVERY_REL + '/finalizer.py', RECOVERY_REL + '/continuation.py',
                  RECOVERY_REL + '/durable_supervisor.py', RECOVERY_REL + '/sequenced_supervisor_002.py',
                  RECOVERY_REL + '/SYNTHETIC_CONTINUATION_TEST_RESULTS_ATTEMPT001.json',
                  ORIGINAL_DELIVERY_REL + '/delivery.py',
                  ORIGINAL_DELIVERY_REL + '/SYNTHETIC_TEST_RESULTS_ATTEMPT003.json',
                  DURABLE_REL + '/start.json', DURABLE_REL + '/continuation_launched.json',
                  DURABLE_REL + '/finalizer_launched.json', GATE_REL,
                  ADAPTER_REL + '/observer_adapter.py', ADAPTER_REL + '/test_observer_adapter.py',
                  ADAPTER_REL + '/run_synthetic_tests.py', ADAPTER_REL + '/OBSERVER_METADATA_ADAPTER_REVIEW.md',
                  ADAPTER_REL + '/' + adapter_proof)}
    required.add(str(PYTHON))
    required |= {str(safe(repo, COMPAT_REL + '/' + name)) for name in COMPAT_NAMES}
    required |= {str(safe(repo, GATE_DIR_REL + '/' + name)) for name in ENTRY_NAMES}
    require(set(pins) == required, 'successor plan exact source/evidence closure differs')
    require(pins[str(safe(repo, RECOVERY_REL + '/finalizer.py'))] == FINALIZER_SHA and
            pins[str(safe(repo, ORIGINAL_DELIVERY_REL + '/delivery.py'))] == DELIVERY_SHA and
            pins[str(safe(repo, GATE_REL))] == GATE_SHA and
            pins[str(safe(repo, COMPAT_REL + '/strict_legacy_proof_adapter.py'))] == STRICT_ADAPTER_SHA and
            pins[str(safe(repo, COMPAT_REL + '/' + STRICT_PROOF_NAME))] == STRICT_PROOF_SHA and
            pins[str(safe(repo, COMPAT_REL + '/DURABLE_LAUNCH_SPEC_003.json'))] == LAUNCH_SPEC_SHA,
            'successor trust anchor differs')
    for name, digest in pins.items():
        path = Path(name)
        require(path.is_absolute() and (path.is_relative_to(repo) or path == PYTHON),
                'unapproved external plan pin')
        require(type(digest) is str and len(digest) == 64, 'invalid plan SHA')
        bound(path, digest)
    require(verify_own_proof(safe(repo, SELF_REL)) == pins[str(safe(repo, SELF_REL + '/' + PROOF_NAME))],
            'successor proof binding differs')
    require(value.get('adapter_command') == adapter_command(repo, value), 'adapter command differs from exact allowlist')
    durable_start = load(safe(repo, DURABLE_REL + '/start.json'))
    wmi = load(safe(repo, COMPAT_REL + '/WMI_DURABLE_SUPERVISOR_CREATION_003.json'))
    require(durable_start.get('commands') == predecessor_commands(repo) and
            durable_start.get('launch_spec_sha256') == LAUNCH_SPEC_SHA and
            durable_start.get('source_sha256') == pins[str(safe(repo, COMPAT_REL + '/compat_supervisor_003.py'))] and
            durable_start.get('actual_entrypoints_are_compatibility_wrappers') is True and
            durable_start.get('automatic_restart') is False and
            durable_start.get('model_workers_started_claimed') is False and
            wmi.get('return_value') == 0 and wmi.get('actual_created_pid') == durable_start.get('pid') and
            wmi.get('launch_spec_sha256') == LAUNCH_SPEC_SHA and wmi.get('completion_claimed') is False and
            wmi.get('model_worker_start_claimed') is False, 'actual durable003 launch authority differs')
    value['_verified_plan_sha256'] = sha(plan_path)
    return value


def pid_inactive(pid):
    """Query only. Any active numeric PID, including reuse, blocks admission."""
    require(os.name == 'nt' and type(pid) is int and pid > 0, 'Windows process identity required')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        require(ctypes.get_last_error() == 87, 'predecessor process absence not verifiable')
        return True
    try:
        code = wintypes.DWORD()
        require(kernel.GetExitCodeProcess(handle, ctypes.byref(code)), 'cannot query predecessor process')
        return code.value != 259
    finally:
        kernel.CloseHandle(handle)


def predecessor_ready(repo, inactive=pid_inactive):
    """Do not read scientific outcomes while waiting for retained actual exits."""
    durable, old = safe(repo, DURABLE_REL), safe(repo, OLD_RECORD_REL)
    require(not (durable / 'supervisor_error.json').exists(), 'original durable supervisor failed')
    require(not safe(repo, RECOVERY_REL + '/continuation_001/stopped.json').exists(), 'continuation stopped')
    require(not (old / 'finish.json').exists(), 'original finalizer already completed; successor refused')
    if not (old / 'stopped.json').exists():
        return False
    stopped = load(old / 'stopped.json')
    require(stopped.get('status') == 'STOPPED_FOR_DIAGNOSIS' and
            stopped.get('phase') == 'reviewed_saved_result_delivery' and
            stopped.get('exception_type') == 'FinalizerError' and
            stopped.get('message') == EXPECTED_STOP_MESSAGE and
            stopped.get('scientific_pass_claimed') is False and
            stopped.get('all_partial_outputs_preserved') is True,
            'original finalizer did not stop at the authorized delivery interface failure')
    required = [durable / name for name in ('continuation_exit.json', 'finalizer_exit.json', 'failure.json',
                                           'finalizer_launched.json')]
    required += [old / name for name in ('DELIVERY_PROCESS_FINISH.json', 'delivery_stderr.log',
                                       'ACTUAL_GATE_VERIFICATION.json', 'start.json', 'source_pins.json')]
    required += [safe(repo, GATE_DIR_REL + '/' + name) for name in ENTRY_NAMES]
    if not all(path.is_file() for path in required):
        return False
    continuation, finalizer, failure = (load(durable / name) for name in
                                       ('continuation_exit.json', 'finalizer_exit.json', 'failure.json'))
    require(type(continuation.get('actual_exit_code')) is int and continuation['actual_exit_code'] == 0 and
            type(finalizer.get('actual_exit_code')) is int and
            finalizer['actual_exit_code'] != 0 and
            all(value.get('automatic_retry') is False for value in (continuation, finalizer, failure)),
            'retained actual child exit codes do not authorize successor')
    require(failure.get('status') == 'CHILD_COMMAND_FAILURE' and
            failure.get('actual_child_exit_codes') == {'continuation': 0, 'finalizer': finalizer['actual_exit_code']} and
            failure.get('scientific_integrity_pass_claimed') is False and failure.get('outputs_preserved') is True,
            'durable terminal evidence differs')
    launch, start, durable_start, continuation_launch = (load(path) for path in
        (durable / 'finalizer_launched.json', old / 'start.json', durable / 'start.json', durable / 'continuation_launched.json'))
    require(launch.get('pid') == start.get('pid') == finalizer.get('pid') and
            continuation_launch.get('pid') == continuation.get('pid'), 'predecessor PID lineage differs')
    require(all(type(value.get('pid')) is int and value['pid'] > 0 for value in (continuation, finalizer)) and
            continuation['pid'] != finalizer['pid'], 'invalid predecessor PID identities')
    require(launch.get('command') == durable_start.get('commands', {}).get('finalizer') and
            continuation_launch.get('command') == durable_start.get('commands', {}).get('continuation'),
            'predecessor commands differ from pinned durable launch')
    require(start.get('previous_root_handoff_sha256') == ROOT_SHA and
            start.get('expected_manifest_digest') == MANIFEST and start.get('expected_F1_digest') == F1 and
            start.get('science_or_statistics_executed') is False, 'original finalizer start identity differs')
    process_finish = load(old / 'DELIVERY_PROCESS_FINISH.json')
    require(type(process_finish.get('exit_code')) is int and process_finish['exit_code'] != 0,
            'original delivery did not actually fail')
    lines = (old / 'delivery_stderr.log').read_text(encoding='utf-8').splitlines()
    require(lines and lines[-1].strip() == EXPECTED_DELIVERY_ERROR,
            'original delivery failure is not the known timestamp interface error')
    gate = load(old / 'ACTUAL_GATE_VERIFICATION.json')
    require(gate.get('status') == 'PASS' and type(gate.get('evidence_sha256')) is dict and gate['evidence_sha256'],
            'original actual gate verification not PASS')
    pins = load(old / 'source_pins.json')
    require(start.get('source_pins_digest') == canonical(pins) and
            pins.get(str(safe(repo, RECOVERY_REL + '/finalizer.py'))) == FINALIZER_SHA and
            pins.get(str(safe(repo, ORIGINAL_DELIVERY_REL + '/delivery.py'))) == DELIVERY_SHA,
            'original tested source pins differ')
    verify_compat_entries(repo, continuation, finalizer, continuation_launch, launch)
    return all(inactive(value['pid']) for value in (continuation, finalizer))


def verify_compat_entries(repo, continuation, finalizer, continuation_launch, finalizer_launch):
    for kind, exit_record, launched in (('continuation', continuation, continuation_launch),
                                       ('finalizer', finalizer, finalizer_launch)):
        entry = load(safe(repo, GATE_DIR_REL + '/ACTUAL_' + kind.upper() + '_ADAPTER_ENTRY_001.json'))
        wrapper = safe(repo, COMPAT_REL + '/compat_' + kind + '.py')
        original = safe(repo, RECOVERY_REL + '/' + kind + '.py')
        expected_original_sha = CONTINUATION_SHA if kind == 'continuation' else FINALIZER_SHA
        require(entry.get('schema') == 'paper3-actual-compatibility-entrypoint-v1' and
                entry.get('pid') == exit_record['pid'] and entry.get('entrypoint') == str(wrapper) and
                entry.get('entrypoint_sha256') == sha(wrapper) and
                entry.get('actual_argv') == launched['command'][4:] and
                entry.get('original_module') == str(original) and
                entry.get('original_module_sha256') == expected_original_sha and
                entry.get('cold_gate_sha256') == GATE_SHA,
                'actual compatibility entrypoint identity differs')
        require(entry.get('about_to_invoke_original_helper_main') is True and
                all(entry.get(name) is False for name in ('original_main_called_directly_by_OS',
                    'scientific_algorithm_or_input_changed', 'model_workers_started_claimed')) and
                entry.get('all_bound_SHA_checks_and_resource_gate_preserved') is True,
                'actual compatibility entrypoint scope differs')
        metadata = entry.get('metadata_reader_compatibility', {})
        require(metadata.get('schema') == 'paper3-strict-legacy-proof-adapter-installation-v1' and
                metadata.get('metadata_only') is True and metadata.get('original_finalizer_sha256') == FINALIZER_SHA and
                metadata.get('adapter_sha256') == STRICT_ADAPTER_SHA and
                metadata.get('compatibility_proof_sha256') == STRICT_PROOF_SHA and
                metadata.get('legacy_original_receipt_sha256') == LEGACY_PROOF_SHA and
                metadata.get('original_verify_function_sha256') == ORIGINAL_VERIFY_FUNCTION_SHA and
                metadata.get('copied_verify_function_sha256') == COPIED_VERIFY_FUNCTION_SHA and
                metadata.get('compatibility_proof_path') == str(safe(repo, COMPAT_REL + '/' + STRICT_PROOF_NAME)) and
                metadata.get('gate_path') == str(safe(repo, GATE_REL)) and
                metadata.get('original_module_file_unchanged') is True and
                metadata.get('full_pin_hash_checks_retained') is True,
                'actual entrypoint strict legacy adapter identity differs')


def wait_predecessor(repo, poll_seconds, pause=time.sleep, ready=predecessor_ready):
    require(type(poll_seconds) is int and 0 < poll_seconds <= 60, 'poll must be bounded to 60 seconds')
    while not ready(repo):
        pause(poll_seconds)


def predecessor_evidence(repo):
    paths = [safe(repo, OLD_RECORD_REL + '/' + name) for name in
             ('start.json', 'source_pins.json', 'stopped.json', 'ACTUAL_GATE_VERIFICATION.json',
              'DELIVERY_PROCESS_FINISH.json', 'delivery_stdout.log', 'delivery_stderr.log')]
    paths += [safe(repo, DURABLE_REL + '/' + name) for name in
              ('start.json', 'continuation_launched.json', 'finalizer_launched.json',
               'continuation_exit.json', 'finalizer_exit.json', 'failure.json')]
    paths += [safe(repo, GATE_DIR_REL + '/' + name) for name in ENTRY_NAMES]
    return {str(path): sha(path) for path in paths}


def launch_snapshots(repo, plan, plan_path):
    """Original package_final archives this payload inside new start.json."""
    result = {}
    for name in (*OWN_NAMES, PROOF_NAME, PLAN_NAME):
        path = safe(repo, SELF_REL + '/' + name)
        expected = (plan['_verified_plan_sha256'] if name == PLAN_NAME else plan['files_sha256'][str(path)])
        payload = bound(path, expected).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == expected, 'launch snapshot changed during read')
        result[name] = {'sha256': expected, 'utf8': payload.decode('utf-8')}
    for name in ENTRY_NAMES:
        path = safe(repo, GATE_DIR_REL + '/' + name)
        expected = plan['files_sha256'][str(path)]
        payload = bound(path, expected).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == expected, 'actual entry snapshot changed during read')
        result[name] = {'sha256': expected, 'utf8': payload.decode('utf-8')}
    return result


def execute(repo, record, plan, f, call=subprocess.call):
    """Called once after original natural STOP; every exception is terminal."""
    require(predecessor_ready(repo), 'original processes are not terminal')
    bound(safe(repo, SELF_REL + '/' + PLAN_NAME), plan['_verified_plan_sha256'])
    old = safe(repo, OLD_RECORD_REL)
    pins = dict(load(old / 'source_pins.json'))
    pins.update(plan['files_sha256'])
    pins[str(safe(repo, SELF_REL + '/' + PLAN_NAME))] = plan['_verified_plan_sha256']
    require(str(safe(repo, f.ROOT_NAME)) not in pins, 'old mutable root must not be a source pin')
    f.recheck(pins)
    f.verify_test_proof(safe(repo, RECOVERY_REL), safe(repo, RECOVERY_REL + '/' + f.HELPER_PROOF), True)
    evidence = f.verify_completed(repo, safe(repo, GATE_REL))
    require(evidence == load(old / 'ACTUAL_GATE_VERIFICATION.json')['evidence_sha256'],
            'current complete evidence differs from original finalizer verified gates')
    evidence.update(predecessor_evidence(repo))
    require(f.sha(safe(repo, f.ROOT_NAME)) == ROOT_SHA, 'root handoff changed; successor refused')
    for relative in (PACKAGE_REL, FINAL_PACKAGE_REL, FINAL_PACKAGE_REL + '.zip'):
        require(not safe(repo, relative).exists(), 'prior delivery/final output exists; no retry')
    f.emit(record / 'source_pins.json', pins)
    f.emit(record / 'ACTUAL_GATE_VERIFICATION.json', {'status': 'PASS', 'verified_utc': utc(),
           'evidence_sha256': evidence, 'verification_function': 'original.finalizer.verify_completed',
           'original_finalizer_natural_stop_verified': True})
    command = adapter_command(repo, plan)
    f.recheck(pins)
    f.recheck(evidence)
    with (record / 'adapter_stdout.log').open('xb') as out, (record / 'adapter_stderr.log').open('xb') as err:
        code = call(command, cwd=repo, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    f.emit(record / 'ADAPTER_PROCESS_FINISH.json', {'exit_code': code, 'finished_utc': utc(),
           'command': command, 'automatic_retry': False})
    require(code == 0, 'certified metadata adapter failed; no retry/publication')
    f.recheck(pins)
    f.recheck(evidence)
    delivery = f.verify_delivery(repo)
    package = f.package_final(repo, record, evidence, delivery, ROOT_SHA, pins)
    f.recheck(pins)
    f.recheck(evidence)
    f.verify_delivery(repo)
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--poll-seconds', default=30, type=int)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'requires -I -S -B')
    require(args.repo == REPO and Path(sys.executable) == PYTHON and
            Path(__file__).resolve().parent == safe(REPO, SELF_REL), 'wrong authorized repository/runtime/source')
    plan = verify_plan(REPO, args.plan)
    f = load_original(REPO)
    root = safe(REPO, SELF_REL)
    record = root / 'attempt001'
    require(not record.exists(), 'successor record already exists; no automatic retry')
    emit(root / 'SUCCESSOR_EXCLUSIVE_RUN_LOCK.json', {'pid': os.getpid(), 'started_utc': utc(),
         'plan_sha256': sha(args.plan), 'automatic_retry': False})
    record.mkdir()
    current = 'waiting_for_original_natural_terminal_failure'
    try:
        emit(record / 'start.json', {'schema': 'paper3-metadata-delivery-successor-start-v1',
             'started_utc': utc(), 'pid': os.getpid(), 'plan_path': str(args.plan), 'plan_sha256': sha(args.plan),
             'previous_root_handoff_sha256': ROOT_SHA, 'manifest_digest': MANIFEST, 'F1_digest': F1,
             'adapter_command': adapter_command(REPO, plan),
             'strict_legacy_reader_installation': f._successor_legacy_reader_installation,
             'planned_reviewed_function_calls': ['certified.strict_legacy_proof_adapter.install',
                 'original.finalizer.verify_test_proof', 'original.finalizer.verify_completed',
                 'original.finalizer.recheck', 'certified.observer_adapter.CLI', 'original.finalizer.verify_delivery',
                 'original.finalizer.package_final -> publish_root, locked_root, copy_verified, history_index, make_zip'],
             'all_launch_plan_pins_sha256': plan['files_sha256'],
             'successor_source_proof_and_plan_archived_in_this_record': launch_snapshots(REPO, plan, args.plan),
             'no_new_models_generators_or_statistics_executed': True, 'automatic_scientific_retry': False})
        wait_predecessor(REPO, args.poll_seconds)
        current = 'verified_metadata_delivery_and_original_archive_publication'
        package = execute(REPO, record, plan, f)
        emit(record / 'finish.json', {'status': 'COMPLETED', 'finished_utc': utc(), 'final_delivery': package,
             'counts': {'initial_states': 60, 'trajectories': 1200, 'paired_groups': 240},
             'original_terminal_records_preserved': True, 'no_new_models_generators_or_statistics_executed': True,
             'not_whole_manuscript_freeze': True, 'automatic_retry': False})
        print(json.dumps({'status': 'COMPLETED', 'final_delivery': package}, indent=2))
    except BaseException as error:
        emit(record / 'stopped.json', {'status': 'STOPPED_FOR_DIAGNOSIS', 'phase': current, 'finished_utc': utc(),
             'exception_type': type(error).__name__, 'message': str(error), 'all_partial_outputs_preserved': True,
             'automatic_retry': False, 'scientific_pass_claimed': False})
        raise


if __name__ == '__main__':
    main()
