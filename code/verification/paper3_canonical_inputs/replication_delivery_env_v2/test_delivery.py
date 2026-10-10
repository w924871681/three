"""Independent synthetic contracts only; never read Paper3 real outcomes."""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock
import types

SOURCE = pathlib.Path(__file__).resolve().parent/'delivery.py'
SPEC = importlib.util.spec_from_file_location('paper3_synthetic_delivery',SOURCE)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)

def objects():
    manifest = {'input_bundle_digest':D.F1_DIGEST,'historical_environment_reproduced':False,
        'original_records_mixed_into_new_results':False,'model_environment_id':'P7_7_REPLICATION_MODEL_ENV_V1',
        'original_protected_snapshot':{f'protected/{i}':'0'*64 for i in range(2535)},
        'original_start_check':{'all_original_bytes_unchanged':True},'critical_files_sha256':{'synthetic_source.py':'0'*64}}
    digest = D.canonical_hash(manifest)
    manifest['manifest_digest'] = digest
    groups = {f'{c}/{seed}/{s}':{'five_methods':True,'all_24_stage_input_fields_equal':True,
        'receipt_sha256':{m:'0'*64 for m in D.METHODS}} for c in range(33000,33020) for seed in (7311,7312,7313) for s in D.SCENARIOS}
    gate = {'scientific_integrity_pass':True,'manifest_digest':digest,'trajectories':1200,'paired_groups':240,
        'old_results_reused':False,'all_inputs_F1':True,'future_flags_false':True,'outcomes_used_to_select_protocol':False,
        'not_unseen_heldout':True,'groups':groups}
    initial = {'manifest_digest':digest,'states':[{'center_id':c,'seed':s} for c in range(33000,33020) for s in (7311,7312,7313)]}
    protocol = {'resampling_unit':'center','centers':list(range(33000,33020)),
        'bootstrap_resamples':4000,'bootstrap_seed':2904,'one_joint_index_matrix_for_all_methods_contrasts_scenarios':True,
        'observed_point_estimates_from_original_center_means':True,'new_unseen_heldout_claimed':False,
        'no_outcome_based_selection':True,'no_original_records_reused':True,'no_exclusions':True,'winner_ranking':False}
    statistics = {'replication_manifest_digest':digest,'input_bundle_digest':D.F1_DIGEST,'counts':D.EXPECTED_COUNTS.copy(),
        'protocol':protocol,'outputs_sha256':{name:'0'*64 for name in D.SUMMARY_NAMES}}
    receipt = {'schema':'paper3-statistics-execution-receipt-v1','status':'COMPLETED','exit_code':0,
        'replication_manifest_digest':digest,'originals_unchanged':True,'joint_resampling_verified':True,
        'new_output_only':True,'models_or_generators_executed':False,'outputs_sha256':statistics['outputs_sha256'].copy()}
    return manifest,gate,initial,statistics,receipt,digest

def tables():
    fields = {'n_centers':'20','ci_low':'0.001','ci_high':'0.009','gate_open_rate':'0.333',
        'ri_rate':'0.02','maintenance_rate':'0.2','retain_rate':'0.78','total_action_cost':'0.0001'}
    methods = [{'method':m,'mean_lifecycle_service_loss':f'0.00{i+2}',**fields} for i,m in enumerate(D.METHODS)]
    scenarios = [{'method':m,'scenario':s,'lifecycle_service_loss':'0.004',**fields} for m in D.METHODS for s in D.SCENARIOS]
    contrast = [{'comparison':'P7.7 - '+m,'mean_difference':('-0.1' if i<2 else '0.1'),
        'ci_low':('-0.2' if i<3 else '0.01'),'ci_high':('0.2' if i>=1 else '-0.01'),
        'n_centers':'20','bootstrap_resamples':'4000','bootstrap_seed':'2904',
        'point_estimate_source':'OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION'} for i,m in enumerate(D.METHODS[:-1])]
    diagnostics = [{'metric':m,'count':'7','rate':'0.0012152777777777778','denominator':'5760'} for m in D.DIAGNOSTICS]
    return dict(zip(D.SUMMARY_NAMES,[methods,scenarios,contrast,diagnostics,
        [{'method':m,'actual_timer':'1.2','standalone_estimate':'2.4'} for m in D.METHODS],
        [{'method':m,'original_mixed_inventory_mean':'0.003','corrected_batch20_mean':'0.004','corrected_minus_original':'0.001'} for m in D.METHODS],
        [{'method':m,'scenario':s,'original_mixed_inventory_mean':'0.003','corrected_batch20_mean':'0.004','corrected_minus_original':'0.001'} for m in D.METHODS for s in D.SCENARIOS],
        [{'comparison':'P7.7 - '+m,'original_observed_method_mean_difference':'0.0','corrected_observed_method_mean_difference':'0.1'} for m in D.METHODS[:-1]]]))

