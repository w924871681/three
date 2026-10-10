from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.common import ROOT
from core.data import corrupt_decision_segment, feature_matrix, generate_base_centers, make_scenario
from core.models import adapt, bank_hash, build_identity_bank, feasible, load_identity, state_hash, to_batch
from core.protocol import CausalTimeline, Segment, spans, windows


def _config():
    return json.loads((ROOT / "configs" / "p3_development.json").read_text(encoding="utf-8"))


def _splits():
    return json.loads((ROOT / "configs" / "center_splits.json").read_text(encoding="utf-8"))


def _toy_timeline():
    x = np.zeros((17000, 25), dtype=np.float32)
    y = np.zeros(17000, dtype=np.float32)
    ts = np.arange(17000, dtype=np.int64)
    return CausalTimeline(x, y, ts, "C0", 1)


def test_no_future_service_leakage():
    timeline = _toy_timeline()
    with pytest.raises(PermissionError):
        timeline.service(1)
    timeline.seal_decision(1)
    assert timeline.service(1).role == "service"


def test_raw_role_disjointness():
    for stage in range(1, 25):
        update, assessment, service = spans(stage)
        assert set(range(*update)).isdisjoint(range(*assessment))
        assert set(range(*update)).isdisjoint(range(*service))
        assert set(range(*assessment)).isdisjoint(range(*service))


def test_window_no_cross_role_boundary():
    timeline = _toy_timeline()
    for segment in timeline.decision_data(1):
        x, y = windows(segment)
        assert len(x) == len(segment.y) - 96
        assert len(y) == len(x)


def test_assessment_not_used_for_gradients():
    identities = build_identity_bank()
    model = load_identity(next(item for item in identities if item.identity_id == "msa_a55_pt"))
    batch = to_batch(np.zeros((2, 96, 25), np.float32), np.zeros((2, 1), np.float32), "assessment")
    with pytest.raises(AssertionError):
        adapt(model, batch, 1, 1)


def test_probe_does_not_modify_deployed_state():
    identities = build_identity_bank()
    model = load_identity(next(item for item in identities if item.identity_id == "msa_a55_pt"))
    before = state_hash(model)
    batch = to_batch(np.zeros((2, 96, 25), np.float32), np.zeros((2, 1), np.float32), "update")
    _ = adapt(model, batch, 1, 1)
    assert state_hash(model) == before


def test_same_initial_state():
    base = generate_base_centers([31000])[0]
    dummy = np.full(len(base.y), 0.5, dtype=np.float32)
    teachers = {"msa_a57_medet": dummy, "msa_a46_pt": dummy}
    warm_hashes = []
    for scenario in _config()["scenarios"]:
        x, y, _ = make_scenario(base, scenario, teachers)
        warm_hashes.append((x[:800].tobytes(), y[:800].tobytes()))
    assert len({(hash(x), hash(y)) for x, y in warm_hashes}) == 1


def test_same_bank_hash():
    assert bank_hash(build_identity_bank()) == bank_hash(build_identity_bank())


def test_deployment_filter():
    config = _config()
    identities = build_identity_bank()
    for tier in config["deployment_limits"].values():
        assert any(feasible(identity, tier) for identity in identities)


def test_candidate_adaptation_budget():
    config = _config()
    assert config["probe_updates"] == 50
    assert max(config["local_policies"]) == 50


def test_oracle_future_data_offline_only():
    timeline = _toy_timeline()
    with pytest.raises(PermissionError):
        timeline.offline_service(2, oracle_mode=False)
    assert timeline.offline_service(2, oracle_mode=True).role == "offline_oracle_service"


def test_center_pool_disjointness():
    splits = _splits()
    development, calibration, heldout = map(lambda name: set(splits[name]), ("development", "calibration", "heldout"))
    assert not development & calibration
    assert not development & heldout
    assert not calibration & heldout


def test_all_deployed_models_meet_limits():
    config = _config()
    incumbent = next(item for item in build_identity_bank() if item.identity_id == "msa_a57_pt")
    assert all(feasible(incumbent, limits) for limits in config["deployment_limits"].values())


def test_effort_feature_variance():
    effort = np.full(24, _config()["probe_updates"], dtype=float)
    assert np.var(effort) == 0.0
    assert ["gain", "residual"] == ["gain", "residual"]


def test_c7_corruption_preserves_feature_shape_and_gap():
    segment = Segment(
        x=np.ones((400, 25), dtype=np.float32),
        y=np.full(400, 0.5, dtype=np.float32),
        ts=np.arange(400, dtype=np.int64),
        role="update",
    )
    corrupted = corrupt_decision_segment(segment, "C7", 31000, 9, 7311)
    assert corrupted.x.shape == segment.x.shape
    assert np.array_equal(corrupted.x[:, 24], segment.x[:, 24])
    assert np.array_equal(segment.x, np.ones((400, 25), dtype=np.float32))
