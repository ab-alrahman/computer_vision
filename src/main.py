from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import load_config
from src.pipeline.annotator import Annotator, VideoWriter
from src.pipeline.detector import YoloDetector
from src.pipeline.geometry import CountingLine, LineCounter
from src.pipeline.rules import RuleEngine
from src.pipeline.source import VideoSource
from src.pipeline.tracker import CentroidTracker
from src.services.report import build_report, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart toll road vision pipeline")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    print("[config] loaded")
    print(f"  model: {config.model.path}")
    print(f"  input: {config.video.input_path}")
    print(f"  output: {config.video.output_path}")
    print(f"  report: {config.video.report_path}")

    if not config.model.path.is_file():
        raise SystemExit(f"[model] missing model file: {config.model.path}")

    if not config.video.input_path.is_file():
        print("[source] input video is not present yet; skeleton is ready")
        print("         add the clip path in configs/default.yaml when available")
        return 0

    smoke_frames = config.runtime.max_frames or 5

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
            speed_limit_kph=config.speed_limit_kph,
        )
        annotator = Annotator(config.class_colors)

        frames_seen = 0
        total_detections = 0
        passages = []
        violations = []
        writer = None
        for frame in source.frames(max_frames=smoke_frames):
            if frames_seen == 0:
                print(f"  first frame shape: {frame.image.shape}")
                height, width = frame.image.shape[:2]
                writer = VideoWriter(config.video.output_path, source.fps, (width, height))
                writer.__enter__()
            try:
                detections = detector.detect(frame.image)
                tracks = tracker.update(detections)
                frame_passages = []
                for counter in counters:
                    frame_passages.extend(counter.update(tracks, frame.frame_index, frame.timestamp_seconds))
                priced_passages, frame_violations = rules.apply_passages(frame_passages)
                passages.extend(priced_passages)
                violations.extend(frame_violations)
                frames_seen += 1
                total_detections += len(detections)
                hud = {
                    "tracks": len(tracks),
                    "passages": len(passages),
                    "violations": len(violations),
                }
                annotator.draw(frame.image, tracks, counting_lines, frame_violations, hud)
                writer.write(frame.image)
                print(
                    f"[frame {frame.frame_index}] detections={len(detections)} "
                    f"active_tracks={len(tracks)} passages={len(priced_passages)} "
                    f"violations={len(frame_violations)}"
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
                f"frame={passage.frame_index}"
            )
        print("[rules] smoke rules passed")
        print(f"  violations: {len(violations)}")
        print(f"  speed limit placeholder: {config.speed_limit_kph:.1f} kph")
        for track in tracker.active_tracks[:10]:
            center = track.centroid
            print(
                f"  - track #{track.track_id} {track.class_name} "
                f"score={track.score:.2f} center=({center.x:.0f},{center.y:.0f})"
            )

    Path(config.video.output_path).parent.mkdir(parents=True, exist_ok=True)
    report = build_report(passages, violations)
    report_path = write_report(config.video.report_path, report)
    print("[report] wrote JSON report")
    print(f"  path: {report_path}")
    print(f"  total passages: {report['summary']['totalPassages']}")
    print(f"  total revenue: {report['summary']['totalRevenue']:.2f}")
    print("[annotator] wrote annotated video")
    print(f"  path: {config.video.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
