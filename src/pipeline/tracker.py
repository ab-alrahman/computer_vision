from __future__ import annotations

from math import hypot

from src.core.types import Detection, Point, Track, TrackState


class CentroidTracker:
    def __init__(self, max_distance_px: float = 80.0, max_lost_frames: int = 10) -> None:
        self.max_distance_px = max_distance_px
        self.max_lost_frames = max_lost_frames
        self.tracks: dict[int, Track] = {}
        self._next_track_id = 1

    def update(self, detections: list[Detection]) -> list[Track]:
        previous_track_ids = set(self.tracks)
        matches = self._match(detections)
        matched_track_ids = set(matches.values())
        matched_detection_indexes = set(matches.keys())

        for detection_index, track_id in matches.items():
            self._update_track(self.tracks[track_id], detections[detection_index])

        for detection_index, detection in enumerate(detections):
            if detection_index not in matched_detection_indexes:
                self._create_track(detection)

        for track_id in previous_track_ids:
            if track_id not in self.tracks:
                continue
            track = self.tracks[track_id]
            if track_id not in matched_track_ids:
                self._mark_lost(track)

        self._drop_expired_tracks()
        return self.active_tracks

    @property
    def active_tracks(self) -> list[Track]:
        return [
            track
            for track in sorted(self.tracks.values(), key=lambda item: item.track_id)
            if track.state == TrackState.ACTIVE
        ]

    def _match(self, detections: list[Detection]) -> dict[int, int]:
        candidates: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(detections):
            for track_id, track in self.tracks.items():
                if track.class_name != detection.class_name:
                    continue
                distance = _distance(track.centroid, detection.bbox.centroid)
                if distance <= self.max_distance_px:
                    candidates.append((distance, detection_index, track_id))

        matches: dict[int, int] = {}
        used_tracks: set[int] = set()
        for _distance_px, detection_index, track_id in sorted(candidates, key=lambda item: item[0]):
            if detection_index in matches or track_id in used_tracks:
                continue
            matches[detection_index] = track_id
            used_tracks.add(track_id)
        return matches

    def _create_track(self, detection: Detection) -> Track:
        track = Track(
            track_id=self._next_track_id,
            bbox=detection.bbox,
            class_name=detection.class_name,
            score=detection.score,
        )
        track.history.append(track.centroid)
        self.tracks[track.track_id] = track
        self._next_track_id += 1
        return track

    def _update_track(self, track: Track, detection: Detection) -> None:
        track.bbox = detection.bbox
        track.class_name = detection.class_name
        track.score = detection.score
        track.state = TrackState.ACTIVE
        track.lost_frames = 0
        track.history.append(track.centroid)

    def _mark_lost(self, track: Track) -> None:
        track.lost_frames += 1
        track.state = TrackState.LOST

    def _drop_expired_tracks(self) -> None:
        expired = [
            track_id
            for track_id, track in self.tracks.items()
            if track.state == TrackState.LOST and track.lost_frames > self.max_lost_frames
        ]
        for track_id in expired:
            del self.tracks[track_id]


def _distance(first: Point, second: Point) -> float:
    return hypot(first.x - second.x, first.y - second.y)
