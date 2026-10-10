"""Outcome-free replay of the frozen generator's center metadata RNG path.

This script consumes RNG draws to reach the metadata tier choice. It never
constructs latent workload, monitoring signals, labels, or experiment outcomes.
It is an audit utility, not an alternative scientific generator.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imported.ravm_dt.main_cfg import MainCfg
from imported.ravm_dt.sim import _make_type_schedule, _sample_budget_tier


def metadata_stream(start: int, count: int, data_seed: int = 7311) -> list[dict]:
    cfg = MainCfg()
    cfg.sim.seed = data_seed
    cfg.sim.n_history = 17000
    for kind in "ABC":
        getattr(cfg.sim, f"type_{kind}").drift_prob = 0.0
    sim = cfg.sim
    rng0 = np.random.RandomState(int(sim.seed) + int(start * 17))
    schedule = _make_type_schedule(count, tuple(sim.type_ratio), ["A", "B", "C"], rng0)
    result = []
    for local_id, ctype in enumerate(schedule):
        rng = np.random.RandomState(int(rng0.randint(0, 2**31 - 1)))
        type_cfg = getattr(sim, f"type_{ctype}")
        dt = int(rng.choice(type_cfg.dt_choices))
        t_base = int(sim.max_metric_delay) + (int(sim.n_history) - 1) * dt + 1

        # _generate_latent_workload RNG calls, without constructing y.
        for low, high in (
            type_cfg.base_logit_range,
            type_cfg.cycle_amp_range,
            (0.0, 2.0 * np.pi),
            (0.0, 2.0 * np.pi),
            (0.0, 2.0 * np.pi),
            type_cfg.ar_phi_range,
            type_cfg.process_sigma_range,
        ):
            rng.uniform(low, high)
        rng.normal(0.0, 1.0, size=t_base)
        burst_rate = float(rng.uniform(*type_cfg.burst_rate_range))
        n_bursts = int(rng.poisson(burst_rate * t_base / 1000.0))
        for _ in range(n_bursts):
            rng.randint(0, t_base)
            rng.uniform(2.0, 14.0)
            rng.uniform(*type_cfg.burst_amp_range)
        if rng.rand() < float(type_cfg.drift_prob):
            rng.randint(int(0.45 * t_base), max(int(0.46 * t_base), int(0.75 * t_base)))
            rng.uniform(*type_cfg.drift_strength_range)
            rng.rand()
            rng.rand()

        # _generate_clean_metrics RNG calls, without constructing X.
        for _ in range(int(sim.k_max)):
            rng.randint(0, int(sim.max_metric_delay) + 1)
            rng.uniform(*sim.metric_gain_range)
            rng.uniform(*sim.metric_bias_range)
            rng.uniform(*sim.metric_quad_range)
            rng.uniform(*sim.metric_process_sigma)
            rng.uniform(0.0, 2.0 * np.pi)
            rng.normal(0.0, 1.0, size=t_base)

        # Schema/noise/missingness RNG calls. Only the schema index set is
        # needed to reproduce subsequent random choices.
        kmax = int(sim.k_max)
        d = int(rng.randint(type_cfg.schema_drop_range[0], type_cfg.schema_drop_range[1] + 1))
        d = min(d, kmax - 1)
        active = np.arange(kmax)
        if d > 0:
            dropped = rng.choice(kmax, size=d, replace=False)
            active = active[~np.isin(active, dropped)]
        rng.uniform(*type_cfg.miss_rate_range)
        miss_block_len = int(rng.randint(type_cfg.miss_block_len_range[0], type_cfg.miss_block_len_range[1] + 1))
        rng.uniform(*type_cfg.noise_sigma_range)
        n_history = int(sim.n_history)
        rng.rand(n_history, kmax)
        mb_cfg = sim.missing_block
        n_metric_blocks = int(rng.randint(mb_cfg.metric_block_count_range[0], mb_cfg.metric_block_count_range[1] + 1))
        for _ in range(n_metric_blocks):
            rng.choice(active)
            rng.randint(0, n_history)
            rng.randint(max(1, miss_block_len // 3), max(2, miss_block_len + 1))
        n_group_blocks = int(rng.randint(mb_cfg.group_block_count_range[0], mb_cfg.group_block_count_range[1] + 1))
        for _ in range(n_group_blocks):
            gmin = min(int(mb_cfg.group_size_range[0]), len(active))
            gmax = min(int(mb_cfg.group_size_range[1]), len(active))
            gsize = int(rng.randint(gmin, gmax + 1)) if gmax >= gmin else len(active)
            rng.choice(active, size=gsize, replace=False)
            rng.randint(0, n_history)
            rng.randint(max(2, miss_block_len // 4), max(3, miss_block_len // 2 + 1))
        if rng.rand() < float(mb_cfg.global_outage_prob):
            n_global = int(rng.randint(mb_cfg.global_outage_count_range[0], mb_cfg.global_outage_count_range[1] + 1))
            for _ in range(n_global):
                rng.randint(0, n_history)
                rng.randint(mb_cfg.global_outage_len_range[0], mb_cfg.global_outage_len_range[1] + 1)
        rng.normal(0.0, 1.0, size=(n_history, kmax))
        tier = _sample_budget_tier(cfg.budget, ctype, rng)
        result.append({"center_id": start + local_id, "center_type": ctype, "deployment_tier": tier})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--verify-old", action="store_true")
    args = parser.parse_args()
    rows = metadata_stream(args.start, args.count)
    if args.verify_old:
        if (args.start, args.count) != (32200, 48):
            raise SystemExit("old verification requires start 32200 and count 48")
        frozen = json.loads(Path("configs/P7_4B_CENTER_ASSIGNMENT.json").read_text(encoding="utf-8"))
        expected = [
            {key: row[key] for key in ("center_id", "center_type", "deployment_tier")}
            for row in frozen["centers"]
        ]
        if rows != expected:
            first = next(((a, b) for a, b in zip(rows, expected) if a != b), None)
            raise SystemExit(f"metadata replay mismatch: {first}")
        print("VERIFIED_48_FROZEN_CENTER_METADATA")
    else:
        print(json.dumps(rows, separators=(",", ":")))


if __name__ == "__main__":
    main()