class GateTests(unittest.TestCase):
    def test_complete_contract(self):
        self.assertTrue(D.validate_gate_objects(*objects()))
    def reject(self,index,key,value):
        data = list(objects())
        data[index][key] = value
        with self.assertRaises(D.DeliveryIntegrityError):
            D.validate_gate_objects(*data)
    def test_1200_required(self): self.reject(1,'trajectories',1199)
    def test_240_required(self): self.reject(1,'paired_groups',239)
    def test_group_fields_required(self):
        data = list(objects()); next(iter(data[1]['groups'].values()))['all_24_stage_input_fields_equal']=False
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_all_method_receipts(self):
        data = list(objects()); next(iter(data[1]['groups'].values()))['receipt_sha256'].pop('B8')
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_actual_group_ids(self):
        data=list(objects()); data[1]['groups']['WRONG']=data[1]['groups'].pop('33000/7311/C0')
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_statistics_pending_rejected(self): self.reject(4,'status','PENDING')
    def test_statistics_failed_rejected(self): self.reject(4,'exit_code',1)
    def test_initial_incomplete_rejected(self): self.reject(2,'states',[])
    def test_duplicate_initial_rejected(self):
        data=list(objects()); data[2]['states'][1]=data[2]['states'][0].copy()
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_old_reuse_rejected(self): self.reject(1,'old_results_reused',True)
    def test_future_flag_rejected(self): self.reject(1,'future_flags_false',False)
    def test_performance_selection_rejected(self): self.reject(1,'outcomes_used_to_select_protocol',True)
    def test_numeric_boolean_rejected(self): self.reject(1,'scientific_integrity_pass',1)
    def test_unseen_claim_rejected(self): self.reject(1,'not_unseen_heldout',False)
    def test_original_change_rejected(self): self.reject(4,'originals_unchanged',False)
    def test_joint_resampling_required(self): self.reject(4,'joint_resampling_verified',False)
    def test_model_execution_stats_rejected(self): self.reject(4,'models_or_generators_executed',True)
    def test_manifest_digest_rejected(self): self.reject(0,'manifest_digest','1'*64)
    def test_canonical_tamper_rejected(self): self.reject(0,'extra_unbound_field',True)
    def test_f1_required(self): self.reject(3,'input_bundle_digest','singleton')
    def test_fixed_bootstrap_seed(self):
        data=list(objects()); data[3]['protocol']['bootstrap_seed']=42
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_fixed_4000(self):
        data=list(objects()); data[3]['protocol']['bootstrap_resamples']=3999
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_no_exclusion(self):
        data=list(objects()); data[3]['protocol']['no_exclusions']=False
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)
    def test_output_inventory_agrees(self): self.reject(4,'outputs_sha256',{})
    def test_complete_saved_counts(self):
        data=list(objects()); data[3]['counts']['raw_trajectories']=1199
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_gate_objects(*data)

