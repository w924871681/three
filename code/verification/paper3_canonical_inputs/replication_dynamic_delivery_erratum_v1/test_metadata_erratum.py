"""Synthetic metadata only: real publishers/queue/backend with fake Popen."""
import contextlib
import copy
import importlib.util
import io
import hashlib
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
import metadata_erratum as E
import erratum_watch as W
import coordinator as C
import queue_store as Q
import frozen_bridge as B
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
F=load(E.BASE/'replication_abrupt_recovery_v1/finalizer.py','erratum_tests_finalizer')
D=load(E.BASE/'replication_delivery_env_v3/delivery.py','erratum_tests_delivery')
FIX=load(E.BASE/'replication_delivery_env_v3/test_delivery.py','erratum_tests_saved_fixtures')
def write(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value),encoding='utf-8');return str(p)
TASK={'center_id':33005,'seed':7312,'scenario':'C3','method':'B1','config_id':'B1_AlwaysMaintainP50_ratio10'}
def fixture(root,extra=None):
    c={'execution_mode':'BRIDGE_SMOKE','attempt_id':'A_DYNAMIC_0001','eligible_tasks':[TASK],**(extra or {})};ch=hashlib.sha256(json.dumps(c).encode()).hexdigest()
    bindings={'manifest_digest':c['manifest_digest'],'input_bundle_digest':c['input_bundle_digest'],'sidecar_digest':c['sidecar_digest'],'contract_sha256':ch} if extra else {'contract_sha256':ch,'synthetic':True}
    ledger=Q.QueueStore(root,[TASK],bindings);claim=ledger.claim('DW0001')
    for i,n in enumerate(('DW0001','DW0002'),1):
        directory=root/'workers'/n;directory.mkdir(parents=True);wc={**c,'worker_id':n,'worker_root':str(directory)}
        Q.exclusive_json(directory,'contract.json',wc);h=E.sha(directory/'contract.json');pid=100+i;model=200+i
        Q.exclusive_json(directory,'launched.json',{'pid':pid,'utc':'2026-01-01T00:00:00+00:00','contract_sha256':h})
        B.publish(directory,'ready.json',{'schema':'paper3-dynamic-worker-ready-v1','pid':model,'worker_id':n,'execution_mode':'BRIDGE_SMOKE','contract_sha256':h})
        process=types.SimpleNamespace(pid=pid,poll=lambda:None);backend=object.__new__(C.FrozenProcessBackend);backend.contract=c
        backend.records={n:{'root':directory,'process':process,'seq':0,'done':0,'ready':True,'actual_pid':model,'exit':False,'contract_sha256':h,'log':io.StringIO()}}
        stream=B.TaskStream(directory,n,c,h,lambda t:{'receipt_sha256':'c'*64,'output_sha256':'d'*64},pause=lambda x:None)
        if i==1:
            backend.assign(n,claim);next(stream)
            try:next(stream)
            except StopIteration:pass
            backend.poll(n);ledger.finish(n,claim['claim_id'],{'validated':True,'task_digest':claim['task_digest'],'receipt_sha256':'c'*64,'output_hash':'d'*64})
        else:
            backend.stop(n)
            try:next(stream)
            except StopIteration:pass
            ledger.boundary_retire(n)
        B.publish(directory,'finished.json',{'schema':'paper3-dynamic-worker-finished-v1','pid':model,'worker_id':n,'execution_mode':'BRIDGE_SMOKE',
            'contract_sha256':h,'finished_utc':'2026-01-01T01:00:00+00:00','summary':{'assigned_tasks':1 if i==1 else 0,'completed_tasks':1 if i==1 else 0,'skipped_valid_tasks':0},
            'original_trajectories_returned_after_full_checks':True,'new_manual_seed_introduced':False,'scientific_algorithm_modified':False,
            'model_output_worker_invariance_claimed':False,'statistics_executed':False})
        process.poll=lambda:0;backend.poll(n)
    return c,ch
