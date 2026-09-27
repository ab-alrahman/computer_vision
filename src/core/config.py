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


@dataclass(frozen=True)
class CountingLineConfig:
    name: str
    points: tuple[tuple[int, int], tuple[int, int]]
    inbound_when_crossing: str


@dataclass(frozen=True)
class RuntimeConfig:
    max_frames: int | None
    display: bool


@dataclass(frozen=True)
class TrackerConfig:
    max_distance_px: float
    max_lost_frames: int


@dataclass(frozen=True)
class AppConfig:
    video: VideoConfig
    model: ModelConfig
    tracker: TrackerConfig
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
    return CountingLineConfig(
        name=str(raw.get("name", "main")),
        points=parsed,  # type: ignore[arg-type]
        inbound_when_crossing=str(raw.get("inbound_when_crossing", "top_to_bottom")),
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
        ),
        tracker=TrackerConfig(
            max_distance_px=float(tracker_raw.get("max_distance_px", 80.0)),
            max_lost_frames=int(tracker_raw.get("max_lost_frames", 10)),
        ),
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
