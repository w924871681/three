from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import run_p6


def test_p6_nested_undefined_metric_serializes_as_null(tmp_path):
    path = tmp_path / "output.json"
    run_p6.write_json(path, {"baseline": {"spearman": float("nan")}, "alpha": None, "metric": 0.5})
    assert json.loads(path.read_text(encoding="utf-8")) == {"baseline": {"spearman": None}, "alpha": None, "metric": 0.5}
    assert "NaN" not in path.read_text(encoding="utf-8")


def test_p6_dataframe_null_and_infinity_boundary(tmp_path):
    records = run_p6.json_records(pd.DataFrame({"alpha": [0.1, np.nan]}))
    assert records == [{"alpha": 0.1}, {"alpha": None}]
    with pytest.raises(ValueError):
        run_p6.write_json(tmp_path / "invalid.json", {"metric": float("inf")})


def test_p6_recovery_cannot_overwrite_final_refit(tmp_path, monkeypatch):
    monkeypatch.setattr(run_p6, "ROOT", tmp_path)
    path = tmp_path / "configs" / "p6_selected_estimator.json"
    path.parent.mkdir()
    path.write_text('{"final_refit_performed": true}', encoding="utf-8")
    with pytest.raises(AssertionError, match="already frozen"):
        run_p6.recover_saved_cv()
