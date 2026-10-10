import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p7_3_outputs_and_scope() -> None:
    required = [
        "reports/P7_3_ROOT_CAUSE_AUDIT.md",
        "results/p7_3/common_diagnostic_table.csv",
        "results/p7_3/continuous_transport_by_pool.csv",
        "results/p7_3/metrics_by_center.csv",
        "results/p7_3/metrics_by_scenario.csv",
        "results/p7_3/pool_distribution_summary.csv",
        "results/p7_3/center_scale_summary.csv",
        "results/p7_3/rank_vs_sign_summary.csv",
        "results/p7_3/history_coverage_summary.csv",
        "results/p7_3/near_zero_margin_summary.csv",
        "results/p7_3/figures/rhat_vs_oracle_by_pool.png",
        "results/p7_3/figures/pool_margin_distributions.png",
        "results/p7_3/figures/center_bias_and_scale.png",
        "results/p7_3/figures/rank_vs_sign_by_center.png",
        "audits/P7_3_READ_ONLY_AUDIT.json",
        "audits/P7_3_READ_ONLY_AUDIT.sha256",
    ]
    assert all((ROOT / rel).is_file() and (ROOT / rel).stat().st_size > 0 for rel in required)
    audit_path = ROOT / "audits/P7_3_READ_ONLY_AUDIT.json"
    assert sha256_file(audit_path) == (ROOT / "audits/P7_3_READ_ONLY_AUDIT.sha256").read_text().strip()

    common = pd.read_csv(ROOT / "results/p7_3/common_diagnostic_table.csv")
    assert len(common) == 15552
    assert common.groupby("pool").size().to_dict() == {
        "ActionCal-v2": 3456,
        "GateCal-v2": 3456,
        "P6-OOF": 8640,
    }
    assert not common.duplicated(["pool", "center_id", "seed", "scenario", "stage"]).any()
    assert not common.center_id.between(33000, 33019).any()
    assert set(common.scenario) == {"C0", "C1", "C3", "C4"}


def test_p7_3_integrity_and_diagnosis() -> None:
    audit = json.loads((ROOT / "audits/P7_3_READ_ONLY_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["status"] == "VALID_READ_ONLY_AUDIT"
    assert audit["primary_diagnosis"] == "D6_MIXED_OR_INCONCLUSIVE"
    assert audit["secondary_diagnosis"] is None
    checks = audit["integrity_checks"]
    assert checks["heldout_accessed"] is False
    assert checks["alibaba_accessed"] is False
    assert checks["P8_executed"] is False
    assert checks["new_threshold_optimized"] is False
    assert checks["fitted_model_artifact_created"] is False
    assert checks["P7_2_FAIL_preserved"] is True
    assert checks["GateCal_raw_artifacts_unchanged"] is True
    assert checks["ActionCal_raw_artifacts_unchanged"] is True

    transport = pd.read_csv(ROOT / "results/p7_3/continuous_transport_by_pool.csv").set_index("pool")
    assert transport.loc["GateCal-v2", "positive_Spearman_centers"] == 12
    assert transport.loc["ActionCal-v2", "positive_Spearman_centers"] == 5
    assert transport.loc["GateCal-v2", "frozen_macro_balanced_sign_accuracy"] > 0.70
    assert transport.loc["ActionCal-v2", "frozen_macro_balanced_sign_accuracy"] < 0.55


def test_frozen_p6_and_p7_2_hashes_remain_bound() -> None:
    p6 = json.loads((ROOT / "audits/P6_ESTIMATOR_FREEZE.json").read_text(encoding="utf-8"))
    assert sha256_file(ROOT / "artifacts/p6_recoverability_estimator.pt") == p6["estimator_sha256"]
    assert sha256_file(ROOT / "artifacts/p6_recoverability_scaler.json") == p6["scaler_sha256"]
    assert (p6["K_S"], p6["K_L"]) == (2, 6)

    final = json.loads((ROOT / "audits/P7_2_FINAL_CALIBRATION_FREEZE.json").read_text(encoding="utf-8"))
    gate = json.loads((ROOT / "audits/P7_2_GATE_FREEZE.json").read_text(encoding="utf-8"))
    assert final["status"] == "FAIL"
    assert all(sha256_file(ROOT / rel) == expected for rel, expected in final["raw_actioncal_hashes"].items())
    assert all(sha256_file(ROOT / rel) == expected for rel, expected in gate["raw_gatecal_hashes"].items())
