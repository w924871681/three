"""Independent synthetic/mocked tests, not executed during implementation.

These tests never invoke project input generators, checkpoints, models or
methods. The materialization orchestration tests replace its runtime with tiny
deterministic synthetic providers and an in-memory writer. Full expected array
lengths are retained so slicing/coverage contracts are meaningfully checked.
"""
from __future__ import annotations

import ast
import dataclasses
import importlib
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import unittest
from unittest import mock

_PACKAGE_NAME = "paper3_civ_tests"
_MODULE_ROOT = str(Path(__file__).resolve().parents[1])
if _PACKAGE_NAME not in sys.modules:
    _package = types.ModuleType(_PACKAGE_NAME)
    _package.__path__ = [_MODULE_ROOT]
    sys.modules[_PACKAGE_NAME] = _package
elif getattr(sys.modules[_PACKAGE_NAME], "__path__", None) != [_MODULE_ROOT]:
    raise RuntimeError("synthetic test package points to an unreviewed directory")
contract = importlib.import_module(f"{_PACKAGE_NAME}.contract")
module = importlib.import_module(f"{_PACKAGE_NAME}.materialization")


class TestAstExtractionSurface(unittest.TestCase):
    def test_rejects_model_io_global_rng_and_imports(self):
        examples = (
            "def f():\n    return open('original.csv', 'w')\n",
            "def f():\n    return torch.load('source.pt')\n",
            "def f():\n    return np.random.seed(7311)\n",
            "def f():\n    import core.models\n",
            "def f():\n    return np.save('original.npy', [])\n",
            "def f():\n    return eval('1')\n",
            "def f():\n    return globals()\n",
        )
        for text in examples:
            with self.subTest(text=text), self.assertRaises(contract.ContractError):
                module._audit_node(ast.parse(text), {"f"})

    def test_allows_reviewed_numpy_result_array_cast(self):
        # The ndarray method after a NumPy call is distinct from an np module
        # API such as np.save; an overly broad prefix test would reject it.
        node = ast.parse("def f():\n    return np.concatenate([], axis=1).astype('float32')\n")
        module._audit_node(node, {"f"})
        import numpy as np

        namespace = module._namespace("paper3_synthetic_reduction_probe", np)
        exec(compile("value=float(np.ones((4,2),dtype=np.float32).mean())",
                     "<synthetic_numpy_mean_regression>", "exec"), namespace)
        self.assertEqual(namespace["value"], 1.0)
        for name in ("core.models", "torch", "numpy.random", "os"):
            with self.subTest(import_name=name), self.assertRaises(contract.ContractError):
                module._numpy_method_import(name)
        with self.assertRaises(contract.ContractError):
            module._numpy_method_import("numpy._core._methods", level=1)
        with self.assertRaises(contract.ContractError):
            module._audit_node(ast.parse("def f():\n    return __import__('numpy._core._methods')\n"), {"f"})

    def test_root_pin_disagreement_fails_before_source_or_numpy_loading(self):
        with self.assertRaisesRegex(contract.ContractError, "root source pins disagree"):
            module.load_pure_runtime(Path("."), {})

    def test_fingerprint_context_distinct_without_any_rng(self):
        payload = {"legacy_array_digest": "a" * 64}
        f = module._fingerprint("base", "F", "b" * 64, "c" * 64, payload)
        s = module._fingerprint("base", "S", "b" * 64, "c" * 64, payload)
        self.assertNotEqual(f, s)


class MemoryWriter:
    def __init__(self):
        self.paths = set()
        self.json_values = {}
        self.array_writes = 0

    def _reserve(self, path):
        if path in self.paths:
            raise AssertionError("verifier attempted to overwrite an output")
        self.paths.add(path)

    def write_array(self, path, array):
        self._reserve(path)
        self.array_writes += 1

    def write_json(self, path, value):
        self._reserve(path)
        self.json_values[path] = value

    def write_jsonl(self, path, rows):
        self._reserve(path)


