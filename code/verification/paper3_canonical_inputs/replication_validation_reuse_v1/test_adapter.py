"""Synthetic pure metadata contracts; no full verifier/native backend/science calls."""
import ast
import copy
import importlib.util
from importlib.machinery import ModuleSpec
import marshal
from pathlib import Path
import struct
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
target = HERE / "original_provenance_adapter.py"
a = ModuleType("paper3_adapter_test_target"); a.__file__ = str(target); a.__package__ = ""
a.__spec__ = ModuleSpec(a.__name__, loader=None, origin=str(target)); sys.modules[a.__name__] = a
exec(compile(target.read_bytes(), str(target), "exec", dont_inherit=True), a.__dict__)


def fixture():
    prefix = str(HERE / "synthetic_venv")
    base = str(HERE / "synthetic_base")
    descriptor = {"schema": "paper3-reviewed-independent-model-runtime-v1",
        "environment_id": a.IDENTITIES["model_environment_id"], "prefix": prefix, "base_prefix": base,
        "python_executable": str(Path(prefix) / "Scripts/python.exe"),
        "site_packages_root": str(Path(prefix) / "Lib/site-packages"), "stdlib_root": str(Path(base) / "Lib"),
        "expected_versions": dict(a.EXPECTED_MODEL_VERSIONS)}
    env = {"python_executable": descriptor["python_executable"], "python_version": "3.11.14",
        "thread_environment": {"OMP_NUM_THREADS": "1"}, "model_runtime_environment": {"CUDA_VISIBLE_DEVICES": ""},
        "byteorder": "little", "platform": "synthetic Windows", "hardware": {"machine": "AMD64", "processor": "fixture", "processor_identifier": "fixture"},
        "packages_imported_during_capture": False, "historical_environment_reproduced": False,
        "site_startup_processed": False, "model_environment_id": a.IDENTITIES["model_environment_id"],
        "model_runtime_descriptor": descriptor, "model_runtime_descriptor_digest": a.canonical(descriptor),
        "site_packages_root": descriptor["site_packages_root"], "input_environment": {"fixture": True},
        "exact_versions": dict(a.EXPECTED_MODEL_VERSIONS)}
    env["model_runtime_environment_digest"] = a.canonical(env["model_runtime_environment"])
    env["input_environment_digest"] = a.canonical(env["input_environment"])
    manifest = {**a.IDENTITIES, "environment": env, "environment_binding": a.canonical(env),
        "frozen_final_configuration": {"fixture_only": True}}
    manifest["manifest_digest"] = a.canonical(manifest)
    observed = {"executable": a.lexical(env["python_executable"]), "python_version": env["python_version"],
        "base_prefix": a.lexical(base), "thread_environment": copy.deepcopy(env["thread_environment"]),
        "model_runtime_environment": copy.deepcopy(env["model_runtime_environment"]),
        "byteorder": env["byteorder"], "platform": env["platform"], "hardware": copy.deepcopy(env["hardware"]),
        "isolated": True, "no_site": True, "no_bytecode": True,
        "scientific_import_pending": False, "scientific_import_post": False, "scientific_modules": []}
    return manifest, observed


def reseal(m):
    m["environment_binding"] = a.canonical(m["environment"])
    m.pop("manifest_digest"); m["manifest_digest"] = a.canonical(m)


