from __future__ import annotations

import json

import numpy as np

from core.common import ROOT
from core.data import _logit, _sigmoid, generate_base_centers
from core.p3_2_data import ONSET_RAW_INDEX, apply_c3_regime_b, c4_target, make_scenario_v2, target_structure


def _config():
    return json.loads((ROOT / "configs" / "p3_2_protocol.json").read_text(encoding="utf-8"))


def test_p3_2_center_pools_are_disjoint():
    config = _config()
    pools = [
        set(config["source_pair"]["source_centers"]),
        set(config["design_centers"]),
        set(config["fresh_development_centers"]),
        set(config["calibration_centers_forbidden"]),
        set(config["heldout_centers_forbidden"]),
    ]
    assert not any(left & right for i, left in enumerate(pools) for right in pools[i + 1 :])


def test_c3_is_direct_regime_replacement_not_target_blending():
    config = _config()
    base = generate_base_centers([31000])[0]
    replacement_x, replacement_y = apply_c3_regime_b(base, config["c3_regime_b"])
    x, y, metadata = make_scenario_v2(base, "C3", config)
    assert metadata["prediction_output_blending"] is False
    assert np.array_equal(y, base.y)
    assert np.array_equal(replacement_y, base.y)
    assert np.array_equal(x[:ONSET_RAW_INDEX], base.x[:ONSET_RAW_INDEX])
    assert np.array_equal(x[ONSET_RAW_INDEX:], replacement_x[ONSET_RAW_INDEX:])
    assert not np.array_equal(x[ONSET_RAW_INDEX:], base.x[ONSET_RAW_INDEX:])


def test_r3_c3_reverses_source_response_without_output_blending():
    config = _config()
    r3 = json.loads((ROOT / "configs" / "p3_2_protocol_r3.json").read_text(encoding="utf-8"))
    config["generator_revision"] = r3["generator_revision"]
    config["c3_regime_b"].update(r3["c3_regime_b"])
    base = generate_base_centers([31000])[0]
    replacement_x, replacement_y = apply_c3_regime_b(base, config["c3_regime_b"])
    x, y, metadata = make_scenario_v2(base, "C3", config)
    center = float(base.metadata["base_logit"])
    expected = _sigmoid(2 * center - _logit(base.y)).astype(np.float32)
    assert metadata["prediction_output_blending"] is False
    assert metadata["target_unchanged_by_design"] is False
    assert np.allclose(replacement_y, expected, rtol=0, atol=1e-6)
    assert np.array_equal(y[:ONSET_RAW_INDEX], base.y[:ONSET_RAW_INDEX])
    assert np.allclose(y[ONSET_RAW_INDEX:], expected[ONSET_RAW_INDEX:], rtol=0, atol=1e-6)
    assert np.array_equal(x[ONSET_RAW_INDEX:], replacement_x[ONSET_RAW_INDEX:])


def test_c4_changes_dependency_without_teacher_predictions():
    config = _config()
    base = generate_base_centers([31000])[0]
    generated = c4_target(base, config["c4_regime_c"])
    x, y, metadata = make_scenario_v2(base, "C4", config)
    assert metadata["prediction_output_blending"] is False
    assert "teacher" not in metadata
    assert np.array_equal(x, base.x)
    assert np.array_equal(y[:ONSET_RAW_INDEX], base.y[:ONSET_RAW_INDEX])
    assert np.array_equal(y[ONSET_RAW_INDEX:], generated[ONSET_RAW_INDEX:])
    assert not np.array_equal(y[ONSET_RAW_INDEX:], base.y[ONSET_RAW_INDEX:])


def test_design_targets_do_not_trigger_smoothing_stop_rule():
    config = _config()
    bases = generate_base_centers(config["design_centers"], data_seed=config["data_seed"])
    for scenario in ("C3", "C4"):
        ratios = {metric: [] for metric in ("std", "range", "adjacent_rmse")}
        for base in bases:
            reference = target_structure(base.y)
            _, y, _ = make_scenario_v2(base, scenario, config)
            candidate = target_structure(y)
            for metric in ratios:
                ratios[metric].append(candidate[metric] / reference[metric])
        for metric, values in ratios.items():
            threshold = config["generator_only_stop_rules"][f"min_postshift_{metric}_ratio_vs_C0"]
            assert float(np.mean(values)) >= threshold


def test_primary_oracle_setting_and_response_features_remain_frozen():
    config = _config()
    assert config["primary_recoverability_horizon"] == 4
    assert config["primary_eta"] == 0.25
    assert config["local_policies"] == [0, 10, 20, 50]
    assert config["feature_components"] == ["gain", "residual"]
