from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import load_config
from src.pipeline.detector import YoloDetector
from src.pipeline.source import VideoSource
from src.pipeline.tracker import CentroidTracker


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

        frames_seen = 0
        total_detections = 0
        for frame in source.frames(max_frames=smoke_frames):
            if frames_seen == 0:
                print(f"  first frame shape: {frame.image.shape}")
            detections = detector.detect(frame.image)
            tracks = tracker.update(detections)
            frames_seen += 1
            total_detections += len(detections)
            print(
                f"[frame {frame.frame_index}] detections={len(detections)} "
                f"active_tracks={len(tracks)}"
            )

        if frames_seen == 0:
            raise SystemExit("[source] video opened but no frames were read")

        print("[detector] smoke inference passed")
        print(f"  frames processed: {frames_seen}")
        print(f"  detections total: {total_detections}")
        print("[tracker] smoke tracking passed")
        print(f"  tracks kept: {len(tracker.tracks)}")
        for track in tracker.active_tracks[:10]:
            center = track.centroid
            print(
                f"  - track #{track.track_id} {track.class_name} "
                f"score={track.score:.2f} center=({center.x:.0f},{center.y:.0f})"
            )

    Path(config.video.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.video.report_path).parent.mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
