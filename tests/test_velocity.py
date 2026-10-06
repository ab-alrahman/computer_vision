from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.core.types import BoundingBox, Point, Track
from src.pipeline.velocity import Homography, SpeedMonitor, TrackSpeed

ROAD_CORNERS = [(100.0, 400.0), (900.0, 400.0), (1000.0, 200.0), (0.0, 200.0)]
WIDTH_METERS = 7.0
LENGTH_METERS = 20.0


def track(track_id: int, center_x: float, center_y: float) -> Track:
    return Track(
        track_id=track_id,
        bbox=BoundingBox(center_x - 10.0, center_y - 10.0, center_x + 10.0, center_y + 10.0),
        class_name="car",
        score=0.9,
    )


class HomographyTests(TestCase):
    def test_corners_map_to_reference_rectangle(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)

        self.assertAlmostEqual(homography.project(Point(100.0, 400.0))[0], 0.0, places=4)
        self.assertAlmostEqual(homography.project(Point(100.0, 400.0))[1], 0.0, places=4)
        self.assertAlmostEqual(homography.project(Point(900.0, 400.0))[0], WIDTH_METERS, places=4)
        self.assertAlmostEqual(homography.project(Point(1000.0, 200.0))[1], LENGTH_METERS, places=4)

    def test_distance_meters_matches_world_distance(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)

        distance = homography.distance_meters(Point(100.0, 400.0), Point(300.0, 400.0))

        self.assertGreater(distance, 0.0)
        self.assertAlmostEqual(
            distance,
            homography.project(Point(300.0, 400.0))[0],
            places=3,
        )

    def test_inverse_project_maps_reference_corners_back(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)

        near_left = homography.inverse_project(Point(0.0, 0.0))
        far_right = homography.inverse_project(Point(WIDTH_METERS, LENGTH_METERS))

        self.assertAlmostEqual(near_left[0], ROAD_CORNERS[0][0], places=3)
        self.assertAlmostEqual(near_left[1], ROAD_CORNERS[0][1], places=3)
        self.assertAlmostEqual(far_right[0], ROAD_CORNERS[2][0], places=3)
        self.assertAlmostEqual(far_right[1], ROAD_CORNERS[2][1], places=3)

    def test_inverse_project_returns_the_original_pixels(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)
        world = homography.project(Point(640.0, 320.0))

        back = homography.inverse_project(Point(world[0], world[1]))

        self.assertAlmostEqual(back[0], 640.0, places=3)
        self.assertAlmostEqual(back[1], 320.0, places=3)

    def test_inverse_project_measures_the_road_in_pixels(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)
        origin = homography.inverse_project(Point(0.0, 0.0))
        near_right = homography.inverse_project(Point(WIDTH_METERS, 0.0))

        self.assertAlmostEqual(abs(near_right[0] - origin[0]), 800.0, places=3)

    def test_requires_four_points(self) -> None:
        with self.assertRaises(ValueError):
            Homography.from_corners(ROAD_CORNERS[:3], WIDTH_METERS, LENGTH_METERS)

    def test_requires_positive_reference_distances(self) -> None:
        with self.assertRaises(ValueError):
            Homography.from_corners(ROAD_CORNERS, 0.0, LENGTH_METERS)

    def test_save_and_load_round_trip(self) -> None:
        homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)

        with TemporaryDirectory() as tmp:
            path = homography.save(Path(tmp) / "nested" / "calibration.json", extra={"frameIndex": 7})
            loaded = Homography.load(path)

            self.assertTrue(path.is_file())
            self.assertEqual(loaded.source_points, homography.source_points)
            self.assertEqual(loaded.reference["widthMeters"], WIDTH_METERS)
            self.assertEqual(loaded.reference["lengthMeters"], LENGTH_METERS)
            self.assertAlmostEqual(
                loaded.distance_meters(Point(100.0, 400.0), Point(900.0, 400.0)),
                WIDTH_METERS,
                places=3,
            )

    def test_load_rejects_missing_matrix(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibration.json"
            path.write_text("{}", encoding="utf-8")

            with self.assertRaises(ValueError):
                Homography.load(path)

    def test_load_rejects_wrong_matrix_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibration.json"
            path.write_text('{"matrix": [[1, 0], [0, 1]]}', encoding="utf-8")

            with self.assertRaises(ValueError):
                Homography.load(path)

    def test_load_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            Homography.load(Path("configs") / "does-not-exist.json")


class SpeedMonitorTests(TestCase):
    def setUp(self) -> None:
        self.homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)
        # position_alpha=1.0 keeps positions raw so these tests exercise the
        # speed EMA alone; position smoothing has its own tests below
        self.monitor = SpeedMonitor(
            homography=self.homography, alpha=1.0, position_alpha=1.0
        )

    def test_rejects_invalid_smoothing_alpha(self) -> None:
        with self.assertRaises(ValueError):
            SpeedMonitor(homography=self.homography, alpha=0.0)

    def test_rejects_invalid_position_alpha(self) -> None:
        with self.assertRaises(ValueError):
            SpeedMonitor(homography=self.homography, position_alpha=0.0)

    def test_rejects_negative_min_step(self) -> None:
        with self.assertRaises(ValueError):
            SpeedMonitor(homography=self.homography, min_step_meters=-1.0)

    def test_rejects_non_positive_plausibility_cap(self) -> None:
        with self.assertRaises(ValueError):
            SpeedMonitor(homography=self.homography, max_plausible_kph=0.0)

    def test_first_sample_has_no_speed(self) -> None:
        states = self.monitor.update([track(1, 500.0, 300.0)], 0.0)

        state = states[1]
        self.assertEqual(state.samples, 1)
        self.assertEqual(state.instant_kph, 0.0)
        self.assertEqual(state.average_kph, 0.0)

    def test_average_speed_follows_travelled_distance(self) -> None:
        self.monitor.update([track(1, 500.0, 300.0)], 0.0)
        states = self.monitor.update([track(1, 600.0, 300.0)], 1.0)

        state = states[1]
        expected_meters = self.homography.project(Point(600.0, 300.0))[0] - self.homography.project(
            Point(500.0, 300.0)
        )[0]
        self.assertAlmostEqual(state.distance_meters, expected_meters, places=3)
        self.assertAlmostEqual(state.average_kph, expected_meters * 3.6, places=2)
        self.assertAlmostEqual(state.max_kph, state.instant_kph, places=3)

    def test_smoothing_blends_consecutive_samples(self) -> None:
        monitor = SpeedMonitor(homography=self.homography, alpha=0.5, position_alpha=1.0)
        monitor.update([track(1, 100.0, 400.0)], 0.0)
        fast = monitor.update([track(1, 900.0, 400.0)], 1.0)[1].instant_kph
        blended = monitor.update([track(1, 950.0, 400.0)], 2.0)[1].instant_kph

        self.assertAlmostEqual(fast, 25.2, places=1)
        self.assertLess(blended, fast)
        self.assertGreater(blended, 1.5)

    def test_long_gap_resets_without_spike(self) -> None:
        self.monitor.update([track(1, 500.0, 300.0)], 0.0)
        states = self.monitor.update([track(1, 900.0, 300.0)], 5.0)

        self.assertEqual(states[1].instant_kph, 0.0)
        self.assertEqual(states[1].distance_meters, 0.0)

    def test_non_positive_delta_is_ignored(self) -> None:
        self.monitor.update([track(1, 500.0, 300.0)], 2.0)
        states = self.monitor.update([track(1, 900.0, 300.0)], 2.0)

        self.assertEqual(states[1].instant_kph, 0.0)

    def test_idle_tracks_are_dropped(self) -> None:
        self.monitor.update([track(1, 500.0, 300.0)], 0.0)
        self.monitor.update([track(1, 600.0, 300.0)], 1.0)
        self.assertIn(1, self.monitor.active_track_ids())

        states = self.monitor.update([], 120.0)

        self.assertNotIn(1, states)
        self.assertIsNone(self.monitor.speed_for(1))

    def test_tracks_are_measured_independently(self) -> None:
        self.monitor.update([track(1, 500.0, 300.0), track(2, 500.0, 350.0)], 0.0)
        states = self.monitor.update([track(1, 600.0, 300.0), track(2, 500.0, 350.0)], 1.0)

        self.assertGreater(states[1].instant_kph, 0.0)
        self.assertEqual(states[2].instant_kph, 0.0)


