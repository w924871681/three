"""Synthetic-only lifecycle, admission and task-boundary regression tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dynamic_bridge_under_test", HERE / "frozen_bridge.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def task(center=33000, method="B0"):
    config = "B0_Frozen_ratio10" if method == "B0" else "B1_AlwaysMaintainP50_ratio10"
    return {"center_id": center, "seed": 7311, "scenario": "C0", "method": method, "config_id": config}


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "tests", prefix="stream_synthetic_")
        self.root = Path(self.temp.name); self.contract = {"eligible_tasks": [task(), task(method="B1")]}
        self.contract_sha = "a" * 64; self.done = []
        def complete(value):
            self.done.append(value)
            return {"receipt_relative": "raw/synthetic.integrity.json", "receipt_sha256": "b" * 64,
                    "output_sha256": "c" * 64, "synthetic_only": True}
        self.stream = b.TaskStream(self.root, "DW0001", self.contract, self.contract_sha, complete)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, seq, value=None, **edits):
        value = copy.deepcopy(value or {"action": "TASK", "task": task(), "claim_id": "claim0001",
                                       "task_digest": b.canonical(task()), "contract_sha256": self.contract_sha})
        value.update(edits); put(self.root / f"commands/{seq:06d}.json", value)

    def stop(self, seq):
        self.command(seq, {"action": "STOP", "contract_sha256": self.contract_sha})

    def test_ack_is_after_original_body_and_before_next_assignment(self):
        self.command(1); self.stop(2)
        self.assertEqual(next(self.stream), task())
        self.assertEqual(self.done, [])
        self.assertFalse((self.root / "events/000001.done.json").exists())
        with self.assertRaises(StopIteration): next(self.stream)
        self.assertEqual(self.done, [task()])
        value = b.load(self.root / "events/000001.done.json")
        self.assertEqual(value["claim_id"], "claim0001")
        self.assertEqual(value["task_digest"], b.canonical(task()))

    def test_len_never_consumes_or_acknowledges(self):
        self.command(1)
        self.assertEqual(len(self.stream), 0); self.assertEqual(len(self.stream), 0)
        next(self.stream)
        self.assertEqual(len(self.stream), 1); self.assertEqual(self.done, [])

    def test_stop_idle_does_not_claim_or_complete(self):
        self.stop(1)
        self.assertEqual(list(self.stream), [])
        self.assertEqual(self.done, []); self.assertEqual(len(self.stream), 0)

    def test_stopped_stream_never_reads_later_command(self):
        self.stop(1)
        with self.assertRaises(StopIteration): next(self.stream)
        self.command(2)
        with self.assertRaises(StopIteration): next(self.stream)
        self.assertEqual(len(self.stream), 0)

    def test_completed_validator_failure_cannot_acknowledge(self):
        self.command(1); self.stop(2); next(self.stream)
        def reject(_): raise b.BridgeError("partial publication")
        self.stream.complete = reject
        with self.assertRaisesRegex(b.BridgeError, "partial publication"): next(self.stream)
        self.assertIsNotNone(self.stream.pending)
        self.assertFalse((self.root / "events/000001.done.json").exists())

    def test_task_outside_eligible_domain_rejected(self):
        other = task(33019)
        self.command(1, task=other, task_digest=b.canonical(other))
        with self.assertRaisesRegex(b.BridgeError, "eligible domain"): next(self.stream)

    def test_wrong_task_digest_rejected(self):
        self.command(1, task_digest="wrong")
        with self.assertRaises(b.BridgeError): next(self.stream)

    def test_wrong_contract_rejected(self):
        self.command(1, contract_sha256="wrong")
        with self.assertRaisesRegex(b.BridgeError, "contract binding"): next(self.stream)

    def test_unsafe_claim_rejected(self):
        self.command(1, claim_id="../outside")
        with self.assertRaisesRegex(b.BridgeError, "claim ID"): next(self.stream)

    def test_duplicate_task_rejected_after_first_ack(self):
        self.command(1); self.command(2, claim_id="claim0002")
        next(self.stream)
        with self.assertRaisesRegex(b.BridgeError, "duplicate task"): next(self.stream)
        self.assertEqual(self.done, [task()])

    def test_duplicate_claim_for_another_task_rejected(self):
        self.command(1)
        other = task(method="B1")
        self.command(2, task=other, task_digest=b.canonical(other))
        next(self.stream)
        with self.assertRaisesRegex(b.BridgeError, "duplicate task or claim"): next(self.stream)

    def test_foreign_worker_rejected(self):
        self.command(1, worker_id="DW0002")
        with self.assertRaisesRegex(b.BridgeError, "another worker"): next(self.stream)

    def test_wrong_sequence_rejected(self):
        self.command(1, sequence=2)
        with self.assertRaisesRegex(b.BridgeError, "sequence"): next(self.stream)

    def test_unknown_command_rejected(self):
        self.command(1, action="RESEED")
        with self.assertRaisesRegex(b.BridgeError, "unknown worker command"): next(self.stream)

    def test_stop_with_claim_rejected(self):
        self.command(1, action="STOP")
        with self.assertRaisesRegex(b.BridgeError, "STOP cannot hold"): next(self.stream)

    def test_task_is_copied_before_original_caller_mutates_it(self):
        self.command(1); self.stop(2)
        assigned = next(self.stream); assigned["center_id"] = 1
        with self.assertRaises(StopIteration): next(self.stream)
        self.assertEqual(self.done, [task()])

    def test_smoke_stops_after_exactly_one_task(self):
        self.stream.contract["execution_mode"] = "BRIDGE_SMOKE"
        self.command(1)
        other = task(method="B1")
        self.command(2, task=other, task_digest=b.canonical(other), claim_id="claim0002")
        next(self.stream)
        with self.assertRaises(StopIteration): next(self.stream)
        self.assertEqual(len(self.stream), 1); self.assertEqual(len(self.done), 1)

    def test_partial_json_waits_only_until_complete(self):
        path = self.root / "commands/000001.json"; path.parent.mkdir()
        path.write_bytes(b"{")
        def finish(_): self.stop(1)
        self.stream.pause = finish
        with self.assertRaises(StopIteration): next(self.stream)

    def test_malformed_json_eventually_fails_closed(self):
        path = self.root / "commands/000001.json"; path.parent.mkdir(); path.write_bytes(b"{")
        clock = [0]
        self.stream.monotonic = lambda: clock[0]
        self.stream.pause = lambda _: clock.__setitem__(0, clock[0] + 1)
        with self.assertRaisesRegex(b.BridgeError, "malformed"): next(self.stream)

    def test_duplicate_json_keys_rejected(self):
        path = self.root / "commands/000001.json"; path.parent.mkdir()
        path.write_bytes(b'{"action":"STOP","action":"TASK"}')
        with self.assertRaisesRegex(b.BridgeError, "duplicate JSON"): next(self.stream)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "tests", prefix="admission_synthetic_")
        self.repo = Path(self.temp.name); self.results = self.repo / "results/new_v3"
        self.sidecar = self.repo / "new_scheduler"; self.executor = self.repo / "frozen_executor"
        self.results.mkdir(parents=True); self.sidecar.mkdir(); self.executor.mkdir()
        self.initial = self.results / "initial_state_manifest.json"; put(self.initial, {"synthetic_only": True})
        for name in ("frozen_bridge.py", "guard_extension.py"):
            (self.sidecar / name).write_text("# synthetic source only\n", encoding="utf-8")
        self.sources = {str(p): b.sha(p) for p in self.sidecar.glob("*.py")}
        self.manifest = {"input_bundle_digest": b.F1_DIGEST,
                         "paths": {"results_root": str(self.results), "executor_root": str(self.executor)}}
        self.digest = b.canonical(self.manifest); self.manifest["manifest_digest"] = self.digest
        put(self.results / "provenance_manifest.json", self.manifest)
        self.proof_path = self.sidecar / "proof.json"
        self.proof = {"schema": "paper3-dynamic-synthetic-test-proof-v1", "all_pass": True,
                      "actual_model_execution": False, "model_runtime_verification": "NOT_EXECUTED",
                      "tests_run": 30, "failures": 0, "errors": 0, "skipped": 0,
                      "implementation_sha256": self.sources}
        put(self.proof_path, self.proof)
        self.gate_path = self.sidecar / "gate.json"
        self.gate = {"schema": "paper3-dynamic-takeover-gate-v1", "status": "PASS",
                     "source_extension_scope": b.EXTENSION_SCOPE, "sidecar_digest": b.canonical(self.sources),
                     "manifest_digest": self.digest, "input_bundle_digest": b.F1_DIGEST,
                     "initial_manifest_sha256": b.sha(self.initial), "old_owners_quiescent": True,
                     "delivery_route_certified": True, "real_model_bridge_smoke_passed": True}
        put(self.gate_path, self.gate)
        self.path = self.sidecar / "contract.json"
        self.contract = {"manifest_path": str(self.results / "provenance_manifest.json"),
                         "eligible_tasks": [task(), task(method="B1")], "retries": {},
                         "initial_state_manifest": "initial_state_manifest.json", "attempt_id": "A_DYNAMIC_0001",
                         "sidecar_sources": self.sources, "sidecar_digest": b.canonical(self.sources),
                         "source_extension_scope": b.EXTENSION_SCOPE, "original_executor_root": str(self.executor),
                         "sourceproof_path": str(self.proof_path), "sourceproof_sha256": b.sha(self.proof_path),
                         "activation_gate_path": str(self.gate_path), "activation_gate_sha256": b.sha(self.gate_path)}
        self.patch = patch.multiple(b, REPO_ROOT=self.repo, RESULTS_ROOT=self.results,
                                   SCHEDULER_ROOT=self.sidecar, EXECUTOR_ROOT=self.executor, MANIFEST_DIGEST=self.digest)
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def validate(self):
        put(self.path, self.contract)
        return b.validate_contract(self.path)

    def gate_edit(self, **edits):
        self.gate.update(edits); put(self.gate_path, self.gate)
        self.contract["activation_gate_sha256"] = b.sha(self.gate_path)

    def proof_edit(self, **edits):
        self.proof.update(edits); put(self.proof_path, self.proof)
        self.contract["sourceproof_sha256"] = b.sha(self.proof_path)

    def test_full_contract_read_only_admission(self):
        value, manifest, digest = self.validate()
        self.assertEqual(value, self.contract); self.assertEqual(manifest, self.manifest)
        self.assertEqual(digest, b.sha(self.path))

    def test_old_owners_must_be_quiescent(self):
        self.gate_edit(old_owners_quiescent=False)
        with self.assertRaisesRegex(b.BridgeError, "old ownership"): self.validate()

    def test_delivery_route_must_be_certified(self):
        self.gate_edit(delivery_route_certified=False)
        with self.assertRaises(b.BridgeError): self.validate()

    def test_full_without_real_model_smoke_rejected(self):
        self.gate_edit(real_model_bridge_smoke_passed=False)
        with self.assertRaisesRegex(b.BridgeError, "real model bridge smoke"): self.validate()

    def test_canonical_input_digest_cannot_change(self):
        self.gate_edit(input_bundle_digest="wrong")
        with self.assertRaises(b.BridgeError): self.validate()

    def test_initial_state_certificate_SHA_cannot_change(self):
        self.gate_edit(initial_manifest_sha256="wrong")
        with self.assertRaises(b.BridgeError): self.validate()

    def test_failed_synthetic_proof_rejected(self):
        self.proof_edit(all_pass=False)
        with self.assertRaises(b.BridgeError): self.validate()

    def test_synthetic_proof_must_not_claim_real_model_execution(self):
        self.proof_edit(actual_model_execution=True)
        with self.assertRaises(b.BridgeError): self.validate()

    def test_skipped_test_not_PASS(self):
        self.proof_edit(skipped=1)
        with self.assertRaises(b.BridgeError): self.validate()

    def test_changed_sidecar_bytes_rejected(self):
        (self.sidecar / "frozen_bridge.py").write_text("# changed", encoding="utf-8")
        with self.assertRaises(b.BridgeError): self.validate()

    def test_proof_source_closure_must_equal_sidecar(self):
        self.proof_edit(implementation_sha256={})
        with self.assertRaises(b.BridgeError): self.validate()

    def test_proof_actual_SHA_required(self):
        self.contract["sourceproof_sha256"] = "wrong"
        with self.assertRaises(b.BridgeError): self.validate()

    def test_takeover_gate_actual_SHA_required(self):
        self.contract["activation_gate_sha256"] = "wrong"
        with self.assertRaises(b.BridgeError): self.validate()

    def test_duplicate_eligible_tasks_rejected(self):
        self.contract["eligible_tasks"] = [task(), task()]
        with self.assertRaises(b.BridgeError): self.validate()

    def test_wrong_sidecar_digest_rejected(self):
        self.contract["sidecar_digest"] = "wrong"
        with self.assertRaises(b.BridgeError): self.validate()

    def test_unknown_execution_mode_rejected(self):
        self.contract["execution_mode"] = "TRAIN"
        with self.assertRaises(b.BridgeError): self.validate()

    def test_one_task_smoke_admitted_without_claiming_runtime_success(self):
        self.contract.update(execution_mode="BRIDGE_SMOKE", eligible_tasks=[task()])
        self.gate_edit(real_model_bridge_smoke_passed=False, scope="ONE_PREDECLARED_PENDING_TASK",
                       smoke_task_digest=b.canonical(task()))
        self.validate()

    def test_smoke_cannot_expand_to_two_tasks(self):
        self.contract["execution_mode"] = "BRIDGE_SMOKE"
        self.gate_edit(scope="ONE_PREDECLARED_PENDING_TASK", smoke_task_digest=b.canonical(task()))
        with self.assertRaises(b.BridgeError): self.validate()

    def test_smoke_task_identity_must_be_predeclared(self):
        self.contract.update(execution_mode="BRIDGE_SMOKE", eligible_tasks=[task()])
        self.gate_edit(scope="ONE_PREDECLARED_PENDING_TASK", smoke_task_digest="wrong")
        with self.assertRaises(b.BridgeError): self.validate()

    def test_bootstrap_eligible_domain_does_not_claim_assignment(self):
        root = self.results / "workers/DW0001"; root.mkdir(parents=True)
        value = {"schema": "paper3-replication-worker-request-v1", "manifest_digest": self.digest,
                 "mode": "trajectory", "worker_id": "DW0001", "attempt_id": self.contract["attempt_id"],
                 "worker_count": 2, "tasks": self.contract["eligible_tasks"],
                 "initial_state_manifest": "initial_state_manifest.json", "retries": {}}
        put(root / "bootstrap_request.json", value)
        path, digest = b.bootstrap_request_check(self.contract, self.manifest, "DW0001", root)
        self.assertEqual(digest, b.sha(path)); self.assertEqual(value["tasks"], self.contract["eligible_tasks"])

    def test_bootstrap_task_mismatch_rejected(self):
        root = self.results / "workers/DW0001"; root.mkdir(parents=True)
        put(root / "bootstrap_request.json", {"tasks": [task()]})
        with self.assertRaises(b.BridgeError): b.bootstrap_request_check(self.contract, self.manifest, "DW0001", root)


class PublicationTests(unittest.TestCase):
    def test_exclusive_output_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=HERE / "tests") as folder:
            root = Path(folder); b.publish(root, "ready.json", {"a": 1})
            before = (root / "ready.json").read_bytes()
            with self.assertRaises(FileExistsError): b.publish(root, "ready.json", {"a": 2})
            self.assertEqual((root / "ready.json").read_bytes(), before)

    def test_relative_escape_rejected(self):
        with self.assertRaises(b.BridgeError): b.safe_child(HERE, "../outside")

    def test_worker_id_cannot_name_an_original_file(self):
        with self.assertRaises(b.BridgeError): b.worker_root_check("../raw", b.RESULTS_ROOT / "raw")

    def test_worker_root_cannot_be_original_results(self):
        with self.assertRaises(b.BridgeError): b.worker_root_check("DW0001", b.REPO_ROOT / "results/p7_7/DW0001")

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(b.BridgeError): b.parse(b'{"x":NaN}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
