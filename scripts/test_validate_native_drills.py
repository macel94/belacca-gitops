#!/usr/bin/env python3
"""Deterministic tests for the native drill evidence validator."""

from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import validate_native_drills as validator


ROOT = SCRIPT_DIR.parent
EVIDENCE = ROOT / "docs" / "NATIVE-DRILL-EVIDENCE.json"


class NativeDrillEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_checked_in_ledger_is_pending_without_measurements(self) -> None:
        summary = validator.validate_document(self.document)
        self.assertEqual(summary["comparable_measurements"], 0)
        self.assertIsNone(summary["p95_seconds"])
        self.assertEqual(summary["p95_status"], "not_available")
        self.assertEqual(summary["acceptance_status"], "pending")

    def test_nearest_rank_p95_with_three_completed_passes(self) -> None:
        for item, duration in zip(self.document["measurements"], (100, 200, 300)):
            self._complete(item, duration)
        summary = validator.validate_document(self.document)
        self.assertEqual(summary["durations_seconds"], [100.0, 200.0, 300.0])
        self.assertEqual(summary["p95_seconds"], 300.0)
        self.assertEqual(summary["p95_status"], "under_target")
        self.assertEqual(summary["acceptance_status"], "passed")

    def test_p95_miss_requires_postmortem(self) -> None:
        for index, (item, duration) in enumerate(zip(self.document["measurements"], (100, 200, 360))):
            status = "missed" if index == 2 else "passed"
            self._complete(item, duration, status=status)
            if status == "missed":
                item["postmortem_reference"] = "https://github.com/macel94/belacca-gitops/issues/10#issuecomment-1"
        summary = validator.validate_document(self.document)
        self.assertEqual(summary["p95_seconds"], 360.0)
        self.assertEqual(summary["p95_status"], "missed")
        self.assertEqual(summary["acceptance_status"], "corrective_action_required")

    def test_completed_measurement_must_match_utc_timestamps(self) -> None:
        self._complete(self.document["measurements"][0], 100)
        self.document["measurements"][0]["timings"]["recovery_seconds"] = 99
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def test_completed_measurement_requires_approved_evidence_host(self) -> None:
        self._complete(self.document["measurements"][0], 100)
        self.document["measurements"][0]["evidence_references"] = ["http://example.invalid/report"]
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def test_required_checks_must_finish_before_recovery_stop(self) -> None:
        self._complete(self.document["measurements"][0], 100)
        self.document["measurements"][0]["verification"]["flux_ready"]["observed_at"] = "2026-01-01T12:01:41.000Z"
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def test_target_must_use_the_scenario_pinned_api(self) -> None:
        self.document["measurements"][0]["target"]["pinned_api_endpoint"] = "https://169.58.143.41:6443"
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def test_completed_measurement_requires_baseline_and_recovery_observations(self) -> None:
        self._complete(self.document["measurements"][0], 100)
        self.document["measurements"][0]["recovery"] = None
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def test_pending_measurement_cannot_include_timing_or_evidence(self) -> None:
        item = self.document["measurements"][0]
        item["timings"]["recovery_seconds"] = 10
        item["evidence_references"] = ["https://github.com/macel94/belacca-gitops/issues/10"]
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(self.document)

    def _complete(self, item: dict, duration: int, *, status: str = "passed") -> None:
        start = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        stop = start + dt.timedelta(seconds=duration)
        item["status"] = status
        item["mutation_executed"] = True
        item["approval"] = {
            "status": "approved",
            "reference": "https://github.com/macel94/belacca-gitops/issues/10#issuecomment-1",
            "approved_by": "incident commander",
            "window_start": start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "window_end": (start + dt.timedelta(minutes=30)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        start_text = start.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        stop_text = stop.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        item["timings"] = {
            "fault_injection_confirmed_at": start_text,
            "recovery_verified_at": stop_text,
            "recovery_seconds": duration,
        }
        item["baseline"] = {"status": "pass", "observed_at": start_text}
        item["recovery"] = {"status": "pass", "observed_at": stop_text}
        observed = stop_text
        item["verification"] = {
            name: {
                "status": "pass",
                "observed_at": observed,
                "evidence_reference": "https://github.com/macel94/belacca-gitops/issues/10#issuecomment-1",
            }
            for name in validator.REQUIRED_CHECKS
        }
        item["infrastructure_report"] = "https://github.com/macel94/belacca-infrastructure/blob/main/docs/NATIVE-FAILURE-DRILL-STATUS.md"
        item["evidence_references"] = ["https://github.com/macel94/belacca-gitops/issues/10#issuecomment-1"]
        item["notes"] = "Sanitized deterministic test record."
        item["postmortem_reference"] = None
        self.document["summary"] = validator.calculate_summary(self.document)


if __name__ == "__main__":
    unittest.main()
