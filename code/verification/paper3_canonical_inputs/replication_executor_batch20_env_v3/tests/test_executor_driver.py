"""Pure in-memory phase/matrix tests; no project, model, generator or disk IO.

Fixtures are independent identifiers and input fields, with outcome sentinels
that fail on comparison/conversion. Phase orchestration uses mocked provenance,
dispatch and publication. These are integrity tests, not scientific statistics.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import call, patch


NAME = "paper3_replication_synthetic_tests"
ROOT = Path(__file__).resolve().parents[1]
if NAME not in sys.modules:
    package = types.ModuleType(NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[NAME] = package
elif tuple(sys.modules[NAME].__path__) != (str(ROOT),):
    raise RuntimeError("synthetic package bound to another source root")
d = importlib.import_module(NAME + ".executor_driver")
SHA = "a" * 64


class PrepareRootAllowanceSyntheticTests(unittest.TestCase):
    def test_pre_freeze_checks_stay_under_stage_c_tests_and_no_other_root_is_admitted(self):
        class EvidenceGateReached(RuntimeError):pass
        with tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"]) as folder:
            root=Path(folder)
            (root/"RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md").write_text("synthetic authorization",encoding="utf-8")
            (root/"stage_c_tests/model_load_compatibility/attempt001").mkdir(parents=True)
            args=types.SimpleNamespace(phase="prepare",test_attempt=1)
            with patch.object(d,"RESULTS",root),\
                 patch.object(d.p,"checked_path",side_effect=lambda base,relative:Path(base)/relative),\
                 patch.object(d.p,"read_json",side_effect=EvidenceGateReached("synthetic stop before source freeze")) as read:
                with self.assertRaises(EvidenceGateReached):d.run(args)
                read.assert_called_once_with(root/"stage_c_tests/attempt001/results.json")
                read.reset_mock()
                (root/"unexpected_root_output").mkdir()
                with self.assertRaisesRegex(RuntimeError,"Unexpected pre-existing output"):
                    d.run(args)
                read.assert_not_called()


class ForbiddenOutcome:
    def __float__(self):
        raise AssertionError("performance value entered integrity gate")

    def __eq__(self, other):
        raise AssertionError("performance value compared by integrity gate")

    def __lt__(self, other):
        raise AssertionError("performance value ranked by integrity gate")


def entries(selected=None, with_poison=False):
    selected = d.tasks()[:5] if selected is None else selected
    output = {}
    for task in selected:
        rows = []
        for stage in range(1, 25):
            row = {field: f"synthetic_input_{field}_{task['center_id']}_{task['seed']}_{task['scenario']}_{stage}"
                   for field in d.INPUT_FIELDS}
            row.update(stage=stage, initial_state_hash=SHA, bank_hash=SHA,
                       deployment_filter_hash=SHA, deployment_tier="synthetic_tier")
            if with_poison:
                row.update(service_mse=ForbiddenOutcome(), regret=ForbiddenOutcome(),
                           identity_after=f"normally_diverging_{task['method']}_{stage}",
                           state_after=f"method_specific_{task['method']}_{stage}")
            rows.append(row)
        output[d.stem(task)] = {"task": copy.deepcopy(task), "rows": rows, "receipt_sha256": SHA}
    return output


class MatrixAndPairingTests(unittest.TestCase):
    def test_exact_predeclared_1200_matrix_and_order(self):
        actual = d.tasks()
        expected = [{"center_id": center, "seed": seed, "scenario": scenario, "method": method, "config_id": config}
                    for center in range(33000, 33020) for seed in (7311, 7312, 7313)
                    for scenario in ("C0", "C1", "C3", "C4") for method, config in d.METHODS]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 1200)
        self.assertEqual(len({d.stem(task) for task in actual}), 1200)
        self.assertEqual({(task["center_id"], task["seed"], task["scenario"]) for task in actual},
                         {(c, s, q) for c in range(33000, 33020) for s in (7311, 7312, 7313) for q in ("C0", "C1", "C3", "C4")})
        self.assertEqual(actual[:5], [{"center_id": 33000, "seed": 7311, "scenario": "C0", "method": m, "config_id": i}
                                     for m, i in d.METHODS])

    def test_five_methods_and_all_24_stages_pair(self):
        result = d.paired_groups(entries())
        self.assertEqual(set(result), {"33000/7311/C0"})
        certificate = result["33000/7311/C0"]
        self.assertTrue(certificate["five_methods"])
        self.assertTrue(certificate["all_24_stage_input_fields_equal"])
        self.assertEqual(set(certificate["receipt_sha256"]), {m for m, _ in d.METHODS})

    def test_every_input_field_mismatch_stops_pairing(self):
        for field in d.INPUT_FIELDS:
            with self.subTest(field=field):
                fixture = entries()
                last = list(fixture.values())[-1]
                last["rows"][16][field] = "DIFFERENT_EXOGENOUS_INITIAL_OR_DEPLOYMENT_FIELD"
                with self.assertRaisesRegex(RuntimeError, "pairing failure"):
                    d.paired_groups(fixture)

    def test_incomplete_group_not_certified_and_duplicate_method_rejected(self):
        fixture = entries()
        fixture.pop(next(iter(fixture)))
        self.assertEqual(d.paired_groups(fixture), {})
        fixture = entries()
        values = list(fixture.values())
        values[-1]["task"]["method"] = values[0]["task"]["method"]
        values[-1]["task"]["config_id"] = values[0]["task"]["config_id"]
        with self.assertRaisesRegex(RuntimeError, "Duplicate/incomplete"):
            d.paired_groups(fixture)

    def test_outcomes_and_later_states_do_not_enter_pairing(self):
        self.assertEqual(d.paired_groups(entries(with_poison=True)), d.paired_groups(entries()))

    def test_full_population_preserves_240_groups_and_20_centers(self):
        result = d.paired_groups(entries(d.tasks()))
        self.assertEqual(len(result), 240)
        self.assertEqual({int(key.split("/")[0]) for key in result}, set(range(33000, 33020)))


class PhaseGateTests(unittest.TestCase):
    def test_minimal_group_is_predeclared_and_not_selected_by_outcome(self):
        manifest = {"manifest_digest": SHA}
        minimal = entries(with_poison=True)
        published = []
        with patch.object(d, "load_manifest", return_value=manifest), \
                patch.object(d.p, "verify_frozen", return_value={"synthetic": True}), \
                patch.object(d, "accepted_records", side_effect=[{}, minimal]), \
                patch.object(d, "dispatch") as dispatch, \
                patch.object(d, "publish", side_effect=lambda path, value: published.append((path, value))):
            dispatch.return_value = {"relative":"execution/minimal/A_MINIMAL_0001"}
            d.run(types.SimpleNamespace(phase="minimal", workers=3))
        dispatch.assert_called_once_with(manifest, "minimal", 3, d.tasks()[:5])
        certificate = next(value for path, value in published if path == "stage_c_minimal_gate.json")
        self.assertTrue(certificate["stage_c_pass"])
        self.assertFalse(certificate["performance_used_for_gate"])
        self.assertTrue(certificate["included_in_predeclared_new_1200"])
        self.assertEqual(certificate["predeclared_group"], "33000/7311/C0")

    def test_minimal_input_failure_never_publishes_pass_gate(self):
        manifest = {"manifest_digest": SHA}
        minimal = entries()
        list(minimal.values())[-1]["rows"][23]["D_srv_hash"] = "mismatch"
        published = []
        with patch.object(d, "load_manifest", return_value=manifest), \
                patch.object(d.p, "verify_frozen", return_value={}), \
                patch.object(d, "accepted_records", side_effect=[{}, minimal]), \
                patch.object(d, "dispatch"), \
                patch.object(d, "publish", side_effect=lambda path, value: published.append((path, value))):
            with self.assertRaises(RuntimeError):
                d.run(types.SimpleNamespace(phase="minimal", workers=3))
        self.assertNotIn("stage_c_minimal_gate.json", [path for path, _ in published])

    def test_full_continues_all_remaining_1195_without_outcome_selection(self):
        manifest = {"manifest_digest": SHA}
        existing = entries(with_poison=True)
        complete = entries(d.tasks(), with_poison=True)
        published = []
        with patch.object(d, "load_manifest", return_value=manifest), \
                patch.object(d.p, "verify_frozen", return_value={}), \
                patch.object(d.p, "checked_path", return_value=Path("synthetic_gate.json")), \
                patch.object(d.p, "read_json", return_value={"stage_c_pass": True, "manifest_digest": SHA}), \
                patch.object(d, "accepted_records", side_effect=[existing, complete]) as accepted, \
                patch.object(d, "dispatch") as dispatch, \
                patch.object(d, "publish", side_effect=lambda path, value: published.append((path, value))):
            dispatch.return_value = {"relative":"execution/full/A_FULL_0001"}
            d.run(types.SimpleNamespace(phase="full", workers=3))
        dispatch.assert_called_once_with(manifest, "full", 3, d.tasks()[5:])
        self.assertEqual(len(dispatch.call_args.args[3]), 1195)
        accepted.assert_has_calls([call(manifest), call(manifest, require_complete=True)])
        certificate = next(value for path, value in published if path == "full_experiment_integrity_gate.json")
        self.assertEqual((certificate["trajectories"], certificate["paired_groups"]), (1200, 240))
        self.assertFalse(certificate["outcomes_used_to_select_protocol"])
        self.assertTrue(certificate["not_unseen_heldout"])
        self.assertTrue(certificate["point_estimates_or_bootstrap_not_yet_computed"])

    def test_full_cannot_bypass_minimal_scientific_gate(self):
        manifest = {"manifest_digest": SHA}
        with patch.object(d, "load_manifest", return_value=manifest), \
                patch.object(d.p, "verify_frozen", return_value={}), \
                patch.object(d.p, "checked_path", return_value=Path("synthetic_gate.json")), \
                patch.object(d.p, "read_json", return_value={"stage_c_pass": False, "manifest_digest": SHA}), \
                patch.object(d, "dispatch") as dispatch:
            with self.assertRaisesRegex(RuntimeError, "Stage C integrity gate"):
                d.run(types.SimpleNamespace(phase="full", workers=3))
        dispatch.assert_not_called()


class AttemptAndResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"],prefix="attempt_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_attempts_are_exclusive_and_preserve_earlier_bytes(self):
        with patch.object(d,"RESULTS",self.root):
            first, rel1 = d._new_phase_attempt("full")
            proof = self.root/rel1/"failure.json"
            proof.write_text("synthetic failure evidence",encoding="utf-8")
            before = proof.read_bytes()
            second, rel2 = d._new_phase_attempt("full")
            self.assertEqual((first,second),("A_FULL_0001","A_FULL_0002"))
            self.assertNotEqual(rel1,rel2)
            self.assertEqual(proof.read_bytes(),before)
            self.assertTrue((self.root/rel2).is_dir())
            (self.root/"execution/full/unknown_evidence.json").write_text("{}",encoding="utf-8")
            with self.assertRaises(RuntimeError): d._new_phase_attempt("full")

    def test_minimal_resume_uses_only_missing_predeclared_tasks(self):
        manifest = {"manifest_digest":SHA}
        existing = entries(d.tasks()[:2])
        completed = entries(with_poison=True)
        with patch.object(d,"load_manifest",return_value=manifest), \
                patch.object(d.p,"verify_frozen",return_value={}), \
                patch.object(d,"accepted_records",side_effect=[existing,completed]), \
                patch.object(d,"dispatch",return_value={"relative":"execution/minimal/A_MINIMAL_0002"}) as dispatch, \
                patch.object(d,"publish") as publish:
            d.run(types.SimpleNamespace(phase="minimal",workers=3))
        dispatch.assert_called_once_with(manifest,"minimal",3,d.tasks()[2:5])
        self.assertIn("execution/minimal/A_MINIMAL_0002/phase_integrity_end.json", [item.args[0] for item in publish.call_args_list])

    def test_failed_retry_requires_exact_input_environment_and_rng(self):
        task = d.tasks()[0]
        manifest = {"manifest_digest":SHA,"input_bundle_digest":"b"*64,"environment":{"fixture":"same"}}
        folder = self.root/f"attempts/{d.stem(task)}/A_MINIMAL_0001/W1"
        folder.mkdir(parents=True)
        rng = {"schema":"paper3-original-task-torch-rng-v1", "bindings":{"task":task,
            "input_bundle_digest":manifest["input_bundle_digest"],"environment_binding":d.p.canonical_hash(manifest["environment"])}}
        rng["state_digest"] = d.p.canonical_hash(rng)
        rng_path = folder/"rng_before.json"
        rng_path.write_text(json.dumps(rng),encoding="utf-8")
        failure = {"task":task,"status":"FAILED","completed_valid":False,
            "manifest_digest":manifest["manifest_digest"],"input_bundle_digest":manifest["input_bundle_digest"],
            "environment_binding":d.p.canonical_hash(manifest["environment"]),
            "rng_relative":rng_path.relative_to(self.root).as_posix(),"rng_file_sha256":d.p.file_sha256(rng_path)}
        failure_path = folder/"failure.json"
        failure_path.write_text(json.dumps(failure),encoding="utf-8")
        with patch.object(d,"RESULTS",self.root):
            actual = d._retry_descriptors(manifest,[task])
            self.assertEqual(actual[d.stem(task)]["failed_receipt_sha256"],d.p.file_sha256(failure_path))
            later = self.root/f"attempts/{d.stem(task)}/A_MINIMAL_0002/W1"
            later.mkdir(parents=True)
            later_failure = {**failure,"rng_relative":None,"rng_file_sha256":None,"failed_before_rng_capture":True}
            (later/"failure.json").write_text(json.dumps(later_failure),encoding="utf-8")
            actual = d._retry_descriptors(manifest,[task])
            self.assertEqual(actual[d.stem(task)]["failed_receipt_sha256"],d.p.file_sha256(failure_path),
                             "later setup failure must preserve previously captured task RNG")
            failure["environment_binding"] = "wrong"
            failure_path.write_text(json.dumps(failure),encoding="utf-8")
            with self.assertRaises(RuntimeError): d._retry_descriptors(manifest,[task])

    def test_rng_without_failure_evidence_cannot_create_fresh_draw(self):
        task = d.tasks()[0]
        folder = self.root/f"attempts/{d.stem(task)}/A_MINIMAL_0001/W1"
        folder.mkdir(parents=True)
        (folder/"rng_before.json").write_text("{}",encoding="utf-8")
        manifest = {"manifest_digest":SHA,"input_bundle_digest":"b"*64,"environment":{"fixture":"same"}}
        with patch.object(d,"RESULTS",self.root),self.assertRaisesRegex(RuntimeError,"lacks explicit failure"):
            d._retry_descriptors(manifest,[task])


if __name__ == "__main__":
    unittest.main()
