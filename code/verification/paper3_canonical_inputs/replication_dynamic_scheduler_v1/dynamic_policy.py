"""Deterministic, input-only resource policy for the independent V3 scheduler.

This module uses only the standard library. It reads no files or model results,
queries no processes, starts nothing, and never signals an in-flight worker.
The caller supplies truthful native observations and applies returned intents.
Worker identities must be unique across restarts. An ADMIT_ONE intent reserves a
slot until a new identity is actually observed. A DRAIN_ONE intent prohibits
the selected worker from claiming another trajectory; retirement itself is
permitted only after an explicit IDLE observation at a trajectory boundary.

Resource parameters govern execution capacity, not the frozen science. The
3.5 GiB private-memory planning floor and 1 GiB commit reserve derive from
replication_abrupt_recovery_v1/recover.py:33,254-257 and the earlier transition
gate migration_controller.py:359-362. The 1 GiB working-set floor, 1 GiB physical
reserve, 256 MiB observed-peak margin and temporal hysteresis are conservative
new scheduling choices, never claims about measured peak memory or speed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
from typing import Sequence

GIB = 1024 ** 3
MIB = 1024 ** 2
PHASES = frozenset({"STARTING", "IDLE", "BUSY", "DRAINING"})


class PolicyInputError(ValueError):
    """Invalid/stale observations must block dispatch, not weaken a gate."""


def _require(value: bool, message: str) -> None:
    if not value:
        raise PolicyInputError(message)


def _integer(value: int, name: str, *, minimum: int = 0) -> None:
    _require(type(value) is int and minimum <= value <= 2**63 - 1,
             f"{name} must be a bounded native integer >= {minimum}")


def _fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PolicyConfig:
    max_workers: int = 3
    planning_private_bytes: int = 7 * GIB // 2
    planning_working_set_bytes: int = GIB
    commit_reserve_bytes: int = GIB
    physical_reserve_bytes: int = GIB
    observed_peak_margin_bytes: int = 256 * MIB
    consecutive_admission_samples: int = 3
    consecutive_pressure_samples: int = 3
    minimum_sample_spacing_ms: int = 10_000
    scale_cooldown_ms: int = 60_000
    maximum_sample_age_ms: int = 30_000

    def __post_init__(self) -> None:
        _integer(self.max_workers, "max_workers", minimum=1)
        _require(self.max_workers <= 3, "Researcher authorization permits at most 3 workers")
        for name in ("planning_private_bytes", "planning_working_set_bytes",
                     "commit_reserve_bytes", "physical_reserve_bytes",
                     "observed_peak_margin_bytes", "minimum_sample_spacing_ms",
                     "scale_cooldown_ms", "maximum_sample_age_ms"):
            _integer(getattr(self, name), name, minimum=1)
        _require(self.planning_private_bytes >= 7 * GIB // 2,
                 "Do not weaken the reviewed 3.5 GiB private-memory floor")
        _require(self.commit_reserve_bytes >= GIB and self.physical_reserve_bytes >= GIB,
                 "Commit and physical reserves must each remain at least 1 GiB")
        for name in ("consecutive_admission_samples", "consecutive_pressure_samples"):
            _integer(getattr(self, name), name, minimum=3)
        _require(self.maximum_sample_age_ms >= self.minimum_sample_spacing_ms,
                 "Freshness window must accommodate distinct observations")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True)
class ResourceSample:
    """Free commit is system commit headroom, not process virtual address space."""
    sampled_monotonic_ms: int
    free_commit_bytes: int
    total_commit_bytes: int
    free_physical_bytes: int
    total_physical_bytes: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _integer(getattr(self, name), name)
        _require(self.total_commit_bytes > 0 and self.total_physical_bytes > 0,
                 "Positive system capacities required")
        _require(self.free_commit_bytes <= self.total_commit_bytes and
                 self.free_physical_bytes <= self.total_physical_bytes,
                 "Free memory exceeds reported system capacity")


@dataclass(frozen=True)
class WorkerObservation:
    """One scientific process identity; do not count its launcher twice.

    IDLE means the previous trajectory was fully published and validated, with
    no currently claimed task. BUSY/DRAINING never authorize termination. Peak
    counters must come from native memory counters, not loss or model rankings.
    """
    worker_id: str
    phase: str
    private_bytes: int
    peak_private_bytes: int
    working_set_bytes: int
    peak_working_set_bytes: int

    def __post_init__(self) -> None:
        _require(isinstance(self.worker_id, str) and
                 re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.worker_id) is not None,
                 "Safe, nonempty unique worker identity required")
        _require(self.phase in PHASES, "Unrecognized worker phase")
        for name in ("private_bytes", "peak_private_bytes", "working_set_bytes", "peak_working_set_bytes"):
            _integer(getattr(self, name), name)
        _require(self.peak_private_bytes >= self.private_bytes and
                 self.peak_working_set_bytes >= self.working_set_bytes,
                 "Worker peak counters cannot be smaller than current counters")
        _require(self.phase == "STARTING" or self.private_bytes > 0,
                 "Running worker requires actual private-memory observation")


@dataclass(frozen=True)
class PolicyState:
    config_fingerprint: str | None = None
    last_sample_monotonic_ms: int | None = None
    last_sample_fingerprint: str | None = None
    last_counted_sample_ms: int | None = None
    last_scale_monotonic_ms: int | None = None
    healthy_streak: int = 0
    pressure_streak: int = 0
    private_peak_bytes: int = 0
    working_set_peak_bytes: int = 0
    worker_ids: tuple[str, ...] = ()
    pending_admission_from_ids: tuple[str, ...] | None = None
    draining_worker_id: str | None = None


@dataclass(frozen=True)
class ResourceGate:
    per_worker_private_budget_bytes: int
    per_worker_working_set_budget_bytes: int
    admission_free_commit_required_bytes: int
    admission_free_physical_required_bytes: int
    pressure_free_commit_threshold_bytes: int
    pressure_free_physical_threshold_bytes: int
    free_commit_bytes: int
    free_physical_bytes: int
    admission_memory_pass: bool
    pressure_present: bool
    distinct_counted_sample: bool
    cooldown_pass: bool
    config_fingerprint: str


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str
    admit_count: int
    drain_worker_id: str | None
    retire_worker_id: str | None
    dispatch_allowed: bool
    observed_workers: int
    target_worker_count: int
    resource_gate: ResourceGate
    next_state: PolicyState
    model_outcomes_used: bool = False
    in_flight_termination_permitted: bool = False


def _validate_state(state: PolicyState, config: PolicyConfig, now: int) -> None:
    _require(type(state) is PolicyState, "Exact PolicyState required")
    _require(state.config_fingerprint in (None, config.fingerprint),
             "Resource policy changed mid-run; require a separate reviewed policy epoch")
    for name in ("healthy_streak", "pressure_streak", "private_peak_bytes", "working_set_peak_bytes"):
        _integer(getattr(state, name), name)
    for name in ("last_sample_monotonic_ms", "last_counted_sample_ms", "last_scale_monotonic_ms"):
        value = getattr(state, name)
        if value is not None:
            _integer(value, name)
            _require(value <= now, "Policy state timestamp lies in the future")
    _require(tuple(sorted(set(state.worker_ids))) == state.worker_ids,
             "Policy worker identities must be a unique sorted tuple")
    if state.pending_admission_from_ids is not None:
        _require(tuple(sorted(set(state.pending_admission_from_ids))) == state.pending_admission_from_ids,
                 "Pending admission identities malformed")
    _require(not (state.draining_worker_id is not None and state.pending_admission_from_ids is not None),
             "Admission and retirement cannot be pending simultaneously")


def decide(config: PolicyConfig, state: PolicyState, sample: ResourceSample,
           workers: Sequence[WorkerObservation], *, now_monotonic_ms: int,
           unclaimed_tasks: int) -> PolicyDecision:
    """Return one outcome-blind scheduling intent and an immutable next state.

    No I/O occurs. Invalid or stale evidence raises PolicyInputError so the
    caller must fail closed without dispatch. Commit/physical pressure blocks
    new trajectory claims immediately, even during cooldown or hysteresis.
    A requested drain must be respected by the caller until a validated IDLE
    boundary; only then may RETIRE_AT_BOUNDARY be applied. Never kill BUSY.
    """
    _require(type(config) is PolicyConfig and type(sample) is ResourceSample,
             "Exact policy configuration and native resource sample required")
    _integer(now_monotonic_ms, "now_monotonic_ms")
    _integer(unclaimed_tasks, "unclaimed_tasks")
    _validate_state(state, config, now_monotonic_ms)
    age = now_monotonic_ms - sample.sampled_monotonic_ms
    _require(0 <= age <= config.maximum_sample_age_ms, "Resource observation is stale or future-dated")
    _require(isinstance(workers, (tuple, list)) and all(type(w) is WorkerObservation for w in workers),
             "Explicit worker observations required")
    ordered = tuple(sorted(workers, key=lambda w: w.worker_id))
    ids = tuple(w.worker_id for w in ordered)
    _require(len(ids) == len(set(ids)) and len(ids) <= config.max_workers,
             "Duplicate worker identity or authorized worker count exceeded")
    observed_count = len(ids)
    fingerprint = _fingerprint(asdict(sample))
    if state.last_sample_monotonic_ms is not None:
        _require(sample.sampled_monotonic_ms >= state.last_sample_monotonic_ms,
                 "Native resource sample moved backwards")
        if sample.sampled_monotonic_ms == state.last_sample_monotonic_ms:
            _require(fingerprint == state.last_sample_fingerprint,
                     "Same sample timestamp has conflicting resource counters")
    private_peak = max((state.private_peak_bytes, *(w.peak_private_bytes for w in ordered)))
    working_peak = max((state.working_set_peak_bytes, *(w.peak_working_set_bytes for w in ordered)))
    private_budget = max(config.planning_private_bytes, private_peak + config.observed_peak_margin_bytes)
    working_budget = max(config.planning_working_set_bytes, working_peak + config.observed_peak_margin_bytes)
    previous_private_budget = max(config.planning_private_bytes, state.private_peak_bytes + config.observed_peak_margin_bytes)
    previous_working_budget = max(config.planning_working_set_bytes, state.working_set_peak_bytes + config.observed_peak_margin_bytes)
    healthy = (sample.free_commit_bytes >= private_budget + config.commit_reserve_bytes and
               sample.free_physical_bytes >= working_budget + config.physical_reserve_bytes)
    pressure = (sample.free_commit_bytes < config.commit_reserve_bytes or
                sample.free_physical_bytes < config.physical_reserve_bytes)
    changed_population = ids != state.worker_ids
    larger_budget = private_budget > previous_private_budget or working_budget > previous_working_budget
    distinct = (state.last_counted_sample_ms is None or
                sample.sampled_monotonic_ms - state.last_counted_sample_ms >= config.minimum_sample_spacing_ms)
    high = 0 if changed_population or larger_budget else state.healthy_streak
    low = 0 if changed_population or larger_budget else state.pressure_streak
    if distinct:
        high = high + 1 if healthy else 0
        low = low + 1 if pressure else 0
    else:
        # A noisy/duplicate sample cannot advance stabilization; a newly failed
        # gate still cancels its previous favorable streak immediately.
        if not healthy:
            high = 0
        if not pressure:
            low = 0
    pending_admission = state.pending_admission_from_ids
    if pending_admission is not None and set(ids) - set(pending_admission):
        pending_admission = None
        high = low = 0
    draining = state.draining_worker_id
    last_scale = state.last_scale_monotonic_ms
    if draining is not None and draining not in ids:
        draining = None
        last_scale = now_monotonic_ms
        high = low = 0
    updated = replace(state, config_fingerprint=config.fingerprint,
        last_sample_monotonic_ms=sample.sampled_monotonic_ms,
        last_sample_fingerprint=fingerprint,
        last_counted_sample_ms=sample.sampled_monotonic_ms if distinct else state.last_counted_sample_ms,
        last_scale_monotonic_ms=last_scale, healthy_streak=high, pressure_streak=low,
        private_peak_bytes=private_peak, working_set_peak_bytes=working_peak,
        worker_ids=ids, pending_admission_from_ids=pending_admission, draining_worker_id=draining)
    cooldown = last_scale is None or now_monotonic_ms - last_scale >= config.scale_cooldown_ms
    gate = ResourceGate(private_budget, working_budget,
        private_budget + config.commit_reserve_bytes, working_budget + config.physical_reserve_bytes,
        config.commit_reserve_bytes, config.physical_reserve_bytes,
        sample.free_commit_bytes, sample.free_physical_bytes, healthy, pressure, distinct, cooldown,
        config.fingerprint)
    dispatch = not pressure and unclaimed_tasks > 0

    def result(action: str, reason: str, *, admit: int = 0, drain: str | None = None,
               retire: str | None = None, target: int | None = None,
               new_state: PolicyState | None = None) -> PolicyDecision:
        return PolicyDecision(action, reason, admit, drain, retire, dispatch, observed_count,
            observed_count if target is None else target, gate, updated if new_state is None else new_state)

    if draining is not None:
        worker = next(w for w in ordered if w.worker_id == draining)
        if worker.phase == "IDLE":
            return result("RETIRE_AT_BOUNDARY", "Previously drained worker reached a validated trajectory boundary",
                retire=draining, target=observed_count - 1,
                new_state=replace(updated, last_scale_monotonic_ms=now_monotonic_ms, healthy_streak=0, pressure_streak=0))
        return result("WAIT_FOR_DRAIN_BOUNDARY", "Keep the in-flight trajectory intact; prohibit this worker's next claim",
                      drain=draining, target=observed_count - 1)
    if pending_admission is not None:
        _require(observed_count < config.max_workers, "Pending admission would exceed authorized maximum")
        return result("WAIT_FOR_START", "One admission slot remains reserved until its new process identity is observed",
                      target=observed_count + 1)
    if pressure:
        if observed_count == 0:
            return result("WAIT_FOR_MEMORY", "No worker starts while either reserve is depleted", target=0)
        if low >= config.consecutive_pressure_samples and cooldown:
            # Choose by native memory only. Prefer an idle worker so no current
            # model work is interrupted; then choose greatest current commit.
            eligible = [w for w in ordered if w.phase != "STARTING"]
            if eligible:
                selected = min(eligible, key=lambda w: (w.phase != "IDLE", -w.private_bytes, w.worker_id))
                marked = replace(updated, draining_worker_id=selected.worker_id, healthy_streak=0, pressure_streak=0)
                if selected.phase == "IDLE":
                    return result("RETIRE_AT_BOUNDARY", "Sustained reserve pressure; retire an idle worker without touching a trajectory",
                        retire=selected.worker_id, target=observed_count - 1,
                        new_state=replace(marked, last_scale_monotonic_ms=now_monotonic_ms))
                return result("DRAIN_ONE", "Sustained reserve pressure; finish this trajectory before retirement",
                    drain=selected.worker_id, target=observed_count - 1, new_state=marked)
        return result("HOLD_PRESSURE", "Block new trajectory claims; await distinct pressure samples/cooldown or a safe boundary")
    if unclaimed_tasks == 0:
        return result("HOLD", "No unclaimed predeclared trajectories remain; add no worker")
    if observed_count >= config.max_workers:
        return result("HOLD", "Authorized maximum already observed")
    if any(w.phase in {"STARTING", "DRAINING"} for w in ordered):
        return result("HOLD", "Wait for startup/drain completion before any additional scale action")
    if healthy and high >= config.consecutive_admission_samples and cooldown:
        return result("ADMIT_ONE", "Both resource gates passed distinct repeated samples after cooldown",
            admit=1, target=observed_count + 1,
            new_state=replace(updated, pending_admission_from_ids=ids,
                              last_scale_monotonic_ms=now_monotonic_ms, healthy_streak=0, pressure_streak=0))
    return result("WAIT_FOR_MEMORY" if observed_count == 0 else "HOLD",
                  "Admission needs both high watermarks, distinct repeated samples, and cooldown")