def report(name):
    table=D.markdown_table([{'phase':'full','attempt':E.SMOKE_ATTEMPT,'start':'time','finish':'time','worker_count':1,'success':True}])
    return ('# SYNTHETIC\n\n'+(table if name in ('EXECUTION_SUMMARY.md',E.DRAFT) else '')+'Saved observed number -1.2345 and CI [-9.5, 6.25].\n').encode()

class CorrectionTests(unittest.TestCase):
    def test_exact_phase_cell_only(self):
        original=report('EXECUTION_SUMMARY.md');out,proof=E.correct_report(original,'EXECUTION_SUMMARY.md')
        self.assertIn(E.CORRECTED_COUNT.encode(),out);self.assertEqual(proof['smoke_cells_changed'],1)
        self.assertIn(b'-1.2345',out);self.assertIn(b'[-9.5, 6.25]',out);self.assertTrue(proof['all_other_report_bytes_preserved'])
        self.assertEqual(out[:-len(E.NOTE.encode())].replace(E.CORRECTED_COUNT.encode(),b'1'),original)
    def test_all_six_and_draft(self):
        for name in (*E.REPORTS,E.DRAFT):
            out,proof=E.correct_report(report(name),name);self.assertTrue(out.endswith(E.NOTE.encode()))
            self.assertEqual(proof['smoke_cells_changed'],int(name in ('EXECUTION_SUMMARY.md',E.DRAFT)))
    def test_missing_smoke_row_rejected(self):
        with self.assertRaises(E.ErratumError):E.correct_report(b'no smoke row\n','EXECUTION_SUMMARY.md')
    def test_duplicate_smoke_row_rejected(self):
        v=report(E.DRAFT);v+=next(x for x in v.splitlines(keepends=True) if E.SMOKE_ATTEMPT.encode() in x)
        with self.assertRaises(E.ErratumError):E.correct_report(v,E.DRAFT)
    def test_unexpected_old_count_rejected(self):
        v=report(E.DRAFT).replace(b'| 1 |',b'| 2 |')
        with self.assertRaises(E.ErratumError):E.correct_report(v,E.DRAFT)
    def test_wrong_report_phase_table_rejected(self):
        with self.assertRaises(E.ErratumError):E.correct_report(report(E.DRAFT),'INPUT_PARITY_AUDIT.md')
    def test_crlf_bytes_preserved(self):
        original=report(E.DRAFT).replace(b'\n',b'\r\n');out,_=E.correct_report(original,E.DRAFT)
        self.assertEqual(out[:-len(E.NOTE.encode())].replace(E.CORRECTED_COUNT.encode(),b'1'),original)
    def test_unrelated_ones_unchanged(self):
        v=report(E.DRAFT)+b'worker 1; experiment 1200; groups 240; bootstrap 4000; seed 2904.\n';out,_=E.correct_report(v,E.DRAFT)
        self.assertIn(b'worker 1; experiment 1200; groups 240; bootstrap 4000; seed 2904.',out)
    def test_corrected_file_index_actual_absolute_paths(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            current=Path(temp)/'corrected_reports';out,proof=E.correct_report(report(E.DRAFT),E.DRAFT,current)
            for name in E.REPORTS:self.assertIn(str(current/name).encode(),out);self.assertIn((current/name).as_posix().encode(),out)
            self.assertEqual(proof['corrected_report_entry_paths'],[str(current/name) for name in E.REPORTS])

class SmokeTests(unittest.TestCase):
    def run_fixture(self,mutate=None):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp)/'smoke';c,ch=fixture(root)
            if mutate:mutate(root,c)
            Q.verify_journal(root)
            return E.inspect_smoke(root,c,ch,active=lambda p:False)
    def test_actual_two_producer_workers_one_task(self):
        v=self.run_fixture();self.assertEqual((v['started_workers'],v['trajectory_workers'],v['trajectory_tasks']),(2,1,1))
        self.assertEqual([x['trajectory_claims'] for x in v['workers']],[1,0]);self.assertTrue(any('.pending_' in n for n in v['evidence_sha256']))
    def change(self,root,relative,key,value):
        path=root/relative;v=E.read(path);v[key]=value;write(path,v)
    def test_dw2_finish_absent(self):
        with self.assertRaises(FileNotFoundError):self.run_fixture(lambda r,c:(r/'workers/DW0002/finished.json').unlink())
    def test_dw2_actual_exit_absent(self):
        with self.assertRaises(FileNotFoundError):self.run_fixture(lambda r,c:(r/'workers/DW0002/actual_exit.json').unlink())
    def test_dw2_nonzero_exit(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/actual_exit.json','actual_exit_code',7))
    def test_bool_exit_rejected(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/actual_exit.json','actual_exit_code',False))
    def test_dw2_finished_not_validated(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/actual_exit.json','finished_validated',False))
    def test_dw2_exit_external_observer_rejected(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/actual_exit.json','producer','EXTERNAL_OBSERVER'))
    def test_dw2_model_pid_mismatch(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/actual_exit.json','actual_model_pid',999))
    def test_dw2_nonzero_claim_summary(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/finished.json','summary',{'assigned_tasks':1,'completed_tasks':1}))
    def test_dw2_stop_reason_mismatch(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0002/commands/000001.json','reason','unknown'))
    def test_live_idle_worker_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp)/'smoke';c,ch=fixture(root)
            with self.assertRaises(E.ErratumError):E.inspect_smoke(root,c,ch,active=lambda pid:pid==102)
    def test_unknown_worker_rejected(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:(r/'workers/DW0003').mkdir())
    def test_worker_seed_change_rejected(self):
        with self.assertRaises(E.ErratumError):self.run_fixture(lambda r,c:self.change(r,'workers/DW0001/finished.json','new_manual_seed_introduced',True))
    def test_pending_unpublished_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/('x.json.pending_'+'f'*32);p.write_text('{}')
            with self.assertRaises(E.ErratumError):E.publication_file(p)
    def test_pending_copy_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'x.json';p.write_text('{}');other=p.with_name(p.name+'.pending_'+'f'*32);other.write_text('{}')
            with self.assertRaises(E.ErratumError):E.publication_file(other)

class SourceAndArchiveTests(unittest.TestCase):
    def test_original_and_v1_bytes_unchanged(self):
        for name,h in E.V1_PINS.items():self.assertEqual(E.sha(E.V1/name),h)
        self.assertEqual(E.sha(E.BASE/'replication_abrupt_recovery_v1/finalizer.py'),E.ORIGINAL_FINALIZER)
        self.assertEqual(E.sha(E.BASE/'replication_delivery_env_v3/delivery.py'),E.ORIGINAL_DELIVERY)
    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'bad.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(E.ErratumError):E.read(p)
    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'bad.json';p.write_text('{"x":NaN}')
            with self.assertRaises(E.ErratumError):E.read(p)
    def test_path_escape_rejected(self):
        with self.assertRaises(E.ErratumError):E.safe(E.REPO.parent/'outside')
    def test_exclusive_record(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            p=Path(temp)/'record.json';E.emit(p,{'x':1})
            with self.assertRaises(FileExistsError):E.emit(p,{'x':2})
    def test_zip_payload_verification(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);p=root/'package';p.mkdir();(p/'stats.csv').write_bytes(b'unchanged statistical bytes\n')
            zipped=root/'old.zip';F.make_zip(p,zipped);E.verify_zip(zipped,F.inventory(p))
            with self.assertRaises(E.ErratumError):E.verify_zip(zipped,{'stats.csv':'0'*64})
    def test_root_expected_v1_hash_not_earliest_f50(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);old=root/F.ROOT_NAME;old.write_bytes(b'synthetic V1 draft');draft=root/'corrected';draft.write_bytes(b'synthetic corrected draft')
            publication=root/'publication';publication.mkdir();old_sha=F.sha(old)
            @contextlib.contextmanager
            def lock(path):
                with Path(path).open('r+b') as f:yield f
            F.publish_root(root,publication,old_sha,draft,F.sha(draft),lock=lock)
            self.assertEqual((publication/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').read_bytes(),b'synthetic V1 draft')
    def test_changed_v1_root_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            root=Path(temp);old=root/F.ROOT_NAME;old.write_bytes(b'changed');draft=root/'corrected';draft.write_bytes(b'new');publication=root/'publication';publication.mkdir()
            @contextlib.contextmanager
            def lock(path):
                with Path(path).open('r+b') as f:yield f
            with self.assertRaises(F.FinalizerError):F.publish_root(root,publication,'0'*64,draft,F.sha(draft),lock=lock)
            self.assertEqual(old.read_bytes(),b'changed')
    def test_complete_independent_repack_preserves_canonical_and_stats(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results=repo/'results';results.mkdir();handoffs=repo/'handoffs';handoffs.mkdir()
            original=handoffs/'v1_final';original.mkdir();reviewed=handoffs/'v1_reviewed';reviewed.mkdir();stats=original/'statistics/result.csv';stats.parent.mkdir();stats.write_bytes(b'mean,ci_low,ci_high\n-1.2345,-9.5,6.25\n')
            for name in (*E.REPORTS,E.DRAFT):(reviewed/name).write_bytes(report(name))
            (repo/F.ROOT_NAME).write_bytes(report(E.DRAFT));old_sha=F.sha(repo/F.ROOT_NAME);inventory=F.inventory(original);old_zip=handoffs/'v1.zip';old_zip_sha=F.make_zip(original,old_zip)
            smoke_root=results/'execution/dynamic/A_DYNAMIC_0001';c,ch=fixture(smoke_root);observed=E.inspect_smoke(smoke_root,c,ch,active=lambda pid:False)
            v1record=repo/'v1record';write(v1record/'start.json',{'pid':999});gate=repo/'gate.json';write(gate,{'old_process_ids':[1,2]})
            proof=repo/'proof.json';write(proof,{'synthetic':True});planfile=repo/'plan.json';write(planfile,{'synthetic':True})
            plan={'record_root':str(repo/'erratumrecord'),'target_relative':'handoffs/erratum','zip_relative':'handoffs/erratum.zip',
                  'proof_path':str(proof),'proof_sha256':F.sha(proof),'root_metadata_erratum_publication_authorized':True}
            v={'final_handoff_relative':'handoffs/v1_final','reviewed_handoff_relative':'handoffs/v1_reviewed','zip_relative':'handoffs/v1.zip','record_root':str(v1record)}
            evidence={'package_inventory':inventory,'delivery':{'package_files_sha256':{n:F.sha(reviewed/n) for n in (*E.REPORTS,E.DRAFT)}},
                'finish':{'result':{'zip_sha256':old_zip_sha}},'observed_smoke':observed,'expected_old_root_sha256':old_sha,
                'statistics_sha256':{str(stats):F.sha(stats)},'statistics_manifest_sha256':'a'*64,'statistics_receipt_sha256':'b'*64,
                'scientific_evidence_sha256':{str(stats):F.sha(stats)},'inactive_process_ids':[1,2,999],
                'v1_sequence_actual_exit_code':'NOT_VERIFIED'}
            original_publish=F.publish_root
            @contextlib.contextmanager
            def lock(path):
                with Path(path).open('r+b') as f:yield f
            def publish(*args,**kw):return original_publish(*args,lock=lock,**kw)
            canonical_before={n:(reviewed/n).read_bytes() for n in (*E.REPORTS,E.DRAFT)}
            with mock.patch.object(E,'REPO',repo),mock.patch.object(E,'RESULTS',results),mock.patch.object(E,'verify_plan',return_value=(plan,v,{'activation_gate_path':str(gate)})),\
                 mock.patch.object(E,'verify_completed',return_value=evidence),mock.patch.object(E,'process_active',lambda pid:False),\
                 mock.patch.object(E,'load',side_effect=[D,F]),mock.patch.object(F,'verify_delivery',return_value={}),mock.patch.object(F,'publish_root',side_effect=publish):
                result=E.execute(planfile,F.sha(planfile))
            target=repo/'handoffs/erratum';manifest=E.read(target/'ERRATUM_MANIFEST.json')
            self.assertEqual(result['status'],'SMOKE_COUNT_METADATA_ERRATUM_COMPLETED');self.assertTrue(manifest['statistics_bytes_unchanged'])
            self.assertEqual((target/'original_v1_final_package/statistics/result.csv').read_bytes(),stats.read_bytes())
            for n,data in canonical_before.items():self.assertEqual((reviewed/n).read_bytes(),data)
            self.assertEqual(F.sha(old_zip),old_zip_sha);self.assertEqual((target/'root_publication/PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').read_bytes(),report(E.DRAFT))
            self.assertIn(E.CORRECTED_COUNT.encode(),(repo/F.ROOT_NAME).read_bytes())
            for name in E.REPORTS:self.assertIn(str(target/'corrected_reports'/name).encode(),(repo/F.ROOT_NAME).read_bytes())
            F.verify_inventory(target,manifest['package_files_sha256'],('ERRATUM_MANIFEST.json','ERRATUM_MANIFEST.json.sha256'))
            E.verify_zip(repo/'handoffs/erratum.zip',F.inventory(target))

class NativeWatchTests(unittest.TestCase):
    class Backend:
        def __init__(self,identity,signals=(True,),code=0):self.value=identity;self.signals=list(signals);self.code=code;self.closed=False;self.opened=[];self.waits=[]
        def open(self,pid):self.opened.append(pid);return 'PINNED_HANDLE'
        def identity(self,handle,pid):assert handle=='PINNED_HANDLE';return self.value
        def wait(self,handle,milliseconds):assert handle=='PINNED_HANDLE';self.waits.append(milliseconds);return self.signals.pop(0)
        def exit_code(self,handle):assert handle=='PINNED_HANDLE';return self.code
        def close(self,handle):assert handle=='PINNED_HANDLE';self.closed=True
    def run_watch(self,root,backend, *, finish=True,stopped=False,source_change=False):
        sequence=root/'v1record';sequence.mkdir();record=root/'watchrecord';identity={'pid':W.V1_SEQUENCE_PID,'creation_filetime':123,'image':'SYNTHETIC','command_line':'SYNTHETIC'}
        if finish:write(sequence/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED'})
        if stopped:write(sequence/'stopped.json',{'status':'STOPPED_FOR_DIAGNOSIS'})
        plan={'watch_record_root':str(record),'expected_native_identity':identity,'v1_plan_path':'SYNTHETIC',
              'proof_path':'SYNTHETIC','proof_sha256':'a'*64,'target_relative':'handoffs/erratum','zip_relative':'handoffs/erratum.zip',
              'erratum_record_root':str(root/'erratumrecord'),'erratum_plan_path':str(root/'erratumplan.json')}
        v={'record_root':str(sequence),'contract_path':str(root/'fullcontract.json'),'contract_sha256':'b'*64};write(root/'fullcontract.json',{})
        gates={'expected_old_root_sha256':'c'*64,'statistics_manifest_sha256':'d'*64,'statistics_receipt_sha256':'e'*64,
               'statistics_sha256':{},'observed_smoke':{},'scientific_evidence_sha256':{}}
        events=[]
        def verify(*args):
            events.append('source')
            if source_change and len(events)>1:raise E.ErratumError('synthetic source changed')
            return plan,v
        def complete(*args,**kw):events.append('all_completion_gates');return gates
        def create(*args,**kw):events.append('create_real_plan');return {'path':'SYNTHETIC','sha256':'f'*64}
        def execute(*args):events.append('metadata_execute');return {'status':'COMPLETED'}
        with mock.patch.object(W,'verify_watch_plan',side_effect=verify),mock.patch.object(W.e,'load',return_value=object()),\
             mock.patch.object(W.e,'bound',side_effect=lambda p,h:Path(p)),mock.patch.object(W.e,'verify_completed',side_effect=complete),\
             mock.patch.object(W.e,'create_plan',side_effect=create),mock.patch.object(W.e,'execute',side_effect=execute):
            result=W.run(root/'watchplan.json','0'*64,observer=backend,pause=lambda seconds:None)
        return result,events,record
    def test_successful_wait_precedes_plan_and_metadata_only_execute(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            identity={'pid':W.V1_SEQUENCE_PID,'creation_filetime':123,'image':'SYNTHETIC','command_line':'SYNTHETIC'}
            backend=self.Backend(identity,signals=(False,True));result,events,record=self.run_watch(Path(temp),backend)
            self.assertTrue(backend.closed);self.assertEqual(backend.opened,[15508]);self.assertEqual(backend.waits,[15000,15000])
            self.assertLess(events.index('all_completion_gates'),events.index('create_real_plan'));self.assertLess(events.index('create_real_plan'),events.index('metadata_execute'))
            obs=E.read(record/'V1_SEQUENCE_NATIVE_EXIT.json');self.assertEqual(obs['actual_exit_code'],0);self.assertFalse(obs['owning_popen_exit_claimed'])
    def reject(self,**options):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            identity=options.pop('identity',{'pid':W.V1_SEQUENCE_PID,'creation_filetime':123,'image':'SYNTHETIC','command_line':'SYNTHETIC'})
            backend=self.Backend(identity,code=options.pop('code',0))
            with self.assertRaises((E.ErratumError,W.e.ErratumError)):self.run_watch(Path(temp),backend,**options)
            self.assertTrue(backend.closed);stopped=E.read(Path(temp)/'watchrecord/stopped.json');self.assertFalse(stopped['automatic_retry'])
            self.assertFalse((Path(temp)/'erratumplan.json').exists())
    def test_nonzero_native_exit_stops_without_retry(self):self.reject(code=7)
    def test_exit_259_after_signal_is_not_inferred_live_or_zero(self):self.reject(code=259)
    def test_bool_native_exit_rejected(self):self.reject(code=False)
    def test_missing_legal_finish_stops(self):self.reject(finish=False)
    def test_old_sequence_stopped_stops(self):self.reject(stopped=True)
    def test_creation_filetime_mismatch_stops(self):self.reject(identity={'pid':15508,'creation_filetime':124,'image':'SYNTHETIC','command_line':'SYNTHETIC'})
    def test_pid_mismatch_stops(self):self.reject(identity={'pid':15509,'creation_filetime':123,'image':'SYNTHETIC','command_line':'SYNTHETIC'})
    def test_command_mismatch_stops(self):self.reject(identity={'pid':15508,'creation_filetime':123,'image':'SYNTHETIC','command_line':'OTHER'})
    def test_source_change_stops(self):self.reject(source_change=True)
    def test_native_wait_is_bounded_and_query_only(self):
        observer=object.__new__(W.NativeObserver);calls=[]
        observer.k=types.SimpleNamespace(OpenProcess=lambda access,inherit,pid:calls.append(access) or 17,WaitForSingleObject=lambda h,ms:0x102)
        self.assertEqual(observer.open(15508),17);self.assertEqual(calls,[0x101000]);self.assertFalse(observer.wait(17,15000))
        with self.assertRaises(W.e.ErratumError):observer.wait(17,15001)

class CompletedContractTests(unittest.TestCase):
    def test_nonzero_statistics_rejected_before_delivery(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            record=Path(temp);write(record/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED'})
            write(record/'start.json',{'pid':9,'plan_sha256':'a'*64});write(record/'STATISTICS_PROCESS_EXIT.json',{'actual_exit_code':7,'automatic_retry':False})
            with self.assertRaises(E.ErratumError):E.verify_completed({'v1_plan_sha256':'a'*64},{'record_root':str(record)},{},None,None,active=lambda p:False)
    def test_live_v1_owner_rejected_before_delivery(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            record=Path(temp);write(record/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED'});write(record/'start.json',{'pid':9})
            with self.assertRaises(E.ErratumError):E.verify_completed({}, {'record_root':str(record)},{},None,None,active=lambda p:True)
    def test_complete_saved_contract_real_validators(self):
        """All verifier branches with synthetic saved contracts, no gate mocks."""
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            repo=Path(temp);results=repo/F.RESULT_REL;results.mkdir(parents=True);record=repo/'v1record';record.mkdir()
            manifest,gate,initial,stats,receipt,_=FIX.objects();protected=repo/'protected';protected.mkdir();payload=repo/'synthetic_protected';payload.write_bytes(b'SYNTHETIC_PROTECTED')
            for i in range(2535):(protected/str(i)).write_bytes(payload.read_bytes())
            manifest['original_protected_snapshot']={f'protected/{i}':E.sha(payload) for i in range(2535)}
            source=repo/'synthetic_source.py';source.write_text('# synthetic\n');manifest['critical_files_sha256']={'synthetic_source.py':E.sha(source)}
            manifest.pop('manifest_digest');digest=D.canonical_hash(manifest);manifest['manifest_digest']=digest
            gate['manifest_digest']=initial['manifest_digest']=stats['replication_manifest_digest']=receipt['replication_manifest_digest']=digest
            for name,value in [('provenance_manifest.json',manifest),('full_experiment_integrity_gate.json',gate),('initial_state_manifest.json',initial)]:write(results/name,value)
            statsroot=results/'statistics_batch20_env_v3';statsroot.mkdir();tables=FIX.tables()
            for name,rows in tables.items():(statsroot/name).write_bytes(D.csv_bytes(rows))
            stats['outputs_sha256']={name:E.sha(statsroot/name) for name in tables};receipt['outputs_sha256']=stats['outputs_sha256']
            stats['input_bindings_sha256']={str(results/n):E.sha(results/n) for n in ('provenance_manifest.json','full_experiment_integrity_gate.json','initial_state_manifest.json')}
            write(statsroot/'statistics_manifest.json',stats);receipt['statistics_manifest_sha256']=E.sha(statsroot/'statistics_manifest.json');write(statsroot/'statistics_execution_receipt.json',receipt)
            write(record/'start.json',{'pid':9,'plan_sha256':'a'*64});write(record/'STATISTICS_PROCESS_EXIT.json',{'actual_exit_code':0,'automatic_retry':False})
            cert=record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json';write(cert,{'status':'PASS','manifest_digest':digest,'trajectories':1200,'paired_groups':240,'static_phase_success_fabricated':False,'evidence_sha256':{}})
            write(record/'FULL_GATE_PUBLICATION.json',{'certificate_sha256':E.sha(cert),'sha256':E.sha(results/'full_experiment_integrity_gate.json')})
            coordinator=repo/'full_exit.json';write(coordinator,{'pid':10,'actual_exit_code':0})
            fullrun='execution/dynamic/A_DYNAMIC_0002';fullworker=results/fullrun/'workers/DW0001';fullworker.mkdir(parents=True)
            write(fullworker/'finished.json',{'pid':12,'contract_sha256':'b'*64});write(fullworker/'actual_exit.json',{'pid':11,'actual_model_pid':12,'actual_exit_code':0,
                'finished_validated':True,'producer':'OWNING_FROZEN_PROCESS_BACKEND','contract_sha256':'b'*64})
            activation=repo/'gate.json';write(activation,{'old_process_ids':list(range(50,62))});sources=E.scheduler_pins()
            full={'run_relative':fullrun,'activation_gate_path':str(activation),'sidecar_sources':sources}
            smokerun='execution/dynamic/A_DYNAMIC_0001';smoke_root=results/smokerun;c,ch=fixture(smoke_root,extra={'manifest_digest':digest,'input_bundle_digest':E.F1,
                 'sidecar_sources':sources,'sidecar_digest':E.canonical(sources),'run_relative':smokerun})
            contract=repo/'smoke_contract.json';write(contract,c);self.assertEqual(E.sha(contract),ch)
            ss=repo/'smoke_coordinator_start.json';write(ss,{'schema':'paper3-dynamic-owned-coordinator-start-v1','pid':13,'contract_sha256':ch})
            se=repo/'smoke_coordinator_exit.json';write(se,{'schema':'paper3-dynamic-owned-coordinator-exit-v1','pid':13,'contract_sha256':ch,
                 'start_receipt_sha256':E.sha(ss),'actual_exit_code':0,'automatic_retry':False})
            smoke=repo/'smoke_certificate.json';write(smoke,{'schema':'paper3-dynamic-real-model-bridge-smoke-v1','status':'PASS','actual_model_execution':True,
                 'frozen_algorithm_modified':False,'model_worker_bitwise_invariance_claimed':False,'all_24_stage_f1_initial_deployment_and_causal_fields_verified':True,
                 'contract':{'path':str(contract),'sha256':ch},'task':TASK,'actual_coordinator_exit':{'path':str(se),'sha256':E.sha(se)}})
            reviewed=repo/'handoffs/reviewed';reviewed.mkdir(parents=True)
            for name in (*E.REPORTS,E.DRAFT):(reviewed/name).write_bytes(report(name));(results/name).write_bytes(report(name))
            delivery={'schema':'paper3-saved-results-delivery-v1','status':'COMPLETED','replication_manifest_digest':digest,'package_root':str(reviewed),
                 'root_handoff_modified':False,'original_protected_files_unchanged':2535,'package_files_sha256':F.inventory(reviewed),
                 'results_report_files_sha256':{str(results/n):E.sha(results/n) for n in (*E.REPORTS,E.DRAFT)}}
            for directory in (reviewed,results):
                write(directory/'DELIVERY_MANIFEST.json',delivery);(directory/'DELIVERY_MANIFEST.json.sha256').write_text(E.sha(directory/'DELIVERY_MANIFEST.json')+'  DELIVERY_MANIFEST.json\n')
            package=repo/'handoffs/final';package.mkdir()
            for n,h in F.inventory(reviewed).items():F.copy_verified(reviewed/n,package/'reviewed_delivery'/n,h)
            pub=package/'root_publication';pub.mkdir();(pub/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md').write_bytes(b'SYNTHETIC_F50')
            fake_f50=E.sha(pub/'PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md');draft_sha=E.sha(reviewed/E.DRAFT)
            write(pub/'PUBLICATION_RECEIPT.json',{'status':'PUBLISHED_VERIFIED_SAVED_DRAFT','previous_sha256':fake_f50,'new_sha256':draft_sha,'all_prior_bytes_archived':True})
            (repo/F.ROOT_NAME).write_bytes(report(E.DRAFT))
            pm={'schema':'paper3-dynamic-final-package-v1','status':'COMPLETED','previous_root_handoff_sha256':fake_f50,'manifest_digest':digest,
                'root_handoff_sha256':draft_sha,'package_files_sha256':F.inventory(package)};write(package/'FINAL_PACKAGE_MANIFEST.json',pm)
            zipped=repo/'handoffs/final.zip';zip_sha=F.make_zip(package,zipped)
            result={'reviewed_package':str(reviewed),'final_package':str(package),'zip_path':str(zipped),'zip_sha256':zip_sha,
                    'root_handoff_sha256':draft_sha,'previous_root_handoff_sha256':fake_f50}
            write(record/'finish.json',{'status':'DYNAMIC_STATISTICS_DELIVERY_COMPLETED','result':result})
            v={'record_root':str(record),'coordinator_exit_path':str(coordinator),'reviewed_handoff_relative':'handoffs/reviewed','final_handoff_relative':'handoffs/final',
               'zip_relative':'handoffs/final.zip','smoke_certificate_path':str(smoke),'smoke_certificate_sha256':E.sha(smoke)}
            with mock.patch.object(E,'REPO',repo),mock.patch.object(E,'RESULTS',results),mock.patch.object(E,'MANIFEST',digest),mock.patch.object(E,'F50',fake_f50),mock.patch.object(F,'MANIFEST',digest):
                verified=E.verify_completed({'v1_plan_sha256':'a'*64},v,full,D,F,active=lambda p:False,queue_name='erratum_complete_contract_queue_fixture')
            self.assertEqual(verified['observed_smoke']['started_workers'],2);self.assertEqual(verified['expected_old_root_sha256'],draft_sha)
            self.assertEqual(verified['statistics_sha256'],{str(statsroot/n):h for n,h in stats['outputs_sha256'].items()})

if __name__=='__main__':unittest.main(verbosity=2)
