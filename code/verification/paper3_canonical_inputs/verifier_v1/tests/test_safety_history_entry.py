"""Independent synthetic/mock tests; authored for later authorization, NOT RUN.

No project generator, model, warm-up, historical file or output is accessed.
Filesystem behavior is mocked; all inputs are tiny literals.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NAME = "paper3_entry_test_package"
if NAME not in sys.modules:
    module = types.ModuleType(NAME)
    module.__path__ = [str(ROOT)]
    sys.modules[NAME] = module
contract = importlib.import_module(NAME + ".contract")
safety = importlib.import_module(NAME + ".safety")
history = importlib.import_module(NAME + ".history")
entry = importlib.import_module(NAME + ".verify_inputs")
preflight = importlib.import_module(NAME + ".preflight")


class EntryTests(unittest.TestCase):
    def test_historical_patch_is_literal_text_never_executes(self):
        relative = "scripts/run_p7_7_final.py"
        add = "*** Begin Patch\n*** Add File: D:/dt-talk/DT_LIFECYCLE_ESCALATION/" + relative + "\n+one\n+two\n*** End Patch"
        change = "*** Begin Patch\n*** Update File: D:/dt-talk/DT_LIFECYCLE_ESCALATION/" + relative + "\n@@\n one\n-two\n+raise RuntimeError('must never execute')\n*** End Patch"
        original = history.apply_text_patch(None, add, relative)
        changed = history.apply_text_patch(original, change, relative)
        self.assertEqual(changed, "one\nraise RuntimeError('must never execute')\n")
        with self.assertRaises(contract.ContractError):
            history.apply_text_patch("different\n", change, relative)
        # JSONL historical protocol event 23150 was accepted by apply_patch even
        # though the deletion hunk's indentation differed from source. Matching
        # may use whitespace fallback; replacement bytes remain verbatim.
        for source, deleted in (("    item\n", "      item"), ("item   \n", "item")):
            with self.subTest(source=source, deleted=deleted):
                whitespace = "*** Begin Patch\n*** Update File: D:/dt-talk/DT_LIFECYCLE_ESCALATION/" + relative + "\n@@\n-" + deleted + "\n+  replacement\n*** End Patch"
                self.assertEqual(history.apply_text_patch(source, whitespace, relative), "  replacement\n")
        # Exact matching must beat a prior whitespace-only match, and rstrip
        # must beat a prior strip-only match, just as the historical tool did.
        self.assertEqual(history._find([" item", "item"], ["item"], 0), 1)
        self.assertEqual(history._find([" item", "item  "], ["item"], 0), 1)

    def test_path_escape_and_windows_names_rejected_before_io(self):
        for invalid in ("../results.csv", "x/../../a", "C:/a", "a\\b", "CON.txt", "a//b", "a."):
            with self.assertRaises(contract.ContractError):
                safety.contained_path(Path("D:/mock"), invalid, must_exist=False)

    def test_exclusive_open_mode(self):
        fake_root = Path("D:/mock/newrun")
        fake_target = fake_root / "a.json"
        with patch.object(safety, "regular_path", side_effect=lambda value, **kwargs: value), \
             patch.object(safety, "contained_path", return_value=fake_target), \
             patch.object(Path, "mkdir"), patch.object(Path, "open") as opened:
            writer = safety.SafeWriter(fake_root)
            writer._open("a.json")
            opened.assert_called_once_with("xb")

    def test_output_run_id_rejected_before_mkdir(self):
        for value in ("../old", "", "a/b", "0bad", "existing:stream"):
            with self.assertRaises(contract.ContractError):
                safety.SafeWriter.reserve(Path("D:/mock"), value)

    def test_f_s_matrix_is_exact_and_ignores_storage_labels(self):
        left = {key: {} for key in ("base", "scenarios", "roles", "references")}
        left["base"]["33000"] = {"profile": {"type": "A"}, "files": {"x": "F1/x.npy"},
                                   "provenance_fingerprint": "different_context_F"}
        right = json.loads(json.dumps(left))
        right["base"]["33000"]["files"]["x"] = "S1/x.npy"
        right["base"]["33000"]["provenance_fingerprint"] = "different_context_S"
        self.assertTrue(all(row["status"] == "MATCH" for row in entry.compare_fields(left, right)))
        right["base"]["33000"]["profile"]["type"] = "B"
        self.assertEqual(entry.compare_fields(left, right)[0]["status"], "MISMATCH")

    def test_definition_never_upgrades_initial_state(self):
        value = preflight.definition()
        self.assertEqual(value["R2"], "PENDING_SEPARATE_AUTHORIZATION")
        self.assertEqual(value["R3"], "PENDING_SEPARATE_AUTHORIZATION")
        self.assertEqual(value["data_seed"], 7311)
        self.assertFalse(value["selection_based_on_performance"])

    def test_finish_sha_graph_excludes_self_and_receipt(self):
        class MemoryWriter:
            def __init__(self):
                self.items = {"input.json": {"x": 1}}
                self.created_sha256 = {}
            def inventory(self): return {name: contract.canonical_hash(value) for name, value in self.items.items()}
            def write_json(self, name, value):
                if name in self.items: raise contract.ContractError("collision")
                self.items[name] = value
        writer = MemoryWriter()
        git = {"root": "D:/mock"}
        state = {"git": git, "pins": {}, "source_environment": {"implementation": {"a": "b"}},
                 "authorization": {"run_id": "mock"}, "authorization_sha256": "0" * 64,
                 "definition_digest": "1" * 64, "dependency_digest": "2" * 64}
        with patch.object(entry, "snapshot_protected", return_value={"file": "sha"}), \
             patch.object(entry, "git_snapshot", return_value=git), \
             patch.object(entry, "implementation_inventory", return_value={"a": "b"}):
            self.assertEqual(entry._finish(writer, state, "mockstart", {"file": "sha"}, git, complete=True), 0)
        self.assertNotIn("run_manifest.json", writer.items["run_manifest.json"]["file_bindings"])
        self.assertNotIn("outputs_inventory.json", writer.items["outputs_inventory.json"]["files"])
        self.assertNotIn("execution_receipt.json", writer.items["outputs_inventory.json"]["files"])
        self.assertFalse(writer.items["execution_receipt.json"]["initial_state_verified"])

    def test_child_command_retains_isolation_and_absent_cache_prefix(self):
        command = entry.worker_command(Path("D:/mock"), Path("D:/mock/auth.json"), "ApprovedRun", "F1")
        self.assertEqual(command[1:5], ["-I", "-S", "-B", "-X"])
        self.assertIn("_never_created_pycache", command[5])
        self.assertEqual(command[-2:], ["--internal-context", "F1"])


if __name__ == "__main__":
    unittest.main()
