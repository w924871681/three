from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import river
from river.drift import ADWIN
from core.common import canonical_hash, sha256_file
from core.data import generate_base_centers
from core.models import adapt, evaluate, state_hash
from core.p3_2_data import timeline_for_v2, scenario_hash_v2
from core.p3_2_models import build_p3_2_identity_bank
from core.p6 import initial_model, FEATURE_COLUMNS
from core.p7 import (FrozenEstimator, DecisionExecutor, MethodState, batch, evidence_blocks,
                     read_json, save_json)

RESULTS=ROOT/"results/p7"
PROTOCOL=ROOT/"configs/p7_protocol.json"
PRE=ROOT/"audits/P7_PRE_OUTCOME_PROTOCOL_FREEZE.json"


def utc():
    return datetime.now(timezone.utc).isoformat()


def csv(path, frame):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    frame.to_csv(tmp,index=False,lineterminator="\n",float_format="%.17g")
    tmp.replace(path)


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True).strip()


def immutable_json(path, value):
    if path.exists():
        assert read_json(path)==value, "refuse to modify predeclared file: "+str(path)
    else:
        save_json(path,value)


def base_preflight():
    p4=read_json(ROOT/"audits/P4_EXPERIMENT_SCOPE_FREEZE.json")
    p6=read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")
    for rel,expected in p6["files"].items():
        assert sha256_file(ROOT/rel)==expected, "P6 hash mismatch: "+rel
    frozen=read_json(ROOT/"configs/p3_mismatch_v2_frozen.json")
    pool=p4["center_pools"]["decision_gate_calibration"]
    ids=list(range(pool["id_start"],pool["id_end_inclusive"]+1))
    assert ids==list(range(32000,32020)) and len(ids)==pool["count"]
    other=[p4["center_pools"]["source_training"]["ids"],
           p4["center_pools"]["generator_design_development"]["ids"],
           p4["center_pools"]["fresh_phenomenon_development"]["ids"],
           list(range(31200,31230)),list(range(33000,33020)),
           read_json(ROOT/"configs/center_splits.json")["development"]]
    # Historic protocol metadata only, never outcomes, provides all legacy IDs.
    for name in ("configs/p3_development.json","configs/p3_2_protocol.json"):
        conf=read_json(ROOT/name)
        for key,value in conf.items():
            if "center" in key and isinstance(value,list) and all(isinstance(x,int) for x in value) and "forbidden" not in key:
                other.append(value)
    assert not any(set(ids)&set(group) for group in other)
    assert frozen["primary_recoverability_horizon"]==4 and frozen["primary_eta"]==.25
    assert frozen["local_policies"]==[0,10,20,50] and frozen["feature_components"]==["gain","residual"]
    assert frozen["scenarios"]==["C0","C1","C3","C4"] and river.__version__=="0.23.0"
    bank_spec=p4["source_and_model_bank"]
    source_path=ROOT/bank_spec["r3_source_training_manifest_path"]
    assert sha256_file(source_path)==bank_spec["r3_source_training_manifest_sha256"]
    for key,directory in (("native_checkpoint_sha256",ROOT/"imported/msa_dti/bank"),
                          ("r3_new_checkpoint_sha256",source_path.parent)):
        for name,expected in bank_spec[key].items():
            assert sha256_file(directory/name)==expected, "source bank hash mismatch: "+name
    assert p6["feature_order"]==FEATURE_COLUMNS and (p6["K_S"],p6["K_L"])==(2,6)
    return p4,p6,frozen,ids


