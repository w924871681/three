"""Synthetic-only adapter/RNG tests, no real project or model execution.

This file is authored for the authorized driver's later test stage. Fixtures
use tiny byte vectors, fake Torch APIs and literal functions entirely in memory.
"""
from __future__ import annotations

import copy
import importlib
import sys
import types
import unittest
from pathlib import Path

NAME = "paper3_replication_synthetic_tests"
ROOT = Path(__file__).resolve().parents[1]
if NAME not in sys.modules:
    package = types.ModuleType(NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[NAME] = package
elif tuple(sys.modules[NAME].__path__) != (str(ROOT),):
    raise RuntimeError("synthetic package bound to another source root")
module = importlib.import_module(NAME + ".science_adapter")


def _runtime_libraries(cuda_available=False):
    cuda = types.SimpleNamespace(is_available=lambda: cuda_available, device_count=lambda: 1,
                                 current_device=lambda: 0, get_device_name=lambda i: "synthetic_gpu",
                                 get_device_capability=lambda i: (8, 0),
                                 get_device_properties=lambda i: types.SimpleNamespace(total_memory=4096, multi_processor_count=2))
    cudnn = types.SimpleNamespace(version=lambda: 90100, enabled=True, deterministic=True,
                                  benchmark=False, allow_tf32=True)
    torch = types.SimpleNamespace(cuda=cuda, __version__="synthetic_torch", version=types.SimpleNamespace(cuda="synthetic_cuda", git_version="synthetic_git"),
                                  backends=types.SimpleNamespace(cudnn=cudnn, cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=False))),
                                  __config__=types.SimpleNamespace(show=lambda: "synthetic_readonly_build"),
                                  get_num_threads=lambda: 2, get_num_interop_threads=lambda: 3,
                                  are_deterministic_algorithms_enabled=lambda: False,
                                  get_default_dtype=lambda: "synthetic_float32")
    numpy = types.SimpleNamespace(__version__="synthetic_numpy", version=types.SimpleNamespace(git_revision="synthetic_np_git"))
    return torch, numpy


class ReadonlyRuntimeTests(unittest.TestCase):
    def test_cpu_runtime_records_defaults_and_missing_driver_honestly(self):
        torch, numpy = _runtime_libraries(False)
        actual = module.capture_scientific_runtime(torch, numpy)
        self.assertEqual(actual["torch_num_threads"], 2)
        self.assertTrue(actual["cudnn_deterministic"])
        self.assertFalse(actual["cudnn_benchmark"])
        self.assertFalse(actual["cuda_available"])
        self.assertEqual(actual["cuda_devices"], [])
        self.assertEqual(actual["cuda_driver"]["status"], "NOT_AVAILABLE")
        self.assertFalse(actual["default_settings_modified_by_verifier"])
        self.assertFalse(actual["manual_seed_called"])
        self.assertEqual(module._hash_json(actual), module._hash_json(module.capture_scientific_runtime(torch, numpy)))

    def test_cuda_metadata_and_optional_native_driver_query_are_bound(self):
        torch, numpy = _runtime_libraries(True)
        calls = []
        torch._C = types.SimpleNamespace(_cuda_getDriverVersion=lambda: calls.append("readonly_driver") or 12040)
        actual = module.capture_scientific_runtime(torch, numpy)
        self.assertEqual(calls, ["readonly_driver"])
        self.assertEqual(actual["cuda_driver"]["version"], 12040)
        self.assertEqual(actual["cuda_current_device"], 0)
        self.assertEqual(actual["cuda_devices"][0]["capability"], [8, 0])
        self.assertIsNone(actual["cuda_devices"][0]["uuid"])
        self.assertEqual(actual["cuda_devices"][0]["total_memory_bytes"], 4096)

    def test_driver_query_failure_is_not_fabricated(self):
        torch, numpy = _runtime_libraries(True)
        def unavailable():
            raise RuntimeError("synthetic_readonly_query_failure")
        torch._C = types.SimpleNamespace(_cuda_getDriverVersion=unavailable)
        actual = module.capture_scientific_runtime(torch, numpy)
        self.assertEqual(actual["cuda_driver"]["status"], "QUERY_FAILED")
        self.assertIsNone(actual["cuda_driver"]["version"])
        self.assertEqual(actual["cuda_driver"]["error_type"], "RuntimeError")

    def test_setting_change_changes_scientific_signature(self):
        torch, numpy = _runtime_libraries(False)
        first = module._hash_json(module.capture_scientific_runtime(torch, numpy))
        torch.backends.cudnn.deterministic = False
        second = module._hash_json(module.capture_scientific_runtime(torch, numpy))
        self.assertNotEqual(first, second)


class FakeTensor:
    def __init__(self, raw):
        self.raw = bytes(raw)
        self.shape = (len(self.raw),)

    def detach(self):
        return self

    def cpu(self):
        return self

    def contiguous(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return self.raw


class FakeTorch:
    __version__ = "synthetic-only"
    version = types.SimpleNamespace(cuda=None)
    uint8 = "synthetic_uint8"
    cuda = types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)

    def __init__(self):
        self.state = FakeTensor(b"\x01\x02\x03\x04")
        self.state_set_calls = 0

    def get_rng_state(self):
        return self.state

    def set_rng_state(self, state):
        self.state = state
        self.state_set_calls += 1

    def tensor(self, value, dtype):
        if dtype != self.uint8:
            raise AssertionError("unexpected synthetic dtype")
        return FakeTensor(value)


