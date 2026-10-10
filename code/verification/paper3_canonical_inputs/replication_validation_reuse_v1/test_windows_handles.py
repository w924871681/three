"""Actual native operations restricted to fresh NEW-directory fixture files."""
import ctypes
from ctypes import wintypes as w
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from session import ReuseError, TreeSpec, ValidationSession
from windows_handles import NativeHandleError, WindowsReadBackend


FIXTURE_PARENT = None  # Set by the independent runner, never a production path.
NATIVE_OBSERVATIONS = []


@unittest.skipUnless(os.name == "nt", "Windows native fixture requires Windows")
class WindowsFixtureTests(unittest.TestCase):
    def setUp(self):
        parent = Path(FIXTURE_PARENT) if FIXTURE_PARENT else None
        if parent is None or not parent.resolve().is_relative_to(Path(__file__).resolve().parent / "synthetic_tests"):
            raise RuntimeError("native fixtures require an exclusive NEW test-record directory")
        self.temp = tempfile.TemporaryDirectory(prefix="native_fixture_", dir=parent)
        self.root = Path(self.temp.name)
        self.path = self.root / "fixed.bin"
        self.path.write_bytes(b"0123456789abcdef")
        self.backend = WindowsReadBackend()
        self.handles = []

    def tearDown(self):
        for handle in list(self.backend._owned):
            self.backend.close(handle)
        self.temp.cleanup()

    def retained(self):
        return self.backend.open_read(self.path, directory=False)

    def denied(self, label, callback):
        try:
            result = callback()
        except OSError as error:
            # CPython's CRT-backed open reports errno=EACCES without winerror;
            # native CreateFile probes below independently capture exact 32.
            if error.winerror is None:
                self.assertEqual(error.errno, 13)
            else:
                self.assertIn(error.winerror, (5, 32, 33))
            NATIVE_OBSERVATIONS.append({"check": label, "actual_denied": True,
                "winerror": error.winerror, "errno": error.errno})
        else:
            if hasattr(result, "close"): result.close()
            self.fail(label + " unexpectedly succeeded")

    def native_write_denied(self, path):
        handle = self.backend.k.CreateFileW(str(path), 0x40000000, 7, None, 3, 0x80, None)
        if handle != ctypes.c_void_p(-1).value and handle is not None:
            self.backend.k.CloseHandle(handle)
            self.fail("native GENERIC_WRITE unexpectedly admitted")
        error = ctypes.get_last_error()
        self.assertEqual(error, 32)
        NATIVE_OBSERVATIONS.append({"check": "native CreateFileW GENERIC_WRITE " + Path(path).name,
            "actual_denied": True, "winerror": error})

    def test_actual_write_delete_rename_block_and_release(self):
        handle = self.retained()
        self.native_write_denied(self.path)
        self.denied("ordinary write open", lambda: self.path.open("wb"))
        self.denied("ordinary delete", self.path.unlink)
        self.denied("ordinary rename", lambda: self.path.rename(self.root / "renamed.bin"))
        self.assertEqual(self.path.read_bytes(), b"0123456789abcdef")
        self.backend.close(handle)
        self.path.write_bytes(b"after release")
        self.path.rename(self.root / "released.bin")
        (self.root / "released.bin").unlink()
        NATIVE_OBSERVATIONS.append({"check": "write rename delete after close", "actual_allowed": True})

    def test_actual_hardlink_alias_write_blocked(self):
        alias = self.root / "alias.bin"
        os.link(self.path, alias)
        self.retained()
        self.native_write_denied(alias)
        self.denied("hardlink alias write", lambda: alias.open("wb"))
        self.assertEqual(alias.read_bytes(), b"0123456789abcdef")
        spec = TreeSpec(str(self.root), {"fixed.bin": "file", "alias.bin": "file"})
        before = self.backend.inventory(spec)
        # An unretained extra hardlink name can be removed without deleting the
        # held primary name or its bytes. This is NOT a universal name lock.
        alias.unlink()
        self.assertEqual(self.path.read_bytes(), b"0123456789abcdef")
        self.assertNotEqual(self.backend.inventory(spec), before)
        NATIVE_OBSERVATIONS.append({"check": "unretained extra hardlink name delete",
            "actual_allowed": True, "primary_bytes_preserved": True, "fresh_inventory_detected_removal": True})
        os.link(self.path, alias)
        alias_handle = self.backend.open_read(alias, directory=False)
        self.denied("separately retained hardlink name delete", alias.unlink)
        self.backend.close(alias_handle)

    def test_actual_handle_noninherit_and_stable_file_id(self):
        first = self.retained(); second = self.retained()
        a, b = self.backend.identity(first), self.backend.identity(second)
        self.assertEqual(a, b)
        self.assertTrue(a["noninheritable"]); self.assertTrue(a["local_NTFS_verified"])
        self.assertEqual(len(a["file_id_128"]), 32)
        self.assertTrue(a["volume_guid_path"].startswith("\\\\?\\volume{"))
        NATIVE_OBSERVATIONS.append({"check": "native FILE_ID128 volumeGUID noninherit NTFS", "actual_pass": True})

    def test_actual_directory_addition_detected_by_inventory(self):
        spec = TreeSpec(str(self.root), {"fixed.bin": "file"})
        handle = self.backend.open_read(self.root, directory=True)
        before = self.backend.inventory(spec)
        (self.root / "new.bin").write_bytes(b"new fixture")
        self.assertNotEqual(self.backend.inventory(spec), before)
        self.backend.close(handle)
        NATIVE_OBSERVATIONS.append({"check": "new child permitted but fresh inventory detects", "actual_pass": True})

    def fixture_session(self):
        inputs = self.root / "inputs"; inputs.mkdir()
        data = inputs / "input.bin"; data.write_bytes(b"fixed fixture input")
        source = inputs / "verifier.py"; source.write_bytes(b"synthetic verifier only")
        bindings = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (data, source)}
        manifest = "f" * 64
        full = lambda: {"manifest_digest": manifest, "critical_scientific_bytes_unchanged": True,
            "environment_file_bytes_checked": True, "original_full_snapshot_checked": True, "all_F1_inputs_checked": True}
        runtime = lambda: {"manifest_digest": manifest, "runtime_semantics_checked": True}
        session = ValidationSession(bindings=bindings,
            trees=[TreeSpec(str(inputs), {"input.bin": "file", "verifier.py": "file"})],
            manifest_digest=manifest, verifier_sources={str(source): bindings[str(source)]},
            original_full_verify=full, runtime_verify=runtime, backend=self.backend,
            accept_documented_native_limitations=True)
        return session, data

    def test_actual_unrelated_sibling_output_with_all_ancestors_retained(self):
        session, data = self.fixture_session()
        with session:
            output = self.root / "output.json"
            with session.publication_guard(output_paths=[str(output)]):
                output.write_bytes(b"new fixture metadata only")
            self.assertEqual(session.state, "SEALED")
        NATIVE_OBSERVATIONS.append({"check": "full session sibling output under retained ancestors",
            "actual_pass": True, "synthetic_full_callbacks": 2, "production_verifier_called": False})

    def test_actual_output_hardlink_alias_blocked(self):
        session, data = self.fixture_session()
        alias = self.root / "output_alias.bin"; os.link(data, alias)
        with session:
            with self.assertRaises(ReuseError):
                with session.publication_guard(output_paths=[str(alias)]): self.fail("alias publication allowed")
        NATIVE_OBSERVATIONS.append({"check": "existing output hardlink FILE_ID alias", "actual_publication_denied": True})

    def mapping(self, protection, access, file_access):
        k = self.backend.k
        k.CreateFileMappingW.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR]
        k.CreateFileMappingW.restype = w.HANDLE
        k.MapViewOfFile.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t]
        k.MapViewOfFile.restype = ctypes.c_void_p
        k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k.UnmapViewOfFile.restype = w.BOOL
        file = k.CreateFileW(str(self.path), file_access, 7, None, 3, 0x80, None)
        self.assertNotEqual(file, ctypes.c_void_p(-1).value)
        mapping = view = None
        try:
            mapping = k.CreateFileMappingW(file, None, protection, 0, 0, None)
            self.assertTrue(mapping, str(ctypes.WinError(ctypes.get_last_error())))
            view = k.MapViewOfFile(mapping, access, 0, 0, 0)
            self.assertTrue(view, str(ctypes.WinError(ctypes.get_last_error())))
        except BaseException:
            if view: k.UnmapViewOfFile(view)
            if mapping: k.CloseHandle(mapping)
            raise
        finally:
            # Critical case: a write mapping survives closure of its file handle.
            self.assertTrue(k.CloseHandle(file))
        return mapping, view

    def test_actual_preexisting_write_mapping_blocks_admission(self):
        mapping, view = self.mapping(4, 2, 0xC0000000)  # PAGE_READWRITE, FILE_MAP_WRITE
        try:
            with self.assertRaises(NativeHandleError): self.retained()
            NATIVE_OBSERVATIONS.append({"check": "preexisting writable mapping after filehandle close",
                "actual_retained_read_admission_denied": True})
        finally:
            self.assertTrue(self.backend.k.UnmapViewOfFile(view))
            self.assertTrue(self.backend.k.CloseHandle(mapping))
        handle = self.retained(); self.backend.close(handle)

    def test_actual_readonly_mapping_compatible(self):
        mapping, view = self.mapping(2, 4, 0x80000000)  # PAGE_READONLY, FILE_MAP_READ
        try:
            handle = self.retained(); self.backend.close(handle)
            NATIVE_OBSERVATIONS.append({"check": "preexisting readonly mapping", "actual_admitted": True})
        finally:
            self.assertTrue(self.backend.k.UnmapViewOfFile(view))
            self.assertTrue(self.backend.k.CloseHandle(mapping))

    def test_actual_copy_on_write_mapping(self):
        mapping, view = self.mapping(8, 1, 0x80000000)  # PAGE_WRITECOPY, FILE_MAP_COPY
        try:
            admitted = False
            try:
                handle = self.retained(); admitted = True
            except NativeHandleError:
                handle = None  # Conservative denial is safe, never a fallback.
            ctypes.memmove(view, b"X", 1)
            self.assertEqual(self.path.read_bytes(), b"0123456789abcdef")
            if handle is not None: self.backend.close(handle)
            NATIVE_OBSERVATIONS.append({"check": "preexisting copy-on-write mapping", "actual_admitted": admitted,
                "private_view_write_left_file_bytes_unchanged": True})
        finally:
            self.assertTrue(self.backend.k.UnmapViewOfFile(view))
            self.assertTrue(self.backend.k.CloseHandle(mapping))


if __name__ == "__main__":
    raise SystemExit("Use NEW run_tests.py with its exclusive NEW fixture directory")