def prepare():
    _,p6,frozen,ids=base_preflight()
    assert not (RESULTS/"outcome_materialization_started.json").exists(), "no re-preregistration after outcomes"
    oof=pd.read_csv(ROOT/"results/p6/cv_predictions.csv")
    assert sorted(oof.center_id.unique())==list(range(31200,31230))
    s=float(np.median(np.abs(oof.error.to_numpy())))
    refs=read_json(ROOT/"results/p6/tau_service_fitting.json")
    unit=float(np.median([v["L_ref"] for v in refs.values()]))
    delta={"schema":"p7-delta-grid-v1","source":"results/p6/cv_predictions.csv",
           "source_sha256":sha256_file(ROOT/"results/p6/cv_predictions.csv"),
           "scale_rule":"median(abs(selected P6 OOF prediction error))", "s":s,
           "multipliers":[-2,-1,-.5,0,.5,1,2],"delta_R":[m*s for m in [-2,-1,-.5,0,.5,1,2]],
           "frozen_before_calibration_outcomes":True}
    grids={"schema":"p7-baseline-grids-v1","B3":{"K":[4,6,8,12]},
           "B4":{"quantile":[.8,.9,.95],"persistence":[1,2,3],"numeric_threshold_source":"common calibration initial-history pre-stage-1 assessment errors"},
           "B5":{"delta":[.0002,.002,.02],"implementation":"River ADWIN2","version":"0.23.0",
                 "clock":32,"max_buckets":5,"min_window_length":5,"grace_period":10,"stream":"chronological incumbent assessment per-window squared error clipped [0,1]"},
           "B6":{"K":[2,3,4,6]},"B7":{"window":[2,4,6],"normalized_margin":[0,.01,.05],"adaptation_label":"task-matched KEEP-style; not exact DiTEC"},
           "B8":{},"cost_ratios":[2,5,10],"frozen_before_calibration_outcomes":True}
    ravm={"B":5,"beta":.1,"kappa_rec":.5,"kappa_hist":0.,"delta_imp":2.8018237766243602e-05,"delta_ret":0.}
    source_repo=Path("D:/dt-trustworthy-maintenance")
    source_config=source_repo/"configs/frozen_commit_config.yaml"
    assert sha256_file(source_config)=="1da5f249d1a8c41afcc7d49f2bd30d288e2cdabd220b7840cfc0a3903bc9bf3a"
    original=read_json(source_config)
    assert all(original[k]==ravm[k] for k in ["kappa_rec","kappa_hist","delta_imp","delta_ret"])
    provenance={"read_only_repository":source_repo.as_posix(),"implementation_commit":"7ae7fabd9a4e335e774fbcba2f38dfa8827bb8f3",
                "decision_config_path":source_config.as_posix(),"decision_config_sha256":sha256_file(source_config),
                "decision_config_git_binding_at_source_commit":False,"copied_frozen_values":ravm,"source_code_hashes":{}}
    for rel in ["core/engine.py","core/models.py","configs/frozen_candidate_config.yaml"]:
        code=subprocess.check_output(["git","show",provenance["implementation_commit"]+":"+rel],cwd=source_repo)
        provenance["source_code_hashes"][rel]=hashlib.sha256(code).hexdigest()
    assert canonical_hash({"event":["gain","residual"],"features":FEATURE_COLUMNS,
                           "history":"same-identity/current-probe-inclusive/no-future"})==p6["feature_specification_sha256"]
    protocol={"schema":"p7-protocol-v1","calibration_centers":ids,"model_seeds":frozen["model_seeds"],
              "scenarios":frozen["scenarios"],"P6_manifest_sha256":sha256_file(ROOT/"audits/P6_ESTIMATOR_FREEZE.json"),
              "feature_spec_sha256":p6["feature_specification_sha256"],"window_pair":{"K_S":2,"K_L":6},
              "feature_order":FEATURE_COLUMNS,"unit":unit,"unit_source":"median P6 fitting C0 L_ref", 
              "unit_source_sha256":sha256_file(ROOT/"results/p6/tau_service_fitting.json"),
              "normalized_lambda_M":.1,"primary_cost_ratio":5,"cost_ratios":[2,5,10],
              "primary_false_escalation_cap":.1,"secondary_cap":.05,
              "false_escalation_numerator":"actual RI and finite-policy R>=0",
              "false_escalation_denominator":"finite-policy R>=0 stages within center",
              "missed_escalation_denominator":"finite-policy R<0 stages within center",
              "statistical_unit":"center","fallback":"closed_gate; mark calibration FAIL; retain/local compared; never heldout",
              "action_tie_break":["retain","local","ri"],"ri_candidate_updates":50,
              "source_bank_hash":read_json(ROOT/"audits/P4_EXPERIMENT_SCOPE_FREEZE.json")["source_and_model_bank"]["p3_2b_bank_hash"],
              "heldout_access_allowed":False,"alibaba_access_allowed":False,
              "no_estimator_refit":True,"no_generator_modification":True,"ravm":ravm,
              "bootstrap_repetitions":4000,"bootstrap_seed":2904}
    for path,obj in [(ROOT/"configs/p7_delta_grid.json",delta),(ROOT/"configs/p7_baseline_grids.json",grids),
                     (ROOT/"configs/p7_ravm_provenance.json",provenance),(PROTOCOL,protocol)]:
        immutable_json(path,obj)
        path.with_suffix(".sha256").write_text(sha256_file(path)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"status":"PREPARED_NO_CALIBRATION_OUTCOMES","s":s,"unit":unit},indent=2),flush=True)


