"""Build the ground-plane homography used for speed measurement.

Pick four points on the road surface in one video frame, tell the script how
wide and how long that rectangle really is in metres, and it writes a 3x3
matrix that turns any pixel into a ground coordinate.

    python scripts/calibrate_geometry.py
    python scripts/calibrate_geometry.py --frame-index 400 --out configs/calibration.json
    python scripts/calibrate_geometry.py --points 200,300 900,300 980,220 260,220

Click order matters and must always describe the same rectangle:
    1. near-left   2. near-right   3. far-right   4. far-left

The two metres values are the real-world size of that rectangle. The width is
usually a lane width or the full carriageway, which you can read off the road
markings. The length is the stretch between the near and far pairs; estimate it
from the video or from a map, it only fixes the scale along the road.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.types import Point  # noqa: E402
from src.pipeline.velocity import Homography  # noqa: E402

WINDOW = "calibrate geometry"
CORNER_COLORS = [(255, 80, 80), (80, 255, 80), (80, 80, 255), (255, 255, 80)]
CORNER_LABELS = ("1 near-left", "2 near-right", "3 far-right", "4 far-left")
GRID_COLOR = (0, 200, 255)


def parse_points(raw: str) -> list[tuple[float, float]]:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", raw)
    if len(numbers) % 2 != 0:
        raise argparse.ArgumentTypeError(f"expected 'x y' pairs, got {raw!r}")
    values = [float(number) for number in numbers]
    return list(zip(values[0::2], values[1::2]))


def parse_point_list(values: list[str] | None) -> list[tuple[float, float]] | None:
    if not values:
        return None
    points = [parse_points(item) for item in values]
    flat = [point for group in points for point in group]
    return flat


MIN_QUAD_AREA_PX = 5000.0


def edge_length(first: tuple[float, float], second: tuple[float, float]) -> float:
    return float(np.hypot(second[0] - first[0], second[1] - first[1]))


def validate_quad(points: list[tuple[float, float]], frame_shape: tuple[int, ...]) -> None:
    polygon = np.array(points, dtype=np.float32)
    height, width = frame_shape[:2]
    area = abs(float(cv2.contourArea(polygon)))
    if area < MIN_QUAD_AREA_PX:
        raise SystemExit(
            f"[calibrate] those four points cover only {area:.0f}px of the "
            f"{width}x{height} frame, far too little to measure a road.\n"
            "           they look like placeholder values, not corners on the tarmac.\n"
            "           rerun --frame-out, open the image, and pick four points spread\n"
            "           across the road surface, far edge higher in the frame than the near edge."
        )
    if not cv2.isContourConvex(polygon.reshape(-1, 1, 2)):
        raise SystemExit(
            "[calibrate] the four points do not form a convex quad.\n"
            "           keep the order: near-left, near-right, far-right, far-left."
        )


def warn_if_flat_perspective(points: list[tuple[float, float]]) -> None:
    near = edge_length(points[0], points[1])
    far = edge_length(points[3], points[2])
    if far >= near:
        print(
            f"[calibrate] warning: the far edge is {far:.0f}px and the near edge is {near:.0f}px.\n"
            "           the far edge should be clearly narrower, otherwise the scale along\n"
            "           the road is guesswork and every speed will be wrong."
        )


def read_frame(video_path: Path, frame_index: int) -> np.ndarray:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise SystemExit(f"[calibrate] could not open video: {video_path}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    index = max(0, min(frame_index, max(total - 1, 0)))
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise SystemExit(f"[calibrate] could not read frame {index} of {video_path}")
    print(f"[calibrate] reading frame {index} of {total} from {video_path.name}")
    return frame


def open_window(image: np.ndarray) -> None:
    try:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.imshow(WINDOW, image)
    except cv2.error as exc:
        raise SystemExit(
            "[calibrate] this OpenCV build has no GUI support, so clicking is unavailable.\n"
            "           fix: pip uninstall -y opencv-python-headless\n"
            "                pip install --force-reinstall opencv-python\n"
            "           or skip the window and type the corners yourself:\n"
            "           python scripts/calibrate_geometry.py --points x1,y1 x2,y2 x3,y3 x4,y4\n"
            f"           original error: {exc}"
        ) from exc


def pick_points(frame: np.ndarray) -> list[tuple[float, float]]:
    height, width = frame.shape[:2]
    canvas = frame.copy()
    points: list[tuple[float, float]] = []

    def on_click(event: int, x: int, y: int, _flags) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or len(points) >= 4:
            return
        if not (0 <= x < width and 0 <= y < height):
            return
        points.append((float(x), float(y)))
        index = len(points) - 1
        cv2.circle(canvas, (x, y), 7, CORNER_COLORS[index], -1)
        cv2.putText(canvas, CORNER_LABELS[index], (x + 10, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, CORNER_COLORS[index], 1, cv2.LINE_AA)
        if len(points) > 1:
            previous = points[-2]
            cv2.line(canvas, (int(previous[0]), int(previous[1])), (x, y),
                      CORNER_COLORS[index], 2)
        if len(points) == 4:
            cv2.polylines(canvas, [np.array(points, dtype=np.int32)], True,
                          GRID_COLOR, 2)
        cv2.imshow(WINDOW, canvas)

    print("\nClick the four road corners in this order:")
    for label in CORNER_LABELS:
        print(f"  {label}")
    print("Press r to reset, Esc to cancel.\n")

    open_window(canvas)
    cv2.setMouseCallback(WINDOW, on_click)

    while True:
        key = cv2.waitKey(30) & 0xFF
        if len(points) == 4:
            break
        if key in (27, ord("q")):
            cv2.destroyAllWindows()
            raise SystemExit("[calibrate] cancelled, nothing written")
        if key == ord("r"):
            points.clear()
            canvas = frame.copy()
            cv2.imshow(WINDOW, canvas)

    cv2.destroyAllWindows()
    return points


def draw_preview(frame: np.ndarray, homography: Homography,
                 out_path: Path | None) -> None:
    height, width = frame.shape[:2]
    preview = frame.copy()
    reference = homography.reference
    width_m = float(reference.get("widthMeters", 3.5))
    length_m = float(reference.get("lengthMeters", 10.0))

    for metres in (5.0, 10.0, 15.0, 20.0):
        if metres > length_m:
            break
        row = [(x, metres) for x in np.linspace(0.0, width_m, 9)]
        _draw_world_line(preview, homography, row, GRID_COLOR)

    for x_metres in np.linspace(0.0, width_m, 9):
        _draw_world_line(preview, homography, [(x_metres, 0.0), (x_metres, length_m)], GRID_COLOR)

    cv2.putText(preview, f"1px = {width_m:.2f}m across x {length_m:.2f}m along",
                (12, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GRID_COLOR, 1, cv2.LINE_AA)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), preview)
        print(f"[calibrate] wrote preview {out_path}")


def _draw_world_line(image: np.ndarray, homography: Homography,
                     world_line: list[tuple[float, float]], color) -> None:
    pixels = [homography.inverse_project(Point(x, y)) for x, y in world_line]
    for first, second in zip(pixels, pixels[1:]):
        cv2.line(image, (int(first[0]), int(first[1])), (int(second[0]), int(second[1])),
                 color, 1, cv2.LINE_AA)


def metres_per_pixel_report(homography: Homography) -> dict[str, float]:
    reference = homography.reference
    width_m = float(reference.get("widthMeters", 0.0))
    length_m = float(reference.get("lengthMeters", 0.0))
    origin = homography.inverse_project(Point(0.0, 0.0))
    near_right = homography.inverse_project(Point(width_m, 0.0))
    far_left = homography.inverse_project(Point(0.0, length_m))
    return {
        "nearWidthPx": round(float(abs(near_right[0] - origin[0])), 2),
        "roadDepthPx": round(float(abs(far_left[1] - origin[1])), 2),
    }


def ask_reference() -> tuple[float, float]:
    default_width = 3.5
    default_length = 10.0
    try:
        width_m = float(input(f"road width in metres [{default_width}]: ") or default_width)
    except ValueError:
        width_m = default_width
    try:
        length_m = float(input(f"road length in metres [{default_length}]: ") or default_length)
    except ValueError:
        length_m = default_length
    if width_m <= 0 or length_m <= 0:
        raise SystemExit("[calibrate] reference distances must be positive")
    return width_m, length_m


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate the ground-plane homography")
    parser.add_argument("--video", default="data/raw/video/Road traffic video for object recognition.mp4")
    parser.add_argument("--frame-index", type=int, default=0)
    parser.add_argument("--out", default="configs/calibration.json")
    parser.add_argument("--preview", default="runs/vision/calibration_preview.jpg")
    parser.add_argument("--width-m", type=float, help="skip the prompt and use this width")
    parser.add_argument("--length-m", type=float, help="skip the prompt and use this length")
    parser.add_argument("--points", nargs="+",
                        help="non-interactive mode: 'x y' pairs, four of them")
    parser.add_argument("--frame-out",
                        help="dump the chosen frame to this image and exit, "
                             "so you can read the corners in any viewer")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"[calibrate] video not found: {video_path}")

    frame = read_frame(video_path, args.frame_index)

    points = parse_point_list(args.points)
    if points is None and args.frame_out:
        frame_out = Path(args.frame_out)
        frame_out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(frame_out), frame)
        print(f"[calibrate] wrote the frame to {frame_out}")
        print("[calibrate] open it in any viewer, read the four corners, then rerun with --points")
        return 0
    if points is None:
        points = pick_points(frame)
    if len(points) != 4:
        raise SystemExit(f"[calibrate] expected four points, got {len(points)}")
    validate_quad(points, frame.shape)
    warn_if_flat_perspective(points)

    if args.width_m and args.length_m:
        width_m, length_m = args.width_m, args.length_m
    elif args.width_m or args.length_m:
        raise SystemExit("[calibrate] give both --width-m and --length-m")
    else:
        width_m, length_m = ask_reference()

    homography = Homography.from_corners(points, width_m, length_m)
    out_path = homography.save(
        args.out,
        extra={
            "video": str(video_path),
            "frameIndex": args.frame_index,
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )

    print(f"\n[calibrate] reference rectangle: {width_m:.2f}m x {length_m:.2f}m")
    for index, (x, y) in enumerate(points):
        print(f"  {CORNER_LABELS[index]:<14} ({x:.0f}, {y:.0f})")
    report = metres_per_pixel_report(homography)
    print(f"  near edge spans {report['nearWidthPx']:.0f}px across the road")
    print(f"  road depth spans {report['roadDepthPx']:.0f}px along it")
    print(f"[calibrate] wrote {out_path}")

    try:
        draw_preview(frame, homography, Path(args.preview) if args.preview else None)
    except Exception as exc:  # noqa: BLE001 - preview is a convenience, never fatal
        print(f"[calibrate] preview skipped: {exc}")

    print("\nSanity check: run the pipeline and read averageSpeedKph in the report.")
    print("A car on a 60 km/h road should land near 60, not 6 or 600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())