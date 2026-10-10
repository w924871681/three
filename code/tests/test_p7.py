"""P7 scientific guards: fake model/data fixtures; no new real-center outcomes."""
import copy
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from core.common import ROOT, canonical_hash, sha256_file
from core.models import ModelIdentity, adapt, state_hash, to_batch
from core.p6 import FEATURE_COLUMNS, causal_history_features
from core.p7 import (DecisionExecutor, MethodState, FrozenEstimator, choose_action,
                     history_features, read_json, robust_local)
from core.protocol import Segment
from scripts.run_p7 import base_preflight, preflight, configs, metrics, PRE, PROTOCOL, RESULTS


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight=torch.nn.Parameter(torch.tensor(.5))

    def forward(self,x):
        return x[:,-1,:1]*self.weight


class ConstantEstimator:
    def predict(self,history):
        return -1.


@pytest.fixture
def toy_executor(monkeypatch):
    import core.p7 as p7
    identities=[ModelIdentity("toy"+str(i),i,"toy","toy","toy","unused", "unused",1,1) for i in range(2)]
    monkeypatch.setattr(p7,"load_identity",lambda identity:Toy())
    # Equal service-independent candidate losses force retain even when search opens.
    monkeypatch.setattr(p7,"evaluate",lambda model,xy:(.25,.5))
    cfg={"B":5,"beta":.1,"kappa_rec":.5,"kappa_hist":0.,"delta_imp":2.8018237766243602e-5,"delta_ret":0.}
    executor=DecisionExecutor(identities,{"parameters":2,"operations":2},ConstantEstimator(),cfg,0,1,1.)
    method={"config_id":"toy","method":"Proposed","cost_ratio":5,"delta_R":0.}
    state=MethodState(method,Toy(),identities[0])
    update=Segment(np.ones((200,1),dtype=np.float32),np.zeros(200,dtype=np.float32),np.arange(200),"update")
    assess=Segment(np.ones((200,1),dtype=np.float32),np.zeros(200,dtype=np.float32),np.arange(200,400),"assessment")
    return executor,state,update,assess


def test_p7_calibration_pool_matches_p4_freeze():
    assert base_preflight()[3]==list(range(32000,32020))
    assert read_json(PROTOCOL)["calibration_centers"]==list(range(32000,32020))


def test_p7_no_final_heldout_access():
    assert read_json(PROTOCOL)["heldout_access_allowed"] is False
    assert set(read_json(PROTOCOL)["calibration_centers"]).isdisjoint(range(33000,33020))
    if (RESULTS/"outcome_materialization_started.json").exists():
        assert read_json(RESULTS/"outcome_materialization_started.json")["heldout_accessed"] is False


def test_p7_no_alibaba_access():
    assert read_json(PROTOCOL)["alibaba_access_allowed"] is False
    # Namespaced integer synthetic IDs never form machine IDs or external paths.
    assert all(isinstance(i,int) for i in read_json(PROTOCOL)["calibration_centers"])
    code=(ROOT/"scripts/run_p7.py").read_text()
    assert "Timeline(center)" not in code and "np.load(" not in code


def test_p7_p6_estimator_hash_unchanged():
    manifest=read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")
    assert sha256_file(ROOT/"artifacts/p6_recoverability_estimator.pt")==manifest["estimator_sha256"]
    estimator=FrozenEstimator()
    assert all(not p.requires_grad for p in estimator.model.parameters())


def test_p7_scaler_hash_unchanged():
    assert sha256_file(ROOT/"artifacts/p6_recoverability_scaler.json")==read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")["scaler_sha256"]
    assert "fit_scaler" not in inspect.getsource(DecisionExecutor)


def test_p7_feature_spec_unchanged():
    expected=read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")["feature_specification_sha256"]
    assert canonical_hash({"event":["gain","residual"],"features":FEATURE_COLUMNS,"history":"same-identity/current-probe-inclusive/no-future"})==expected
    events=pd.DataFrame([{"center_id":0,"seed":0,"scenario":"fake","stage":i+1,"identity_id":"toy",
                          "probe_gain":i/10,"probe_residual":i/100,"R_B50":0.} for i in range(8)])
    reference=causal_history_features(events,2,6)
    for i in range(8):
        np.testing.assert_allclose(history_features([(j/10,j/100) for j in range(i+1)]),reference.iloc[i][FEATURE_COLUMNS].to_numpy(dtype=float))


def test_p7_window_pair_unchanged():
    pair=read_json(PROTOCOL)["window_pair"]
    assert pair=={"K_S":2,"K_L":6}
    assert canonical_hash(pair)==read_json(ROOT/"audits/P6_ESTIMATOR_FREEZE.json")["selected_window_pair_sha256"]


def test_p7_delta_grid_frozen_before_outcomes():
    preflight()
    delta=read_json(ROOT/"configs/p7_delta_grid.json")
    oof=pd.read_csv(ROOT/delta["source"])
    assert delta["s"]==float(oof.error.abs().median())
    np.testing.assert_array_equal(delta["delta_R"],np.array([-2,-1,-.5,0,.5,1,2])*delta["s"])
    assert read_json(PRE)["calibration_outcomes_materialized"] is False


