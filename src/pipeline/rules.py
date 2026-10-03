from __future__ import annotations

from dataclasses import replace

from src.core.types import EventType, PassageEvent, ViolationEvent, VehicleClass


class RuleEngine:
    def __init__(self, toll_prices: dict[str, float], speed_limit_kph: float = 80.0,
                 speed_hysteresis_kph: float = 3.0) -> None:
        self.toll_prices = toll_prices
        self.speed_limit_kph = speed_limit_kph
        self.speed_hysteresis_kph = speed_hysteresis_kph
        self._speeding_track_ids: set[int] = set()

    def apply_passages(self, passages: list[PassageEvent]) -> tuple[list[PassageEvent], list[ViolationEvent]]:
        priced_passages: list[PassageEvent] = []
        violations: list[ViolationEvent] = []

        for passage in passages:
            priced = replace(passage, amount=self.toll_for(passage.class_name))
            priced_passages.append(priced)

            if passage.class_name == VehicleClass.MOTORCYCLE.value:
                violations.append(
                    ViolationEvent(
                        track_id=passage.track_id,
                        event_type=EventType.MOTORCYCLE_VIOLATION,
                        class_name=passage.class_name,
                        direction=passage.direction,
                        frame_index=passage.frame_index,
                        timestamp_seconds=passage.timestamp_seconds,
                        details={"reason": "non-police motorcycle is not allowed"},
                    )
                )

            if self.is_speeding(passage.track_id):
                violations.append(
                    ViolationEvent(
                        track_id=passage.track_id,
                        event_type=EventType.SPEED_VIOLATION,
                        class_name=passage.class_name,
                        direction=passage.direction,
                        frame_index=passage.frame_index,
                        timestamp_seconds=passage.timestamp_seconds,
                        details={
                            "reason": "average speed above the limit",
                            "averageSpeedKph": round(passage.average_speed_kph, 2),
                            "speedKph": round(passage.speed_kph, 2),
                            "limitKph": self.speed_limit_kph,
                        },
                    )
                )

        return priced_passages, violations

    def toll_for(self, class_name: str) -> float:
        return float(self.toll_prices.get(class_name, 0.0))

    def evaluate_speed(self, track_id: int, average_speed_kph: float) -> bool:
        if average_speed_kph <= 0.0:
            return False

        if track_id in self._speeding_track_ids:
            if average_speed_kph < self.speed_limit_kph - self.speed_hysteresis_kph:
                self._speeding_track_ids.discard(track_id)
        elif average_speed_kph > self.speed_limit_kph + self.speed_hysteresis_kph:
            self._speeding_track_ids.add(track_id)
        return track_id in self._speeding_track_ids

    def is_speeding(self, track_id: int) -> bool:
        return track_id in self._speeding_track_ids

    def speeding_track_ids(self) -> set[int]:
        return set(self._speeding_track_ids)