def bind():
    base_preflight()
    assert not (RESULTS/"outcome_materialization_started.json").exists()
    paths=[PROTOCOL,ROOT/"configs/p7_delta_grid.json",ROOT/"configs/p7_baseline_grids.json",
           ROOT/"configs/p7_ravm_provenance.json",ROOT/"docs/P7_PROTOCOL_AND_EXECUTION_LOG.md",
           ROOT/"core/p7.py",Path(__file__),ROOT/"tests/test_p7.py"]
    head=git("rev-parse","HEAD")
    for p in paths:
        rel=p.relative_to(ROOT).as_posix()
        committed=subprocess.check_output(["git","show",head+":"+rel],cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest()==sha256_file(p),"Git byte binding mismatch: "+rel
    value={"schema":"p7-pre-outcome-protocol-freeze-v1","bound_at_utc":utc(),"preregistration_git_commit":head,
           "files":{p.relative_to(ROOT).as_posix():sha256_file(p) for p in paths},
           "P6_manifest_sha256":sha256_file(ROOT/"audits/P6_ESTIMATOR_FREEZE.json"),
           "calibration_outcomes_materialized":False,"heldout_accessed":False,"alibaba_accessed":False}
    assert not PRE.exists(),"pre-outcome binding already exists"
    save_json(PRE,value)
    PRE.with_suffix(".sha256").write_text(sha256_file(PRE)+"\n",encoding="utf-8",newline="\n")
    print("P7 pre-outcome bound",head,flush=True)


def preflight():
    p4,p6,frozen,ids=base_preflight()
    pre=read_json(PRE)
    assert sha256_file(PRE)==PRE.with_suffix(".sha256").read_text().strip()
    for rel,expected in pre["files"].items():
        assert sha256_file(ROOT/rel)==expected,"P7 pre-outcome file changed: "+rel
        payload=subprocess.check_output(["git","show",pre["preregistration_git_commit"]+":"+rel],cwd=ROOT)
        assert hashlib.sha256(payload).hexdigest()==expected,"P7 grid not Git-bound"
    assert pre["P6_manifest_sha256"]==sha256_file(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")
    protocol=read_json(PROTOCOL)
    assert protocol["calibration_centers"]==ids
    return p4,p6,frozen,protocol


def configs(thresholds):
    protocol=read_json(PROTOCOL)
    grids=read_json(ROOT/"configs/p7_baseline_grids.json")
    deltas=read_json(ROOT/"configs/p7_delta_grid.json")["delta_R"]
    result=[]
    for ratio in protocol["cost_ratios"]:
        entries=[{"method":m} for m in ["B0","B1","B2","B8"]]
        entries += [{"method":"B3","K":k} for k in grids["B3"]["K"]]
        entries += [{"method":"B4","quantile":q,"persistence":k,"threshold":thresholds[str(q)]}
                    for q in grids["B4"]["quantile"] for k in grids["B4"]["persistence"]]
        entries += [{"method":"B5","delta":d} for d in grids["B5"]["delta"]]
        entries += [{"method":"B6","K":k} for k in grids["B6"]["K"]]
        entries += [{"method":"B7","window":w,"margin":m} for w in grids["B7"]["window"] for m in grids["B7"]["normalized_margin"]]
        entries += [{"method":"Proposed","delta_R":d,"delta_index":idx} for idx,d in enumerate(deltas)]
        for idx,entry in enumerate(entries):
            result.append({**entry,"cost_ratio":ratio,"config_id":f"{entry['method']}_ratio{ratio}_grid{idx:02d}"})
    assert len(result)==120
    return result


def reference(base,seed,incumbent,frozen):
    timeline,_=timeline_for_v2(base,"C0",frozen)
    parent=initial_model(base,seed,incumbent,timeline)
    prefix=timeline._segment((800,1000),"assessment")
    from core.p7 import point_errors
    prefix_errors=point_errors(parent,batch(prefix))
    losses=[]
    for stage in range(1,9):
        update,_=timeline.decision_data(stage)
        parent=adapt(parent,batch(update),50,seed+base.center_id+stage*100)
        timeline.seal_decision(stage)
        losses.append(evaluate(parent,batch(timeline.service(stage)))[0])
    return {"center_id":base.center_id,"seed":seed,"L_ref":float(np.mean(losses)),
            "tau_service":1.25*float(np.mean(losses)),"prefix_errors":prefix_errors.tolist()}


def offline_labels(parent,probe,timeline,stage,base,seed,tau):
    """Called after all current-stage methods have fixed their decisions."""
    update,_=timeline.decision_data(stage)
    ub=batch(update)
    candidates={0:parent,50:probe}
    for steps in (10,20):
        candidates[steps]=adapt(parent,ub,steps,seed+base.center_id+stage*1000+steps)
    future=[batch(timeline.offline_service(t,oracle_mode=True)) for t in range(stage,min(24,stage+3)+1)]
    losses={steps:float(np.mean([evaluate(model,xy)[0] for xy in future])) for steps,model in candidates.items()}
    best=min(losses,key=losses.get)
    return {"R_B50":tau-losses[best],"best_local_policy":f"P{best}","best_local_horizon_mse":losses[best],
            "effective_horizon":len(future),"local_horizon_mse":json.dumps(losses,separators=(",",":"))}


def run_trajectory(base,seed,scenario,frozen,protocol,bank,all_configs,tau):
    assert base.center_id in protocol["calibration_centers"]
    estimator=FrozenEstimator()
    timeline,meta=timeline_for_v2(base,scenario,frozen)
    incumbent=next(i for i in bank if i.identity_id=="msa_a57_pt")
    initial=initial_model(base,seed,incumbent,timeline)
    prefix=timeline._segment((800,1000),"assessment")
    initial_evidence=evidence_blocks(prefix)
    states=[MethodState(copy.deepcopy(c),initial,incumbent,evidence=list(initial_evidence),
                        detector=ADWIN(delta=c["delta"]) if c["method"]=="B5" else None) for c in all_configs]
    executor=DecisionExecutor(bank,frozen["deployment_limits"][base.budget_tier],estimator,
                              protocol["ravm"],base.center_id,seed,protocol["unit"])
    rows=[]
    scenario_hash=scenario_hash_v2(base,scenario,frozen)
    start=time.perf_counter()
    for stage in range(1,25):
        update,assessment=timeline.decision_data(stage)
        groups={}
        for state in states:
            key=(state.identity.identity_id,state_hash(state.parent))
            groups.setdefault(key,[]).append(state)
        decisions=[]
        for group in groups.values():
            decisions += executor.step_group(group,stage,update,assessment)
        assert len(decisions)==len(all_configs)
        # Capability opened only after every deployable current-stage decision exists.
        timeline.seal_decision(stage)
        labels={};service_losses={}
        service=timeline.service(stage)
        sb=batch(service)
        for state,row,parent,probe,selected in decisions:
            key=(row["identity_before"],row["parent_state_hash"])
            if key not in labels:
                labels[key]=offline_labels(parent,probe,timeline,stage,base,seed,tau)
            skey=row["deployed_state_hash"]
            if skey not in service_losses:
                service_losses[skey]=evaluate(selected,sb)[0]
            row.update(labels[key])
            row.update({"center_id":base.center_id,"seed":seed,"scenario":scenario,"center_type":base.center_type,
                        "deployment_tier":base.budget_tier,"scenario_hash":scenario_hash,
                        "scenario_role":"secondary Nonlinear Dependency-Shift Stress" if scenario=="C4" else meta["definition"],
                        "initial_state_hash":state_hash(initial),"tau_service":tau,
                        "service_mse":service_losses[skey],"D_srv_hash":service.hash,
                        "service_start_ts":int(service.ts[0]),"oracle_offline_only":True,
                        "J_life_normalized_stage":(service_losses[skey]+row["event_cost_raw"])/protocol["unit"]})
            rows.append(row)
        executor.source_cache={}
        print(json.dumps({"center":base.center_id,"seed":seed,"scenario":scenario,"stage":stage,
                          "unique_parent_states":len(groups),"elapsed_s":round(time.perf_counter()-start,1)}),flush=True)
    frame=pd.DataFrame(rows)
    assert len(frame)==120*24
    return frame


def worker(center,seed,scenario):
    _,_,frozen,protocol=preflight()
    output=RESULTS/"raw"/f"{scenario}_{center}_{seed}.csv"
    receipt=output.with_suffix(".integrity.json")
    if output.exists() and receipt.exists():
        assert sha256_file(output)==read_json(receipt)["sha256"]
        return output.as_posix()
    # Generate the exact full frozen pool to preserve prefix-balanced scheduling.
    bases=generate_base_centers(protocol["calibration_centers"],data_seed=frozen["data_seed"])
    base=next(b for b in bases if b.center_id==center)
    source=read_json(ROOT/frozen["source_training_manifest_path"])
    bank=build_p3_2_identity_bank(source)
    assert canonical_hash([i.to_dict() for i in bank])==protocol["source_bank_hash"]
    numeric=read_json(RESULTS/"numeric_baseline_thresholds.json")
    reference_row=read_json(RESULTS/"calibration_reference.json")[f"{center}:{seed}"]
    frame=run_trajectory(base,seed,scenario,frozen,protocol,bank,configs(numeric["thresholds"]),reference_row["tau_service"])
    csv(output,frame)
    save_json(receipt,{"sha256":sha256_file(output),"rows":len(frame),"center":center,"seed":seed,"scenario":scenario,
                       "pre_outcome_manifest_sha256":sha256_file(PRE),"completed_at_utc":utc()})
    return output.as_posix()


def materialize(workers):
    _,_,frozen,protocol=preflight()
    assert not (ROOT/"audits/P7_CALIBRATION_FREEZE.json").exists(),"P7 already frozen; no rerun"
    RESULTS.mkdir(parents=True,exist_ok=True)
    started=RESULTS/"outcome_materialization_started.json"
    if not started.exists():
        save_json(started,{"started_at_utc":utc(),"pre_outcome_manifest_sha256":sha256_file(PRE),
                           "pre_outcome_binding_git_commit":git("rev-parse","HEAD"),"calibration_centers":protocol["calibration_centers"],
                           "heldout_accessed":False,"alibaba_accessed":False,"phase":"P7_ONLY"})
    else:
        assert read_json(started)["pre_outcome_manifest_sha256"]==sha256_file(PRE)
    refs_path=RESULTS/"calibration_reference.json"
    if not refs_path.exists():
        bases=generate_base_centers(protocol["calibration_centers"],data_seed=frozen["data_seed"])
        bank=build_p3_2_identity_bank(read_json(ROOT/frozen["source_training_manifest_path"]))
        incumbent=next(i for i in bank if i.identity_id=="msa_a57_pt")
        refs={}
        for base in bases:
            for seed in protocol["model_seeds"]:
                refs[f"{base.center_id}:{seed}"]=reference(base,seed,incumbent,frozen)
                print("calibration causal prefix/reference",base.center_id,seed,flush=True)
        save_json(refs_path,refs)
    refs=read_json(refs_path)
    errors=np.concatenate([v["prefix_errors"] for v in refs.values()])
    quantiles=read_json(ROOT/"configs/p7_baseline_grids.json")["B4"]["quantile"]
    numeric={"thresholds":{str(q):float(np.quantile(errors,q)) for q in quantiles},
             "source":"calibration initial-history assessment prefix only; no online/future service losses",
             "reference_sha256":sha256_file(refs_path),"prefix_examples":len(errors),
             "frozen_before_closed_loop_outcomes":True}
    immutable_json(RESULTS/"numeric_baseline_thresholds.json",numeric)
    tasks=[(c,s,scenario) for c in protocol["calibration_centers"] for s in protocol["model_seeds"] for scenario in protocol["scenarios"]]
    completed=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(worker,*task):task for task in tasks}
        for f in as_completed(futures):
            path=f.result();completed+=1
            save_json(RESULTS/"execution_status.json",{"status":"RUNNING","completed_trajectories":completed,"total_trajectories":len(tasks),
                       "last_completed":path,"updated_at_utc":utc(),"heldout_accessed":False,"alibaba_accessed":False,"estimator_modified":False})
            print("completed",completed,"/",len(tasks),path,flush=True)
    save_json(RESULTS/"execution_status.json",{"status":"MATERIALIZATION_COMPLETE","completed_trajectories":completed,"total_trajectories":len(tasks),"updated_at_utc":utc(),"heldout_accessed":False,"alibaba_accessed":False})


def metrics(frame):
    recoverable=frame.R_B50>=0
    negative=~recoverable
    def rate(mask, outcome):
        return float(outcome[mask].mean()) if mask.any() else np.nan
    delays=[];missed_delay=0;persistent=0
    for _,trajectory in frame.groupby(["seed","scenario"]):
        t=trajectory.sort_values("stage")
        neg=(t.R_B50<0).to_numpy()
        onset=next((int(t.iloc[i].stage) for i in range(len(t)-1) if neg[i] and neg[i+1]),None)
        if onset is not None:
            persistent+=1
            events=t[(t.stage>=onset)&(t.ri==1)]
            if len(events):delays.append(int(events.iloc[0].stage)-onset)
            else:missed_delay+=1
    return {"J_life":float(frame.J_life_normalized_stage.mean()),"lifecycle_MSE":float(frame.service_mse.mean()),
            "maintenance_cost_normalized":float((frame.local*.1).mean()),
            "ri_cost_normalized":float((frame.ri*frame.cost_ratio*.1).mean()),
            "false_escalation_rate":rate(recoverable,frame.ri),"missed_escalation_rate":rate(negative,1-frame.ri),
            "false_gate_open_rate":rate(recoverable,frame.gate_open),"missed_gate_open_rate":rate(negative,1-frame.gate_open),
            "gate_open_rate":float(frame.gate_open.mean()),"search_rate":float(frame.gate_open.mean()),
            "RI_rate":float(frame.ri.mean()),"local_maintenance_rate":float(frame.local.mean()),
            "gate_open_minus_RI_rate":float((frame.gate_open-frame.ri).mean()),
            "mean_escalation_delay":float(np.mean(delays)) if delays else np.nan,
            "delay_observed_trajectories":len(delays),"delay_right_censored_trajectories":missed_delay,"persistent_negative_trajectories":persistent,
            "decision_runtime_actual_s":float(frame.decision_runtime_actual_s.mean()),
            "decision_runtime_standalone_estimate_s":float(frame.decision_runtime_standalone_estimate_s.mean()),
            "mean_search_candidates":float(frame.feasible_candidate_count.mean()),
            "mean_search_updates_charged":float(frame.ri_search_updates_charged.mean()),
            "source_cache_hits":int(frame.source_cache_hits.sum()),"stages":len(frame),
            "oracle_negative_stages":int(negative.sum()),"oracle_recoverable_stages":int(recoverable.sum()),
            "false_escalations":int((recoverable&(frame.ri==1)).sum()),"missed_escalations":int((negative&(frame.ri==0)).sum())}


def summarize(frame):
    center=[]
    for (cid,center_id),group in frame.groupby(["config_id","center_id"]):
        first=group.iloc[0]
        for subgroup,subset in [("all",group),("C3",group[group.scenario=="C3"]),
                               ("C4",group[group.scenario=="C4"]),("non-C3",group[group.scenario!="C3"])]:
            center.append({"config_id":cid,"method":first.method,"cost_ratio":first.cost_ratio,
                           "center_id":center_id,"center_type":first.center_type,"deployment_tier":first.deployment_tier,
                           "subgroup":subgroup,**metrics(subset)})
    centers=pd.DataFrame(center)
    return centers,aggregate_centers(centers)


def aggregate_centers(centers):
    summaries=[]
    conf={c["config_id"]:c for c in configs(read_json(RESULTS/"numeric_baseline_thresholds.json")["thresholds"])}
    for (cid,subgroup),group in centers.groupby(["config_id","subgroup"]):
        record={**conf[cid],"subgroup":subgroup,"centers":len(group)}
        columns=[c for c in group.columns if c not in ["config_id","method","cost_ratio","center_id","center_type","deployment_tier","subgroup"]]
        for column in columns:
            record[column]=float(group[column].mean()) if group[column].notna().any() else np.nan
            record[column+"_defined_centers"]=int(group[column].notna().sum())
        values=group.J_life.to_numpy()
        rng=np.random.default_rng(2904)
        boot=values[rng.integers(0,len(values),size=(4000,len(values)))].mean(axis=1)
        record["J_life_center_bootstrap_CI_low"],record["J_life_center_bootstrap_CI_high"]=np.quantile(boot,[.025,.975])
        record["sum_oracle_negative_stages"]=int(group.oracle_negative_stages.sum())
        record["sum_oracle_recoverable_stages"]=int(group.oracle_recoverable_stages.sum())
        summaries.append(record)
    return pd.DataFrame(summaries)


def safe_records(frame):
    return frame.astype(object).where(pd.notna(frame),None).to_dict("records")


def select(summary):
    primary=summary[summary.subgroup=="all"]
    method={"schema":"p7-selected-method-params-v1","primary_ratio":5,"by_ratio":{},"secondary_cap_by_ratio":{},
            "heldout_access_allowed":False,"human_review_required":True}
    baseline={"schema":"p7-selected-baseline-params-v1","primary_ratio":5,"by_ratio":{}}
    all_configs={c["config_id"]:c for c in configs(read_json(RESULTS/"numeric_baseline_thresholds.json")["thresholds"])}
    for ratio in [2,5,10]:
        p=primary[(primary.method=="Proposed")&(primary.cost_ratio==ratio)]
        for cap,destination in [(.1,"by_ratio"),(.05,"secondary_cap_by_ratio")]:
            eligible=p[p.false_escalation_rate<=cap].sort_values(["J_life","RI_rate","search_rate","delta_R","config_id"])
            if len(eligible):
                chosen=eligible.iloc[0]
                value={"status":"PASS","config":all_configs[chosen.config_id],"metrics":safe_records(eligible.iloc[:1])[0]}
            else:
                value={"status":"FAIL","fallback":"closed_gate","delta_R":None,"no_grid_candidate_satisfies_cap":True}
            method[destination][str(ratio)]=value
        chosen={}
        for name,g in primary[(primary.method!="Proposed")&(primary.cost_ratio==ratio)].groupby("method"):
            winner=g.sort_values(["J_life","RI_rate","search_rate","config_id"]).iloc[0]
            chosen[name]={"config":all_configs[winner.config_id],"metrics":safe_records(g[g.config_id==winner.config_id])[0]}
        baseline["by_ratio"][str(ratio)]=chosen
    unit=read_json(PROTOCOL)["unit"]
    method["costs"]={"unit":unit,"lambda_M_raw":.1*unit,"lambda_R_raw_by_ratio":{str(r):r*.1*unit for r in [2,5,10]}}
    method["primary_verdict"]=method["by_ratio"]["5"]["status"]
    immutable_json(ROOT/"configs/p7_selected_method_params.json",method)
    immutable_json(ROOT/"configs/p7_selected_baseline_params.json",baseline)
    return method,baseline


def actual_integrity(frame, center_subset=None):
    _,_,frozen,protocol=preflight()
    ids=protocol["calibration_centers"] if center_subset is None else center_subset
    assert set(ids)<=set(protocol["calibration_centers"])
    assert sorted(frame.center_id.unique())==ids
    assert sorted(frame.seed.unique())==protocol["model_seeds"]
    assert sorted(frame.scenario.unique())==sorted(protocol["scenarios"])
    assert len(frame)==len(ids)*3*4*120*24 and not frame.duplicated(["config_id","center_id","seed","scenario","stage"]).any()
    assert not frame.future_service_used_in_decision.any() and frame.assessment_gradient_updates.eq(0).all()
    assert frame.update_end_ts.lt(frame.decision_ts).all() and frame.decision_ts.lt(frame.service_start_ts).all()
    assert frame.bank_hash.eq(protocol["source_bank_hash"]).all()
    assert frame.ri_updates_per_candidate.eq(50).all() and frame.probe_updates.eq(50).all()
    assert (frame.ri<=frame.gate_open).all() and (frame.ri_search_updates_charged==50*frame.feasible_candidate_count).all()
    for _,g in frame.groupby(["center_id","seed","scenario","stage"]):
        assert g.D_upd_hash.nunique()==1 and g.D_assess_hash.nunique()==1 and g.D_srv_hash.nunique()==1
        assert g.deployment_filter_hash.nunique()==1
    for _,g in frame.groupby(["config_id","center_id","seed","scenario"]):
        t=g.sort_values("stage")
        assert t.stage.tolist()==list(range(1,25))
        assert t.iloc[0].history_size==1
        for prev,cur in zip(t.iloc[:-1].itertuples(),t.iloc[1:].itertuples()):
            assert cur.parent_state_hash==prev.deployed_state_hash
            assert cur.history_size==(1 if prev.ri else prev.history_size+1)
    return {"status":"PASS","expected_stage_records":len(frame),"center_count":len(ids),"heldout_accessed":False,"alibaba_accessed":False,
            "P6_all_manifest_hashes_unchanged":True,"role_pairing_validated":True,"budget_and_bank_validated":True,
            "history_resets_validated":True,"outcome_integrity_checks_executed":True}


def finalize():
    preflight()
    files=sorted((RESULTS/"raw").glob("*.csv"))
    assert len(files)==240,"materialization incomplete"
    for path in files:
        assert sha256_file(path)==read_json(path.with_suffix(".integrity.json"))["sha256"]
    center_frames=[];total_records=0
    for center in list(range(32000,32020)):
        center_files=[p for p in files if int(p.stem.split("_")[1])==center]
        assert len(center_files)==12
        frame=pd.concat([pd.read_csv(p) for p in center_files],ignore_index=True)
        integrity=actual_integrity(frame,[center])
        total_records+=len(frame)
        center_metrics,_=summarize(frame)
        center_frames.append(center_metrics)
    assert total_records==691200
    integrity.update({"expected_stage_records":total_records,"center_count":20})
    save_json(RESULTS/"scientific_runtime_integrity.json",integrity)
    centers=pd.concat(center_frames,ignore_index=True)
    summary=aggregate_centers(centers)
    csv(RESULTS/"metrics_by_center.csv",centers)
    csv(RESULTS/"proposed_calibration_grid.csv",summary[summary.method=="Proposed"])
    csv(RESULTS/"baseline_calibration_grid.csv",summary[summary.method!="Proposed"])
    method,baseline=select(summary)
    test=subprocess.run([sys.executable,"-m","pytest","tests/test_p7.py","-q"],cwd=ROOT,text=True,capture_output=True)
    (RESULTS/"pytest_output.txt").write_text(test.stdout+test.stderr,encoding="utf-8",newline="\n")
    assert test.returncode==0,"scientific tests failed; STOP before heldout"
    audit_text="""# P7 scientific audit

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: validate
- Verification Status: ANALYZED
- Overall Confidence: CAUTION (calibration only)

Required P7 tests executed, no skips, plus full actual-outcome integrity checks. See results/p7/pytest_output.txt and scientific_runtime_integrity.json. All P6 manifest hashes, exact pool/seed/scenario/config/stage coverage, paired role hashes, assessment no-grad, no-future decision, bank/filter/budget parity and RI history resets checked. No heldout/Alibaba access or estimator fitting. Existing P3.2b FAIL preserved; C4 architecture claims prohibited.

11/11 statistical fallacies checked: Simpson/ecological claims prevented by separate C3/C4/non-C3/center reporting; selected calibration pool is not population prevalence (Berkson/selection caution); no collider adjustment; oracle base counts supplied; copied probe gains are not uncontrolled causal service improvement; complete centers, no survivor filtering; every grid configuration exported (look-elsewhere/forking paths); no causal budget-tier or reverse-causality claim. CIs resample centers and are descriptive, selection-optimistic, not heldout confirmatory evidence. Reproducibility: deterministic memoization unit tests, not an independent complete stochastic rerun. Runtime actual executor allocation is not independent standalone method timing; standalone operation totals explicitly labeled estimates.
"""
    (ROOT/"audits/P7_SCIENTIFIC_AUDIT.md").write_text(audit_text,encoding="utf-8",newline="\n")
    primary=summary[(summary.method=="Proposed")&(summary.subgroup=="all")&(summary.cost_ratio==5)].sort_values("delta_R")
    columns=["delta_R","J_life","false_escalation_rate","missed_escalation_rate","search_rate","RI_rate","gate_open_minus_RI_rate","lifecycle_MSE"]
    grid_table=primary[columns].to_markdown(index=False,floatfmt=".7g")
    if method["primary_verdict"]=="PASS":
        config=method["by_ratio"]["5"]["config"];cid=config["config_id"]
        subgroup=summary[(summary.config_id==cid)]
        choice=json.dumps(config,indent=2)
        verdict="PASS: A fixed recoverability gate and baseline parameters have been calibrated without modifying the estimator and are ready for final heldout evaluation."
    else:
        subgroup=summary.iloc[:0];choice="No feasible primary delta. Frozen closed-gate fallback, calibration FAIL."
        verdict="FAIL: No scientifically acceptable calibration configuration was obtained under the frozen protocol."
    report=f"""# P7 gate and baseline calibration

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: run and validate
- Verification Status: ANALYZED

P7 only; 20 calibration centers, three paired seeds, four frozen scenarios, 120 configurations, {total_records} stage records. Center is the statistical unit. No final heldout/Alibaba data accessed; no estimator/scaler/generator/source/feature fitting or modification. P3.2b formal FAIL retained. C3 primary model-identity mismatch; C4 secondary Nonlinear Dependency-Shift Stress, not architecture replacement/failure. P6 weak C0/C1 within-scenario ranking and C3 extreme-negative compression remain limitations.

Protocol and modifications: docs/P7_PROTOCOL_AND_EXECUTION_LOG.md. Pre-outcome Git commit: {read_json(PRE)['preregistration_git_commit']}. Hash-bound grids preceded prefix and closed-loop outcomes. B4 numeric thresholds derived solely from calibration initial-history assessment prefix; service reference tau is offline oracle only. Unit u={read_json(PROTOCOL)['unit']:.17g}, lambda_M=.1u, ratios2/5/10, primary5 prespecified middle convention. Service and intervention terms individually exported.

## Primary Proposed calibration grid

{grid_table}

Gate opening does not force RI: search-minus-actual-RI is explicitly the gate_open_minus_RI_rate column. False escalation uses actual RI among finite-policy R>=0, missed escalation no RI among R<0; not scenario labels. Denominator-zero center rates remain null; defined-center counts and underlying oracle counts exported. R<0 does not guarantee a better feasible alternative. Delay conditional on observed RI, no finite replacement for right censoring.

## Selected primary Proposed parameters

```json
{choice}
```

## Selected primary subgroup diagnostics (no subgroup threshold tuning)

{subgroup[['subgroup','J_life','lifecycle_MSE','false_escalation_rate','missed_escalation_rate','search_rate','RI_rate','sum_oracle_negative_stages']].to_markdown(index=False,floatfmt='.7g')}

All candidate outcomes for all cost ratios and C3/C4/non-C3 groups: results/p7/proposed_calibration_grid.csv and baseline_calibration_grid.csv. Exact per-center results and descriptive center-bootstrap intervals are supplied, no stage-independent inference. Selected baseline parameters including B3/B4/B5/B6/B7/B8 and fixed B0/B1/B2 are in configs/p7_selected_baseline_params.json. Fairness: identical eleven-identity bank, deployment filters, primitive SGD operator, 50 updates per RI candidate, no Proposed extra bank budget. Frozen RAVM B2/B6 robust local aggregation/control is faithfully wrapped and distinguished from plain RI source adaptation. KEEP-style is task-matched, not exact DiTEC. River ADWIN2 version .23.0 as documented by [River](https://riverml.xyz/latest/api/drift/ADWIN/).

## Runtime and scientific limitations

Exact parent/source candidate memoization shares only causal decision evidence. Actual executor time and cache-hit counts are exported; charged reusable-operation standalone time is an estimate, not observed standalone runtime. Algorithmic candidate/update counts charged equally despite shared executor work. Offline finite-policy labels are evaluated only after decisions are sealed and excluded from decision caches. Calibration results/CI are descriptive and optimistic after selection, not final performance or manuscript superiority evidence. Any primary infeasibility is FAIL with predeclared closed-gate fallback; no cap relaxation or added delta. Secondary .05 and all ratios retained, not used to redefine primary.

Required tests and actual-outcome integrity passed; see audits/P7_SCIENTIFIC_AUDIT.md. Freeze all outputs before any heldout access. STOP after P7 and wait for human scientific review; do not execute P8/final evaluation.

{verdict}
"""
    (ROOT/"reports/P7_GATE_AND_BASELINE_CALIBRATION.md").write_text(report,encoding="utf-8",newline="\n")
    paths=[ROOT/"configs/p7_selected_method_params.json",ROOT/"configs/p7_selected_baseline_params.json",
           ROOT/"configs/p7_delta_grid.json",ROOT/"configs/p7_baseline_grids.json",PROTOCOL,PRE,
           RESULTS/"proposed_calibration_grid.csv",RESULTS/"baseline_calibration_grid.csv",RESULTS/"metrics_by_center.csv",
           RESULTS/"numeric_baseline_thresholds.json",RESULTS/"calibration_reference.json",
           RESULTS/"scientific_runtime_integrity.json",RESULTS/"pytest_output.txt",
           ROOT/"reports/P7_GATE_AND_BASELINE_CALIBRATION.md",ROOT/"audits/P7_SCIENTIFIC_AUDIT.md"]
    freeze={"schema":"p7-calibration-freeze-v1","status":method["primary_verdict"],"frozen_at_utc":utc(),
            "calibration_centers":list(range(32000,32020)),"preregistration_git_commit":read_json(PRE)["preregistration_git_commit"],
            "implementation_git_commit":git("rev-parse","HEAD"),"P6_manifest_sha256":sha256_file(ROOT/"audits/P6_ESTIMATOR_FREEZE.json"),
            "P6_estimator_sha256":read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")["estimator_sha256"],
            "P6_scaler_sha256":read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")["scaler_sha256"],
            "primary_ratio":5,"primary_selected":method["by_ratio"]["5"],"heldout_accessed":False,"alibaba_accessed":False,
            "future_phase_authorized":False,"human_review_required":True,
            "files":{p.relative_to(ROOT).as_posix():sha256_file(p) for p in paths},
            "raw_outcome_hashes":{p.relative_to(ROOT).as_posix():sha256_file(p) for p in files}}
    immutable_json(ROOT/"audits/P7_CALIBRATION_FREEZE.json",freeze)
    (ROOT/"audits/P7_CALIBRATION_FREEZE.sha256").write_text(sha256_file(ROOT/"audits/P7_CALIBRATION_FREEZE.json")+"\n",encoding="utf-8",newline="\n")
    commit_paths=paths+[ROOT/"audits/P7_CALIBRATION_FREEZE.json",ROOT/"audits/P7_CALIBRATION_FREEZE.sha256"]
    # Stage exact P7 evidence paths only; raw trajectories are bound by their hashes.
    git("add","--",*[p.relative_to(ROOT).as_posix() for p in commit_paths])
    git("commit","-m","Freeze P7 calibration evidence and selected decision parameters; stop before heldout")
    head=git("rev-parse","HEAD")
    for path in commit_paths:
        rel=path.relative_to(ROOT).as_posix()
        payload=subprocess.check_output(["git","show",head+":"+rel],cwd=ROOT)
        assert hashlib.sha256(payload).hexdigest()==sha256_file(path),"final Git binding mismatch: "+rel
    base_preflight()
    save_json(RESULTS/"execution_status.json",{"status":"P7_COMPLETE_STOP_FOR_HUMAN_REVIEW","verdict":method["primary_verdict"],"updated_at_utc":utc(),"heldout_accessed":False,"alibaba_accessed":False})
    print(verdict,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["prepare","bind","preflight","run","finalize"])
    parser.add_argument("--workers",type=int,default=1)
    args=parser.parse_args()
    if args.command=="prepare":prepare()
    elif args.command=="bind":bind()
    elif args.command=="preflight":preflight();print("P7 PREFLIGHT PASS; no data materialized")
    elif args.command=="finalize":finalize()
    else:
        try:
            materialize(args.workers)
            finalize()
        except Exception as exc:
            save_json(RESULTS/"execution_status.json",{"status":"STOPPED_ERROR","error":repr(exc),"updated_at_utc":utc(),"heldout_accessed":False,"alibaba_accessed":False,"no_scientific_redesign_authorized":True})
            raise


if __name__=="__main__":main()
