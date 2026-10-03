from __future__ import annotations

from unittest import TestCase

from src.core.types import Direction, EventType, PassageEvent
from src.pipeline.rules import RuleEngine


def passage(class_name: str, average_speed_kph: float = 0.0) -> PassageEvent:
    return PassageEvent(
        track_id=7,
        class_name=class_name,
        direction=Direction.INBOUND,
        amount=0.0,
        frame_index=42,
        timestamp_seconds=1.4,
        speed_kph=average_speed_kph,
        average_speed_kph=average_speed_kph,
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

    def test_speed_below_limit_keeps_track_clean(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0)

        self.assertFalse(engine.evaluate_speed(3, 60.0))
        self.assertEqual(engine.speeding_track_ids(), set())

    def test_speed_above_limit_flags_track(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0)

        self.assertTrue(engine.evaluate_speed(3, 95.0))
        self.assertEqual(engine.speeding_track_ids(), {3})

    def test_hysteresis_keeps_flag_inside_the_band(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0, speed_hysteresis_kph=3.0)
        engine.evaluate_speed(3, 95.0)

        self.assertTrue(engine.evaluate_speed(3, 79.0))
        self.assertTrue(engine.evaluate_speed(3, 81.0))

    def test_hysteresis_clears_flag_once_slow_enough(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0, speed_hysteresis_kph=3.0)
        engine.evaluate_speed(3, 95.0)

        self.assertFalse(engine.evaluate_speed(3, 76.0))
        self.assertEqual(engine.speeding_track_ids(), set())

    def test_zero_speed_never_flags_a_track(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0)

        self.assertFalse(engine.evaluate_speed(3, 0.0))
        self.assertEqual(engine.speeding_track_ids(), set())

    def test_speeding_passage_emits_speed_violation(self) -> None:
        engine = RuleEngine({"car": 1.0}, speed_limit_kph=80.0)
        engine.evaluate_speed(7, 92.0)

        passages, violations = engine.apply_passages([passage("car", 92.0)])

        self.assertEqual(passages[0].amount, 1.0)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].event_type, EventType.SPEED_VIOLATION)
        self.assertEqual(violations[0].details["limitKph"], 80.0)
        self.assertEqual(violations[0].details["averageSpeedKph"], 92.0)

    def test_motorcycle_and_speed_violations_can_fire_together(self) -> None:
        engine = RuleEngine({"motorcycle": 0.0}, speed_limit_kph=80.0)
        engine.evaluate_speed(7, 120.0)

        _, violations = engine.apply_passages([passage("motorcycle", 120.0)])

        self.assertEqual(
            [violation.event_type for violation in violations],
            [EventType.MOTORCYCLE_VIOLATION, EventType.SPEED_VIOLATION],
        )