def synthetic_runtime():
    import numpy as np

    @dataclasses.dataclass
    class TypeCfg:
        drift_prob: float = 0.5
        dt_choices: list = dataclasses.field(default_factory=lambda: [1])

    @dataclasses.dataclass
    class SimCfg:
        seed: int = 1
        n_history: int = 1
        type_ratio: tuple = (3, 4, 3)
        k_max: int = 12
        type_A: TypeCfg = dataclasses.field(default_factory=TypeCfg)
        type_B: TypeCfg = dataclasses.field(default_factory=TypeCfg)
        type_C: TypeCfg = dataclasses.field(default_factory=TypeCfg)

        @property
        def max_dt(self):
            return 1

    @dataclasses.dataclass
    class MainCfg:
        sim: SimCfg = dataclasses.field(default_factory=SimCfg)

    calls = []
    schedule = list("AAABBBBCCCAAABBBBCCC")

    def generate(ids, data_seed, n_history):
        calls.append((tuple(ids), data_seed, n_history))
        result = []
        for center in ids:
            kind = schedule[center - 33000] if len(ids) == 20 else "A"
            x = np.zeros((17000, 24), dtype=np.float32)
            x[:, 12:] = 1.0
            y = np.full((17000,), (center - 33000) / 40, dtype=np.float32)
            ts = 8 + np.arange(17000, dtype=np.int64)
            result.append(SimpleNamespace(
                center_id=center, center_type=kind, budget_tier="medium",
                dt=1, x=x, y=y, ts=ts,
                metadata={"center_type": kind, "dt": 1, "base_logit": 0.0},
            ))
        return result

    def features(x, dt):
        return np.concatenate(
            [x.astype(np.float32), np.full((len(x), 1), dt / 4, dtype=np.float32)],
            axis=1,
        )

    def scenario(base, name, config):
        return base.x.copy(), base.y.copy(), {
            "scenario": name, "onset_raw_index": 6520,
            "generator_revision": "p3_mismatch_v2_r3",
        }

    return {
        "np": np, "MainCfg": MainCfg, "generate_base_centers": generate,
        "feature_matrix": features, "make_scenario_v2": scenario,
        "calls": calls,
    }


def synthetic_bank():
    limits = {"parameters": 100000, "operations": 5000000}
    return {
        "bank_hash": "d" * 64,
        "limits_by_tier": {"medium": limits},
        "feasibility": {"medium": {
            "deployment_filter_hash": contract.canonical_hash(limits),
            "feasible_mask": [True, True],
            "feasible_ids": ["msa_a57_pt", "synthetic_candidate"],
            "initial_candidate_ids": ["synthetic_candidate"],
        }},
    }


