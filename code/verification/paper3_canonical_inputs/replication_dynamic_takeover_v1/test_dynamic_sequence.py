"""Synthetic contract tests; no model, statistics arithmetic or real delivery."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'replication_dynamic_scheduler_v1'))
import dynamic_sequence as S
import dynamic_delivery_route as R
import dynamic_statistics_route as T
import coordinator as C
import queue_store as Q
import frozen_bridge as B

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
D=module(HERE.parent/'replication_delivery_env_v3/delivery.py','dynamic_test_original_delivery')
F=module(HERE.parent/'replication_delivery_env_v3/test_delivery.py','dynamic_test_original_fixture')
FINAL=module(HERE.parent/'replication_abrupt_recovery_v1/finalizer.py','dynamic_test_original_finalizer')
MATRIX=[{'center_id':c,'seed':seed,'scenario':q,'method':m,'config_id':i}
        for c in range(33000,33020) for seed in (7311,7312,7313) for q in ('C0','C1','C3','C4')
        for m,i in (('B0','B0_Frozen_ratio10'),('B1','B1_AlwaysMaintainP50_ratio10'),('B2','B2_RAVM_ratio10'),
                    ('B8','B8_AlwaysOpen_ratio10'),('P7.7','P7_7_RECOVERABILITY_GUIDED_ratio10_grid33'))]

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8');return str(path)
def owner():
    return ({'schema':'paper3-dynamic-owned-coordinator-start-v1','pid':9,'contract_sha256':'a'*64,'started_utc':'2026-01-01T00:00:00+00:00'},
            {'schema':'paper3-dynamic-owned-coordinator-exit-v1','pid':9,'contract_sha256':'a'*64,'actual_exit_code':0,
             'finished_utc':'2026-01-01T01:00:00+00:00','automatic_retry':False})
def worker():
    h='b'*64
    return {'launch':{'pid':10,'contract_sha256':h},
            'ready':{'schema':'paper3-dynamic-worker-ready-v1','pid':11,'worker_id':'DW0001','contract_sha256':h,'execution_mode':'FULL'},
            'finish':{'schema':'paper3-dynamic-worker-finished-v1','pid':11,'worker_id':'DW0001','contract_sha256':h,'execution_mode':'FULL',
                      'summary':{'assigned_tasks':1,'completed_tasks':1,'skipped_valid_tasks':0},'original_trajectories_returned_after_full_checks':True,
                      'new_manual_seed_introduced':False,'scientific_algorithm_modified':False,'model_output_worker_invariance_claimed':False,'statistics_executed':False},
            'exit':{'schema':'paper3-dynamic-owned-worker-exit-v1','pid':10,'actual_model_pid':11,'contract_sha256':h,'actual_exit_code':0,
                    'finished_validated':True,'producer':'OWNING_FROZEN_PROCESS_BACKEND','automatic_retry':False}}

class PureGates(unittest.TestCase):
    def test_actual_owner_zero(self):S.validate_owner(*owner(),'a'*64,active=lambda p:False)
    def reject_owner(self,key,value,which=1):
        a,b=owner();(a,b)[which][key]=value
        with self.assertRaises(S.RouteError):S.validate_owner(a,b,'a'*64,active=lambda p:False)
    def test_owner_nonzero(self):self.reject_owner('actual_exit_code',1)
    def test_owner_bool_is_not_zero(self):self.reject_owner('actual_exit_code',False)
    def test_owner_contract(self):self.reject_owner('contract_sha256','0'*64)
    def test_owner_pid(self):self.reject_owner('pid',8)
    def test_owner_retry(self):self.reject_owner('automatic_retry',True)
    def test_owner_schema(self):self.reject_owner('schema','OLD_STATIC_SUCCESS')
    def test_owner_naive_time(self):self.reject_owner('finished_utc','2026-01-01T00:00:00')
    def test_owner_live(self):
        with self.assertRaises(S.RouteError):S.validate_owner(*owner(),'a'*64,active=lambda p:True)
    def check_worker(self,w):S.validate_worker(w,{'worker_id':'DW0001'},'b'*64,active=lambda p:False,expected_task_count=1)
    def test_actual_worker_zero(self):self.check_worker(worker())
    def reject_worker(self,part,key,value):
        w=worker();w[part][key]=value
        with self.assertRaises(S.RouteError):self.check_worker(w)
    def test_worker_nonzero(self):self.reject_worker('exit','actual_exit_code',2)
    def test_worker_bool_exit(self):self.reject_worker('exit','actual_exit_code',False)
    def test_worker_model_pid(self):self.reject_worker('exit','actual_model_pid',12)
    def test_worker_popen_pid(self):self.reject_worker('exit','pid',12)
    def test_worker_finish_validation(self):self.reject_worker('exit','finished_validated',False)
    def test_worker_producer(self):self.reject_worker('exit','producer','EXTERNAL_OBSERVER')
    def test_worker_contract(self):self.reject_worker('ready','contract_sha256','c'*64)
    def test_worker_seed(self):self.reject_worker('finish','new_manual_seed_introduced',True)
    def test_worker_algorithm(self):self.reject_worker('finish','scientific_algorithm_modified',True)
    def test_worker_invariance(self):self.reject_worker('finish','model_output_worker_invariance_claimed',True)
    def test_worker_statistics(self):self.reject_worker('finish','statistics_executed',True)
    def test_worker_coverage(self):self.reject_worker('finish','summary',{'assigned_tasks':2,'completed_tasks':1})
    def test_path_escape(self):
        with self.assertRaises(S.RouteError):S.safe(S.REPO.parent/'outside.json')
    def test_duplicate_json(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'bad.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(S.RouteError):S.read(p)
    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'bad.json';p.write_text('{"x":NaN}')
            with self.assertRaises(S.RouteError):S.read(p)
    def test_exclusive_publication(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'a.json';S.emit(p,{'a':1})
            with self.assertRaises(FileExistsError):S.emit(p,{'a':2})
            self.assertEqual(S.read(p),{'a':1})
    def test_original_sources_exact(self):
        for name,h in S.ORIGINAL.items():self.assertEqual(S.sha(S.BASE/name),h)

class ProductionContractTests(unittest.TestCase):
    def test_real_backend_stop_stream_and_poll_contract(self):
        """Actual producer methods with fake Popen; no process is started."""
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);h='b'*64;task=MATRIX[0]
            backend=object.__new__(C.FrozenProcessBackend);backend.contract={'execution_mode':'FULL'}
            process=types.SimpleNamespace(pid=10,poll=lambda:None)
            backend.records={'DW0001':{'root':root,'process':process,'seq':0,'done':0,'ready':True,'actual_pid':11,'exit':False,
                                      'contract_sha256':h,'log':io.StringIO()}}
            claim={'claim_id':'C000002','worker_id':'DW0001','task':task,'task_digest':Q.canonical(task),'bindings':{'synthetic':True}}
            backend.assign('DW0001',claim)
            stream=B.TaskStream(root,'DW0001',{'execution_mode':'FULL','eligible_tasks':[task]},h,
                                lambda t:{'receipt_sha256':'c'*64,'output_sha256':'d'*64},pause=lambda t:None)
            self.assertEqual(next(stream),task);stream._acknowledge()
            events=backend.poll('DW0001');self.assertEqual(events[0]['type'],'DONE')
            backend.stop('DW0001')
            with self.assertRaises(StopIteration):next(stream)
            self.assertEqual(Q.read_json(root/'commands/000002.json'),{'action':'STOP','reason':'validated trajectory boundary; no inflight termination','contract_sha256':h})
            B.publish(root,'finished.json',worker()['finish']);process.poll=lambda:0
            events=backend.poll('DW0001');actual=Q.read_json(root/'actual_exit.json')
            self.assertEqual(events[0]['type'],'EXIT');self.assertEqual(actual['actual_exit_code'],0)
            w=worker();w['exit']=actual;S.validate_worker(w,{'worker_id':'DW0001'},h,active=lambda p:False,expected_task_count=1)
            for path in root.rglob('*'):
                if path.is_file():self.assertTrue(S.terminal_file(path))
            self.assertTrue(list(root.rglob('*.pending_*')))
    def test_real_backend_nonzero_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);backend=object.__new__(C.FrozenProcessBackend);backend.contract={'execution_mode':'FULL'}
            backend.records={'DW0001':{'root':root,'process':types.SimpleNamespace(pid=10,poll=lambda:7),'seq':0,'done':0,
                 'ready':True,'actual_pid':11,'exit':False,'contract_sha256':'b'*64,'log':io.StringIO()}}
            B.publish(root,'finished.json',worker()['finish']);backend.poll('DW0001');w=worker();w['exit']=Q.read_json(root/'actual_exit.json')
            with self.assertRaises(S.RouteError):S.validate_worker(w,{'worker_id':'DW0001'},'b'*64,active=lambda p:False,expected_task_count=1)
    def test_pending_without_canonical_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            path=Path(temp)/('x.json.pending_'+'a'*32);path.write_text('{}')
            with self.assertRaises(S.RouteError):S.terminal_file(path)
    def test_pending_copy_not_hardlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);(root/'x.json').write_text('{}');path=root/('x.json.pending_'+'a'*32);path.write_text('{}')
            with self.assertRaises(S.RouteError):S.terminal_file(path)
    def test_pending_changed_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);Q.exclusive_json(root,'x.json',{'x':1});pending=next(root.glob('*.pending_*'))
            # Replace only the synthetic canonical hardlink, retaining the old pending bytes.
            (root/'x.json').unlink();(root/'x.json').write_text('{"x":2}')
            with self.assertRaises(S.RouteError):S.terminal_file(pending)
    def test_unknown_partial_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'x.partial';p.write_text('x')
            with self.assertRaises(S.RouteError):S.terminal_file(p)
    def test_real_queue_replay_and_retained_population(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp)/'run';q=Q.QueueStore(root,MATRIX,{'synthetic':True},already_complete=[Q.task_stem(t) for t in MATRIX[:-1]])
            claim=q.claim('DW0001');q.finish('DW0001',claim['claim_id'],{'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':'c'*64,'output_hash':'d'*64});q.boundary_retire('DW0001')
            proof=Q.verify_journal(root);self.assertEqual((proof['complete'],proof['pending'],proof['active_claims']),(1200,0,{}))
            for path in root.rglob('*'):
                if path.is_file():S.terminal_file(path)

class OriginTests(unittest.TestCase):
    def guard(self):return types.SimpleNamespace(allowed_module_origin=lambda name,path,**k:name=='original',install_statistics_import_guard=lambda *a:{'numpy_and_stdlib_only':True})
    def test_additive_exact_origin(self):
        g=self.guard();path=HERE/'dynamic_sequence.py';h=S.sha(path);T.install_origin_extension(g,{str(path):h})
        self.assertTrue(g.allowed_module_origin('original',path,bound={}))
        self.assertTrue(g.allowed_module_origin('sidecar',path,bound={str(path).casefold():h}))
        self.assertFalse(g.allowed_module_origin('sidecar',path,bound={str(path).casefold():'0'*64}))
        self.assertFalse(g.allowed_module_origin('other',HERE/'controlled_quiesce.py',bound={}))
    def test_guard_proof_discloses_extension(self):
        g=self.guard();T.install_origin_extension(g,{})
        proof=g.install_statistics_import_guard({}, {}, None)
        self.assertFalse(proof['numpy_and_stdlib_only']);self.assertTrue(proof['numerical_dependencies_numpy_and_stdlib_only'])
        self.assertEqual(proof['metadata_origin_extension'],'ORIGINAL_STATISTICS_GUARD_PLUS_EXACT_DYNAMIC_DELIVERY_SIDECAR_SHA256')
    def test_arithmetic_entry_unchanged(self):
        # Configuration loads frozen source only; no run_statistics invocation.
        plan={'implementation_sha256':S.source_pins(),'record_root':str(HERE/'SYNTHETIC_NOT_CREATED')};qp=S.BASE/'replication_dynamic_scheduler_v1/queue_store.py'
        stats=T.configure(plan,{'sidecar_sources':{str(qp):S.sha(qp)}})
        self.assertEqual(Path(stats.__file__),S.BASE/'replication_statistics_batch20_env_v3/statistics.py')
        self.assertEqual(stats.run_statistics.__code__.co_filename,stats.__file__)
        for n in ('aggregate_rows','joint_center_tables','execution_cost_tables','original_comparison_tables'):
            self.assertEqual(getattr(stats,n).__code__.co_filename,stats.__file__)

class ActivationAndGateTests(unittest.TestCase):
    def test_activation_actual_api_and_owned_metadata_launch(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);directory=repo/'activation001';directory.mkdir();base=repo/'base'
            launch=base/'autonomous_replication_execution_20261009_v3/phase_launches/full_002/start.json';write(launch,{'synthetic':True})
            proof=repo/'proof.json';write(proof,{'synthetic':True});quiescence=directory/'quiescence/quiescence_complete.json';write(quiescence,{'synthetic':True})
            smoke=directory/'smoke.json';write(smoke,{'synthetic':True})
            gate=directory/'full_activation_gate.json';write(gate,{'delivery_route_certificate':{'path':str(proof),'sha256':S.sha(proof)},
                 'quiescence_certificate':{'path':str(quiescence),'sha256':S.sha(quiescence)},
                 'real_model_bridge_smoke_certificate':{'path':str(smoke),'sha256':S.sha(smoke)}})
            contract=directory/'full_contract.json';write(contract,{'activation_gate_path':str(gate),'activation_gate_sha256':S.sha(gate),'attempt_id':'A_DYNAMIC_0002'})
            activation={'files_sha256':{str(proof):S.sha(proof)}}
            with mock.patch.object(S,'BASE',base),mock.patch.object(S,'verify_proof'),mock.patch.object(S,'verify_plan'):
                ref=S.plan_for_activation(activation,directory,{'path':str(contract),'sha256':S.sha(contract)},{'path':str(smoke),'sha256':S.sha(smoke)})
                value=S.read(ref['path']);self.assertEqual(value['coordinator_start_path'],str(directory/'full_coordinator_start.json'))
                self.assertEqual(value['coordinator_exit_path'],str(directory/'full_coordinator_exit.json'))
                self.assertIn(str(launch),value['activation_evidence_sha256'])
                with mock.patch.object(S.subprocess,'Popen',return_value=types.SimpleNamespace(pid=4321)) as popen:
                    S.launch_owned_sequence(ref,directory)
                    self.assertEqual(popen.call_args.args[0],[S.METADATA_PYTHON,'-I','-S','-B',str(HERE/'dynamic_sequence.py'),'execute','--plan',ref['path']])
                self.assertEqual(S.read(directory/'delivery_sequence_launched.json')['pid'],4321)
    def test_full_history_preserves_unfinished_static_phase(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results=repo/'results';record=repo/'record';record.mkdir()
            req=results/'execution/full/A_FULL_0002/W1_request.json'
            write(req,{'manifest_digest':S.MANIFEST,'attempt_id':'A_FULL_0002','mode':'trajectory','performance_based_continuation':False,'tasks':MATRIX[5:]})
            certificate=record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json';write(certificate,{'schema':'paper3-dynamic-full-integrity-certificate-v1','status':'PASS',
                  'dynamic_attempt_id':'A_DYNAMIC_0002','evidence_sha256':{str(req):S.sha(req)},'retained_tasks':124,'completed_dynamic_tasks':1076})
            full=results/'full_experiment_integrity_gate.json';write(full,{'groups':{}})
            write(record/'FULL_GATE_PUBLICATION.json',{'certificate_sha256':S.sha(certificate),'sha256':S.sha(full)})
            path=repo/'plan.json';write(path,{});bindings={};p=types.SimpleNamespace(regular_path=lambda p:Path(p),file_sha256=S.sha)
            with mock.patch.object(S,'RESULTS',results):
                history=S.full_history({'_plan_path':str(path)},{'attempt_id':'A_DYNAMIC_0002'},p,bindings,{},MATRIX[5:],certificate)
            self.assertEqual(history['last_attempt_id'],'A_DYNAMIC_0002');self.assertTrue(history['phase_complete'])
            self.assertEqual(history['preserved_static_attempts'][0]['status'],'INTERRUPTED_BY_CERTIFIED_DYNAMIC_TAKEOVER')
            self.assertFalse(history['old_static_success_fabricated']);self.assertFalse((req.parent/'completion.json').exists())
            self.assertFalse((req.parent/'failure.json').exists());self.assertIn(str(certificate),bindings)
    def test_full_gate_truthful_original_schema_after_closure_only(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results=repo/'results';results.mkdir();record=repo/'record';record.mkdir();groups={str(i):{} for i in range(240)}
            proof={n:True for n in ('critical_scientific_bytes_unchanged','environment_file_bytes_checked','original_full_snapshot_checked','all_F1_inputs_checked')}
            p=types.SimpleNamespace(verify_frozen=lambda *a,**k:proof,publish_json=lambda root,relative,value:write(Path(root)/relative,value))
            terminal={'attempt_id':'A_DYNAMIC_0002','evidence_sha256':{},'retained_tasks':124,'completed_dynamic_tasks':1076,'groups':groups,
                      'retained_lineage':{'A_MINIMAL_0001':5,'A_FULL_0001':118,'A_DYNAMIC_0001':1}}
            with mock.patch.object(S,'RESULTS',results):S.publish_full_gate(p,{'paths':{'input_run':str(repo)}},terminal,record)
            self.assertEqual(S.read(results/'full_experiment_integrity_gate.json'),S.gate_value(groups))
            self.assertFalse(S.read(record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json')['static_phase_success_fabricated'])
            with mock.patch.object(S,'RESULTS',results),self.assertRaises(S.RouteError):S.publish_full_gate(p,{'paths':{'input_run':str(repo)}},terminal,record)

class ReportTests(unittest.TestCase):
    def fixtures(self,repo):
        results=repo/'results/p7_7_integrity_replication_batch20_env_v3';base=repo/'verification/paper3_canonical_inputs';bindings={}
        for phase in ('initial','minimal'):
            p=results/f'execution/{phase}/A_{phase.upper()}_0001/completion.json'
            write(p,{'manifest_digest':S.MANIFEST,'phase':phase,'attempt_id':p.parent.name,'start':'2026-01-01T00:00:00+00:00',
                     'finish':'2026-01-01T01:00:00+00:00','success':True,'worker_count':1});bindings[str(p)]=S.sha(p)
        p=results/'execution/full/A_FULL_0001/failure.json'
        write(p,{'manifest_digest':S.MANIFEST,'phase':'full','attempt_id':p.parent.name,'started':'2026-01-01T02:00:00+00:00',
                 'finished':'2026-01-01T03:00:00+00:00','original_driver_terminal_record':False,'external_observer':True,
                 'exit_code':None,'child_exit_code':None,'success':False});bindings[str(p)]=S.sha(p)
        p=base/'autonomous_replication_execution_20261009_v3/phase_launches/full_002/start.json'
        write(p,{'phase':'full','attempt':2,'workers':2,'started_utc':'2026-01-01T04:00:00+00:00'});bindings[str(p)]=S.sha(p)
        termination=repo/'termination.json';write(termination,{'schema':'paper3-intentional-cutover-native-termination-v1','all_twelve_old_owners_dead':True,
                 'normal_completion_claimed':False,'worker_exception_invented':False,'created_utc':'2026-01-01T05:00:00+00:00'})
        q=repo/'quiescence.json';write(q,{'termination_evidence':{'path':str(termination),'sha256':S.sha(termination)}})
        start,end=owner();sp=repo/'smoke_coordinator_start.json';write(sp,start);end['start_receipt_sha256']=S.sha(sp);ep=repo/'smoke_coordinator_exit.json';write(ep,end)
        bindings[str(sp)]=S.sha(sp);smoke=repo/'smoke.json';write(smoke,{'actual_coordinator_exit':{'path':str(ep),'sha256':S.sha(ep)},'contract':{'sha256':'a'*64}})
        full_end=repo/'full_exit.json';write(full_end,end)
        plan={'quiescence_path':str(q),'smoke_certificate_path':str(smoke),'coordinator_exit_path':str(full_end)}
        terminal={'coordinator_start':start,'coordinator_exit':end,'retained_tasks':200,'completed_dynamic_tasks':1000,
                  'retained_lineage':{'A_MINIMAL_0001':5,'A_FULL_0001':118,'A_FULL_0002':76,'A_DYNAMIC_0001':1}}
        return results,base,bindings,plan,terminal
    def test_phase_rows_real_original_markdown(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results,base,bindings,plan,terminal=self.fixtures(repo)
            api=module(S.BASE/'replication_delivery_env_v3/delivery.py','dynamic_test_phase_api');api._original_phase_artifact=api.phase_artifact
            with mock.patch.object(R.s,'BASE',base),mock.patch.object(R.s,'RESULTS',results),mock.patch.object(R.s,'process_active',lambda p:False):
                rows=R.phase_rows(api,results,bindings,S.MANIFEST,plan,{'attempt_id':'A_DYNAMIC_0002'},terminal)
            text=api.markdown_table(rows)
            self.assertIn('INTENTIONALLY_INTERRUPTED',text);self.assertIn('76',text);self.assertIn('1000',text)
            old=next(r for r in rows if r['attempt']=='A_FULL_0001')
            self.assertEqual(old['finish'],'NOT_VERIFIED');self.assertEqual(old['external_observation_cutoff'],'2026-01-01T03:00:00+00:00')
            self.assertFalse((results/'execution/full/A_FULL_0002/failure.json').exists())
            self.assertEqual({frozenset(x) for x in rows},{frozenset(rows[0])})
    def test_report_publisher_extra_source_inventory(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results=repo/D.RESULT_RELATIVE;stats=results/D.STATS_RELATIVE;stats.mkdir(parents=True)
            api=module(S.BASE/'replication_delivery_env_v3/delivery.py','dynamic_test_publish_api')
            source=repo/'synthetic.py';source.write_text('# synthetic\n');manifest,*_=F.objects()
            manifest.update(candidate_id='SYNTHETIC',input_protocol='SYNTHETIC',input_definition_digest='0'*64,input_dependency_digest='0'*64,
                stage_b_bindings={},input_files_sha256={},environment_binding={},environment={},critical_files_sha256={'synthetic.py':S.sha(source)},
                original_protected_snapshot={'synthetic.py':S.sha(source)},paths={'executor_root':str(repo/'NO_EXECUTOR')},executor_sha256={})
            core=[results/n for n in ('provenance_manifest.json','full_experiment_integrity_gate.json','initial_state_manifest.json')]
            core += [stats/n for n in ('statistics_manifest.json','statistics_execution_receipt.json')]
            for p in core:write(p,{})
            routeplan=repo/'plan.json';write(routeplan,{});proof=repo/'proof.json';write(proof,{})
            record=repo/'record';write(record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json',{});write(record/'FULL_GATE_PUBLICATION.json',{})
            plan={'route_proof_path':str(proof),'_plan_path':str(routeplan),'record_root':str(record)}
            terminal={'retained_tasks':124,'completed_dynamic_tasks':1076}
            R.configure(api,plan,{},terminal)
            bundle={'repo':repo,'results':results,'statistics_root':stats,'manifest':manifest,'tables':F.tables(),
                    'phases':[{'phase':'full','attempt':'A_DYNAMIC_0002','finish':'OWNED_SYNTHETIC'}],
                    'failed_attempts':{},'outputs':{},'statistics':{'outputs_sha256':{},'implementation_files_sha256':{}},
                    'read_proofs_sha256':{str(p):S.sha(p) for p in core},'binding_files':{},'raw_index':[{'path':'SYNTHETIC','sha256':'0'*64,'copied':False}]}
            api.audit_saved_evidence=lambda *a:bundle
            receipt=api.publish_delivery(repo,manifest['manifest_digest'],'handoffs/SYNTHETIC_DYNAMIC')
            package=Path(receipt['package_root']);inventory=receipt['package_files_sha256']
            for name in S.OWN:self.assertEqual(inventory['source/dynamic_delivery/'+name],S.sha(package/'source/dynamic_delivery'/name))
            self.assertIn('ADAPTATION_DECLARATION.json',' '.join(inventory))
            self.assertIn('No scheduling-invariant',(package/'EXECUTION_SUMMARY.md').read_text(encoding='utf-8'))
            for name in api.REPORT_NAMES:self.assertTrue((results/name).exists())
            self.assertFalse((repo/'PAPER3_FINAL_REPLICATION_HANDOFF.md').exists())
    def test_original_locked_publish_archives_and_zip(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);root=repo/FINAL.ROOT_NAME;root.write_bytes(b'synthetic old')
            draft=repo/'draft.md';draft.write_bytes(b'synthetic new');publication=repo/'publication';publication.mkdir()
            @contextlib.contextmanager
            def synthetic_lock(path):
                with Path(path).open('r+b') as f:yield f
            digest=FINAL.publish_root(repo,publication,FINAL.sha(root),draft,FINAL.sha(draft),lock=synthetic_lock)
            self.assertEqual((publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').read_bytes(),b'synthetic old')
            self.assertEqual(FINAL.sha(root),digest)
            zipped=repo/'synthetic.zip';self.assertEqual(FINAL.make_zip(publication,zipped),FINAL.sha(zipped))
    def test_original_root_changed_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);root=repo/FINAL.ROOT_NAME;root.write_bytes(b'changed');draft=repo/'draft';draft.write_bytes(b'new');publication=repo/'publication';publication.mkdir()
            @contextlib.contextmanager
            def lock(path):
                with Path(path).open('r+b') as f:yield f
            with self.assertRaises(FINAL.FinalizerError):FINAL.publish_root(repo,publication,'0'*64,draft,FINAL.sha(draft),lock=lock)
            self.assertEqual(root.read_bytes(),b'changed')

class FullTerminalTests(unittest.TestCase):
    def fixture(self,repo):
        """Full 1200 metadata matrix + genuine queue/bridge/backend producers."""
        results=repo/'results';results.mkdir();raw=results/'raw';raw.mkdir();records={};already={}
        for index,task in enumerate(MATRIX):
            name=Q.task_stem(task)
            attempt='A_MINIMAL_0001' if index<5 else 'A_FULL_0001' if index<123 else 'A_DYNAMIC_0001' if index==123 else 'A_FULL_0002' if index<1199 else 'A_DYNAMIC_0002'
            (raw/(name+'.csv')).write_text('SYNTHETIC_NO_OUTCOME\n',encoding='utf-8')
            write(raw/(name+'.integrity.json'),{'attempt_id':attempt,'task':task})
            records[name]={'task':task,'receipt':{'attempt_id':attempt}}
            if index<1199:already[name]=S.sha(raw/(name+'.integrity.json'))
        qp=S.BASE/'replication_dynamic_scheduler_v1/queue_store.py';proof=repo/'scheduler_proof.json';write(proof,{})
        gate=repo/'gate.json';write(gate,{'old_process_ids':list(range(50,62))})
        c={'manifest_digest':S.MANIFEST,'input_bundle_digest':S.F1,'execution_mode':'FULL','attempt_id':'A_DYNAMIC_0002',
           'run_relative':'execution/dynamic/A_DYNAMIC_0002','eligible_tasks':MATRIX,'already_complete':already,'retries':{},
           'sidecar_sources':{str(qp):S.sha(qp)},'sidecar_digest':'a'*64,'python_executable':'SYNTHETIC_FROZEN_PYTHON',
           'activation_gate_path':str(gate),'sourceproof_path':str(proof),'sourceproof_sha256':S.sha(proof)}
        cp=repo/'contract.json';write(cp,c);ch=S.sha(cp);run=results/c['run_relative']
        ledger=Q.QueueStore(run,MATRIX,{'manifest_digest':S.MANIFEST,'input_bundle_digest':S.F1,'sidecar_digest':c['sidecar_digest'],'contract_sha256':ch},already_complete=already)
        workerroot=run/'workers/DW0001';workerroot.mkdir(parents=True);wc={**c,'worker_id':'DW0001','worker_root':str(workerroot)}
        Q.exclusive_json(workerroot,'contract.json',wc);wh=S.sha(workerroot/'contract.json')
        bootstrap={'schema':'paper3-replication-worker-request-v1','mode':'trajectory','worker_count':3,'retries':{},'sidecar_digest':c['sidecar_digest'],
                   'tasks':MATRIX,'manifest_digest':S.MANIFEST,'worker_id':'DW0001','attempt_id':c['attempt_id'],
                   'dynamic_eligible_population_only':True,'performance_based_continuation':False}
        Q.exclusive_json(workerroot,'bootstrap_request.json',bootstrap)
        runtime=results/'runtime.json';write(runtime,{'SYNTHETIC':True})
        w=worker();ready={**w['ready'],'contract_sha256':wh,'bootstrap_request_sha256':S.sha(workerroot/'bootstrap_request.json'),
                         'runtime_receipt_path':'runtime.json','runtime_receipt_sha256':S.sha(runtime)}
        B.publish(workerroot,'ready.json',ready)
        launch={'pid':10,'contract_sha256':wh,'command':[c['python_executable'],'-I','-S','-B','-X',f'pycache_prefix={results/"_dynamic_never_pycache_DW0001"}',
                 str(S.BASE/'replication_dynamic_scheduler_v1/frozen_bridge.py'),'--contract',str(workerroot/'contract.json'),'--worker-id','DW0001','--worker-root',str(workerroot)]}
        Q.exclusive_json(workerroot,'launched.json',launch)
        backend=object.__new__(C.FrozenProcessBackend);backend.contract=c;proc=types.SimpleNamespace(pid=10,poll=lambda:None)
        backend.records={'DW0001':{'root':workerroot,'process':proc,'seq':0,'done':0,'ready':True,'actual_pid':11,'exit':False,'contract_sha256':wh,'log':io.StringIO()}}
        claim=ledger.claim('DW0001');backend.assign('DW0001',claim);name=Q.task_stem(claim['task'])
        receipt_sha=S.sha(raw/(name+'.integrity.json'));output_sha=S.sha(raw/(name+'.csv'))
        stream=B.TaskStream(workerroot,'DW0001',c,wh,lambda t:{'receipt_sha256':receipt_sha,'output_sha256':output_sha},pause=lambda x:None)
        next(stream);stream._acknowledge();backend.poll('DW0001')
        ledger.finish('DW0001',claim['claim_id'],{'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':receipt_sha,'output_hash':output_sha})
        backend.stop('DW0001')
        with self.assertRaises(StopIteration):next(stream)
        finish={**w['finish'],'contract_sha256':wh,'runtime_receipt_path':'runtime.json','runtime_receipt_sha256':S.sha(runtime)}
        B.publish(workerroot,'finished.json',finish);proc.poll=lambda:0;backend.poll('DW0001');ledger.boundary_retire('DW0001')
        Q.exclusive_json(run,'DYNAMIC_EXECUTION_COMPLETED.json',{'status':'DYNAMIC_TASKS_COMPLETED','completed':1200,'pairing':{'complete_paired_groups':240},
                    'scientific_integrity_pass':False,'statistics_executed':False,'original_pipeline_final_gate_still_required':True})
        start,end=owner();start['contract_sha256']=end['contract_sha256']=ch;start['contract_path']=str(cp)
        start['command']=[S.METADATA_PYTHON,'-I','-S','-B',str(S.BASE/'replication_dynamic_scheduler_v1/coordinator.py'),'--contract',str(cp)]
        sp=repo/'coordinator_start.json';write(sp,start);end['start_receipt_sha256']=S.sha(sp);ep=repo/'coordinator_exit.json';write(ep,end)
        routeproof=repo/'routeproof.json';write(routeproof,{})
        native=repo/'termination.json';write(native,{'schema':'paper3-intentional-cutover-native-termination-v1','all_twelve_old_owners_dead':True,
             'normal_completion_claimed':False,'worker_exception_invented':False,'outcomes':[{'pid':pid,'observed_dead':True,'exit_code':7} for pid in range(50,62)]})
        quiescence=repo/'quiescence.json';write(quiescence,{'schema':'paper3-controlled-quiescence-result-v1','status':'OLD_OWNERS_INTENTIONALLY_QUIESCED',
             'statistics_executed':False,'scientific_integrity_pass':False,'completed_count':1198,'termination_evidence':{'path':str(native),'sha256':S.sha(native)}})
        smoke_start,smoke_end=owner();ss=repo/'smoke_coordinator_start.json';write(ss,smoke_start);smoke_end['start_receipt_sha256']=S.sha(ss)
        se=repo/'smoke_coordinator_exit.json';write(se,smoke_end);smoke_name=Q.task_stem(MATRIX[123]);smoke=repo/'smoke.json'
        write(smoke,{'schema':'paper3-dynamic-real-model-bridge-smoke-v1','status':'PASS','actual_model_execution':True,
             'all_24_stage_f1_initial_deployment_and_causal_fields_verified':True,'frozen_algorithm_modified':False,'model_worker_bitwise_invariance_claimed':False,
             'actual_coordinator_exit':{'path':str(se),'sha256':S.sha(se)},'contract':{'sha256':'a'*64},'task':MATRIX[123],
             'completion_proof':{'validated':True,'receipt_sha256':already[smoke_name],'output_hash':S.sha(raw/(smoke_name+'.csv'))}})
        plan={'contract_path':str(cp),'contract_sha256':ch,'coordinator_start_path':str(sp),'coordinator_exit_path':str(ep),
              'route_proof_path':str(routeproof),'activation_evidence_sha256':{str(gate):S.sha(gate)},
              'quiescence_path':str(quiescence),'quiescence_sha256':S.sha(quiescence),'smoke_certificate_path':str(smoke),'smoke_certificate_sha256':S.sha(smoke)}
        driver=types.SimpleNamespace(tasks=lambda:MATRIX,stem=Q.task_stem,accepted_records=lambda *a,**k:records,paired_groups=lambda r:{str(i):{} for i in range(240)})
        return results,plan,c,driver,run
    def call(self,results,plan,c,driver):
        sys.modules.pop('paper3_dynamic_route_queue',None)
        with mock.patch.object(S,'RESULTS',results):return S.verify_dynamic_terminal(plan,c,driver,{},active=lambda p:False)
    def test_complete_actual_schema_full_route(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            results,plan,c,d,run=self.fixture(Path(temp));terminal=self.call(results,plan,c,d)
            self.assertEqual((terminal['retained_tasks'],terminal['completed_dynamic_tasks'],terminal['worker_count']),(1199,1,1))
            self.assertTrue(any('.pending_' in n for n in terminal['evidence_sha256']))
            self.assertEqual(terminal['retained_lineage']['A_FULL_0002'],1075)
    def test_marker_not_substitute_for_worker_actual_exit(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            results,plan,c,d,run=self.fixture(Path(temp));p=run/'workers/DW0001/actual_exit.json';v=S.read(p);v['actual_exit_code']=7;write(p,v)
            with self.assertRaises(S.RouteError):self.call(results,plan,c,d)
    def test_retained_receipt_change_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            results,plan,c,d,run=self.fixture(Path(temp));write(results/'raw'/f'{Q.task_stem(MATRIX[0])}.integrity.json',{'changed':True})
            with self.assertRaises(S.RouteError):self.call(results,plan,c,d)
    def test_complete_marker_does_not_hide_stopped_queue(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            results,plan,c,d,run=self.fixture(Path(temp));events=sorted((run/'journal').glob('*.json'));last=Q.read_json(events[-1]);index=len(events)+1
            Q.exclusive_json(run,f'journal/{index:06d}.json',{'schema':'paper3-dynamic-queue-event-v1','sequence':index,'previous_sha256':Q.sha(events[-1]),
               'action':'STOPPED','utc':Q.utc(),'bindings':last['bindings'],'body':{'claims_not_requeued':{},'new_random_draw_retry':False,'reason':'synthetic'}})
            with self.assertRaises(S.RouteError):self.call(results,plan,c,d)
    def test_worker_stop_reason_required(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            results,plan,c,d,run=self.fixture(Path(temp));p=run/'workers/DW0001/commands/000002.json';v=S.read(p);v.pop('reason');write(p,v)
            with self.assertRaises(S.RouteError):self.call(results,plan,c,d)

if __name__=='__main__':unittest.main(verbosity=2)
