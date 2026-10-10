"""Independent synthetic cutover tests: no native API or scientific execution."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controlled_quiesce as q

ACTUAL_SOURCE = Path(q.__file__).resolve()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(data)
    return q.sha(path)


def task(method="B0", scene="C0"):
    return {"center_id": 33000, "seed": 7311, "scenario": scene,
            "method": method, "config_id": q.METHODS[method]}


def state(raw):
    return {"dtype": "uint8", "shape": [len(raw)], "byte_count": len(raw),
            "base64": base64.b64encode(raw).decode(), "sha256": hashlib.sha256(raw).hexdigest()}


class FakeBackend:
    """A pure Python state machine; PIDs are integers with no native meaning."""
    def __init__(self, owners):
        self.owners = {p["pid"]: {**p, "exit_code": 259, "cpu_100ns": 100} for p in owners}
        self.calls, self.suspended, self.closed = [], set(), set()
        self.fail_suspend, self.fail_terminate, self.fail_resume = None, None, None
        self.extra_pid, self.bad_identity, self.moving_cpu = None, None, None

    def inventory(self):
        result = [pid for pid, item in self.owners.items() if item["exit_code"] == 259]
        if self.extra_pid is not None:
            result.append(self.extra_pid)
        return result

    def open(self, pid):
        self.calls.append(("open", pid)); return pid

    def info(self, handle, pid):
        value = copy.deepcopy(self.owners[handle])
        if self.bad_identity == pid:
            value["creation_filetime"] += 1
        if self.moving_cpu == pid and pid in self.suspended:
            self.owners[handle]["cpu_100ns"] += 1
        return value

    def suspend(self, handle):
        self.calls.append(("suspend", handle))
        if self.fail_suspend == handle:
            raise RuntimeError("synthetic suspend rejection")
        self.suspended.add(handle)

    def resume(self, handle):
        self.calls.append(("resume", handle))
        if self.fail_resume == handle:
            raise RuntimeError("synthetic resume rejection")
        self.suspended.remove(handle)

    def exit_code(self, handle):
        return self.owners[handle]["exit_code"]

    def terminate_and_wait(self, handle, pid):
        self.calls.append(("terminate", handle))
        if self.fail_terminate == handle:
            raise RuntimeError("synthetic native termination failure")
        assert handle in self.suspended
        assert len([c for c in self.calls if c[0] == "suspend"]) == 12
        self.owners[handle]["exit_code"] = 0xE0000002
        self.suspended.remove(handle)
        return {"pid": pid, "observed_dead": True, "exit_code": 0xE0000002, "termination_requested": True,
                "method": "SYNTHETIC_ONLY_NO_NATIVE_API"}

    def close(self, handle):
        self.calls.append(("close", handle)); self.closed.add(handle)


class CutoverTests(unittest.TestCase):
    def setUp(self):
        fixture_root = Path(getattr(sys, "_paper3_dynamic_takeover_test_artifact_root",
                                   ACTUAL_SOURCE.parent / "controlled_quiesce_synthetic_tests/_unittest_fixtures"))
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixture_root)
        self.repo = Path(self.temp.name)
        self.results = self.repo / "results/p7_7_integrity_replication_batch20_env_v3"
        self.here, self.dynamic = self.repo / "new_cutover", self.repo / "old_dynamic"
        self.results.mkdir(parents=True); self.here.mkdir(); self.dynamic.mkdir()
        self.patch = patch.multiple(q, REPO=self.repo, RESULTS=self.results, HERE=self.here, DYNAMIC=self.dynamic)
        self.patch.start()
        self.old_manifest = q.MANIFEST
        self.runtime = {"torch_version": "2.5.1+cu121", "torch_cuda_build_version": "12.1",
                        "cuda_devices": [{"index": 0, "name": "SYNTHETIC_DEVICE"}]}
        self.critical = {"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json": "2" * 64}
        body = {"input_bundle_digest": q.F1, "environment": {"synthetic_only": True},
                "critical_files_sha256": self.critical, "executor_sha256": {"fake.py": "3" * 64}}
        q.MANIFEST = q.canonical(body)
        put(self.results / "provenance_manifest.json", {**body, "manifest_digest": q.MANIFEST})
        states = [{"center_id": c, "seed": s, "initial_state_hash": "4" * 64}
                  for c in range(33000, 33020) for s in (7311, 7312, 7313)]
        initial = {"completed_cases": 60, "manifest_digest": q.MANIFEST, "input_bundle_digest": q.F1,
                   "scientific_runtime_signature": q.canonical(self.runtime), "states": states}
        initial_sha = put(self.results / "initial_state_manifest.json", initial)
        self.bindings = {"manifest_digest": q.MANIFEST, "input_bundle_digest": q.F1,
                         "environment_binding": q.canonical(body["environment"]),
                         "source_bindings_digest": q.canonical(body["critical_files_sha256"]),
                         "executor_bundle_digest": q.canonical(body["executor_sha256"]),
                         "initial_state_manifest_sha256": initial_sha,
                         "scientific_runtime_signature": q.canonical(self.runtime)}
        source = self.here / "readonly_snapshot.py"
        source.write_text("def snapshot_builder(contract):\n    return json.loads(json.dumps(SNAPSHOT))\n", encoding="utf-8")
        self.namespace = {"json": json}
        exec(compile(source.read_text(), str(source), "exec"), self.namespace)
        self.builder = self.namespace["snapshot_builder"]
        dependency = self.dynamic / "fake_dependency.py"; dependency.write_text("# pure synthetic fixture\n")
        sources = {str(source): q.sha(source), str(dependency): q.sha(dependency), str(ACTUAL_SOURCE): q.sha(ACTUAL_SOURCE)}
        self.owners = []
        for index, role in enumerate(q.CONTROL_ROLES, 1):
            self.owners.append({"pid": index, "parent_pid": 100, "creation_filetime": 1000 + index,
                                "image": str(self.repo / "python.exe"), "command_line": str(self.repo / (role + ".py")),
                                "role": role})
        for index, (worker, role) in enumerate(((w, r) for w in ("W1", "W2") for r in q.MODEL_ROLES), 9):
            self.owners.append({"pid": index, "parent_pid": index - 1 if role == "worker_base" else 8,
                                "creation_filetime": 1000 + index, "image": str(self.repo / "python.exe"),
                                "command_line": str(self.repo / (worker + "_" + role + ".py")),
                                "role": role, "worker_id": worker})
        self.requests = {}
        self.pending = []
        for worker, method in (("W1", "B8"), ("W2", "P7.7")):
            assigned = task(method, "C1")
            path = self.results / f"execution/full/{q.OLD_ATTEMPT}/{worker}_request.json"
            payload = {"schema": "paper3-replication-worker-request-v1", "manifest_digest": q.MANIFEST,
                       "mode": "trajectory", "worker_id": worker, "attempt_id": q.OLD_ATTEMPT,
                       "worker_count": 2, "performance_based_continuation": False, "tasks": [assigned]}
            self.requests[worker] = {"path": str(path), "sha256": put(path, payload)}
            relative = f"attempts/{q.task_stem(assigned)}/{q.OLD_ATTEMPT}/{worker}/rng_before.json"
            rng = {"schema": "paper3-original-task-torch-rng-v1", "scope": "EXISTING_EXECUTION_RNG_PROVENANCE",
                   "manual_seed_called": False, "torch_version": self.runtime["torch_version"], "cuda_runtime": "12.1",
                   "bindings": {"task": assigned, "input_bundle_digest": q.F1,
                                "source_bindings_digest": self.bindings["source_bindings_digest"],
                                "environment_binding": self.bindings["environment_binding"],
                                "final_configuration_sha256": "2" * 64, "expected_initial_state_hash": "4" * 64},
                   "cpu": state(b"CPU_TEST_BYTES"), "cuda": [{"device_index": 0, "device_name": "SYNTHETIC_DEVICE",
                                                              "state": state(b"CUDA_TEST_BYTES")} ]}
            rng["state_digest"] = q.canonical(rng)
            self.pending.append({"task": assigned, "worker_id": worker, "attempt_id": q.OLD_ATTEMPT,
                                 "rng_relative": relative, "rng_file_sha256": put(self.results / relative, rng),
                                 "rng_state_digest": rng["state_digest"], "initial_state_hash": "4" * 64})
        saved_records, artifacts = {}, {}
        for method in q.METHODS:
            saved = task(method); name = q.task_stem(saved)
            receipt = {"schema": "paper3-batch20-replication-trajectory-receipt-v1", "valid": True,
                       "task": saved, "trajectory_rows": 24, **self.bindings, "initial_state_hash": "4" * 64,
                       "attempt_id": "A_FULL_0001", "worker_id": "W1"}
            csv = self.results / f"raw/{name}.csv"; csv.parent.mkdir(exist_ok=True); csv.write_bytes(b"synthetic_only\n")
            receipt["output_hash"] = q.sha(csv); artifacts[str(csv)] = q.sha(csv)
            for path_key, hash_key, extension in (("audit_relative", "audit_hash", "audit.json"),
                    ("rng_relative", "rng_file_sha256", "rng_before.json"),
                    ("attempt_csv_relative", "attempt_csv_hash", "trajectory.csv"),
                    ("runtime_receipt_path", "runtime_receipt_sha256", "runtime.json")):
                relative = f"attempts/{name}/A_FULL_0001/W1/{extension}"
                receipt[path_key] = relative; receipt[hash_key] = put(self.results / relative, {"synthetic_only": True})
                artifacts[str(self.results / relative)] = receipt[hash_key]
            raw_receipt = self.results / f"raw/{name}.integrity.json"
            saved_records[name] = put(raw_receipt, receipt); artifacts[str(raw_receipt)] = saved_records[name]
        for item in self.pending:
            artifacts[str(self.results / item["rng_relative"])] = item["rng_file_sha256"]
        for path in (self.results / "provenance_manifest.json", self.results / "initial_state_manifest.json"):
            artifacts[str(path)] = q.sha(path)
        self.snapshot = {"schema": "paper3-dynamic-cutover-snapshot-v1", "bindings": self.bindings,
                         "saved_records": saved_records, "saved_artifacts": artifacts, "completed_count": 5,
                         "paired_count": 1, "pending": copy.deepcopy(self.pending), "unknown_artifacts": [],
                         "validation_scope": "FROZEN_REFERENCE_VALIDATE_COMPLETION_ALL_SAVED_24_STAGES", "captured_utc": "FAKE"}
        self.namespace["SNAPSHOT"] = self.snapshot
        gate = {"schema": "paper3-dynamic-pre-stop-certification-v1", "status": "STATIC_AND_SYNTHETIC_ROUTE_CERTIFIED",
                "manifest_digest": q.MANIFEST, "input_bundle_digest": q.F1, "source_bindings_digest": q.canonical(sources),
                "guard_extension_certified": True, "statistics_provenance_adapter_certified": True,
                "delivery_route_certified": True, "quiesce_synthetic_tests_passed": True,
                "real_model_smoke_before_full_required": True}
        gate_path = self.here / "pre_stop.json"
        self.contract = {"schema": "paper3-controlled-dynamic-cutover-contract-v1", "repository": str(self.repo),
                         "results_root": str(self.results), "old_attempt_id": q.OLD_ATTEMPT,
                         "intentional_inflight_interruption_authorized": True, "performance_used_for_cutover": False,
                         "bindings": self.bindings, "scientific_runtime": self.runtime,
                         "processes": self.owners, "requests": self.requests, "snapshot_source_sha256": sources,
                         "pre_stop_certification": {"path": str(gate_path), "sha256": put(gate_path, gate)}}
        self.backend = FakeBackend(self.owners)
        self.evidence = self.here / "evidence001"

    def tearDown(self):
        q.MANIFEST = self.old_manifest
        self.patch.stop(); self.temp.cleanup()

    def run_cutover(self):
        return q.run_quiescence(self.contract, self.evidence, self.backend, self.builder)

    def rejected_before_stop(self):
        with self.assertRaises(q.CutoverError): self.run_cutover()
        self.assertFalse(any(action == "terminate" for action, _ in self.backend.calls))
        self.assertEqual(self.backend.suspended, set())

    def test_successful_two_pending_intentional_cutover_truthful_receipts(self):
        original = {name: q.sha(name) for name in self.snapshot["saved_artifacts"]}
        result = self.run_cutover()
        self.assertEqual(result["status"], "OLD_OWNERS_INTENTIONALLY_QUIESCED")
        self.assertEqual(len(result["pending_interruption_receipts"]), 2)
        self.assertEqual(len(self.backend.closed), 12); self.assertEqual(self.backend.suspended, set())
        self.assertFalse(result["scientific_integrity_pass"]); self.assertFalse(result["trajectory_boundary_drain_claimed"])
        for pending in self.pending:
            receipt = q.read((self.results / pending["rng_relative"]).parent / "failure.json")
            self.assertEqual(receipt["producer"], "intentional-cutover-observer")
            self.assertFalse(receipt["worker_exception_observed"]); self.assertNotIn("traceback", receipt)
            self.assertEqual(receipt["actual_exit_code"], 0xE0000002)
            self.assertEqual(receipt["rng_state_digest"], pending["rng_state_digest"])
        self.assertEqual(original, {name: q.sha(name) for name in original})

    def test_controls_all_suspend_before_any_model(self):
        self.run_cutover(); ids = [pid for action, pid in self.backend.calls if action == "suspend"]
        self.assertEqual(ids[:8], list(range(1, 9))); self.assertEqual(set(ids[8:]), {9, 10, 11, 12})

    def test_models_terminate_before_any_control(self):
        self.run_cutover(); ids = [pid for action, pid in self.backend.calls if action == "terminate"]
        self.assertEqual(set(ids[:4]), {9, 10, 11, 12}); self.assertEqual(set(ids[4:]), set(range(1, 9)))

    def test_failed_snapshot_resumes_all_twelve(self):
        self.snapshot["unknown_artifacts"] = ["unexpected"]
        self.rejected_before_stop()
        self.assertEqual(len([c for c in self.backend.calls if c[0] == "resume"]), 12)
        self.assertEqual(q.read(self.evidence / "stopped.json")["actual_terminated_count"], 0)

    def test_suspend_failure_resumes_every_previously_suspended(self):
        self.backend.fail_suspend = 6; self.rejected_before_stop()
        self.assertEqual([pid for action, pid in self.backend.calls if action == "resume"], [5, 4, 3, 2, 1])

    def test_partial_termination_resumes_all_surviving_paused_handles(self):
        self.backend.fail_terminate = 9
        with self.assertRaises(q.CutoverError): self.run_cutover()
        self.assertEqual(self.backend.suspended, set())
        stopped = q.read(self.evidence / "stopped.json")
        self.assertEqual(stopped["actual_terminated_count"], 3)
        self.assertEqual(len([c for c in self.backend.calls if c[0] == "resume"]), 9)
        self.assertFalse(any((self.results / p["rng_relative"]).parent.joinpath("failure.json").exists() for p in self.pending))

    def test_resume_failure_is_retained_not_hidden(self):
        self.snapshot["unknown_artifacts"] = ["bad"]; self.backend.fail_resume = 5
        with self.assertRaises(q.CutoverError): self.run_cutover()
        stopped = q.read(self.evidence / "stopped.json")
        self.assertTrue(any(row.get("resume_error") for row in stopped["resume_or_terminal_observations"]))
        self.assertEqual(len([c for c in self.backend.calls if c[0] == "resume"]), 12)

    def test_pid_reuse_rejected_before_suspension(self):
        self.backend.bad_identity = 10; self.rejected_before_stop()
        self.assertFalse(any(action == "suspend" for action, _ in self.backend.calls))

    def test_additional_owner_rejected_before_suspension(self):
        self.backend.extra_pid = 999; self.rejected_before_stop()

    def test_cpu_movement_while_suspended_rejected(self):
        self.backend.moving_cpu = 10; self.rejected_before_stop()

    def test_wrong_target_repo_rejected(self):
        self.contract["repository"] = str(self.repo / "wrong"); self.rejected_before_stop()

    def test_without_intentional_authorization_rejected(self):
        self.contract["intentional_inflight_interruption_authorized"] = False; self.rejected_before_stop()

    def test_performance_based_stop_rejected(self):
        self.contract["performance_used_for_cutover"] = True; self.rejected_before_stop()

    def test_old_attempt_identity_cannot_be_reused(self):
        self.contract["old_attempt_id"] = "A_FULL_0001"; self.rejected_before_stop()

    def test_missing_control_owner_rejected(self):
        self.contract["processes"] = self.owners[1:]; self.rejected_before_stop()

    def test_duplicate_native_pid_rejected(self):
        self.contract["processes"][-1]["pid"] = 1; self.rejected_before_stop()

    def test_wrong_wrapper_ancestry_rejected(self):
        self.contract["processes"][-1]["parent_pid"] = 999; self.rejected_before_stop()

    def test_missing_source_pin_rejected(self):
        self.contract["snapshot_source_sha256"].pop(str(ACTUAL_SOURCE)); self.rejected_before_stop()

    def test_source_sha_changed_rejected(self):
        self.contract["snapshot_source_sha256"][str(ACTUAL_SOURCE)] = "0" * 64; self.rejected_before_stop()

    def test_missing_real_route_certification_rejected(self):
        self.contract["pre_stop_certification"]["sha256"] = "0" * 64; self.rejected_before_stop()

    def test_false_route_certificate_rejected(self):
        path = Path(self.contract["pre_stop_certification"]["path"])
        gate = q.read(path); gate["delivery_route_certified"] = False
        path.write_text(json.dumps(gate)); self.contract["pre_stop_certification"]["sha256"] = q.sha(path)
        self.rejected_before_stop()

    def test_wrong_request_sha_rejected(self):
        self.contract["requests"]["W1"]["sha256"] = "0" * 64; self.rejected_before_stop()

    def test_wrong_snapshot_bindings_rejected(self):
        self.snapshot["bindings"] = {**self.bindings, "input_bundle_digest": "0" * 64}; self.rejected_before_stop()

    def test_weak_validation_scope_rejected(self):
        self.snapshot["validation_scope"] = "COUNTS_ONLY"; self.rejected_before_stop()

    def test_false_record_count_rejected(self):
        self.snapshot["completed_count"] = 6; self.rejected_before_stop()

    def test_false_pair_count_rejected(self):
        self.snapshot["paired_count"] = 2; self.rejected_before_stop()

    def test_unreceipted_raw_csv_rejected_and_preserved(self):
        path = self.results / "raw/unknown.csv"; path.write_bytes(b"preserve")
        self.rejected_before_stop(); self.assertEqual(path.read_bytes(), b"preserve")

    def test_changed_completed_csv_rejected(self):
        next((self.results / "raw").glob("*.csv")).write_bytes(b"changed"); self.rejected_before_stop()

    def test_missing_bound_artifact_rejected(self):
        self.snapshot["saved_artifacts"].pop(str(self.results / self.pending[0]["rng_relative"])); self.rejected_before_stop()

    def test_pending_body_partial_rejected_and_preserved(self):
        path = (self.results / self.pending[0]["rng_relative"]).parent / "trajectory.csv"; path.write_bytes(b"partial")
        self.rejected_before_stop(); self.assertTrue(path.exists())

    def test_unpublished_attempt_receipt_rejected(self):
        path = (self.results / self.pending[0]["rng_relative"]).parent / "receipt.json"; put(path, {"partial": True})
        self.rejected_before_stop()

    def test_unknown_attempt_folder_rejected(self):
        path = self.results / f"attempts/unknown/{q.OLD_ATTEMPT}/W1"; path.mkdir(parents=True)
        self.rejected_before_stop()

    def test_more_than_one_pending_per_worker_rejected(self):
        self.snapshot["pending"][1]["worker_id"] = "W1"; self.rejected_before_stop()

    def test_wrong_pending_task_rejected(self):
        self.snapshot["pending"][0]["task"] = task("B2", "C1"); self.rejected_before_stop()

    def test_wrong_pending_initial_hash_rejected(self):
        self.snapshot["pending"][0]["initial_state_hash"] = "0" * 64; self.rejected_before_stop()

    def test_wrong_rng_file_sha_rejected(self):
        self.snapshot["pending"][0]["rng_file_sha256"] = "0" * 64; self.rejected_before_stop()

    def rng_edit(self, edit):
        item = self.snapshot["pending"][0]; path = self.results / item["rng_relative"]; rng = q.read(path)
        edit(rng); rng.pop("state_digest"); rng["state_digest"] = q.canonical(rng)
        path.write_text(json.dumps(rng)); item["rng_file_sha256"] = q.sha(path); item["rng_state_digest"] = rng["state_digest"]
        self.snapshot["saved_artifacts"][str(path)] = q.sha(path)

    def test_manual_rng_seed_rejected(self):
        self.rng_edit(lambda r: r.update(manual_seed_called=True)); self.rejected_before_stop()

    def test_wrong_rng_cpu_base64_bytehash_rejected(self):
        self.rng_edit(lambda r: r["cpu"].update(sha256="0" * 64)); self.rejected_before_stop()

    def test_wrong_rng_runtime_rejected(self):
        self.rng_edit(lambda r: r.update(torch_version="0.0")); self.rejected_before_stop()

    def test_wrong_rng_cuda_device_rejected(self):
        self.rng_edit(lambda r: r["cuda"][0].update(device_name="OTHER")); self.rejected_before_stop()

    def test_wrong_rng_source_binding_rejected(self):
        self.rng_edit(lambda r: r["bindings"].update(source_bindings_digest="0" * 64)); self.rejected_before_stop()

    def test_callback_exception_resumes_every_process(self):
        self.namespace.pop("SNAPSHOT"); self.rejected_before_stop()

    def test_existing_evidence_directory_never_overwritten(self):
        self.evidence.mkdir(); path = self.evidence / "retain.txt"; path.write_text("retain")
        self.rejected_before_stop(); self.assertEqual(path.read_text(), "retain")

    def test_root_lock_blocks_second_controller_before_native_action(self):
        put(self.here / "CONTROLLED_QUIESCE_EXCLUSIVE_LOCK.json", {"preserve": True})
        self.rejected_before_stop(); self.assertEqual(self.backend.calls, [])

    def test_publication_never_overwrites(self):
        q.publish(self.here, "test.json", {"preserve": True})
        with self.assertRaises(q.CutoverError): q.publish(self.here, "test.json", {})
        self.assertEqual(q.read(self.here / "test.json"), {"preserve": True})

    def test_all_file_evidence_binds_exact_task_and_rng(self):
        result = self.run_cutover()
        for item in result["pending_interruption_receipts"]:
            self.assertEqual(q.sha(item["path"]), item["sha256"])
            failure = q.read(item["path"])
            self.assertEqual(failure["task"], item["task"])
            self.assertEqual(failure["rng_state_digest"], item["rng_state_digest"])


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError("requires -I -S -B")
    if args.attempt < 1:
        raise RuntimeError("positive exclusive attempt required")
    root = ACTUAL_SOURCE.parent / f"controlled_quiesce_synthetic_tests/attempt{args.attempt:03d}"
    root.mkdir(parents=True, exist_ok=False)
    sys._paper3_dynamic_takeover_test_artifact_root = str(root / "fixtures")
    sources = {str(path): q.sha(path) for path in (ACTUAL_SOURCE, Path(__file__).resolve())}
    started = datetime.now(timezone.utc).isoformat()
    with (root / "test.log").open("x", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CutoverTests))
    after = {name: q.sha(name) for name in sources}
    forbidden = [name for name in sys.modules if name in {"torch", "numpy", "pandas"} or name.startswith("core.")]
    proof = {"schema": "paper3-controlled-quiesce-synthetic-test-proof-v1", "all_pass": result.wasSuccessful() and
             not result.skipped and not forbidden and after == sources, "tests_run": result.testsRun,
             "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
             "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
             "implementation_sha256": after, "source_inventory_unchanged": after == sources,
             "forbidden_scientific_modules_imported": forbidden, "real_processes_modified": False,
             "native_api_adapter_instantiated": False, "actual_model_execution": False,
             "actual_generator_execution": False, "statistics_execution": False,
             "test_log_sha256": q.sha(root / "test.log"), "production_quiescence": "NOT_EXECUTED"}
    q.publish(root, "results.json", proof)
    print(json.dumps(proof))
    if not proof["all_pass"]:
        print((root / "test.log").read_text()[-20000:]); raise SystemExit(1)


if __name__ == "__main__":
    main()
