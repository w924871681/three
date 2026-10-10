from __future__ import annotations

import copy
import time
from dataclasses import dataclass

import numpy as np
import torch

from .common import canonical_hash
from .data import BaseCenter, corrupt_decision_segment, timeline_for
from .models import (
    DEVICE,
    ModelIdentity,
    adapt,
    bank_hash,
    evaluate,
    feasible,
    load_identity,
    state_hash,
    to_batch,
)
from .protocol import Segment, spans, windows


@dataclass
class P3RunResult:
    stage_rows: list[dict]
    candidate_rows: list[dict]
    run_audit: dict


def _batch(segment: Segment):
    x, y = windows(segment)
    return to_batch(x, y, segment.role)


def _service_curve(model, timeline, stage: int, max_horizon: int) -> list[float]:
    losses = []
    for future_stage in range(stage, min(24, stage + max_horizon - 1) + 1):
        service = timeline.offline_service(future_stage, oracle_mode=True)
        x, y = windows(service)
        losses.append(evaluate(model, to_batch(x, y, "offline_oracle_service"))[0])
    return losses


def _prefix_means(losses: list[float], horizons: list[int]) -> dict[int, tuple[float, int]]:
    return {h: (float(np.mean(losses[: min(h, len(losses))])), min(h, len(losses))) for h in horizons}


def initial_model(base: BaseCenter, seed: int, incumbent: ModelIdentity, timeline) -> torch.nn.Module:
    model = load_identity(incumbent)
    warm = _batch(timeline.warmup())
    return adapt(model, warm, steps=50, seed=seed + base.center_id)


def reference_loss(base: BaseCenter, seed: int, incumbent: ModelIdentity, teachers: dict[str, np.ndarray]) -> float:
    timeline, _ = timeline_for(base, "C0", teachers)
    parent = initial_model(base, seed, incumbent, timeline)
    values = []
    for stage in range(1, 9):
        update, _ = timeline.decision_data(stage)
        candidate = adapt(parent, _batch(update), steps=50, seed=seed + base.center_id + stage * 100)
        timeline.seal_decision(stage)
        values.append(evaluate(candidate, _batch(timeline.service(stage)))[0])
        parent = candidate
    return float(np.mean(values))


