"""Outcome-free P7.6B-0 tests. All generated centers here are test-only IDs."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest

from core.data import generate_base_centers
from core.p7_6b_selected_data import selected_base_centers
from scripts import run_p7_6b as runner
from scripts.p7_6b_benchmark import _fixture, _init


def test_frozen_assignment_and_preflight():
    assignment, protocol = runner.preflight()
    runner.validate_assignment(assignment, protocol)
    fit = runner.canonical_tasks(assignment, "fit")
    val = runner.canonical_tasks(assignment, "validation")
    assert len(fit) == len(val) == 432
    assert len({x.key for x in fit + val}) == 864
    assert [x.center_id for x in fit] == sorted(x.center_id for x in fit)
    assert {x.center_id for x in fit}.isdisjoint(x.center_id for x in val)
    assert fit[0].scenario == "C0" and fit[1].scenario == "C1"


def test_denials_and_validation_lock():
    for center in range(33000, 33020):
        with pytest.raises(RuntimeError):
            runner.deny_center(center)
    for mode in ("final-heldout", "Alibaba", "P8"):
        with pytest.raises(RuntimeError):
            runner.deny_mode(mode)
    with pytest.raises(RuntimeError, match="Validation locked"):
        runner.preflight(phase="validation", require_opening=True)
    # The later human decision authorized Fit only; Validation stays closed.
    assert runner.require_execution_authorization("fit")["authorized_phases"] == ["fit"]
    with pytest.raises(RuntimeError, match="not separately authorized"):
        runner.require_execution_authorization("validation")
    with pytest.raises(RuntimeError, match="formal Fit locked"):
        runner.require_r0_fit_release()


def test_selected_generator_byte_parity_on_dummy_stream():
    # Full generator consumes the whole dummy batch; adapter may only materialize
    # selected IDs while reproducing its schedule and per-center RNG exactly.
    start, count = 90000, 6
    selected = [90000, 90002, 90005]
    original = {x.center_id: x for x in generate_base_centers(list(range(start, start + count)), data_seed=7311)}
    lazy = selected_base_centers(start=start, count=count, selected_ids=selected)
    for center in lazy:
        ref = original[center.center_id]
        assert (center.center_type, center.budget_tier, center.dt) == (ref.center_type, ref.budget_tier, ref.dt)
        for field in ("x", "y", "ts"):
            assert np.array_equal(getattr(center, field), getattr(ref, field))
        assert center.metadata == ref.metadata


def test_atomic_receipt_resume_and_corruption(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    task = runner.Task(90000, 7311, "C0", "p", "g", "b")
    csv, scales, receipt, claim = runner.output_paths("fit", task)
    assert not runner.validate_receipt("fit", task, "r")
    runner.atomic_bytes(csv, b"stage,value\n1,1\n")
    with pytest.raises(RuntimeError, match="incomplete"):
        runner.validate_receipt("fit", task, "r")
    runner.atomic_bytes(scales, b"stage,S_m\n0,1\n")
    value = {"trajectory_id": task.key, "center_id": task.center_id,
             "model_seed": task.model_seed, "scenario": task.scenario,
             "protocol_sha256": "p", "generator_sha256": "g", "behavior_sha256": "b",
             "runtime_config_sha256": "r", "status": "COMPLETE", "rows": 24,
             "all_stage_path_matches": True, "trajectory_sha256": runner.sha256_file(csv),
             "scales_sha256": runner.sha256_file(scales)}
    runner.atomic_json(receipt, value)
    assert runner.validate_receipt("fit", task, "r")
    runner.atomic_bytes(csv, b"corrupted")
    with pytest.raises(RuntimeError, match="SHA mismatch"):
        runner.validate_receipt("fit", task, "r")


def test_dummy_scheduler_one_vs_four_exact():
    ids = tuple(range(90000, 90008))
    def collect(workers):
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=("cpu", 1)) as pool:
            result = list(pool.map(_fixture, ids, ["cpu"] * len(ids)))
        return hashlib.sha256(json.dumps([r[1] for r in result], sort_keys=True).encode()).hexdigest()
    assert collect(1) == collect(4)


def test_scale_exact_104_median_floor(monkeypatch):
    from scripts import run_p7_4b as p7b
    class Segment:
        y = np.zeros(200)
        hash = "test-only"
    monkeypatch.setattr(p7b, "batch", lambda segment: segment)
    errors = np.arange(104, dtype=float) / 100
    monkeypatch.setattr(p7b, "point_errors", lambda model, segment: errors)
    scale = p7b.scale_from_reference(None, Segment(), "initial", "dummy", 90000, 1, "C0", 0)
    assert scale["valid_point_error_count"] == 104
    assert scale["S_m"] == float(np.median(errors))
    monkeypatch.setattr(p7b, "point_errors", lambda model, segment: np.zeros(104))
    floor = p7b.scale_from_reference(None, Segment(), "RI", "dummy", 90000, 1, "C0", 1)
    assert floor["S_m"] == 1e-12 and floor["floor_activated"] == 1
    monkeypatch.setattr(p7b, "point_errors", lambda model, segment: np.zeros(103))
    with pytest.raises(AssertionError, match="104"):
        p7b.scale_from_reference(None, Segment(), "RI", "dummy", 90000, 1, "C0", 1)


def test_single_shared_behavior_path_fields():
    from scripts import run_p7_4b as p7b
    row = {"parent_state_hash": "parent", "action": "local",
           "identity_after": "same", "deployed_state_hash": "deployed"}
    path = p7b.paired_path_assert(row, "previous")
    assert row["behavior_path_match"] is True
    assert row["A0_parent_state_hash"] == row["A1_parent_state_hash"]
    assert row["A0_action"] == row["A1_action"]
    assert row["A0_post_action_identity"] == row["A1_post_action_identity"]
    assert row["A0_post_action_path_hash"] == row["A1_post_action_path_hash"] == path


def test_bootstrap_uses_frozen_seed_on_dummy_records():
    import pandas as pd
    from scripts.p7_6b_science import _bootstrap
    rows = []
    for center in range(90000, 90003):
        for target in (-3., -2., -1., 1., 2., 3.):
            rows.append({"center_id": center, "A0_target": target,
                         "A1_target": target / 2,
                         "A0_prediction": target + (center - 90001) * .1,
                         "A1_prediction": target / 2 + (center - 90001) * .02})
    frame = pd.DataFrame(rows)
    a, samples_a = _bootstrap(frame, [90000, 90001, 90002], resamples=5)
    b, samples_b = _bootstrap(frame, [90000, 90001, 90002], resamples=5)
    assert a == b and samples_a.equals(samples_b)
    assert len(samples_a) == 5
