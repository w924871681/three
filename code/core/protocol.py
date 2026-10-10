from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .common import array_digest


def spans(stage: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    if not 1 <= stage <= 24:
        raise ValueError(stage)
    boundary = 1400 + (stage - 1) * 640
    update = (1000, 1400) if stage == 1 else (boundary - 400, boundary)
    assessment = (boundary, boundary + 240)
    service = (boundary + 240, boundary + 640)
    return update, assessment, service


@dataclass
class Segment:
    x: np.ndarray
    y: np.ndarray
    ts: np.ndarray
    role: str

    @property
    def hash(self) -> str:
        return array_digest(self.x, self.y, self.ts)

    def copy(self, role: str | None = None) -> "Segment":
        return Segment(self.x.copy(), self.y.copy(), self.ts.copy(), role or self.role)


def windows(segment: Segment, length: int = 96) -> tuple[np.ndarray, np.ndarray]:
    count = len(segment.y) - length
    if count <= 0:
        raise ValueError("segment too short for role-contained windowing")
    x = np.lib.stride_tricks.sliding_window_view(segment.x, length, axis=0)[:count]
    x = x.transpose(0, 2, 1).copy()
    y = segment.y[length:, None].copy()
    return x, y


class CausalTimeline:
    def __init__(self, x: np.ndarray, y: np.ndarray, ts: np.ndarray, scenario: str, center_id: int):
        self._x = x.copy()
        self._y = y.copy()
        self._ts = ts.copy()
        for value in (self._x, self._y, self._ts):
            value.flags.writeable = False
        self.scenario = scenario
        self.center_id = center_id
        self._decisions: set[int] = set()

    def _segment(self, bounds: tuple[int, int], role: str) -> Segment:
        a, b = bounds
        return Segment(self._x[a:b].copy(), self._y[a:b].copy(), self._ts[a:b].copy(), role)

    def warmup(self) -> Segment:
        return self._segment((0, 800), "warmup")

    def decision_data(self, stage: int) -> tuple[Segment, Segment]:
        update, assessment, _ = spans(stage)
        return self._segment(update, "update"), self._segment(assessment, "assessment")

    def seal_decision(self, stage: int) -> None:
        self._decisions.add(stage)

    def service(self, stage: int) -> Segment:
        if stage not in self._decisions:
            raise PermissionError("service data unavailable before stage decision is sealed")
        return self._segment(spans(stage)[2], "service")

    def offline_service(self, stage: int, *, oracle_mode: bool) -> Segment:
        if not oracle_mode:
            raise PermissionError("future service access is restricted to explicit offline oracle mode")
        return self._segment(spans(stage)[2], "offline_oracle_service")
