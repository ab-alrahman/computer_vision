from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.core.types import Direction, EventType, PassageEvent, ViolationEvent
from src.services.report import build_report, write_report


class ReportTests(TestCase):
    def test_builds_counts_and_revenue(self) -> None:
        passages = [
            PassageEvent(1, "car", Direction.INBOUND, 1.0, 10, 0.3),
            PassageEvent(2, "truck", Direction.INBOUND, 2.5, 11, 0.4),
            PassageEvent(3, "car", Direction.OUTBOUND, 1.0, 12, 0.5),
        ]
        violations = [
            ViolationEvent(4, EventType.MOTORCYCLE_VIOLATION, "motorcycle", Direction.OUTBOUND, 13, 0.6)
        ]

        report = build_report(passages, violations)

        self.assertEqual(report["summary"]["totalPassages"], 3)
        self.assertEqual(report["summary"]["totalViolations"], 1)
        self.assertEqual(report["summary"]["totalRevenue"], 4.5)
        self.assertEqual(report["counts"]["INBOUND"]["car"], 1)
        self.assertEqual(report["counts"]["INBOUND"]["truck"], 1)
        self.assertEqual(report["counts"]["OUTBOUND"]["car"], 1)
        self.assertEqual(report["revenueByClass"]["car"], 2.0)
        self.assertEqual(report["violations"][0]["eventType"], "MOTORCYCLE_VIOLATION")
        self.assertEqual(report["speedingTrackIds"], [])
        self.assertNotIn("speedLimitKph", report["summary"])
        self.assertNotIn("maxAverageSpeedKph", report["summary"])

    def test_omits_speed_fields_without_measurements(self) -> None:
        report = build_report([PassageEvent(1, "car", Direction.INBOUND, 1.0, 10, 0.3)], [], 80.0)

        self.assertEqual(report["summary"]["speedLimitKph"], 80.0)
        self.assertNotIn("maxAverageSpeedKph", report["summary"])

    def test_reports_speed_statistics(self) -> None:
        passages = [
            PassageEvent(1, "car", Direction.INBOUND, 1.0, 10, 0.3, 95.0, 88.0),
            PassageEvent(2, "car", Direction.INBOUND, 1.0, 11, 0.4, 40.0, 42.0),
        ]

        report = build_report(passages, [], speed_limit_kph=80.0)

        self.assertEqual(report["summary"]["speedLimitKph"], 80.0)
        self.assertEqual(report["summary"]["maxAverageSpeedKph"], 88.0)
        self.assertEqual(report["summary"]["meanAverageSpeedKph"], 65.0)
        self.assertEqual(report["passages"][0]["speedKph"], 95.0)
        self.assertEqual(report["passages"][0]["averageSpeedKph"], 88.0)

    def test_collects_speeding_track_ids(self) -> None:
        violations = [
            ViolationEvent(9, EventType.SPEED_VIOLATION, "car", Direction.INBOUND, 13, 0.6),
            ViolationEvent(4, EventType.MOTORCYCLE_VIOLATION, "motorcycle", Direction.OUTBOUND, 14, 0.7),
        ]

        report = build_report([], violations)

        self.assertEqual(report["speedingTrackIds"], [9])

    def test_writes_report_json(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "report.json"
            report = build_report([], [])

            written = write_report(target, report)

            self.assertEqual(written, target)
            self.assertTrue(target.is_file())
            loaded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(loaded["summary"]["totalPassages"], 0)

