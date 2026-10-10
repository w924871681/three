"""Synthetic metadata-only tests; no real Torch import, model or optimizer.

Fake ModuleType identities and code filenames are fixtures for the exact two
known source-created namespace records. They are never supplied to a project
model and do not replace any installed package in an experiment.
"""
from __future__ import annotations

import importlib.machinery
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import provenance as p


def synthetic_initializer(self):
    types.ModuleType.__init__(self,type(self)._fixture_name)
    if type(self)._fixture_name=="torch.ops": self.loaded_libraries=set()


class TorchGeneratedNamespaceSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"],prefix="namespace_")
        self.addCleanup(self.tmp.cleanup)
        self.site = Path(self.tmp.name)/"site"
        (self.site/"torch").mkdir(parents=True)
        self.paths = {name:self.site/"torch"/file for name,file in (
            ("torch","__init__.py"),("torch._ops","_ops.py"),("torch._classes","_classes.py"))}
        for name,path in self.paths.items(): path.write_text("# synthetic metadata fixture for "+name+"\n",encoding="utf-8")
        self.modules = {}
        for name,path in self.paths.items():
            module = types.ModuleType(name)
            module.__file__ = str(path)
            loader = importlib.machinery.SourceFileLoader(name,str(path))
            module.__spec__ = importlib.machinery.ModuleSpec(name,loader,origin=str(path))
            self.modules[name] = module
        self.modules["torch"].__version__ = p.EXPECTED_MODEL_VERSIONS["torch"]
        for name,owner_name,class_name,attribute,marker in (
                ("torch.ops","torch._ops","_Ops","ops","_ops.py"),
                ("torch.classes","torch._classes","_Classes","classes","_classes.py")):
            owner = self.modules[owner_name]
            owner.__dict__["types"] = types
            code = synthetic_initializer.__code__.replace(co_filename=str(self.paths[owner_name]),
                co_name="__init__",co_qualname=class_name+".__init__")
            initializer = types.FunctionType(code,owner.__dict__,"__init__")
            cls = type(class_name,(types.ModuleType,),{"__module__":owner_name,"__file__":marker,
                "__init__":initializer,"_fixture_name":name})
            owner.__dict__[class_name] = cls
            generated = cls()
            owner.__dict__[attribute] = generated
            self.modules["torch"].__dict__[attribute] = generated
            self.modules[name] = generated
        self.manifest = {"environment":{"site_packages_root":str(self.site)}}
        self.bound = {str(path).casefold():p.file_sha256(path) for path in self.paths.values()}
        self.patched = patch.dict(sys.modules,self.modules)
        self.patched.start(); self.addCleanup(self.patched.stop)

    def verify(self,name="torch.ops",module=None):
        return p._verify_torch_generated_namespace(name,self.modules[name] if module is None else module,
                                                   self.manifest,self.bound)

    def test_only_two_exact_source_created_namespaces_are_certified(self):
        self.assertTrue(self.verify("torch.ops"))
        self.assertTrue(self.verify("torch.classes"))
        unknown = types.ModuleType("unbound.ops")
        unknown.__file__ = "_ops.py"
        self.assertFalse(p._verify_torch_generated_namespace("unbound.ops",unknown,self.manifest,self.bound))

    def test_wrong_class_owner_alias_marker_or_generated_spec_is_rejected(self):
        fake = types.ModuleType("torch.ops")
        fake.__file__ = "_ops.py"
        with self.assertRaises(p.ProvenanceError): self.verify(module=fake)
        actual = self.modules["torch.ops"]
        actual.__file__ = "_different.py"
        with self.assertRaises(p.ProvenanceError): self.verify()
        del actual.__file__
        actual.__spec__ = types.SimpleNamespace(origin="unbound")
        with self.assertRaises(p.ProvenanceError): self.verify()
        actual.__spec__ = None
        self.modules["torch"].ops = fake
        with self.assertRaises(p.ProvenanceError): self.verify()
        self.modules["torch"].ops = actual
        sys.modules["torch.ops"] = fake
        with self.assertRaises(p.ProvenanceError): self.verify()

    def test_creator_source_bytes_and_constructor_code_origin_are_fresh(self):
        actual = self.modules["torch.ops"]
        initializer = type(actual).__dict__["__init__"]
        old = initializer.__code__
        initializer.__code__ = old.replace(co_filename=str(self.paths["torch"]))
        with self.assertRaises(p.ProvenanceError): self.verify()
        initializer.__code__ = old
        self.paths["torch._ops"].write_text("changed creator source\n",encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): self.verify()

    def test_generated_namespace_does_not_authorize_unbound_native_libraries(self):
        library = self.site/"native_fixture.dll"
        library.write_bytes(b"synthetic-non-executable-library")
        self.modules["torch.ops"].loaded_libraries.add(str(library))
        with self.assertRaises(p.ProvenanceError): self.verify()
        self.bound[str(library).casefold()] = p.file_sha256(library)
        self.assertTrue(self.verify())
        library.write_bytes(b"changed synthetic library")
        with self.assertRaises(p.ProvenanceError): self.verify()


if __name__=="__main__": unittest.main()
