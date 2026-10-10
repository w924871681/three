"""Metadata-only regression for Windows pre-guard platform queries."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import provenance as p


class PlatformBootstrapSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap = patch.object(p,"_PLATFORM_BOOTSTRAP",None)
        self.guard = patch.object(p,"_WRITE_GUARD_INSTALLED",False)
        self.bootstrap.start();self.addCleanup(self.bootstrap.stop)
        self.guard.start();self.addCleanup(self.guard.stop)

    def metadata(self):
        return patch.multiple(p.platform,platform=lambda:"Windows-SYNTHETIC-EXACT",
                              machine=lambda:"SYNTHETIC_MACHINE",processor=lambda:"SYNTHETIC_PROCESSOR")

    def test_same_stdlib_values_are_retained_in_an_immutable_process_cache(self):
        with self.metadata():
            first=p.bootstrap_platform_metadata()
        self.assertEqual(dict(first),{"platform":"Windows-SYNTHETIC-EXACT","machine":"SYNTHETIC_MACHINE","processor":"SYNTHETIC_PROCESSOR"})
        self.assertIs(type(first),MappingProxyType)
        with self.assertRaises(TypeError):first["platform"]="changed"
        self.assertIs(p.bootstrap_platform_metadata(),first)

    def test_cached_metadata_does_not_requery_os_after_guard_installation(self):
        with self.metadata():expected=p.bootstrap_platform_metadata()
        p._WRITE_GUARD_INSTALLED=True
        with patch.object(p.platform,"platform",side_effect=RuntimeError("query forbidden")),\
             patch.object(p.platform,"machine",side_effect=RuntimeError("query forbidden")),\
             patch.object(p.platform,"processor",side_effect=RuntimeError("query forbidden")):
            self.assertIs(p.bootstrap_platform_metadata(),expected)

    def test_missing_cache_after_guard_fails_closed_without_subprocess_or_query(self):
        p._WRITE_GUARD_INSTALLED=True
        with patch.object(p.platform,"platform") as query,self.assertRaises(p.ProvenanceError):
            p.bootstrap_platform_metadata()
        query.assert_not_called()

    def test_cache_rejects_wrong_process_mutable_values_or_changed_digest(self):
        with self.metadata():p.bootstrap_platform_metadata()
        original=p._PLATFORM_BOOTSTRAP
        for replacement in ((os.getpid()+1,original[1],original[2]),
                            (os.getpid(),dict(original[1]),original[2]),
                            (os.getpid(),original[1],"0"*64)):
            p._PLATFORM_BOOTSTRAP=replacement
            with self.subTest(value=replacement),self.assertRaises(p.ProvenanceError):p.bootstrap_platform_metadata()
        p._PLATFORM_BOOTSTRAP=original

    def test_write_guard_bootstraps_before_hook_and_keeps_subprocess_prohibition(self):
        with tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"]) as folder:
            hooks=[]
            def install(hook):
                self.assertFalse(p._WRITE_GUARD_INSTALLED)
                self.assertIsNotNone(p._PLATFORM_BOOTSTRAP)
                hooks.append(hook)
            with self.metadata(),patch.object(p,"_results_root",return_value=Path(folder)),\
                 patch.object(p,"_WRITE_ROOT",None),patch.object(p.sys,"addaudithook",side_effect=install):
                p.install_write_guard(folder)
                self.assertTrue(p._WRITE_GUARD_INSTALLED)
                for event in ("subprocess.Popen","os.system","os.exec","os.posix_spawn"):
                    with self.subTest(event=event),self.assertRaises(p.ProvenanceError):hooks[0](event,("synthetic-not-executed",))

    def test_invalid_stdlib_metadata_is_not_cached_as_success(self):
        with self.metadata(),patch.object(p.platform,"platform",return_value=None),self.assertRaises(p.ProvenanceError):p.bootstrap_platform_metadata()
        self.assertIsNone(p._PLATFORM_BOOTSTRAP)

    def test_capture_retains_platform_after_real_distribution_metadata_loop(self):
        """Complete capture return reads synthetic METADATA files, no packages."""
        with tempfile.TemporaryDirectory(dir=os.environ["PAPER3_SYNTHETIC_TEMP_ROOT"]) as folder:
            root=Path(folder)
            base=root/"base";prefix=root/"independent_venv"
            stdlib=base/"Lib";site=prefix/"Lib"/"site-packages"
            scripts=prefix/"Scripts"
            for directory in (stdlib,site,scripts):directory.mkdir(parents=True,exist_ok=True)
            executable=scripts/"python.exe";executable.write_bytes(b"synthetic-not-executable")
            pyvenv=prefix/"pyvenv.cfg";pyvenv.write_text("include-system-site-packages = false\n",encoding="utf-8")
            expected=dict(p.EXPECTED_MODEL_VERSIONS)
            metadata_paths={}
            for name,version in expected.items():
                distribution=site/(name.replace("-","_")+"-"+version+".dist-info")
                distribution.mkdir()
                metadata=distribution/"METADATA"
                metadata.write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",encoding="utf-8")
                metadata_paths[name]=metadata
            environment={"python_version":p.platform.python_version(),"byteorder":p.sys.byteorder,
                "platform":"Windows-SYNTHETIC-EXACT",
                "hardware":{"machine":"SYNTHETIC_MACHINE","processor":"SYNTHETIC_PROCESSOR",
                            "processor_identifier":os.environ.get("PROCESSOR_IDENTIFIER")},
                "thread_environment":{name:os.environ.get(name) for name in p.THREAD_ENV},
                "numpy_files_sha256":{},"stdlib_root":str(stdlib)}
            paths={"python_executable":executable,"base_prefix":base,"prefix":prefix,
                   "site_packages_root":site,"stdlib_root":stdlib}
            descriptor={"expected_versions":expected,"fixture":"metadata-only-independent-runtime"}
            progress=[]
            with self.metadata(),patch.object(p,"_runtime_layout",return_value=(paths,pyvenv,{"include-system-site-packages":"false"})),\
                 patch.object(p.sys,"executable",str(executable)),patch.object(p.sys,"base_prefix",str(base)),\
                 patch.object(p.sys,"pycache_prefix",str(root/"never_created_pycache")):
                captured=p.capture_model_environment(environment,descriptor,progress=progress.append)
            self.assertEqual(captured["platform"],"Windows-SYNTHETIC-EXACT")
            self.assertEqual(captured["hardware"],environment["hardware"])
            self.assertEqual(captured["exact_versions"],expected)
            self.assertEqual(len(captured["distributions"]),len(expected))
            self.assertEqual(captured["input_environment"],environment)
            self.assertFalse(captured["packages_imported_during_capture"])
            self.assertFalse(captured["historical_environment_reproduced"])
            self.assertTrue(progress)
            for name,metadata in metadata_paths.items():
                distribution=captured["distributions"][metadata.parent.name]
                self.assertEqual(distribution["name"],name)
                self.assertEqual(distribution["metadata_sha256"],p.file_sha256(metadata))
                self.assertEqual(captured["bound_files_sha256"][str(metadata)],p.file_sha256(metadata))


if __name__=="__main__":unittest.main()
