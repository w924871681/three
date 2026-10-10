"""In-memory worker integrity tests; no project imports, model or file writes."""
from __future__ import annotations

import copy
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

NAME = "paper3_replication_synthetic_tests"
ROOT = Path(__file__).resolve().parents[1]
if NAME not in sys.modules:
    package = types.ModuleType(NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[NAME] = package
elif tuple(sys.modules[NAME].__path__) != (str(ROOT),):
    raise RuntimeError("synthetic package bound to another source root")
w = importlib.import_module(NAME + ".executor_worker")
s = importlib.import_module(NAME + ".science_adapter")

SHA = "a" * 64
OTHER_SHA = "b" * 64
RESULT_ROOT = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_v1")
TASK = {"center_id": 33000, "seed": 7311, "scenario": "C0", "method": "B0", "config_id": "B0_Frozen_ratio10"}


def manifest():
    return {"paths": {"results_root": str(RESULT_ROOT)}, "manifest_digest": SHA,
            "input_bundle_digest": SHA, "environment": {"synthetic_environment": True},
            "critical_files_sha256": {"scripts/run_p7_7_final.py": SHA, "core/p7.py": SHA,
                                      "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json": SHA},
            "frozen_final_configuration": {"comparators": [{"method": m, "config_id": c} for m, c in s.METHODS]}}


def request(mode="trajectory"):
    value = {"schema": w.REQUEST_SCHEMA, "manifest_digest": SHA, "mode": mode,
             "worker_id": "W1", "attempt_id": "A_MINIMAL_0001", "worker_count": 3}
    if mode == "trajectory":
        value["tasks"] = [copy.deepcopy(TASK)]
    else:
        value["cases"] = [{"center_id": c, "seed": seed} for c in s.CENTERS for seed in s.SEEDS]
    return value


class RequestIntegrityTests(unittest.TestCase):
    def parse(self, value):
        path = RESULT_ROOT / "execution/minimal/W1_request.json"
        with patch.object(w.provenance, "regular_path", side_effect=lambda path: Path(path)), \
                patch.object(w.provenance, "read_json", return_value=copy.deepcopy(value)), \
                patch.object(w.provenance, "file_sha256", return_value=SHA):
            return w._request(manifest(), path, value["mode"], "W1", "A_MINIMAL_0001")

    def test_exact_request_bound_to_immutable_manifest(self):
        value = self.parse(request())
        self.assertEqual(value["request_file_sha256"], SHA)
        self.assertEqual(value["tasks"], [TASK])

    def test_worker_limit_is_integrity_not_performance_gate(self):
        for count in (0, 4, True, "3"):
            value = request()
            value["worker_count"] = count
            with self.assertRaises(w.provenance.ProvenanceError):
                self.parse(value)

    def test_reject_outcome_based_continuation_and_duplicate_task(self):
        value = request()
        value["performance_based_continuation"] = True
        with self.assertRaises(w.provenance.ProvenanceError):
            self.parse(value)
        value = request()
        value["tasks"].append(copy.deepcopy(TASK))
        with self.assertRaises(w.provenance.ProvenanceError):
            self.parse(value)

    def test_wrong_method_config_and_request_identity_rejected(self):
        value = request()
        value["tasks"][0]["config_id"] = "NOT_FROZEN"
        with self.assertRaises(s.ScienceIntegrityError):
            self.parse(value)
        value = request()
        value["manifest_digest"] = OTHER_SHA
        with self.assertRaises(w.provenance.ProvenanceError):
            self.parse(value)

    def test_initial_request_exact_ordered_sixty_cases(self):
        self.assertEqual(len(self.parse(request("initial"))["cases"]), 60)
        value = request("initial")
        value["cases"].reverse()
        with self.assertRaises(w.provenance.ProvenanceError):
            self.parse(value)

    def test_phase_attempt_labels_supported_and_traversal_rejected(self):
        for label in ("A_INITIAL_0001", "A_MINIMAL_0001", "A_FULL_0001"):
            self.assertEqual(w._label(label), label)
        for label in ("../outside", "W1/../W2", "W1\\W2", "", "1W"):
            with self.assertRaises(w.provenance.ProvenanceError):
                w._label(label)


class CompletedAndRetryTests(unittest.TestCase):
    def test_runtime_mismatch_blocks_before_any_trajectory_or_array_load(self):
        m = manifest()
        initial = {"schema": w.INITIAL_SCHEMA, "manifest_digest": SHA, "input_bundle_digest": SHA,
                   "environment_binding": w.provenance.canonical_hash(m["environment"]),
                   "canonical_warmup_reference_created": True, "completed_cases": 60,
                   "scientific_runtime_signature": SHA}
        with patch.object(w.provenance, "checked_path", side_effect=lambda root, rel, **kwargs: Path(root) / rel), \
                patch.object(w.provenance, "read_json", return_value=initial):
            with self.assertRaises(w.provenance.ProvenanceError):
                w._initial_references(m, runtime_signature=OTHER_SHA)

    def fixture(self):
        m = manifest()
        roles = {f"33000/C0/{stage}/{role}": {"legacy_role_hash": SHA}
                 for stage in range(1, 25) for role in ("update", "assessment", "service")}
        store = types.SimpleNamespace(bundle={"roles": roles})
        audit = {"task": TASK, "original_run_one_code_object_preserved": True,
                 "original_globals_mutated": False, "source_bindings_sha256": m["critical_files_sha256"],
                 "initial_state": {"initial_state_hash": SHA, "before_first_decision_verified": True},
                 "timeline_access": {"violation_count": 0, "completed_stages": 24, "phase": "SERVICED"}}
        receipt = {"schema": w.RECEIPT_SCHEMA, "valid": True, "task": TASK,
                   "manifest_digest": SHA, "input_bundle_digest": SHA, "initial_state_hash": SHA,
                   "initial_state_manifest_sha256": SHA, "environment_binding": w.provenance.canonical_hash(m["environment"]),
                   "trajectory_rows": 24, "runner_hash": SHA, "implementation_hash": SHA, "protocol_hash": SHA,
                   "source_bindings_digest": w.provenance.canonical_hash(m["critical_files_sha256"]),
                   "stage_input_hashes": w._expected_stage_hashes(store, TASK), "output_hash": SHA,
                   "audit_relative": "attempts/audit.json", "audit_hash": SHA,
                   "audit_path": "attempts/audit.json", "audit_sha256": SHA,
                   "rng_relative": "attempts/rng.json", "rng_file_sha256": SHA,
                   "rng_before_path": "attempts/rng.json", "rng_before_sha256": SHA,
                   "attempt_csv_relative": "attempts/trajectory.csv", "attempt_csv_hash": SHA}
        return m, store, audit, receipt

    def completed(self, m, store, audit, receipt, digest=SHA):
        def read(path):
            return copy.deepcopy(audit if str(path).endswith("audit.json") else receipt)
        with patch.object(w.provenance, "checked_path", side_effect=lambda root, rel, **kwargs: Path(root) / rel), \
                patch.object(Path, "exists", return_value=True), patch.object(Path, "is_file", return_value=True), \
                patch.object(w.provenance, "read_json", side_effect=read), \
                patch.object(w.provenance, "file_sha256", return_value=digest):
            return w._existing_completed(m, store, TASK, SHA, SHA)

    def test_completed_receipt_requires_all_scientific_byte_bindings(self):
        m, store, audit, receipt = self.fixture()
        self.assertEqual(self.completed(m, store, audit, receipt), receipt)
        with self.assertRaises(w.provenance.ProvenanceError):
            self.completed(m, store, audit, receipt, digest=OTHER_SHA)

    def test_resume_rejects_incomplete_roles_wrong_initial_and_causal_coverage(self):
        m, store, audit, receipt = self.fixture()
        receipt["stage_input_hashes"].pop()
        with self.assertRaises(w.provenance.ProvenanceError):
            self.completed(m, store, audit, receipt)
        m, store, audit, receipt = self.fixture()
        receipt["initial_state_hash"] = OTHER_SHA
        with self.assertRaises(w.provenance.ProvenanceError):
            self.completed(m, store, audit, receipt)
        m, store, audit, receipt = self.fixture()
        audit["timeline_access"]["completed_stages"] = 23
        with self.assertRaises(w.provenance.ProvenanceError):
            self.completed(m, store, audit, receipt)

    def test_resume_cannot_accept_initial_audit_after_first_decision(self):
        m, store, audit, receipt = self.fixture()
        audit["initial_state"]["before_first_decision_verified"] = False
        with self.assertRaises(w.provenance.ProvenanceError):
            self.completed(m, store, audit, receipt)

    def test_retry_requires_failed_same_task_receipt_and_rng_byte_binding(self):
        failed = {"task": TASK, "status": "FAILED", "completed_valid": False,
                  "rng_relative": "attempts/rng.json", "rng_file_sha256": SHA}
        req = {"retries": {w._stem(TASK): {"failed_receipt_relative": "attempts/failure.json", "failed_receipt_sha256": SHA}}}
        with patch.object(w.provenance, "checked_path", side_effect=lambda root, rel, **kwargs: Path(root) / rel), \
                patch.object(w.provenance, "file_sha256", return_value=SHA), \
                patch.object(w.provenance, "read_json", side_effect=lambda p: failed if str(p).endswith("failure.json") else {"synthetic_state": True}):
            result = w._retry(RESULT_ROOT, TASK, req)
            self.assertEqual(result["rng_state"], {"synthetic_state": True})
            failed["completed_valid"] = True
            with self.assertRaises(w.provenance.ProvenanceError):
                w._retry(RESULT_ROOT, TASK, req)


if __name__ == "__main__":
    unittest.main()
