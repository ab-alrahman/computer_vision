from __future__ import annotations

from dataclasses import dataclass

from src.core.config import CountingLineConfig
from src.core.types import Direction, PassageEvent, Point, Track


@dataclass(frozen=True)
class CountingLine:
    name: str
    start: Point
    end: Point
    inbound_when_crossing: str = "top_to_bottom"

    @classmethod
    def from_config(cls, config: CountingLineConfig) -> "CountingLine":
        start, end = config.points
        return cls(
            name=config.name,
            start=Point(float(start[0]), float(start[1])),
            end=Point(float(end[0]), float(end[1])),
            inbound_when_crossing=config.inbound_when_crossing,
        )


class LineCounter:
    def __init__(self, line: CountingLine) -> None:
        self.line = line

    def update(self, tracks: list[Track], frame_index: int,
               timestamp_seconds: float) -> list[PassageEvent]:
        events: list[PassageEvent] = []
        for track in tracks:
            if track.counted or len(track.history) < 2:
                continue
            previous = track.history[-2]
            current = track.history[-1]
            if not crossed_line(previous, current, self.line):
                continue
            direction = infer_direction(previous, current, self.line)
            track.direction = direction
            track.counted = True
            events.append(
                PassageEvent(
                    track_id=track.track_id,
                    class_name=track.class_name,
                    direction=direction,
                    amount=0.0,
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                )
            )
        return events


def crossed_line(previous: Point, current: Point, line: CountingLine) -> bool:
    previous_side = signed_side(previous, line)
    current_side = signed_side(current, line)
    if previous_side == 0.0 or current_side == 0.0:
        return previous_side != current_side
    return (previous_side < 0 < current_side) or (previous_side > 0 > current_side)


def infer_direction(previous: Point, current: Point, line: CountingLine) -> Direction:
    previous_side = signed_side(previous, line)
    current_side = signed_side(current, line)
    crossing = _crossing_name(previous_side, current_side, line)
    if crossing == line.inbound_when_crossing:
        return Direction.INBOUND
    return Direction.OUTBOUND


def signed_side(point: Point, line: CountingLine) -> float:
    dx = line.end.x - line.start.x
    dy = line.end.y - line.start.y
    return dx * (point.y - line.start.y) - dy * (point.x - line.start.x)


def _crossing_name(previous_side: float, current_side: float, line: CountingLine) -> str:
    if abs(line.end.y - line.start.y) <= abs(line.end.x - line.start.x):
        return "top_to_bottom" if current_side > previous_side else "bottom_to_top"
    return "left_to_right" if current_side < previous_side else "right_to_left"