class TestSyntheticOrchestration(unittest.TestCase):
    def run_fixture(self, label):
        runtime = synthetic_runtime()
        writer = MemoryWriter()
        config = {
            "generator_revision": "p3_mismatch_v2_r3",
            "scenarios": list(contract.SCENARIOS),
        }
        pins = {
            **module.EXTRACTED_SOURCE_PINS,
            "configs/p3_mismatch_v2_frozen.json": module.MISMATCH_CONFIG_PIN,
        }
        # _inside and file readers are mocked: no original file is touched.
        with mock.patch.object(module, "load_pure_runtime", return_value=runtime), \
                mock.patch.object(module, "_inside", return_value=Path("synthetic-unopened-config")), \
                mock.patch.object(contract, "file_sha256", return_value=module.MISMATCH_CONFIG_PIN), \
                mock.patch.object(contract, "read_json", return_value=config):
            result = module.materialize_context(
                Path("."), label, writer, "b" * 64, "c" * 64,
                synthetic_bank(), pins,
            )
        return result, runtime["calls"], writer

    def test_full_batch_is_one_ordered_call_and_complete_input_only(self):
        result, calls, writer = self.run_fixture("F1")
        self.assertEqual(calls, [(tuple(range(33000, 33020)), 7311, 17000)])
        self.assertEqual(
            tuple(len(result[key]) for key in ("base", "scenarios", "roles", "references")),
            (20, 80, 5760, 160),
        )
        self.assertFalse(result["initial_state_verified"])
        self.assertEqual(result["initial_state_verification"], "NOT_VERIFIED / SEPARATE_AUTH_REQUIRED")
        self.assertEqual(len(result["reference_parity_checks"]), 40)
        self.assertEqual(writer.array_writes, 20 * 3 + 80 * 4)
        self.assertTrue(all(path.startswith(("inputs/F1/", "inventories/F1/")) for path in writer.paths))

    def test_full_replicate_labels_and_output_paths_do_not_change_fingerprint(self):
        one, _, _ = self.run_fixture("F1")
        two, _, _ = self.run_fixture("F2")
        self.assertNotEqual(
            one["scenarios"]["33000/C0"]["files"],
            two["scenarios"]["33000/C0"]["files"],
        )
        self.assertEqual(one["input_bundle_digest"], two["input_bundle_digest"])
        for kind in ("base", "scenarios", "roles", "references"):
            self.assertEqual(
                {key: value["provenance_fingerprint"] for key, value in one[kind].items()},
                {key: value["provenance_fingerprint"] for key, value in two[kind].items()},
            )

    def test_singleton_descending_order_is_mechanism_control_not_new_inputs(self):
        one, first_calls, _ = self.run_fixture("S1")
        two, second_calls, _ = self.run_fixture("S2")
        self.assertEqual([call[0][0] for call in first_calls], list(range(33000, 33020)))
        self.assertEqual([call[0][0] for call in second_calls], list(range(33019, 32999, -1)))
        self.assertTrue(all(len(call[0]) == 1 for call in first_calls + second_calls))
        self.assertEqual(one["input_bundle_digest"], two["input_bundle_digest"])

    def test_model_seed_method_or_worker_not_accepted_materialization_inputs(self):
        import inspect

        names = set(inspect.signature(module.materialize_context).parameters)
        self.assertFalse(names & {"model_seed", "method", "workers", "warmup", "train", "evaluate"})


class TestSyntheticRoleBoundaries(unittest.TestCase):
    def test_final_service_and_reference_use_features_not_raw24_digest(self):
        import numpy as np

        raw = np.zeros((17000, 24), dtype=np.float32)
        feature = np.concatenate([raw, np.full((17000, 1), 0.5, dtype=np.float32)], axis=1)
        y = np.linspace(0, 1, 17000, dtype=np.float32)
        ts = 8 + np.arange(17000, dtype=np.int64) * 2
        update, assessment, service = contract.stage_spans(24)
        info = module._segment_info(
            "F", 33003, "C4", "service", service, raw, feature, y, ts,
            "a" * 64, "b" * 64, "c" * 64, {}, 24,
            int(ts[update[1] - 1]), int(ts[assessment[1] - 1]),
        )
        self.assertEqual(info["span"], [16360, 16760])
        self.assertEqual(info["window_count"], 304)
        self.assertEqual(info["start_ts"], 32728)
        self.assertEqual(info["end_ts"], 33526)
        self.assertEqual(
            info["legacy_role_hash"],
            contract.legacy_array_digest(feature[16360:16760], y[16360:16760], ts[16360:16760]),
        )
        self.assertNotEqual(
            info["legacy_role_hash"],
            contract.legacy_array_digest(raw[16360:16760], y[16360:16760], ts[16360:16760]),
        )
        reference = module._segment_info(
            "F", 33003, "C4", "reference", (800, 1000), raw, feature, y, ts,
            "a" * 64, "b" * 64, "c" * 64, {},
        )
        self.assertEqual(reference["window_count"], 104)
        self.assertNotEqual(reference["raw_legacy_array_digest"], reference["feature_legacy_array_digest"])


if __name__ == "__main__":
    unittest.main()
