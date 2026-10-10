"""Recover exact serial source in memory from a fixed, previously audited patch chain.

JSON and quoted JavaScript literals are data. Nothing from the session is executed.
Recovered runner is evidence only and is never imported or called.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contract import ContractError, file_sha256
from .safety import regular_path

RUNNER_LINES = (22278,22306,22360,22734,22826,23143,23177,23212,23294,
                23340,23374,23422,23822,23833,23840,23847)
PROTOCOL_LINES = (22285,22320,22380,22860,23150,23374,23408,23422,23450,
                  23505,23531,23566,23735,23875)
EXPECTED = {
    "scripts/run_p7_7_final.py": "20c0a3546f5cff28dc0dccb3737bc27ee47d81b06fcb94f9fe294ca576e43ec5",
    "configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json": "8785dc1ecf9e8123f47d786b880011774ed952daa56345b6f61e60361d15838d",
}


def _find(lines: list[str], pattern: list[str], start: int) -> int:
    """Match historical apply_patch's forward whitespace-fallback semantics.

    Historical event 23150 used six spaces for a deletion context that had four
    spaces in the previous protocol text. The successful original patch matched
    it after stripping whitespace. Preserve the precedence exact, rstrip, strip;
    apply replacement text verbatim and still require both final byte SHA256s.
    This changes matching only, never silently normalizes reconstructed source.
    """
    for mode in ("exact", "rstrip", "strip"):
        expected = pattern if mode == "exact" else [getattr(row, mode)() for row in pattern]
        for index in range(start, len(lines) - len(pattern) + 1):
            actual = lines[index:index + len(pattern)]
            if mode != "exact":
                actual = [getattr(row, mode)() for row in actual]
            if actual == expected:
                return index
    raise ContractError("historical patch context missing")


def apply_text_patch(text: str | None, patch: str, relative: str) -> str:
    target = "D:/dt-talk/DT_LIFECYCLE_ESCALATION/" + relative
    rows = patch.splitlines()
    markers = [i for i, row in enumerate(rows) if row.startswith("*** ")
               and (" File: " in row or row == "*** End Patch")]
    relevant = [i for i in markers if rows[i] in ("*** Add File: " + target,
                                                  "*** Update File: " + target)]
    if not relevant:
        raise ContractError("target not present in pinned historical event")
    for begin in relevant:
        end = next(i for i in markers if i > begin)
        body = rows[begin + 1:end]
        if rows[begin].startswith("*** Add"):
            if text is not None or any(not row.startswith("+") for row in body):
                raise ContractError("invalid historical add")
            text = "\n".join(row[1:] for row in body) + "\n"
            continue
        if text is None:
            raise ContractError("historical update before add")
        source = text.splitlines()
        cursor = 0
        index = 0
        while index < len(body):
            row = body[index]
            if row.startswith("@@"):
                anchor = row[3:] if row.startswith("@@ ") else ""
                if anchor:
                    cursor = _find(source, [anchor], cursor) + 1
                index += 1
                old, new = [], []
                while index < len(body) and not body[index].startswith("@@"):
                    item = body[index]
                    if item == "*** End of File":
                        index += 1
                        continue
                    if not item or item[0] not in " +-":
                        raise ContractError("unsupported historical hunk encoding")
                    if item[0] in " -": old.append(item[1:])
                    if item[0] in " +": new.append(item[1:])
                    index += 1
                if old or new:
                    position = _find(source, old, cursor) if old else cursor
                    source[position:position + len(old)] = new
                    cursor = position + len(new)
            else:
                raise ContractError("unrecognized historical patch command")
        text = "\n".join(source) + "\n"
    return text


def recover_history(session: Path, expected_session_sha256: str) -> dict:
    session = regular_path(session)
    if file_sha256(session) != expected_session_sha256:
        raise ContractError("history source differs from approved complete session SHA")
    wanted = set(RUNNER_LINES) | set(PROTOCOL_LINES)
    events = {}
    with session.open("r", encoding="utf-8") as handle:
        for line_number, row in enumerate(handle, 1):
            if line_number not in wanted:
                continue
            payload = json.loads(row)["payload"]
            value = payload.get("input", "")
            match = re.match(r'\s*const patch\s*=\s*("(?:[^"\\]|\\.)*")\s*;', value)
            if payload.get("name") != "exec" or not match:
                raise ContractError("pinned session event is not a quoted text patch")
            events[line_number] = json.loads(match.group(1))
    if set(events) != wanted:
        raise ContractError("incomplete historical session")
    recovered = {}
    for relative, chain in (("scripts/run_p7_7_final.py", RUNNER_LINES),
                            ("configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json", PROTOCOL_LINES)):
        text = None
        for line_number in chain:
            text = apply_text_patch(text, events[line_number], relative)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != EXPECTED[relative]:
            raise ContractError(f"exact historical byte hash mismatch: {relative}")
        recovered[relative] = {"sha256": digest, "byte_count": len(text.encode("utf-8")),
                               "event_lines": list(chain), "recovered_text": text}
    return {"status": "VERIFIED_EXACT_HISTORICAL_SOURCE", "session_path": str(session),
            "session_sha256": expected_session_sha256, "objects": recovered,
            "historical_environment_reproduced": False,
            "historical_runner_executed": False}
