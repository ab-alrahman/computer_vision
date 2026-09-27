from __future__ import annotations

from unittest import TestCase

from src.core.types import BoundingBox, Direction, Track
from src.pipeline.geometry import CountingLine, LineCounter, crossed_line
from src.core.types import Point


def track_with_history(track_id: int, points: list[Point]) -> Track:
    last = points[-1]
    track = Track(
        track_id=track_id,
        bbox=BoundingBox(last.x - 5, last.y - 5, last.x + 5, last.y + 5),
        class_name="car",
        score=0.9,
    )
    track.history.extend(points)
    return track


class GeometryTests(TestCase):
    def test_detects_horizontal_line_crossing(self) -> None:
        line = CountingLine("main", Point(0, 10), Point(100, 10))

        self.assertTrue(crossed_line(Point(5, 5), Point(5, 15), line))
        self.assertFalse(crossed_line(Point(5, 5), Point(20, 5), line))

    def test_counts_track_once_and_marks_direction(self) -> None:
        line = CountingLine("main", Point(0, 10), Point(100, 10), "top_to_bottom")
        counter = LineCounter(line)
        track = track_with_history(1, [Point(20, 5), Point(20, 15)])

        first = counter.update([track], frame_index=7, timestamp_seconds=1.2)
        second = counter.update([track], frame_index=8, timestamp_seconds=1.3)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertTrue(track.counted)
        self.assertEqual(track.direction, Direction.INBOUND)
        self.assertEqual(first[0].track_id, 1)

    def test_reverse_crossing_is_outbound(self) -> None:
        line = CountingLine("main", Point(0, 10), Point(100, 10), "top_to_bottom")
        counter = LineCounter(line)
        track = track_with_history(1, [Point(20, 15), Point(20, 5)])

        events = counter.update([track], frame_index=7, timestamp_seconds=1.2)

        self.assertEqual(events[0].direction, Direction.OUTBOUND)

