from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2

from src.core.types import FrameData


class VideoSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._capture: cv2.VideoCapture | None = None

    def __enter__(self) -> "VideoSource":
        if not self.path.is_file():
            raise FileNotFoundError(f"video file not found: {self.path}")
        self._capture = cv2.VideoCapture(str(self.path))
        if not self._capture.isOpened():
            raise RuntimeError(f"could not open video: {self.path}")
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def fps(self) -> float:
        capture = self._require_capture()
        fps = capture.get(cv2.CAP_PROP_FPS)
        return float(fps) if fps and fps > 0 else 0.0

    @property
    def frame_count(self) -> int:
        return int(self._require_capture().get(cv2.CAP_PROP_FRAME_COUNT))

    def frames(self, max_frames: int | None = None) -> Iterator[FrameData]:
        capture = self._require_capture()
        frame_index = 0
        while max_frames is None or frame_index < max_frames:
            ok, image = capture.read()
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            yield FrameData(
                frame_index=frame_index,
                timestamp_seconds=float(timestamp_ms) / 1000.0,
                image=image,
            )
            frame_index += 1

    def _require_capture(self) -> cv2.VideoCapture:
        if self._capture is None:
            raise RuntimeError("VideoSource must be opened with a context manager")
        return self._capture

