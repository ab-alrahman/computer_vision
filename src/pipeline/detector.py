from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.core.types import BoundingBox, Detection


class YoloDetector:
    def __init__(self, model_path: str | Path, confidence_threshold: float = 0.35,
                 image_size: int = 640,
                 class_thresholds: dict[str, float] | None = None) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.class_thresholds = class_thresholds or {}
        self._model: Any | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.model_path.is_file():
            raise FileNotFoundError(f"model file not found: {self.model_path}")
        from ultralytics import YOLO

        self._model = YOLO(str(self.model_path))

    def detect(self, image: Any) -> list[Detection]:
        self.load()
        floor = min([self.confidence_threshold, *self.class_thresholds.values()],
                    default=self.confidence_threshold)
        results = self._model.predict(
            source=image,
            conf=floor,
            imgsz=self.image_size,
            verbose=False,
        )
        if not results:
            return []
        names = getattr(self._model, "names", {})
        return detections_from_result(results[0], names, self._threshold_for)

    def _threshold_for(self, class_name: str) -> float:
        return self.class_thresholds.get(class_name, self.confidence_threshold)


class MultiModelDetector:
    """Run several YOLO models and keep the strongest non-duplicate boxes."""

    def __init__(self, model_paths: list[str | Path], confidence_threshold: float = 0.35,
                 image_size: int = 640,
                 class_thresholds: dict[str, float] | None = None,
                 iou_threshold: float = 0.5) -> None:
        self.detectors = [
            YoloDetector(path, confidence_threshold, image_size, class_thresholds)
            for path in model_paths
        ]
        self.iou_threshold = iou_threshold

    def detect(self, image: Any) -> list[Detection]:
        detections: list[Detection] = []
        for detector in self.detectors:
            detections.extend(detector.detect(image))
        return merge_detections(detections, self.iou_threshold)


def merge_detections(detections: list[Detection], iou_threshold: float = 0.5) -> list[Detection]:
    """Class-agnostic NMS: overlapping boxes keep the highest confidence one."""
    kept: list[Detection] = []
    for detection in sorted(detections, key=lambda item: item.score, reverse=True):
        if any(_box_iou(detection.bbox, existing.bbox) >= iou_threshold for existing in kept):
            continue
        kept.append(detection)
    return kept


def _box_iou(first: BoundingBox, second: BoundingBox) -> float:
    x1 = max(first.x1, second.x1)
    y1 = max(first.y1, second.y1)
    x2 = min(first.x2, second.x2)
    y2 = min(first.y2, second.y2)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if intersection == 0.0:
        return 0.0
    first_area = max(0.0, first.x2 - first.x1) * max(0.0, first.y2 - first.y1)
    second_area = max(0.0, second.x2 - second.x1) * max(0.0, second.y2 - second.y1)
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def detections_from_result(result: Any, names: dict[int, str],
                           threshold_for: Callable[[str], float] | None = None) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    xyxy_rows = _to_list(boxes.xyxy)
    class_ids = [int(value) for value in _to_list(boxes.cls)]
    scores = [float(value) for value in _to_list(boxes.conf)]

    detections: list[Detection] = []
    for xyxy, class_id, score in zip(xyxy_rows, class_ids, scores):
        class_name = str(names.get(class_id, class_id))
        if threshold_for is not None and score < threshold_for(class_name):
            continue
        x1, y1, x2, y2 = (float(value) for value in xyxy)
        detections.append(
            Detection(
                bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                score=score,
                class_id=class_id,
                class_name=class_name,
            )
        )
    return detections


def _to_list(value: Any) -> list:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)

