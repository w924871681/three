"""Synthetic-only tests. No original project package, generator or model import.

An authorized isolated test harness provides the approved NumPy dependency.
These tests construct small fake segment/container code and synthetic arrays;
they never open the canonical input publication or model checkpoints.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np


_spec = importlib.util.spec_from_file_location("paper3_stage_c_fixed_synthetic", Path(__file__).with_name("fixed_inputs.py"))
fixed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixed)


class SyntheticSegment:
    def __init__(self, x, y, ts, role):
        self.x, self.y, self.ts, self.role = x, y, ts, role

    @property
    def hash(self):
        return fixed._legacy_digest(self.x, self.y, self.ts)


class SyntheticTimeline:
    def __init__(self, x, y, ts, scenario, center_id):
        self._x, self._y, self._ts = x.copy(), y.copy(), ts.copy()
        for array in (self._x, self._y, self._ts):
            array.flags.writeable = False
        self.scenario, self.center_id = scenario, center_id
        self._decisions = set()

    def _segment(self, bounds, role):
        a, b = bounds
        return SyntheticSegment(self._x[a:b].copy(), self._y[a:b].copy(), self._ts[a:b].copy(), role)

    def seal_decision(self, stage):
        self._decisions.add(stage)


class FixedTimelineSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.x = np.zeros((17000, 25), dtype=np.float32)
        self.y = np.arange(17000, dtype=np.float32) / np.float32(17000)
        self.ts = 8 + np.arange(17000, dtype=np.int64)
        self.roles = {}
        for stage in range(1, 25):
            for role, span in zip(fixed.ROLES, fixed._spans(stage)):
                a, b = span
                self.roles[(stage, role)] = {"stage": stage, "legacy_role_hash": fixed._legacy_digest(self.x[a:b], self.y[a:b], self.ts[a:b])}
        self.references = {}
        for role, (a, b) in (("warmup", (0, 800)), ("reference", (800, 1000))):
            self.references[role] = {"legacy_role_hash": fixed._legacy_digest(self.x[a:b], self.y[a:b], self.ts[a:b])}
        self.diagnostic_path = Path(__file__).with_name("synthetic_frozen_offline.py").resolve()
        self.timeline = fixed._audit_timeline_type(SyntheticTimeline)(
            self.x, self.y, self.ts, "C0", 33000, roles=self.roles,
            references=self.references, diagnostic_path=self.diagnostic_path)

    def diagnostic(self, stage, requested=None):
        # Only a synthetic function/code filename; no historical source executed.
        code = "def offline_labels(timeline, stage, requested):\n    timeline.decision_data(stage)\n    return timeline.offline_service(requested, oracle_mode=True)\n"
        namespace = {}
        exec(compile(code, str(self.diagnostic_path), "exec"), namespace)
        return namespace["offline_labels"](self.timeline, stage, stage if requested is None else requested)

    def test_complete_order_and_24_stage_hashes(self):
        self.assertEqual(self.timeline.warmup().hash, self.references["warmup"]["legacy_role_hash"])
        self.assertEqual(self.timeline._segment((800, 1000), "assessment").hash, self.references["reference"]["legacy_role_hash"])
        for stage in range(1, 25):
            update, assessment = self.timeline.decision_data(stage)
            self.assertEqual(update.hash, self.roles[(stage, "update")]["legacy_role_hash"])
            self.assertEqual(assessment.hash, self.roles[(stage, "assessment")]["legacy_role_hash"])
            self.timeline.seal_decision(stage)
            self.assertEqual(self.timeline.service(stage).hash, self.roles[(stage, "service")]["legacy_role_hash"])
        evidence = self.timeline.get_access_evidence()
        self.assertEqual(evidence["completed_stages"], 24)
        self.assertEqual(evidence["violation_count"], 0)

    def test_service_before_seal_is_rejected(self):
        self.timeline.decision_data(1)
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.timeline.service(1)
        self.assertEqual(self.timeline.get_access_evidence()["violation_count"], 1)

    def test_direct_future_and_nonsequential_stage_rejected(self):
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.timeline._segment(fixed._spans(2)[2], "service")
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.timeline.decision_data(2)

    def test_oracle_marker_alone_does_not_authorize_future(self):
        self.timeline.decision_data(1)
        self.timeline.seal_decision(1)
        self.timeline.service(1)
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.timeline.offline_service(2, oracle_mode=True)

    def test_frozen_diagnostic_after_service_is_recorded(self):
        self.timeline.decision_data(1)
        self.timeline.seal_decision(1)
        self.timeline.service(1)
        segment = self.diagnostic(1, 4)
        self.assertEqual(segment.role, "offline_oracle_service")
        self.assertEqual(segment.hash, self.roles[(4, "service")]["legacy_role_hash"])
        evidence = self.timeline.get_access_evidence()
        oracle = [e for e in evidence["events"] if e.get("purpose") == "offline_oracle_after_commit"]
        self.assertEqual(len(oracle), 1)
        self.assertTrue(oracle[0]["current_decision_sealed"])
        self.assertEqual(oracle[0]["requested_stage"], 4)
        self.assertEqual(evidence["completed_stages"], 1)

    def test_frozen_diagnostic_before_commit_is_rejected(self):
        self.timeline.decision_data(1)
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.diagnostic(1, 2)

    def test_frozen_diagnostic_horizon_cannot_expand(self):
        self.timeline.decision_data(1)
        self.timeline.seal_decision(1)
        self.timeline.service(1)
        with self.assertRaises(fixed.FixedInputIntegrityError):
            self.diagnostic(1, 5)

    def test_returned_original_segment_remains_independent_copy(self):
        warmup = self.timeline.warmup()
        warmup.x[0, 0] = np.float32(1)
        self.assertEqual(self.timeline._x[0, 0], np.float32(0))
        self.assertFalse(self.timeline._x.flags.writeable)


class MetadataSyntheticTests(unittest.TestCase):
    def test_tagged_array_dtype_shape_and_read_only_restored(self):
        item = {fixed.ARRAY_TAG: True, "dtype_str": ">f8", "shape": [2], "data": [0.125, 0.5]}
        array = fixed._restore_metadata(item)
        self.assertEqual(array.dtype.str, ">f8")
        self.assertEqual(array.shape, (2,))
        self.assertFalse(array.flags.writeable)
        self.assertEqual(float(array[0]), 0.125)

    def test_bad_tag_shape_object_and_extra_fields_rejected(self):
        cases = [
            {fixed.ARRAY_TAG: True, "dtype_str": "<f4", "shape": [3], "data": [1, 2]},
            {fixed.ARRAY_TAG: True, "dtype_str": "|O", "shape": [1], "data": [1]},
            {fixed.ARRAY_TAG: True, "dtype_str": "<f4", "shape": [1], "data": [1], "extra": 0},
        ]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(fixed.FixedInputIntegrityError):
                fixed._restore_metadata(item)


if __name__ == "__main__":
    unittest.main()