class SpeedJitterTests(TestCase):
    """bbox jitter divided by dt is what produced the phantom speeding."""

    def setUp(self) -> None:
        self.homography = Homography.from_corners(ROAD_CORNERS, WIDTH_METERS, LENGTH_METERS)

    def _run(self, monitor: SpeedMonitor, xs: list[float], dt: float = 1.0) -> TrackSpeed:
        states: dict[int, TrackSpeed] = {}
        for index, x in enumerate(xs):
            states = monitor.update([track(1, x, 300.0)], index * dt)
        return states[1]

    def test_smoothed_positions_ignore_bbox_jitter(self) -> None:
        # a track parked on the line flips +/-80px between frames; dividing that
        # by dt produces a phantom 100kph read on unsmoothed positions
        jitter = [500.0 + (80.0 if i % 2 else -80.0) for i in range(20)]
        raw = self._run(
            SpeedMonitor(self.homography, alpha=0.3, position_alpha=1.0), jitter, dt=0.05
        )
        smoothed = self._run(
            SpeedMonitor(self.homography, alpha=0.3, position_alpha=0.3), jitter, dt=0.05
        )

        self.assertGreater(raw.average_kph, 80.0)
        self.assertLess(smoothed.average_kph, 80.0)

    def test_plausibility_cap_drops_impossible_jumps(self) -> None:
        monitor = SpeedMonitor(self.homography, alpha=1.0, position_alpha=1.0,
                               max_plausible_kph=160.0)
        monitor.update([track(1, 100.0, 400.0)], 0.0)

        state = monitor.update([track(1, 900.0, 400.0)], 0.1)[1]

        self.assertEqual(state.instant_kph, 0.0)
        self.assertEqual(state.average_kph, 0.0)

    def test_min_step_drops_sub_pixel_dither(self) -> None:
        monitor = SpeedMonitor(self.homography, alpha=1.0, position_alpha=1.0,
                               min_step_meters=1.0)
        monitor.update([track(1, 500.0, 400.0)], 0.0)

        state = monitor.update([track(1, 505.0, 400.0)], 1.0)[1]

        self.assertEqual(state.instant_kph, 0.0)

    def test_real_speeder_survives_smoothing_and_cap(self) -> None:
        # full road width in 0.2s is ~97kph on this homography: over the 80 limit
        monitor = SpeedMonitor(self.homography, alpha=0.3, position_alpha=0.3,
                               max_plausible_kph=160.0)
        xs = [100.0 + i * 800.0 for i in range(9)]

        state = self._run(monitor, xs, dt=0.2)

        self.assertGreater(state.instant_kph, 80.0)
        self.assertGreater(state.average_kph, 80.0)