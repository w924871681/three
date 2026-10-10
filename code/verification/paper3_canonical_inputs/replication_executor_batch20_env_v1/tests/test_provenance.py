"""Synthetic standard-library provenance tests; no project/model/generator imports.

All fixtures live beneath the launcher's authorized synthetic temporary root.
Irreversible process hooks are intercepted, never installed in the test runner.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import provenance as p


class ProvenanceSyntheticTests(unittest.TestCase):
    def setUp(self):
        root = os.environ.get("PAPER3_SYNTHETIC_TEMP_ROOT")
        self.assertIsNotNone(root,"launcher must designate new-output-only synthetic fixtures")
        self.temporary = tempfile.TemporaryDirectory(dir=root,prefix="provenance_")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_strict_json_hash_and_duplicate_rejection(self):
        self.assertEqual(p.canonical_hash({"a":1,"b":[2,3]}),p.canonical_hash({"b":[2,3],"a":1}))
        file = self.folder/"fixture.json"
        file.write_text('{"a":1,"a":2}',encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): p.read_json(file)
        file.write_text('{"value":NaN}',encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): p.read_json(file)
        with self.assertRaises(p.ProvenanceError): p.canonical_hash({"value":float("inf")})
        with self.assertRaises(p.ProvenanceError): p.canonical_hash({1:"non-string key"})

    def test_independent_runtime_variables_bound_without_mutating_stage_b(self):
        actual = {name:None for name in p.MODEL_RUNTIME_ENV}
        actual.update(CUDA_VISIBLE_DEVICES="0",CUBLAS_WORKSPACE_CONFIG=":4096:8",MKL_THREADING_LAYER="INTEL",
                      OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2")
        historical_input = {"thread_environment":{name:actual[name] for name in p.THREAD_ENV}}
        original = json.dumps(historical_input,sort_keys=True)
        with patch.object(p.os.environ,"get",side_effect=lambda name,*args:actual.get(name)):
            snapshot = p._model_runtime_environment()
            environment = {"input_environment":historical_input,"model_runtime_environment":snapshot,
                           "model_runtime_environment_digest":p.canonical_hash(snapshot)}
            p._verify_model_runtime_environment(environment)
            self.assertEqual(original,json.dumps(historical_input,sort_keys=True))
            actual["CUDA_VISIBLE_DEVICES"] = "1"
            with self.assertRaises(p.ProvenanceError): p._verify_model_runtime_environment(environment)
            actual["CUDA_VISIBLE_DEVICES"] = "0"
            environment["model_runtime_environment_digest"] = "f"*64
            with self.assertRaises(p.ProvenanceError): p._verify_model_runtime_environment(environment)
            environment["model_runtime_environment"] = {"CUDA_VISIBLE_DEVICES":"0"}
            with self.assertRaises(p.ProvenanceError): p._verify_model_runtime_environment(environment)

    def test_path_traversal_reserved_and_reparse_rejected(self):
        for name in ("../outside","/absolute","sub\\file","CON.json","NUL","sub/COM1.bin","trailing.","a//b"):
            with self.subTest(name=name),self.assertRaises(p.ProvenanceError):
                p.checked_path(self.folder,name,must_exist=False)
        allowed = p.checked_path(self.folder,"nested/output.json",must_exist=False)
        self.assertEqual(allowed,self.folder/"nested"/"output.json")
        fixture = self.folder/"fixture.txt"
        fixture.write_text("synthetic",encoding="utf-8")
        info = types.SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400)
        with patch.object(Path,"lstat",return_value=info),self.assertRaises(p.ProvenanceError):
            p.regular_path(fixture)

    def test_exclusive_atomic_publication_keeps_original_output(self):
        repo = self.folder/"fixture_repo"
        results = repo/p.RESULTS_NAME
        results.mkdir(parents=True)
        with patch.object(p,"REPOSITORY",repo):
            receipt = p.publish_json(results,"nested/input.json",{"synthetic":True})
            self.assertEqual(receipt["sha256"],p.file_sha256(results/"nested/input.json"))
            before = (results/"nested/input.json").read_bytes()
            with self.assertRaises(p.ProvenanceError):
                p.publish_json(results,"nested/input.json",{"synthetic":False})
            self.assertEqual(before,(results/"nested/input.json").read_bytes())
            self.assertEqual([],list((results/"nested").glob("*.partial_*")))

    def test_write_audit_guard_paths_directory_fds_and_hardlink_cleanup(self):
        hooks = []
        with patch.object(p,"_results_root",return_value=self.folder),patch.object(p,"_WRITE_ROOT",None),\
             patch.object(p,"_WRITE_GUARD_INSTALLED",False),patch.object(p.sys,"addaudithook",side_effect=hooks.append):
            p.install_write_guard(self.folder)
            self.assertEqual(len(hooks),1)
            hook = hooks[0]
            file = self.folder/"output.json"
            hook("open",(str(file),"w",os.O_WRONLY|os.O_CREAT))
            with self.assertRaises(p.ProvenanceError): hook("open",(str(self.folder.parent/"outside"),"w",os.O_WRONLY))
            for event in ("os.rename","os.link"):
                with self.subTest(event=event),self.assertRaises(p.ProvenanceError):
                    hook(event,("relative_source","relative_target",0,-1))
            with self.assertRaises(p.ProvenanceError): hook("os.symlink",("source","target",-1))
            with self.assertRaises(p.ProvenanceError): hook("subprocess.Popen",("not-executed",[],None,None))
            file.write_text("fixture",encoding="utf-8")
            second = self.folder/"linked.json"
            os.link(file,second)
            with self.assertRaises(p.ProvenanceError): hook("open",(str(file),"w",os.O_TRUNC|os.O_WRONLY))
            hook("os.remove",(str(second),-1))
            second.unlink()
            hook("open",(str(file),"w",os.O_TRUNC|os.O_WRONLY))
            with patch.object(p,"_descriptor_path",return_value=str(file)):
                hook("open",(123,"wb",os.O_WRONLY))
            with patch.object(p,"_descriptor_path",return_value=str(self.folder.parent/"outside")),self.assertRaises(p.ProvenanceError):
                hook("open",(123,"wb",os.O_WRONLY))

    def test_generator_call_guard_aliases_and_allowed_maintenance(self):
        repo = self.folder/"fixture_repo"
        repo.mkdir()
        traces = []
        with patch.object(p,"REPOSITORY",repo),patch.object(p,"_GENERATOR_REPO",None),\
             patch.object(p,"_GENERATOR_PROFILE",None),patch.object(p.sys,"setprofile",side_effect=traces.append),\
             patch.object(p.threading,"setprofile"):
            p.install_generator_guard(repo)
            trace = traces[0]
            def frame(name,filename):
                return types.SimpleNamespace(f_code=types.SimpleNamespace(co_name=name,co_filename=str(filename)))
            with self.assertRaises(p.ProvenanceError):
                trace(frame("generate_base_centers",repo/"core/data.py"),"call",None)
            with self.assertRaises(p.ProvenanceError):
                trace(frame("make_scenario_v2",repo/"core/p3_2_data.py"),"call",None)
            trace(frame("adapt",repo/"core/models.py"),"call",None)
            trace(frame("train_steps",repo/"core/models.py"),"call",None)
            trace(frame("generate_base_centers",self.folder/"not_original.py"),"call",None)

    def test_import_binding_accepts_exact_source_and_rejects_changes(self):
        repo = self.folder/"fixture_repo"
        executor = self.folder/"fixture_executor"
        repo.mkdir(); executor.mkdir()
        file = executor/"synthetic.py"
        file.write_text("pass\n",encoding="utf-8")
        manifest = {"paths":{"repo":str(repo),"executor_root":str(executor)},
                    "environment":{"bound_files_sha256":{}},"original_python_dependency_sha256":{},
                    "executor_sha256":{"synthetic.py":p.file_sha256(file)}}
        guard = p.ModelImportGuard(manifest)
        spec = types.SimpleNamespace(origin=str(file),submodule_search_locations=None)
        with patch.object(p.BuiltinImporter,"find_spec",return_value=None),\
             patch.object(p.FrozenImporter,"find_spec",return_value=None),\
             patch.object(p.PathFinder,"find_spec",return_value=spec):
            self.assertIs(guard.find_spec("synthetic"),spec)
            file.write_text("different = True\n",encoding="utf-8")
            with self.assertRaises(p.ProvenanceError): guard.find_spec("synthetic")
            spec.origin = str(self.folder/"unbound.py")
            (self.folder/"unbound.py").write_text("pass\n",encoding="utf-8")
            with self.assertRaises(p.ProvenanceError): guard.find_spec("synthetic")

    def test_adapter_pin_extraction_is_literal_and_read_only(self):
        file = self.folder/"science_adapter.py"
        digest = "a"*64
        file.write_text("SOURCE_PINS = {'artifacts/fake.pt': '"+digest+"'}\nraise RuntimeError('must not execute')\n",encoding="utf-8")
        before = file.read_bytes()
        self.assertEqual(p._adapter_source_pins(self.folder),{"artifacts/fake.pt":digest})
        self.assertEqual(before,file.read_bytes())
        file.write_text("SOURCE_PINS = dict(dynamic='not literal')\n",encoding="utf-8")
        with self.assertRaises((p.ProvenanceError,ValueError)): p._adapter_source_pins(self.folder)

    def test_manifest_byte_graph_and_scientific_sources_fail_closed(self):
        repo = self.folder/"fixture_repo"
        results,executor,run = repo/p.RESULTS_NAME,self.folder/"executor",self.folder/"input_run"
        results.mkdir(parents=True); executor.mkdir(); run.mkdir()
        (repo/"core").mkdir()
        source = repo/"core"/"fixture.py"
        source.write_text("pass\n",encoding="utf-8")
        (executor/"executor.py").write_text("pass\n",encoding="utf-8")
        authorization = results/"RESEARCHER_AUTHORIZATION_AND_STAGE_GATES.md"
        authorization.write_text("synthetic authorization fixture",encoding="utf-8")
        environment = {"synthetic":True}
        manifest = {"replication_id":p.REPLICATION_ID,"candidate_id":p.CANDIDATE_ID,"input_protocol":p.INPUT_PROTOCOL,
            "runtime_id":p.RUNTIME_ID,"model_environment_id":p.MODEL_ENVIRONMENT_ID,
            "paths":{"repo":str(repo),"input_run":str(run),"results_root":str(results),"executor_root":str(executor)},
            "critical_files_sha256":{"core/fixture.py":p.file_sha256(source)},
            "executor_sha256":{"executor.py":p.file_sha256(executor/"executor.py")},
            "environment":environment,"environment_binding":p.canonical_hash(environment),
            "authorization_record_sha256":p.file_sha256(authorization)}
        manifest["manifest_digest"] = p.canonical_hash(manifest)
        publication = results/"provenance_manifest.json"
        publication.write_text(json.dumps(manifest),encoding="utf-8")
        with patch.object(p,"REPOSITORY",repo),patch.object(p,"_verify_current_environment"):
            self.assertTrue(p.verify_frozen(manifest,verify_environment=False)["critical_scientific_bytes_unchanged"])
            source.write_text("changed = True\n",encoding="utf-8")
            with self.assertRaises(p.ProvenanceError): p.verify_frozen(manifest,verify_environment=False)
            source.write_text("pass\n",encoding="utf-8")
            (executor/"unbound.py").write_text("pass\n",encoding="utf-8")
            with self.assertRaises(p.ProvenanceError): p.verify_frozen(manifest,verify_environment=False)


if __name__=="__main__":
    unittest.main()
