"""Isolated synthetic filesystem fixtures. No repository result/model imports."""
import ast
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('standalone_finalizer',HERE/'finalizer.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
cspec=importlib.util.spec_from_file_location('standalone_continuation',HERE/'continuation.py')
c=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(c);c.f=f
NATIVE_PROCESS_DEAD=f.native_process_dead
NATIVE_FREE_COMMIT=f.native_free_commit_bytes

def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')
def alter(path,edit):
    value=f.load(path);edit(value)
    if value.get('schema')=='paper3-abrupt-recovery-pure-audit-v1':
        body=dict(value);body.pop('audit_digest',None);value['audit_digest']=f.canonical(body)
    if value.get('schema')=='paper3-abrupt-recovery-gate-v1':
        body=dict(value);body.pop('gate_digest',None);value['gate_digest']=f.canonical(body)
    put(path,value)

class FinalizerTests(unittest.TestCase):
    def setUp(self):
        scratch=HERE/'continuation_synthetic_scratch';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='paper3_finalizer_synthetic_',dir=scratch)
        self.repo=Path(self.temp.name).resolve();self.saved_manifest=f.MANIFEST;self.saved_root=f.FIXED_ROOT_SHA
        self.process_patch=patch.object(f,'native_process_dead',return_value=True);self.process_patch.start()
        self.resource_patch=patch.object(f,'native_free_commit_bytes',return_value=64*1024**3);self.resource_patch.start()
        self.prior=self.repo/f.SEQUENCE_REL/'authorized_sequence_003';self.prior.mkdir(parents=True)
        self.seq=self.repo/f.CONTINUATION_REL
        self.results=self.repo/f.RESULT_REL
        self.seq.mkdir(parents=True);self.results.mkdir(parents=True)
        source=self.repo/f.SELF_REL/'continuation.py';source.write_text('# synthetic sequence\n')
        (self.seq/'sequence_source_snapshot.py').write_bytes(source.read_bytes())
        put(self.seq/'start.json',{'outcome_based_continuation':False,'implementation_sha256':f.sha(source)})
        put(self.seq/'finish.json',{'status':'AUTHORIZED_CONTINUATION_COMPLETED'})
        manifest={'environment':{},'input_bundle_digest':f.F1,'historical_environment_reproduced':False,'original_protected_snapshot':{str(n):'dummy' for n in range(2535)}}
        f.MANIFEST=f.canonical(manifest);manifest['manifest_digest']=f.MANIFEST;put(self.results/'provenance_manifest.json',manifest)
        for phase,attempt in (('prepare',2),('initial',1),('minimal',1),('full',2),('statistics',1),('model-load',2)):
            self.phase(phase,attempt)
            if phase!='model-load':put((self.prior if phase in ('prepare','initial','minimal') else self.seq)/(phase+'_passed.json'),{'exit_code':0,'gate':{'manifest_digest':f.MANIFEST} if phase=='prepare' else {'gate_checked':True,'phase':phase}})
        model=self.results/'stage_c_tests/model_load_compatibility/attempt002/model_load_compatibility_receipt.json';put(model,{'status':'PASS'})
        terminal=self.repo/f.SEQUENCE_REL/'phase_launches/model-load_002/finish.json'
        put(self.prior/'model_load_gate.json',{'receipt':str(model),'sha256':f.sha(model),'terminal_sha256':f.sha(terminal)})
        states=[{'center_id':c,'seed':s} for c in range(33000,33020) for s in (7311,7312,7313)]
        put(self.results/'initial_state_manifest.json',{'manifest_digest':f.MANIFEST,'input_bundle_digest':f.F1,'completed_cases':60,'states':states})
        put(self.results/'stage_c_minimal_gate.json',{'manifest_digest':f.MANIFEST,'stage_c_pass':True,'completed_trajectories':5,'performance_used_for_gate':False})
        groups={f'{c}/{s}/{scene}':{'five_methods':True,'all_24_stage_input_fields_equal':True,'receipt_sha256':{m:'fixture' for m in f.METHODS}} for c in range(33000,33020) for s in (7311,7312,7313) for scene in ('C0','C1','C3','C4')}
        put(self.results/'full_experiment_integrity_gate.json',{'manifest_digest':f.MANIFEST,'scientific_integrity_pass':True,'trajectories':1200,'paired_groups':240,'all_inputs_F1':True,'old_results_reused':False,'groups':groups})
        stats=self.results/'statistics_batch20_env_v3';stats.mkdir();(stats/'output.csv').write_text('synthetic,value\nonly,1\n')
        put(stats/'statistics_manifest.json',{'fixture':True})
        put(stats/'statistics_execution_receipt.json',{'schema':'paper3-statistics-execution-receipt-v1','status':'COMPLETED','exit_code':0,'replication_manifest_digest':f.MANIFEST,'originals_unchanged':True,'joint_resampling_verified':True,'models_or_generators_executed':False,'statistics_manifest_sha256':f.sha(stats/'statistics_manifest.json'),'outputs_sha256':{'output.csv':f.sha(stats/'output.csv')}})
        failed=self.results/'execution/full/A_FULL_0001/failure.json'
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'synthetic original handoff');f.FIXED_ROOT_SHA=f.sha(root)
        source_relatives=(f.SELF_REL+'/cold_audit.py',f.SELF_REL+'/recover.py',f.SELF_REL+'/continuation.py',f.SELF_REL+'/finalizer.py',f.SEQUENCE_REL+'/authorized_sequence.py',f.SEQUENCE_REL+'/phase_launcher.py',f.PREFIX+'replication_finalizer_env_v3/finalizer.py')
        for relative in source_relatives:
            path=self.repo/relative;path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_text('# synthetic source fixture')
        pins={str(self.repo/relative):f.sha(self.repo/relative) for relative in source_relatives}
        proof=self.repo/f.SELF_REL/f.COLD_PROOF
        put(proof,{'status':'PASS','all_pass':True,'tests_run':42,'failures':0,'errors':0,'skipped':0,'implementation_sha256':{str(self.repo/f.SELF_REL/name):f.sha(self.repo/f.SELF_REL/name) for name in ('recover.py','cold_audit.py')}})
        execution=self.repo/f.SELF_REL/'cold_recovery_001';execution.mkdir()
        snapshot=execution/'observer_snapshot.json';put(snapshot,{'schema':'synthetic-cold-observer','synthetic_only':True})
        audit=execution/'cold_audit.json';put(audit,{'schema':'paper3-abrupt-recovery-pure-audit-v1','status':'COLD_SNAPSHOT_CONSISTENT','all_checks_pass':True,'completed_trajectories':123,'complete_paired_groups':24,'initial_cases':60,'original_files_unchanged':True,'frozen_sources_unchanged':True,'all_existing_records_verified':True,'models_generators_or_statistics_executed':False,'processes_modified':False,'snapshot_digest':f.canonical(f.load(snapshot))})
        alter(audit,lambda x:None)
        task={'center_id':33002,'seed':7311,'scenario':'C0','method':'B8','config_id':'B8_AlwaysOpen_ratio10'};stem='B8_AlwaysOpen_ratio10_33002_7311_C0'
        pending=self.results/'attempts'/stem/'A_FULL_0001/W1';pending.mkdir(parents=True)
        bindings={'task':task,'input_bundle_digest':f.F1,'environment_binding':f.canonical({})}
        rng=pending/'rng_before.json';rng_body={'bindings':bindings,'synthetic_only':True};put(rng,{**rng_body,'state_digest':f.canonical(rng_body)})
        shared={'producer':'external-cold-recovery-observer','worker_exception_observed':False,'exit_code':None,'child_exit_code':None}
        put(failed,{**shared,'phase':'full','attempt_id':'A_FULL_0001','manifest_digest':f.MANIFEST})
        interruption=pending/'failure.json';put(interruption,{**shared,'status':'INTERRUPTED','completed_valid':False,'task':task,'manifest_digest':f.MANIFEST,'input_bundle_digest':f.F1,'environment_binding':f.canonical({}),'rng_relative':rng.relative_to(self.results).as_posix(),'rng_file_sha256':f.sha(rng),'failed_before_rng_capture':False})
        files=(proof,snapshot,audit,failed,interruption,rng,self.results/'provenance_manifest.json',self.results/'initial_state_manifest.json')
        evidence={str(path):f.sha(path) for path in files}
        self.gate_path=execution/'cold_gate.json'
        def rec(path):return {'path':str(path),'sha256':f.sha(path)}
        gate={'schema':'paper3-abrupt-recovery-gate-v1','status':'PASS','repository':str(self.repo),'results_root':str(self.results),'manifest_digest':f.MANIFEST,'input_bundle_digest':f.F1,'root_handoff_sha256':f.FIXED_ROOT_SHA,'worker_count':2,'performance_used_for_recovery':False,'model_output_worker_invariance_claimed':False,'resource_gate_pass':True,'process_absence_checked':True,'all_old_processes_absent':True,'completed_trajectories':123,'complete_paired_groups':24,'unknown_or_partial_artifacts':0,'old_attempt_id':'A_FULL_0001','new_attempt_id':'A_FULL_0002','source_bindings_sha256':pins,'evidence_sha256':evidence,'old_processes':[{'pid':123+i,'expected_creation_filetime':456+i,'original_identity_absent':True,'old_exit_code':None,'observed_utc':'2026-10-09T12:00:00+00:00'} for i in range(7)],'old_terminal_records':{'sequence_stopped':False,'finalizer_stopped':False,'phase_launcher_finished':False},'human_Codex_close_report':'VERIFIED_USER_REPORT','causal_exit_actor':'NOT_VERIFIED','observer_snapshot':rec(snapshot),'cold_audit':rec(audit),'task_failure_receipt':rec(interruption),'phase_failure_receipt':rec(failed),'initial_state_manifest_sha256':f.sha(self.results/'initial_state_manifest.json'),'pending_task':task,'pending_rng_relative':rng.relative_to(self.results).as_posix(),'pending_rng_file_sha256':f.sha(rng),'pending_rng_state_digest':f.load(rng)['state_digest'],'actual_prelaunch_resource_sample':{'historical_worker_private_bytes':int(3.5*1024**3),'private_bytes_source':'CONSERVATIVE_BOUND_NOT_CURRENT_MEASUREMENT','minimum_free_commit_bytes':8*1024**3,'free_commit_bytes':10*1024**3,'requested_worker_count':2},'minimum_free_commit_bytes':8*1024**3}
        gate['gate_digest']=f.canonical(gate);put(self.gate_path,gate)
        alter(self.seq/'start.json',lambda x:x.update(transition_gate_sha256=f.sha(self.gate_path)))
        alter(self.seq/'finish.json',lambda x:x.update(manifest_digest=f.MANIFEST))
    def tearDown(self): f.MANIFEST=self.saved_manifest;f.FIXED_ROOT_SHA=self.saved_root;self.process_patch.stop();self.resource_patch.stop();self.temp.cleanup()
    def phase(self,phase,attempt):
        root=self.repo/f.SEQUENCE_REL/f'phase_launches/{phase}_{attempt:03d}';root.mkdir(parents=True)
        launcher=self.repo/f.SEQUENCE_REL/'phase_launcher.py';launcher.write_text('# launcher fixture\n')
        script=self.repo/f.SEQUENCE_REL/(phase+'_fixture.py');script.write_text('# no execution\n')
        command=[str(self.repo/f.ENV_REL),'-I','-S','-B',str(script)]
        pins={str(launcher):f.sha(launcher),str(script):f.sha(script)}
        put(root/'start.json',{'command':command,'launch_source_sha256':pins})
        put(root/'finish.json',{'phase':phase,'attempt':attempt,'exit_code':0,'child_exit_code':0,'launch_source_bindings_unchanged':True,'changed_source_paths':[],'command':command})
        (root/'launcher_source_snapshot.py').write_bytes(launcher.read_bytes());(root/'invoked_script_source_snapshot.py').write_bytes(script.read_bytes())
    def test_complete_actual_gate_fixture_passes(self): self.assertGreater(len(f.verify_completed(self.repo,self.gate_path)),20)
    def test_launched_only_not_completed(self):
        (self.seq/'finish.json').unlink()
        with self.assertRaises(FileNotFoundError):f.verify_completed(self.repo,self.gate_path)
    def test_sequence_stop_wins_over_finish(self):
        put(self.seq/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS'})
        with self.assertRaises(f.FinalizerError):f.verify_completed(self.repo,self.gate_path)
    def test_snapshot_mutation_rejected(self):
        (self.repo/f.SEQUENCE_REL/'phase_launches/initial_001/invoked_script_source_snapshot.py').write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_completed(self.repo,self.gate_path)
    def test_live_source_mutation_rejected(self):
        (self.repo/f.SEQUENCE_REL/'initial_fixture.py').write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_completed(self.repo,self.gate_path)
    def test_sequence_source_mutation_rejected(self):
        (self.repo/f.SELF_REL/'continuation.py').write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_completed(self.repo,self.gate_path)
    def test_actual_stats_output_mutation_rejected(self):
        (self.results/'statistics_batch20_env_v3/output.csv').write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_completed(self.repo,self.gate_path)
    def test_wait_has_no_science_child(self):
        (self.seq/'finish.json').unlink();calls=[]
        def sleep(seconds):calls.append(seconds);put(self.seq/'finish.json',{'status':'AUTHORIZED_CONTINUATION_COMPLETED'})
        f.wait_terminal(self.repo,30,sleep);self.assertEqual(calls,[30])
    def test_wait_stopped_no_sleep(self):
        put(self.seq/'stopped.json',{'phase':'full','status':'STOPPED_FOR_DIAGNOSIS'})
        with self.assertRaises(f.FinalizerError):f.wait_terminal(self.repo,30,lambda x:self.fail('sleep after stop'))
    def test_wait_bound(self):
        for value in (0,-1,61):
            with self.assertRaises(f.FinalizerError):f.wait_terminal(self.repo,value)
    def test_safe_relative_traversal(self):
        for path in ('../bad',str(self.repo/'absolute')):
            with self.assertRaises(f.FinalizerError):f.safe(self.repo,path)
    def test_safe_symlink_rejected(self):
        # Synthetic link flag exercises rejection without requiring symlink privilege.
        original=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda path:True if path==self.repo/'link' else original(path)):
            with self.assertRaises(f.FinalizerError):f.safe(self.repo,'link/file')
    def test_safe_reparse_flag_rejected(self):
        class State:st_file_attributes=0x400
        with patch.object(Path,'lstat',return_value=State()),patch.object(Path,'is_symlink',return_value=False):
            with self.assertRaises(f.FinalizerError):f.reject_reparse(self.repo)
    def test_duplicate_json_rejected(self):
        path=self.repo/'duplicate.json';path.write_text('{"a":1,"a":2}')
        with self.assertRaises(f.FinalizerError):f.load(path)
    def test_nonfinite_json_rejected(self):
        path=self.repo/'bad.json';path.write_text('{"a":NaN}')
        with self.assertRaises(f.FinalizerError):f.load(path)
    def test_exclusive_never_overwrites(self):
        path=self.repo/'exclusive';f.exclusive(path,b'first')
        with self.assertRaises(FileExistsError):f.exclusive(path,b'next')
        self.assertEqual(path.read_bytes(),b'first')
    def test_source_pin_mutation(self):
        path=self.repo/'source.py';path.write_text('first');pins={str(path):f.sha(path)};path.write_text('second')
        with self.assertRaises(f.FinalizerError):f.recheck(pins)
    @contextmanager
    def fixture_lock(self,path):
        with Path(path).open('r+b') as stream:yield stream
    def test_root_archived_exactly_before_publish(self):
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'previous');draft=self.repo/'draft.md';draft.write_bytes(b'actual saved draft')
        publication=self.repo/'publication';publication.mkdir()
        digest=f.publish_root(self.repo,publication,f.bytes_sha(b'previous'),draft,f.sha(draft),self.fixture_lock)
        self.assertEqual(root.read_bytes(),b'actual saved draft');self.assertEqual((publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').read_bytes(),b'previous')
        self.assertEqual(digest,f.sha(root));self.assertEqual(f.load(publication/'PUBLICATION_RECEIPT.json')['previous_sha256'],f.bytes_sha(b'previous'))
    def test_root_race_refuses_overwrite(self):
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'other researcher update');draft=self.repo/'draft';draft.write_bytes(b'draft');publication=self.repo/'publication';publication.mkdir()
        with self.assertRaises(f.FinalizerError):f.publish_root(self.repo,publication,f.bytes_sha(b'previous'),draft,f.sha(draft),self.fixture_lock)
        self.assertEqual(root.read_bytes(),b'other researcher update');self.assertEqual(list(publication.iterdir()),[])
    def test_existing_archive_prevents_root_write(self):
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'previous');draft=self.repo/'draft';draft.write_bytes(b'draft');publication=self.repo/'publication';publication.mkdir();(publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').write_bytes(b'existing')
        with self.assertRaises(FileExistsError):f.publish_root(self.repo,publication,f.sha(root),draft,f.sha(draft),self.fixture_lock)
        self.assertEqual(root.read_bytes(),b'previous')
    def test_windows_lock_denies_second_writer(self):
        if os.name!='nt':self.skipTest('Windows-only kernel guarantee')
        root=self.repo/'lock';root.write_bytes(b'original')
        with f.locked_root(root):
            with self.assertRaises(PermissionError):root.open('wb')
            with self.assertRaises(PermissionError):root.unlink()
            self.assertEqual(root.read_bytes(),b'original')
        self.assertEqual(root.read_bytes(),b'original')
        with root.open('r+b') as stream:stream.write(b'allowed!')
        self.assertEqual(root.read_bytes(),b'allowed!')
    def test_draft_mutation_refuses_root_write(self):
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'previous');draft=self.repo/'draft';draft.write_bytes(b'bound draft');expected=f.sha(draft);draft.write_bytes(b'changed draft');publication=self.repo/'publication';publication.mkdir()
        with self.assertRaises(f.FinalizerError):f.publish_root(self.repo,publication,f.sha(root),draft,expected,self.fixture_lock)
        self.assertEqual(root.read_bytes(),b'previous');self.assertEqual(list(publication.iterdir()),[])
    def test_precommit_failure_refuses_root_write(self):
        root=self.repo/f.ROOT_NAME;root.write_bytes(b'previous');draft=self.repo/'draft';draft.write_bytes(b'bound draft');publication=self.repo/'publication';publication.mkdir()
        def fail():raise f.FinalizerError('binding mismatch')
        with self.assertRaises(f.FinalizerError):f.publish_root(self.repo,publication,f.sha(root),draft,f.sha(draft),self.fixture_lock,fail)
        self.assertEqual(root.read_bytes(),b'previous');self.assertEqual(list(publication.iterdir()),[])
    def test_copy_hash_read_race_rejected(self):
        source=self.repo/'source';source.write_bytes(b'bound');target=self.repo/'target';digest=f.sha(source);real=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda path:b'changed' if path==source else real(path)):
            with self.assertRaises(f.FinalizerError):f.copy_verified(source,target,digest)
        self.assertFalse(target.exists())
    def test_copy_destination_matches_binding(self):
        source=self.repo/'source';source.write_bytes(b'bound');target=self.repo/'target';f.copy_verified(source,target,f.sha(source));self.assertEqual(f.sha(source),f.sha(target))
    def test_zip_exact_sha_inventory(self):
        package=self.repo/'package';package.mkdir();(package/'a').write_bytes(b'abc');(package/'b').write_bytes(b'def')
        target=self.repo/'package.zip';digest=f.make_zip(package,target);self.assertEqual(digest,f.sha(target))
        with zipfile.ZipFile(target) as archive:self.assertEqual(set(archive.namelist()),{'a','b'})
    def test_existing_zip_refuses_overwrite(self):
        package=self.repo/'package';package.mkdir();(package/'a').write_text('synthetic');target=self.repo/'package.zip';target.write_bytes(b'existing')
        with self.assertRaises(f.FinalizerError):f.make_zip(package,target)
        self.assertEqual(target.read_bytes(),b'existing')
    def test_inventory_unbound_extra_rejected(self):
        package=self.repo/'package';package.mkdir();(package/'a').write_text('a');expected=f.inventory(package);(package/'b').write_text('b')
        with self.assertRaises(f.FinalizerError):f.verify_inventory(package,expected)
    def test_command_has_only_reviewed_delivery(self):
        command=f.delivery_command(self.repo);self.assertEqual(command[:4],[str(self.repo/f.ENV_REL),'-I','-S','-B'])
        self.assertEqual([x for x in command if x.endswith('.py')],[str(self.repo/f.DELIVERY_REL/'delivery.py')]);self.assertIn(f.MANIFEST,command)
    def delivery_fixture(self):
        package=self.repo/f.PACKAGE_REL;package.mkdir(parents=True)
        reports={}
        for name in (*f.REPORTS,'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'):
            (package/name).write_text('synthetic saved report '+name)
            (self.results/name).write_bytes((package/name).read_bytes())
            reports[str(self.results/name)]=f.sha(self.results/name)
        files=f.inventory(package)
        delivery={'schema':'paper3-saved-results-delivery-v1','status':'COMPLETED','replication_manifest_digest':f.MANIFEST,'package_root':str(package),'root_handoff_modified':False,'original_protected_files_unchanged':2535,'package_files_sha256':files,'results_report_files_sha256':reports}
        payload=(json.dumps(delivery)+'\n').encode()
        for root in (package,self.results):
            (root/'DELIVERY_MANIFEST.json').write_bytes(payload)
            (root/'DELIVERY_MANIFEST.json.sha256').write_text(f.bytes_sha(payload)+'  DELIVERY_MANIFEST.json\n')
        return package
    def test_reviewed_delivery_fixture_passes(self):
        package=self.delivery_fixture();delivery=f.verify_delivery(self.repo)
        self.assertEqual(delivery['_verified_manifest_sha256'],f.sha(package/'DELIVERY_MANIFEST.json'))
    def test_reviewed_delivery_draft_tamper_rejected(self):
        package=self.delivery_fixture();(package/'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md').write_text('unbound altered draft')
        with self.assertRaises(f.FinalizerError):f.verify_delivery(self.repo)
    def test_reviewed_delivery_unbound_extra_rejected(self):
        package=self.delivery_fixture();(package/'unbound').write_text('extra')
        with self.assertRaises(f.FinalizerError):f.verify_delivery(self.repo)
    def test_reviewed_delivery_result_report_tamper_rejected(self):
        self.delivery_fixture();(self.results/f.REPORTS[0]).write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_delivery(self.repo)
    def test_reviewed_delivery_sidecar_tamper_rejected(self):
        package=self.delivery_fixture();(package/'DELIVERY_MANIFEST.json.sha256').write_text('bad')
        with self.assertRaises(f.FinalizerError):f.verify_delivery(self.repo)
    def test_reviewed_delivery_manifest_copy_tamper_rejected(self):
        self.delivery_fixture();(self.results/'DELIVERY_MANIFEST.json').write_text('{}')
        with self.assertRaises(f.FinalizerError):f.verify_delivery(self.repo)
    def test_authority_parsed_from_same_payload(self):
        package=self.delivery_fixture();real=f.load
        def reject_reread(path):
            if Path(path)==package/'DELIVERY_MANIFEST.json':self.fail('manifest authority re-read instead of exact byte payload')
            return real(path)
        with patch.object(f,'load',side_effect=reject_reread):f.verify_delivery(self.repo)
    def test_synthetic_proof_source_binding(self):
        root=self.repo/'toy_source';root.mkdir();(root/'one.py').write_text('# source')
        proof=root/'proof.json';put(proof,{'all_pass':True,'exit_code':0,'real_delivery_published':False,'real_outcomes_read':False,'models_generators_or_statistics_executed':False,'implementation_sha256':{'one.py':f.sha(root/'one.py')}})
        f.verify_test_proof(root,proof);(root/'one.py').write_text('# changed')
        with self.assertRaises(f.FinalizerError):f.verify_test_proof(root,proof)
    def test_no_science_imports(self):
        tree=ast.parse((HERE/'finalizer.py').read_text())
        forbidden={'numpy','pandas','torch','river','scipy','sklearn','core','science_adapter','statistics'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):self.assertTrue(all(x.name.split('.')[0] not in forbidden for x in node.names))
            if isinstance(node,ast.ImportFrom):self.assertNotIn((node.module or '').split('.')[0],forbidden)
    def test_history_indexes_all_statuses_no_raw(self):
        scope=self.repo/f.SEQUENCE_REL/'prior_attempt';scope.mkdir();put(scope/'stopped.json',{'fixture':'failure'});put(scope/'finish.json',{'fixture':'success'})
        raw=self.results/'raw';raw.mkdir();(raw/'large.csv').write_text('excluded')
        index=f.history_index(self.repo);self.assertIn(str(scope/'stopped.json'),index);self.assertIn(str(scope/'finish.json'),index);self.assertNotIn(str(raw/'large.csv'),index)
    def test_transition_valid_fixture(self):self.assertEqual(f.verify_transition_gate(self.repo,self.gate_path)['gate']['worker_count'],2)
    def test_transition_root_not_postpublication_immutable_pin(self):
        root=self.repo/f.ROOT_NAME;alter(self.gate_path,lambda x:x['source_bindings_sha256'].update({str(root):f.sha(root)}))
        admitted=f.verify_transition_gate(self.repo,self.gate_path)
        self.assertNotIn(str(root),admitted['evidence_sha256'])
        root.write_bytes(b'authorized later saved-draft publication')
        f.recheck(admitted['evidence_sha256'])
    def test_transition_gate_payload_sha_sealed(self):
        original=Path.read_bytes;changed=False
        def read(path):
            nonlocal changed
            payload=original(path)
            if path==self.gate_path and not changed:
                changed=True;path.write_bytes(payload+b' ')
            return payload
        with patch.object(Path,'read_bytes',side_effect=None,autospec=True) as mocked:
            mocked.side_effect=read
            with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def recert_evidence(self,path):
        alter(self.gate_path,lambda x:x['evidence_sha256'].update({str(path):f.sha(path)}))
        for field in ('observer_snapshot','cold_audit','task_failure_receipt','phase_failure_receipt'):
            if f.load(self.gate_path).get(field,{}).get('path')==str(path):alter(self.gate_path,lambda x:x[field].update(sha256=f.sha(path)))
    def test_transition_missing_mandatory_controller_source(self):
        alter(self.gate_path,lambda x:x['source_bindings_sha256'].pop(str(self.repo/f.SELF_REL/'recover.py')))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_controller_proof_not_bound(self):
        alter(self.gate_path,lambda x:x['evidence_sha256'].pop(str(self.repo/f.SELF_REL/f.COLD_PROOF)))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_controller_test_fail_rejected(self):
        path=self.repo/f.SELF_REL/f.COLD_PROOF;alter(path,lambda x:x.update(all_pass=False,failures=1));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_proof_declared_skipped_rejected(self):
        path=self.repo/f.SELF_REL/f.COLD_PROOF;alter(path,lambda x:x.update(skipped=1));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_review_test_source_mismatch(self):
        path=self.repo/f.SELF_REL/f.COLD_PROOF;alter(path,lambda x:x['implementation_sha256'].update({str(self.repo/f.SELF_REL/'cold_audit.py'):'wrong'}));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_root_preflight_fail_rejected(self):
        path=self.gate_path.parent/'cold_audit.json';alter(path,lambda x:x.update(status='FAIL',mismatches=[{'fixture':'bad'}]));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_root_preflight_wrong_implementation(self):
        path=self.gate_path.parent/'cold_audit.json';alter(path,lambda x:x.update(snapshot_digest='wrong'));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_one_process_not_enough(self):
        alter(self.gate_path,lambda x:x.update(old_processes=x['old_processes'][:1]))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_missing_external_review(self):
        alter(self.gate_path,lambda x:x['evidence_sha256'].pop(str(self.gate_path.parent/'cold_audit.json')))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_fabricated_worker_traceback_rejected(self):
        bridge=Path(f.load(self.gate_path)['task_failure_receipt']['path']);alter(bridge,lambda x:x.update(traceback='invented worker exception'));self.recert_evidence(bridge)
        alter(self.gate_path,lambda x:x['task_failure_receipt'].update(sha256=f.sha(bridge)))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_missing_interrupted_task_bridge(self):
        alter(self.gate_path,lambda x:x.update(pending_rng_relative=''))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def actual_self_creation(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
        kernel.GetProcessTimes.restype=wintypes.BOOL
        times=[wintypes.FILETIME() for _ in range(4)]
        self.assertTrue(kernel.GetProcessTimes(kernel.GetCurrentProcess(),*times))
        return (times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
    def test_native_process_admission_detects_self_alive(self):
        self.assertFalse(NATIVE_PROCESS_DEAD({'pid':os.getpid(),'creation_filetime':self.actual_self_creation()}))
    def test_native_process_admission_distinguishes_creation(self):
        self.assertTrue(NATIVE_PROCESS_DEAD({'pid':os.getpid(),'creation_filetime':self.actual_self_creation()+1}))
    def test_native_process_admission_absent_pid(self):
        self.assertTrue(NATIVE_PROCESS_DEAD({'pid':0,'creation_filetime':1}))
    def test_native_free_commit_probe_read_only(self):
        amount=NATIVE_FREE_COMMIT();self.assertIs(type(amount),int);self.assertGreaterEqual(amount,0)
    def test_transition_root_mismatch(self):
        (self.repo/f.ROOT_NAME).write_bytes(b'other update')
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_source_mismatch(self):
        (self.repo/f.SELF_REL/'recover.py').write_text('changed')
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_fabricated_old_sequence_terminal_rejected(self):
        put(self.prior/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','fabricated':True})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_fabricated_old_finalizer_terminal_rejected(self):
        put(self.repo/f.PREFIX/'replication_finalizer_env_v3/attempt001/stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS','fabricated':True})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_old_phase_failure_missing(self):
        (self.results/'execution/full/A_FULL_0001/failure.json').unlink()
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_full1_fake_pass(self):
        put(self.results/'execution/full/A_FULL_0001/completion.json',{'success':True})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_current_old_process_alive(self):
        with patch.object(f,'native_process_dead',return_value=False):
            with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_old_rng_without_failure(self):
        put(self.results/'attempts/task/A_FULL_0001/W1/rng_before.json',{'fixture':True})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_old_unpublished_completed_attempt(self):
        put(self.results/'attempts/task/A_FULL_0001/W1/receipt.json',{'fixture':True})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_global_partial_raw_admission(self):
        raw=self.results/'raw';raw.mkdir();(raw/'partial.csv').write_text('incomplete')
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path,admission=True)
    def test_transition_insufficient_current_commit(self):
        with patch.object(f,'native_free_commit_bytes',return_value=6*1024**3):
            with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path,check_resource=True)
    def test_transition_underbudget_sevenGiB(self):
        alter(self.gate_path,lambda x:x.update(minimum_free_commit_bytes=6*1024**3))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_performance_based(self):
        alter(self.gate_path,lambda x:x.update(performance_used_for_recovery=True))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_wrong_F1(self):
        alter(self.gate_path,lambda x:x.update(input_bundle_digest='wrong'))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_wrong_workers(self):
        alter(self.gate_path,lambda x:x.update(worker_count=3))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_transition_requires_zero_pending(self):
        alter(self.gate_path,lambda x:x.update(unknown_or_partial_artifacts=1))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_continuation_exact_launcher_commands(self):
        full=c.phase_command(self.repo,'full');stats=c.phase_command(self.repo,'statistics')
        self.assertEqual(full[full.index('--attempt')+1],'2');self.assertEqual(full[full.index('--workers')+1],'2')
        self.assertEqual(stats[stats.index('--attempt')+1],'1');self.assertEqual(stats[stats.index('--workers')+1],'1')
        self.assertEqual([x for x in full if x.endswith('.py')],[str(self.repo/f.SEQUENCE_REL/'phase_launcher.py')])
    def test_continuation_failed_full2_never_starts_statistics(self):
        folder=self.repo/f.SEQUENCE_REL/'phase_launches/full_002';folder.rename(folder.with_name('saved_full_fixture'))
        record=self.repo/'synthetic_continuation_record';record.mkdir();commands=[]
        def child(command,cwd):commands.append(command);return 2
        with self.assertRaises(f.FinalizerError):c.run_phases(self.repo,record,self.gate_path,{},child)
        self.assertEqual(len(commands),1);self.assertFalse((record/'full_passed.json').exists());self.assertFalse((record/'statistics_start.json').exists())
    def test_continuation_existing_phase2_refused(self):
        record=self.repo/'synthetic_continuation_record';record.mkdir()
        with self.assertRaises(f.FinalizerError):c.run_phases(self.repo,record,self.gate_path,{},lambda *a,**k:self.fail('child should not start'))
    def test_continuation_helper_has_no_model_imports(self):
        tree=ast.parse((HERE/'continuation.py').read_text())
        forbidden={'numpy','torch','pandas','river','core','scipy','sklearn'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):self.assertTrue(all(x.name.split('.')[0] not in forbidden for x in node.names))
            if isinstance(node,ast.ImportFrom):self.assertNotIn((node.module or '').split('.')[0],forbidden)

    def test_cold_exact_ratio10_config_admitted(self):
        self.assertEqual(f.verify_transition_gate(self.repo,self.gate_path)['gate']['pending_task']['config_id'],'B8_AlwaysOpen_ratio10')
    def test_cold_config_alias_rejected(self):
        for alias in ('B8_AlwaysOpen','B8_AlwaysOpen_RI','B8'):
            alter(self.gate_path,lambda x:x['pending_task'].update(config_id=alias))
            with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_absent_old_terminals_are_valid(self):
        self.assertFalse((self.prior/'stopped.json').exists())
        self.assertFalse((self.repo/f.SEQUENCE_REL/'phase_launches/full_001/finish.json').exists())
        self.assertTrue(f.verify_transition_gate(self.repo,self.gate_path))
    def test_cold_fabricated_old_launcher_exit_rejected(self):
        put(self.repo/f.SEQUENCE_REL/'phase_launches/full_001/finish.json',{'exit_code':1,'child_exit_code':1})
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_unknown_old_exit_cannot_be_zero(self):
        path=Path(f.load(self.gate_path)['phase_failure_receipt']['path']);alter(path,lambda x:x.update(exit_code=0));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_task_unknown_exit_cannot_be_invented(self):
        path=Path(f.load(self.gate_path)['task_failure_receipt']['path']);alter(path,lambda x:x.update(child_exit_code=1));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_human_report_does_not_verify_cause(self):
        alter(self.gate_path,lambda x:x.update(causal_exit_actor='VERIFIED_CODEX'))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_unknown_creation_ticks_are_not_fabricated(self):
        alter(self.gate_path,lambda x:x['old_processes'][0].update(expected_creation_filetime=None))
        self.assertTrue(f.verify_transition_gate(self.repo,self.gate_path))
    def test_cold_numeric_pid_not_seven_distinct_instances(self):
        alter(self.gate_path,lambda x:x['old_processes'].__setitem__(1,dict(x['old_processes'][0])))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_missing_initial60_evidence_rejected(self):
        alter(self.gate_path,lambda x:x['evidence_sha256'].pop(str(self.results/'initial_state_manifest.json')))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_122_completed_not_original123(self):
        alter(self.gate_path,lambda x:x.update(completed_trajectories=122))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_audit_cannot_only_claim_pass_without_count_proof(self):
        path=Path(f.load(self.gate_path)['cold_audit']['path']);alter(path,lambda x:x.pop('all_existing_records_verified'));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_missing_initial60_audit_proof(self):
        path=Path(f.load(self.gate_path)['cold_audit']['path']);alter(path,lambda x:x.update(initial_cases=59));self.recert_evidence(path)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_unapproved_external_pin_rejected(self):
        external=self.repo.parent/(self.repo.name+'_external_pin');external.write_bytes(b'unapproved synthetic bytes')
        try:
            alter(self.gate_path,lambda x:x['source_bindings_sha256'].update({str(external):f.sha(external)}))
            with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
        finally:external.unlink()
    def test_cold_frozen_external_environment_pin_accepted(self):
        external=self.repo.parent/(self.repo.name+'_external_pin');external.write_bytes(b'allowlisted synthetic runtime bytes')
        try:
            manifest=self.results/'provenance_manifest.json';value=f.load(manifest);value['environment']['bound_files_sha256']={str(external):f.sha(external)}
            unsigned=dict(value);unsigned.pop('manifest_digest');f.MANIFEST=f.canonical(unsigned);value['manifest_digest']=f.MANIFEST;put(manifest,value)
            # This isolated admission fixture updates its synthetic frozen identity,
            # never any real protocol/model/input file.
            self.recert_evidence(manifest)
            alter(self.gate_path,lambda x:x.update(manifest_digest=f.MANIFEST))
            for name in ('task_failure_receipt','phase_failure_receipt'):
                file=Path(f.load(self.gate_path)[name]['path']);alter(file,lambda x:x.update(manifest_digest=f.MANIFEST,environment_binding=f.canonical(value['environment'])));self.recert_evidence(file)
            initial=self.results/'initial_state_manifest.json';alter(initial,lambda x:x.update(manifest_digest=f.MANIFEST));self.recert_evidence(initial)
            alter(self.gate_path,lambda x:x.update(initial_state_manifest_sha256=f.sha(initial)))
            rng=self.results/f.load(self.gate_path)['pending_rng_relative'];state=f.load(rng);state['bindings']['environment_binding']=f.canonical(value['environment']);body=dict(state);body.pop('state_digest');state['state_digest']=f.canonical(body);put(rng,state);self.recert_evidence(rng)
            failure=Path(f.load(self.gate_path)['task_failure_receipt']['path']);alter(failure,lambda x:x.update(rng_file_sha256=f.sha(rng)));self.recert_evidence(failure)
            alter(self.gate_path,lambda x:x.update(pending_rng_file_sha256=f.sha(rng),pending_rng_state_digest=state['state_digest']))
            alter(self.gate_path,lambda x:x['source_bindings_sha256'].update({str(external):f.sha(external)}))
            self.assertTrue(f.verify_transition_gate(self.repo,self.gate_path))
        finally:external.unlink()
    def test_cold_rng_state_digest_invented_rejected(self):
        alter(self.gate_path,lambda x:x.update(pending_rng_state_digest='f'*64))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_resource_budget_below8GiB_rejected(self):
        alter(self.gate_path,lambda x:x.update(minimum_free_commit_bytes=7*1024**3))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_resource_planning_bound_not_measurement(self):
        alter(self.gate_path,lambda x:x['actual_prelaunch_resource_sample'].update(private_bytes_source='CURRENT_MEASUREMENT'))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_global_dropout_invariance_not_claimed(self):
        alter(self.gate_path,lambda x:x.update(model_output_worker_invariance_claimed=True))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_gate_canonical_digest_wrong_rejected(self):
        value=f.load(self.gate_path);value['gate_digest']='0'*64;put(self.gate_path,value)
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)
    def test_cold_actual_source_pin_not_bound_proof_rejected(self):
        alter(self.gate_path,lambda x:x['source_bindings_sha256'].pop(str(self.repo/f.SELF_REL/'cold_audit.py')))
        with self.assertRaises(f.FinalizerError):f.verify_transition_gate(self.repo,self.gate_path)

    def test_cold_actual_gate_producer_consumer_contract(self):
        # Exercise the actual new producer with isolated synthetic files and fake
        # observer/driver/auditor interfaces; no real scientific modules execute.
        import sys
        import types
        spec=importlib.util.spec_from_file_location('cold_producer_contract_fixture',HERE/'recover.py')
        producer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=producer;spec.loader.exec_module(producer)
        old=f.load(self.gate_path);execution=self.gate_path.parent
        pending=self.results/old['pending_rng_relative'];failure_path=Path(old['task_failure_receipt']['path']);phase_path=Path(old['phase_failure_receipt']['path'])
        failure=f.load(failure_path);phase=f.load(phase_path);failure_path.unlink();phase_path.unlink()
        evidence={name:digest for name,digest in old['evidence_sha256'].items() if name not in {str(failure_path),str(phase_path)}}
        snapshot={'process_absence':old['old_processes'],'evidence_bindings':{'expected':evidence},'old_terminal_records':old['old_terminal_records'],'context':{'manifest':f.load(self.results/'provenance_manifest.json')},'source_bindings':{'expected':old['source_bindings_sha256']}}
        audit=f.load(old['cold_audit']['path'])
        def audit_snapshot(value):
            result=dict(audit);result.update(snapshot_digest=f.canonical(value),pending_task=old['pending_task'],pending_rng_relative=old['pending_rng_relative'],pending_rng_file_sha256=old['pending_rng_file_sha256'],pending_rng_state_digest=old['pending_rng_state_digest'],initial_state_manifest_sha256=old['initial_state_manifest_sha256']);body=dict(result);body.pop('audit_digest',None);result['audit_digest']=f.canonical(body);return result
        def failure_receipts(*args):return failure,phase
        auditor=types.SimpleNamespace(audit_snapshot=audit_snapshot,failure_receipts=failure_receipts)
        records={str(i):None for i in range(123)}
        def stem(task):return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"
        def retries(*args):return {stem(old['pending_task']):{'failed_receipt_relative':failure_path.relative_to(self.results).as_posix(),'failed_receipt_sha256':f.sha(failure_path)}}
        driver=types.SimpleNamespace(accepted_records=lambda m:records,paired_groups=lambda e:list(range(24)),tasks=lambda:[old['pending_task']],stem=stem,_retry_descriptors=retries)
        observer=types.SimpleNamespace(absence=lambda:old['old_processes'],target_processes=lambda:[],resources=lambda:old['actual_prelaunch_resource_sample'])
        context={'snapshot':snapshot,'audit':audit,'execution_dir':execution,'source_pins':old['source_bindings_sha256'],'driver':driver,'auditor':auditor,'snapshot_ref':old['observer_snapshot'],'audit_ref':old['cold_audit']}
        changes={'REPO':self.repo,'RESULTS':self.results,'MANIFEST_DIGEST':f.MANIFEST,'INPUT_DIGEST':f.F1,'ROOT_SHA':f.FIXED_ROOT_SHA}
        with patch.multiple(producer,**changes),patch.object(producer,'terminal_observations',return_value=old['old_terminal_records']):
            emitted=producer.run_recovery(context,observer)
        generated=execution/'cold_recovery_gate.json'
        self.assertEqual(emitted['schema'],'paper3-abrupt-recovery-gate-v1')
        self.assertTrue(f.verify_transition_gate(self.repo,generated,check_resource=True,admission=True))