class TableTests(unittest.TestCase):
    def test_all_fields_verbatim(self):
        value=tables(); before=copy.deepcopy(value)
        self.assertIs(D.validate_saved_tables(value),value)
        self.assertEqual(value,before)
    def test_adverse_and_zero_crossing_retained(self):
        value=tables(); D.validate_saved_tables(value)
        table=D.markdown_table(value['final_paired_contrasts.csv'])
        self.assertIn('P7.7 - B8',table); self.assertIn('0.1',table); self.assertIn('-0.2',table)
    def test_missing_method(self):
        value=tables(); value['final_metrics_by_method.csv'].pop()
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_duplicate_scenario(self):
        value=tables(); value['final_metrics_by_scenario.csv'][1]=value['final_metrics_by_scenario.csv'][0]
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_nonfinite_endpoint(self):
        value=tables(); value['final_metrics_by_method.csv'][0]['mean_lifecycle_service_loss']='NaN'
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_inverted_interval(self):
        value=tables(); value['final_paired_contrasts.csv'][0]['ci_low']='3'
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_bootstrap_mean_rejected(self):
        value=tables(); value['final_paired_contrasts.csv'][0]['point_estimate_source']='BOOTSTRAP_REPLICATE_MEAN'
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_all_diagnostics_required(self):
        value=tables(); value['final_decision_diagnostics.csv'].pop()
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_saved_diagnostic_denominator(self):
        value=tables(); value['final_decision_diagnostics.csv'][0]['denominator']='239'
        with self.assertRaises(D.DeliveryIntegrityError): D.validate_saved_tables(value)
    def test_render_full_disclosure(self):
        manifest,*_=objects(); bundle={'repo':pathlib.Path('SYNTHETIC_REPOSITORY'),
            'results':pathlib.Path('SYNTHETIC_RESULTS'),'statistics_root':pathlib.Path('SYNTHETIC_STATISTICS'),
            'manifest':manifest,'tables':tables(),'phases':[{'phase':'full','start':'2026-01-01T00:00:00+00:00','finish':'2026-01-01T01:00:00+00:00'}],
            'failed_attempts':{}}
        reports=D.render_reports(bundle)
        self.assertEqual(len(reports),8)
        text='\n'.join(reports.values())
        for token in ('NOT_VERIFIED','not an unseen','dropout','C1','P0/10/20/50','H_t=min(4,25-t)','missed escalation','P7.7 - B8','C4','DELIVERY_MANIFEST'):
            self.assertIn(token,text)
        self.assertIn('Draft for Main',reports['PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'])

class FilesystemTests(unittest.TestCase):
    def test_reparse_point_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(pathlib.Path,'is_symlink',return_value=False),mock.patch.object(pathlib.Path,'lstat',return_value=types.SimpleNamespace(st_file_attributes=0x400)):
                with self.assertRaises(D.DeliveryIntegrityError): D.reject_reparse(folder)
    def test_copy_payload_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source=pathlib.Path(folder)/'source'; source.write_bytes(b'bound'); destination=pathlib.Path(folder)/'destination'
            expected=D.digest_file(source)
            with mock.patch.object(pathlib.Path,'read_bytes',return_value=b'changed-after-check'):
                with self.assertRaises(D.DeliveryIntegrityError): D.copy_bound(source,destination,expected)
            self.assertFalse(destination.exists())
    def test_copy_verifies_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source=pathlib.Path(folder)/'source'; source.write_bytes(b'bound'); destination=pathlib.Path(folder)/'destination'
            expected=D.digest_file(source)
            D.copy_bound(source,destination,expected)
            self.assertEqual(destination.read_bytes(),b'bound')
    def test_exclusive_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'output'
            D.exclusive_bytes(path,b'first')
            with self.assertRaises(D.DeliveryIntegrityError): D.exclusive_bytes(path,b'second')
            self.assertEqual(path.read_bytes(),b'first')
    def test_no_parent_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(D.DeliveryIntegrityError): D.safe_path(folder,'../outside')
    def test_no_absolute_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(D.DeliveryIntegrityError): D.safe_path(folder,pathlib.Path(folder).resolve())
    def test_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'input'; path.write_bytes(b'original'); digest=D.digest_file(path)
            path.write_bytes(b'changed')
            with self.assertRaises(D.DeliveryIntegrityError): D.bound_bytes(path,digest)
    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'input'; path.write_text('{"x":1,"x":2}',encoding='utf-8')
            with self.assertRaises(D.DeliveryIntegrityError): D.load_json(path)
    def test_infinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'input'; path.write_text('{"x":Infinity}',encoding='utf-8')
            with self.assertRaises(D.DeliveryIntegrityError): D.load_json(path)
    def test_duplicate_csv_header_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'input'; path.write_text('method,method\nB0,B0\n',encoding='utf-8')
            with self.assertRaises(D.DeliveryIntegrityError): D.read_csv_strings(path)
    def test_cell_strings_not_rounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'input'; path.write_text('x\n0.002524255871657655\n',encoding='utf-8')
            self.assertEqual(D.read_csv_strings(path)[0]['x'],'0.002524255871657655')
    def test_root_handoff_output_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(D.DeliveryIntegrityError): D.publish_delivery(folder,'fake','PAPER3_FINAL_REPLICATION_HANDOFF.md')
    def test_existing_package_rejected_before_evidence_read(self):
        with tempfile.TemporaryDirectory() as folder:
            (pathlib.Path(folder)/'handoffs'/'existing').mkdir(parents=True)
            with self.assertRaises(D.DeliveryIntegrityError): D.publish_delivery(folder,'fake','handoffs/existing')
    def test_existing_report_rejected_before_evidence_read(self):
        with tempfile.TemporaryDirectory() as folder:
            results=pathlib.Path(folder)/D.RESULT_RELATIVE; results.mkdir(parents=True)
            report=results/'EXECUTION_SUMMARY.md'; report.write_text('keep',encoding='utf-8')
            with self.assertRaises(D.DeliveryIntegrityError): D.publish_delivery(folder,'fake','handoffs/new')
            self.assertEqual(report.read_text(),'keep')
    def test_synthetic_proof_sha_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); source=root/'synthetic.py'; source.write_bytes(b'synthetic only')
            proof=root/'proof.json'; value={'all_pass':True,'exit_code':0,'real_outcomes_read':False,
                'models_generators_or_statistics_executed':False,'real_delivery_published':False,
                'implementation_sha256':{'synthetic.py':D.digest_file(source)}}
            proof.write_text(json.dumps(value),encoding='utf-8')
            D.verify_synthetic_proof(root,proof)
            source.write_bytes(b'changed')
            with self.assertRaises(D.DeliveryIntegrityError): D.verify_synthetic_proof(root,proof)