def test_p7_baseline_grids_frozen_before_outcomes():
    preflight()
    grid=read_json(ROOT/"configs/p7_baseline_grids.json")
    assert grid["B3"]["K"]==[4,6,8,12] and grid["B6"]["K"]==[2,3,4,6]
    assert grid["B4"]["quantile"]==[.8,.9,.95] and grid["B4"]["persistence"]==[1,2,3]
    assert grid["B5"]["delta"]==[.0002,.002,.02]
    assert len(configs({str(q):1. for q in [.8,.9,.95]}))==120


def test_p7_no_future_service_in_decision(toy_executor,monkeypatch):
    from core.protocol import CausalTimeline
    def forbidden(*args,**kwargs):
        raise AssertionError("future service in decision")
    monkeypatch.setattr(CausalTimeline,"service",forbidden)
    monkeypatch.setattr(CausalTimeline,"offline_service",forbidden)
    executor,state,update,assessment=toy_executor
    row=executor.step_group([state],1,update,assessment)[0][1]
    assert row["future_service_used_in_decision"] is False
    assert "timeline" not in vars(executor)


def test_p7_assessment_not_used_for_gradients():
    x=np.ones((3,96,1),dtype=np.float32);y=np.zeros((3,1),dtype=np.float32)
    with pytest.raises(AssertionError,match="forbidden"):
        adapt(Toy(),to_batch(x,y,"assessment"),1,0)


def test_p7_same_candidate_budget_across_methods(toy_executor):
    executor,state,u,a=toy_executor
    states=[]
    for method in ["Proposed","B8","B3"]:
        s=copy.deepcopy(state);s.config={**s.config,"method":method,"K":1}
        states.append(s)
    decisions=executor.step_group(states,1,u,a)
    assert all(row["ri_updates_per_candidate"]==50 and row["feasible_candidate_count"]==1 for _,row,*_ in decisions)
    assert all(row["ri_search_updates_charged"]==50 for _,row,*_ in decisions)


def test_p7_same_bank_and_deployment_filter(toy_executor):
    executor,state,u,a=toy_executor
    rows=executor.step_group([state,copy.deepcopy(state)],1,u,a)
    assert rows[0][1]["bank_hash"]==rows[1][1]["bank_hash"]
    assert rows[0][1]["deployment_filter_hash"]==rows[1][1]["deployment_filter_hash"]
    assert all(row["D_upd_hash"]==u.hash and row["D_assess_hash"]==a.hash for _,row,*_ in rows)


def test_p7_gate_open_not_forced_reinstantiation(toy_executor):
    executor,state,u,a=toy_executor
    row=executor.step_group([state],1,u,a)[0][1]
    assert row["gate_open"]==1 and row["ri"]==0 and row["action"]=="retain"
    assert choose_action(1.,.9,[(0,.5)],.1,.5)==("retain",None)


def test_p7_center_level_statistics():
    from scripts.run_p7 import summarize, aggregate_centers
    code=inspect.getsource(summarize)
    assert 'groupby(["config_id","center_id"])' in code
    assert 'values=group.J_life.to_numpy()' in inspect.getsource(aggregate_centers)
    assert read_json(PROTOCOL)["statistical_unit"]=="center"
    # Conditional-center macro is not a stage-pooled conditional rate.
    center=pd.DataFrame({"center":[0]*9+[1],"false":[1]*9+[0]})
    assert center.groupby("center").false.mean().mean()==.5
    assert center.false.mean()==.9


def test_p7_selected_parameters_frozen_before_heldout():
    assert read_json(PROTOCOL)["heldout_access_allowed"] is False
    path=ROOT/"configs/p7_selected_method_params.json"
    if path.exists():
        selected=read_json(path)
        assert selected["heldout_access_allowed"] is False and selected["human_review_required"] is True
        freeze=ROOT/"audits/P7_CALIBRATION_FREEZE.json"
        if freeze.exists():
            assert sha256_file(path)==read_json(freeze)["files"][path.relative_to(ROOT).as_posix()]
    else:
        assert not (ROOT/"audits/P7_CALIBRATION_FREEZE.json").exists()


def test_p7_exact_causal_memoization(toy_executor):
    executor,state,u,a=toy_executor
    duplicate=copy.deepcopy(state)
    first=executor.step_group([state],1,u,a)[0][1]
    second=executor.step_group([duplicate],1,u,a)[0][1]
    for key in ["action","deployed_state_hash","feature_vector_hash","predicted_R","pre_assessment_mse"]:
        assert first[key]==second[key]
    assert second["source_cache_hits"]==1


def test_p7_ravm_real_reject_not_negative_gain(toy_executor):
    from core.p7 import ravm_accept, evidence_blocks
    executor,state,u,a=toy_executor
    parent=Toy();before=state_hash(parent)
    candidate=robust_local(parent,to_batch(*__import__('core.protocol',fromlist=['windows']).windows(u),"update"),1,executor.cfg)
    assert state_hash(parent)==before
    assert isinstance(ravm_accept(candidate,parent,evidence_blocks(a),evidence_blocks(a),executor.cfg),bool)
    code=inspect.getsource(DecisionExecutor)
    assert 'accepted_ravm=ravm_accept' in code
    assert 'state.reject_streak=0 if accepted_ravm else state.reject_streak+1' in code


def test_p7_reset_history_on_ri(toy_executor):
    _,state,_,_=toy_executor
    state.history=[(1.,1.)];state.evidence=[1];state.recent_assessments=[1];state.reject_streak=4
    state.reset_after_ri()
    assert state.history==state.evidence==state.recent_assessments==[] and state.reject_streak==0
