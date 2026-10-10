"""Exact lazy selection from the frozen contiguous generator stream.

The frozen generator schedules a whole contiguous batch before assigning a
per-center RNG seed. This adapter reproduces that schedule and calls the
*unchanged* generator helper functions only for requested center IDs. It must
be equality-tested against ``generate_base_centers`` on test-only IDs before
any P7.6B execution. It does not change scientific random-number semantics.
"""
from __future__ import annotations

import numpy as np

from imported.ravm_dt.main_cfg import MainCfg
from imported.ravm_dt.sim import (
    _apply_monitoring_missingness,
    _generate_clean_metrics,
    _generate_latent_workload,
    _make_type_schedule,
    _sample_budget_tier,
)

from .data import BaseCenter


def selected_base_centers(
    *, start: int, count: int, selected_ids: list[int], data_seed: int = 7311,
    n_history: int = 17000,
) -> list[BaseCenter]:
    """Generate only selected centers, preserving full-batch ID/seed semantics."""
    wanted = set(map(int, selected_ids))
    if len(wanted) != len(selected_ids):
        raise ValueError("duplicate selected center ID")
    if not wanted.issubset(set(range(start, start + count))):
        raise ValueError("selected center outside frozen stream")
    cfg = MainCfg()
    cfg.sim.seed = int(data_seed)
    cfg.sim.n_history = int(n_history)
    for kind in "ABC":
        getattr(cfg.sim, f"type_{kind}").drift_prob = 0.0
    sim_cfg = cfg.sim
    rng0 = np.random.RandomState(int(sim_cfg.seed) + int(start * 17))
    schedule = _make_type_schedule(
        n_centers=count, type_ratio=tuple(sim_cfg.type_ratio),
        allowed_types=["A", "B", "C"], rng=rng0,
    )
    result = []
    for local_id, ctype in enumerate(schedule):
        center_id = start + local_id
        center_seed = int(rng0.randint(0, 2**31 - 1))
        if center_id not in wanted:
            continue
        rng = np.random.RandomState(center_seed)
        type_cfg = getattr(sim_cfg, f"type_{ctype}")
        dt = int(rng.choice(type_cfg.dt_choices))
        kmax = int(sim_cfg.k_max)
        t_obs = int(sim_cfg.n_history)
        t_base = int(sim_cfg.max_metric_delay) + (t_obs - 1) * dt + 1
        y_base, workload_meta = _generate_latent_workload(t_base, type_cfg, sim_cfg, rng)
        x_base, metric_meta = _generate_clean_metrics(y_base, kmax, sim_cfg, rng)
        sample_idx = int(sim_cfg.max_metric_delay) + np.arange(t_obs, dtype=np.int64) * dt
        y_true = y_base[sample_idx].astype(np.float32)
        x_clean = x_base[sample_idx].astype(np.float32)
        d = int(rng.randint(type_cfg.schema_drop_range[0], type_cfg.schema_drop_range[1] + 1))
        d = min(d, kmax - 1)
        schema_mask = np.ones((kmax,), dtype=np.float32)
        if d > 0:
            drop_idx = rng.choice(kmax, size=d, replace=False)
            schema_mask[drop_idx] = 0.0
        miss_rate = float(rng.uniform(*type_cfg.miss_rate_range))
        miss_block_len = int(rng.randint(type_cfg.miss_block_len_range[0], type_cfg.miss_block_len_range[1] + 1))
        noise_sigma = float(rng.uniform(*type_cfg.noise_sigma_range))
        mask = np.ones((t_obs, kmax), dtype=np.float32)
        mask[:, schema_mask < 0.5] = 0.0
        missing_meta = _apply_monitoring_missingness(
            M=mask, schema_mask=schema_mask, miss_rate=miss_rate,
            miss_block_len=miss_block_len, sim_cfg=sim_cfg, rng=rng,
        )
        obs_noise = rng.normal(0.0, noise_sigma, size=x_clean.shape).astype(np.float32)
        x_observed = np.clip(x_clean + obs_noise, 0.0, 1.0)
        x_filled = (x_observed * mask).astype(np.float32)
        tier = _sample_budget_tier(cfg.budget, ctype, rng)
        metadata = {
            "generator": "hierarchical_stochastic_v2",
            "center_type": ctype,
            "dt": dt,
            "miss_rate_draw": miss_rate,
            "miss_block_len_draw": miss_block_len,
            "noise_sigma_draw": noise_sigma,
            "schema_drop_count": d,
            "observed_ratio": float(mask.mean()),
            **workload_meta,
            **metric_meta,
            **missing_meta,
        }
        raw_x = np.concatenate([x_filled, mask], axis=1).astype(np.float32)
        result.append(BaseCenter(
            center_id=center_id, center_type=ctype, budget_tier=tier, dt=dt,
            x=raw_x, y=y_true, ts=sample_idx.astype(np.int64), metadata=metadata,
        ))
    if len(result) != len(wanted):
        raise AssertionError("selected center generation incomplete")
    return result
