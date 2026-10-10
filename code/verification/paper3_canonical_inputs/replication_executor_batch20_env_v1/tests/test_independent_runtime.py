"""Independent-layout synthetic tests; never import a model or package installer."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import provenance as p


class IndependentRuntimeSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"], prefix="runtime_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix, self.base = self.root / "independent_venv", self.root / "base_read_only"
        (self.prefix / "Scripts").mkdir(parents=True)
        (self.prefix / "Lib" / "site-packages").mkdir(parents=True)
        (self.base / "Lib").mkdir(parents=True)
        (self.prefix / "Scripts" / "python.exe").write_bytes(b"synthetic-only-not-executable")
        self.cfg = self.prefix / "pyvenv.cfg"
        self.cfg.write_text(f"home = {self.base}\ninclude-system-site-packages = false\nversion = 3.11.15\n", encoding="utf-8")
        self.evidence = self.root / "install_receipt.json"
        self.evidence.write_text('{"synthetic_only":true}\n', encoding="utf-8")
        self.descriptor = {"schema":"paper3-reviewed-independent-model-runtime-v1",
            "environment_id":p.MODEL_ENVIRONMENT_ID,"prefix":str(self.prefix),"base_prefix":str(self.base),
            "python_executable":str(self.prefix / "Scripts" / "python.exe"),
            "site_packages_root":str(self.prefix / "Lib" / "site-packages"),
            "stdlib_root":str(self.base / "Lib"),"expected_versions":dict(p.EXPECTED_MODEL_VERSIONS),
            "installation_evidence_files_sha256":{str(self.evidence):p.file_sha256(self.evidence)}}

    def test_independent_layout_keeps_input_environment_outside_runtime_descriptor(self):
        before = copy.deepcopy(self.descriptor)
        paths, cfg, values = p._runtime_layout(self.descriptor)
        self.assertEqual(paths["prefix"], self.prefix)
        self.assertEqual(paths["base_prefix"], self.base)
        self.assertEqual(paths["site_packages_root"], self.prefix / "Lib" / "site-packages")
        self.assertEqual(cfg, self.cfg)
        self.assertEqual(values["include-system-site-packages"], "false")
        self.assertEqual(self.descriptor, before)

    def test_shared_site_and_wrong_base_are_rejected(self):
        self.cfg.write_text(f"home = {self.base}\ninclude-system-site-packages = true\n",encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(self.descriptor)
        self.cfg.write_text(f"home = {self.prefix}\ninclude-system-site-packages = false\n",encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(self.descriptor)

    def test_every_key_scientific_version_pin_is_exact(self):
        for name in p.EXPECTED_MODEL_VERSIONS:
            with self.subTest(name=name):
                changed = copy.deepcopy(self.descriptor)
                changed["expected_versions"][name] = "unauthorized-version"
                with self.assertRaises(p.ProvenanceError): p._runtime_layout(changed)
        self.assertEqual(self.descriptor["expected_versions"]["pandas"], "2.3.3")
        self.assertEqual(self.descriptor["expected_versions"]["river"], "0.23.0")

    def test_model_environment_identity_and_site_path_cannot_be_switched(self):
        for name,value in (("environment_id","HISTORICAL_ENV"),("site_packages_root",str(self.base / "Lib"))):
            with self.subTest(name=name):
                changed = copy.deepcopy(self.descriptor)
                changed[name] = value
                with self.assertRaises(p.ProvenanceError): p._runtime_layout(changed)

    def test_installation_evidence_is_required_and_byte_bound(self):
        missing = copy.deepcopy(self.descriptor)
        missing["installation_evidence_files_sha256"] = {}
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(missing)
        layout = self.root/"layout.json"
        layout.write_text(json.dumps({"environment_id":p.MODEL_ENVIRONMENT_ID}),encoding="utf-8")
        optional = copy.deepcopy(self.descriptor)
        optional["layout_evidence_path"] = str(layout)
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(optional)
        optional["installation_evidence_files_sha256"][str(layout)] = p.file_sha256(layout)
        p._runtime_layout(optional)
        self.evidence.write_bytes(b"changed")
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(self.descriptor)

    def test_reviewed_descriptor_source_object_and_bytes_cannot_change(self):
        path = self.root / "reviewed_descriptor.json"
        path.write_text(json.dumps(self.descriptor),encoding="utf-8")
        augmented = copy.deepcopy(self.descriptor)
        augmented.update(descriptor_source_file=str(path),descriptor_source_sha256=p.file_sha256(path))
        p._runtime_layout(augmented)
        changed = copy.deepcopy(augmented)
        changed["claimed_historical_environment_reproduced"] = True
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(changed)
        path.write_text(json.dumps({**self.descriptor,"new_claim":True}),encoding="utf-8")
        with self.assertRaises(p.ProvenanceError): p._runtime_layout(augmented)

    def test_distribution_names_are_canonicalized_without_relaxing_versions(self):
        actual = p._normalized_versions({"Jinja2":"3.1.6","MarkupSafe":"3.0.3","typing_extensions":"4.16.0"})
        self.assertEqual(actual,{"jinja2":"3.1.6","markupsafe":"3.0.3","typing-extensions":"4.16.0"})
        for values in ({"NumPy":"2.4.6","numpy":"2.4.6"},{"invalid/name":"1"},{"numpy":None}):
            with self.subTest(values=values),self.assertRaises(p.ProvenanceError): p._normalized_versions(values)


if __name__ == "__main__": unittest.main()
