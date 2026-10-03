from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.core.config import load_config


class ConfigTests(TestCase):
    def test_load_default_config(self) -> None:
        config = load_config("configs/default.yaml")

        self.assertEqual(config.model.path.parent.name, "models")
        self.assertEqual(config.model.confidence_threshold, 0.35)
        self.assertEqual(config.tracker.max_distance_px, 80.0)
        self.assertEqual(config.toll_prices["truck"], 2.5)
        self.assertEqual(config.counting_lines[0].name, "main")

    def test_load_default_config_speed_block(self) -> None:
        config = load_config("configs/default.yaml")

        self.assertTrue(config.speed.enabled)
        self.assertEqual(config.speed.calibration_path.name, "calibration.json")
        self.assertEqual(config.speed.hysteresis_kph, 3.0)
        self.assertEqual(config.speed.smoothing_alpha, 0.3)
        self.assertEqual(config.speed_limit_kph, 80.0)

    def test_speed_defaults_apply_without_a_speed_block(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "minimal.yaml"
            config_path.write_text("model:\n  path: models/yolo11n.pt\n", encoding="utf-8")

            config = load_config(config_path)

            self.assertTrue(config.speed.enabled)
            self.assertIsNone(config.speed.calibration_path)
            self.assertEqual(config.speed.hysteresis_kph, 3.0)
            self.assertEqual(config.speed.smoothing_alpha, 0.3)

    def test_speed_can_be_disabled(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "off.yaml"
            config_path.write_text("speed:\n  enabled: false\n", encoding="utf-8")

            self.assertFalse(load_config(config_path).speed.enabled)

    def test_relative_paths_resolve_from_project_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "configs"
            config_dir.mkdir()
            config_path = config_dir / "default.yaml"
            config_path.write_text(
                "video:\n"
                "  input: data/raw/demo.mp4\n"
                "  output: runs/out.mp4\n"
                "  report: runs/report.json\n"
                "model:\n"
                "  path: models/yolo11n.pt\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual(config.video.input_path.resolve(), (root / "data" / "raw" / "demo.mp4").resolve())
            self.assertEqual(config.model.path.resolve(), (root / "models" / "yolo11n.pt").resolve())
