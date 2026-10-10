from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .common import canonical_hash
from .data import BaseCenter
from .models import ModelIdentity, adapt, evaluate, load_identity, state_hash, to_batch
from .p3_2_data import timeline_for_v2
from .protocol import Segment, windows


FEATURE_COLUMNS = [
    "mean_gain_short",
    "mean_residual_short",
    "mean_gain_long",
    "mean_residual_long",
    "coverage_short",
    "coverage_long",
]


def _batch(segment: Segment):
    x, y = windows(segment)
    return to_batch(x, y, segment.role)


def initial_model(base: BaseCenter, seed: int, incumbent: ModelIdentity, timeline):
    model = load_identity(incumbent)
    return adapt(model, _batch(timeline.warmup()), steps=50, seed=seed + base.center_id)


def _service_curve(model, service_batches: dict[int, object], stage: int, horizon: int) -> list[float]:
    if hasattr(model, "rnn"):
        model.rnn.flatten_parameters()
    return [
        evaluate(model, service_batches[future_stage])[0]
        for future_stage in range(stage, min(24, stage + horizon - 1) + 1)
    ]


@dataclass
class P6Trajectory:
    rows: list[dict]
    reference_losses: list[float]


def run_p6_trajectory(
    base: BaseCenter,
    seed: int,
    scenario: str,
    incumbent: ModelIdentity,
    config: dict,
    tau_service: float | None,
) -> P6Trajectory:
    """Materialize causal response events and the offline H=4/B50 target only.

    No alternative identity is loaded or evaluated. Future service is visible only
    to the offline target path. The current response event is constructed from the
    update/assessment roles before the stage decision is sealed.
    """

    horizon = 4
    local_policies = [0, 10, 20, 50]
    timeline, scenario_meta = timeline_for_v2(base, scenario, config)
    service_batches = {
        stage: _batch(timeline.offline_service(stage, oracle_mode=True))
        for stage in range(1, 25)
    }
    parent = initial_model(base, seed, incumbent, timeline)
    rows: list[dict] = []
    reference_losses: list[float] = []

    for stage in range(1, 25):
        update, assessment = timeline.decision_data(stage)
        update_batch = _batch(update)
        assessment_batch = _batch(assessment)
        before_hash = state_hash(parent)
        probe = adapt(parent, update_batch, steps=50, seed=seed + base.center_id + stage * 100)
        if before_hash != state_hash(parent):
            raise AssertionError("copied local probe modified the deployed parent")

        pre_loss, _ = evaluate(parent, assessment_batch)
        post_loss, _ = evaluate(probe, assessment_batch)
        gain = (pre_loss - post_loss) / (pre_loss + 1e-12)

        horizon_losses: dict[int, float] = {}
        current_probe_service_loss = None
        effective_horizon = min(horizon, 25 - stage)
        for steps in local_policies:
            if steps == 0:
                candidate = copy.deepcopy(parent)
            elif steps == 50:
                candidate = probe
            else:
                candidate = adapt(
                    parent,
                    update_batch,
                    steps=steps,
                    seed=seed + base.center_id + stage * 1000 + steps,
                )
            curve = _service_curve(candidate, service_batches, stage, horizon)
            horizon_losses[steps] = float(np.mean(curve))
            if steps == 50:
                current_probe_service_loss = float(curve[0])

        if scenario == "C0" and stage <= 8:
            if current_probe_service_loss is None:
                raise AssertionError("missing C0 reference service loss")
            reference_losses.append(current_probe_service_loss)

        best_steps = min(local_policies, key=lambda value: horizon_losses[value])
        best_loss = horizon_losses[best_steps]
        timeline.seal_decision(stage)
        service = timeline.service(stage)
        rows.append(
            {
                "run_id": f"p6-{scenario}-{base.center_id}-{seed}",
                "phase": "p6_fitting",
                "center_id": base.center_id,
                "center_pool": "p4_frozen_estimator_fitting",
                "center_type": base.center_type,
                "deployment_tier": base.budget_tier,
                "seed": seed,
                "scenario": scenario,
                "scenario_role": (
                    "secondary Nonlinear Dependency-Shift Stress"
                    if scenario == "C4"
                    else scenario_meta["definition"]
                ),
                "stage": stage,
                "identity_id": incumbent.identity_id,
                "incumbent_state_hash": before_hash,
                "probe_state_hash": state_hash(probe),
                "probe_update_count": 50,
                "probe_pre_assess_loss": pre_loss,
                "probe_post_assess_loss": post_loss,
                "probe_gain": gain,
                "probe_residual": post_loss,
                "feature_event_hash": canonical_hash([gain, post_loss]),
                "feature_components": "gain,residual",
                "recoverability_horizon": horizon,
                "effective_horizon": effective_horizon,
                "best_policy_B50": f"P{best_steps}",
                "best_loss_B50": best_loss,
                "probe_current_service_loss_offline": current_probe_service_loss,
                "tau_service": tau_service,
                "R_B50": None if tau_service is None else float(tau_service - best_loss),
                "D_upd_hash": update.hash,
                "D_assess_hash": assessment.hash,
                "D_srv_hash": service.hash,
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

    return P6Trajectory(rows=rows, reference_losses=reference_losses)


def attach_tau(rows: list[dict], tau_service: float) -> list[dict]:
    result = []
    for row in rows:
        value = dict(row)
        value["tau_service"] = float(tau_service)
        value["R_B50"] = float(tau_service - float(value["best_loss_B50"]))
        result.append(value)
    return result


def causal_history_features(events: pd.DataFrame, k_short: int, k_long: int) -> pd.DataFrame:
    if not 0 < k_short < k_long:
        raise ValueError("require 0 < K_S < K_L")
    required = {
        "center_id", "seed", "scenario", "stage", "identity_id",
        "probe_gain", "probe_residual", "R_B50",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"missing event columns: {missing}")

    ordered = events.sort_values(["center_id", "seed", "scenario", "stage"]).copy()
    rows: list[dict] = []
    for _, group in ordered.groupby(["center_id", "seed", "scenario"], sort=False):
        history: list[tuple[float, float]] = []
        prior_identity = None
        prior_stage = None
        for event in group.itertuples(index=False):
            if prior_stage is not None and int(event.stage) != prior_stage + 1:
                raise AssertionError("response history has a missing or reordered stage")
            if prior_identity is None or event.identity_id != prior_identity:
                history = []
            history.append((float(event.probe_gain), float(event.probe_residual)))
            short = np.asarray(history[-k_short:], dtype=np.float64)
            long = np.asarray(history[-k_long:], dtype=np.float64)
            rows.append(
                {
                    **{column: getattr(event, column) for column in ordered.columns},
                    "history_size": len(history),
                    "K_S": k_short,
                    "K_L": k_long,
                    "mean_gain_short": float(short[:, 0].mean()),
                    "mean_residual_short": float(short[:, 1].mean()),
                    "mean_gain_long": float(long[:, 0].mean()),
                    "mean_residual_long": float(long[:, 1].mean()),
                    "coverage_short": float(len(short) / k_short),
                    "coverage_long": float(len(long) / k_long),
                }
            )
            prior_identity = event.identity_id
            prior_stage = int(event.stage)
    result = pd.DataFrame(rows)
    if result[FEATURE_COLUMNS].shape[1] != 6 or result[FEATURE_COLUMNS].isna().any().any():
        raise AssertionError("P6 feature matrix must contain exactly six complete dimensions")
    return result


def fit_scaler(values: np.ndarray) -> dict[str, list[float]]:
    matrix = np.asarray(values, dtype=np.float64)
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=0)
    scale[scale == 0] = 1.0
    return {"mean": mean.tolist(), "scale": scale.tolist()}


def apply_scaler(values: np.ndarray, scaler: dict[str, list[float]]) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    return (matrix - np.asarray(scaler["mean"])) / np.asarray(scaler["scale"])
