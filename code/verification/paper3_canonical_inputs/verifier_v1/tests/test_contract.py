"""Independent synthetic tests, supplied but NOT RUN during implementation.

No generator, model, checkpoint, lifecycle method, performance metric or legacy
result is imported/read. Temporary filesystem writes are unnecessary: IO tests
use mocked read-only streams, and bank tests use synthetic metadata dictionaries.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contract.py"
SPEC = importlib.util.spec_from_file_location("paper3_contract_under_test", CONTRACT_PATH)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class PureContractTests(unittest.TestCase):
    def test_population_and_method_order(self):
        self.assertEqual(contract.CENTERS, tuple(range(33000, 33020)))
        self.assertEqual(contract.SEEDS, (7311, 7312, 7313))
        self.assertEqual(contract.SCENARIOS, ("C0", "C1", "C3", "C4"))
        self.assertEqual([value[0] for value in contract.METHODS], ["B0", "B1", "B2", "B8", "P7.7"])

    def test_all_stage_bounds_and_role_lengths(self):
        self.assertEqual(contract.stage_spans(1), ((1000, 1400), (1400, 1640), (1640, 2040)))
        self.assertEqual(contract.stage_spans(24), ((15720, 16120), (16120, 16360), (16360, 16760)))
        for stage in range(1, 25):
            spans = contract.stage_spans(stage)
            self.assertEqual([b - a for a, b in spans], [400, 240, 400])
            self.assertEqual(spans[0][1], spans[1][0])
            self.assertEqual(spans[1][1], spans[2][0])
            self.assertLessEqual(spans[2][1], 17000)
        for invalid in (0, 25, True, 1.0, "1"):
            with self.assertRaises(contract.ContractError):
                contract.stage_spans(invalid)

    def test_legacy_canonical_hash_independent_byte_reference(self):
        value = {"β": [1, 0.1, True], "a": {"z": None}}
        expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(contract.canonical_hash(value), expected)
        with self.assertRaises(contract.ContractError):
            contract.canonical_hash({"x": float("nan")})
        with self.assertRaises(contract.ContractError):
            contract.canonical_hash({1: "a"})

    def test_read_json_rejects_duplicates_and_nonfinite(self):
        for text in ('{"x":1,"x":2}', '{"a":{"b":1,"b":2}}', '{"x":NaN}', '{"x":1e999}'):
            with patch.object(Path, "open", return_value=io.StringIO(text)):
                with self.assertRaises(contract.ContractError):
                    contract.read_json("synthetic.json")
        with patch.object(Path, "open", return_value=io.StringIO('{"x":1,"y":[true,null]}')):
            self.assertEqual(contract.read_json("synthetic.json"), {"x": 1, "y": [True, None]})

    def test_file_hash_reads_bytes_only(self):
        payload = b"synthetic input contract\x00" * 100
        with patch.object(Path, "open", return_value=io.BytesIO(payload)) as opened:
            self.assertEqual(contract.file_sha256("synthetic.bin"), hashlib.sha256(payload).hexdigest())
        opened.assert_called_once_with("rb")


class SyntheticArrayTests(unittest.TestCase):
    def test_legacy_array_digest_matches_original_algorithm_no_cast(self):
        import numpy as np

        for dtype in ("<f4", ">f4"):
            x = np.arange(24, dtype=np.dtype(dtype)).reshape(6, 4)[:, ::2]
            y = np.arange(6, dtype=np.float32)
            ts = np.arange(6, dtype=np.int64) * 2
            digest = hashlib.sha256()
            for array in (x, y, ts):
                value = np.ascontiguousarray(array)
                digest.update(str(value.shape).encode())
                digest.update(value.dtype.str.encode())
                digest.update(value.tobytes())
            before = [value.copy() for value in (x, y, ts)]
            self.assertEqual(contract.legacy_array_digest(x, y, ts), digest.hexdigest())
            self.assertNotEqual(contract.legacy_array_digest(x, y, ts), contract.legacy_array_digest(y, x, ts))
            for original, saved in zip((x, y, ts), before):
                self.assertTrue(np.array_equal(original, saved))
                self.assertEqual(original.dtype, saved.dtype)
                self.assertEqual(original.shape, saved.shape)

    def test_metadata_conversion_preserves_dtype_shape_and_integer(self):
        import numpy as np

        original = {"weights": np.array([[0.5, -0.0]], dtype=">f4"), "large": np.uint64(2**63 + 7), "nested": (np.bool_(True),)}
        result = contract.jsonable(original)
        self.assertEqual(result["weights"]["dtype_str"], ">f4")
        self.assertEqual(result["weights"]["shape"], [1, 2])
        self.assertTrue(result["weights"][contract.ARRAY_TAG])
        self.assertEqual(result["large"], 2**63 + 7)
        self.assertEqual(result["nested"], [True])
        self.assertIn("-0.0", json.dumps(result))
        for invalid in (np.array([None], dtype=object), np.array([float("inf")]), {contract.ARRAY_TAG: True}, {1: "a"}, {"x": object()}):
            with self.assertRaises(contract.ContractError):
                contract.jsonable(invalid)

    def test_shape_contract_and_summary(self):
        import numpy as np

        x = np.zeros((6, 2), dtype=np.float32)
        y = np.zeros(6, dtype=np.float32)
        ts = np.arange(6, dtype=np.int64) * 4
        contract.check_shapes(x, y, ts, raw_features=2, n=6)
        summary = contract.describe_arrays(x, y, ts)
        self.assertEqual(summary["arrays"]["x"]["shape"], [6, 2])
        self.assertEqual(summary["arrays"]["x"]["dtype_str"], x.dtype.str)
        self.assertEqual(summary["legacy_array_digest"], contract.legacy_array_digest(x, y, ts))
        invalids = [(x.astype(np.float64), y, ts), (x, y[:, None], ts), (x, y, ts.astype(np.float64)), (x, y, np.array([0, 4, 8, 12, 16, 21], dtype=np.int64))]
        for invalid in invalids:
            with self.assertRaises(contract.ContractError):
                contract.check_shapes(*invalid, raw_features=2, n=6)
        with self.assertRaises(contract.ContractError):
            contract.legacy_array_digest(np.array([float("nan")]))


class StaticBankTests(unittest.TestCase):
    @staticmethod
    def manifests():
        identities = []
        for index, identity in enumerate(contract.NATIVE_IDS + contract.SOURCE_IDS):
            identities.append({
                "identity_id": identity, "architecture_index": index,
                "architecture": "synthetic", "family": "synthetic",
                "source_initialization_id": f"synthetic_{index}",
                "checkpoint": f"synthetic/{index}.pt", "checkpoint_sha256": "a" * 64,
                "parameter_count": 30001 if index == 0 else 100,
                "operation_count": 1500001 if index == 1 else 100,
            })
        native = {"identities": identities[:8], "bank_hash": contract.canonical_hash(identities[:8])}
        source = {"generator_revision": "p3_mismatch_v2_r3", "assets": identities[8:], "native_incumbent": identities[5]}
        source["assets"][0] = {**source["assets"][0], "source_validation_mse": 12345.0}
        config = {"generator_revision": "p3_mismatch_v2_r3", "deployment_limits": {
            "tight": {"parameters": 30000, "operations": 1500000},
            "medium": {"parameters": 100000, "operations": 5000000},
            "loose": {"parameters": 500000, "operations": 20000000},
        }}
        return native, source, config

    def test_order_whitelist_feasibility_and_no_checkpoint_verification(self):
        payloads = self.manifests()
        with patch.object(contract, "read_json", side_effect=payloads), patch.object(contract, "file_sha256", return_value="b" * 64):
            result = contract.identity_bank(CONTRACT_PATH.parent)
        self.assertEqual([value["identity_id"] for value in result["identities"]], list(contract.NATIVE_IDS + contract.SOURCE_IDS))
        self.assertTrue(all(tuple(value) == contract.IDENTITY_FIELDS for value in result["identities"]))
        self.assertEqual(result["feasibility"]["tight"]["feasible_mask"][:2], [False, False])
        self.assertEqual(len(result["feasibility"]["medium"]["feasible_ids"]), 11)
        self.assertNotIn(contract.INCUMBENT_ID, result["feasibility"]["medium"]["initial_candidate_ids"])
        self.assertFalse(result["checkpoint_bytes_verified"])
        self.assertFalse(result["resource_profiling_executed"])

    def test_reordered_bank_changed_limits_and_corrupt_binding_rejected(self):
        for variant in ("order", "limits", "hash", "incumbent"):
            native, source, config = copy.deepcopy(self.manifests())
            if variant == "order":
                native["identities"][0:2] = reversed(native["identities"][0:2])
            elif variant == "limits":
                config["deployment_limits"]["tight"]["parameters"] += 1
            elif variant == "hash":
                native["bank_hash"] = "0" * 64
            else:
                source["native_incumbent"]["parameter_count"] += 1
            with patch.object(contract, "read_json", side_effect=(native, source, config)), patch.object(contract, "file_sha256", return_value="b" * 64):
                with self.assertRaises(contract.ContractError):
                    contract.identity_bank(CONTRACT_PATH.parent)


if __name__ == "__main__":
    unittest.main()
