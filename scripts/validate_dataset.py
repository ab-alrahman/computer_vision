from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_dataset(data_yaml: Path) -> tuple[Path, dict, dict[int, str]]:
    raw = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    names = raw.get("names")
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}
    if not names:
        raise ValueError(f"{data_yaml}: 'names' is empty or missing")
    root = Path(raw.get("path") or data_yaml.parent)
    if root.is_absolute():
        candidates = [root]
    else:
        candidates = [(data_yaml.parent / root).resolve(), (Path.cwd() / root).resolve()]
    for candidate in candidates:
        if candidate.is_dir():
            root = candidate
            break
    else:
        root = candidates[0]
    return root, raw, {int(k): str(v) for k, v in names.items()}


def parse_label_file(path: Path, num_classes: int) -> tuple[Counter, list[str]]:
    counts: Counter = Counter()
    errors: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"{path.name}:{lineno} expected 5 fields, got {len(parts)}")
            continue
        try:
            cls = int(float(parts[0]))
            coords = [float(v) for v in parts[1:]]
        except ValueError:
            errors.append(f"{path.name}:{lineno} non-numeric content")
            continue
        if not 0 <= cls < num_classes:
            errors.append(f"{path.name}:{lineno} class id {cls} out of range 0..{num_classes - 1}")
            continue
        if any(not 0.0 <= v <= 1.0 for v in coords):
            errors.append(f"{path.name}:{lineno} coordinates must be normalized to 0..1")
            continue
        width, height = coords[2], coords[3]
        if width <= 0.0 or height <= 0.0:
            errors.append(f"{path.name}:{lineno} zero-area box (w<=0 or h<=0)")
            continue
        x1, y1 = coords[0] - width / 2, coords[1] - height / 2
        x2, y2 = coords[0] + width / 2, coords[1] + height / 2
        if x2 <= 0.0 or y2 <= 0.0 or x1 >= 1.0 or y1 >= 1.0:
            errors.append(f"{path.name}:{lineno} box lies entirely outside the image")
            continue
        counts[cls] += 1
    return counts, errors


def file_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def perceptual_digest(path: Path, size: int = 16) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for the leakage check") from exc
    with Image.open(path) as img:
        img = img.convert("L").resize((size, size), Image.Resampling.BILINEAR)
        return hashlib.sha1(img.tobytes()).hexdigest()


def scan_split(root: Path, raw: dict, split: str, num_classes: int) -> dict:
    if split not in raw:
        return {"missing": True}
    images_dir = (root / raw[split]).resolve()
    labels_dir = (root / raw[split].replace("images", "labels")).resolve()

    if not images_dir.is_dir():
        return {"missing": False, "exists": False, "dir": str(images_dir)}

    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    labels = sorted(p for p in labels_dir.glob("*.txt")) if labels_dir.is_dir() else []

    class_counts: Counter = Counter()
    errors: list[str] = []
    orphans_img: list[str] = []
    digests: dict[str, str] = {}

    for img in images:
        label = labels_dir / f"{img.stem}.txt"
        if not label.exists():
            orphans_img.append(img.name)
            continue
        counts, errs = parse_label_file(label, num_classes)
        class_counts.update(counts)
        errors.extend(errs)
        try:
            digests[img.name] = perceptual_digest(img)
        except Exception:
            digests[img.name] = file_digest(img)

    return {
        "missing": False,
        "exists": True,
        "dir": str(images_dir),
        "num_images": len(images),
        "num_labels": len(labels),
        "num_background": len(orphans_img),
        "background_files": orphans_img[:10],
        "class_counts": class_counts,
        "errors": errors,
        "digests": digests,
    }


def check_leakage(splits: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    train = splits.get("train", {}).get("digests") or {}
    val = splits.get("val", {}).get("digests") or {}
    shared = set(train.values()) & set(val.values())
    if shared:
        problems.append(
            f"{len(shared)} near-duplicate image(s) appear in both train and val "
            "(split by source, not by frame)"
        )
    return problems


def report(splits: dict, names: dict[int, str], min_instances: dict[str, int], data_yaml: Path) -> int:
    num_classes = len(names)
    print("=" * 72)
    print(f"dataset: {data_yaml}")
    print(f"classes: {num_classes} -> " + ", ".join(f"{i}:{n}" for i, n in sorted(names.items())))
    print("=" * 72)

    fatal = 0
    totals: Counter = Counter()

    for split in ("train", "val", "test"):
        info = splits.get(split, {})
        if info.get("missing"):
            print(f"\n[{split}] not defined in data.yaml (optional)")
            continue
        if not info.get("exists"):
            print(f"\n[{split}] MISSING directory: {info.get('dir')}")
            fatal += 1
            continue

        print(f"\n[{split}] images={info['num_images']} labels={info['num_labels']} background={info['num_background']}")
        if info["num_images"] == 0:
            print("  ERROR: no images found")
            fatal += 1
            continue
        if info["num_images"] != info["num_labels"]:
            print(f"  WARNING: {info['num_images'] - info['num_labels']} image(s) without a label file")
        for line in info["errors"][:10]:
            print(f"  ERROR: {line}")
        fatal += len(info["errors"])

        for cls_id, count in sorted(info["class_counts"].items()):
            name = names.get(cls_id, f"unknown_{cls_id}")
            totals[name] += count
            print(f"    {cls_id:>2} {name:<28} {count:>6}")

        for cls_id in range(num_classes):
            if info["class_counts"].get(cls_id, 0) == 0:
                print(f"  WARNING: class {cls_id} ({names[cls_id]}) has zero instances in {split}")

    print("\n" + "-" * 72)
    print("merged train+val instance totals")
    for name in names.values():
        print(f"    {name:<28} {totals.get(name, 0):>6}")

    print("\nminimum-instance gate")
    for name, minimum in min_instances.items():
        actual = totals.get(name, 0)
        status = "OK" if actual >= minimum else "FAIL"
        if actual < minimum:
            fatal += 1
        print(f"    {name:<28} {actual:>6} / {minimum:<6} {status}")

    for problem in check_leakage(splits):
        print(f"\nLEAKAGE: {problem}")
        fatal += 1

    print("\n" + "=" * 72)
    if fatal:
        print(f"RESULT: FAILED ({fatal} blocking problem(s))")
    else:
        print("RESULT: PASSED - ready to train")
    print("=" * 72)
    return fatal


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight validation for a YOLO dataset")
    parser.add_argument("--data", default="data/toll6k.yaml", help="path to data.yaml")
    parser.add_argument("--min-config", default="configs/train.yaml", help="path to train.yaml")
    parser.add_argument("--check-leakage", action="store_true", help="also compare train/val perceptual hashes")
    args = parser.parse_args()

    data_yaml = Path(args.data).resolve()
    if not data_yaml.is_file():
        print(f"ERROR: data yaml not found: {data_yaml}")
        return 2

    root, raw, names = load_dataset(data_yaml)
    min_instances: dict[str, int] = {}
    min_config = Path(args.min_config)
    if min_config.is_file():
        config = yaml.safe_load(min_config.read_text(encoding="utf-8")) or {}
        min_instances = config.get("min_class_instances") or {}

    num_classes = len(names)
    splits = {s: scan_split(root, raw, s, num_classes) for s in ("train", "val", "test")}

    if not args.check_leakage:
        for info in splits.values():
            info.pop("digests", None)

    return 1 if report(splits, names, min_instances, data_yaml) else 0


if __name__ == "__main__":
    sys.exit(main())
