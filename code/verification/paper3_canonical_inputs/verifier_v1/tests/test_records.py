"""Synthetic-only tests for future, separately authorized execution.

These tests never import project modules, generate real inputs or read results.
The present implementation task authorizes writing, not executing them.
"""
from __future__ import annotations

import csv
import importlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_PACKAGE = "paper3_civ_tests"
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if _PACKAGE not in sys.modules:
    _package = types.ModuleType(_PACKAGE)
    _package.__path__ = [str(_SOURCE_ROOT)]
    sys.modules[_PACKAGE] = _package
elif tuple(sys.modules[_PACKAGE].__path__) != (str(_SOURCE_ROOT),):
    raise RuntimeError("synthetic test package points outside reviewed verifier source")
_contract = importlib.import_module(_PACKAGE + ".contract")
_records = importlib.import_module(_PACKAGE + ".records")
METHODS, ContractError = _contract.METHODS, _contract.ContractError
INPUT_FIELDS = _records.INPUT_FIELDS
_safe_file, group_parity = _records._safe_file, _records.group_parity
match_reference, projected_csv = _records.match_reference, _records.projected_csv


def project_text(text):
    """Mocked read-only open: no directory, temporary file or disk write."""
    with mock.patch.object(Path, "open", return_value=io.StringIO(text)):
        return projected_csv(_SOURCE_ROOT / "synthetic_readonly_fixture.csv")


