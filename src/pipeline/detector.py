from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.types import BoundingBox, Detection, VehicleClass


VEHICLE_CLASSES = {item.value for item in VehicleClass}


class YoloDetector:
    def __init__(self, model_path: str | Path, confidence_threshold: float = 0.35,
                 image_size: int = 640) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
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
        results = self._model.predict(
            source=image,
            conf=self.confidence_threshold,
            imgsz=self.image_size,
            verbose=False,
        )
        if not results:
            return []
        names = getattr(self._model, "names", {})
        return detections_from_result(results[0], names)


def detections_from_result(result: Any, names: dict[int, str]) -> list[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    xyxy_rows = _to_list(boxes.xyxy)
    class_ids = [int(value) for value in _to_list(boxes.cls)]
    scores = [float(value) for value in _to_list(boxes.conf)]

    detections: list[Detection] = []
    for xyxy, class_id, score in zip(xyxy_rows, class_ids, scores):
        class_name = str(names.get(class_id, class_id))
        if class_name not in VEHICLE_CLASSES:
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