def mutation_test(name,path,edit):
    def method(self):
        alter(self.repo/path,edit)
        with self.assertRaises((f.FinalizerError,KeyError)):f.verify_completed(self.repo,self.gate_path)
    method.__name__=name;setattr(FinalizerTests,name,method)

MUTATIONS=(
 ('sequence_not_complete',f.CONTINUATION_REL+'/finish.json',lambda x:x.update(status='STARTED')),
 ('outcome_based_continue',f.CONTINUATION_REL+'/start.json',lambda x:x.update(outcome_based_continuation=True)),
 ('phase_exit_failed',f.SEQUENCE_REL+'/phase_launches/full_002/finish.json',lambda x:x.update(exit_code=1)),
 ('child_exit_failed',f.SEQUENCE_REL+'/phase_launches/full_002/finish.json',lambda x:x.update(child_exit_code=1)),
 ('phase_source_changed',f.SEQUENCE_REL+'/phase_launches/full_002/finish.json',lambda x:x.update(changed_source_paths=['x'])),
 ('sequence_gate_missing',f.CONTINUATION_REL+'/full_passed.json',lambda x:x.update(gate={})),
 ('prepare_digest_wrong',f.SEQUENCE_REL+'/authorized_sequence_003/prepare_passed.json',lambda x:x.update(gate={'manifest_digest':'wrong'})),
 ('manifest_wrong',f.RESULT_REL+'/provenance_manifest.json',lambda x:x.update(manifest_digest='wrong')),
 ('F1_wrong',f.RESULT_REL+'/provenance_manifest.json',lambda x:x.update(input_bundle_digest='wrong')),
 ('initial59',f.RESULT_REL+'/initial_state_manifest.json',lambda x:x.update(completed_cases=59)),
 ('initial_duplicate',f.RESULT_REL+'/initial_state_manifest.json',lambda x:x['states'].__setitem__(0,x['states'][1])),
 ('minimal_not_passed',f.RESULT_REL+'/stage_c_minimal_gate.json',lambda x:x.update(stage_c_pass=False)),
 ('minimal_performance_selection',f.RESULT_REL+'/stage_c_minimal_gate.json',lambda x:x.update(performance_used_for_gate=True)),
 ('only1199',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:x.update(trajectories=1199)),
 ('only239groups',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:x.update(paired_groups=239)),
 ('group_missing',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:x['groups'].pop(next(iter(x['groups'])))),
 ('group_parity_false',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:next(iter(x['groups'].values())).update(all_24_stage_input_fields_equal=False)),
 ('method_missing',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:next(iter(x['groups'].values()))['receipt_sha256'].pop('B0')),
 ('old_reuse',f.RESULT_REL+'/full_experiment_integrity_gate.json',lambda x:x.update(old_results_reused=True)),
 ('stats_only_launched',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(status='STARTED')),
 ('stats_exit_failed',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(exit_code=1)),
 ('stats_wrong_digest',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(replication_manifest_digest='wrong')),
 ('bootstrap_joint_false',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(joint_resampling_verified=False)),
 ('originals_changed',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(originals_unchanged=False)),
 ('stats_model_called',f.RESULT_REL+'/statistics_batch20_env_v3/statistics_execution_receipt.json',lambda x:x.update(models_or_generators_executed=True)),
)
for name,path,edit in MUTATIONS:mutation_test('test_reject_'+name,path,edit)

if __name__=='__main__':unittest.main()
