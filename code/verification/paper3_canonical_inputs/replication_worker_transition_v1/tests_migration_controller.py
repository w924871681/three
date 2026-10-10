"""Synthetic-only controller tests, including one owned stdlib Windows child.

Never targets an experiment process, loads a model, or generates research data.
Run with --receipt NEW_PATH to retain exclusive actual test evidence.
"""
from __future__ import annotations
import argparse
import base64
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paper3_worker_transition_controller_tests_subject", HERE / "migration_controller.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeBackend:
    def __init__(self, infos, *, resource_free=9 * m.GIB, fail_suspend=None, fail_terminate=None):
        self.infos = copy.deepcopy(infos)
        self.free = resource_free
        self.fail_suspend = fail_suspend
        self.fail_terminate = fail_terminate
        self.suspended, self.resumed, self.terminated = [], [], []
        self.closed = False

    def open(self, pid):
        return pid

    def info(self, handle, pid):
        return dict(self.infos[pid])

    def resources(self):
        return {"captured_utc": m.utc(), "free_commit_bytes": self.free, "free_physical_bytes": self.free}

    def scientific_workers(self):
        return [{"ProcessId": 36468, "ParentProcessId": 26012}, {"ProcessId": 26012, "ParentProcessId": 30160}]

    def suspend(self, handle):
        if self.fail_suspend == handle:
            raise m.MigrationError("synthetic suspend failure")
        self.suspended.append(handle)

    def resume(self, handle):
        self.resumed.append(handle)

    def terminate_and_wait(self, handle, pid):
        if self.fail_terminate == handle:
            raise m.MigrationError("synthetic terminate failure")
        self.terminated.append(handle)
        return {"pid": pid, "observed_terminated": True, "exit_code": 0xE0000001,
                "already_exited_after_peer_termination": False, "observed_utc": m.utc()}

    def close(self):
        self.closed = True


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper3_transition_synthetic_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.here = self.root / "helpers"
        self.here.mkdir()
        self.results = self.root / "results"
        self.results.mkdir()
        self.execution = self.here / "transition_001"
        self.execution.mkdir()
        self.patches = [patch.object(m, "HERE", self.here), patch.object(m, "RESULTS", self.results)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        request_path = self.results / "execution/full/A_FULL_0001/W1_request.json"
        request_path.parent.mkdir(parents=True)
        request_path.write_text("{}", encoding="utf-8")
        self.argv = [m.EXPECTED_PROCESSES[1]["image"], "-I", "-S", "-B", str(m.EXECUTOR / "executor_worker.py"),
                     "--manifest", str(self.results / "provenance_manifest.json"), "--request-file", str(request_path),
                     "--worker-id", "W1", "--attempt-id", "A_FULL_0001"]
        (request_path.parent / "W1_process.json").write_text(json.dumps({"command": self.argv}), encoding="utf-8")
        self.infos = {}
        for expected in m.EXPECTED_PROCESSES:
            line = '"' + expected["image"] + '" ' + subprocess.list2cmdline(self.argv[1:]) if expected["role"] == "worker_base" else subprocess.list2cmdline(self.argv)
            self.infos[expected["pid"]] = {"pid": expected["pid"], "creation_filetime": expected["creation_filetime"],
                                           "image": expected["image"], "command_line": line, "exit_code": 259,
                                           "private_bytes": 3 * m.GIB, "parent_pid": 26012 if expected["pid"] == 36468 else 30160}
        self.task = {"center_id": 33000, "seed": 7311, "scenario": "C1", "method": "B0", "config_id": "B0_Frozen_ratio10"}
        self.rng_rel = "attempts/B0_Frozen_ratio10_33000_7311_C1/A_FULL_0001/W1/rng_before.json"
        self.rng = self.results / self.rng_rel
        self.rng.parent.mkdir(parents=True)
        self.rng.write_text(json.dumps({"synthetic_only": True}), encoding="utf-8")
        self.csv = self.results / "raw/completed.csv"
        self.csv.parent.mkdir()
        self.csv.write_text("synthetic non-outcome input\n", encoding="utf-8")
        self.receipt = self.results / "raw/completed.integrity.json"
        self.receipt.write_text('{"synthetic":true}', encoding="utf-8")
        self.frozen_source = self.root / "frozen.py"
        self.frozen_source.write_text("# Synthetic source only\n", encoding="utf-8")
        self.frozen = {str(self.frozen_source): m.sha(self.frozen_source)}
        self.snapshot = {"schema": "paper3-worker-transition-snapshot-v1", "captured_utc": m.utc(),
                         "context": {"manifest": {"environment_binding": "a" * 64}, "initial_hashes": {"33000_7311": "b" * 64}},
                         "raw_entries": [{"csv_relative": "raw/completed.csv", "receipt_relative": "raw/completed.integrity.json",
                                          "csv_sha256": m.sha(self.csv), "receipt_file_sha256": m.sha(self.receipt)}],
                         "pending": [{"task": self.task, "artifacts": {"rng_before.json": {"relative_path": self.rng_rel,
                                      "file_sha256": m.sha(self.rng), "payload_base64": base64.b64encode(self.rng.read_bytes()).decode()}}}],
                         "worker": {"snapshot_stable": False},
                         "resources": {"free_commit_bytes": 9 * m.GIB}}

    def invoke(self, backend=None, builder=None, reviewer=None, verifier=None, external_reviewer=None):
        backend = backend or FakeBackend(self.infos)
        result = m.controlled_stop(execution_dir=self.execution, backend=backend,
                                   snapshot_builder=builder or (lambda processes, resources: copy.deepcopy(self.snapshot)),
                                   reviewer=reviewer or (lambda snapshot: {"status": "SNAPSHOT_CONSISTENT", "eligible_to_terminate": True}),
                                   external_reviewer=external_reviewer or (lambda receipt, journal: {"status": "EXTERNAL_INTERRUPTION_EVIDENCE_CONSISTENT"}),
                                   frozen_verifier=verifier or (lambda: self.frozen))
        return result, backend

    def test_success_writes_truthful_bridge_after_two_observed_stops(self):
        original_csv = self.csv.read_bytes()
        result, backend = self.invoke()
        self.assertEqual(backend.terminated, [36468, 26012])
        self.assertEqual(backend.resumed, [])
        self.assertTrue(backend.closed)
        failure = m.read(result["failure_receipt"]["path"])
        self.assertEqual(failure["status"], "INTERRUPTED")
        self.assertFalse(failure["completed_valid"])
        self.assertFalse(failure["worker_python_exception_claimed"])
        self.assertNotIn("traceback", failure)
        self.assertEqual(failure["producer"], "external-migration-controller")
        self.assertEqual(failure["rng_file_sha256"], m.sha(self.rng))
        self.assertEqual(self.csv.read_bytes(), original_csv)
        self.assertTrue((self.execution / "EXTERNAL_INTERRUPTION_RECEIPT.json").is_file())

    def test_low_commit_never_suspends_or_terminates(self):
        backend = FakeBackend(self.infos, resource_free=4 * m.GIB)
        with self.assertRaisesRegex(m.MigrationError, "Insufficient"):
            self.invoke(backend)
        self.assertEqual(backend.suspended, [])
        self.assertEqual(backend.terminated, [])
        self.assertTrue(backend.closed)

    def test_frozen_source_failure_never_suspends(self):
        backend = FakeBackend(self.infos)
        def fail():
            raise m.MigrationError("synthetic frozen-source failure")
        with self.assertRaisesRegex(m.MigrationError, "frozen-source"):
            self.invoke(backend, verifier=fail)
        self.assertEqual(backend.suspended, [])
        self.assertEqual(backend.terminated, [])

    def test_second_suspend_failure_resumes_first(self):
        backend = FakeBackend(self.infos, fail_suspend=26012)
        with self.assertRaises(m.MigrationError):
            self.invoke(backend)
        self.assertEqual(backend.resumed, [36468])
        self.assertEqual(backend.terminated, [])

    def test_snapshot_failure_resumes_both_without_kill(self):
        backend = FakeBackend(self.infos)
        def fail(*args):
            raise m.MigrationError("partial pending snapshot")
        with self.assertRaisesRegex(m.MigrationError, "partial"):
            self.invoke(backend, builder=fail)
        self.assertEqual(backend.resumed, [26012, 36468])
        self.assertEqual(backend.terminated, [])
        self.assertFalse((self.rng.parent / "failure.json").exists())

    def test_unstable_snapshot_resumes_both(self):
        backend = FakeBackend(self.infos)
        count = [0]
        def unstable(*args):
            result = copy.deepcopy(self.snapshot)
            count[0] += 1
            result["different_bytes"] = count[0]
            return result
        with self.assertRaisesRegex(m.MigrationError, "not stable"):
            self.invoke(backend, builder=unstable)
        self.assertEqual(backend.resumed, [26012, 36468])
        self.assertEqual(backend.terminated, [])

    def test_review_rejection_resumes_both(self):
        backend = FakeBackend(self.infos)
        with self.assertRaisesRegex(m.MigrationError, "did not pass"):
            self.invoke(backend, reviewer=lambda _: {"status": "FAIL"})
        self.assertEqual(backend.resumed, [26012, 36468])
        self.assertEqual(backend.terminated, [])

    def test_source_change_after_pause_resumes_without_termination(self):
        backend = FakeBackend(self.infos)
        def mutate(*args):
            self.frozen_source.write_text("# synthetic changed\n", encoding="utf-8")
            return copy.deepcopy(self.snapshot)
        with self.assertRaisesRegex(m.MigrationError, "changed"):
            self.invoke(backend, builder=mutate)
        self.assertEqual(backend.resumed, [26012, 36468])
        self.assertEqual(backend.terminated, [])

    def test_reused_pid_creation_tick_is_rejected(self):
        infos = copy.deepcopy(self.infos)
        infos[36468]["creation_filetime"] += 1
        backend = FakeBackend(infos)
        with self.assertRaisesRegex(m.MigrationError, "creation identity"):
            self.invoke(backend)
        self.assertEqual(backend.suspended, [])
        self.assertEqual(backend.terminated, [])

    def test_extra_native_argument_is_rejected(self):
        infos = copy.deepcopy(self.infos)
        infos[36468]["command_line"] += " --unexpected-option"
        backend = FakeBackend(infos)
        with self.assertRaisesRegex(m.MigrationError, "Full native"):
            self.invoke(backend)
        self.assertEqual(backend.suspended, [])

    def test_changed_scientific_inventory_resumes_without_termination(self):
        backend = FakeBackend(self.infos)
        counter = [0]
        def inventory():
            counter[0] += 1
            result = [{"ProcessId": 36468, "ParentProcessId": 26012}, {"ProcessId": 26012, "ParentProcessId": 30160}]
            if counter[0] > 1:
                result.append({"ProcessId": 999, "ParentProcessId": 0})
            return result
        backend.scientific_workers = inventory
        with self.assertRaisesRegex(m.MigrationError, "inventory changed"):
            self.invoke(backend)
        self.assertEqual(backend.terminated, [])
        self.assertEqual(backend.resumed, [26012, 36468])

    def test_external_poststop_review_rejection_never_publishes_bridge(self):
        backend = FakeBackend(self.infos)
        with self.assertRaisesRegex(m.MigrationError, "review rejected"):
            self.invoke(backend, external_reviewer=lambda receipt, journal: {"status": "FAIL"})
        self.assertEqual(backend.terminated, [36468, 26012])
        self.assertFalse((self.rng.parent / "failure.json").exists())
        self.assertTrue((self.execution / "external_termination_journal.json").exists())

    def test_main_frozen_source_guard_precedes_any_driver_import(self):
        target = self.here / "transition_002"
        argv = ["migration_controller.py", "--execution-dir", str(target), "--implementation-pins", str(self.here / "pins.json"),
                "--authorize-native-transition"]
        with patch.object(sys, "argv", argv), patch.object(m, "read", return_value={}), \
                patch.object(m, "verify_frozen_files", side_effect=m.MigrationError("synthetic source guard")), \
                patch.object(m, "load_driver") as driver, patch.object(m, "NativeBackend") as native:
            with self.assertRaisesRegex(m.MigrationError, "source guard"):
                m.main()
            driver.assert_not_called()
            native.assert_not_called()
        self.assertFalse(target.exists())

    def test_failure_after_base_kill_never_claims_complete_bridge(self):
        backend = FakeBackend(self.infos, fail_terminate=26012)
        with self.assertRaisesRegex(m.MigrationError, "terminate"):
            self.invoke(backend)
        self.assertEqual(backend.terminated, [36468])
        self.assertEqual(backend.resumed, [26012])
        self.assertFalse((self.rng.parent / "failure.json").exists())
        record = m.read(self.execution / "controller_failure.json")
        self.assertEqual(record["terminated_count"], 1)

    def test_partial_pending_publication_after_stop_blocks_bridge(self):
        backend = FakeBackend(self.infos)
        original_stop = backend.terminate_and_wait
        def partial(handle, pid):
            value = original_stop(handle, pid)
            if pid == 26012:
                (self.rng.parent / "trajectory.csv").write_text("synthetic partial", encoding="utf-8")
            return value
        backend.terminate_and_wait = partial
        with self.assertRaisesRegex(m.MigrationError, "partial publication"):
            self.invoke(backend)
        self.assertFalse((self.rng.parent / "failure.json").exists())

    def test_no_existing_publication_is_overwritten(self):
        file = self.root / "retained.json"
        file.write_bytes(b"retained")
        with self.assertRaises(FileExistsError):
            m.publish(self.root, "retained.json", {"changed": True})
        self.assertEqual(file.read_bytes(), b"retained")

    def test_atomic_bridge_does_not_replace_existing_failure(self):
        failure = self.rng.parent / "failure.json"
        failure.write_bytes(b"retained original failure")
        with self.assertRaises(m.MigrationError):
            m.publish_bridge_atomically(self.execution, self.rng.parent, {"synthetic": True})
        self.assertEqual(failure.read_bytes(), b"retained original failure")

    def test_escape_path_rejected(self):
        with self.assertRaises(m.MigrationError):
            m.checked(self.execution, "../original.csv", exists=False)

    def test_commit_thresholds_are_independent_and_conservative(self):
        self.assertEqual(m.resource_check({"free_commit_bytes": 8 * m.GIB}, 3 * m.GIB), int(4.5 * m.GIB))
        self.assertEqual(m.resource_check({"free_commit_bytes": 8 * m.GIB}, 3 * m.GIB, after_stop=True), 7 * m.GIB)
        with self.assertRaises(m.MigrationError):
            m.resource_check({"free_commit_bytes": 7 * m.GIB}, 4 * m.GIB, after_stop=True)

    def test_publication_directory_must_be_exclusive_new(self):
        (self.execution / "preexisting.txt").write_text("keep", encoding="utf-8")
        backend = FakeBackend(self.infos)
        with self.assertRaisesRegex(m.MigrationError, "not empty"):
            self.invoke(backend)
        self.assertEqual(backend.suspended, [])


class NativeOwnedChildTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows native lifecycle test")
    def test_native_owned_stdlib_child_lifecycle(self):
        """Only this freshly spawned child is ever paused/resumed/terminated."""
        backend = m.NativeBackend()
        child, handle = None, None
        with tempfile.TemporaryDirectory(prefix="paper3_owned_native_child_") as folder:
            tick = Path(folder) / "ticks.txt"
            # Open+append+close each tick: no buffered output or model dependency.
            code = "import pathlib,time,sys\np=pathlib.Path(sys.argv[1])\nwhile True:\n with p.open('ab') as f: f.write(b'x')\n time.sleep(0.02)\n"
            # Spawn the actual base executable directly, avoiding a venv Windows
            # redirector child whose suspended wrapper would not pause Python.
            child_python = str(Path(sys.base_prefix) / "python.exe")
            self.assertTrue(Path(child_python).is_file())
            command = [child_python, "-I", "-S", "-B", "-c", code, str(tick)]
            try:
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                handle = backend.open(child.pid)
                initial = backend.info(handle, child.pid)
                self.assertEqual(initial["pid"], child.pid)
                self.assertGreater(initial["creation_filetime"], 0)
                self.assertEqual(initial["exit_code"], 259)
                self.assertIn(str(tick), initial["command_line"])
                deadline = time.monotonic() + 5
                while not tick.exists() or tick.stat().st_size < 2:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                backend.suspend(handle)
                before = tick.stat().st_size
                time.sleep(0.15)
                self.assertEqual(tick.stat().st_size, before)
                after_suspend = backend.info(handle, child.pid)
                self.assertEqual(after_suspend["creation_filetime"], initial["creation_filetime"])
                backend.resume(handle)
                deadline = time.monotonic() + 2
                while tick.stat().st_size <= before:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                result = backend.terminate_and_wait(handle, child.pid)
                self.assertTrue(result["observed_terminated"])
                self.assertNotEqual(result["exit_code"], 259)
                self.assertIsNotNone(child.wait(timeout=2))
            finally:
                if child is not None and child.poll() is None:
                    # Exact owned Popen handle; never an experiment PID.
                    if handle is not None:
                        backend.terminate_and_wait(handle, child.pid)
                    else:
                        child.terminate()
                    child.wait(timeout=2)
                backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    source_pins = {str(HERE / name): m.sha(HERE / name) for name in ("migration_controller.py", "tests_migration_controller.py")}
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    text = output.getvalue()
    print(text, flush=True)
    m.recheck_hashes(source_pins)
    status = result.wasSuccessful() and not result.skipped
    receipt = {"schema": "paper3-worker-transition-controller-synthetic-tests-v1", "status": "PASS" if status else "FAIL",
               "all_pass": status, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "created_utc": m.utc(), "implementation_sha256": source_pins,
               "native_owned_child_lifecycle_passed": status and os.name == "nt", "real_experiment_processes_controlled": False,
               "model_generator_training_statistics_executed": False, "test_output": text}
    if args.receipt:
        require_parent = m.regular(args.receipt.parent)
        m.publish(require_parent, args.receipt.name, receipt)
    return 0 if status else 1


if __name__ == "__main__":
    raise SystemExit(main())
