"""P7 closed-loop calibration. Decision scopes never receive service tensors."""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from river.drift import ADWIN

from .common import ROOT, canonical_hash, sha256_file
from .models import DEVICE, adapt, evaluate, feasible, load_identity, state_hash, to_batch
from .p6 import FEATURE_COLUMNS, apply_scaler
from .protocol import Segment, windows


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(path)


def batch(segment):
    return to_batch(*windows(segment), segment.role)


def sync():
    if DEVICE.type == "cuda":
        torch.cuda.synchronize()


class FrozenMLP(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = torch.nn.Sequential(torch.nn.Linear(6,16), torch.nn.ReLU(),
                                          torch.nn.Linear(16,8), torch.nn.ReLU(), torch.nn.Linear(8,1))

    def forward(self, x):
        return self.layers(x).squeeze(-1)


class FrozenEstimator:
    def __init__(self):
        manifest = read_json(ROOT / "audits/P6_ESTIMATOR_FREEZE.json")
        assert manifest["K_S"] == 2 and manifest["K_L"] == 6
        assert manifest["feature_order"] == FEATURE_COLUMNS
        for rel, expected in manifest["files"].items():
            assert sha256_file(ROOT / rel) == expected, "P6 immutable hash mismatch: " + rel
        self.scaler = read_json(ROOT / "artifacts/p6_recoverability_scaler.json")
        assert self.scaler["feature_order"] == FEATURE_COLUMNS
        payload = torch.load(ROOT / "artifacts/p6_recoverability_estimator.pt", weights_only=True, map_location="cpu")
        assert payload["K_S"] == 2 and payload["K_L"] == 6
        self.multiplier = float(payload["target_multiplier"])
        self.model = FrozenMLP()
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)

    @torch.no_grad()
    def predict(self, history):
        values = history_features(history)
        scaled = apply_scaler(values[None, :], self.scaler)
        return float(self.model(torch.as_tensor(scaled, dtype=torch.float32))[0]) / self.multiplier


def history_features(history):
    assert history
    short, long = np.asarray(history[-2:]), np.asarray(history[-6:])
    return np.array([short[:,0].mean(), short[:,1].mean(), long[:,0].mean(), long[:,1].mean(),
                     len(short)/2, len(long)/6], dtype=np.float64)


@torch.no_grad()
def point_errors(model, xy):
    model.eval()
    x,y = xy
    pred = torch.cat([model(x[i:i+256]) for i in range(0,len(x),256)])
    return (pred-y).square().mean(1).cpu().numpy()


def evidence_blocks(segment, count=6):
    n = len(segment.y)-96
    result=[]
    for ids in np.array_split(np.arange(n), count):
        if len(ids):
            result.append(Segment(segment.x[ids[0]:ids[-1]+97].copy(),
                                  segment.y[ids[0]:ids[-1]+97].copy(),
                                  segment.ts[ids[0]:ids[-1]+97].copy(), "assessment"))
    return result


