"""Pure synthetic import-origin metadata tests; no scientific package import."""
from __future__ import annotations

import copy
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import provenance as p


class ImportBindingCacheSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"],prefix="import_cache_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo, self.executor = self.root/"repo",self.root/"executor"
        self.repo.mkdir(); self.executor.mkdir()
        (self.repo/"core").mkdir()
        self.env = self.root/"environment.py"
        self.original = self.repo/"core/original.py"
        self.source = self.executor/"fixture.py"
        for path in (self.env,self.original,self.source): path.write_text("pass\n",encoding="utf-8")
        self.manifest = {"paths":{"repo":str(self.repo),"executor_root":str(self.executor)},
            "environment":{"bound_files_sha256":{str(self.env):p.file_sha256(self.env)}},
            "original_python_dependency_sha256":{"core/original.py":p.file_sha256(self.original)},
            "executor_sha256":{"fixture.py":p.file_sha256(self.source)}}
        self.cache = patch.object(p,"_IMPORT_BINDINGS_CACHE",{})
        self.cache.start(); self.addCleanup(self.cache.stop)

    def test_same_complete_binding_reuses_immutable_table_without_path_rescan(self):
        with patch.object(p,"regular_path",wraps=p.regular_path) as normalize:
            first = p._bound_imports(self.manifest)
            first_calls = normalize.call_count
            second = p._bound_imports(copy.deepcopy(self.manifest))
            self.assertIs(first,second)
            self.assertEqual(normalize.call_count,first_calls)
            self.assertGreater(first_calls,0)
        with self.assertRaises(TypeError): first[str(self.source).casefold()] = "a"*64

    def test_cache_key_changes_for_every_origin_map_and_repository_root(self):
        original = p._bound_imports(self.manifest)
        for field in ("environment","original_python_dependency_sha256","executor_sha256"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.manifest)
                mapping = changed[field]["bound_files_sha256"] if field=="environment" else changed[field]
                mapping[next(iter(mapping))] = "b"*64
                self.assertIsNot(original,p._bound_imports(changed))
        other = self.root/"other_repo"
        (other/"core").mkdir(parents=True)
        (other/"core/original.py").write_text("pass\n",encoding="utf-8")
        changed = copy.deepcopy(self.manifest)
        changed["paths"]["repo"] = str(other)
        self.assertIsNot(original,p._bound_imports(changed))
        self.assertEqual(original[str(self.source).casefold()],p.file_sha256(self.source))

    def test_cached_origin_table_still_requires_fresh_actual_file_sha(self):
        p._bound_imports(self.manifest)
        guard = p.ModelImportGuard(self.manifest)
        spec = types.SimpleNamespace(origin=str(self.source),submodule_search_locations=None)
        with patch.object(p.BuiltinImporter,"find_spec",return_value=None), \
                patch.object(p.FrozenImporter,"find_spec",return_value=None), \
                patch.object(p.PathFinder,"find_spec",return_value=spec):
            self.assertIs(guard.find_spec("synthetic"),spec)
            self.source.write_text("changed after cache creation\n",encoding="utf-8")
            with self.assertRaises(p.ProvenanceError): guard.find_spec("synthetic")

    def test_cached_origin_table_still_requires_fresh_reparse_rejection(self):
        guard = p.ModelImportGuard(self.manifest)
        spec = types.SimpleNamespace(origin=str(self.source),submodule_search_locations=None)
        reparse = types.SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400)
        with patch.object(p.BuiltinImporter,"find_spec",return_value=None), \
                patch.object(p.FrozenImporter,"find_spec",return_value=None), \
                patch.object(p.PathFinder,"find_spec",return_value=spec), \
                patch.object(Path,"lstat",return_value=reparse),self.assertRaises(p.ProvenanceError):
            guard.find_spec("synthetic")


if __name__ == "__main__": unittest.main()
