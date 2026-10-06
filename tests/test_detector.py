from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

import numpy as np

from src.pipeline.detector import detections_from_result


class FakeBoxes:
    def __init__(self) -> None:
        self.xyxy = np.array([[10, 20, 110, 120], [1, 2, 30, 40]], dtype=float)
        self.cls = np.array([2, 0], dtype=float)
        self.conf = np.array([0.91, 0.77], dtype=float)

    def __len__(self) -> int:
        return 2


class DetectorTests(TestCase):
    def test_converts_yolo_boxes_to_vehicle_detections(self) -> None:
        result = SimpleNamespace(boxes=FakeBoxes())

        detections = detections_from_result(result, {2: "car", 0: "person"})

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].class_name, "car")
        self.assertEqual(detections[0].score, 0.91)
        self.assertEqual(detections[0].bbox.x1, 10)

    def test_returns_empty_list_when_result_has_no_boxes(self) -> None:
        result = SimpleNamespace(boxes=None)

        self.assertEqual(detections_from_result(result, {}), [])


class MixedBoxes:
    """car at high confidence, motorcycle at low confidence."""

    def __init__(self) -> None:
        self.xyxy = np.array([[10, 20, 110, 120], [5, 5, 25, 25]], dtype=float)
        self.cls = np.array([2, 3], dtype=float)
        self.conf = np.array([0.91, 0.18], dtype=float)

    def __len__(self) -> int:
        return 2


class ClassThresholdTests(TestCase):
    NAMES = {2: "car", 3: "motorcycle"}

    def test_low_confidence_motorcycle_is_dropped_by_default(self) -> None:
        result = SimpleNamespace(boxes=MixedBoxes())

        detections = detections_from_result(result, self.NAMES, lambda _: 0.35)

        self.assertEqual([d.class_name for d in detections], ["car"])

    def test_per_class_threshold_admits_small_motorcycle(self) -> None:
        result = SimpleNamespace(boxes=MixedBoxes())
        thresholds = {"motorcycle": 0.15}

        detections = detections_from_result(
            result, self.NAMES, lambda name: thresholds.get(name, 0.35)
        )

        self.assertEqual(
            sorted(d.class_name for d in detections), ["car", "motorcycle"]
        )
