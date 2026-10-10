"""Separate, gated statistics for the authorized independent batch20 replication.

Top-level import is standard-library only. No original runner, generator, model,
training or old statistics entry point is imported or executed. Real arithmetic
is available only through run_statistics after complete scientific/phase gates.
Pure aggregation helpers accept small synthetic contracts for independent tests.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import types
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
RESULTS_ROOT = REPOSITORY/"results/p7_7_integrity_replication_batch20_v1"
EXECUTOR_ROOT = REPOSITORY/"verification/paper3_canonical_inputs/replication_executor_batch20_v1"
INPUT_RUN = REPOSITORY/"verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1/CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"
CENTERS = tuple(range(33000,33020))
SEEDS = (7311,7312,7313)
SCENARIOS = ("C0","C1","C3","C4")
METHODS = ("B0","B1","B2","B8","P7.7")
CONFIG_IDS = ("B0_Frozen_ratio10","B1_AlwaysMaintainP50_ratio10","B2_RAVM_ratio10","B8_AlwaysOpen_ratio10","P7_7_RECOVERABILITY_GUIDED_ratio10_grid33")
STAGES = 24
BOOTSTRAP_SEED = 2904
BOOTSTRAP_DRAWS = 4000
STATISTICS_ID = "P7_7_JOINT_CENTER_STATISTICS_BATCH20_V1"
OUTPUT_PREFIX = "statistics_batch20_v1"
CENTER_COLUMNS = ("lifecycle_service_loss","maintenance_count","maintenance_rate","ri_count","ri_rate",
                  "maintenance_cost","ri_cost","total_action_cost","retain_rate","gate_open_rate")
ROW_FIELDS = ("method","center_id","seed","scenario","stage","service_mse","action","gate_open",
              "event_cost_raw","best_local_policy","R_B50")


class StatisticsIntegrityError(RuntimeError):
    pass


def _assert(value,message):
    if not value: raise StatisticsIntegrityError(message)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def _number(value,name):
    _assert(type(value) is not bool,f"boolean numeric value: {name}")
    try: result = float(value)
    except (TypeError,ValueError) as error: raise StatisticsIntegrityError("invalid numeric value: "+name) from error
    _assert(math.isfinite(result),"nonfinite existing record value: "+name)
    return result


def _integer(value,name):
    result = _number(value,name)
    _assert(result.is_integer(),"nonintegral record value: "+name)
    return int(result)


def _mean(values):
    _assert(bool(values),"empty scientific aggregation")
    return math.fsum(values)/len(values)


def aggregate_rows(rows, *, centers=CENTERS,seeds=SEEDS,scenarios=SCENARIOS,methods=METHODS,
                   stages=STAGES,service_unit=None):
    """Stage -> trajectory -> center aggregation, never stages as independent units.

    fsum/count implements the frozen arithmetic means with finite float64 CSV
    values. Floating summation need not be bit-identical to historical pandas.
    Optional alternate contracts are strictly for synthetic tests; real wrapper
    always passes the frozen 20x3x4x5x24 constants.
    """
    expected = {(method,center,seed,scenario) for method in methods for center in centers
                for seed in seeds for scenario in scenarios}
    grouped = defaultdict(dict)
    normalized = []
    for incoming in rows:
        _assert(all(name in incoming for name in ROW_FIELDS),"missing original statistics field")
        row = {"method":str(incoming["method"]),"center_id":_integer(incoming["center_id"],"center_id"),
               "seed":_integer(incoming["seed"],"seed"),"scenario":str(incoming["scenario"]),
               "stage":_integer(incoming["stage"],"stage"),"action":str(incoming["action"]),
               "best_local_policy":str(incoming["best_local_policy"])}
        for name in ("service_mse","event_cost_raw","R_B50"):
            row[name] = _number(incoming[name],name)
        row["gate_open"] = _integer(incoming["gate_open"],"gate_open")
        _assert(row["service_mse"]>=0 and row["event_cost_raw"]>=0,"negative existing loss/cost")
        _assert(row["action"] in {"retain","local","ri"} and row["gate_open"] in {0,1},"invalid action/gate indicator")
        _assert(row["action"]!="ri" or row["gate_open"]==1,"RI without open gate")
        key = (row["method"],row["center_id"],row["seed"],row["scenario"])
        _assert(key in expected,"record outside fixed statistics contract")
        _assert(1<=row["stage"]<=stages and row["stage"] not in grouped[key],"duplicate/out-of-range stage")
        if service_unit is not None:
            cost = 10*(.1*service_unit) if row["action"]=="ri" else .1*service_unit if row["action"]=="local" else 0.
            _assert(math.isclose(row["event_cost_raw"],cost,rel_tol=1e-12,abs_tol=1e-15),"existing frozen action-cost unit differs")
        grouped[key][row["stage"]] = row
        normalized.append(row)
    _assert(set(grouped)==expected,"incomplete trajectory matrix; no exclusion or imputation permitted")
    trajectories = []
    for method in methods:
        for center in centers:
            for seed in seeds:
                for scenario in scenarios:
                    records = grouped[method,center,seed,scenario]
                    _assert(set(records)==set(range(1,stages+1)),"incomplete 24-stage trajectory")
                    records = [records[stage] for stage in range(1,stages+1)]
                    result = {"method":method,"center_id":center,"seed":seed,"scenario":scenario,
                              "lifecycle_service_loss":_mean([row["service_mse"] for row in records]),
                              "stages":stages}
                    for action,prefix in (("local","maintenance"),("ri","ri"),("retain","retain")):
                        result[prefix+"_count"] = sum(row["action"]==action for row in records)
                        result[prefix+"_rate"] = result[prefix+"_count"]/stages
                    result["gate_open_count"] = sum(row["gate_open"] for row in records)
                    result["gate_open_rate"] = result["gate_open_count"]/stages
                    result["maintenance_cost"] = math.fsum(row["event_cost_raw"] for row in records if row["action"]=="local")
                    result["ri_cost"] = math.fsum(row["event_cost_raw"] for row in records if row["action"]=="ri")
                    result["total_action_cost"] = math.fsum(row["event_cost_raw"] for row in records)
                    trajectories.append(result)
    center_rows,scenario_center_rows,scenario_rows = [],[],[]
    for method in methods:
        for center in centers:
            selected = [row for row in trajectories if row["method"]==method and row["center_id"]==center]
            _assert(len(selected)==len(seeds)*len(scenarios),"center aggregation incomplete")
            center_rows.append({"method":method,"center_id":center,**{name:_mean([row[name] for row in selected]) for name in CENTER_COLUMNS}})
            for scenario in scenarios:
                selected_scenario = [row for row in selected if row["scenario"]==scenario]
                _assert(len(selected_scenario)==len(seeds),"scenario-center seed aggregation incomplete")
                scenario_center_rows.append({"method":method,"center_id":center,"scenario":scenario,
                    **{name:_mean([row[name] for row in selected_scenario]) for name in CENTER_COLUMNS}})
        for scenario in scenarios:
            selected = [row for row in scenario_center_rows if row["method"]==method and row["scenario"]==scenario]
            _assert(len(selected)==len(centers),"scenario strata need complete centers")
            scenario_rows.append({"method":method,"scenario":scenario,"n_centers":len(centers),
                                  **{name:_mean([row[name] for row in selected]) for name in CENTER_COLUMNS}})
    proposed = [row for row in normalized if row["method"]=="P7.7"]
    _assert(proposed,"Proposed diagnostic stages missing")
    masks = {
        "correct retain":lambda row:row["action"]=="retain" and row["best_local_policy"]=="P0",
        "unnecessary RI":lambda row:row["action"]=="ri" and not row["R_B50"]<0.,
        "correct escalation":lambda row:row["action"]=="ri" and row["R_B50"]<0.,
        "missed escalation":lambda row:row["action"]!="ri" and row["R_B50"]<0.,
    }
    diagnostics = [{"metric":name,"count":sum(predicate(row) for row in proposed),
                    "rate":sum(predicate(row) for row in proposed)/len(proposed),"denominator":len(proposed)}
                   for name,predicate in masks.items()]
    return {"trajectory":trajectories,"center":center_rows,"scenario_center":scenario_center_rows,
            "scenario":scenario_rows,"diagnostics":diagnostics,"row_count":len(normalized)}


def joint_center_tables(aggregates, *, centers=CENTERS,methods=METHODS,scenarios=SCENARIOS,
                        draws=BOOTSTRAP_DRAWS,seed=BOOTSTRAP_SEED):
    """Exactly one joint draw matrix for every method, contrast and scenario stratum."""
    import numpy as np
    _assert(type(draws) is int and draws>0 and len(centers)>=2,"invalid synthetic/real center bootstrap contract")
    center = {(row["method"],row["center_id"]):row for row in aggregates["center"]}
    _assert(len(center)==len(aggregates["center"]) and set(center)=={(m,c) for m in methods for c in centers},"unique complete method-center rows required")
    matrix = np.asarray([[center[method,c]["lifecycle_service_loss"] for c in centers] for method in methods],dtype=np.float64)
    _assert(bool(np.isfinite(matrix).all()),"nonfinite center endpoint")
    indices = np.random.default_rng(seed).integers(0,len(centers),size=(draws,len(centers)),dtype=np.int64)
    sampled_means = matrix[:,indices].mean(axis=2)
    summaries,method_bootstrap,contrasts,paired_bootstrap,loo = [],[],[],[],[]
    for number,method in enumerate(methods):
        values = matrix[number]
        low,high = np.quantile(sampled_means[number],[.025,.975],method="linear")
        summaries.append({"method":method,"mean_lifecycle_service_loss":_mean(values.tolist()),
                          "ci_low":float(low),"ci_high":float(high),"n_centers":len(centers),
                          **{name:_mean([center[method,c][name] for c in centers]) for name in CENTER_COLUMNS if name!="lifecycle_service_loss"}})
        method_bootstrap.extend({"method":method,"bootstrap_id":i,"lifecycle_service_loss":float(value)}
                                for i,value in enumerate(sampled_means[number]))
    _assert("P7.7" in methods,"Proposed endpoint absent")
    proposed_index = methods.index("P7.7")
    for number,baseline in enumerate(methods):
        if baseline=="P7.7": continue
        differences = matrix[proposed_index]-matrix[number]
        samples = differences[indices].mean(axis=1)
        low,high = np.quantile(samples,[.025,.975],method="linear")
        comparison = f"P7.7 - {baseline}"
        contrasts.append({"comparison":comparison,"mean_difference":_mean(differences.tolist()),
                          "ci_low":float(low),"ci_high":float(high),"n_centers":len(centers),
                          "bootstrap_resamples":draws,"bootstrap_seed":seed,
                          "point_estimate_source":"OBSERVED_PAIRED_CENTER_MEAN_DIFFERENCES"})
        paired_bootstrap.extend({"comparison":comparison,"bootstrap_id":i,"difference":float(value)}
                                for i,value in enumerate(samples))
        loo.extend({"comparison":comparison,"omitted_center":int(omitted),
                    "difference":_mean([float(differences[i]) for i,c in enumerate(centers) if c!=omitted])}
                   for omitted in centers)
    strata = {(row["method"],row["center_id"],row["scenario"]):row for row in aggregates["scenario_center"]}
    _assert(len(strata)==len(aggregates["scenario_center"]) and set(strata)=={(m,c,q) for m in methods for c in centers for q in scenarios},"unique complete scenario-center strata required")
    scenario_summary = []
    for method in methods:
        for scenario in scenarios:
            values = np.asarray([strata[method,c,scenario]["lifecycle_service_loss"] for c in centers],dtype=np.float64)
            _assert(bool(np.isfinite(values).all()),"nonfinite scenario-center endpoint")
            low,high = np.quantile(values[indices].mean(axis=1),[.025,.975],method="linear")
            scenario_summary.append({"method":method,"scenario":scenario,"n_centers":len(centers),
                **{name:_mean([strata[method,c,scenario][name] for c in centers]) for name in CENTER_COLUMNS},
                "ci_low":float(low),"ci_high":float(high),"ci_scope":"ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL"})
    return {"indices":indices,"method":summaries,"method_bootstrap":method_bootstrap,"contrasts":contrasts,
            "bootstrap":paired_bootstrap,"loo":loo,"scenario":scenario_summary}


def _bound_executor_modules(manifest):
    """Import only the new frozen stdlib-only integrity reader and provenance module."""
    package_name = "paper3_statistics_bound_executor"
    _assert(package_name not in sys.modules,"statistics gate loader requires fresh process")
    package = types.ModuleType(package_name)
    package.__path__ = [str(EXECUTOR_ROOT)]
    sys.modules[package_name] = package
    loaded = {}
    for name in ("provenance","executor_driver"):
        path = EXECUTOR_ROOT/(name+".py")
        expected = manifest["executor_sha256"].get(name+".py")
        _assert(expected is not None and hashlib.sha256(path.read_bytes()).hexdigest()==expected,"frozen integrity reader source changed")
        spec = importlib.util.spec_from_file_location(package_name+"."+name,path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        loaded[name] = module
        _assert(hashlib.sha256(path.read_bytes()).hexdigest()==expected,"integrity reader changed during import")
    return loaded["provenance"],loaded["executor_driver"]


def _strict_manifest(path):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            _assert(key not in result,"duplicate statistics-gate JSON key")
            result[key] = value
        return result
    def invalid(value): raise StatisticsIntegrityError("nonfinite statistics-gate JSON")
    return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=unique,parse_constant=invalid)


def _bind(bindings,path,provenance):
    path = provenance.regular_path(path)
    digest = provenance.file_sha256(path)
    existing = bindings.setdefault(str(path),digest)
    _assert(existing==digest,"input binding changed during statistics gate")
    return path


def validate_statistics_gate(repo,results_root, *, expected_manifest_digest):
    """No outcome statistics until all 1200/240 actual records and end proofs pass."""
    _assert(Path(repo).resolve()==REPOSITORY and Path(results_root).resolve()==RESULTS_ROOT,"wrong statistics repository/results root")
    manifest_path = RESULTS_ROOT/"provenance_manifest.json"
    manifest = _strict_manifest(manifest_path)
    _assert(manifest.get("manifest_digest")==expected_manifest_digest,"explicit expected replication manifest digest differs")
    p,driver = _bound_executor_modules(manifest)
    p.verify_frozen(manifest,repo,INPUT_RUN,results_root,verify_environment=True,full=True,check_inputs=True)
    bindings = {}
    _bind(bindings,manifest_path,p)
    gate_path = _bind(bindings,p.checked_path(RESULTS_ROOT,"full_experiment_integrity_gate.json"),p)
    gate = p.read_json(gate_path)
    expected = {"scientific_integrity_pass":True,"manifest_digest":manifest["manifest_digest"],
                "trajectories":1200,"paired_groups":240,"old_results_reused":False,"all_inputs_F1":True,
                "future_flags_false":True,"outcomes_used_to_select_protocol":False,
                "point_estimates_or_bootstrap_not_yet_computed":True,"not_unseen_heldout":True}
    _assert(all(gate.get(name)==value for name,value in expected.items()),"complete pre-statistics full integrity gate missing")
    minimum = p.read_json(_bind(bindings,p.checked_path(RESULTS_ROOT,"stage_c_minimal_gate.json"),p))
    _assert(minimum.get("stage_c_pass") is True and minimum.get("manifest_digest")==manifest["manifest_digest"]
            and minimum.get("completed_trajectories")==5 and minimum.get("predeclared_group")=="33000/7311/C0"
            and minimum.get("performance_used_for_gate") is False,"predeclared Stage C gate missing")
    request_tasks = {}
    for phase in ("initial","minimal","full"):
        completion = p.read_json(_bind(bindings,p.checked_path(RESULTS_ROOT,f"execution/{phase}/completion.json"),p))
        _assert(completion.get("success") is True and completion.get("phase")==phase and
                completion.get("worker_exit_codes") and all(type(code) is int and code==0 for code in completion["worker_exit_codes"].values()),"phase worker completion proof missing")
        end = p.read_json(_bind(bindings,p.checked_path(RESULTS_ROOT,f"execution/{phase}/phase_integrity_end.json"),p))
        _assert(end.get("manifest_digest")==manifest["manifest_digest"] and all(end.get(name) is True for name in
                ("critical_scientific_bytes_unchanged","environment_file_bytes_checked","original_full_snapshot_checked","all_F1_inputs_checked")),"phase end byte/environment/input proof missing")
        phase_tasks = []
        for worker,code in completion["worker_exit_codes"].items():
            request_path = _bind(bindings,p.checked_path(RESULTS_ROOT,f"execution/{phase}/{worker}_request.json"),p)
            request = p.read_json(request_path)
            _assert(request.get("manifest_digest")==manifest["manifest_digest"] and request.get("worker_id")==worker,
                    "phase request provenance differs")
            mode = "initial" if phase=="initial" else "trajectory"
            _assert(request.get("mode")==mode and type(request.get("worker_count")) is int and 1<=request["worker_count"]<=3,
                    "phase worker mode/resource bound differs")
            worker_end = p.read_json(_bind(bindings,p.checked_path(RESULTS_ROOT,
                f"workers/{worker}_{request['attempt_id']}_{mode}.completion.json"),p))
            _assert(worker_end.get("valid") is True and worker_end.get("manifest_digest")==manifest["manifest_digest"] and
                    worker_end.get("request_file_sha256")==p.file_sha256(request_path) and
                    worker_end.get("original_scientific_files_unchanged") is True and worker_end.get("statistics_executed") is False,
                    "individual worker final proof missing")
            phase_tasks.extend(request["cases" if phase=="initial" else "tasks"])
        request_tasks[phase] = phase_tasks
    expected_initial = [{"center_id":c,"seed":s} for c in CENTERS for s in SEEDS]
    expected_tasks = driver.tasks()
    _assert(request_tasks["initial"]==expected_initial,"initial 60-case execution contract differs")
    key = lambda task:tuple(task[name] for name in ("center_id","seed","scenario","method","config_id"))
    _assert(len(request_tasks["minimal"])==5 and set(map(key,request_tasks["minimal"]))==set(map(key,expected_tasks[:5])),"minimal request matrix differs")
    _assert(len(request_tasks["full"])==1195 and set(map(key,request_tasks["full"]))==set(map(key,expected_tasks[5:])),"remaining 1195-task execution matrix differs")
    records = driver.accepted_records(manifest,require_complete=True)
    groups = driver.paired_groups(records)
    _assert(len(records)==1200 and len(groups)==240 and gate["groups"]==groups,"actual raw matrix/group proofs changed after final gate")
    for entry in records.values():
        name = driver.stem(entry["task"])
        for relative in (f"raw/{name}.csv",f"raw/{name}.integrity.json",entry["receipt"]["audit_relative"],
                         entry["receipt"]["rng_relative"],entry["receipt"]["attempt_csv_relative"]):
            _bind(bindings,p.checked_path(RESULTS_ROOT,relative),p)
    initial_path = _bind(bindings,p.checked_path(RESULTS_ROOT,"initial_state_manifest.json"),p)
    for item in p.read_json(initial_path)["states"]:
        for relative in (item["path"],item["receipt_path"]): _bind(bindings,p.checked_path(RESULTS_ROOT,relative),p)
    _bind(bindings,REPOSITORY/"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json",p)
    _bind(bindings,REPOSITORY/"scripts/run_p7_7_final.py",p)
    _bind(bindings,INPUT_RUN/"execution_receipt.json",p)
    _bind(bindings,INPUT_RUN/"contexts/F1.json",p)
    _bind(bindings,Path(__file__),p)
    for file in Path(__file__).parent.rglob("*.py"): _bind(bindings,file,p)
    cfg = manifest["frozen_final_configuration"]
    _assert(tuple(cfg["final_population"]["centers"])==CENTERS and tuple(cfg["final_population"]["seeds"])==SEEDS and
            tuple(cfg["final_population"]["scenarios"])==SCENARIOS,"frozen statistics population differs")
    _assert(tuple((item["method"],item["config_id"]) for item in cfg["comparators"])==tuple(zip(METHODS,CONFIG_IDS)),"frozen comparator order differs")
    plan = cfg["statistical_plan"]
    _assert(plan["unit"]=="center" and plan["bootstrap_resamples"]==BOOTSTRAP_DRAWS and plan["bootstrap_seed"]==BOOTSTRAP_SEED
            and plan["interval"]=="percentile 95% interval using NumPy linear quantiles" and plan["winner_ranking"] is False
            and plan["scenario_stratified_reporting"] is True and plan["leave_one_center_out"] is True,"frozen statistical definitions differ")
    return {"manifest":manifest,"provenance":p,"records":records,"groups":groups,"bindings":bindings,"config":cfg}


def _read_outcome_rows(gate):
    p,rows = gate["provenance"],[]
    for entry in gate["records"].values():
        task = entry["task"]
        name = next(name for name,candidate in gate["records"].items() if candidate is entry)
        path = p.checked_path(RESULTS_ROOT,f"raw/{name}.csv")
        _assert(p.file_sha256(path)==entry["csv_sha256"],"raw CSV changed before outcome read")
        with path.open("r",encoding="utf-8-sig",newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            _assert(len(header)==len(set(header)) and set(ROW_FIELDS)<=set(header),"invalid outcome CSV header")
            projection = {name:header.index(name) for name in ROW_FIELDS}
            for tokens in reader:
                _assert(len(tokens)==len(header),"invalid outcome CSV record width")
                row = {name:tokens[index] for name,index in projection.items()}
                _assert(row["method"]==task["method"] and row["scenario"]==task["scenario"] and
                        int(row["center_id"])==task["center_id"] and int(row["seed"])==task["seed"],"outcome CSV task differs")
                rows.append(row)
        _assert(p.file_sha256(path)==entry["csv_sha256"],"raw CSV changed during outcome read")
    _assert(len(rows)==28800,"complete 28800-stage outcome matrix required")
    return rows


def _csv_bytes(rows):
    _assert(bool(rows),"empty statistics output table")
    fields = list(rows[0])
    _assert(all(set(row)==set(fields) for row in rows),"statistics output schema varies")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream,fieldnames=fields,lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def run_statistics(repo,results_root, *, expected_manifest_digest):
    """Authorized Stage E entry: never mix old records or execute their statistics."""
    _assert(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,"statistics requires -I -S -B")
    gate = validate_statistics_gate(repo,results_root,expected_manifest_digest=expected_manifest_digest)
    p,manifest = gate["provenance"],gate["manifest"]
    _assert(not (RESULTS_ROOT/OUTPUT_PREFIX).exists(),"statistics output already exists; no overwrite/reselection permitted")
    p.require_isolation(RESULTS_ROOT)
    p.install_write_guard(RESULTS_ROOT)
    p.install_generator_guard(REPOSITORY)
    # Extend only the separately frozen new statistics implementation into the
    # import allowlist. Original scientific files and executor bindings are intact.
    from .runtime_guard import install_statistics_import_guard
    install_statistics_import_guard(manifest,gate["bindings"],p)
    site = manifest["environment"]["site_packages_root"]
    if site not in sys.path: sys.path.append(site)
    rows = _read_outcome_rows(gate)
    aggregates = aggregate_rows(rows,service_unit=float(gate["config"]["service_unit"]))
    _assert(len(aggregates["trajectory"])==1200 and len(aggregates["center"])==100 and
            len(aggregates["scenario_center"])==400 and len(aggregates["diagnostics"])==4,"scientific aggregation coverage differs")
    tables = joint_center_tables(aggregates)
    import numpy as np
    matrix = tables.pop("indices")
    _assert(matrix.shape==(4000,20) and matrix.dtype==np.dtype("int64"),"joint index matrix differs")
    buffer = io.BytesIO()
    np.save(buffer,matrix,allow_pickle=False)
    output_bytes = {"joint_center_resample_indices.npy":buffer.getvalue()}
    mapping = {"final_metrics_by_trajectory.csv":aggregates["trajectory"],"final_metrics_by_center.csv":aggregates["center"],
        "final_metrics_by_scenario_center.csv":aggregates["scenario_center"],"final_metrics_by_method.csv":tables["method"],
        "final_metrics_by_scenario.csv":tables["scenario"],"final_paired_contrasts.csv":tables["contrasts"],
        "final_method_bootstrap.csv":tables["method_bootstrap"],"final_paired_bootstrap.csv":tables["bootstrap"],
        "final_loo.csv":tables["loo"],"final_decision_diagnostics.csv":aggregates["diagnostics"]}
    output_bytes.update({name:_csv_bytes(value) for name,value in mapping.items()})
    # Recheck all input bytes after arithmetic, before any result publication.
    for filename,expected in gate["bindings"].items():
        _assert(p.file_sha256(filename)==expected,"statistics input changed before publication")
    p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
    outputs = {}
    for name,payload in output_bytes.items():
        publication = p.publish_bytes(RESULTS_ROOT,OUTPUT_PREFIX+"/"+name,payload)
        outputs[name] = publication["sha256"]
    protocol = {"statistics_id":STATISTICS_ID,"resampling_unit":"center","centers":list(CENTERS),
        "aggregation":"24-stage mean -> seed/scenario mean within center -> mean across 20 centers",
        "bootstrap_resamples":4000,"bootstrap_seed":2904,"interval":"percentile 95%, NumPy method=linear",
        "one_joint_index_matrix_for_all_methods_contrasts_scenarios":True,"observed_point_estimates_from_original_center_means":True,
        "historical_draw_sequence_reproduced":False,
        "historical_difference":"Original runner advanced different draws per method/contrast; independent authorized replication shares one matrix.",
        "floating_aggregation":"finite float64 values, fsum/count arithmetic means; not bit-identical historical pandas claim",
        "diagnostics":"Same four frozen offline-label masks, overlapping, denominator=5760 Proposed stages",
        "cost_semantics":"Raw selected-action costs separately reported; no addition to primary service endpoint",
        "new_unseen_heldout_claimed":False,"winner_ranking":False,"no_outcome_based_selection":True,
        "no_original_records_reused":True,"no_exclusions":True,"models_or_generators_executed":False}
    statistics_manifest = {"schema":"paper3-joint-center-statistics-manifest-v1","protocol":protocol,
        "replication_manifest_digest":manifest["manifest_digest"],"input_bundle_digest":manifest["input_bundle_digest"],
        "input_bindings_sha256":gate["bindings"],"outputs_sha256":outputs,
        "counts":{"raw_trajectories":1200,"five_method_groups":240,"stages":28800,"center_method_rows":100,
                  "scenario_center_rows":400,"paired_bootstrap_rows":16000,"method_bootstrap_rows":20000,"loo_rows":80},
        "implementation_files_sha256":{str(file):p.file_sha256(file) for file in Path(__file__).parent.rglob("*.py")},
        "created_utc":datetime.now(timezone.utc).isoformat()}
    publication = p.publish_json(RESULTS_ROOT,OUTPUT_PREFIX+"/statistics_manifest.json",statistics_manifest)
    for filename,expected in gate["bindings"].items():
        _assert(p.file_sha256(filename)==expected,"statistics input changed after publication")
    p.verify_frozen(manifest,verify_environment=True,full=True,check_inputs=True)
    for name,expected in outputs.items():
        _assert(p.file_sha256(p.checked_path(RESULTS_ROOT,OUTPUT_PREFIX+"/"+name))==expected,"statistics output changed before receipt")
    receipt = {"schema":"paper3-statistics-execution-receipt-v1","status":"COMPLETED","exit_code":0,
        "statistics_id":STATISTICS_ID,"replication_manifest_digest":manifest["manifest_digest"],
        "statistics_manifest_sha256":publication["sha256"],"outputs_sha256":outputs,"originals_unchanged":True,
        "models_or_generators_executed":False,"new_output_only":True,"joint_resampling_verified":True,
        "created_utc":datetime.now(timezone.utc).isoformat()}
    p.publish_json(RESULTS_ROOT,OUTPUT_PREFIX+"/statistics_execution_receipt.json",receipt)
    return receipt
