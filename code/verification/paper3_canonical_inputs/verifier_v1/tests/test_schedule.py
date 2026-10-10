"""Synthetic, model-free tests. Authored only; not executed in this task."""
from __future__ import annotations

import importlib
import stat
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
_schedule = importlib.import_module(_PACKAGE + ".schedule")
ContractError = _contract.ContractError
_read_path, resume_decision, task_list = _schedule._read_path, _schedule.resume_decision, _schedule.task_list


def expected_metadata():
    result = {name: f"fixture-{name}" for name in (
        "definition_digest", "dependency_digest", "input_bundle_digest", "scenario_fingerprint",
        "profile_fingerprint", "deployment_fingerprint", "group_reference_fingerprint",
        "role_manifest_fingerprint", "blob_manifest_fingerprint")}
    result.update(role_entry_count=72, group_method_ids=["B0", "B1", "B2", "B8", "P7.7"],
                  completion_state="INPUT_MATERIALIZATION_COMPLETE")
    return result


class ScheduleTests(unittest.TestCase):
    def test_frozen_permutation_is_total_without_random_number_calls(self):
        tasks = task_list()
        self.assertEqual(len(tasks), 1200)
        keys = lambda items: {(t["center_id"], t["seed"], t["scenario"], t["method"]) for t in items}
        self.assertEqual(len(keys(tasks)), 1200)
        self.assertEqual(keys([tasks[(7 * index) % 1200] for index in range(1200)]), keys(tasks))
        self.assertEqual(keys(list(reversed(tasks))), keys(tasks))

    def test_resume_requires_all_scientific_bindings(self):
        names = ("definition_digest", "dependency_digest", "input_bundle_digest", "scenario_fingerprint",
                 "profile_fingerprint", "deployment_fingerprint", "group_reference_fingerprint",
                 "role_manifest_fingerprint", "role_entry_count", "group_method_ids", "blob_manifest_fingerprint", "completion_state")
        expected = expected_metadata()
        expected["runner_hash"] = "compatible-runner"
        same = resume_decision(dict(expected), expected)
        self.assertTrue(same["input_resume_qualified"])
        self.assertFalse(same["model_resume_allowed"])
        for field in names:
            saved = dict(expected)
            saved[field] = "MUTATED"
            self.assertFalse(resume_decision(saved, expected)["input_resume_qualified"])
            saved.pop(field)
            self.assertFalse(resume_decision(saved, expected)["input_resume_qualified"])

    def test_external_initial_claim_cannot_turn_input_verifier_into_model_authorization(self):
        expected = expected_metadata()
        result = resume_decision(dict(expected), expected, initial_state_certificate=True)
        self.assertTrue(result["input_resume_qualified"])
        self.assertFalse(result["initial_state_verified"])
        self.assertFalse(result["model_resume_allowed"])
        self.assertFalse(result["r2_qualified"])
        self.assertFalse(result["r3_qualified"])

    def test_complete_marker_does_not_waive_role_or_group_coverage(self):
        expected = expected_metadata()
        for field, wrong in (("role_entry_count", 71), ("group_method_ids", ["B0"]), ("completion_state", "INTERRUPTED")):
            self.assertFalse(resume_decision(dict(expected, **{field: wrong}), expected)["input_resume_qualified"])

    def test_reader_path_cannot_leave_new_run_root(self):
        for path in ("../../results/p7_7/raw/x.csv", "C:/frozen/x.npy", "/absolute.npy", "a//x.npy"):
            with self.assertRaises(ContractError):
                _read_path(_SOURCE_ROOT, path)
        root = (_SOURCE_ROOT / "synthetic_readonly_run").absolute()
        info = types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
        # Pure mocked filesystem metadata; never create the named path.
        with mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "is_symlink", return_value=False), \
             mock.patch.object(Path, "lstat", return_value=info), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "resolve", lambda self, **kwargs: self.absolute()):
            self.assertEqual(_read_path(root, "data.npy"), root / "data.npy")


if __name__ == "__main__":
    unittest.main()
