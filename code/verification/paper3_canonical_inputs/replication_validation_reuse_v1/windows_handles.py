"""Windows-only, noninheritable retained read handles; import has no WinAPI IO.

No file writes/deletes, privilege elevation, process control, scientific imports
or file hashing at metadata boundaries. Native APIs initialize on construction.
FILE_SHARE_READ forbids ordinary new write/delete opens and admission while a
conflicting write handle/mapping exists. Actual fixture tests remain necessary;
special filesystems, privileged storage writers and kernel compromise are outside
this mechanism. Full original SHA bookends remain mandatory.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import hashlib
import os
from pathlib import Path
import stat


class NativeHandleError(RuntimeError):
    pass


class WindowsReadBackend:
    def __init__(self):
        if os.name != "nt":
            raise NativeHandleError("Windows native backend unavailable; no metadata fallback")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                       w.DWORD, w.DWORD, w.HANDLE]
        self.k.CreateFileW.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.CloseHandle.restype = w.BOOL
        self.k.GetFileInformationByHandleEx.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.k.GetFileInformationByHandleEx.restype = w.BOOL
        self.k.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.c_void_p]
        self.k.GetFileInformationByHandle.restype = w.BOOL
        self.k.GetHandleInformation.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        self.k.GetHandleInformation.restype = w.BOOL
        self.k.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
        self.k.GetFinalPathNameByHandleW.restype = w.DWORD
        self.k.GetCurrentProcess.argtypes = []
        self.k.GetCurrentProcess.restype = w.HANDLE
        self.k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        self.k.GetProcessTimes.restype = w.BOOL
        self.k.GetVolumeInformationByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD,
            ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
        self.k.GetVolumeInformationByHandleW.restype = w.BOOL
        self._owned = set()
        self._ntfs_volumes = set()
        self._pending_cleanup = {}

    @staticmethod
    def _raise(operation):
        code = ctypes.get_last_error()
        raise NativeHandleError(operation + ": " + str(ctypes.WinError(code)))

    def process_identity(self):
        times = [w.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(self.k.GetCurrentProcess(), *(ctypes.byref(t) for t in times)):
            self._raise("GetProcessTimes(current)")
        return (os.getpid(), (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)

    def open_read(self, path, *, directory):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts or str(path).startswith("\\\\"):
            raise NativeHandleError("only absolute local filesystem paths are supported")
        # Null SECURITY_ATTRIBUTES makes the handle noninheritable. OPEN_REPARSE
        # opens the reparse itself; identity() rejects its attribute rather than
        # silently following it. Ancestors are separately retained/verified.
        handle = self.k.CreateFileW(str(path), 0x80000000, 0x1, None, 3,
            0x00200000 | (0x02000000 if directory else 0), None)
        if handle == ctypes.c_void_p(-1).value or handle is None:
            self._raise("CreateFileW retained read " + str(path))
        self._owned.add(handle)
        try:
            identity = self.identity(handle)
            if identity["directory"] is not directory:
                raise NativeHandleError("file/directory kind differs: " + str(path))
            return handle
        except BaseException:
            try:
                self.close(handle)
            except BaseException as error:
                self._pending_cleanup[handle] = {"handle": handle, "path": str(path),
                    "kind": "backend_open_rejection", "error_type": type(error).__name__, "message": str(error)}
                raise
            raise

    def identity(self, handle):
        if handle not in self._owned:
            raise NativeHandleError("handle is not owned/live")
        class FileId(ctypes.Structure):
            _fields_ = [("volume", ctypes.c_ulonglong), ("file_id", ctypes.c_ubyte * 16)]
        class Basic(ctypes.Structure):
            _fields_ = [("attributes", w.DWORD), ("creation", w.FILETIME), ("access", w.FILETIME),
                ("write", w.FILETIME), ("volume", w.DWORD), ("size_high", w.DWORD), ("size_low", w.DWORD),
                ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]
        file_id, basic, flags = FileId(), Basic(), w.DWORD()
        if not self.k.GetFileInformationByHandleEx(handle, 18, ctypes.byref(file_id), ctypes.sizeof(file_id)):
            self._raise("GetFileInformationByHandleEx(FileIdInfo)")
        if not self.k.GetFileInformationByHandle(handle, ctypes.byref(basic)):
            self._raise("GetFileInformationByHandle")
        if not any(file_id.file_id):
            raise NativeHandleError("all-zero FILE_ID128 rejected")
        if not self.k.GetHandleInformation(handle, ctypes.byref(flags)):
            self._raise("GetHandleInformation")
        if flags.value & 1:
            raise NativeHandleError("inheritable handle rejected")
        if basic.attributes & 0x400:
            raise NativeHandleError("reparse point handle rejected")
        buffer = ctypes.create_unicode_buffer(32768)
        # VOLUME_NAME_GUID (1) binds a volume identity, not a mutable drive label.
        size = self.k.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 1)
        if not size or size >= len(buffer):
            self._raise("GetFinalPathNameByHandleW(volume GUID)")
        final_path = buffer.value.casefold()
        if not final_path.startswith("\\\\?\\volume{") or "}\\" not in final_path:
            raise NativeHandleError("nonlocal/non-volume-GUID path rejected")
        volume_key = (file_id.volume, final_path.split("}\\", 1)[0])
        if volume_key not in self._ntfs_volumes:
            filesystem = ctypes.create_unicode_buffer(256)
            serial, maximum, features = w.DWORD(), w.DWORD(), w.DWORD()
            if not self.k.GetVolumeInformationByHandleW(handle, None, 0, ctypes.byref(serial),
                    ctypes.byref(maximum), ctypes.byref(features), filesystem, len(filesystem)):
                self._raise("GetVolumeInformationByHandleW")
            if filesystem.value.upper() != "NTFS":
                raise NativeHandleError("only locally observed NTFS volumes are supported")
            self._ntfs_volumes.add(volume_key)
        return {"volume_serial": file_id.volume, "file_id_128": bytes(file_id.file_id).hex(),
            "volume_guid_path": final_path, "directory": bool(basic.attributes & 0x10),
            "size": (basic.size_high << 32) | basic.size_low, "attributes": basic.attributes,
            "noninheritable": True, "share_mode": "FILE_SHARE_READ_ONLY", "local_NTFS_verified": True}

    def close(self, handle):
        if handle not in self._owned:
            raise NativeHandleError("unknown/already closed native handle")
        if not self.k.CloseHandle(handle):
            self._raise("CloseHandle")
        self._owned.remove(handle)
        self._pending_cleanup.pop(handle, None)

    def pending_cleanup(self):
        return tuple(dict(item) for item in self._pending_cleanup.values())

    @staticmethod
    def same_file_identity(first, second):
        return (first["volume_serial"], first["file_id_128"]) == (second["volume_serial"], second["file_id_128"])

    @staticmethod
    def path_exists(path):
        try:
            value = Path(path).lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise NativeHandleError("reparse output path rejected")
        return True

    @staticmethod
    def inventory(spec):
        root = Path(spec.root)
        result = {}
        def check(path):
            attributes = path.lstat()
            if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, "st_file_attributes", 0) & 0x400:
                raise NativeHandleError("reparse/symlink inventory entry rejected: " + str(path))
            return attributes
        check(root)
        def descend(directory):
            for item in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                value = check(item)
                relative = item.relative_to(root).as_posix()
                if stat.S_ISDIR(value.st_mode):
                    if item.name in spec.excluded_directory_names:
                        continue
                    result[relative] = "directory"
                    descend(item)
                elif stat.S_ISREG(value.st_mode):
                    if not spec.file_suffixes or item.suffix.lower() in spec.file_suffixes:
                        result[relative] = "file"
                else:
                    raise NativeHandleError("nonregular inventory entry rejected: " + str(item))
        descend(root)
        return result

    @staticmethod
    def hash_file(path):
        h = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                h.update(chunk)
        return h.hexdigest()
