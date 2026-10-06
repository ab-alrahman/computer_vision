from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class VideoConfig:
    input_path: Path
    output_path: Path
    report_path: Path


@dataclass(frozen=True)
class ModelConfig:
    path: Path
    confidence_threshold: float
    image_size: int
    class_thresholds: dict[str, float]


@dataclass(frozen=True)
class CountingLineConfig:
    name: str
    points: tuple[tuple[int, int], tuple[int, int]]
    inbound_when_crossing: str
    deadband_px: float


@dataclass(frozen=True)
class RuntimeConfig:
    max_frames: int | None
    display: bool


@dataclass(frozen=True)
class TrackerConfig:
    max_distance_px: float
    max_lost_frames: int


@dataclass(frozen=True)
class SpeedConfig:
    enabled: bool
    calibration_path: Path | None
    hysteresis_kph: float
    smoothing_alpha: float
    position_alpha: float
    min_step_meters: float
    max_plausible_kph: float


@dataclass(frozen=True)
class EnhancementConfig:
    enabled: bool
    denoise: bool
    denoise_diameter: int
    denoise_sigma_color: float
    denoise_sigma_space: float
    clahe: bool
    clahe_clip_limit: float
    clahe_grid: int
    sharpen: bool
    sharpen_radius: float
    sharpen_amount: float


@dataclass(frozen=True)
class AppConfig:
    video: VideoConfig
    model: ModelConfig
    tracker: TrackerConfig
    speed: SpeedConfig
    enhancement: EnhancementConfig
    class_colors: dict[str, tuple[int, int, int]]
    toll_prices: dict[str, float]
    counting_lines: list[CountingLineConfig]
    speed_limit_kph: float
    runtime: RuntimeConfig


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _as_color(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError(f"expected BGR color triplet, got {value!r}")
    return tuple(int(part) for part in value)


def _as_line(raw: dict[str, Any]) -> CountingLineConfig:
    points = raw.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError(f"counting line needs two points, got {points!r}")
    parsed = tuple((int(point[0]), int(point[1])) for point in points)
    deadband_px = float(raw.get("deadband_px", 0.0))
    if deadband_px < 0.0:
        raise ValueError(f"counting line deadband_px must be >= 0, got {deadband_px}")
    return CountingLineConfig(
        name=str(raw.get("name", "main")),
        points=parsed,  # type: ignore[arg-type]
        inbound_when_crossing=str(raw.get("inbound_when_crossing", "top_to_bottom")),
        deadband_px=deadband_px,
    )


def _as_speed(raw: dict[str, Any], base_dir: Path) -> SpeedConfig:
    calibration = raw.get("calibration")
    calibration_path = _resolve_path(calibration, base_dir) if calibration else None
    return SpeedConfig(
        enabled=bool(raw.get("enabled", True)),
        calibration_path=calibration_path,
        hysteresis_kph=float(raw.get("hysteresis_kph", 3.0)),
        smoothing_alpha=float(raw.get("smoothing_alpha", 0.3)),
        position_alpha=float(raw.get("position_alpha", 0.3)),
        min_step_meters=float(raw.get("min_step_meters", 0.15)),
        max_plausible_kph=float(raw.get("max_plausible_kph", 160.0)),
    )


def _as_enhancement(raw: dict[str, Any]) -> EnhancementConfig:
    clahe_grid = int(raw.get("clahe_grid", 8))
    if clahe_grid < 1:
        raise ValueError(f"enhancement clahe_grid must be >= 1, got {clahe_grid}")
    denoise_diameter = int(raw.get("denoise_diameter", 5))
    if denoise_diameter <= 0 or denoise_diameter % 2 == 0:
        raise ValueError(f"enhancement denoise_diameter must be a positive odd number, got {denoise_diameter}")
    return EnhancementConfig(
        enabled=bool(raw.get("enabled", True)),
        denoise=bool(raw.get("denoise", True)),
        denoise_diameter=denoise_diameter,
        denoise_sigma_color=float(raw.get("denoise_sigma_color", 40.0)),
        denoise_sigma_space=float(raw.get("denoise_sigma_space", 40.0)),
        clahe=bool(raw.get("clahe", True)),
        clahe_clip_limit=float(raw.get("clahe_clip_limit", 2.0)),
        clahe_grid=clahe_grid,
        sharpen=bool(raw.get("sharpen", True)),
        sharpen_radius=float(raw.get("sharpen_radius", 3.0)),
        sharpen_amount=float(raw.get("sharpen_amount", 0.6)),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base_dir = config_path.parent.parent

    video_raw = raw.get("video") or {}
    model_raw = raw.get("model") or {}
    tracker_raw = raw.get("tracker") or {}
    runtime_raw = raw.get("runtime") or {}
    speed_raw = raw.get("speed") or {}
    enhancement_raw = raw.get("enhancement") or {}

    return AppConfig(
        video=VideoConfig(
            input_path=_resolve_path(video_raw.get("input", "data/raw/toll_0400_0900.mp4"), base_dir),
            output_path=_resolve_path(video_raw.get("output", "runs/vision/output.mp4"), base_dir),
            report_path=_resolve_path(video_raw.get("report", "runs/vision/report.json"), base_dir),
        ),
        model=ModelConfig(
            path=_resolve_path(model_raw.get("path", "models/yolo11n.pt"), base_dir),
            confidence_threshold=float(model_raw.get("confidence_threshold", 0.35)),
            image_size=int(model_raw.get("image_size", 640)),
            class_thresholds={
                str(name): float(value)
                for name, value in (model_raw.get("class_thresholds") or {}).items()
            },
        ),
        tracker=TrackerConfig(
            max_distance_px=float(tracker_raw.get("max_distance_px", 80.0)),
            max_lost_frames=int(tracker_raw.get("max_lost_frames", 10)),
        ),
        speed=_as_speed(speed_raw, base_dir),
        enhancement=_as_enhancement(enhancement_raw),
        class_colors={
            str(name): _as_color(color)
            for name, color in (raw.get("class_colors") or {}).items()
        },
        toll_prices={
            str(name): float(price)
            for name, price in (raw.get("toll_prices") or {}).items()
        },
        counting_lines=[_as_line(item) for item in raw.get("counting_lines", [])],
        speed_limit_kph=float(raw.get("speed_limit_kph", 80.0)),
        runtime=RuntimeConfig(
            max_frames=runtime_raw.get("max_frames"),
            display=bool(runtime_raw.get("display", False)),
        ),
    )
