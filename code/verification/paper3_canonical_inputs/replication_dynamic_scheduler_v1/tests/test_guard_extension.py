"""Synthetic import-origin closure tests; no scientific import or model call."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
from types import MappingProxyType
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dynamic_guard_extension_under_test", HERE / "guard_extension.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "tests", prefix="guard_synthetic_")
        self.repo = Path(self.temp.name); self.executor = self.repo / "executor"
        self.sidecar = self.repo / "scheduler"; self.executor.mkdir(); self.sidecar.mkdir()
        self.prov_source = self.executor / "provenance.py"
        source = ('from types import MappingProxyType\n'
                  'class ModelImportGuard: pass\n'
                  '_WRITE_GUARD_INSTALLED = False\n'
                  'def _bound_imports(manifest):\n'
                  '    return MappingProxyType(manifest["synthetic_origins"])\n')
        self.prov_source.write_text(source, encoding="utf-8")
        name = "synthetic_dynamic_provenance_" + str(id(self))
        self.module = types.ModuleType(name); self.module.__file__ = str(self.prov_source)
        sys.modules[name] = self.module
        exec(compile(source, str(self.prov_source), "exec"), self.module.__dict__)
        for name in ("guard_extension.py", "frozen_bridge.py"):
            (self.sidecar / name).write_text("# synthetic origin only\n", encoding="utf-8")
        self.sources = {str(p): g.sha(p) for p in self.sidecar.glob("*.py")}
        self.contract = {"source_extension_scope": g.EXTENSION_SCOPE, "sidecar_sources": self.sources,
                         "sidecar_digest": g.canonical(self.sources)}
        self.manifest = {"manifest_digest": "a" * 64, "paths": {"executor_root": str(self.executor)},
                         "executor_sha256": {"provenance.py": g.sha(self.prov_source)},
                         "synthetic_origins": {str(self.executor / "original.py").casefold(): "b" * 64}}
        self.patch = patch.multiple(g, REPO_ROOT=self.repo, SCHEDULER_ROOT=self.sidecar, EXECUTOR_ROOT=self.executor)
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); sys.modules.pop(self.module.__name__, None); self.temp.cleanup()

    def install(self):
        return g.install(self.module, self.manifest, self.contract)

    def test_original_origins_preserved_and_table_immutable(self):
        before = copy.deepcopy(self.manifest); receipt = self.install()
        table = self.module._bound_imports(self.manifest)
        self.assertIs(type(table), MappingProxyType)
        for name, digest in before["synthetic_origins"].items(): self.assertEqual(table[name], digest)
        self.assertEqual(len(table), len(before["synthetic_origins"]) + len(self.sources))
        self.assertEqual(before, self.manifest); self.assertTrue(receipt["original_origins_preserved"])
        with self.assertRaises(TypeError): table["new"] = "x"

    def test_does_not_hide_modules_or_change_file_identity(self):
        modules = set(sys.modules); before = self.module.__file__; source = self.prov_source.read_bytes()
        self.install()
        self.assertEqual(set(sys.modules), modules); self.assertEqual(self.module.__file__, before)
        self.assertEqual(self.prov_source.read_bytes(), source)

    def test_actual_added_source_SHA_checked_every_origin_lookup(self):
        self.install(); (self.sidecar / "frozen_bridge.py").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(g.GuardExtensionError, "source SHA differs"):
            self.module._bound_imports(self.manifest)

    def test_original_provenance_bytes_checked_after_install(self):
        self.install(); self.prov_source.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(g.GuardExtensionError, "provenance bytes changed"):
            self.module._bound_imports(self.manifest)

    def test_original_closure_cannot_change(self):
        self.install(); self.manifest["synthetic_origins"]["unexpected"] = "c" * 64
        with self.assertRaisesRegex(g.GuardExtensionError, "closure changed"):
            self.module._bound_imports(self.manifest)

    def test_other_manifest_cannot_reuse_extension(self):
        self.install(); other = copy.deepcopy(self.manifest); other["manifest_digest"] = "wrong"
        with self.assertRaisesRegex(g.GuardExtensionError, "another manifest"):
            self.module._bound_imports(other)

    def test_repeated_install_rejected(self):
        self.install()
        with self.assertRaisesRegex(g.GuardExtensionError, "already installed"): self.install()

    def test_post_write_guard_install_rejected(self):
        self.module._WRITE_GUARD_INSTALLED = True
        with self.assertRaisesRegex(g.GuardExtensionError, "precede original preparation"): self.install()

    def test_post_import_guard_install_rejected(self):
        with patch.object(sys, "meta_path", [*sys.meta_path, self.module.ModelImportGuard()]):
            with self.assertRaisesRegex(g.GuardExtensionError, "already installed"): self.install()

    def test_origin_provider_must_be_original_function(self):
        self.module._bound_imports = lambda _: MappingProxyType({})
        with self.assertRaisesRegex(g.GuardExtensionError, "freshly imported"): self.install()

    def test_sidecar_cannot_overlap_an_original_origin(self):
        self.manifest["synthetic_origins"][str(self.sidecar / "guard_extension.py").casefold()] = "b" * 64
        with self.assertRaisesRegex(g.GuardExtensionError, "replace an original"): self.install()

    def test_wrong_original_executor_root_rejected(self):
        self.manifest["paths"]["executor_root"] = str(self.repo / "other")
        with self.assertRaisesRegex(g.GuardExtensionError, "executor root differs"): self.install()

    def test_wrong_original_provenance_SHA_rejected(self):
        self.manifest["executor_sha256"]["provenance.py"] = "wrong"
        with self.assertRaisesRegex(g.GuardExtensionError, "provenance SHA differs"): self.install()

    def test_exact_scope_required(self):
        self.contract["source_extension_scope"] = "ALLOW_EVERYTHING"
        with self.assertRaisesRegex(g.GuardExtensionError, "scope differs"): self.install()

    def test_digest_required(self):
        self.contract["sidecar_digest"] = "wrong"
        with self.assertRaisesRegex(g.GuardExtensionError, "digest differs"): self.install()

    def test_missing_production_source_rejected(self):
        del self.sources[str(self.sidecar / "frozen_bridge.py")]
        self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaisesRegex(g.GuardExtensionError, "both production"): self.install()

    def test_external_source_rejected_even_with_correct_SHA(self):
        path = self.repo / "external.py"; path.write_text("external", encoding="utf-8")
        self.sources[str(path)] = g.sha(path); self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaisesRegex(g.GuardExtensionError, "outside independent scheduler"): self.install()

    def test_non_python_addition_rejected(self):
        path = self.sidecar / "data.json"; path.write_text("{}", encoding="utf-8")
        self.sources[str(path)] = g.sha(path); self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaises(g.GuardExtensionError): self.install()

    def test_invalid_source_SHA_rejected(self):
        self.sources[str(self.sidecar / "guard_extension.py")] = "wrong"
        self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaisesRegex(g.GuardExtensionError, "malformed"): self.install()

    def test_case_aliases_cannot_gain_multiple_origins(self):
        name = str(self.sidecar / "guard_extension.py")
        self.sources[name.upper()] = self.sources[name]; self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaises(g.GuardExtensionError): self.install()

    def test_reparse_source_rejected(self):
        original = Path.is_symlink; target = self.sidecar / "guard_extension.py"
        with patch.object(Path, "is_symlink", lambda path: path == target or original(path)):
            with self.assertRaisesRegex(g.GuardExtensionError, "symlink"): self.install()

    def test_sidecar_map_cannot_change_after_install(self):
        self.install()
        path = self.sidecar / "unexpected.py"; path.write_text("# new", encoding="utf-8")
        self.sources[str(path)] = g.sha(path); self.contract["sidecar_digest"] = g.canonical(self.sources)
        with self.assertRaisesRegex(g.GuardExtensionError, "bindings changed"):
            self.module._bound_imports(self.manifest)

    def test_original_guard_class_untouched(self):
        original = self.module.ModelImportGuard; self.install()
        self.assertIs(self.module.ModelImportGuard, original)

    def test_receipt_never_claims_actual_model_execution(self):
        value = self.install()
        self.assertFalse(value["real_model_execution_claimed"])
        self.assertFalse(value["loaded_modules_hidden"])
        self.assertFalse(value["module_file_attributes_changed"])
        self.assertFalse(value["scientific_algorithm_modified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
