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
