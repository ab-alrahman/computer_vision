from __future__ import annotations

from unittest import TestCase

from src.core.types import BoundingBox, Detection, TrackState
from src.pipeline.tracker import CentroidTracker


def detection(x1: float, y1: float, x2: float, y2: float, class_name: str = "car") -> Detection:
    return Detection(
        bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
        score=0.9,
        class_id=2,
        class_name=class_name,
    )


class CentroidTrackerTests(TestCase):
    def test_keeps_track_id_for_nearby_detection(self) -> None:
        tracker = CentroidTracker(max_distance_px=30, max_lost_frames=2)

        first = tracker.update([detection(0, 0, 20, 20)])
        second = tracker.update([detection(5, 5, 25, 25)])

        self.assertEqual(first[0].track_id, second[0].track_id)
        self.assertEqual(len(second[0].history), 2)

    def test_creates_new_track_when_detection_is_far(self) -> None:
        tracker = CentroidTracker(max_distance_px=10, max_lost_frames=2)

        tracker.update([detection(0, 0, 20, 20)])
        tracks = tracker.update([detection(100, 100, 120, 120)])

        self.assertEqual([track.track_id for track in tracks], [2])
        self.assertEqual(tracker.tracks[1].state, TrackState.LOST)

    def test_does_not_match_different_classes(self) -> None:
        tracker = CentroidTracker(max_distance_px=100, max_lost_frames=2)

        tracker.update([detection(0, 0, 20, 20, "car")])
        tracks = tracker.update([detection(2, 2, 22, 22, "bus")])

        self.assertEqual(tracks[0].track_id, 2)
        self.assertEqual(tracks[0].class_name, "bus")

    def test_drops_lost_tracks_after_limit(self) -> None:
        tracker = CentroidTracker(max_distance_px=30, max_lost_frames=1)

        tracker.update([detection(0, 0, 20, 20)])
        tracker.update([])
        tracker.update([])

        self.assertEqual(tracker.tracks, {})

