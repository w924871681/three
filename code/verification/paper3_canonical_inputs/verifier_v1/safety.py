"""Exclusive, append-only verification output. No project imports or execution."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
from pathlib import Path

from .contract import ContractError, file_sha256


def regular_path(path: Path, *, must_exist: bool = True) -> Path:
    """Reject every existing symlink/junction/reparse ancestor, including Windows."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ContractError(f"reparse/symlink path forbidden: {part}")
    if must_exist and not path.exists():
        raise ContractError(f"missing path: {path}")
    return path.resolve(strict=must_exist)


def contained_path(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise ContractError("use a forward-slash relative path")
    parts = relative.split("/")
    if not relative or any(p in ("", ".", "..") for p in parts):
        raise ContractError("empty/dot/traversal path forbidden")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or ":" in p or p.endswith((".", " "))
           or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
           for p in parts):
        raise ContractError("unsafe path component")
    resolved_root = regular_path(root)
    candidate = regular_path(resolved_root.joinpath(*parts), must_exist=must_exist)
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise ContractError("path escaped its authorized root")
    return candidate


class SafeWriter:
    """No overwrite/delete/rename; file creation uses O_EXCL and checked ancestors.

    Requires exclusive workspace custody; OS-level malicious junction substitution
    between checking a path and opening it is outside this local audit threat model.
    """

    def __init__(self, root: Path):
        self.root = regular_path(root)
        self.created_sha256: dict[str, str] = {}

    def _record(self, relative: str) -> str:
        self.created_sha256[relative] = file_sha256(contained_path(self.root, relative))
        return relative

    @classmethod
    def reserve(cls, repo: Path, run_id: str) -> "SafeWriter":
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", run_id):
            raise ContractError("invalid preallocated run_id")
        base = regular_path(repo) / "verification" / "paper3_canonical_inputs"
        regular_path(base)
        protocol = base / "P7_7_CANONICAL_INPUT_VERIFICATION_V1"
        regular_path(protocol, must_exist=False)
        protocol.mkdir(exist_ok=True)
        regular_path(protocol)
        root = protocol / run_id
        regular_path(root, must_exist=False)
        root.mkdir(exist_ok=False)
        return cls(root)

    def _open(self, relative: str):
        path = contained_path(self.root, relative, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        contained_path(self.root, relative, must_exist=False)
        return path.open("xb")

    def write_bytes(self, relative: str, value: bytes) -> str:
        with self._open(relative) as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        return self._record(relative)

    def write_json(self, relative: str, value) -> str:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                             allow_nan=False).encode("utf-8") + b"\n"
        return self.write_bytes(relative, payload)

    def write_jsonl(self, relative: str, rows) -> str:
        with self._open(relative) as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                        allow_nan=False).encode("utf-8") + b"\n")
        return self._record(relative)

    def write_csv(self, relative: str, rows: list[dict]) -> str:
        columns = sorted({key for row in rows for key in row})
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True,
                                             allow_nan=False) if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})
        return self.write_bytes(relative, output.getvalue().encode("utf-8"))

    def write_array(self, relative: str, array) -> str:
        import numpy as np
        if array.dtype.hasobject:
            raise ContractError("pickle/object arrays forbidden")
        with self._open(relative) as handle:
            np.save(handle, np.ascontiguousarray(array), allow_pickle=False)
        return self._record(relative)

    def inventory(self) -> dict[str, str]:
        output = {}
        for path in sorted(self.root.rglob("*")):
            regular_path(path)
            if path.is_file():
                output[path.relative_to(self.root).as_posix()] = file_sha256(path)
        return output
