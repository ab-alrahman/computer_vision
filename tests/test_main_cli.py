from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.core.config import load_config
from src.core.types import Direction, PassageEvent
from src.main import (
    attach_speeds,
    build_speed_monitor,
    positive_float,
    positive_int,
    resolve_max_frames,
    resolve_speed_limit,
)
from src.pipeline.velocity import Homography, TrackSpeed


class MainCliTests(TestCase):
    def test_resolve_max_frames_prefers_cli_value(self) -> None:
        self.assertEqual(resolve_max_frames(5, 20, False), 20)

    def test_resolve_max_frames_can_process_all_frames(self) -> None:
        self.assertIsNone(resolve_max_frames(5, 20, True))

    def test_resolve_max_frames_defaults_to_smoke_run(self) -> None:
        self.assertEqual(resolve_max_frames(None, None, False), 5)

    def test_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    def test_positive_float_accepts_speed_limit(self) -> None:
        self.assertEqual(positive_float("95.5"), 95.5)

    def test_positive_float_rejects_zero(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_float("0")

    def test_resolve_speed_limit_prefers_cli_value(self) -> None:
        self.assertEqual(resolve_speed_limit(80.0, 60.0), 60.0)

    def test_resolve_speed_limit_falls_back_to_config(self) -> None:
        self.assertEqual(resolve_speed_limit(80.0, None), 80.0)

    def test_speed_monitor_is_none_without_calibration_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "missing.yaml"
            config_path.write_text(
                f"speed:\n  enabled: true\n  calibration: {root / 'not-there.json'}\n",
                encoding="utf-8",
            )

            self.assertIsNone(build_speed_monitor(load_config(config_path)))

    def test_speed_monitor_is_none_when_speed_is_disabled(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            homography = Homography.from_corners([(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)], 7.0, 20.0)
            calibration_path = homography.save(root / "calibration.json")
            config_path = root / "off.yaml"
            config_path.write_text(
                f"speed:\n  enabled: false\n  calibration: {calibration_path}\n",
                encoding="utf-8",
            )

            self.assertIsNone(build_speed_monitor(load_config(config_path)))

    def test_speed_monitor_loads_calibration(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            homography = Homography.from_corners([(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)], 7.0, 20.0)
            homography.save(root / "calibration.json")
            config_path = root / "on.yaml"
            config_path.write_text(
                f"speed:\n  enabled: true\n  calibration: {root / 'calibration.json'}"
                "\n  smoothing_alpha: 0.5\n",
                encoding="utf-8",
            )

            monitor = build_speed_monitor(load_config(config_path))

            self.assertIsNotNone(monitor)
            self.assertEqual(monitor.alpha, 0.5)
            self.assertEqual(monitor.homography.reference["widthMeters"], 7.0)


class AttachSpeedsTests(TestCase):
    def test_attach_speeds_copies_measured_values(self) -> None:
        passage = PassageEvent(4, "car", Direction.INBOUND, 0.0, 10, 0.3)
        speeds = {4: TrackSpeed(track_id=4, instant_kph=91.234, average_kph=88.567)}

        enriched = attach_speeds([passage], speeds)

        self.assertEqual(enriched[0].speed_kph, 91.23)
        self.assertEqual(enriched[0].average_speed_kph, 88.57)
        self.assertEqual(passage.speed_kph, 0.0)

    def test_attach_speeds_keeps_passage_without_state(self) -> None:
        passage = PassageEvent(4, "car", Direction.INBOUND, 1.0, 10, 0.3)

        enriched = attach_speeds([passage], {})

        self.assertEqual(enriched[0].speed_kph, 0.0)
        self.assertEqual(enriched[0].amount, 1.0)

