from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import AppConfig, load_config
from src.core.types import PassageEvent
from src.pipeline.annotator import Annotator, VideoWriter
from src.pipeline.detector import YoloDetector
from src.pipeline.geometry import CountingLine, LineCounter
from src.pipeline.rules import RuleEngine
from src.pipeline.source import VideoSource
from src.pipeline.tracker import CentroidTracker
from src.pipeline.velocity import Homography, SpeedMonitor, TrackSpeed
from src.services.report import build_report, write_report


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive number")
    return parsed


def resolve_max_frames(config_value: int | None, cli_value: int | None, all_frames: bool) -> int | None:
    if all_frames:
        return None
    if cli_value is not None:
        return cli_value
    return config_value if config_value is not None else 5


def resolve_speed_limit(config_value: float, cli_value: float | None) -> float:
    return float(cli_value if cli_value is not None else config_value)


def build_speed_monitor(config: AppConfig) -> SpeedMonitor | None:
    if not config.speed.enabled:
        return None
    calibration_path = config.speed.calibration_path
    if calibration_path is None or not calibration_path.is_file():
        return None
    return SpeedMonitor(
        homography=Homography.load(calibration_path),
        alpha=config.speed.smoothing_alpha,
    )


def attach_speeds(passages: list[PassageEvent],
                  speeds: dict[int, TrackSpeed]) -> list[PassageEvent]:
    enriched: list[PassageEvent] = []
    for passage in passages:
        state = speeds.get(passage.track_id)
        if state is None:
            enriched.append(passage)
            continue
        enriched.append(
            replace(
                passage,
                speed_kph=round(state.instant_kph, 2),
                average_speed_kph=round(state.average_kph, 2),
            )
        )
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart toll road vision pipeline")
    parser.add_argument("--config", default="configs/default.yaml")
    frame_group = parser.add_mutually_exclusive_group()
    frame_group.add_argument("--max-frames", type=positive_int, help="maximum frames to process")
    frame_group.add_argument("--all-frames", action="store_true", help="process the full video")
    parser.add_argument("--output", help="override annotated video output path")
    parser.add_argument("--report", help="override JSON report output path")
    parser.add_argument("--speed-limit", type=positive_float,
                        help="override the speed limit in km/h")
    args = parser.parse_args()

    config = load_config(args.config)
    output_path = Path(args.output).resolve() if args.output else config.video.output_path
    report_path = Path(args.report).resolve() if args.report else config.video.report_path
    max_frames = resolve_max_frames(config.runtime.max_frames, args.max_frames, args.all_frames)
    speed_limit = resolve_speed_limit(config.speed_limit_kph, args.speed_limit)

    print("[config] loaded")
    print(f"  model: {config.model.path}")
    print(f"  input: {config.video.input_path}")
    print(f"  output: {output_path}")
    print(f"  report: {report_path}")
    print(f"  max frames: {'all' if max_frames is None else max_frames}")
    print(f"  speed limit: {speed_limit:.1f} kph")

    if not config.model.path.is_file():
        raise SystemExit(f"[model] missing model file: {config.model.path}")

    if not config.video.input_path.is_file():
        print("[source] input video is not present yet; skeleton is ready")
        print("         add the clip path in configs/default.yaml when available")
        return 0

    speed_monitor = build_speed_monitor(config)
    if speed_monitor is None:
        print("[speed] disabled: no usable calibration, run scripts/calibrate_geometry.py first")
    else:
        reference = speed_monitor.homography.reference
        print(f"[speed] homography loaded from {config.speed.calibration_path}")
        if reference:
            print(f"  reference rectangle: {reference.get('widthMeters')}m x "
                  f"{reference.get('lengthMeters')}m")
    report_speed_limit = speed_limit if speed_monitor is not None else None

    with VideoSource(config.video.input_path) as source:
        print("[source] smoke read passed")
        print(f"  fps: {source.fps:.2f}")
        print(f"  frames: {source.frame_count}")

        detector = YoloDetector(
            model_path=config.model.path,
            confidence_threshold=config.model.confidence_threshold,
            image_size=config.model.image_size,
        )
        tracker = CentroidTracker(
            max_distance_px=config.tracker.max_distance_px,
            max_lost_frames=config.tracker.max_lost_frames,
        )
        counting_lines = [CountingLine.from_config(line_config) for line_config in config.counting_lines]
        counters = [LineCounter(line) for line in counting_lines]
        rules = RuleEngine(
            toll_prices=config.toll_prices,
            speed_limit_kph=speed_limit,
            speed_hysteresis_kph=config.speed.hysteresis_kph,
        )
        annotator = Annotator(config.class_colors)

        frames_seen = 0
        total_detections = 0
        passages = []
        violations = []
        writer = None
        for frame in source.frames(max_frames=max_frames):
            if frames_seen == 0:
                print(f"  first frame shape: {frame.image.shape}")
                height, width = frame.image.shape[:2]
                writer = VideoWriter(output_path, source.fps, (width, height))
                writer.__enter__()
            try:
                detections = detector.detect(frame.image)
                tracks = tracker.update(detections)
                speeds: dict[int, TrackSpeed] = {}
                if speed_monitor is not None:
                    speeds = speed_monitor.update(tracks, frame.timestamp_seconds)
                    for track in tracks:
                        state = speeds.get(track.track_id)
                        if state is not None:
                            rules.evaluate_speed(track.track_id, state.average_kph)
                frame_passages = []
                for counter in counters:
                    frame_passages.extend(counter.update(tracks, frame.frame_index, frame.timestamp_seconds))
                frame_passages = attach_speeds(frame_passages, speeds)
                priced_passages, frame_violations = rules.apply_passages(frame_passages)
                passages.extend(priced_passages)
                violations.extend(frame_violations)
                frames_seen += 1
                total_detections += len(detections)
                fastest = max((state.average_kph for state in speeds.values()), default=0.0)
                hud = {
                    "tracks": len(tracks),
                    "passages": len(passages),
                    "violations": len(violations),
                    "speeding": len(rules.speeding_track_ids()),
                    "max avg kph": f"{fastest:.1f}",
                }
                annotator.draw(
                    frame.image,
                    tracks,
                    counting_lines,
                    frame_violations,
                    hud,
                    rules.speeding_track_ids(),
                )
                writer.write(frame.image)
                print(
                    f"[frame {frame.frame_index}] detections={len(detections)} "
                    f"active_tracks={len(tracks)} passages={len(priced_passages)} "
                    f"violations={len(frame_violations)} fastest_avg_kph={fastest:.1f}"
                )
            finally:
                pass
        if writer is not None:
            writer.__exit__(None, None, None)

        if frames_seen == 0:
            raise SystemExit("[source] video opened but no frames were read")

        print("[detector] smoke inference passed")
        print(f"  frames processed: {frames_seen}")
        print(f"  detections total: {total_detections}")
        print("[tracker] smoke tracking passed")
        print(f"  tracks kept: {len(tracker.tracks)}")
        print("[geometry] smoke counting passed")
        print(f"  passages: {len(passages)}")
        for passage in passages[:10]:
            print(
                f"  - track #{passage.track_id} {passage.class_name} "
                f"direction={passage.direction.value} amount={passage.amount:.2f} "
                f"frame={passage.frame_index} "
                f"avg_speed={passage.average_speed_kph:.1f}kph"
            )
        print("[rules] smoke rules passed")
        print(f"  violations: {len(violations)}")
        print(f"  speed limit: {speed_limit:.1f} kph")
        for violation in violations[:10]:
            print(f"  - track #{violation.track_id} {violation.event_type.value} {violation.details}")
        for track in tracker.active_tracks[:10]:
            center = track.centroid
            print(
                f"  - track #{track.track_id} {track.class_name} "
                f"score={track.score:.2f} center=({center.x:.0f},{center.y:.0f})"
            )

    report = build_report(passages, violations, speed_limit_kph=report_speed_limit)
    report_path = write_report(report_path, report)
    print("[report] wrote JSON report")
    print(f"  path: {report_path}")
    print(f"  total passages: {report['summary']['totalPassages']}")
    print(f"  total revenue: {report['summary']['totalRevenue']:.2f}")
    print("[annotator] wrote annotated video")
    print(f"  path: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
