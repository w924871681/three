"""Synthetic metadata-only regressions and an optional real read-only preflight.

No production executor/model/statistics module is imported.  Fixture writes stay
inside unittest TemporaryDirectory; production preflight performs only reads.
"""
import copy
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paper3_history_compat_tests_api", HERE / "history_compat.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
SHA = "1" * 64
TASK = {"center_id": 33002, "seed": 7311, "scenario": "C0", "method": "B8",
        "config_id": "B8_AlwaysOpen_ratio10"}
OTHER = {**TASK, "center_id": 33003}


class HistoryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper3_history_metadata_tests_")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.results = self.repo / "results" / h.RESULT_NAME
        self.directory = self.results / "execution/full/A_FULL_0001"
        self.path = self.directory / "W1_request.json"
        self.base = self.repo / "verification/paper3_canonical_inputs"
        self.executor = self.base / "replication_executor_batch20_env_v3"
        self.launch = self.base / "autonomous_replication_execution_20261009_v3/phase_launches/full_001"
        self.write(self.executor / "executor_driver.py", b"# SYNTHETIC issuer, never executed\n")
        self.write(self.executor / "executor_worker.py", b"# SYNTHETIC worker, never executed\n")
        self.write(self.launch / "invoked_script_source_snapshot.py", (self.executor / "executor_driver.py").read_bytes())
        self.write(self.results / "initial_state_manifest.json", b'{"synthetic":true}\n')
        self.issuer_sha = h.sha(self.executor / "executor_driver.py")
        self.worker_sha = h.sha(self.executor / "executor_worker.py")
        self.manifest = {"manifest_digest": SHA, "input_bundle_digest": "2" * 64,
            "paths": {"repo": str(self.repo), "results_root": str(self.results)},
            "environment": {"python_executable": str(self.repo / "synthetic_venv/python.exe")},
            "executor_sha256": {"executor_driver.py": self.issuer_sha, "executor_worker.py": self.worker_sha}}
        self.write_json(self.results / "provenance_manifest.json", self.manifest)
        self.write_json(self.launch / "start.json", {"phase": "full", "attempt": 1, "workers": 1,
            "performance_based_continuation": False,
            "launch_source_sha256": {str(self.executor / "executor_driver.py"): self.issuer_sha}})
        self.request = {"schema": h.REQUEST_SCHEMA, "manifest_digest": SHA, "mode": "trajectory",
            "worker_id": "W1", "attempt_id": "A_FULL_0001", "worker_count": 1,
            "tasks": [copy.deepcopy(TASK)], "initial_state_manifest": "initial_state_manifest.json", "retries": {}}
        self.expected = {h.canonical(TASK)}
        self.patches = [mock.patch.object(h, "ISSUER_SHA", self.issuer_sha),
                        mock.patch.object(h, "WORKER_SHA", self.worker_sha),
                        mock.patch.object(h, "INITIAL_SHA", h.sha(self.results / "initial_state_manifest.json")),
                        mock.patch.object(h, "LEGACY_REQUEST_SHA", {}),
                        mock.patch.object(h, "LEGACY_PROCESS_SHA", {})]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.save_request()

    @staticmethod
    def write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def write_json(self, path, value):
        self.write(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())

    def save_request(self, pin=True):
        self.write_json(self.path, self.request)
        worker = self.request["worker_id"]
        command = [self.manifest["environment"]["python_executable"], "-I", "-S", "-B", "-X",
            f"pycache_prefix={self.results / ('_never_created_pycache_full_' + self.directory.name + '_' + worker)}",
            str(self.executor / "executor_worker.py"), "--manifest", str(self.results / "provenance_manifest.json"),
            "--mode", "trajectory", "--request-file", str(self.path), "--worker-id", worker,
            "--attempt-id", self.directory.name]
        self.process_path = self.directory / (worker + "_process.json")
        self.write_json(self.process_path, {"pid": 123, "request_sha256": h.sha(self.path), "command": command})
        if pin:
            key = (self.directory.name, self.path.name)
            h.LEGACY_REQUEST_SHA[key] = h.sha(self.path)
            h.LEGACY_PROCESS_SHA[key] = h.sha(self.process_path)

    def check(self):
        return h.validate_request(self.path, self.request, directory=self.directory,
            manifest_digest=SHA, expected_names=self.expected)

    def reject(self, substring=None):
        with self.assertRaises(h.HistoryCompatibilityError) as caught:
            self.check()
        if substring:
            self.assertIn(substring, str(caught.exception))

    def test_exact_legacy_missing_flag_accepted(self):
        result = self.check()
        self.assertTrue(result["missing_optional_flag_accepted_as_original_worker_default"])
        self.assertFalse(result["outcomes_read"])
        self.assertFalse(result["requests_modified"])
        self.assertEqual(h.sha(self.path), result["request_sha256"])

    def test_explicit_false_accepted_without_absent_legacy_exception(self):
        self.request["performance_based_continuation"] = False
        self.save_request()
        h.LEGACY_REQUEST_SHA.clear()
        h.LEGACY_PROCESS_SHA.clear()
        self.assertFalse(self.check()["missing_optional_flag_accepted_as_original_worker_default"])

    def test_true_rejected(self):
        self.request["performance_based_continuation"] = True
        self.save_request()
        self.reject("nonboolean")

    def test_null_rejected(self):
        self.request["performance_based_continuation"] = None
        self.save_request()
        self.reject("nonboolean")

    def test_integer_zero_rejected(self):
        self.request["performance_based_continuation"] = 0
        self.save_request()
        self.reject("nonboolean")

    def test_string_false_rejected(self):
        self.request["performance_based_continuation"] = "false"
        self.save_request()
        self.reject("nonboolean")

    def test_unidentified_missing_flag_rejected(self):
        h.LEGACY_REQUEST_SHA.clear()
        self.reject("identified legacy")

    def test_legacy_request_sha_mismatch_rejected(self):
        h.LEGACY_REQUEST_SHA[(self.directory.name, self.path.name)] = "f" * 64
        self.reject("SHA")

    def test_legacy_process_sha_mismatch_rejected(self):
        h.LEGACY_PROCESS_SHA[(self.directory.name, self.path.name)] = "f" * 64
        self.reject("SHA")

    def test_changed_schema_rejected(self):
        self.request["schema"] = "unknown-schema"
        self.save_request()
        self.reject("binding")

    def test_changed_manifest_rejected(self):
        self.request["manifest_digest"] = "f" * 64
        self.save_request()
        self.reject("binding")

    def test_attempt_mismatch_rejected(self):
        self.request["attempt_id"] = "A_FULL_0002"
        self.save_request()
        self.reject("binding")

    def test_mode_mismatch_rejected(self):
        self.request["mode"] = "initial"
        self.save_request()
        self.reject("binding")

    def test_worker_filename_mismatch_rejected(self):
        self.request["worker_id"] = "W2"
        self.save_request()
        self.reject("allocation")

    def test_boolean_worker_count_rejected(self):
        self.request["worker_count"] = True
        self.save_request()
        self.reject("allocation")

    def test_too_many_workers_rejected(self):
        self.request["worker_count"] = 4
        self.save_request()
        self.reject("allocation")

    def test_wrong_initial_path_rejected(self):
        self.request["initial_state_manifest"] = "another.json"
        self.save_request()
        self.reject("certificate")

    def test_unrecognized_request_field_rejected(self):
        self.request["service_loss"] = 0.001
        self.save_request()
        self.reject("fields")

    def test_outside_expected_task_rejected(self):
        self.request["tasks"] = [OTHER]
        self.save_request()
        self.reject("predeclared")

    def test_method_config_alias_rejected(self):
        self.request["tasks"][0]["config_id"] = "B8_AlwaysOpen"
        self.save_request()
        self.reject("config")

    def test_extra_task_field_rejected(self):
        self.request["tasks"][0]["score"] = 1
        self.save_request()
        self.reject("five fields")

    def test_boolean_center_rejected(self):
        self.request["tasks"][0]["center_id"] = True
        self.save_request()
        self.reject("center/seed")

    def test_duplicate_tasks_rejected(self):
        self.request["tasks"].append(copy.deepcopy(TASK))
        self.save_request()
        self.reject("duplicate")

    def test_empty_tasks_rejected(self):
        self.request["tasks"] = []
        self.save_request()
        self.reject("no preassigned")

    def test_memory_request_different_from_file_rejected(self):
        self.request["worker_count"] = 2
        self.reject("actual preserved")

    def test_issuer_bytes_changed_rejected(self):
        self.write(self.executor / "executor_driver.py", b"# changed synthetic source\n")
        self.reject("SHA")

    def test_worker_bytes_changed_rejected(self):
        self.write(self.executor / "executor_worker.py", b"# changed synthetic source\n")
        self.reject("SHA")

    def test_snapshot_bytes_changed_rejected(self):
        self.write(self.launch / "invoked_script_source_snapshot.py", b"# wrong snapshot\n")
        self.reject("SHA")

    def test_manifest_source_pin_changed_rejected(self):
        self.manifest["executor_sha256"]["executor_driver.py"] = "f" * 64
        self.write_json(self.results / "provenance_manifest.json", self.manifest)
        self.reject("source pins")

    def test_launcher_performance_true_rejected(self):
        p = self.launch / "start.json"
        value = h.read(p)
        value["performance_based_continuation"] = True
        self.write_json(p, value)
        self.reject("launcher")

    def test_initial_manifest_changed_rejected(self):
        self.write(self.results / "initial_state_manifest.json", b"changed initial metadata")
        self.reject("SHA")

    def test_process_request_link_changed_rejected(self):
        value = h.read(self.process_path)
        value["request_sha256"] = "f" * 64
        self.write_json(self.process_path, value)
        h.LEGACY_PROCESS_SHA[(self.directory.name, self.path.name)] = h.sha(self.process_path)
        self.reject("request/process")

    def test_process_command_changed_rejected(self):
        value = h.read(self.process_path)
        value["command"][0] = "wrong interpreter"
        self.write_json(self.process_path, value)
        h.LEGACY_PROCESS_SHA[(self.directory.name, self.path.name)] = h.sha(self.process_path)
        self.reject("invocation")

    def test_retry_outside_tasks_rejected(self):
        self.request["retries"] = {"another_task": {}}
        self.save_request()
        self.reject("retry outside")

    def add_retry(self, captured=True):
        stem = h.task_stem(TASK)
        relative = Path("attempts") / stem / "A_FULL_0000/W1/failure.json"
        failed = {"schema": "paper3-batch20-failed-task-receipt-v1", "manifest_digest": SHA,
                  "task": TASK, "status": "INTERRUPTED", "completed_valid": False,
                  "failed_before_rng_capture": not captured}
        if captured:
            rng = {"bindings": {"task": TASK, "input_bundle_digest": self.manifest["input_bundle_digest"]},
                   "manual_seed_called": False, "synthetic_state": "not a real tensor"}
            rng["state_digest"] = h.canonical(rng)
            rng_relative = relative.with_name("rng_before.json")
            self.write_json(self.results / rng_relative, rng)
            failed.update(rng_relative=rng_relative.as_posix(), rng_file_sha256=h.sha(self.results / rng_relative))
        self.write_json(self.results / relative, failed)
        self.request["retries"] = {stem: {"failed_receipt_relative": relative.as_posix(),
                                          "failed_receipt_sha256": h.sha(self.results / relative)}}
        self.save_request()
        return relative, failed

    def test_exact_captured_rng_retry_accepted(self):
        self.add_retry()
        result = self.check()
        self.assertEqual(result["task_count"], 1)
        self.assertTrue(any(n.endswith("rng_before.json") for n in result["source_and_evidence_sha256"]))

    def test_pre_capture_certified_retry_accepted(self):
        self.add_retry(captured=False)
        self.assertEqual(self.check()["task_count"], 1)

    def test_retry_failure_sha_changed_rejected(self):
        relative, _ = self.add_retry()
        self.write(self.results / relative, b"changed metadata")
        self.reject("SHA")

    def test_retry_completed_record_rejected(self):
        relative, failed = self.add_retry()
        failed["completed_valid"] = True
        self.write_json(self.results / relative, failed)
        self.request["retries"][h.task_stem(TASK)]["failed_receipt_sha256"] = h.sha(self.results / relative)
        self.save_request()
        self.reject("incomplete")

    def test_retry_path_escape_rejected(self):
        self.add_retry()
        self.request["retries"][h.task_stem(TASK)]["failed_receipt_relative"] = "../outside.json"
        self.save_request()
        self.reject("path")

    def test_retry_rng_bytes_changed_rejected(self):
        relative, _ = self.add_retry()
        self.write(self.results / relative.with_name("rng_before.json"), b"changed RNG metadata")
        self.reject("SHA")

    def history_fixture(self):
        record = self.repo / "verification/synthetic_record"
        cert = record / "DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json"
        self.write_json(cert, {"schema": "paper3-dynamic-full-integrity-certificate-v1", "status": "PASS",
            "dynamic_attempt_id": "A_DYNAMIC_0002", "evidence_sha256": {},
            "retained_tasks": 332, "completed_dynamic_tasks": 868, "synthetic_fixture": True})
        self.write_json(self.results / "full_experiment_integrity_gate.json", {"synthetic_fixture": True})
        self.write_json(record / "FULL_GATE_PUBLICATION.json", {"certificate_sha256": h.sha(cert),
            "sha256": h.sha(self.results / "full_experiment_integrity_gate.json")})
        plan_path = record / "synthetic_plan.json"
        self.write_json(plan_path, {"synthetic_fixture": True})
        s = types.SimpleNamespace(read=h.read, require=h.require, sha=h.sha, canonical=h.canonical,
            RESULTS=self.results, BASE=self.base, MANIFEST=SHA,
            bound=lambda path, digest: h.bound(path, digest, self.repo, {}))
        p = types.SimpleNamespace(regular_path=lambda path: h.regular(path, self.repo), file_sha256=h.sha)
        return s, {"_plan_path": str(plan_path)}, {"attempt_id": "A_DYNAMIC_0002"}, p, {}, self.manifest, [TASK], cert

    def test_full_history_preserves_static_interruption_not_success(self):
        args = self.history_fixture()
        result = h.full_history(*args)
        old = result["preserved_static_attempts"][0]
        self.assertEqual(old["status"], "INTERRUPTED_BY_CERTIFIED_DYNAMIC_TAKEOVER")
        self.assertFalse(old["claimed_dynamic_success"])
        self.assertFalse(result["old_static_success_fabricated"])
        self.assertEqual(result["last_attempt_id"], "A_DYNAMIC_0002")

    def test_full_history_preserves_explicit_failure_and_unknown_exit(self):
        args = self.history_fixture()
        failed = {"phase": "full", "manifest_digest": SHA, "attempt_id": self.directory.name,
                  "exit_code": None, "external_observer": True}
        self.write_json(self.directory / "failure.json", failed)
        result = h.full_history(*args)
        self.assertEqual(result["preserved_static_attempts"][0]["status"], "ORIGINAL_STATIC_FAILURE_PRESERVED")
        self.assertIsNone(h.read(self.directory / "failure.json")["exit_code"])

    def test_full_history_rejects_ambiguous_static_terminal(self):
        args = self.history_fixture()
        for name in ("failure.json", "completion.json"):
            self.write_json(self.directory / name, {"phase": "full", "manifest_digest": SHA, "attempt_id": self.directory.name})
        with self.assertRaisesRegex(h.HistoryCompatibilityError, "ambiguous"):
            h.full_history(*args)

    def test_full_history_requires_exact_requested_domain(self):
        args = list(self.history_fixture())
        args[6] = [TASK, OTHER]
        with self.assertRaisesRegex(h.HistoryCompatibilityError, "did not cover"):
            h.full_history(*args)

    def test_full_history_rejects_changed_certificate_binding(self):
        args = self.history_fixture()
        value = h.read(args[-1])
        value["retained_tasks"] = 333
        self.write_json(args[-1], value)
        with self.assertRaisesRegex(h.HistoryCompatibilityError, "SHA"):
            h.full_history(*args)

    def test_validator_does_not_change_any_fixture_bytes(self):
        before = {str(p): h.sha(p) for p in self.repo.rglob("*") if p.is_file()}
        self.check()
        after = {str(p): h.sha(p) for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class RealReadOnlyMetadataPreflight(unittest.TestCase):
    def test_three_actual_legacy_requests_without_models_or_statistics(self):
        repo = HERE.parents[2]
        if not (repo / "results" / h.RESULT_NAME / "provenance_manifest.json").is_file():
            self.skipTest("real repository is unavailable; synthetic tests remain independent")
        result = h.real_request_preflight(repo)
        self.assertEqual(result["status"], "LEGACY_REQUEST_METADATA_PREFLIGHT_PASS")
        self.assertEqual([row["task_count"] for row in result["requests"]], [1195, 539, 538])
        self.assertTrue(all(row["missing_optional_flag_accepted_as_original_worker_default"] for row in result["requests"]))
        self.assertFalse(result["models_or_statistics_executed"])
        self.assertFalse(result["files_modified"])


if __name__ == "__main__":
    unittest.main()
