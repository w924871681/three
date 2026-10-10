from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from imported.ravm_dt.main_cfg import MainCfg
from imported.ravm_dt.sim import simulate_centers

from .common import array_digest
from .protocol import CausalTimeline, Segment, spans


@dataclass
class BaseCenter:
    center_id: int
    center_type: str
    budget_tier: str
    dt: int
    x: np.ndarray
    y: np.ndarray
    ts: np.ndarray
    metadata: dict


def feature_matrix(raw_x: np.ndarray, dt: int) -> np.ndarray:
    gap = np.full((len(raw_x), 1), float(dt) / 4.0, dtype=np.float32)
    return np.concatenate([raw_x.astype(np.float32), gap], axis=1)


def generate_base_centers(
    center_ids: list[int], data_seed: int = 7311, n_history: int = 17000
) -> list[BaseCenter]:
    if not center_ids:
        return []
    expected = list(range(int(center_ids[0]), int(center_ids[0]) + len(center_ids)))
    if [int(value) for value in center_ids] != expected:
        raise ValueError("center_ids must be a contiguous ordered range")
    cfg = MainCfg()
    cfg.sim.seed = data_seed
    cfg.sim.n_history = int(n_history)
    for kind in "ABC":
        getattr(cfg.sim, f"type_{kind}").drift_prob = 0.0
    generated = simulate_centers(
        cfg,
        len(center_ids),
        seed_offset=center_ids[0] * 17,
        start_center_id=center_ids[0],
    )
    result = []
    for center in generated:
        raw_x = np.concatenate([center.X, center.M], axis=1).astype(np.float32)
        result.append(
            BaseCenter(
                center_id=center.center_id,
                center_type=center.center_type,
                budget_tier=center.budget_tier,
                dt=center.dt,
                x=raw_x,
                y=center.y.astype(np.float32),
                ts=center.timestamps.astype(np.int64),
                metadata=center.metadata,
            )
        )
    return result


def full_windows(x: np.ndarray, dt: int, length: int = 96) -> tuple[np.ndarray, np.ndarray]:
    features = feature_matrix(x, dt)
    count = len(features) - length
    windows_x = np.lib.stride_tricks.sliding_window_view(features, length, axis=0)[:count]
    return windows_x.transpose(0, 2, 1).copy(), np.arange(length, len(features), dtype=np.int64)


def _logit(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(value, 1e-5, 1 - 1e-5)
    return np.log(clipped / (1 - clipped))


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -12, 12)))


def _physical_shift(base: BaseCenter, shift: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    active = shift != 0
    y = base.y.copy()
    y[active] = _sigmoid(_logit(base.y[active]) + shift[active]).astype(np.float32)
    values = base.x[:, :12].copy()
    masks = base.x[:, 12:].copy()
    gains = base.metadata["metric_gains"]
    delays = base.metadata["metric_delays"]
    for index, gain in enumerate(gains):
        delay = int(delays[index] // base.dt)
        delayed = np.concatenate([np.repeat(shift[0], delay), shift[:-delay]]) if delay else shift
        metric_active = delayed != 0
        values[metric_active, index] = (
            _sigmoid(_logit(values[metric_active, index]) + float(gain) * delayed[metric_active])
            * masks[metric_active, index]
        ).astype(np.float32)
    return np.concatenate([values, masks], axis=1), y


def make_scenario(base: BaseCenter, scenario: str, teacher_predictions: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, dict]:
    n = len(base.y)
    index = np.arange(n)
    onset = 1400 + 8 * 640
    shift = np.zeros(n, dtype=np.float64)
    metadata = {"scenario": scenario, "onset_raw_index": onset, "generator_revision": "p3_prespecified_v1"}
    if scenario == "C1":
        shift = 0.8 * np.clip((index - onset) / (8 * 640), 0, 1)
        x, y = _physical_shift(base, shift)
        metadata["definition"] = "within-family gradual logit and metric shift"
    elif scenario == "C2":
        shift[index >= onset] = 0.8
        x, y = _physical_shift(base, shift)
        metadata["definition"] = "within-family abrupt logit and metric shift"
    elif scenario == "C6":
        shift[((index >= onset) & (index < 1400 + 16 * 640))] = 0.8
        x, y = _physical_shift(base, shift)
        metadata["definition"] = "A-B-A recurring within-family parameter regime"
    elif scenario in {"C3", "C4", "C8"}:
        x, y = base.x.copy(), base.y.copy()
        teacher = "msa_a57_medet" if scenario == "C3" else "msa_a46_pt"
        pred = teacher_predictions[teacher]
        valid = np.isfinite(pred) & (index >= onset)
        y[valid] = np.clip(0.8 * pred[valid] + 0.2 * y[valid], 0, 1)
        metadata["teacher_identity"] = teacher
        metadata["teacher_blend"] = 0.8
        metadata["definition"] = (
            "same-architecture frozen source-initialization replacement stress condition"
            if scenario == "C3"
            else "frozen TCN-teacher architecture replacement stress condition"
        )
        metadata["construct_validity_boundary"] = "teacher-defined controlled stress condition; not evidence of natural prevalence"
    else:
        x, y = base.x.copy(), base.y.copy()
        metadata["definition"] = "stationary clean regime" if scenario == "C0" else "stationary regime with transient decision-time corruption"
    return x.astype(np.float32), y.astype(np.float32), metadata


def corrupt_decision_segment(segment: Segment, scenario: str, center: int, stage: int, model_seed: int) -> Segment:
    active = (scenario == "C7" and stage in {9, 10}) or (scenario == "C8" and stage >= 9)
    if not active:
        return segment
    alpha = 0.20 if scenario == "C7" else 0.10
    result = segment.copy()
    rng = np.random.default_rng(np.random.SeedSequence([9417, center, stage, model_seed, 0 if segment.role == "update" else 1]))
    for block in np.array_split(np.arange(len(result.y)), 10):
        count = int(np.floor(len(block) * alpha))
        if not count:
            continue
        ids = rng.choice(block, count, replace=False)
        if scenario == "C7":
            result.x[ids, :12] = (
                np.clip(result.x[ids, :12] + rng.normal(0, 0.15, (count, 12)), 0, 1)
                * result.x[ids, 12:24]
            )
            result.y[ids] = np.clip(result.y[ids] + rng.normal(0, 0.15, count), 0, 1)
        else:
            result.x[ids, :6] = np.clip(result.x[ids, :6] + 0.2, 0, 1) * result.x[ids, 12:18]
            result.y[ids] = np.clip(result.y[ids] + 0.2, 0, 1)
    return result


def timeline_for(base: BaseCenter, scenario: str, teachers: dict[str, np.ndarray]) -> tuple[CausalTimeline, dict]:
    x, y, metadata = make_scenario(base, scenario, teachers)
    return CausalTimeline(feature_matrix(x, base.dt), y, base.ts, scenario, base.center_id), metadata


def scenario_hash(base: BaseCenter, scenario: str, teachers: dict[str, np.ndarray]) -> str:
    x, y, _ = make_scenario(base, scenario, teachers)
    return array_digest(x, y, base.ts)
