from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import cv2

from src.core.types import Track, ViolationEvent
from src.pipeline.geometry import CountingLine


VIOLATION_COLOR = (0, 0, 255)
DEFAULT_COLOR = (255, 255, 255)
COUNTING_LINE_COLOR = (192, 192, 192)


class Annotator:
    def __init__(self, class_colors: dict[str, tuple[int, int, int]]) -> None:
        self.class_colors = class_colors

    def draw(self, image, tracks: list[Track], lines: Iterable[CountingLine],
             violations: list[ViolationEvent], counters: dict[str, int]) -> None:
        violation_track_ids = {event.track_id for event in violations}
        for line in lines:
            draw_counting_line(image, line)
        for track in tracks:
            is_violation = track.track_id in violation_track_ids
            draw_track(image, track, self.color_for(track, is_violation))
        draw_hud(image, counters)

    def color_for(self, track: Track, is_violation: bool = False) -> tuple[int, int, int]:
        if is_violation:
            return VIOLATION_COLOR
        color = self.class_colors.get(track.class_name, DEFAULT_COLOR)
        return color if color != VIOLATION_COLOR else DEFAULT_COLOR


class VideoWriter:
    def __init__(self, path: str | Path, fps: float, frame_size: tuple[int, int]) -> None:
        self.path = Path(path)
        self.fps = fps if fps > 0 else 25.0
        self.frame_size = frame_size
        self._writer: cv2.VideoWriter | None = None

    def __enter__(self) -> "VideoWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(self.path), fourcc, self.fps, self.frame_size)
        if not self._writer.isOpened():
            raise RuntimeError(f"could not open video writer: {self.path}")
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def write(self, image) -> None:
        if self._writer is None:
            raise RuntimeError("VideoWriter must be opened with a context manager")
        self._writer.write(image)


def draw_track(image, track: Track, color: tuple[int, int, int]) -> None:
    box = track.bbox
    p1 = (int(box.x1), int(box.y1))
    p2 = (int(box.x2), int(box.y2))
    cv2.rectangle(image, p1, p2, color, 2)
    label = f"#{track.track_id} {track.class_name} {track.score:.2f}"
    label_origin = (p1[0], max(15, p1[1] - 8))
    cv2.putText(image, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def draw_counting_line(image, line: CountingLine) -> None:
    start = (int(line.start.x), int(line.start.y))
    end = (int(line.end.x), int(line.end.y))
    cv2.line(image, start, end, COUNTING_LINE_COLOR, 3)
    cv2.putText(image, line.name, (start[0], max(15, start[1] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COUNTING_LINE_COLOR, 1, cv2.LINE_AA)


def draw_hud(image, counters: dict[str, int]) -> None:
    y = 24
    for label, value in counters.items():
        cv2.putText(image, f"{label}: {value}", (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 2, cv2.LINE_AA)
        y += 22