class ExactFunctionTests(unittest.TestCase):
    def original(self):
        namespace = {
            "timeline_for_v2": lambda value: "historical_timeline",
            "scenario_hash_v2": lambda value: "historical_digest",
            "initial_model": lambda value: "historical_initial",
            "bank_builder": lambda: "UNCHANGED_BANK",
            "offline_labels": lambda: "UNCHANGED_OFFLINE_ORDER",
        }
        exec(compile("def original(value=1):\n    return (timeline_for_v2(value),scenario_hash_v2(value),initial_model(value),bank_builder(),offline_labels())\n",
                     "<synthetic_frozen_function>", "exec"), namespace)
        return namespace["original"]

    def test_only_three_globals_change_code_and_original_namespace_stay_identical(self):
        original = self.original()
        before = dict(original.__globals__)
        adapted = module.isolated_frozen_call(original, {
            "timeline_for_v2": lambda value: "fixed_timeline",
            "scenario_hash_v2": lambda value: "fixed_digest",
            "initial_model": lambda value: "audited_original_initial",
        })
        self.assertIs(adapted.__code__, original.__code__)
        self.assertEqual(original.__globals__, before)
        self.assertEqual(adapted(), ("fixed_timeline", "fixed_digest", "audited_original_initial", "UNCHANGED_BANK", "UNCHANGED_OFFLINE_ORDER"))
        self.assertEqual(original()[0], "historical_timeline")

    def test_bank_or_offline_override_rejected(self):
        original = self.original()
        for extra in ("bank_builder", "offline_labels", "adapt"):
            callbacks = {name: lambda *args: None for name in module.ALLOWED_GLOBAL_OVERRIDES}
            callbacks[extra] = lambda *args: None
            with self.assertRaises(module.ScienceIntegrityError):
                module.isolated_frozen_call(original, callbacks)

    def test_all_population_tuples_and_wrong_config_rejection(self):
        cfg = {"comparators": [{"method": method, "config_id": config} for method, config in module.METHODS]}
        count = 0
        for center in module.CENTERS:
            for seed in module.SEEDS:
                for scenario in module.SCENARIOS:
                    for method, config in module.METHODS:
                        task = dict(center_id=center, seed=seed, scenario=scenario, method=method, config_id=config)
                        self.assertEqual(module._check_task(task, cfg)["method"], method)
                        count += 1
        self.assertEqual(count, 1200)
        wrong = dict(center_id=33000, seed=7311, scenario="C0", method="P7.7", config_id="other")
        with self.assertRaises(module.ScienceIntegrityError):
            module._check_task(wrong, cfg)


class RngProvenanceTests(unittest.TestCase):
    def test_capture_records_actual_state_without_set_or_seed(self):
        torch = FakeTorch()
        result = module.capture_rng_state(torch, {"task": "synthetic"})
        self.assertEqual(torch.state_set_calls, 0)
        self.assertFalse(result["manual_seed_called"])
        self.assertEqual(result["cpu"]["byte_count"], 4)
        self.assertEqual(result["cuda"], [])

    def test_failed_same_task_exact_restore_and_valid_completion_forbidden(self):
        torch = FakeTorch()
        bindings = {"task": "one", "input": "fixed", "source": "frozen", "environment": "frozen"}
        state = module.capture_rng_state(torch, bindings)
        recorded = {"rng_state": state, "failed_attempt_status": "FAILED", "completed_valid": False,
                    "failed_attempt_receipt_sha256": "f" * 64}
        torch.state = FakeTensor(b"\x04\x03\x02\x01")
        result = module.restore_failed_task_rng(torch, recorded, bindings)
        self.assertEqual(result["state_digest"], state["state_digest"])
        self.assertEqual(torch.state_set_calls, 1)
        for change in ({"completed_valid": True}, {"failed_attempt_status": "COMPLETED"}, {"failed_attempt_receipt_sha256": ""}):
            with self.assertRaises(module.ScienceIntegrityError):
                module.restore_failed_task_rng(torch, dict(recorded, **change), bindings)

    def test_cross_task_or_corrupt_state_fails_before_restore(self):
        torch = FakeTorch()
        bindings = {"task": "one"}
        state = module.capture_rng_state(torch, bindings)
        recorded = {"rng_state": state, "failed_attempt_status": "INTERRUPTED", "completed_valid": False,
                    "failed_attempt_receipt_sha256": "f" * 64}
        with self.assertRaises(module.ScienceIntegrityError):
            module.restore_failed_task_rng(torch, recorded, {"task": "different"})
        bad = copy.deepcopy(recorded)
        bad["rng_state"]["cpu"]["base64"] = "AAAA"
        with self.assertRaises(module.ScienceIntegrityError):
            module.restore_failed_task_rng(torch, bad, bindings)
        self.assertEqual(torch.state_set_calls, 0)


if __name__ == "__main__":
    unittest.main()
