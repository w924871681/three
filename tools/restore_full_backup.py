#!/usr/bin/env python3
"""Verify or restore a Paper3 split-ZIP backup using only Python's standard library.

Download FULL_BACKUP_MANIFEST.json, its .sha256 sidecar (if published), the
selected groups' *_FILES.json indexes, and every selected .zip.NNN part into
one assets directory. The output path must not exist or must be an empty real
directory. The script never executes extracted files or overwrites files.

Examples (Python 3.10+):
  python restore_full_backup.py --manifest assets/FULL_BACKUP_MANIFEST.json \
      --assets assets --output restored --verify-only
  python restore_full_backup.py --manifest assets/FULL_BACKUP_MANIFEST.json \
      --assets assets --output restored --groups raw canonical

Default: select every manifest group. --verify-only writes no output or joined
ZIP: a seekable reader reads the original ordered parts directly. Restoration
joins each group into a new temporary ZIP under the output directory and removes
that ZIP only after the entire group has passed verification. Use
--keep-joined-zip to retain it. On failure, already created files and the partial
or complete joined ZIP remain for inspection; use a different empty output for
a retry. A manifest sidecar detects corruption, not publisher authenticity.

Group "requires" dependencies are included automatically. An indexed file may
use content_reference={"group": "controlled_environment", "archive_path": ...}
instead of storing duplicate bytes in its ZIP. Its dependency's regular payload
file must already be fully verified and have identical size/SHA256. Verification
reuses that result; restoration copies and hashes it into an independent file.

The ordered part list may mix original .zip.NNN parts with 64 MiB transport
subparts named .zip.NNN.net64.MMM. Each original part must appear exactly once,
either intact or as its complete consecutive subpart sequence. Subdivision does
not change the logical ZIP bytes or its SHA256.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
import uuid
import zipfile


SCHEMA = "paper3-full-data-environment-backup-v1"
GROUP_IDS = ("raw", "canonical", "controlled_environment", "base_environment")
BLOCK_BYTES = 1024 * 1024
MAX_PART_BYTES = 256 * 1024 * 1024
NET_PART_BYTES = 64 * 1024 * 1024
HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


class BackupError(Exception):
    """A supplied backup or destination failed validation."""


def fail(message: str) -> None:
    raise BackupError(message)


def sha256(value, label: str) -> str:
    if not isinstance(value, str) or not HEX_SHA256.fullmatch(value):
        fail(f"{label}: expected a 64-character SHA256 digest")
    return value.lower()


def count(value, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        fail(f"{label}: expected an integer >= {minimum}")
    return value


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail(f"Duplicate JSON property: {key!r}")
        result[key] = value
    return result


def read_json(path: Path, expected_hash: str | None = None):
    if path.is_symlink() or not path.is_file():
        fail(f"Expected a regular, non-symlink file: {path}")
    raw = path.read_bytes()
    if expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash:
        fail(f"SHA256 mismatch: {path.name}")
    try:
        result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=object_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"Invalid JSON in {path.name}: {error}")
    if not isinstance(result, dict):
        fail(f"Expected a JSON object in {path.name}")
    return result


def portable_path(value, label: str, directory: bool = False) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{label}: empty or non-string archive path")
    if directory and value.endswith("/"):
        value = value[:-1]
    if not value or "\\" in value or value.startswith("/"):
        fail(f"{label}: unsafe archive path {value!r}")
    pieces = value.split("/")
    for piece in pieces:
        if (
            not piece or piece in (".", "..") or piece.endswith((".", " "))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in piece)
            or piece.split(".", 1)[0].upper() in WINDOWS_DEVICES
        ):
            fail(f"{label}: unsafe/nonportable archive path {value!r}")
    return "/".join(pieces)


def asset_path(assets: Path, name, label: str) -> Path:
    normalized = portable_path(name, label)
    if "/" in normalized:
        fail(f"{label}: assets must be plain filenames")
    path = assets / normalized
    if path.is_symlink() or not path.is_file():
        fail(f"Missing regular asset file: {path}")
    return path


def collision_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


class PathRegistry:
    def __init__(self):
        self.entries = {}

    def add(self, name: str, kind: str) -> None:
        pieces = name.split("/")
        candidates = [("/".join(pieces[:i]), "directory") for i in range(1, len(pieces))]
        candidates.append((name, kind))
        for path, entry_kind in candidates:
            key = collision_key(path)
            previous = self.entries.get(key)
            if previous is not None:
                old_path, old_kind = previous
                if old_path != path:
                    fail(f"Case/Unicode path collision: {old_path!r} and {path!r}")
                if old_kind != entry_kind or entry_kind == "file":
                    fail(f"Duplicate file or file/directory collision: {path!r}")
            else:
                self.entries[key] = (path, entry_kind)


class MultipartReader(io.RawIOBase):
    """Seekable, read-only concatenation; no temporary copy and bounded memory."""

    def __init__(self, parts):
        super().__init__()
        self._paths = [part["path"] for part in parts]
        self._ends = []
        total = 0
        for part in parts:
            total += part["bytes"]
            self._ends.append(total)
        self._length = total
        self._position = 0
        self._stream = None
        self._stream_index = None

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self._position

    def seek(self, offset, whence=os.SEEK_SET):
        self._checkClosed()
        origin = {os.SEEK_SET: 0, os.SEEK_CUR: self._position, os.SEEK_END: self._length}
        if whence not in origin:
            raise ValueError("Invalid seek origin")
        target = origin[whence] + offset
        if target < 0:
            raise ValueError("Negative seek position")
        self._position = target
        return target

    def read(self, size=-1):
        self._checkClosed()
        remaining = max(0, self._length - self._position)
        if size is None or size < 0:
            size = remaining
        wanted = min(size, remaining)
        chunks = []
        while wanted:
            index = bisect.bisect_right(self._ends, self._position)
            start = self._ends[index - 1] if index else 0
            if self._stream_index != index:
                if self._stream is not None:
                    self._stream.close()
                self._stream = self._paths[index].open("rb")
                self._stream_index = index
            self._stream.seek(self._position - start)
            chunk = self._stream.read(min(wanted, self._ends[index] - self._position))
            if not chunk:
                fail(f"Unexpected EOF in part {self._paths[index].name}")
            chunks.append(chunk)
            self._position += len(chunk)
            wanted -= len(chunk)
        return b"".join(chunks)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self):
        if self._stream is not None:
            self._stream.close()
        super().close()


def load_plans(manifest_path: Path, assets: Path, requested):
    sidecar = Path(str(manifest_path) + ".sha256")
    expected_manifest_hash = None
    if sidecar.exists() or sidecar.is_symlink():
        if sidecar.is_symlink() or not sidecar.is_file():
            fail("Manifest SHA256 sidecar must be a regular file")
        tokens = sidecar.read_text(encoding="utf-8-sig").split()
        expected_manifest_hash = sha256(tokens[0] if tokens else None, "Manifest sidecar")
    manifest = read_json(manifest_path, expected_manifest_hash)
    if manifest.get("schema") != SCHEMA:
        fail(f"Unsupported manifest schema: {manifest.get('schema')!r}")
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        fail("Manifest groups must be a nonempty list")
    identities = []
    group_map = {}
    for group in groups:
        if not isinstance(group, dict) or group.get("id") not in GROUP_IDS:
            fail("Every manifest group needs a supported group id")
        identities.append(group["id"])
        group_map[group["id"]] = group
    if len(identities) != len(set(identities)):
        fail("Duplicate manifest group ids")
    if requested and (len(requested) != len(set(requested)) or set(requested) - set(identities)):
        fail("Requested groups are duplicated or absent from the manifest")
    for group in groups:
        requires = group.get("requires", [])
        if (not isinstance(requires, list)
                or any(not isinstance(gid, str) or gid not in group_map for gid in requires)
                or len(requires) != len(set(requires))):
            fail(f"{group['id']}: requires must list distinct existing group ids")
    ordered_ids, visiting, visited = [], set(), set()

    def visit(gid):
        if gid in visiting:
            fail(f"Cyclic group dependency involving {gid}")
        if gid in visited:
            return
        visiting.add(gid)
        for dependency in group_map[gid].get("requires", []):
            visit(dependency)
        visiting.remove(gid)
        visited.add(gid)
        ordered_ids.append(gid)

    for gid in requested or identities:
        visit(gid)
    registry = PathRegistry()
    used_assets = set()
    plans = []
    for gid in ordered_ids:
        group = group_map[gid]
        gid = group["id"]
        index_path = asset_path(assets, group.get("index_asset"), f"{gid} index_asset")
        index = read_json(index_path, sha256(group.get("index_sha256"), f"{gid} index_sha256"))
        if not isinstance(index.get("files"), list):
            fail(f"{gid}: index.files must be a list")
        files = {}
        for row in index["files"]:
            if not isinstance(row, dict):
                fail(f"{gid}: file index entries must be objects")
            name = portable_path(row.get("archive_path"), f"{gid} archive_path")
            if name in files:
                fail(f"{gid}: duplicate indexed file {name!r}")
            registry.add(name, "file")
            files[name] = {
                "bytes": count(row.get("bytes"), f"{gid}/{name} bytes"),
                "sha256": sha256(row.get("sha256"), f"{gid}/{name} sha256"),
            }
            if "content_reference" in row:
                reference = row["content_reference"]
                if (not isinstance(reference, dict)
                        or not {"group", "archive_path"} <= set(reference)
                        or set(reference) - {"group", "archive_path", "bytes"}
                        or reference.get("group") not in group.get("requires", [])):
                    fail(f"{gid}/{name}: content_reference must name a declared dependency")
                if "bytes" in reference:
                    reference_bytes = count(reference["bytes"], f"{gid}/{name} content_reference bytes")
                    if reference_bytes != files[name]["bytes"]:
                        fail(f"{gid}/{name}: content_reference bytes differ from indexed file size")
                files[name]["content_reference"] = {
                    "group": reference["group"],
                    "archive_path": portable_path(reference["archive_path"], "Content reference"),
                }
        directory_rows = index.get("directories", [])
        if not isinstance(directory_rows, list):
            fail(f"{gid}: index.directories must be a list when present")
        directories = set()
        for row in directory_rows:
            value = row.get("archive_path") if isinstance(row, dict) else row
            name = portable_path(value, f"{gid} directory", directory=True)
            if name in directories:
                fail(f"{gid}: duplicate indexed directory {name!r}")
            registry.add(name, "directory")
            directories.add(name)
        if count(group.get("file_count"), f"{gid} file_count") != len(files):
            fail(f"{gid}: file_count does not match the index")
        total_bytes = sum(row["bytes"] for row in files.values())
        if count(group.get("uncompressed_bytes"), f"{gid} uncompressed_bytes") != total_bytes:
            fail(f"{gid}: uncompressed_bytes does not match the index")
        part_rows = group.get("parts")
        if not isinstance(part_rows, list) or not part_rows:
            fail(f"{gid}: parts must be a nonempty ordered list")
        zip_bytes = count(group.get("zip_bytes"), f"{gid} zip_bytes", 1)
        parts = []
        zip_name = None
        original_parts = []
        previous_original, previous_subpart = 0, None
        has_net64 = False
        for number, row in enumerate(part_rows, 1):
            if not isinstance(row, dict):
                fail(f"{gid}: part entries must be objects")
            part_path = asset_path(assets, row.get("name"), f"{gid} part name")
            match = re.fullmatch(r"(.+\.zip)\.([0-9]{3,})(?:\.net64\.([0-9]{3,}))?", part_path.name)
            if not match:
                fail(f"{gid}: invalid ZIP part or net64 subpart name")
            original = int(match.group(2))
            subpart = int(match.group(3)) if match.group(3) is not None else None
            if zip_name is None:
                zip_name = match.group(1)
            canonical_name = f"{zip_name}.{original:03d}"
            if subpart is not None:
                canonical_name += f".net64.{subpart:03d}"
                has_net64 = True
            if part_path.name != canonical_name:
                fail(f"{gid}: inconsistent ZIP stem or noncanonical part numbering")
            if original == previous_original + 1:
                if subpart not in (None, 1):
                    fail(f"{gid}: net64 subparts must start at 001")
                original_parts.append([])
            elif (original != previous_original or previous_subpart is None
                  or subpart != previous_subpart + 1):
                fail(f"{gid}: unordered, repeated or missing ZIP part/subpart")
            previous_original, previous_subpart = original, subpart
            key = collision_key(part_path.name)
            if key in used_assets:
                fail(f"Duplicate part asset across groups: {part_path.name}")
            used_assets.add(key)
            size = count(row.get("bytes"), f"{gid} part bytes", 1)
            if size > MAX_PART_BYTES:
                fail(f"{gid}: part exceeds the 256 MiB format limit")
            if subpart is not None and size > NET_PART_BYTES:
                fail(f"{gid}: net64 subpart exceeds the 64 MiB format limit")
            original_parts[-1].append((subpart, size))
            parts.append({"path": part_path, "bytes": size,
                          "sha256": sha256(row.get("sha256"), f"{gid} part sha256")})
        if has_net64:
            # The original writer cuts every nonfinal original part at 256 MiB.
            # Reconstruct those boundaries to detect even a missing final
            # subpart before opening the ZIP, while retaining legacy acceptance.
            expected_original_count = (zip_bytes + MAX_PART_BYTES - 1) // MAX_PART_BYTES
            if len(original_parts) != expected_original_count:
                fail(f"{gid}: incomplete original ZIP part sequence")
            for original, segments in enumerate(original_parts, 1):
                original_bytes = min(MAX_PART_BYTES, zip_bytes - (original - 1) * MAX_PART_BYTES)
                if segments[0][0] is None:
                    expected_segments = [(None, original_bytes)]
                else:
                    expected_segments = [
                        (subpart, min(NET_PART_BYTES, original_bytes - offset))
                        for subpart, offset in enumerate(range(0, original_bytes, NET_PART_BYTES), 1)
                    ]
                if segments != expected_segments:
                    fail(f"{gid}: missing or incorrectly sized net64/original part {original:03d}")
        if sum(part["bytes"] for part in parts) != zip_bytes:
            fail(f"{gid}: zip_bytes differs from the sum of part sizes")
        plans.append({"id": gid, "parts": parts, "files": files, "directories": directories,
                      "zip_bytes": zip_bytes, "zip_sha256": sha256(group.get("zip_sha256"), f"{gid} zip_sha256")})
    plans_by_id = {plan["id"]: plan for plan in plans}
    for plan in plans:
        for name, row in plan["files"].items():
            reference = row.get("content_reference")
            if reference is None:
                continue
            target = plans_by_id[reference["group"]]["files"].get(reference["archive_path"])
            if target is None:
                fail(f"{plan['id']}/{name}: content_reference target is missing or a directory")
            if "content_reference" in target:
                fail(f"{plan['id']}/{name}: content_reference cannot target another reference")
            if (row["bytes"], row["sha256"]) != (target["bytes"], target["sha256"]):
                fail(f"{plan['id']}/{name}: content_reference size/SHA256 mismatch")
    return plans, expected_manifest_hash is not None


def check_output(path: Path) -> Path:
    # Check the supplied path before resolving: resolving would hide a symlink.
    if path.is_symlink():
        fail("Output must not be a symlink")
    resolved = path.resolve()
    if path.exists():
        if not path.is_dir() or next(path.iterdir(), None) is not None:
            fail("Output must be a new or empty directory; existing files are never overwritten")
    return resolved


def verify_parts(plan, joined=None) -> None:
    whole = hashlib.sha256()
    whole_bytes = 0
    for part in plan["parts"]:
        digest = hashlib.sha256()
        actual_bytes = 0
        with part["path"].open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                fail(f"Part is not a regular file: {part['path'].name}")
            while chunk := stream.read(BLOCK_BYTES):
                actual_bytes += len(chunk)
                if actual_bytes > part["bytes"]:
                    fail(f"Part size mismatch: {part['path'].name}")
                digest.update(chunk)
                whole.update(chunk)
                if joined is not None:
                    joined.write(chunk)
        if actual_bytes != part["bytes"]:
            fail(f"Part size mismatch: {part['path'].name}")
        if digest.hexdigest() != part["sha256"]:
            fail(f"Part SHA256 mismatch: {part['path'].name}")
        whole_bytes += actual_bytes
    if whole_bytes != plan["zip_bytes"] or whole.hexdigest() != plan["zip_sha256"]:
        fail(f"{plan['id']}: joined ZIP size or SHA256 mismatch")


def validate_members(archive: zipfile.ZipFile, plan):
    files, directories = {}, set()
    registry = PathRegistry()
    for info in archive.infolist():
        name = portable_path(info.filename, "ZIP member", directory=info.is_dir())
        if info.orig_filename != info.filename:
            fail(f"ZIP member contains a truncated/NUL path: {info.orig_filename!r}")
        unix_kind = stat.S_IFMT(info.external_attr >> 16)
        if unix_kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            fail(f"ZIP symlink or special file is forbidden: {name!r}")
        if info.flag_bits & 1:
            fail(f"Encrypted ZIP member is unsupported: {name!r}")
        if info.is_dir():
            if name in directories or info.file_size != 0 or unix_kind == stat.S_IFREG:
                fail(f"Invalid or duplicate ZIP directory: {name!r}")
            registry.add(name, "directory")
            directories.add(name)
        else:
            registry.add(name, "file")
            if unix_kind == stat.S_IFDIR:
                fail(f"ZIP directory mode conflicts with its filename: {name!r}")
            expected = plan["files"].get(name)
            if expected is None or "content_reference" in expected or info.file_size != expected["bytes"]:
                fail(f"Unexpected ZIP file or indexed size mismatch: {name!r}")
            files[name] = info
    stored_files = {name for name, row in plan["files"].items() if "content_reference" not in row}
    if set(files) != stored_files or directories != plan["directories"]:
        fail(f"{plan['id']}: ZIP entries do not exactly match indexed files and directories")
    return files


def ensure_directory(root: Path, relative: str = "") -> Path:
    if root.is_symlink() or not root.is_dir():
        fail("Output directory changed or is a symlink")
    current = root
    for part in relative.split("/") if relative else []:
        current = current / part
        if current.is_symlink():
            fail(f"Destination symlink is forbidden: {current}")
        try:
            current.mkdir()
        except FileExistsError:
            if not current.is_dir():
                fail(f"Destination is not a directory: {current}")
    return current


def process_zip(archive: zipfile.ZipFile, plan, output: Path | None, verified_files, verified_groups) -> None:
    members = validate_members(archive, plan)
    if output is not None:
        for directory in sorted(plan["directories"], key=lambda name: (name.count("/"), name)):
            ensure_directory(output, directory)
    for name in sorted(members):
        expected = plan["files"][name]
        target_stream = None
        if output is not None:
            parent, _, basename = name.rpartition("/")
            directory = ensure_directory(output, parent)
            target_stream = (directory / basename).open("xb")
        digest = hashlib.sha256()
        actual_bytes = 0
        try:
            with archive.open(members[name], "r") as stream:
                while chunk := stream.read(BLOCK_BYTES):
                    actual_bytes += len(chunk)
                    if actual_bytes > expected["bytes"]:
                        fail(f"Extracted file exceeds indexed size: {name}")
                    digest.update(chunk)
                    if target_stream is not None:
                        target_stream.write(chunk)
        finally:
            if target_stream is not None:
                target_stream.close()
        if actual_bytes != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
            fail(f"Extracted member size or SHA256 mismatch: {name}")
        verified_files[(plan["id"], name)] = {
            "bytes": actual_bytes, "sha256": digest.hexdigest(), "is_reference": False,
        }
    for name, expected in sorted(plan["files"].items()):
        reference = expected.get("content_reference")
        if reference is None:
            continue
        target_key = (reference["group"], reference["archive_path"])
        target = verified_files.get(target_key)
        if (reference["group"] not in verified_groups or target is None
                or target["is_reference"]
                or (target["bytes"], target["sha256"]) != (expected["bytes"], expected["sha256"])):
            fail(f"{plan['id']}/{name}: reference target has not been fully verified")
        if output is not None:
            source = output / reference["archive_path"]
            if source.is_symlink() or not source.is_file():
                fail(f"Verified reference source is not a regular file: {source}")
            parent, _, basename = name.rpartition("/")
            directory = ensure_directory(output, parent)
            digest = hashlib.sha256()
            actual_bytes = 0
            # Deliberately copy bytes, never hardlink: each restored environment
            # must remain independently modifiable.
            with source.open("rb") as inp, (directory / basename).open("xb") as out:
                while chunk := inp.read(BLOCK_BYTES):
                    actual_bytes += len(chunk)
                    if actual_bytes > expected["bytes"]:
                        fail(f"Reference source exceeds indexed size: {name}")
                    digest.update(chunk)
                    out.write(chunk)
            if actual_bytes != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                fail(f"Copied reference size or SHA256 mismatch: {name}")
        verified_files[(plan["id"], name)] = {
            "bytes": expected["bytes"], "sha256": expected["sha256"], "is_reference": True,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New or empty destination; verify-only does not create it")
    parser.add_argument("--verify-only", action="store_true", help="Verify all selected bytes without writing output")
    parser.add_argument("--groups", nargs="+", choices=GROUP_IDS)
    parser.add_argument("--keep-joined-zip", action="store_true", help="Retain successfully verified joined ZIPs under output")
    args = parser.parse_args(argv)
    if args.verify_only and args.keep_joined_zip:
        parser.error("--keep-joined-zip cannot be combined with --verify-only")
    try:
        output = check_output(args.output)
        plans, sidecar_verified = load_plans(args.manifest, args.assets, args.groups)
        print("Manifest sidecar: " + ("verified" if sidecar_verified else "not present"), flush=True)
        if not args.verify_only:
            # Recheck immediately before writing; never merge with existing content.
            check_output(args.output)
            output.mkdir(parents=True, exist_ok=True)
            check_output(output)
        verified_files, verified_groups = {}, set()
        for plan in plans:
            print(f"Verifying {plan['id']}: {len(plan['files'])} files, {len(plan['parts'])} parts", flush=True)
            if args.verify_only:
                verify_parts(plan)
                with MultipartReader(plan["parts"]) as reader, zipfile.ZipFile(reader, "r") as archive:
                    process_zip(archive, plan, None, verified_files, verified_groups)
            else:
                joined_path = output / f".paper3-joined-{plan['id']}-{uuid.uuid4().hex}.zip"
                with joined_path.open("xb") as joined:
                    verify_parts(plan, joined)
                with zipfile.ZipFile(joined_path, "r") as archive:
                    process_zip(archive, plan, output, verified_files, verified_groups)
                if not args.keep_joined_zip:
                    joined_path.unlink()
            verified_groups.add(plan["id"])
            print(f"PASS {plan['id']}", flush=True)
        total = sum(len(plan["files"]) for plan in plans)
        print(f"SUCCESS: {total} files {'verified without extraction' if args.verify_only else 'restored and verified'}.", flush=True)
        return 0
    except (BackupError, OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile, EOFError) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