class PhaseSchemaTests(unittest.TestCase):
    def fixtures(self,root):
        bindings={}
        for phase in ('initial','minimal','full'):
            path=root/'execution'/phase/('A_'+phase.upper()+'_0001')/'completion.json'
            path.parent.mkdir(parents=True)
            value={'phase':phase,'attempt_id':'A_'+phase.upper()+'_0001','manifest_digest':'0'*64,
                'start':'2026-01-01T00:00:00+00:00','finish':'2026-01-01T01:00:00+00:00','worker_count':1,'success':True}
            path.write_text(json.dumps(value),encoding='utf-8'); bindings[str(path)]=D.digest_file(path)
        return bindings
    def test_actual_executor_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); bindings=self.fixtures(root)
            phases=D.read_phase_history(root,bindings,'0'*64)
            self.assertEqual({row['phase'] for row in phases},{'initial','minimal','full'})
    def test_failed_attempt_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); bindings=self.fixtures(root)
            path=root/'execution'/'full'/'A_FULL_0002'/'failure.json'; path.parent.mkdir()
            path.write_text(json.dumps({'phase':'full','attempt_id':'A_FULL_0002','manifest_digest':'0'*64,
                'start':'2026-01-01T02:00:00+00:00','finish':'2026-01-01T03:00:00+00:00','error':'synthetic'}),encoding='utf-8')
            bindings[str(path)]=D.digest_file(path)
            phases=D.read_phase_history(root,bindings,'0'*64)
            self.assertEqual(len(phases),4); self.assertIn('synthetic',[row['failure'] for row in phases])
    def test_wrong_attempt_layout_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder)
            with self.assertRaises(D.DeliveryIntegrityError): D.phase_artifact(root,root/'execution'/'full'/'wrong'/'completion.json')
    def test_local_time_requires_offset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); bindings=self.fixtures(root)
            path=next(iter(bindings)); value=json.loads(pathlib.Path(path).read_text()); value['start']='2026-01-01T00:00:00'
            pathlib.Path(path).write_text(json.dumps(value)); bindings[path]=D.digest_file(path)
            with self.assertRaises(D.DeliveryIntegrityError): D.read_phase_history(root,bindings,'0'*64)

if __name__=='__main__':
    unittest.main(verbosity=2)
