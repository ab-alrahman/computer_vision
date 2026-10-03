from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VehicleClass(str, Enum):
    CAR = "car"
    VAN = "van"
    BUS = "bus"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    TRAFFIC_POLICE_MOTORCYCLE = "traffic-police motorcycle"


class Direction(str, Enum):
    UNKNOWN = "UNKNOWN"
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class TrackState(str, Enum):
    ACTIVE = "ACTIVE"
    LOST = "LOST"


class EventType(str, Enum):
    PASSAGE = "PASSAGE"
    MOTORCYCLE_VIOLATION = "MOTORCYCLE_VIOLATION"
    SPEED_VIOLATION = "SPEED_VIOLATION"


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def centroid(self) -> Point:
        return Point((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


@dataclass(frozen=True)
class Detection:
    bbox: BoundingBox
    score: float
    class_id: int
    class_name: str


@dataclass
class Track:
    track_id: int
    bbox: BoundingBox
    class_name: str
    score: float
    state: TrackState = TrackState.ACTIVE
    direction: Direction = Direction.UNKNOWN
    counted: bool = False
    lost_frames: int = 0
    history: list[Point] = field(default_factory=list)

    @property
    def centroid(self) -> Point:
        return self.bbox.centroid


@dataclass(frozen=True)
class PassageEvent:
    track_id: int
    class_name: str
    direction: Direction
    amount: float
    frame_index: int
    timestamp_seconds: float
    speed_kph: float = 0.0
    average_speed_kph: float = 0.0


@dataclass(frozen=True)
class ViolationEvent:
    track_id: int
    event_type: EventType
    class_name: str
    direction: Direction
    frame_index: int
    timestamp_seconds: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrameData:
    frame_index: int
    timestamp_seconds: float
    image: Any


@dataclass(frozen=True)
class FrameResult:
    frame: FrameData
    detections: list[Detection]
    tracks: list[Track]
    passages: list[PassageEvent]
    violations: list[ViolationEvent]