class AdapterTests(unittest.TestCase):
    def test_pure_metadata_accepts_exact_contract(self):
        m, o = fixture(); result = a.non_file_predicates(m, o)
        self.assertTrue(result["runtime_semantics_checked"])
        self.assertFalse(result["new_file_SHA_check_performed"])

    def test_each_fresh_runtime_predicate_rejects(self):
        changes = {"executable": "different.exe", "python_version": "3.11.0", "base_prefix": "different",
            "thread_environment": {}, "model_runtime_environment": {}, "byteorder": "big", "platform": "other",
            "hardware": {}, "isolated": False, "no_site": False, "no_bytecode": False,
            "scientific_import_pending": True, "scientific_import_post": True, "scientific_modules": ["numpy"]}
        for key, value in changes.items():
            with self.subTest(key=key):
                m, o = fixture(); o[key] = value
                with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_manifest_mutation_rejects_without_reseal(self):
        m, o = fixture(); m["frozen_final_configuration"]["fixture_only"] = False
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_resealed_wrong_scientific_identity_rejects(self):
        for key in a.IDENTITIES:
            with self.subTest(key=key):
                m, o = fixture(); m[key] = "other"; reseal(m)
                with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_resealed_runtime_scope_rejects(self):
        for key in ("packages_imported_during_capture", "historical_environment_reproduced", "site_startup_processed"):
            with self.subTest(key=key):
                m, o = fixture(); m["environment"][key] = True; reseal(m)
                with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_empty_configuration_rejects(self):
        m, o = fixture(); m["frozen_final_configuration"] = {}; reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_descriptor_digest_rejects(self):
        m, o = fixture(); m["environment"]["model_runtime_descriptor"]["schema"] = "other"; reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_runtime_layout_semantics_reject_resealed_change(self):
        m, o = fixture(); env = m["environment"]; env["model_runtime_descriptor"]["stdlib_root"] = str(HERE)
        env["model_runtime_descriptor_digest"] = a.canonical(env["model_runtime_descriptor"]); reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_input_environment_digest_rejects(self):
        m, o = fixture(); m["environment"]["input_environment"] = {"other": True}; reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_exact_dependency_versions_reject(self):
        m, o = fixture(); m["environment"]["exact_versions"]["numpy"] = "other"; reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_duplicate_canonical_distribution_rejects(self):
        m, o = fixture(); env = m["environment"]; descriptor = env["model_runtime_descriptor"]
        descriptor["expected_versions"]["scikit_learn"] = "1.9.0"
        env["model_runtime_descriptor_digest"] = a.canonical(descriptor); reseal(m)
        with self.assertRaises(a.AdapterError): a.non_file_predicates(m, o)

    def test_original_source_pin_and_real_import_only(self):
        self.assertEqual(a.digest(a.PROVENANCE), a.PROVENANCE_SHA256)
        p = a.load_original_provenance()
        self.assertEqual(a.lexical(p.verify_frozen.__code__.co_filename), a.lexical(a.PROVENANCE))
        self.assertIsNone(p._PLATFORM_BOOTSTRAP)
        self.assertIsNone(p._SCIENTIFIC_IMPORT_POST)

    def test_valid_forged_pyc_is_ignored_by_exact_source_loader(self):
        with tempfile.TemporaryDirectory(prefix="paper3_exact_loader_") as directory:
            source = Path(directory) / "fixture.py"
            source_bytes = b"VALUE = 'APPROVED_SOURCE'\n"
            source.write_bytes(source_bytes)
            pyc = Path(importlib.util.cache_from_source(str(source))); pyc.parent.mkdir()
            forged = compile("VALUE = 'FORGED_CACHE'\n", str(source), "exec")
            header = importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(source.stat().st_mtime), len(source_bytes))
            pyc.write_bytes(header + marshal.dumps(forged))
            reference_spec = importlib.util.spec_from_file_location("synthetic_reference_" + uuid.uuid4().hex, source)
            reference = importlib.util.module_from_spec(reference_spec); reference_spec.loader.exec_module(reference)
            self.assertEqual(reference.VALUE, "FORGED_CACHE")  # -B still permits existing pyc reads.
            name = "synthetic_exact_" + uuid.uuid4().hex
            module = a.exact_source_module(source, name, a.hashlib.sha256(source_bytes).hexdigest())
            try:
                self.assertEqual(module.VALUE, "APPROVED_SOURCE")
                self.assertIsNone(module.__cached__)
                self.assertIsNone(module.__loader__)
            finally:
                sys.modules.pop(name, None)

    def test_exact_loader_rejects_unapproved_source_bytes(self):
        with tempfile.TemporaryDirectory(prefix="paper3_exact_loader_") as directory:
            source = Path(directory) / "fixture.py"; source.write_bytes(b"VALUE = 'different'\n")
            name = "synthetic_rejected_" + uuid.uuid4().hex
            with self.assertRaises(a.AdapterError):
                a.exact_source_module(source, name, "0" * 64)
            self.assertNotIn(name, sys.modules)

    def test_exact_loader_reads_source_once_and_executes_that_read(self):
        with tempfile.TemporaryDirectory(prefix="paper3_exact_loader_") as directory:
            source = Path(directory) / "fixture.py"
            approved = b"VALUE = 'ONE_READ'\n"
            name = "synthetic_one_read_" + uuid.uuid4().hex
            with patch.object(Path, "read_bytes", side_effect=[approved, b"raise RuntimeError('second read')\n"]) as read:
                module = a.exact_source_module(source, name, a.hashlib.sha256(approved).hexdigest())
                self.assertEqual(read.call_count, 1)
            try:
                self.assertEqual(module.VALUE, "ONE_READ")
            finally:
                sys.modules.pop(name, None)

    def test_exact_loader_module_registration_supports_dataclasses(self):
        with tempfile.TemporaryDirectory(prefix="paper3_exact_loader_") as directory:
            source = Path(directory) / "fixture.py"
            payload = b"from dataclasses import dataclass\n@dataclass\nclass Record:\n    value: int\ndef origin(): pass\n"
            source.write_bytes(payload); name = "synthetic_dataclass_" + uuid.uuid4().hex
            module = a.exact_source_module(source, name, a.hashlib.sha256(payload).hexdigest())
            try:
                self.assertEqual(module.Record(7).value, 7)
                self.assertIs(sys.modules[name], module)
                self.assertEqual(module.__file__, str(source))
                self.assertEqual(module.__spec__.origin, str(source))
                self.assertEqual(module.__package__, "")
                self.assertEqual(module.origin.__code__.co_filename, str(source))
            finally:
                sys.modules.pop(name, None)

    def test_exact_loader_removes_failed_module(self):
        with tempfile.TemporaryDirectory(prefix="paper3_exact_loader_") as directory:
            source = Path(directory) / "fixture.py"; payload = b"raise RuntimeError('fixture failure')\n"
            source.write_bytes(payload); name = "synthetic_failure_" + uuid.uuid4().hex
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                a.exact_source_module(source, name, a.hashlib.sha256(payload).hexdigest())
            self.assertNotIn(name, sys.modules)

    def test_production_module_loads_use_reviewed_pins_not_fresh_source_digest(self):
        tree = ast.parse((HERE / "original_provenance_adapter.py").read_text(encoding="utf-8"))
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "exec_module"])
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "exact_source_module"]
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(isinstance(c.args[2], ast.Name) and c.args[2].id == "PROVENANCE_SHA256" for c in calls))
        self.assertTrue(any(isinstance(c.args[2], ast.Subscript) and isinstance(c.args[2].value, ast.Name)
            and c.args[2].value.id == "verifier_sources" for c in calls))

    def test_bookend_source_calls_original_with_all_flags_true(self):
        tree = ast.parse((HERE / "original_provenance_adapter.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self" and n.func.attr == "_full"]
        self.assertEqual(len(calls), 1)
        self.assertEqual({k.arg: k.value.value for k in calls[0].keywords},
            {"verify_environment": True, "full": True, "check_inputs": True})

    def test_adapter_has_no_statistics_model_process_or_publication_entry(self):
        tree = ast.parse((HERE / "original_provenance_adapter.py").read_text(encoding="utf-8"))
        imports = {n.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
        self.assertFalse(imports & (a.SCIENCE | {"subprocess"}))
        forbidden = {"run_statistics", "publish_delivery", "publish_root", "make_zip", "Popen", "terminate", "kill"}
        self.assertFalse({n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)} & forbidden)


if __name__ == "__main__":
    unittest.main(verbosity=2)
