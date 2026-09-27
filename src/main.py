from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import load_config
from src.pipeline.detector import YoloDetector
from src.pipeline.source import VideoSource


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

    with VideoSource(config.video.input_path) as source:
        first_frame = next(source.frames(max_frames=1), None)
        if first_frame is None:
            raise SystemExit("[source] video opened but no frames were read")
        print("[source] smoke read passed")
        print(f"  fps: {source.fps:.2f}")
        print(f"  frames: {source.frame_count}")
        print(f"  first frame shape: {first_frame.image.shape}")

        detector = YoloDetector(
            model_path=config.model.path,
            confidence_threshold=config.model.confidence_threshold,
            image_size=config.model.image_size,
        )
        detections = detector.detect(first_frame.image)
        print("[detector] smoke inference passed")
        print(f"  detections: {len(detections)}")
        for detection in detections[:10]:
            bbox = detection.bbox
            print(
                f"  - {detection.class_name} {detection.score:.2f} "
                f"bbox=({bbox.x1:.0f},{bbox.y1:.0f},{bbox.x2:.0f},{bbox.y2:.0f})"
            )

    Path(config.video.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.video.report_path).parent.mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
