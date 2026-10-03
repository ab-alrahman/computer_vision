from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.core.types import Direction, EventType, PassageEvent, ViolationEvent


def build_report(passages: list[PassageEvent], violations: list[ViolationEvent],
                 speed_limit_kph: float | None = None) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {
        direction.value: defaultdict(int) for direction in Direction
    }
    revenue_by_class: dict[str, float] = defaultdict(float)
    speeding_track_ids: set[int] = set()

    for passage in passages:
        counts[passage.direction.value][passage.class_name] += 1
        revenue_by_class[passage.class_name] += passage.amount

    for violation in violations:
        if violation.event_type == EventType.SPEED_VIOLATION:
            speeding_track_ids.add(violation.track_id)

    speeds = [passage.average_speed_kph for passage in passages if passage.average_speed_kph > 0]
    summary: dict[str, Any] = {
        "totalPassages": len(passages),
        "totalViolations": len(violations),
        "totalRevenue": round(sum(item.amount for item in passages), 2),
    }
    if speed_limit_kph is not None:
        summary["speedLimitKph"] = speed_limit_kph
    if speeds:
        summary["maxAverageSpeedKph"] = round(max(speeds), 2)
        summary["meanAverageSpeedKph"] = round(sum(speeds) / len(speeds), 2)

    return {
        "summary": summary,
        "counts": {
            direction: dict(sorted(class_counts.items()))
            for direction, class_counts in counts.items()
        },
        "revenueByClass": {
            class_name: round(amount, 2)
            for class_name, amount in sorted(revenue_by_class.items())
        },
        "speedingTrackIds": sorted(speeding_track_ids),
        "passages": [_passage_to_dict(item) for item in passages],
        "violations": [_violation_to_dict(item) for item in violations],
    }


def write_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def _passage_to_dict(event: PassageEvent) -> dict[str, Any]:
    return {
        "trackId": event.track_id,
        "className": event.class_name,
        "direction": event.direction.value,
        "amount": event.amount,
        "frameIndex": event.frame_index,
        "timestampSeconds": event.timestamp_seconds,
        "speedKph": round(event.speed_kph, 2),
        "averageSpeedKph": round(event.average_speed_kph, 2),
    }


def _violation_to_dict(event: ViolationEvent) -> dict[str, Any]:
    return {
        "trackId": event.track_id,
        "eventType": event.event_type.value,
        "className": event.class_name,
        "direction": event.direction.value,
        "frameIndex": event.frame_index,
        "timestampSeconds": event.timestamp_seconds,
        "details": event.details,
    }