def csv_text(fields, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def fixture_rows(method="B0", config="fixture"):
    rows = []
    for stage in range(1, 25):
        row = {field: "synthetic" for field in INPUT_FIELDS}
        row.update(method=method, config_id=config, center_id=33000, seed=7311, scenario="C0", stage=stage,
                   center_type="A", deployment_tier="medium", update_end_ts=stage * 10 - 1, decision_ts=stage * 10)
        row.update(D_upd_hash=f"u{stage}", D_assess_hash=f"a{stage}", D_srv_hash=f"s{stage}",
                   scenario_hash="scene", bank_hash="bank", deployment_filter_hash="limits",
                   initial_state_hash="f" * 64, identity_before="msa_a57_pt")
        rows.append(row)
    return rows


def fixture_bundle(rows):
    return {
        "base": {"33000": {"profile": {"center_type": "A", "budget_tier": "medium"},
            "deployment": {"bank_hash": "bank", "deployment_filter_hash": "limits", "feasible_mask": [True],
                           "feasible_ids": ["one"], "initial_candidate_ids": []}}},
        "scenarios": {"33000/C0": {"legacy_scenario_hash": "scene", "metadata": {"definition": "synthetic"}}},
        "roles": {f"33000/C0/{row['stage']}/{role}": {
            "legacy_role_hash": row[field], "update_end_ts": row["update_end_ts"], "decision_ts": row["decision_ts"]}
            for row in rows for role, field in (("update", "D_upd_hash"), ("assessment", "D_assess_hash"), ("service", "D_srv_hash"))},
    }


class RecordProjectionTests(unittest.TestCase):
    def test_poisoned_outcomes_are_discarded_and_later_states_are_not_accessed(self):
        """Non-numeric outcome poison cannot affect an input projection."""
        fields = list(INPUT_FIELDS) + ["service_mse", "predicted_R", "J_life_service_only", "deployed_state_hash"]
        rows = [dict(row, service_mse="DO_NOT_PARSE", predicted_R="DO_NOT_PARSE",
                     J_life_service_only="DO_NOT_PARSE", deployed_state_hash="METHOD_SPECIFIC") for row in fixture_rows()]
        returned = project_text(csv_text(fields, rows))
        self.assertEqual(len(returned), 24)
        self.assertFalse(any(set(row) - set(INPUT_FIELDS) for row in returned))
        self.assertNotIn("identity_before", returned[1])
        self.assertNotIn("initial_state_hash", returned[1])

    def test_missing_non_task_input_fields_remain_missing(self):
        fields = ["method", "config_id", "center_id", "seed", "scenario", "stage"]
        returned = project_text(csv_text(fields, [{key: fixture_rows()[0][key] for key in fields}]))
        self.assertNotIn("D_srv_hash", returned[0])

    def test_duplicate_header_rejected(self):
        with self.assertRaises(ContractError):
            project_text("stage,stage\n1,1\n")

    def test_evidence_traversal_and_absolute_paths_rejected(self):
        for bad in ("../other.csv", "C:/other.csv", "/absolute.csv", "x//file.csv"):
            with self.assertRaises(ContractError):
                _safe_file(_SOURCE_ROOT, bad)


class QualificationTests(unittest.TestCase):
    def test_all_saved_fields_match_but_full_history_and_initial_pending(self):
        rows = fixture_rows()
        result = match_reference(rows, fixture_bundle(rows), 33000, "C0")
        self.assertTrue(result["r1_qualified"])
        self.assertFalse(result["initial_state_verified"])
        self.assertEqual(result["r2_status"], "PENDING_SEPARATE_AUTHORIZATION")
        self.assertEqual(result["static_feasibility"]["evidence_form"], "INDIRECT_FROM_MATCHED_TIER_BANK_HASH_AND_LIMITS_HASH")
        self.assertTrue(all(item["status"] == "NOT_RECORDED" for item in result["not_recorded"]))

    def test_one_of_seventy_two_role_hashes_can_block_qualification(self):
        rows = fixture_rows()
        bundle = fixture_bundle(rows)
        rows[-1]["D_srv_hash"] = "wrong-last-service"
        result = match_reference(rows, bundle, 33000, "C0")
        self.assertFalse(result["r1_qualified"])
        self.assertTrue(any(item["stage"] == 24 and item["field"] == "D_srv_hash" and item["status"] == "OBSERVED_MISMATCH" for item in result["observations"]))

    def test_missing_resource_metadata_cannot_pass_on_arrays_alone(self):
        rows = fixture_rows()
        bundle = fixture_bundle(rows)
        for row in rows:
            row.pop("deployment_filter_hash")
        result = match_reference(rows, bundle, 33000, "C0")
        self.assertFalse(result["r1_qualified"])
        self.assertTrue(any(item["status"] == "NOT_RECORDED" for item in result["observations"]))

    def test_missing_stage_cannot_claim_full_input_coverage(self):
        rows = fixture_rows()
        self.assertFalse(match_reference(rows[:-1], fixture_bundle(rows), 33000, "C0")["r1_qualified"])

    def test_saved_initial_equality_never_upgrades_r2_or_r3(self):
        records = [{"task": {"method": method}, "rows": fixture_rows(method, config), "r0_qualified": True,
                    "matches": {"F": {"r1_qualified": True}, "S": {"r1_qualified": True}}} for method, config in METHODS]
        result = group_parity(records)
        self.assertEqual(result["exogenous_parity"], "MATCH")
        self.assertTrue(result["saved_initial_state_parity"])
        self.assertFalse(result["r2_qualified"])
        self.assertFalse(result["r3_qualified"])
        records[-1]["rows"][0]["initial_state_hash"] = "e" * 64
        result = group_parity(records)
        self.assertEqual(result["exogenous_parity"], "MATCH")
        self.assertFalse(result["saved_initial_state_parity"])

    def test_deployment_mismatch_is_exogenous_and_missing_fields_are_unverifiable(self):
        records = [{"task": {"method": method}, "rows": fixture_rows(method, config)} for method, config in METHODS]
        records[-1]["rows"][0]["deployment_tier"] = "tight"
        self.assertEqual(group_parity(records)["exogenous_parity"], "MISMATCH")
        records[-1]["rows"][0].pop("deployment_tier")
        self.assertEqual(group_parity(records)["exogenous_parity"], "NOT_VERIFIABLE")


if __name__ == "__main__":
    unittest.main()
