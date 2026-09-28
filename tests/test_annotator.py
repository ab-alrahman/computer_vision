from __future__ import annotations

from unittest import TestCase

import numpy as np

from src.core.types import BoundingBox, EventType, Track, ViolationEvent, Direction
from src.pipeline.annotator import Annotator, DEFAULT_COLOR, VIOLATION_COLOR


class AnnotatorTests(TestCase):
    def test_red_is_reserved_for_violations(self) -> None:
        annotator = Annotator({"car": VIOLATION_COLOR})
        track = Track(1, BoundingBox(0, 0, 10, 10), "car", 0.9)

        self.assertEqual(annotator.color_for(track), DEFAULT_COLOR)

    def test_violation_track_uses_red(self) -> None:
        annotator = Annotator({"car": (255, 128, 0)})
        track = Track(1, BoundingBox(0, 0, 10, 10), "car", 0.9)

        self.assertEqual(annotator.color_for(track, is_violation=True), VIOLATION_COLOR)

    def test_draw_changes_image_pixels(self) -> None:
        annotator = Annotator({"car": (255, 128, 0)})
        image = np.zeros((80, 120, 3), dtype=np.uint8)
        track = Track(1, BoundingBox(10, 10, 40, 40), "car", 0.9)
        violation = ViolationEvent(
            track_id=1,
            event_type=EventType.MOTORCYCLE_VIOLATION,
            class_name="car",
            direction=Direction.INBOUND,
            frame_index=0,
            timestamp_seconds=0.0,
        )

        annotator.draw(image, [track], [], [violation], {"tracks": 1})

        self.assertGreater(int(image.sum()), 0)