def run_p3_trajectory(
    base: BaseCenter,
    seed: int,
    scenario: str,
    identities: list[ModelIdentity],
    teachers: dict[str, np.ndarray],
    config: dict,
    tau_service: float,
) -> P3RunResult:
    horizons = [int(value) for value in config["recoverability_horizons"]]
    local_policies = [int(value) for value in config["local_policies"]]
    limits = config["deployment_limits"][base.budget_tier]
    incumbent = next(item for item in identities if item.identity_id == "msa_a57_pt")
    alternatives = [item for item in identities if item.identity_id != incumbent.identity_id and feasible(item, limits)]
    timeline, scenario_meta = timeline_for(base, scenario, teachers)
    parent = initial_model(base, seed, incumbent, timeline)
    initial_hash = state_hash(parent)
    identity_id = incumbent.identity_id
    stage_rows: list[dict] = []
    candidate_rows: list[dict] = []
    parent_integrity = []

    for stage in range(1, 25):
        raw_update, raw_assessment = timeline.decision_data(stage)
        update = corrupt_decision_segment(raw_update, scenario, base.center_id, stage, seed)
        assessment = corrupt_decision_segment(raw_assessment, scenario, base.center_id, stage, seed)
        update_batch = _batch(update)
        assessment_batch = _batch(assessment)
        before_hash = state_hash(parent)

        probe_start = time.perf_counter()
        probe = adapt(parent, update_batch, steps=50, seed=seed + base.center_id + stage * 100)
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        probe_time = time.perf_counter() - probe_start
        after_parent_hash = state_hash(parent)
        parent_integrity.append(before_hash == after_parent_hash)
        if before_hash != after_parent_hash:
            raise AssertionError("local probe modified deployed model")
        pre_loss, _ = evaluate(parent, assessment_batch)
        post_loss, _ = evaluate(probe, assessment_batch)
        gain = (pre_loss - post_loss) / (pre_loss + 1e-12)

        local_candidates = {}
        for steps in local_policies:
            if steps == 0:
                candidate = copy.deepcopy(parent)
            elif steps == 50:
                # P50 is exactly the already-computed fixed local probe. Reusing
                # that immutable candidate avoids duplicating the same policy.
                candidate = probe
            else:
                candidate = adapt(
                    parent,
                    update_batch,
                    steps=steps,
                    seed=seed + base.center_id + stage * 1000 + steps,
                )
            curve = _service_curve(candidate, timeline, stage, max(horizons))
            local_candidates[steps] = _prefix_means(curve, horizons)

        ri_candidates = {}
        for offset, alternative in enumerate(alternatives):
            started = time.perf_counter()
            model = load_identity(alternative)
            adapted = adapt(
                model,
                update_batch,
                steps=50,
                seed=seed + base.center_id + stage * 1000 + 500 + offset,
            )
            assess_loss, _ = evaluate(adapted, assessment_batch)
            curve = _service_curve(adapted, timeline, stage, max(horizons))
            prefix = _prefix_means(curve, horizons)
            ri_candidates[alternative.identity_id] = (alternative, adapted, assess_loss, prefix)
            candidate_rows.append(
                {
                    "run_id": f"p3-{scenario}-{base.center_id}-{seed}",
                    "center_id": base.center_id,
                    "seed": seed,
                    "scenario": scenario,
                    "stage": stage,
                    "candidate_identity_id": alternative.identity_id,
                    "candidate_architecture": alternative.architecture,
                    "candidate_source_init_id": alternative.source_initialization_id,
                    "feasible": True,
                    "adapted_state_hash": state_hash(adapted),
                    "adaptation_updates": 50,
                    "assessment_loss": assess_loss,
                    "candidate_cost": 1.0,
                    "surrogate_objective": assess_loss,
                    "adaptation_time_s": time.perf_counter() - started,
                    "horizon_loss_h2": prefix[2][0],
                    "horizon_loss_h4": prefix[4][0],
                    "horizon_loss_h6": prefix[6][0],
                }
            )

        timeline.seal_decision(stage)
        service = timeline.service(stage)
        service_mse, service_mae = evaluate(probe, _batch(service))

        for horizon in horizons:
            best_steps, (best_local_loss, effective_h) = min(
                ((steps, values[horizon]) for steps, values in local_candidates.items()),
                key=lambda pair: pair[1][0],
            )
            if ri_candidates:
                selected_identity, selected = min(
                    ri_candidates.items(), key=lambda pair: pair[1][3][horizon][0]
                )
                alternative, adapted, selected_assess_loss, ri_prefix = selected
                best_ri_loss = ri_prefix[horizon][0]
                selected_architecture = alternative.architecture
                selected_source = alternative.source_initialization_id
            else:
                selected_identity = "NONE"
                best_ri_loss = float("nan")
                selected_architecture = "NONE"
                selected_source = "NONE"
                selected_assess_loss = float("nan")
            recoverability = tau_service - best_local_loss
            ri_gain = best_local_loss - best_ri_loss if np.isfinite(best_ri_loss) else float("nan")
            u_bounds, a_bounds, s_bounds = spans(stage)
            stage_rows.append(
                {
                    "run_id": f"p3-{scenario}-{base.center_id}-{seed}",
                    "center_id": base.center_id,
                    "center_pool": "development",
                    "seed": seed,
                    "scenario": scenario,
                    "scenario_subtype": scenario_meta["definition"],
                    "stage": stage,
                    "recoverability_horizon": horizon,
                    "effective_horizon": effective_h,
                    "incumbent_identity_id": identity_id,
                    "incumbent_architecture": incumbent.architecture,
                    "incumbent_source_init_id": incumbent.source_initialization_id,
                    "incumbent_state_hash": before_hash,
                    "D_upd_hash": update.hash,
                    "D_assess_hash": assessment.hash,
                    "D_srv_hash": service.hash,
                    "probe_state_hash": state_hash(probe),
                    "probe_update_count": 50,
                    "probe_pre_assess_loss": pre_loss,
                    "probe_post_assess_loss": post_loss,
                    "probe_gain": gain,
                    "probe_residual": post_loss,
                    "probe_effort": 50,
                    "feature_vector_hash": canonical_hash([gain, post_loss]),
                    "feature_components": "gain,residual",
                    "recoverability_oracle_approx": recoverability,
                    "oracle_recoverable": bool(recoverability >= 0),
                    "tau_service": tau_service,
                    "best_local_policy": f"P{best_steps}",
                    "best_bounded_local_horizon_loss": best_local_loss,
                    "best_reinstantiation_horizon_loss": best_ri_loss,
                    "reinstantiation_gain": ri_gain,
                    "num_bank_candidates": len(identities),
                    "num_feasible_alternatives": len(alternatives),
                    "best_alternative_identity_id": selected_identity,
                    "best_alternative_architecture": selected_architecture,
                    "best_alternative_source_init_id": selected_source,
                    "selected_assess_loss": selected_assess_loss,
                    "service_mse": service_mse,
                    "service_mae": service_mae,
                    "local_probe_time_s": probe_time,
                    "operation_count": incumbent.operation_count,
                    "parameter_count": incumbent.parameter_count,
                    "operation_limit": limits["operations"],
                    "parameter_limit": limits["parameters"],
                    "deployment_feasible": feasible(incumbent, limits),
                    "update_start_ts": int(update.ts[0]),
                    "assessment_ts": int(assessment.ts[-1]),
                    "decision_ts": int(assessment.ts[-1]),
                    "service_start_ts": int(service.ts[0]),
                    "service_end_ts": int(service.ts[-1]),
                    "oracle_future_data_offline_only": True,
                    "scenario_hash": canonical_hash(scenario_meta),
                }
            )
        parent = probe

    audit = {
        "run_id": f"p3-{scenario}-{base.center_id}-{seed}",
        "scenario": scenario,
        "center_id": base.center_id,
        "seed": seed,
        "initial_state_hash": initial_hash,
        "bank_hash": bank_hash(identities),
        "parent_immutable_during_probe": all(parent_integrity),
        "candidate_count": len(alternatives),
        "deployment_tier": base.budget_tier,
        "scenario_metadata": scenario_meta,
    }
    return P3RunResult(stage_rows, candidate_rows, audit)
