"""Synthetic phase/default provenance; no real scientific package imports."""
from __future__ import annotations

import copy
import hashlib
import os
import sys
import types
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import provenance as p

REAL_GUARDS=p._scientific_import_phase_guards
REAL_WRITER=p._scientific_import_writer
REAL_LOADED=p._loaded_sklearn_initializer


class ScientificImportTransitionSyntheticTests(unittest.TestCase):
    def setUp(self):
        for name,value in (("_SCIENTIFIC_IMPORT_PENDING",None),("_SCIENTIFIC_IMPORT_POST",None),
                           ("_SCIENTIFIC_IMPORT_OBSERVER_INSTALLED",False)):
            self.enterContext(patch.object(p,name,value))
        self.current={name:None for name in p.MODEL_RUNTIME_ENV}
        environment={"model_runtime_environment":dict(self.current),
                     "model_runtime_environment_digest":p.canonical_hash(self.current)}
        self.manifest={"manifest_digest":"a"*64,"environment":environment,"paths":{"results_root":"synthetic"}}
        self.source={"path":str(Path(__file__)),"sha256":p.SKLEARN_DEFAULTS_SOURCE_SHA256,
                     "code":compile("pass\n",str(Path(__file__)),"exec",dont_inherit=True)}
        self.source["code_digest"]=hashlib.sha256(p.marshal.dumps(self.source["code"])).hexdigest()
        self.threadpool_source={"path":str(Path(__file__))+".threadpool_fixture",
            "sha256":p.THREADPOOL_DEFAULTS_SOURCE_SHA256,
            "code":compile("pass\n",str(Path(__file__))+".threadpool_fixture","exec",dont_inherit=True)}
        self.threadpool_source["code_digest"]=hashlib.sha256(p.marshal.dumps(self.threadpool_source["code"])).hexdigest()
        self.hooks=[]
        self.enterContext(patch.object(p,"_model_runtime_environment",side_effect=lambda:dict(self.current)))
        self.enterContext(patch.object(p,"_scientific_import_phase_guards",return_value=None))
        self.enterContext(patch.object(p,"_sklearn_import_source",return_value=self.source))
        self.enterContext(patch.object(p,"_threadpool_import_source",return_value=self.threadpool_source))
        self.enterContext(patch.object(p,"file_sha256",side_effect=lambda path:
            p.THREADPOOL_DEFAULTS_SOURCE_SHA256 if str(path)==self.threadpool_source["path"] else p.SKLEARN_DEFAULTS_SOURCE_SHA256))
        self.enterContext(patch.object(p,"_loaded_sklearn_initializer",return_value=42))
        self.enterContext(patch.object(p,"_loaded_threadpool_initializer",return_value=43))
        self.enterContext(patch.object(p,"_scientific_import_writer",side_effect=lambda pending,name:p.SKLEARN_IMPORT_DEFAULTS[name][1]))
        self.enterContext(patch.object(p.sys,"addaudithook",side_effect=self.hooks.append))

    def begin(self):return p.begin_scientific_import_transition(self.manifest)

    def events(self):
        observer=self.hooks[0]
        observer("exec",(self.source["code"],))
        for name,(value,line) in p.SKLEARN_IMPORT_DEFAULTS.items():
            if self.current[name] is None:
                observer("os.putenv",(name.encode(),value.encode()))
                self.current[name]=value

    def complete(self):
        token=self.begin();self.events()
        return p.complete_scientific_import_transition(self.manifest,token)

    def test_metadata_only_phase_is_strict_raw_and_never_imports_package(self):
        p._verify_model_runtime_environment(self.manifest["environment"])
        self.assertEqual(self.hooks,[])
        self.current["KMP_DUPLICATE_LIB_OK"]="True"
        with self.assertRaises(p.ProvenanceError):p._verify_model_runtime_environment(self.manifest["environment"])
        self.assertIsNone(p._SCIENTIFIC_IMPORT_POST)

    def test_exact_two_observed_defaults_create_sealed_post_without_verifier_mutation(self):
        proof=self.complete()
        self.assertEqual(set(proof["observed_writer_events"]),set(p.SKLEARN_IMPORT_DEFAULTS))
        self.assertEqual(proof["raw_runtime_variables"],self.manifest["environment"]["model_runtime_environment"])
        self.assertEqual(proof["post_import_runtime_variables"],self.current)
        self.assertFalse(proof["verifier_set_environment_variables"])
        self.assertFalse(proof["numerical_neutrality_claimed"])
        self.assertFalse(proof["historical_environment_reproduced"])
        p._verify_model_runtime_environment(self.manifest["environment"])
        proof["post_import_runtime_variables"]["CUDA_VISIBLE_DEVICES"]="spoof"
        p._verify_model_runtime_environment(self.manifest["environment"])

    def test_no_token_no_initializer_and_module_key_alone_cannot_certify(self):
        token=self.begin()
        with self.assertRaises(p.ProvenanceError):p.complete_scientific_import_transition(self.manifest,object())
        with self.assertRaises(p.ProvenanceError):p.complete_scientific_import_transition(self.manifest,token)
        p._SCIENTIFIC_IMPORT_PENDING=None
        with patch.dict(p.sys.modules,{"sklearn":types.ModuleType("sklearn")}):
            with self.assertRaises(p.ProvenanceError):self.begin()

    def test_missing_guards_or_nonraw_launch_fail_before_boundary(self):
        with patch.object(p,"_scientific_import_phase_guards",side_effect=lambda manifest:REAL_GUARDS(manifest)),\
             patch.object(p,"_WRITE_GUARD_INSTALLED",False):
            with self.assertRaises(p.ProvenanceError):self.begin()
        self.current["KMP_INIT_AT_FORK"]="FALSE"
        with self.assertRaises(p.ProvenanceError):self.begin()

    def test_post_phase_rejects_raw_rollback_and_every_other_variable_change(self):
        self.complete();correct=dict(self.current)
        for name in p.MODEL_RUNTIME_ENV:
            self.current[name]=None if name in p.SKLEARN_IMPORT_DEFAULTS else "tampered"
            with self.subTest(name=name),self.assertRaises(p.ProvenanceError):
                p._verify_model_runtime_environment(self.manifest["environment"])
            self.current=dict(correct)

    def test_mutation_without_bound_writer_wrong_value_or_duplicate_is_rejected(self):
        token=self.begin();observer=self.hooks[0]
        observer("exec",(self.source["code"],))
        for event,args in (("os.putenv",(b"OMP_NUM_THREADS",b"2")),
                           ("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"TRUE")),
                           ("os.unsetenv",(b"KMP_DUPLICATE_LIB_OK",))):
            with self.subTest(event=event,args=args),self.assertRaises(p.ProvenanceError):observer(event,args)
        with patch.object(p,"_scientific_import_writer",side_effect=p.ProvenanceError("unbound writer")):
            with self.assertRaises(p.ProvenanceError):observer("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True"))
        observer("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True"));self.current["KMP_DUPLICATE_LIB_OK"]="True"
        with self.assertRaises(p.ProvenanceError):observer("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True"))

    def test_source_exec_spoof_and_duplicate_initializer_are_rejected(self):
        self.begin();observer=self.hooks[0]
        spoof=compile("different=1\n",self.source["path"],"exec",dont_inherit=True)
        with self.assertRaises(p.ProvenanceError):observer("exec",(spoof,))
        observer("exec",(self.source["code"],))
        with self.assertRaises(p.ProvenanceError):observer("exec",(self.source["code"],))

    def test_token_pid_manifest_and_environment_cannot_change(self):
        token=self.begin();self.events()
        with patch.object(p.os,"getpid",return_value=os.getpid()+1):
            with self.assertRaises(p.ProvenanceError):p.complete_scientific_import_transition(self.manifest,token)
        for change in ("manifest","environment"):
            wrong=copy.deepcopy(self.manifest)
            if change=="manifest":wrong["manifest_digest"]="b"*64
            else:wrong["environment"]["extra"]="unbound"
            with self.subTest(change=change),self.assertRaises(p.ProvenanceError):p.complete_scientific_import_transition(wrong,token)

    def test_post_seal_pid_manifest_source_or_module_identity_tampering_rejected(self):
        self.complete();original=p._SCIENTIFIC_IMPORT_POST
        for replacement in ((os.getpid()+1,original[1],original[2]),
                            (os.getpid(),dict(original[1]),original[2]),
                            (os.getpid(),original[1],"f"*64)):
            p._SCIENTIFIC_IMPORT_POST=replacement
            with self.subTest(value=replacement),self.assertRaises(p.ProvenanceError):p._verify_model_runtime_environment(self.manifest["environment"])
        p._SCIENTIFIC_IMPORT_POST=original
        with self.assertRaises(p.ProvenanceError):p._verified_scientific_import_post(self.manifest["environment"],"b"*64)
        with patch.object(p,"_loaded_sklearn_initializer",return_value=43):
            with self.assertRaises(p.ProvenanceError):p._verify_model_runtime_environment(self.manifest["environment"])

    def test_post_phase_cannot_be_reentered_reloaded_or_mutated(self):
        self.complete()
        with self.assertRaises(p.ProvenanceError):self.begin()
        for event,args in (("exec",(self.source["code"],)),("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True")),
                           ("os.unsetenv",(b"KMP_INIT_AT_FORK",))):
            with self.subTest(event=event),self.assertRaises(p.ProvenanceError):self.hooks[0](event,args)

    def test_existing_launch_values_are_preserved_by_setdefault_not_replaced(self):
        self.current["KMP_INIT_AT_FORK"]="pre-existing-frozen-value"
        self.manifest["environment"]["model_runtime_environment"]=dict(self.current)
        self.manifest["environment"]["model_runtime_environment_digest"]=p.canonical_hash(self.current)
        proof=self.complete()
        self.assertEqual(proof["post_import_runtime_variables"]["KMP_INIT_AT_FORK"],"pre-existing-frozen-value")
        self.assertEqual(set(proof["observed_writer_events"]),{"KMP_DUPLICATE_LIB_OK"})

    def test_exact_writer_helper_checks_code_line_path_and_single_frame(self):
        frame=types.SimpleNamespace(f_code=self.source["code"],f_lineno=56,f_back=None)
        with patch.object(p.sys,"_getframe",return_value=frame):
            self.assertEqual(REAL_WRITER({"source":self.source},"KMP_DUPLICATE_LIB_OK"),56)
        invalid=(types.SimpleNamespace(f_code=self.source["code"],f_lineno=57,f_back=None),
                 types.SimpleNamespace(f_code=compile("wrong=1",self.source["path"],"exec"),f_lineno=56,f_back=None),
                 types.SimpleNamespace(f_code=compile("pass","unbound.py","exec"),f_lineno=56,f_back=None),
                 types.SimpleNamespace(f_code=self.source["code"],f_lineno=56,f_back=frame))
        for bad in invalid:
            with self.subTest(frame=bad),patch.object(p.sys,"_getframe",return_value=bad),self.assertRaises(p.ProvenanceError):
                REAL_WRITER({"source":self.source},"KMP_DUPLICATE_LIB_OK")

    def test_loaded_module_key_requires_exact_origin_version_and_file_bytes(self):
        module=types.ModuleType("sklearn");module.__file__=self.source["path"]
        module.__version__=p.EXPECTED_MODEL_VERSIONS["scikit-learn"]
        module.__spec__=types.SimpleNamespace(name="sklearn",origin=self.source["path"])
        with patch.dict(p.sys.modules,{"sklearn":module}):
            self.assertEqual(REAL_LOADED(self.source),id(module))
            module.__version__="wrong"
            with self.assertRaises(p.ProvenanceError):REAL_LOADED(self.source)
            module.__version__=p.EXPECTED_MODEL_VERSIONS["scikit-learn"]
            module.__spec__.origin="unbound.py"
            with self.assertRaises((p.ProvenanceError,FileNotFoundError)):REAL_LOADED(self.source)

    def test_threadpool_first_writer_before_sklearn_exec_has_exact_source_proof(self):
        token=self.begin();observer=self.hooks[0]
        with patch.object(p,"_scientific_import_writer",return_value=48):
            observer("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True"))
        self.current["KMP_DUPLICATE_LIB_OK"]="True"
        observer("exec",(self.source["code"],))
        observer("os.putenv",(b"KMP_INIT_AT_FORK",b"FALSE"));self.current["KMP_INIT_AT_FORK"]="FALSE"
        proof=p.complete_scientific_import_transition(self.manifest,token)
        self.assertEqual(proof["observed_writer_events"]["KMP_DUPLICATE_LIB_OK"],{"value":"True","line":48})
        self.assertEqual(proof["observed_writer_sources"]["KMP_DUPLICATE_LIB_OK"],
            {"path":self.threadpool_source["path"],"sha256":p.THREADPOOL_DEFAULTS_SOURCE_SHA256})
        self.assertEqual(proof["threadpool_module_object_id"],43)
        with patch.object(p,"_loaded_threadpool_initializer",return_value=44),self.assertRaises(p.ProvenanceError):
            p._verify_model_runtime_environment(self.manifest["environment"])

    def test_sklearn_writer_cannot_precede_its_observed_initializer(self):
        self.begin()
        with self.assertRaises(p.ProvenanceError):self.hooks[0]("os.putenv",(b"KMP_DUPLICATE_LIB_OK",b"True"))

    def test_threadpool_writer_helper_rejects_wrong_code_line_and_wrong_variable(self):
        pending={"source":self.source,"threadpool_source":self.threadpool_source}
        frame=types.SimpleNamespace(f_code=self.threadpool_source["code"],f_lineno=48,f_back=None)
        with patch.object(p.sys,"_getframe",return_value=frame):
            self.assertEqual(REAL_WRITER(pending,"KMP_DUPLICATE_LIB_OK"),48)
            with self.assertRaises(p.ProvenanceError):REAL_WRITER(pending,"KMP_INIT_AT_FORK")
        for bad in (types.SimpleNamespace(f_code=self.threadpool_source["code"],f_lineno=49,f_back=None),
                    types.SimpleNamespace(f_code=compile("wrong=1",self.threadpool_source["path"],"exec"),f_lineno=48,f_back=None)):
            with patch.object(p.sys,"_getframe",return_value=bad),self.assertRaises(p.ProvenanceError):
                REAL_WRITER(pending,"KMP_DUPLICATE_LIB_OK")


if __name__=="__main__":unittest.main()