def robust_local(parent, xy, seed, cfg):
    """Frozen RAVM five independent block deltas, total 50 updates."""
    x,y=xy
    deltas=[]
    original=parent.state_dict()
    for offset, ids in enumerate(np.array_split(np.arange(len(x)), cfg["B"])):
        candidate=adapt(parent, to_batch(x[ids],y[ids],"update"), 50//cfg["B"], seed+offset)
        deltas.append({key:value-original[key] for key,value in candidate.state_dict().items()})
    trim=int(cfg["B"]*cfg["beta"])
    candidate=copy.deepcopy(parent)
    candidate.load_state_dict({key:value+torch.stack([d[key] for d in deltas]).sort(dim=0).values[
        trim:cfg["B"]-trim].mean(0) for key,value in original.items()})
    return candidate


def robust_score(candidate,parent,blocks,kappa):
    if not blocks:
        return float("inf")
    differences=np.array([float((point_errors(candidate,batch(b))-point_errors(parent,batch(b))).mean()) for b in blocks])
    median=float(np.median(differences))
    return median+kappa*float(np.median(np.abs(differences-median)))


def ravm_accept(candidate,parent,recent,history,cfg):
    return (robust_score(candidate,parent,recent,cfg["kappa_rec"]) <= -cfg["delta_imp"]
            and robust_score(candidate,parent,history,cfg["kappa_hist"]) <= cfg["delta_ret"])


@dataclass
class MethodState:
    config: dict
    parent: object
    identity: object
    history: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    recent_assessments: list = field(default_factory=list)
    error_streak: int = 0
    reject_streak: int = 0
    detector: object = None
    # Optional frozen representation scale used by an operational estimator.
    # Existing methods leave this unset; the P7.7 Branch-B A1 estimator owns
    # its value and resets it only at an accepted identity transition.
    a1_scale: float = None

    def reset_after_ri(self):
        self.history=[]
        self.evidence=[]
        self.recent_assessments=[]
        self.error_streak=0
        self.reject_streak=0
        if self.config["method"] == "B5":
            self.detector=ADWIN(delta=self.config["delta"])


def choose_action(pre_loss, local_loss, alternatives, lambda_m, lambda_r, local_allowed=True):
    """No forced RI. Exact ties retain > local > bank-ordered RI."""
    candidates=[(pre_loss,0,"retain",None)]
    if local_allowed:
        candidates.append((local_loss+lambda_m,1,"local",None))
    candidates.extend((loss+lambda_r,2,"ri",idx) for idx,loss in alternatives)
    return min(candidates, key=lambda x:(x[0],x[1]))[2:]


class DecisionExecutor:
    """Only decision-time role batches. No timeline or oracle in this object."""
    def __init__(self, bank, limits, estimator, cfg, center, seed, unit):
        self.bank=bank
        self.limits=limits
        self.estimator=estimator
        self.cfg=cfg
        self.center=center
        self.seed=seed
        self.unit=unit
        self.source_cache={}

    def source_candidates(self, stage, update_batch, assessment_batch, update_hash, assess_hash, exclude_identity):
        assert update_batch.role == "update" and assessment_batch.role == "assessment"
        result={}
        newly_spent=0.
        for idx,identity in enumerate(self.bank):
            if identity.identity_id == exclude_identity or not feasible(identity,self.limits):
                continue
            key=(stage,idx,update_hash,assess_hash)
            hit=key in self.source_cache
            if not hit:
                sync();start=time.perf_counter()
                model=adapt(load_identity(identity),update_batch,50,
                            self.seed+self.center+stage*1000+500+idx)
                loss=evaluate(model,assessment_batch)[0]
                sync();duration=time.perf_counter()-start
                self.source_cache[key]=(model,loss,duration)
                newly_spent+=duration
            result[idx]=(*self.source_cache[key],hit)
        return result,newly_spent

    def step_group(self, states, stage, update, assessment):
        assert update.role == "update" and assessment.role == "assessment"
        assert update.ts[-1] < assessment.ts[0]
        parent=states[0].parent
        identity=states[0].identity
        before=state_hash(parent)
        assert all(state_hash(s.parent)==before and s.identity.identity_id==identity.identity_id for s in states)
        ub,ab=batch(update),batch(assessment)
        sync();start=time.perf_counter()
        probe=adapt(parent,ub,50,self.seed+self.center+stage*100)
        pre=evaluate(parent,ab)[0]
        post=evaluate(probe,ab)[0]
        gain=(pre-post)/(pre+1e-12)
        sync();common_time=time.perf_counter()-start
        assert state_hash(parent)==before
        robust=None
        robust_time=0.
        if any(s.config["method"] in ("B2","B6") for s in states):
            sync();start=time.perf_counter()
            robust=robust_local(parent,ub,self.seed+self.center+stage*100,self.cfg)
            robust_loss=evaluate(robust,ab)[0]
            sync();robust_time=time.perf_counter()-start
        recent_blocks=evidence_blocks(assessment)
        result=[]
        for position,state in enumerate(states):
            c=state.config
            method=c["method"]
            lm=.1*self.unit
            lr=c["cost_ratio"]*lm
            sync();start=time.perf_counter()
            state.history.append((gain,post))
            if hasattr(self.estimator, "predict_state"):
                prediction=self.estimator.predict_state(state)
            else:
                prediction=self.estimator.predict(state.history)
            local=probe
            local_loss=post
            local_allowed=True
            accepted_ravm=None
            gate=False
            if method in ("B2","B6"):
                local=robust
                local_loss=robust_loss
                accepted_ravm=ravm_accept(robust,parent,recent_blocks,state.evidence,self.cfg)
                local_allowed=accepted_ravm
                state.reject_streak=0 if accepted_ravm else state.reject_streak+1
            if method == "B3":
                gate=stage%c["K"]==0
            elif method == "B4":
                state.error_streak=state.error_streak+1 if pre>c["threshold"] else 0
                gate=state.error_streak>=c["persistence"]
            elif method == "B5":
                for value in np.clip(point_errors(parent,ab),0,1):
                    state.detector.update(float(value))
                    gate=gate or state.detector.drift_detected
            elif method == "B6":
                gate=state.reject_streak>=c["K"]
            elif method in ("B7","B8"):
                gate=True
            elif method in ("Proposed", "P7.7"):
                gate=prediction<float(c.get("gate_boundary", c["delta_R"]))
            sources={}
            source_work=0.
            alternatives=[]
            if gate:
                sources,source_work=self.source_candidates(stage,ub,ab,update.hash,assessment.hash,identity.identity_id)
                for idx,(model,loss,_,_) in sources.items():
                    if self.bank[idx].identity_id==identity.identity_id:
                        continue
                    eligible=True
                    if method == "B7":
                        past=(state.recent_assessments+[assessment])[-c["window"]:]
                        advantages=[(evaluate(parent,batch(seg))[0]-evaluate(model,batch(seg))[0]-lr)/self.unit for seg in past]
                        eligible=float(np.mean(advantages))>c["margin"]
                    if eligible:
                        alternatives.append((idx,loss))
            action,index=choose_action(pre,local_loss,alternatives,lm,lr,local_allowed)
            if method == "B0":
                action,index="retain",None
            elif method == "B1":
                action,index="local",None
            elif method == "B2":
                action,index=("local",None) if accepted_ravm else ("retain",None)
            selected=parent if action=="retain" else local if action=="local" else sources[index][0]
            selected_identity=identity if action!="ri" else self.bank[index]
            assert action!="ri" or gate
            assert feasible(selected_identity,self.limits), "deployment violation"
            assert state_hash(parent)==before
            sync();own_time=time.perf_counter()-start
            # Actual work attributed once; reusable timings are explicitly estimates.
            requested=[v for idx,v in sources.items() if self.bank[idx].identity_id!=identity.identity_id]
            charged=sum(v[2] for v in requested)
            standalone=common_time+own_time-source_work+charged
            if method in ("B2","B6"):
                standalone+=robust_time
            row={"config_id":c["config_id"],"method":method,"cost_ratio":c["cost_ratio"],
                 "stage":stage,"identity_before":identity.identity_id,"identity_after":selected_identity.identity_id,
                 "parent_state_hash":before,"deployed_state_hash":state_hash(selected),
                 "D_upd_hash":update.hash,"D_assess_hash":assessment.hash,
                 "update_end_ts":int(update.ts[-1]),"decision_ts":int(assessment.ts[-1]),
                 "assessment_gradient_updates":0,"probe_updates":50,"ri_updates_per_candidate":50,
                 "bank_hash":canonical_hash([i.to_dict() for i in self.bank]),
                 "deployment_filter_hash":canonical_hash(self.limits),"probe_gain":gain,"probe_residual":post,
                 "predicted_R":prediction,"gate_boundary":float(c.get("gate_boundary", c.get("delta_R", 0.0))),
                 "gate_estimator":c.get("gate_estimator", "P6"),
                 "history_size":len(state.history),"feature_vector_hash":canonical_hash(history_features(state.history).tolist()),
                 "pre_assessment_mse":pre,"post_assessment_mse":post,"gate_open":int(gate),
                 "ri":int(action=="ri"),"local":int(action=="local"),"action":action,
                 "event_cost_raw":lr if action=="ri" else lm if action=="local" else 0.,
                 "feasible_candidate_count":len(requested),"ri_search_updates_charged":50*len(requested),
                 "source_cache_hits":sum(int(v[3]) for v in requested),"shared_parent_cache_hit":int(position>0),
                 "decision_runtime_actual_s":own_time+(common_time+robust_time if position==0 else 0.),
                 "decision_runtime_standalone_estimate_s":standalone,
                 "ravm_accept":None if accepted_ravm is None else int(accepted_ravm),
                 "future_service_used_in_decision":False,"source_adapt_seed_rule":"seed+center+stage*1000+500+bank_index"}
            # Return label parents to a separate caller AFTER a decision is fixed.
            result.append((state,row,parent,probe,selected))
            state.parent=selected
            state.identity=selected_identity
            if action=="ri":
                state.reset_after_ri()
                if hasattr(self.estimator, "on_identity_birth"):
                    self.estimator.on_identity_birth(state, selected, assessment)
            else:
                state.evidence=(state.evidence+recent_blocks)[-24:]
                state.recent_assessments=(state.recent_assessments+[assessment])[-6:]
        return result
