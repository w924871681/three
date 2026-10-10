"""Independent read-only arithmetic verification of saved Paper 3 evidence.

Never imports the experiment or original statistics implementation. Raw CSV bytes
are each read once, hashed and parsed from the same buffer. Only new files beside
this script may be published, with exclusive creation. Existing statistics are
comparison targets, never overwritten. Run with frozen venv Python -I -B.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, sys, time, traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RES = ROOT / 'results/p7_7_integrity_replication_batch20_env_v3'
STAT = RES / 'statistics_batch20_env_v3'
METHODS = ('B0', 'B1', 'B2', 'B8', 'P7.7')
CENTERS = tuple(range(33000, 33020))
SEEDS = (7311, 7312, 7313)
SCENARIOS = ('C0', 'C1', 'C3', 'C4')
METRICS = ('lifecycle_service_loss','maintenance_count','maintenance_rate','ri_count','ri_rate',
           'maintenance_cost','ri_cost','total_action_cost','retain_rate','gate_open_rate')
RUNTIME = ('feasible_candidate_count','ri_search_updates_charged','source_cache_hits',
           'shared_parent_cache_hit','decision_runtime_actual_s','decision_runtime_standalone_estimate_s')
ABS_TOL, REL_TOL = 1e-14, 1e-12
V4 = ROOT / 'verification/paper3_canonical_inputs/replication_dynamic_delivery_recovery_v4/FINAL_READONLY_ACCEPTANCE_004.json'
V4_SHA = 'c4229bcd5f46612c5bb062412f1f2f308ea8ef44cda8fca9a12c5143cf003e64'
SOURCES = ('verification/paper3_canonical_inputs/replication_statistics_batch20_env_v3/statistics.py',
           'core/p7.py','scripts/run_p7_7_final.py')

def require(value, message):
    if not value: raise RuntimeError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def mean(values):
    values = list(values)
    return math.fsum(values) / len(values)
def cells(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    require(len(reader.fieldnames) == len(set(reader.fieldnames)), 'duplicate CSV header')
    rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows), 'malformed CSV')
    return rows
def write_new(name, payload):
    with (OUT / name).open('xb') as stream: stream.write(payload)
def json_bytes(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()

class Evidence:
    def __init__(self): self.index = {}; self.cache = {}; self.signatures = {}; self.comparisons = {}; self.raw_index = []
    def read(self, path, expected=None):
        path = Path(path).resolve()
        if path in self.cache:
            data = self.cache[path]
        else:
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns), 'file mutated while read: '+str(path))
            self.signatures[path] = (after.st_size,after.st_mtime_ns)
            self.cache[path] = data
            self.index[str(path)] = {'sha256':sha(data), 'bytes':len(data)}
        if expected: require(sha(data)==expected, 'SHA mismatch: '+str(path))
        return data
    def obj(self,path,expected=None): return json.loads(self.read(path,expected))
    def compare(self, name, expected, keys):
        actual = cells(self.read(STAT / name))
        def key(row): return tuple(str(row[k]) for k in keys)
        amap = {key(row):row for row in actual}; emap = {key(row):row for row in expected}
        require(len(amap)==len(actual) and len(emap)==len(expected) and amap.keys()==emap.keys(), name+' row coverage mismatch')
        numeric = text = 0; maximum = 0.0
        for k, row in emap.items():
            require(row.keys()==amap[k].keys(), name+' columns mismatch')
            for field, value in row.items():
                found = amap[k][field]
                if isinstance(value,(int,float,np.integer,np.floating)) and not isinstance(value,bool):
                    found = float(found); value = float(value)
                    require(math.isfinite(found) and math.isfinite(value),name+' nonfinite')
                    delta = abs(found-value); maximum = max(maximum,delta); numeric += 1
                    require(math.isclose(found,value,rel_tol=REL_TOL,abs_tol=ABS_TOL), f'{name} {k} {field}: saved={found!r} independent={value!r}')
                else:
                    text += 1
                    require(found==str(value),f'{name} {k} {field}: categorical mismatch')
        self.comparisons[name] = {'status':'PASS','rows':len(actual),'numeric_cells':numeric,'categorical_cells':text,'max_abs_difference':maximum}
    def unchanged_metadata(self):
        for p, expected in self.signatures.items():
            s=p.stat(); require((s.st_size,s.st_mtime_ns)==expected, 'input metadata changed before publication: '+str(p))

def verify(e):
    v4=e.obj(V4,V4_SHA)
    require(v4['scientific_and_artifact_acceptance']=='PASS','prior full audit is not PASS')
    manifest=e.obj(STAT/'statistics_manifest.json','a2cd080532db281ca60ae89ee9edf5e272552689f8be9220eaf7c7857b3f1468')
    receipt=e.obj(STAT/'statistics_execution_receipt.json','82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec')
    require(receipt['status']=='COMPLETED' and receipt['exit_code']==0,'statistics receipt incomplete')
    require(receipt['outputs_sha256']==manifest['outputs_sha256'],'saved output bindings disagree')
    for name,digest in manifest['outputs_sha256'].items(): e.read(STAT/name,digest)
    require(len(manifest['outputs_sha256'])==16,'statistics output inventory differs')
    for name in SOURCES: e.read(ROOT/name)
    protocol=manifest['protocol']
    require(protocol['bootstrap_resamples']==4000 and protocol['bootstrap_seed']==2904 and protocol['resampling_unit']=='center','protocol differs')
    require(protocol['one_joint_index_matrix_for_all_methods_contrasts_scenarios'] is True,'joint matrix contract absent')
    raw_paths=sorted((RES/'raw').glob('*.csv'))
    require(len(raw_paths)==1200,'raw CSV inventory is not 1200')
    expected_tasks={(m,c,s,q) for m in METHODS for c in CENTERS for s in SEEDS for q in SCENARIOS}
    tasks={}; trajectory=[]; costs=[]; proposed=[]; candidate_rule_rows=0; per_candidate_updates=set(); probe_updates=set()
    sources=Counter(); total_stage_count=0; cache_hits=0
    bindings=manifest['input_bindings_sha256']
    for path in raw_paths:
        expected=bindings.get(str(path)); require(expected is not None,'raw not bound by saved statistics manifest')
        data=e.read(path,expected); rows=cells(data)
        require(len(rows)==24 and {int(r['stage']) for r in rows}==set(range(1,25)),'raw stage coverage')
        keys={(r['method'],int(r['center_id']),int(r['seed']),r['scenario']) for r in rows}
        require(len(keys)==1,'multiple tasks in one CSV'); key=keys.pop()
        require(key in expected_tasks and key not in tasks,'duplicate/out-of-contract trajectory'); tasks[key]=rows
        rp=path.with_suffix('.integrity.json'); rec=e.obj(rp,bindings[str(rp)])
        require(rec['valid'] is True and rec['output_hash']==sha(data) and rec['trajectory_rows']==24,'raw receipt invalid')
        require((rec['task']['method'],rec['task']['center_id'],rec['task']['seed'],rec['task']['scenario'])==key,'receipt task mismatch')
        sources[rec['attempt_id']]+=1
        e.raw_index.append({'path':str(path),'sha256':sha(data),'bytes':len(data),'receipt_path':str(rp),'receipt_sha256':e.index[str(rp)]['sha256'],**dict(zip(('method','center_id','seed','scenario'),key))})
        row=dict(zip(('method','center_id','seed','scenario'),key)); row['stages']=24
        row['lifecycle_service_loss']=mean(float(r['service_mse']) for r in rows)
        require(all(math.isfinite(float(r['service_mse'])) and float(r['service_mse'])>=0 for r in rows),'invalid loss')
        for action,prefix in (('local','maintenance'),('ri','ri'),('retain','retain')):
            row[prefix+'_count']=sum(r['action']==action for r in rows); row[prefix+'_rate']=row[prefix+'_count']/24
        row['gate_open_count']=sum(int(r['gate_open']) for r in rows); row['gate_open_rate']=row['gate_open_count']/24
        row['maintenance_cost']=math.fsum(float(r['event_cost_raw']) for r in rows if r['action']=='local')
        row['ri_cost']=math.fsum(float(r['event_cost_raw']) for r in rows if r['action']=='ri')
        row['total_action_cost']=math.fsum(float(r['event_cost_raw']) for r in rows); trajectory.append(row)
        cost=dict(zip(('method','center_id','seed','scenario'),key)); cost['stages']=24
        for field in RUNTIME:
            vals=[float(r[field]) for r in rows]
            require(all(math.isfinite(x) and x>=0 for x in vals),'invalid timer/counter')
            cost[field+'_stage_sum']=math.fsum(vals); cost[field+'_stage_mean']=mean(vals)
        costs.append(cost)
        for r in rows:
            require(int(r['ri_search_updates_charged'])==50*int(r['feasible_candidate_count']),'charged updates do not equal 50 per eligible candidate')
            require(int(r['ri'])==int(r['action']=='ri') and int(r['local'])==int(r['action']=='local'),'action indicators differ')
            require(not int(r['ri']) or int(r['gate_open'])==1,'RI without gate')
            per_candidate_updates.add(int(r['ri_updates_per_candidate'])); probe_updates.add(int(r['probe_updates']))
            candidate_rule_rows+=1; cache_hits+=int(r['source_cache_hits'])+int(r['shared_parent_cache_hit'])
        if key[0]=='P7.7': proposed.extend(rows)
        total_stage_count+=len(rows)
    require(set(tasks)==expected_tasks and total_stage_count==28800,'incomplete matrix')
    print('1200 raw CSV buffers verified and aggregated; checking saved tables.',flush=True)
    e.compare('final_metrics_by_trajectory.csv',trajectory,('method','center_id','seed','scenario'))
    e.compare('final_execution_cost_by_trajectory.csv',costs,('method','center_id','seed','scenario'))
    center=[]; strata=[]
    for method in METHODS:
        for c in CENTERS:
            selected=[r for r in trajectory if r['method']==method and r['center_id']==c]
            center.append({'method':method,'center_id':c,**{f:mean(r[f] for r in selected) for f in METRICS}})
            for q in SCENARIOS:
                selected_q=[r for r in selected if r['scenario']==q]
                strata.append({'method':method,'center_id':c,'scenario':q,**{f:mean(r[f] for r in selected_q) for f in METRICS}})
    e.compare('final_metrics_by_center.csv',center,('method','center_id'))
    e.compare('final_metrics_by_scenario_center.csv',strata,('method','center_id','scenario'))
    indices=np.load(io.BytesIO(e.read(STAT/'joint_center_resample_indices.npy')),allow_pickle=False)
    expected_indices=np.random.default_rng(2904).integers(0,20,size=(4000,20),dtype=np.int64)
    require(indices.dtype==np.int64 and indices.shape==(4000,20) and np.array_equal(indices,expected_indices),'saved bootstrap indices differ from seed 2904')
    e.comparisons['joint_center_resample_indices.npy']={'status':'PASS','shape':[4000,20],'dtype':'int64','all_80000_indices_match_seed_2904':True}
    center_map={(r['method'],r['center_id']):r for r in center}; stratum_map={(r['method'],r['center_id'],r['scenario']):r for r in strata}
    matrix=np.array([[center_map[m,c]['lifecycle_service_loss'] for c in CENTERS] for m in METHODS])
    # Each draw reuses the SAME 20 resampled center positions jointly. The
    # original observed means, not means over the draws, are point estimates.
    samples=np.mean(matrix[:,indices],axis=2)
    method_table=[]; method_draws=[]
    for j,m in enumerate(METHODS):
        low,high=np.quantile(samples[j],[.025,.975],method='linear')
        method_table.append({'method':m,'mean_lifecycle_service_loss':mean(matrix[j]),'ci_low':float(low),'ci_high':float(high),'n_centers':20,
            **{f:mean(center_map[m,c][f] for c in CENTERS) for f in METRICS if f!='lifecycle_service_loss'}})
        method_draws.extend({'method':m,'bootstrap_id':i,'lifecycle_service_loss':float(x)} for i,x in enumerate(samples[j]))
    e.compare('final_metrics_by_method.csv',method_table,('method',)); e.compare('final_method_bootstrap.csv',method_draws,('method','bootstrap_id'))
    contrasts=[]; pair_draws=[]; loo=[]
    for j,m in enumerate(METHODS[:-1]):
        diffs=matrix[-1]-matrix[j]; draws=diffs[indices].mean(axis=1); low,high=np.quantile(draws,[.025,.975],method='linear'); comparison='P7.7 - '+m
        contrasts.append({'comparison':comparison,'mean_difference':method_table[-1]['mean_lifecycle_service_loss']-method_table[j]['mean_lifecycle_service_loss'],
            'ci_low':float(low),'ci_high':float(high),'n_centers':20,'bootstrap_resamples':4000,'bootstrap_seed':2904,'point_estimate_source':'OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION'})
        pair_draws.extend({'comparison':comparison,'bootstrap_id':i,'difference':float(x)} for i,x in enumerate(draws))
        loo.extend({'comparison':comparison,'omitted_center':c,'difference':mean(float(x) for k,x in enumerate(diffs) if CENTERS[k]!=c)} for c in CENTERS)
    e.compare('final_paired_contrasts.csv',contrasts,('comparison',)); e.compare('final_paired_bootstrap.csv',pair_draws,('comparison','bootstrap_id')); e.compare('final_loo.csv',loo,('comparison','omitted_center'))
    scenarios=[]
    for m in METHODS:
        for q in SCENARIOS:
            values=np.array([stratum_map[m,c,q]['lifecycle_service_loss'] for c in CENTERS]); low,high=np.quantile(values[indices].mean(axis=1),[.025,.975],method='linear')
            scenarios.append({'method':m,'scenario':q,'n_centers':20,**{f:mean(stratum_map[m,c,q][f] for c in CENTERS) for f in METRICS},'ci_low':float(low),'ci_high':float(high),'ci_scope':'ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL'})
    e.compare('final_metrics_by_scenario.csv',scenarios,('method','scenario'))
    predicates={'correct retain':lambda r:r['action']=='retain' and r['best_local_policy']=='P0',
        'unnecessary RI':lambda r:r['action']=='ri' and float(r['R_B50'])>=0,
        'correct escalation':lambda r:r['action']=='ri' and float(r['R_B50'])<0,
        'missed escalation':lambda r:r['action']!='ri' and float(r['R_B50'])<0}
    diagnostics=[{'metric':name,'count':sum(fn(r) for r in proposed),'rate':sum(fn(r) for r in proposed)/len(proposed),'denominator':len(proposed)} for name,fn in predicates.items()]
    e.compare('final_decision_diagnostics.csv',diagnostics,('metric',))
    cost_methods=[]
    for m in METHODS:
        chosen=[r for r in costs if r['method']==m]; row={'method':m,'n_centers':20,'n_trajectories':240,'n_stage_records':5760}
        for f in RUNTIME:
            row[f+'_total_recorded']=math.fsum(r[f+'_stage_sum'] for r in chosen)
            row[f+'_mean_trajectory_center_averaged']=mean(mean(r[f+'_stage_sum'] for r in chosen if r['center_id']==c) for c in CENTERS)
        cost_methods.append(row)
    e.compare('final_execution_cost_by_method.csv',cost_methods,('method',))
    original={}
    for name in ('final_metrics_by_method.csv','final_metrics_by_scenario.csv'):
        p=ROOT/'results/p7_7'/name; original[name]=cells(e.read(p,bindings[str(p)]))
    om={r['method']:r for r in original['final_metrics_by_method.csv']}; os={(r['method'],r['scenario']):r for r in original['final_metrics_by_scenario.csv']}
    comparison_methods=[]
    for r in method_table:
        m=r['method']; old=float(om[m]['mean_lifecycle_service_loss']); new=r['mean_lifecycle_service_loss']
        comparison_methods.append({'method':m,'original_mixed_inventory_mean':old,'corrected_batch20_mean':new,'corrected_minus_original':new-old,
            'original_ci_low':float(om[m]['ci_low']),'original_ci_high':float(om[m]['ci_high']),'corrected_ci_low':r['ci_low'],'corrected_ci_high':r['ci_high'],'causal_attribution':'NOT_IDENTIFIED_FROM_MEAN_CHANGE'})
    e.compare('original_vs_corrected_by_method.csv',comparison_methods,('method',))
    comparison_scenarios=[]
    for r in scenarios:
        old=float(os[r['method'],r['scenario']]['lifecycle_service_loss']); new=r['lifecycle_service_loss']
        comparison_scenarios.append({'method':r['method'],'scenario':r['scenario'],'original_mixed_inventory_mean':old,'corrected_batch20_mean':new,'corrected_minus_original':new-old,'causal_attribution':'NOT_IDENTIFIED_FROM_MEAN_CHANGE'})
    e.compare('original_vs_corrected_by_scenario.csv',comparison_scenarios,('method','scenario'))
    comparison_contrasts=[]
    for r,m in zip(contrasts,METHODS[:-1]):
        old=float(om['P7.7']['mean_lifecycle_service_loss'])-float(om[m]['mean_lifecycle_service_loss']); new=r['mean_difference']
        comparison_contrasts.append({'comparison':r['comparison'],'original_observed_method_mean_difference':old,'corrected_observed_method_mean_difference':new,'corrected_minus_original_difference':new-old,'corrected_ci_low':r['ci_low'],'corrected_ci_high':r['ci_high'],'original_paired_inference_scope':'239 matched groups; one group mismatch; mixed canonical population','new_heldout_is_unseen':False,'causal_attribution':'NOT_IDENTIFIED_FROM_CONTRAST_CHANGE'})
    e.compare('original_vs_corrected_observed_contrasts.csv',comparison_contrasts,('comparison',))
    require(len(e.comparisons)==16,'not all sixteen outputs compared')
    require(contrasts[-1]['mean_difference']>0 and contrasts[-1]['ci_low']<0<contrasts[-1]['ci_high'],'B8 claim boundary differs')
    require(per_candidate_updates==probe_updates=={50},'saved 50 update fields differ')
    return {'status':'PASS','scope':'INDEPENDENT_SAVED_NUMERICAL_EVIDENCE_VERIFICATION',
        'raw_csv_count':1200,'raw_stage_count':total_stage_count,'five_method_groups':240,'all_raw_csv_read_once':True,
        'raw_attempt_counts':dict(sources),'method_summaries':method_table,'contrasts':contrasts,'scenarios':scenarios,'diagnostics':diagnostics,
        'runtime_search_summaries':cost_methods,'candidate_updates_relation_verified_rows':candidate_rule_rows,
        'candidate_update_count':50,'probe_update_count':50,'recorded_cache_hit_total':cache_hits,
        'bootstrap':{'seed':2904,'draws':4000,'center_count':20,'same_joint_indices_all_outputs':True,'saved_indices_equal_numpy_seeded_indices':True,'interval':'percentile 95%, linear quantiles','observed_point_estimate':'original center method mean subtraction'},
        'comparison_tolerance':{'absolute':ABS_TOL,'relative':REL_TOL,'categorical':'exact'},'output_comparisons':e.comparisons,
        'prior_full_integrity_acceptance':{'path':str(V4),'sha256':V4_SHA,'environment_and_protected_files_not_rescanned':True,'prior_arithmetic_recalculation':False},
        'independent_implementation_imports_original_statistics_or_models':False,'models_training_or_new_experiments_run':False,
        'original_files_modified':False,'historical_environment_numerical_equivalence':'NOT_VERIFIED',
        'runtime_measurement_limitations':['Recorded decision-call attribution is not complete end-to-end walltime or CPU/GPU work.','Standalone runtime estimate remains an estimate even where its saved value equals the actual attributed timer.','Search updates are charged counters of 50 per candidate, not observed hardware instruction counts.'],
        'numpy':{'version':np.__version__,'path':np.__file__},'python':{'version':sys.version,'executable':sys.executable},
        'scientific_claims':{'P7.7_B0_B1_B2_saved_paired_intervals_below_zero':all(r['ci_high']<0 for r in contrasts[:3]),'P7.7_B8_interval_crosses_zero':True,'B8_superiority_supported':False,'B8_equivalence_supported':False,'new_unseen_heldout_claimed':False,'paper_automatically_frozen':False},
        'diagnostic_definition':{'unnecessary_RI':'action == ri and R_B50 >= 0','missed_escalation':'action != ri and R_B50 < 0','denominator':'all 5760 Proposed stage records, not only gate-open, RI, or R_B50-negative cases','masks':'potentially overlapping and nonexhaustive; offline finite-reference proxies, not verified online counterfactual errors'}}

def markdown(result):
    lines=['# Final Statistics Verification','',f"Status: **{result['status']}**. Independent numerical verification of existing saved results; no model execution.",'',
        'The prior v4 full acceptance is reused for scientific provenance, paired inputs, initial references, protected original files and environment integrity. It explicitly stated statistics_recomputed=false, so this verification adds the previously uncovered independent arithmetic check. It does not repeat the environment scan.','',
        f"Prior receipt: `{V4}`; SHA256 `{V4_SHA}`.",
        f"Numerical source: `{STAT}`; complete input paths and SHA256 are in STATISTICS_INPUT_INDEX.json and RAW_CSV_INDEX.json.",'',
        'All 1200 CSV files (28800 rows) were each read once into a hash-checked buffer matched to their receipt and saved statistics manifest. All sixteen saved numerical outputs, including every 20000 method and 16000 paired bootstrap row, matched the independent calculations. Numeric comparisons use absolute tolerance 1e-14 and relative tolerance 1e-12; categorical fields and all 80000 bootstrap indices match exactly.','',
        '## Method means and rates','', '| Method | Mean service loss | Gate-open rate | RI rate |','|---|---:|---:|---:|']
    for r in result['method_summaries']: lines.append(f"| {r['method']} | {r['mean_lifecycle_service_loss']:.17g} | {r['gate_open_rate']:.17g} | {r['ri_rate']:.17g} |")
    lines+=['','## Observed paired contrasts','', '| Contrast | Observed difference | 95% interval |','|---|---:|---|']
    for r in result['contrasts']: lines.append(f"| {r['comparison']} | {r['mean_difference']:.17g} | [{r['ci_low']:.17g}, {r['ci_high']:.17g}] |")
    lines+=['','The P7.7-minus-B8 interval crosses zero. Neither superiority nor statistical equivalence is supported. The three other marginal paired intervals lie below zero; this is the saved 95% interval protocol, without a new multiplicity adjustment or a claim of simultaneous family-wise coverage.','',
        '## Protocol and scenario verification','',
        'The endpoint is the mean of 24 stage service losses, then the mean of 3 seeds and 4 scenarios within each center, then an equal mean over 20 centers. Action cost is reported separately and never added to the service-loss endpoint. Resampling uses center as the unit. NumPy default_rng(2904) generates exactly the saved 4000×20 int64 index matrix. The same draw matrix is reused jointly for all methods, paired differences, and descriptive scenario intervals. Percentile endpoints use linear 2.5% and 97.5% quantiles. Point estimates come from the original observed center means, not the mean of bootstrap replicates. All 80 leave-one-center-out contrasts also match.','',
        '| Method | C0 | C1 | C3 | C4 |','|---|---:|---:|---:|---:|']
    for m in METHODS:
        values=[next(r['lifecycle_service_loss'] for r in result['scenarios'] if r['method']==m and r['scenario']==q) for q in SCENARIOS]
        lines.append('| '+m+' | '+' | '.join(format(x,'.17g') for x in values)+' |')
    lines+=['','All scenario action counts, rates, action costs and saved descriptive intervals were compared, not just the displayed means. C0 and C1 do not support a universal Proposed-wins-every-scenario claim.','',
        '## Search work and saved timer evidence','',
        '| Method | Candidate count total | Charged search updates | Actual attributed decision seconds | Standalone estimated seconds |','|---|---:|---:|---:|---:|']
    for r in result['runtime_search_summaries']:
        lines.append('| '+r['method']+' | '+' | '.join(format(r[f+'_total_recorded'],'.17g') for f in ('feasible_candidate_count','ri_search_updates_charged','decision_runtime_actual_s','decision_runtime_standalone_estimate_s'))+' |')
    lines+=['','Every stage satisfies charged RI updates = 50 × feasible candidate count. These are recorded eligible-candidate counts and charged algorithmic updates; 50 is per candidate and is not a global search budget. core/p7.py lines 299–310 define the cached decision-call attribution and the standalone estimate. All saved cache-hit counters are zero in this inventory, and these two runtime columns happen to agree. Their meanings remain distinct. Neither column measures full end-to-end experiment walltime, total CPU/GPU work, complete resource usage, or energy; those quantities are NOT_VERIFIED by these CSV timers.','',
        '## Offline diagnostics and denominators','', '| Metric | Count | Denominator | Rate |','|---|---:|---:|---:|']
    for r in result['diagnostics']: lines.append(f"| {r['metric']} | {r['count']} | {r['denominator']} | {r['rate']:.17g} |")
    lines+=['','unnecessary RI means action=ri and R_B50≥0. missed escalation means action≠ri and R_B50<0; it is not restricted to closed-gate cases. The denominator for both is all 5760 Proposed stages. The four masks may overlap and are not exhaustive. They use saved finite-reference offline labels, not verified online counterfactual outcomes. Missed escalation remains a method limitation.','',
        '## Scope and preservation','',
        'The original-versus-corrected tables also match their saved original summaries; no original inference was rerun and changes are not causal attribution. This remains an integrity-correction replication on previously observed inputs, not new unseen held-out evidence. Historical environment numerical equivalence remains NOT_VERIFIED. No manuscript section is automatically frozen.','',
        'Evidence implementation: verify_statistics.py. Detailed fresh comparisons: STATISTICS_VERIFICATION.json. Hash-bound source and input index: STATISTICS_INPUT_INDEX.json. Full raw paths and hashes (without copying raw CSV): RAW_CSV_INDEX.json.']
    return '\n'.join(lines)+'\n'

def main():
    start=time.monotonic(); e=Evidence()
    require(not (OUT/'STATISTICS_VERIFICATION.json').exists(),'unique verification output already exists')
    try:
        result=verify(e); e.unchanged_metadata()
        result.update({'created_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-start,'verifier_sha256':sha(Path(__file__).read_bytes()),'evidence_file_count':len(e.index),'evidence_bytes_read':sum(v['bytes'] for v in e.index.values())})
        write_new('RAW_CSV_INDEX.json',json_bytes({'schema':'paper3-independent-raw-csv-index-v1','count':len(e.raw_index),'files':e.raw_index}))
        write_new('STATISTICS_INPUT_INDEX.json',json_bytes({'schema':'paper3-statistics-verification-input-index-v1','files':e.index}))
        write_new('STATISTICS_VERIFICATION.json',json_bytes(result))
        write_new('FINAL_STATISTICS_VERIFICATION.md',markdown(result).encode())
        print(json.dumps({'status':'PASS','elapsed_seconds':result['elapsed_seconds'],'comparisons':len(e.comparisons),'max_abs_difference':max(x.get('max_abs_difference',0) for x in e.comparisons.values()),'output_dir':str(OUT)}),flush=True)
    except Exception as error:
        failure={'status':'BLOCKED','error':repr(error),'traceback':traceback.format_exc(),'completed_comparisons':e.comparisons,'created_utc':datetime.now(timezone.utc).isoformat()}
        write_new('STATISTICS_VERIFICATION_FAILURE.json',json_bytes(failure)); raise

if __name__=='__main__': main()
