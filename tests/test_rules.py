from __future__ import annotations

from unittest import TestCase

from src.core.types import Direction, EventType, PassageEvent
from src.pipeline.rules import RuleEngine


def passage(class_name: str) -> PassageEvent:
    return PassageEvent(
        track_id=7,
        class_name=class_name,
        direction=Direction.INBOUND,
        amount=0.0,
        frame_index=42,
        timestamp_seconds=1.4,
    )


class RuleEngineTests(TestCase):
    def test_assigns_toll_amount_to_passage(self) -> None:
        engine = RuleEngine({"car": 1.0, "truck": 2.5})

        passages, violations = engine.apply_passages([passage("truck")])

        self.assertEqual(passages[0].amount, 2.5)
        self.assertEqual(violations, [])

    def test_motorcycle_creates_violation(self) -> None:
        engine = RuleEngine({"motorcycle": 0.0})

        passages, violations = engine.apply_passages([passage("motorcycle")])

        self.assertEqual(passages[0].amount, 0.0)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].event_type, EventType.MOTORCYCLE_VIOLATION)
        self.assertEqual(violations[0].track_id, 7)

    def test_traffic_police_motorcycle_is_allowed(self) -> None:
        engine = RuleEngine({"traffic-police motorcycle": 0.0})

        passages, violations = engine.apply_passages([passage("traffic-police motorcycle")])

        self.assertEqual(passages[0].amount, 0.0)
        self.assertEqual(violations, [])

    def test_speed_placeholder_returns_no_events_for_now(self) -> None:
        engine = RuleEngine({}, speed_limit_kph=80.0)

        self.assertEqual(engine.speed_violations_placeholder(), [])

