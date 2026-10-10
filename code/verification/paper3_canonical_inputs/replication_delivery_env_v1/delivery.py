"""Read saved, receipted outcomes only AFTER complete scientific/statistics gates.

Standard library only. Does not import project models, generators, NumPy,
executors or statistics implementations. Does not calculate new endpoints,
resamples, quantiles, effect estimates or original-versus-new differences.
The sole executable mode publishes exclusive reports and a new handoff folder.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import stat
from datetime import datetime, timezone
from pathlib import Path

RESULT_RELATIVE = 'results/p7_7_integrity_replication_batch20_env_v1'
STATS_RELATIVE = 'statistics_batch20_env_v1'
F1_DIGEST = 'ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228'
METHODS = ('B0','B1','B2','B8','P7.7')
SCENARIOS = ('C0','C1','C3','C4')
DIAGNOSTICS = ('correct retain','unnecessary RI','correct escalation','missed escalation')
REPORT_NAMES = ('EXECUTION_SUMMARY.md','INPUT_PARITY_AUDIT.md','EXPERIMENT_INTEGRITY_AUDIT.md',
                'CORRECTED_FINAL_STATISTICS.md','ORIGINAL_VS_REPLICATION_COMPARISON.md','SCIENTIFIC_FREEZE_DECISION.md')
SUMMARY_NAMES = ('final_metrics_by_method.csv','final_metrics_by_scenario.csv','final_paired_contrasts.csv',
                 'final_decision_diagnostics.csv','final_execution_cost_by_method.csv',
                 'original_vs_corrected_by_method.csv','original_vs_corrected_by_scenario.csv',
                 'original_vs_corrected_observed_contrasts.csv')
EXPECTED_COUNTS = {'raw_trajectories':1200,'five_method_groups':240,'stages':28800,
                   'center_method_rows':100,'scenario_center_rows':400,'paired_bootstrap_rows':16000,
                   'method_bootstrap_rows':20000,'loo_rows':80}

class DeliveryIntegrityError(RuntimeError):
    pass

def require(condition, message):
    if not condition:
        raise DeliveryIntegrityError(message)

def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def exact_fields(value, expected):
    return all(value.get(key) is item if type(item) is bool else value.get(key)==item for key,item in expected.items())

def safe_path(root, relative):
    root = Path(root).resolve()
    value = Path(relative)
    require(not value.is_absolute() and '..' not in value.parts, 'unsafe relative path')
    candidate = root / value
    require(candidate.resolve().is_relative_to(root), 'path escaped target root')
    for part in (candidate,*candidate.parents):
        if part == root.parent:
            break
        reject_reparse(part)
    return candidate

def reject_reparse(path):
    path = Path(path)
    require(not path.is_symlink(),'symlink path rejected')
    if path.exists():
        attributes = getattr(path.lstat(),'st_file_attributes',0)
        require(not attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400),'Windows junction/reparse point rejected')

def phase_artifact(root,path):
    root,path = Path(root).resolve(),Path(path).resolve()
    if not path.is_relative_to(root):
        return None
    parts = path.relative_to(root).parts
    if not parts or parts[0]!='execution':
        return None
    require(len(parts)==4 and parts[1] in ('initial','minimal','full'),'unexpected execution attempt path')
    prefix = 'A_'+parts[1].upper()+'_'
    require(parts[2].startswith(prefix) and len(parts[2])==len(prefix)+4 and parts[2][-4:].isdigit()
            and int(parts[2][-4:])>0,'malformed phase attempt identity')
    return parts[1],parts[2]

def load_json(path):
    def unique(pairs):
        value = {}
        for key,item in pairs:
            require(key not in value,'duplicate JSON key')
            value[key] = item
        return value
    with Path(path).open('r',encoding='utf-8') as stream:
        return json.load(stream,object_pairs_hook=unique,parse_constant=lambda value: (_ for _ in ()).throw(DeliveryIntegrityError('nonfinite JSON')))

def bound_bytes(path, expected):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(),'bound file unavailable')
    require(digest_file(path)==expected,'bound file SHA mismatch: '+str(path))
    return path

def read_csv_strings(path):
    with Path(path).open('r',encoding='utf-8',newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames))==len(reader.fieldnames),'duplicate/missing CSV header')
        rows = list(reader)
    require(rows and all(None not in row and all(value is not None for value in row.values()) for row in rows),'incomplete/empty CSV')
    return rows

def finite(value):
    try:
        result = float(value)
    except (ValueError,TypeError) as error:
        raise DeliveryIntegrityError('invalid saved numeric field') from error
    require(math.isfinite(result),'nonfinite saved numeric field')
    return result

def unique_rows(rows, keys, expected):
    observed = [tuple(row[key] for key in keys) for row in rows]
    require(len(observed)==len(set(observed)) and set(observed)==set(expected),'summary coverage or uniqueness mismatch')

def validate_saved_tables(tables):
    unique_rows(tables['final_metrics_by_method.csv'],('method',),[(m,) for m in METHODS])
    unique_rows(tables['final_metrics_by_scenario.csv'],('method','scenario'),[(m,s) for m in METHODS for s in SCENARIOS])
    unique_rows(tables['final_paired_contrasts.csv'],('comparison',),[('P7.7 - '+m,) for m in METHODS[:-1]])
    unique_rows(tables['final_decision_diagnostics.csv'],('metric',),[(m,) for m in DIAGNOSTICS])
    unique_rows(tables['final_execution_cost_by_method.csv'],('method',),[(m,) for m in METHODS])
    unique_rows(tables['original_vs_corrected_by_method.csv'],('method',),[(m,) for m in METHODS])
    unique_rows(tables['original_vs_corrected_by_scenario.csv'],('method','scenario'),[(m,s) for m in METHODS for s in SCENARIOS])
    unique_rows(tables['original_vs_corrected_observed_contrasts.csv'],('comparison',),[('P7.7 - '+m,) for m in METHODS[:-1]])
    for filename in ('final_metrics_by_method.csv','final_metrics_by_scenario.csv'):
        endpoint = 'mean_lifecycle_service_loss' if 'by_method' in filename else 'lifecycle_service_loss'
        for row in tables[filename]:
            require(row['n_centers']=='20','saved summary center count differs')
            for field in (endpoint,'ci_low','ci_high','gate_open_rate','ri_rate','maintenance_rate','retain_rate','total_action_cost'):
                finite(row[field])
            require(finite(row[endpoint])>=0 and finite(row['ci_low'])<=finite(row['ci_high']),'invalid saved endpoint/interval')
    for row in tables['final_paired_contrasts.csv']:
        require(row['n_centers']=='20' and row['bootstrap_resamples']=='4000' and row['bootstrap_seed']=='2904','contrast bootstrap contract differs')
        require(row['point_estimate_source']=='OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION','contrast point estimate replaced by bootstrap mean')
        for field in ('mean_difference','ci_low','ci_high'):
            finite(row[field])
        require(finite(row['ci_low'])<=finite(row['ci_high']),'invalid contrast interval')
    for row in tables['final_decision_diagnostics.csv']:
        require(row['denominator']=='5760','diagnostic denominator differs')
        require(0<=finite(row['count'])<=5760 and 0<=finite(row['rate'])<=1,'invalid saved diagnostic')
    return tables

def validate_gate_objects(manifest, gate, initial, statistics, receipt, expected_digest):
    require(manifest.get('manifest_digest')==expected_digest,'expected replication digest differs')
    unsigned = dict(manifest)
    unsigned.pop('manifest_digest',None)
    require(canonical_hash(unsigned)==expected_digest,'replication manifest canonical digest differs')
    require(manifest.get('input_bundle_digest')==F1_DIGEST,'input is not the fixed F1 bundle')
    require(manifest.get('historical_environment_reproduced') is False and manifest.get('original_records_mixed_into_new_results') is False,'historical/mixed provenance claim differs')
    require(manifest.get('model_environment_id')=='P7_7_REPLICATION_MODEL_ENV_V1','model environment differs')
    require(len(manifest.get('original_protected_snapshot',{}))==2535,'original protected snapshot count differs')
    require(manifest.get('original_start_check',{}).get('all_original_bytes_unchanged') is True,'original initial byte proof absent')
    expected = {'scientific_integrity_pass':True,'manifest_digest':expected_digest,'trajectories':1200,
        'paired_groups':240,'old_results_reused':False,'all_inputs_F1':True,'future_flags_false':True,
        'outcomes_used_to_select_protocol':False,'not_unseen_heldout':True}
    require(exact_fields(gate,expected),'full scientific gate not complete')
    group_ids = {f'{c}/{seed}/{s}' for c in range(33000,33020) for seed in (7311,7312,7313) for s in SCENARIOS}
    require(set(gate.get('groups',{}))==group_ids,'240-group certificate coverage differs')
    for group in gate['groups'].values():
        require(group.get('five_methods') is True and group.get('all_24_stage_input_fields_equal') is True,'five-method parity certificate failed')
        require(set(group.get('receipt_sha256',{}))==set(METHODS),'five-method receipt certificate missing')
    require(initial.get('manifest_digest')==expected_digest and len(initial.get('states',[]))==60,'sixty initial references not certified')
    require({(item['center_id'],item['seed']) for item in initial['states']}==
            {(c,s) for c in range(33000,33020) for s in (7311,7312,7313)},'initial reference cases differ')
    require(receipt.get('schema')=='paper3-statistics-execution-receipt-v1' and receipt.get('status')=='COMPLETED'
            and receipt.get('exit_code')==0 and receipt.get('replication_manifest_digest')==expected_digest,'statistics execution not completed')
    require(receipt.get('originals_unchanged') is True and receipt.get('joint_resampling_verified') is True
            and receipt.get('new_output_only') is True and receipt.get('models_or_generators_executed') is False,'statistics scope/integrity proof differs')
    require(statistics.get('replication_manifest_digest')==expected_digest and statistics.get('input_bundle_digest')==F1_DIGEST,'statistics provenance differs')
    require(statistics.get('counts')==EXPECTED_COUNTS,'statistics completion counts differ')
    protocol = statistics.get('protocol',{})
    expected_protocol = {'resampling_unit':'center','centers':list(range(33000,33020)),
        'bootstrap_resamples':4000,'bootstrap_seed':2904,'one_joint_index_matrix_for_all_methods_contrasts_scenarios':True,
        'observed_point_estimates_from_original_center_means':True,'new_unseen_heldout_claimed':False,
        'no_outcome_based_selection':True,'no_original_records_reused':True,'no_exclusions':True,'winner_ranking':False}
    require(exact_fields(protocol,expected_protocol),'frozen statistics semantics differ')
    require(receipt.get('outputs_sha256')==statistics.get('outputs_sha256'),'statistics output inventory differs')
    require(set(SUMMARY_NAMES)<=set(statistics.get('outputs_sha256',{})),'required saved summaries unavailable')
    return True

def markdown_table(rows, fields=None):
    require(rows,'no table rows')
    fields = list(fields or rows[0])
    escape = lambda value: str(value).replace('|','\\|').replace('\n',' ')
    result = ['| '+' | '.join(fields)+' |','| '+' | '.join(['---']*len(fields))+' |']
    result.extend('| '+' | '.join(escape(row[field]) for field in fields)+' |' for row in rows)
    return '\n'.join(result)+'\n'

def read_phase_history(root, bindings, digest):
    phases = []
    for path_text,expected in sorted(bindings.items()):
        path = Path(path_text)
        identity = phase_artifact(root,path)
        if identity and path.name in {'completion.json','failure.json'}:
            bound_bytes(path,expected)
            value = load_json(path)
            require(value.get('manifest_digest')==digest,'phase provenance differs')
            require(value.get('phase')==identity[0] and value.get('attempt_id')==identity[1],'phase attempt receipt identity differs')
            require(path.name!='completion.json' or value.get('success') is True,'phase success flag missing')
            start,finish = value.get('start'),value.get('finish')
            require(start and finish,'phase real timestamps absent')
            require(datetime.fromisoformat(start).tzinfo is not None and datetime.fromisoformat(finish).tzinfo is not None,'phase timestamp offset absent')
            phases.append({'phase':value['phase'],'attempt':value.get('attempt_id','NOT_RECORDED'),
                'start':start,'finish':finish,'worker_count':value.get('worker_count','NOT_RECORDED_FOR_FAILURE'),
                'success':value.get('success',False),'failure':value.get('error',''), 'source_path':str(path),'sha256':expected})
    for phase in ('initial','minimal','full'):
        require(any(row['phase']==phase and row['success'] is True for row in phases),'successful phase completion receipt absent')
    require(len({(row['phase'],row['attempt']) for row in phases})==len(phases),'ambiguous phase terminal proof')
    return phases

def audit_saved_evidence(repo, expected_digest):
    repo = Path(repo).resolve()
    results = safe_path(repo,RESULT_RELATIVE)
    statistics_root = safe_path(results,STATS_RELATIVE)
    manifest = load_json(safe_path(results,'provenance_manifest.json'))
    gate = load_json(safe_path(results,'full_experiment_integrity_gate.json'))
    initial = load_json(safe_path(results,'initial_state_manifest.json'))
    statistics_path = safe_path(statistics_root,'statistics_manifest.json')
    statistics = load_json(statistics_path)
    receipt = load_json(safe_path(statistics_root,'statistics_execution_receipt.json'))
    validate_gate_objects(manifest,gate,initial,statistics,receipt,expected_digest)
    bound_bytes(statistics_path,receipt['statistics_manifest_sha256'])
    bindings = statistics['input_bindings_sha256']
    require(bindings,'statistics input binding inventory empty')
    normalized_bindings = {str(Path(name).resolve()):digest for name,digest in bindings.items()}
    require(len(normalized_bindings)==len(bindings),'aliased input binding paths rejected')
    for relative in ('provenance_manifest.json','full_experiment_integrity_gate.json','initial_state_manifest.json'):
        core = safe_path(results,relative)
        require(normalized_bindings.get(str(core.resolve()))==digest_file(core),'required core proof is not bound by successful statistics')
    allowed = [repo,Path(manifest['environment']['base_prefix']).resolve()]
    for filename,expected in bindings.items():
        require(any(Path(filename).resolve().is_relative_to(root) for root in allowed),'unexpected external statistics binding')
        bound_bytes(filename,expected)
    for relative,expected in manifest['original_protected_snapshot'].items():
        bound_bytes(safe_path(repo,relative),expected)
    for relative,expected in manifest['critical_files_sha256'].items():
        bound_bytes(safe_path(repo,relative),expected)
    outputs = {}
    for relative,expected in statistics['outputs_sha256'].items():
        path = bound_bytes(safe_path(statistics_root,relative),expected)
        outputs[relative] = path
    tables = validate_saved_tables({name:read_csv_strings(outputs[name]) for name in SUMMARY_NAMES})
    phases = read_phase_history(results,bindings,expected_digest)
    raw_entries = []
    for filename,expected in bindings.items():
        path = Path(filename)
        if path.parent.resolve()==(results/'raw').resolve() and path.name.endswith(('.csv','.integrity.json')):
            raw_entries.append({'path':str(path.resolve()),'sha256':expected,'copied':False})
    require(len([row for row in raw_entries if row['path'].endswith('.csv')])==1200 and
            len([row for row in raw_entries if row['path'].endswith('.integrity.json')])==1200,'raw hash index lacks 1200 CSV/receipts')
    failures = statistics.get('failed_attempt_evidence_files_sha256',{})
    require(all(bindings.get(name)==expected for name,expected in failures.items()),'failed-attempt evidence not preserved')
    read_proofs = {str(path):digest_file(path) for path in (results/'provenance_manifest.json',results/'full_experiment_integrity_gate.json',
                  results/'initial_state_manifest.json',statistics_path,statistics_root/'statistics_execution_receipt.json')}
    return {'repo':repo,'results':results,'statistics_root':statistics_root,'manifest':manifest,'gate':gate,
        'initial':initial,'statistics':statistics,'receipt':receipt,'tables':tables,'phases':phases,
        'outputs':outputs,'raw_index':raw_entries,'failed_attempts':failures,
        'binding_files':bindings,'originals_unchanged_count':2535,'read_proofs_sha256':read_proofs}

LIMITATIONS = '''This is an integrity-correction independent replication after original outcomes were observed. It is not an unseen or newly held-out evaluation. Historical final runtime equivalence is NOT_VERIFIED; the authorized independent runtime uses pandas2.3.3/River0.23.0/psutil7.2.2 and binds other frozen scientific dependencies. Frozen original Torch dropout/global RNG remains part of the original method; exact failed-task RNG evidence supports controlled retry, while universal scheduling-invariant stochastic paths are not asserted. Paired input/initial/deployment integrity does not remove that limitation. No estimator refit, threshold adjustment, model-bank change or population reselection is authorized. Action penalties are not complete measured compute cost; cached-call timers, standalone estimates and search counters remain distinct. Python audited IO/causal guards are evidence of the controlled paths, not a general native-library or operating-system sandbox proof. Section3–4 remain subject to the prior manuscript audit: theoretical C1 policy class is not identical to the one-shot P0/10/20/50 offline margin, nor is that margin identical to the normalized MLP online decision score; required paper-only bridging remains unresolved. H_t=min(4,25-t) and the50-update allowance per candidate must not be described as an overall search budget. The old S3–4 audit's characterization of239/961 as merely execution lineage is superseded by the later single-group forensic audit and actual StageB full-batch/singleton input verification. Scientific integrity PASS certifies the replication evidence; it does not automatically freeze Sections3–4, the whole paper, superiority, deployment validity or publication readiness.'''

def render_reports(bundle):
    manifest,tables = bundle['manifest'],bundle['tables']
    results = bundle['results']
    evidence = f"Repository: `{bundle['repo']}`. Results: `{results}`. Replication digest `{manifest['manifest_digest']}`. F1 bundle `{manifest['input_bundle_digest']}`. Saved statistics receipt: `{bundle['statistics_root']/'statistics_execution_receipt.json'}`. All numeric table strings below come from saved, hash-bound CSV cells; no statistic was recalculated by this report generator. **This delivery is valid only with the final COMPLETED DELIVERY_MANIFEST.json binding the exact report SHA.**\n"
    status = 'COMPLETED;1200/1200 trajectories;240/240 groups;60/60 initial references;2535 original protected files unchanged.\n'
    phase_text = markdown_table(bundle['phases'])
    hashes = markdown_table([{'file':name,'sha256':value} for name,value in manifest['critical_files_sha256'].items()])
    method = markdown_table(tables['final_metrics_by_method.csv'])
    scenarios = markdown_table(tables['final_metrics_by_scenario.csv'])
    contrasts = markdown_table(tables['final_paired_contrasts.csv'])
    diagnostics = markdown_table(tables['final_decision_diagnostics.csv'])
    cost = markdown_table(tables['final_execution_cost_by_method.csv'])
    comparison = '\n'.join(markdown_table(tables[name]) for name in SUMMARY_NAMES[-3:])
    parity = 'The saved complete gate certifies each of240 center–seed–scenario groups across five methods and all24 stage input fields, initial state, scenario, deployment tier/filter and bank identities. Later deployed-state differences are permitted method consequences. All records use the same preverified F1 batch20 population; no singleton regeneration or old-trajectory reuse. These are executor/statistics gate certifications, plus fresh bound-byte checking here; this report generator does not execute a model or reconstruct initialization.\n'
    source_change = 'New executor changes input reading to the preserved F1 arrays, restores common initial references, isolates tasks, records causal/runtime/RNG receipts, and adds provenance/resume guards. Frozen original run_one/method logic, models, A1 estimator, zero gate, costs, source bank and scientific configuration remain byte-bound. No equivalence to the exact historical environment or universal dropout scheduling invariance is asserted. New statistic implementation uses the authorized joint20-center4000-draw/seed2904 index matrix and saved observed center-mean subtraction. Historical draw sequence is not reproduced; original summaries remain historical mixed-inventory descriptions.\n'
    failures = markdown_table([{'file':k,'sha256':v} for k,v in bundle['failed_attempts'].items()]) if bundle['failed_attempts'] else 'No failure artifacts are listed in the final bound statistics manifest; no missing-record inference is made.\n'
    reports = {
        'EXECUTION_SUMMARY.md':'# Execution Summary\n\n'+status+'\n'+evidence+'\n## Recorded actual phase attempts\n\n'+phase_text+'\n## Preserved failures\n\n'+failures+'\n'+LIMITATIONS+'\n',
        'INPUT_PARITY_AUDIT.md':'# Input Parity Audit\n\n'+status+'\n'+evidence+'\n'+parity+'\nThe240 individual group proofs and1200 CSV/receipt hash records remain indexed; no large raw CSV is copied.\n\n'+LIMITATIONS+'\n',
        'EXPERIMENT_INTEGRITY_AUDIT.md':'# Experiment Integrity Audit\n\n'+status+'\n'+evidence+'\n'+parity+'\n'+source_change+'\n## Frozen source/model/config bindings\n\n'+hashes+'\n## Causal and preservation evidence\n\nSaved full gate future_flags_false=True; statistics receipt originals_unchanged=True; all2535 original snapshot bytes were independently rechecked before delivery. Stored source/config/input/environment and phase end proofs are referenced, not substituted by manuscript text.\n\n'+LIMITATIONS+'\n',
        'CORRECTED_FINAL_STATISTICS.md':'# Corrected Final Statistics\n\n'+status+'\n'+evidence+'\n## All five methods and lifecycle actions\n\n'+method+'\n## All four observed Proposed-minus-baseline contrasts\n\n'+contrasts+'\nNegative observed differences favor Proposed service loss; positive differences are adverse. Intervals including zero do not establish a directional difference. All four are retained regardless of sign or significance. No bootstrap replicate mean replaces the observed effect.\n\n## All four scenarios for all five methods\n\n'+scenarios+'\n## All four frozen offline-label diagnostics\n\n'+diagnostics+'\nThese masks are potentially overlapping and nonexhaustive; missed escalation is action != ri and R_B50 <0, not solely a closed-gate error.\n\n## Actual saved cost/search summaries\n\n'+cost+'\n'+LIMITATIONS+'\n',
        'ORIGINAL_VS_REPLICATION_COMPARISON.md':'# Original vs Replication Comparison\n\n'+evidence+'\n'+comparison+'\nAll differences above were already computed and saved by the independently receipted statistics stage. No direction is used to choose dependencies, stop execution or alter reporting. Mean change cannot identify a cause: canonical materialization, stochastic original method paths and the approved independent runtime are not isolated intervention factors. Original239 F/961 S mixed provenance and one cross-method mismatching group prevent treating the old full inventory as a completely canonical paired population. Original files and original CIs remain intact and are not replaced by these reports.\n\n'+LIMITATIONS+'\n',
        'SCIENTIFIC_FREEZE_DECISION.md':'# Scientific Freeze Decision\n\n'+status+'\n'+evidence+'\nImplementation/input/initial-state/deployment/source/output and complete statistics gates PASS for the saved corrective replication. This provides evidence to revise the paper experiment section using all saved results, including adverse and zero-crossing intervals. Paper Sections3–4 estimator semantics and previous manuscript audit findings still require separate scientific/editorial resolution; executing this replication does not automatically freeze the manuscript.\n\n'+LIMITATIONS+'\n'
    }
    reports['PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'] = '# Paper3 Final Replication Handoff — Draft for Main to Archive/Publish\n\n'+status+'\n'+evidence+'\n## Execution Status\n\n'+phase_text+'\n## Protocol Integrity\n\n'+parity+'\n'+hashes+'\n## Final Scientific Results\n\n'+method+'\n'+contrasts+'\n'+scenarios+'\n'+diagnostics+'\n'+cost+'\n## Original vs Corrected\n\n'+comparison+'\n## Scientific Verdict\n\n'+LIMITATIONS+'\n## File Index\n\n'+ '\n'.join(f'- `{results/name}`' for name in REPORT_NAMES)+'\n\nStatistics root: `'+str(bundle['statistics_root'])+'`. Full raw outputs remain in `'+str(results/'raw')+'`; raw hashes, source/config/input/environment and phase/failure proofs are in the new package index. Main must archive the preceding root handoff before replacing it; this generator never writes that root file.\n'
    reports['SOURCE_CHANGE_DESCRIPTION.md'] = '# Source Change Description\n\n'+source_change+'\n'+hashes+'\n'+LIMITATIONS+'\n'
    return reports

def exclusive_bytes(path,payload):
    path = Path(path)
    require(not path.exists(),'exclusive output already exists: '+str(path))
    for part in (path,*path.parents): reject_reparse(part)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload)

def copy_bound(source,destination,expected):
    source = bound_bytes(source,expected)
    payload = source.read_bytes()
    require(hashlib.sha256(payload).hexdigest()==expected,'copy payload is not the bound scientific bytes')
    exclusive_bytes(destination,payload)
    bound_bytes(destination,expected)
    return expected

def csv_bytes(rows):
    require(rows,'empty index')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')

def publish_delivery(repo, expected_digest, handoff_relative):
    repo = Path(repo).resolve()
    results = safe_path(repo,RESULT_RELATIVE)
    package = safe_path(repo,handoff_relative)
    handoffs = safe_path(repo,'handoffs')
    require(package.resolve().is_relative_to(handoffs.resolve()) and package.resolve()!=handoffs.resolve(),'handoff directory must be an independent child under repo/handoffs')
    require(not package.exists(),'handoff output already exists')
    for name in (*REPORT_NAMES,'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md','DELIVERY_MANIFEST.json','DELIVERY_MANIFEST.json.sha256'):
        require(not safe_path(results,name).exists(),'report output already exists')
    bundle = audit_saved_evidence(repo,expected_digest)
    reports = render_reports(bundle)
    package.mkdir(parents=True,exist_ok=False)
    publications = {}
    copied = {}
    for name,payload in reports.items():
        data = payload.encode('utf-8')
        exclusive_bytes(package/name,data)
        copied[str(package/name)] = hashlib.sha256(data).hexdigest()
        if name in REPORT_NAMES or name=='PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md':
            exclusive_bytes(results/name,data)
            publications[str(results/name)] = hashlib.sha256(data).hexdigest()
    for name,path in bundle['outputs'].items():
        target = package/'statistics'/name
        copied[str(target)] = copy_bound(path,target,bundle['statistics']['outputs_sha256'][name])
    core_paths = [results/'provenance_manifest.json',results/'full_experiment_integrity_gate.json',results/'initial_state_manifest.json',
                  bundle['statistics_root']/'statistics_manifest.json',bundle['statistics_root']/'statistics_execution_receipt.json']
    for path in core_paths:
        target = package/'manifests'/path.name
        copied[str(target)] = copy_bound(path,target,bundle['read_proofs_sha256'][str(path)])
    for name,digest in bundle['failed_attempts'].items():
        relative = Path(name).resolve().relative_to(results.resolve())
        target = package/'failure_evidence'/relative
        copied[str(target)] = copy_bound(name,target,digest)
    for name,digest in bundle['binding_files'].items():
        source = Path(name)
        if phase_artifact(results,source) and source.suffix=='.json':
            target = package/'phase_evidence'/source.resolve().relative_to(results.resolve())
            copied[str(target)] = copy_bound(source,target,digest)
    exclusive_bytes(package/'indexes'/'CORRECTED_RAW_FILE_INDEX.csv',csv_bytes(bundle['raw_index']))
    original_index = [{'path':str(safe_path(repo,name)),'sha256':digest,'copied':False}
                      for name,digest in bundle['manifest']['original_protected_snapshot'].items()]
    exclusive_bytes(package/'indexes'/'ORIGINAL_PROTECTED_FILE_INDEX.csv',csv_bytes(original_index))
    exclusive_bytes(package/'indexes'/'ALL_STATISTICS_INPUT_BINDINGS.json',(json.dumps(bundle['binding_files'],indent=2)+'\n').encode())
    provenance_index = {key:bundle['manifest'][key] for key in ('candidate_id','input_protocol','input_definition_digest',
        'input_dependency_digest','input_bundle_digest','stage_b_bindings','input_files_sha256','critical_files_sha256',
        'environment_binding','environment','historical_environment_reproduced')}
    exclusive_bytes(package/'indexes'/'INPUT_SOURCE_CONFIG_ENVIRONMENT_BINDINGS.json',(json.dumps(provenance_index,indent=2)+'\n').encode())
    for path in (package/'indexes').iterdir(): copied[str(path)] = digest_file(path)
    for relative,digest in bundle['manifest']['critical_files_sha256'].items():
        if Path(relative).suffix.lower() in {'.py','.json','.txt','.toml','.yaml','.yml','.md'}:
            target = package/'source'/'original_frozen'/relative
            copied[str(target)] = copy_bound(safe_path(repo,relative),target,digest)
    for relative in ('configs/requirements_frozen.txt','PAPER3_SINGLE_GROUP_INTEGRITY_FORENSIC_REPORT.md',
        'PAPER3_CANONICAL_INPUT_VERIFICATION_PLAN.md','PAPER3_S3_S4_IMPLEMENTATION_CONSISTENCY_AUDIT.md'):
        digest = bundle['manifest']['original_protected_snapshot'].get(relative)
        if digest:
            target = package/'source'/'original_frozen'/relative
            if str(target) not in copied:
                copied[str(target)] = copy_bound(safe_path(repo,relative),target,digest)
    descriptor = bundle['manifest']['environment'].get('model_runtime_descriptor',{})
    for name,digest in descriptor.get('installation_evidence_files_sha256',{}).items():
        source = Path(name)
        require(source.resolve().is_relative_to(repo),'unexpected dependency evidence path')
        target = package/'environment_evidence'/source.name
        copied[str(target)] = copy_bound(source,target,digest)
    for module_root_key,hashes_key in [('executor_root','executor_sha256')]:
        source_root = Path(bundle['manifest']['paths'][module_root_key])
        for relative,digest in bundle['manifest'][hashes_key].items():
            source = bound_bytes(safe_path(source_root,relative),digest)
            target = package/'source'/'executor'/relative
            copied[str(target)] = copy_bound(source,target,digest)
    for name,digest in bundle['statistics'].get('implementation_files_sha256',{}).items():
        source = bound_bytes(name,digest)
        stat_root = safe_path(repo,'verification/paper3_canonical_inputs/replication_statistics_batch20_env_v1')
        require(source.resolve().is_relative_to(stat_root.resolve()),'unexpected statistics implementation path')
        target = package/'source'/'statistics'/source.resolve().relative_to(stat_root.resolve())
        copied[str(target)] = copy_bound(source,target,digest)
    source = Path(__file__).resolve()
    target = package/'source'/'delivery'/source.name
    copied[str(target)] = copy_bound(source,target,digest_file(source))
    # Recheck the binding inventory and protected originals after publication.
    for name,digest in bundle['binding_files'].items():
        bound_bytes(name,digest)
    for name,digest in bundle['manifest']['original_protected_snapshot'].items():
        bound_bytes(safe_path(repo,name),digest)
    for name,digest in bundle['read_proofs_sha256'].items(): bound_bytes(name,digest)
    for relative,digest in bundle['statistics']['outputs_sha256'].items(): bound_bytes(safe_path(bundle['statistics_root'],relative),digest)
    for name,digest in publications.items(): bound_bytes(name,digest)
    for name,digest in copied.items(): bound_bytes(name,digest)
    require({str(path) for path in package.rglob('*') if path.is_file()}==set(copied),'unexpected unbound package file')
    inventory = {str(path.relative_to(package)).replace('\\','/'):digest_file(path)
                 for path in sorted(package.rglob('*')) if path.is_file()}
    delivery = {'schema':'paper3-saved-results-delivery-v1','status':'COMPLETED',
        'replication_manifest_digest':expected_digest,'statistics_receipt_sha256':digest_file(core_paths[-1]),
        'results_report_files_sha256':publications,'package_root':str(package),'package_files_sha256':inventory,
        'original_protected_files_unchanged':2535,'real_models_or_generators_executed_by_delivery':False,
        'new_statistics_or_bootstrap_executed_by_delivery':False,'root_handoff_modified':False,
        'manifest_self_and_sidecar_excluded':True,'created_utc':datetime.now(timezone.utc).isoformat()}
    payload = (json.dumps(delivery,indent=2,allow_nan=False)+'\n').encode()
    for root in (results,package):
        exclusive_bytes(root/'DELIVERY_MANIFEST.json',payload)
        exclusive_bytes(root/'DELIVERY_MANIFEST.json.sha256',(hashlib.sha256(payload).hexdigest()+'  DELIVERY_MANIFEST.json\n').encode())
    return delivery

def verify_synthetic_proof(source_root,receipt_path):
    source_root = Path(source_root).resolve()
    receipt_path = Path(receipt_path).resolve()
    require(receipt_path.parent==source_root,'test proof must be in the independent delivery implementation root')
    proof = load_json(receipt_path)
    expected = {'all_pass':True,'exit_code':0,'real_outcomes_read':False,
                'models_generators_or_statistics_executed':False,'real_delivery_published':False}
    require(exact_fields(proof,expected),'independent synthetic proof not successful or scope differs')
    actual = {path.name:digest_file(path) for path in source_root.glob('*.py')}
    require(proof.get('implementation_sha256')==actual,'delivery implementation changed after synthetic proof')
    return digest_file(receipt_path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True)
    parser.add_argument('--expected-manifest-digest',required=True)
    parser.add_argument('--handoff-relative',required=True)
    parser.add_argument('--synthetic-test-receipt',required=True)
    args = parser.parse_args()
    require(__import__('sys').flags.isolated and __import__('sys').flags.no_site and __import__('sys').dont_write_bytecode,'delivery requires -I -S -B')
    verify_synthetic_proof(Path(__file__).resolve().parent,args.synthetic_test_receipt)
    delivery = publish_delivery(args.repo,args.expected_manifest_digest,args.handoff_relative)
    print(json.dumps({'status':delivery['status'],'package_root':delivery['package_root'],'reports':list(delivery['results_report_files_sha256'])},indent=2))

if __name__=='__main__':
    main()
