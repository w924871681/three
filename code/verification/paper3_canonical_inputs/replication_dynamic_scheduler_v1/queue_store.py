"""Append-only exclusive task ownership for a new dynamic execution attempt.

No model imports, seeds, losses, generator calls, or historical file mutations.
One coordinator owns a ledger; model workers receive one immutable command at a
time. An interrupted claim is never automatically recycled.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path


class IntegrityError(RuntimeError):
    pass


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def safe(root, relative, *, exists=False):
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise IntegrityError("absolute/escaping/empty relative path")
    # Reject symlinks AND Windows junction/reparse points, including ancestors.
    candidate = root / relative
    for part in (root, *root.parents, *candidate.parents, candidate):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise IntegrityError("reparse/symlink path forbidden")
    resolved = candidate.resolve(strict=exists)
    if root.resolve(strict=True) not in resolved.parents:
        raise IntegrityError("resolved path escapes independent root")
    return resolved


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise IntegrityError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise IntegrityError("nonfinite JSON constant: " + value)
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=pairs, parse_constant=invalid)


def exclusive_json(root, relative, value):
    """Publish complete bytes by an exclusive same-directory hardlink.

    A temporary hardlink is deliberately retained as independent evidence. No
    existing publication is overwritten or deleted, including after failure.
    """
    path = safe(root, relative)
    if path.exists():
        raise IntegrityError("immutable publication already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = safe(root, relative)
    data = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                       allow_nan=False) + "\n").encode()
    temporary = path.parent / (path.name + ".pending_" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)  # Never os.replace: a collision is a hard failure.
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise IntegrityError("unsafe identity")
    return value


def task_stem(task):
    if set(task) != {"center_id", "seed", "scenario", "method", "config_id"}:
        raise IntegrityError("task fields differ from frozen task identity")
    label(task["config_id"])
    if (type(task["center_id"]) is not int or not 33000 <= task["center_id"] <= 33019
            or type(task["seed"]) is not int or task["seed"] not in (7311, 7312, 7313)
            or task["scenario"] not in ("C0", "C1", "C3", "C4")
            or task["method"] not in ("B0", "B1", "B2", "B8", "P7.7")):
        raise IntegrityError("task outside frozen matrix")
    configs = {"B0": "B0_Frozen_ratio10", "B1": "B1_AlwaysMaintainP50_ratio10",
               "B2": "B2_RAVM_ratio10", "B8": "B8_AlwaysOpen_ratio10",
               "P7.7": "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"}
    if task['config_id'] != configs[task['method']]:
        raise IntegrityError("method/frozen configuration identity differs")
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"


class QueueStore:
    """Single writer, immutable claims, immutable hash-chained state events."""

    def __init__(self, root, tasks, bindings, *, already_complete=()):
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=False)
        self.bindings = json.loads(json.dumps(bindings))
        self.tasks = {task_stem(t): dict(t) for t in tasks}
        if len(self.tasks) != len(tasks):
            raise IntegrityError("duplicate task population")
        complete = set(already_complete)
        if not complete <= self.tasks.keys():
            raise IntegrityError("completed task outside frozen population")
        self.states = {name: "COMPLETE" if name in complete else "PENDING" for name in self.tasks}
        self.claims = {}
        self.active = {}
        self.sequence = 0
        self.previous = None
        self.stopped = False
        exclusive_json(self.root, "COORDINATOR_EXCLUSIVE_LOCK.json", {"pid": os.getpid(), "utc": utc(), **self.bindings})
        self._event("INITIALIZED", {"ordered_tasks": list(self.tasks), "already_complete": sorted(complete)})

    def _event(self, action, body):
        self.sequence += 1
        event = {"schema": "paper3-dynamic-queue-event-v1", "sequence": self.sequence,
                 "previous_sha256": self.previous, "action": action, "utc": utc(),
                 "bindings": self.bindings, "body": body}
        published = exclusive_json(self.root, f"journal/{self.sequence:06d}.json", event)
        self.previous = published["sha256"]
        return event

    @property
    def pending(self):
        return sum(value == "PENDING" for value in self.states.values())

    @property
    def complete(self):
        return sum(value == "COMPLETE" for value in self.states.values())

    def claim(self, worker_id):
        label(worker_id)
        if self.stopped:
            raise IntegrityError("stopped coordinator cannot dispatch")
        if worker_id in self.active:
            raise IntegrityError("worker already owns an unfinished claim")
        name = next((name for name, state in self.states.items() if state == "PENDING"), None)
        if name is None:
            return None
        claim_id = f"C{self.sequence + 1:06d}"
        claim = {"claim_id": claim_id, "worker_id": worker_id, "task": self.tasks[name],
                 "task_digest": canonical(self.tasks[name]), "bindings": self.bindings}
        self._event("CLAIMED", claim)
        self.states[name] = "CLAIMED"
        self.claims[claim_id] = claim
        self.active[worker_id] = claim_id
        return dict(claim)

    def finish(self, worker_id, claim_id, proof):
        if self.stopped:
            raise IntegrityError("stopped ledger requires independent recovery; no inferred completion")
        if self.active.get(worker_id) != claim_id or claim_id not in self.claims:
            raise IntegrityError("completion does not own this claim")
        claim = self.claims[claim_id]
        if (proof.get("validated") is not True or proof.get("task_digest") != claim["task_digest"]
                or not re.fullmatch(r"[a-f0-9]{64}", proof.get("receipt_sha256", ""))
                or not re.fullmatch(r"[a-f0-9]{64}", proof.get("output_hash", ""))):
            raise IntegrityError("completion requires independently validated actual receipt/CSV")
        self._event("COMPLETED", {**claim, "proof": proof})
        self.states[task_stem(claim["task"])] = "COMPLETE"
        del self.active[worker_id]

    def stop(self, reason, *, worker_id=None, claim_id=None):
        if self.stopped:
            return
        if worker_id is not None and self.active.get(worker_id) != claim_id:
            raise IntegrityError("failure does not own this claim")
        self._event("STOPPED", {"reason": str(reason), "worker_id": worker_id,
                                "claim_id": claim_id, "claims_not_requeued": dict(self.active),
                                "new_random_draw_retry": False})
        self.stopped = True

    def boundary_retire(self, worker_id):
        if worker_id in self.active:
            raise IntegrityError("cannot retire a worker inside a trajectory")
        self._event("RETIRED_AT_BOUNDARY", {"worker_id": label(worker_id), "inflight_killed": False})


def verify_journal(root):
    """Read-only verification; does not infer missing claims successful or retryable."""
    root = Path(root)
    previous = None
    bindings = None
    active, complete, tasks, claims = {}, set(), set(), {}
    stopped = False
    for index, path in enumerate(sorted((root / "journal").glob("*.json")), 1):
        path = safe(root, path.relative_to(root), exists=True)
        if path.name != f"{index:06d}.json":
            raise IntegrityError("missing/reordered journal entry")
        event = read_json(path)
        if event.get('schema') != 'paper3-dynamic-queue-event-v1':
            raise IntegrityError('journal schema differs')
        if event["sequence"] != index or event["previous_sha256"] != previous:
            raise IntegrityError("broken event sequence/hash chain")
        if bindings is None:
            bindings = event["bindings"]
        elif event["bindings"] != bindings:
            raise IntegrityError("mixed queue provenance")
        body, action = event["body"], event["action"]
        if index == 1:
            if action != "INITIALIZED":
                raise IntegrityError("missing population declaration")
            tasks = set(body["ordered_tasks"])
            if len(tasks) != len(body["ordered_tasks"]):
                raise IntegrityError("duplicate population")
            complete = set(body["already_complete"])
            if not complete <= tasks:
                raise IntegrityError("invalid inherited inventory")
        elif action == "CLAIMED":
            name = task_stem(body["task"])
            if (stopped or name not in tasks or name in complete or name in {task_stem(c['task']) for c in active.values()}
                    or body["worker_id"] in active or body["claim_id"] in claims
                    or canonical(body["task"]) != body["task_digest"] or body["bindings"] != bindings):
                raise IntegrityError("invalid/duplicate claim")
            claims[body["claim_id"]] = body
            active[body["worker_id"]] = body
        elif action == "COMPLETED":
            name = task_stem(body["task"])
            original = active.get(body["worker_id"])
            if stopped or original is None or task_stem(original["task"]) != name:
                raise IntegrityError("invalid completion after stop/without claim")
            if (any(body.get(key) != original[key] for key in ("claim_id", "worker_id", "task", "task_digest", "bindings"))
                    or body["claim_id"] not in claims or body["proof"].get("validated") is not True
                    or body["proof"].get("task_digest") != original["task_digest"]
                    or not re.fullmatch(r"[a-f0-9]{64}", body["proof"].get("receipt_sha256", ""))
                    or not re.fullmatch(r"[a-f0-9]{64}", body["proof"].get("output_hash", ""))):
                raise IntegrityError("invalid completion proof")
            complete.add(name)
            del active[body["worker_id"]]
        elif action == "RETIRED_AT_BOUNDARY":
            if body["worker_id"] in active or body.get("inflight_killed") is not False:
                raise IntegrityError("retirement inside active trajectory")
        elif action == "STOPPED":
            expected_active = {worker: claim['claim_id'] for worker, claim in active.items()}
            if body.get('claims_not_requeued') != expected_active or body.get('new_random_draw_retry') is not False:
                raise IntegrityError('stop record lost/requeued an unfinished claim')
            stopped = True
        else:
            raise IntegrityError("unknown journal action")
        previous = sha(path)
    if bindings is None:
        raise IntegrityError("empty queue journal")
    return {"bindings": bindings, "complete": len(complete), "pending": len(tasks - complete - {task_stem(c['task']) for c in active.values()}),
            "active_claims": active, "stopped": stopped, "last_sha256": previous,
            "scientific_integrity_pass": False}
