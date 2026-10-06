from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.core.types import Point, Track

KPH = 3.6


@dataclass(frozen=True)
class Homography:
    matrix: np.ndarray
    source_points: tuple[tuple[float, float], ...] = ()
    reference: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_corners(cls, image_points: list[tuple[float, float]],
                     width_meters: float, length_meters: float) -> "Homography":
        if len(image_points) != 4:
            raise ValueError(f"homography needs four image points, got {len(image_points)}")
        if width_meters <= 0 or length_meters <= 0:
            raise ValueError("reference distances must be positive")

        source = np.array(image_points, dtype=np.float32)
        destination = np.array(
            [
                (0.0, 0.0),
                (width_meters, 0.0),
                (width_meters, length_meters),
                (0.0, length_meters),
            ],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(source, destination)
        return cls(
            matrix=matrix,
            source_points=tuple((float(x), float(y)) for x, y in image_points),
            reference={"widthMeters": width_meters, "lengthMeters": length_meters},
        )

    @classmethod
    def load(cls, path: str | Path) -> "Homography":
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"calibration file not found: {target}")
        raw = json.loads(target.read_text(encoding="utf-8"))
        if "matrix" not in raw:
            raise ValueError(f"calibration file has no 'matrix': {target}")
        matrix = np.array(raw["matrix"], dtype=np.float64)
        if matrix.shape != (3, 3):
            raise ValueError(f"calibration matrix must be 3x3, got {matrix.shape}")
        points = raw.get("imagePoints") or ()
        return cls(
            matrix=matrix,
            source_points=tuple((float(x), float(y)) for x, y in points),
            reference={
                key: float(value)
                for key, value in (raw.get("reference") or {}).items()
                if isinstance(value, (int, float))
            },
        )

    def to_dict(self) -> dict:
        return {
            "matrix": [[float(value) for value in row] for row in self.matrix],
            "imagePoints": [[x, y] for x, y in self.source_points],
            "reference": dict(self.reference),
        }

    def save(self, path: str | Path, extra: dict | None = None) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        if extra:
            payload.update(extra)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    @property
    def inverse_matrix(self) -> np.ndarray:
        return np.linalg.inv(self.matrix)

    def project(self, point: Point) -> tuple[float, float]:
        vector = np.array([[[point.x, point.y]]], dtype=np.float64)
        warped = cv2.perspectiveTransform(vector, self.matrix)[0, 0]
        return float(warped[0]), float(warped[1])

    def inverse_project(self, point: Point) -> tuple[float, float]:
        vector = np.array([[[point.x, point.y]]], dtype=np.float64)
        warped = cv2.perspectiveTransform(vector, self.inverse_matrix)[0, 0]
        return float(warped[0]), float(warped[1])

    def distance_meters(self, first: Point, second: Point) -> float:
        first_x, first_y = self.project(first)
        second_x, second_y = self.project(second)
        return float(np.hypot(second_x - first_x, second_y - first_y))


@dataclass
class TrackSpeed:
    track_id: int
    instant_kph: float = 0.0
    average_kph: float = 0.0
    max_kph: float = 0.0
    distance_meters: float = 0.0
    elapsed_seconds: float = 0.0
    samples: int = 0
    last_x: float = 0.0
    last_y: float = 0.0
    last_timestamp: float = 0.0
    smooth_x: float | None = None
    smooth_y: float | None = None


class SpeedMonitor:
    def __init__(self, homography: Homography, alpha: float = 0.3,
                 max_gap_seconds: float = 1.0, max_idle_seconds: float = 30.0,
                 position_alpha: float = 0.3, min_step_meters: float = 0.15,
                 max_plausible_kph: float = 160.0) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"smoothing alpha must be in (0, 1], got {alpha}")
        if not 0.0 < position_alpha <= 1.0:
            raise ValueError(
                f"position_alpha must be in (0, 1], got {position_alpha}")
        if min_step_meters < 0.0:
            raise ValueError(
                f"min_step_meters must be >= 0, got {min_step_meters}")
        if max_plausible_kph <= 0.0:
            raise ValueError(
                f"max_plausible_kph must be positive, got {max_plausible_kph}")
        self.homography = homography
        self.alpha = alpha
        self.max_gap_seconds = max_gap_seconds
        self.max_idle_seconds = max_idle_seconds
        self.position_alpha = position_alpha
        self.min_step_meters = min_step_meters
        self.max_plausible_kph = max_plausible_kph
        self.states: dict[int, TrackSpeed] = {}

    def update(self, tracks: list[Track], timestamp_seconds: float) -> dict[int, TrackSpeed]:
        for track in tracks:
            self._update_track(track, timestamp_seconds)
        self._drop_idle(timestamp_seconds)
        return dict(self.states)

    def speed_for(self, track_id: int) -> TrackSpeed | None:
        return self.states.get(track_id)

    def active_track_ids(self) -> set[int]:
        return {track_id for track_id, state in self.states.items() if state.samples > 1}

    def _update_track(self, track: Track, timestamp_seconds: float) -> None:
        world_x, world_y = self.homography.project(track.centroid)
        state = self.states.get(track.track_id)

        if state is None:
            state = TrackSpeed(track_id=track.track_id)
            self.states[track.track_id] = state

        if state.smooth_x is None or state.smooth_y is None:
            state.smooth_x, state.smooth_y = world_x, world_y
        else:
            state.smooth_x = self._blend(state.smooth_x, world_x)
            state.smooth_y = self._blend(state.smooth_y, world_y)

        delta_t = timestamp_seconds - state.last_timestamp
        if state.samples == 0 or delta_t <= 0:
            self._resync(state, timestamp_seconds)
            return

        if delta_t > self.max_gap_seconds:
            self._resync(state, timestamp_seconds)
            return

        step_meters = float(np.hypot(state.smooth_x - state.last_x,
                                     state.smooth_y - state.last_y))
        state.last_x, state.last_y = state.smooth_x, state.smooth_y
        state.last_timestamp = timestamp_seconds
        state.samples += 1

        if step_meters < self.min_step_meters:
            return

        instant_kph = (step_meters / delta_t) * KPH
        if instant_kph > self.max_plausible_kph:
            return

        state.instant_kph = (
            instant_kph
            if state.instant_kph == 0.0
            else self.alpha * instant_kph + (1.0 - self.alpha) * state.instant_kph
        )
        state.distance_meters += step_meters
        state.elapsed_seconds += delta_t
        state.average_kph = (state.distance_meters / state.elapsed_seconds) * KPH
        state.max_kph = max(state.max_kph, state.instant_kph)

    def _blend(self, previous: float, current: float) -> float:
        return self.position_alpha * current + (1.0 - self.position_alpha) * previous

    def _resync(self, state: TrackSpeed, timestamp_seconds: float) -> None:
        state.last_x = state.smooth_x or 0.0
        state.last_y = state.smooth_y or 0.0
        state.last_timestamp = timestamp_seconds
        state.samples += 1

    def _drop_idle(self, timestamp_seconds: float) -> None:
        stale = [
            track_id
            for track_id, state in self.states.items()
            if timestamp_seconds - state.last_timestamp > self.max_idle_seconds
        ]
        for track_id in stale:
            del self.states[track_id]