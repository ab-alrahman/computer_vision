"""Fine-tune YOLO11n on the 6 toll-road classes.

Lessons applied from the Week7 course material (docs/Computer_Vision_Course):
  - per-class metrics must be read through DetMetrics.ap_class_index, never by
    raw class id, because Ultralytics drops classes that have no instances
  - best.pt is picked on the val split only; test is reported, never optimised
  - the confidence threshold has to be justified with a sweep, not guessed
  - Precision is the metric that hurts citizens, Recall is the metric that
    loses revenue, so both are gated
  - results.csv keys arrive space-padded and must be stripped before parsing
  - workers=0 and amp=False are mandatory on Windows/macOS dataloaders
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("YOLO_VERBOSE", "False")

import torch
import yaml
from ultralytics import YOLO, settings

settings.update({"sync": False})

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_dataset import (  # noqa: E402
    IMAGE_SUFFIXES,
    load_dataset,
    report,
    scan_split,
)

HYPERPARAM_KEYS = {
    "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale", "shear",
    "perspective", "flipud", "fliplr", "mosaic", "mixup", "copy_paste",
}

DEFAULT_THRESHOLDS = [round(0.05 * step, 2) for step in range(1, 19)]
MATCH_IOU = 0.5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def detect_device(requested: str | int | None) -> str | int:
    if isinstance(requested, int):
        if torch.cuda.is_available():
            return requested
        raise SystemExit(
            f"[device] CUDA device {requested} was requested, but this Python environment "
            "has a CPU-only PyTorch build. Install a CUDA-enabled torch package."
        )
    if requested and requested != "auto":
        value = requested.strip().lower()
        if value.isdigit():
            device_id = int(value)
            if torch.cuda.is_available():
                return device_id
            raise SystemExit(
                f"[device] CUDA device {device_id} was requested, but this Python environment "
                "has a CPU-only PyTorch build. Install a CUDA-enabled torch package."
            )
        if value.startswith("cuda"):
            if torch.cuda.is_available():
                return 0 if value == "cuda" else int(value.split(":", 1)[1])
            raise SystemExit(
                f"[device] {requested} was requested, but this Python environment "
                "has a CPU-only PyTorch build. Install a CUDA-enabled torch package."
            )
        return requested
    mps = getattr(getattr(torch.backends, "mps", None), "is_available", None)
    if callable(mps) and mps():
        return "mps"
    if torch.cuda.is_available():
        return 0
    return "cpu"


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run_preflight(config: dict, skip: bool) -> tuple[Path, dict, dict[int, str]]:
    root, raw, names = load_dataset(Path(config["data"]))
    min_instances = config.get("min_class_instances") or {}
    splits = {s: scan_split(root, raw, s, len(names)) for s in ("train", "val", "test")}
    for info in splits.values():
        info.pop("digests", None)
    fatal = report(splits, names, min_instances, Path(config["data"]))
    if fatal and not skip:
        raise SystemExit(f"[preflight] {fatal} blocking problem(s) - fix the dataset first")
    if fatal:
        print(f"[preflight] {fatal} problem(s) reported but --skip-preflight was given")
    return root, raw, names


def split_instance_counts(root: Path, raw: dict, split: str, names: dict[int, str]) -> Counter:
    counts: Counter = Counter()
    relative = raw.get("val" if split == "val" else "test") or raw.get("val")
    if not relative:
        return counts
    labels_dir = (root / relative).parent.parent / "labels" / Path(relative).name
    if not labels_dir.is_dir():
        return counts
    for path in labels_dir.glob("*.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts:
                counts[names.get(int(float(parts[0])), parts[0])] += 1
    return counts


def build_train_args(config: dict, overrides: dict) -> dict:
    args = {
        "data": config["data"],
        "epochs": config.get("epochs", 80),
        "imgsz": config.get("imgsz", 640),
        "batch": config.get("batch", 16),
        "device": config.get("device", 0),
        "workers": 0,
        "amp": config.get("amp", True),
        "project": config.get("project", "runs"),
        "name": config.get("name", "toll6"),
        "exist_ok": config.get("exist_ok", False),
        "seed": config.get("seed", 42),
        "deterministic": config.get("deterministic", True),
        "optimizer": config.get("optimizer", "auto"),
        "lr0": config.get("lr0", 0.001),
        "lrf": config.get("lrf", 0.01),
        "cos_lr": config.get("cos_lr", True),
        "momentum": config.get("momentum", 0.937),
        "weight_decay": config.get("weight_decay", 0.0005),
        "warmup_epochs": config.get("warmup_epochs", 3),
        "patience": config.get("patience", 20),
        "freeze": config.get("freeze", None),
        "close_mosaic": config.get("close_mosaic", 10),
        "amp": config.get("amp", False),
        "cache": config.get("cache", False),
        "plots": config.get("plots", True),
        "verbose": config.get("verbose", True),
    }
    for key in HYPERPARAM_KEYS:
        if key in config:
            args[key] = config[key]
    args.update(overrides)
    if args.get("freeze") in (None, 0, "0", ""):
        args.pop("freeze", None)
    if args.get("device") in ("cpu", "mps"):
        args["amp"] = False
    if str(args.get("device")) == "cpu":
        args.setdefault("workers", 0)
    project = Path(args["project"])
    if not project.is_absolute():
        project = (Path.cwd() / project).resolve()
    args["project"] = str(project)
    return args


def read_history(run_dir: Path) -> dict:
    path = run_dir / "results.csv"
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k.strip(): v for k, v in row.items()} for row in csv.DictReader(handle)]
    rows = [r for r in rows if r.get("epoch") not in (None, "")]
    if not rows:
        return {}
    for row in rows:
        for key in ("metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/precision(B)", "metrics/recall(B)"):
            try:
                row[key] = float(row.get(key, "nan"))
            except (TypeError, ValueError):
                row[key] = float("nan")
    best = max(rows, key=lambda r: r["metrics/mAP50-95(B)"])
    final = rows[-1]

    def pick(row: dict) -> dict:
        return {
            "epoch": int(float(row["epoch"])),
            "map50": round(row["metrics/mAP50(B)"], 4),
            "map5095": round(row["metrics/mAP50-95(B)"], 4),
            "precision": round(row["metrics/precision(B)"], 4),
            "recall": round(row["metrics/recall(B)"], 4),
        }

    return {"epochsRun": len(rows), "best": pick(best), "final": pick(final)}


def per_class_metrics(model: YOLO, data: str, imgsz: int, device, split: str,
                      names: dict[int, str], instances: Counter,
                      project: Path) -> tuple[dict[str, dict], Path]:
    plots_dir = project / f"val_{split}"
    metrics = model.val(data=data, imgsz=imgsz, device=device, split=split,
                        plots=True, verbose=False, project=str(project),
                        name=f"val_{split}", exist_ok=True)
    table: dict[str, dict] = {}
    for row, class_id in enumerate(metrics.ap_class_index):
        name = names.get(int(class_id), str(int(class_id)))
        table[name] = {
            "instances": int(instances.get(name, 0)),
            "precision": round(float(metrics.box.p[row]), 4),
            "recall": round(float(metrics.box.r[row]), 4),
            "map50": round(float(metrics.box.ap50[row]), 4),
            "map5095": round(float(metrics.box.ap[row]), 4),
        }
    for name in names.values():
        if name not in table:
            count = int(instances.get(name, 0))
            table[name] = {"instances": count, "precision": 0.0, "recall": 0.0,
                           "map50": 0.0, "map5095": 0.0, "noInstances": count == 0}
    return table, plots_dir


def normalise_targets(raw: dict) -> dict[str, dict]:
    targets: dict[str, dict] = {}
    for name, value in (raw or {}).items():
        if isinstance(value, dict):
            targets[name] = {k: float(v) for k, v in value.items() if k in ("recall", "precision")}
        else:
            targets[name] = {"recall": float(value)}
    return targets


def check_targets(table: dict[str, dict], targets: dict[str, dict], label: str) -> list[str]:
    failures: list[str] = []
    if not targets:
        return failures
    print(f"\n[targets] {label}")
    for name, wanted in targets.items():
        row = table.get(name)
        if row is None:
            failures.append(f"{name}: class absent from the dataset yaml")
            print(f"  {name:<30} MISSING FROM names")
            continue
        if row.get("noInstances"):
            failures.append(f"{name}: 0 instances in this split, metrics undefined")
            print(f"  {name:<30} no instances in split")
            continue
        for metric, minimum in wanted.items():
            actual = row[metric]
            ok = actual >= minimum
            if not ok:
                failures.append(f"{name}: {metric} {actual:.3f} < target {minimum:.3f}")
            print(f"  {name:<30} {metric:<9} {actual:.3f} target {minimum:.3f} "
                  f"{'PASS' if ok else 'FAIL'}")
    return failures


def read_yolo_boxes(path: Path) -> list[tuple[int, list[float]]]:
    boxes: list[tuple[int, list[float]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        cls = int(float(parts[0]))
        xc, yc, w, h = (float(v) for v in parts[1:])
        boxes.append((cls, [xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2]))
    return boxes


def box_iou(a: list[float], b: list[float]) -> float:
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def count_matches(preds: list[tuple[int, float, list[float]]],
                  gts: list[tuple[int, list[float]]],
                  per_class: dict[int, Counter]) -> None:
    used = [False] * len(gts)
    for cls, _score, box in sorted(preds, key=lambda p: -p[1]):
        best_iou, best_idx = 0.0, -1
        for idx, (gcls, gbox) in enumerate(gts):
            if used[idx] or gcls != cls:
                continue
            value = box_iou(box, gbox)
            if value > best_iou:
                best_iou, best_idx = value, idx
        if best_iou >= MATCH_IOU:
            used[best_idx] = True
            per_class[cls]["tp"] += 1
        else:
            per_class[cls]["fp"] += 1
    for idx, (gcls, _gbox) in enumerate(gts):
        if not used[idx]:
            per_class[gcls]["fn"] += 1


def _rates(counter: Counter) -> dict:
    tp = counter["tp"]
    precision = tp / (tp + counter["fp"]) if tp + counter["fp"] else 0.0
    recall = tp / (tp + counter["fn"]) if tp + counter["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": counter["fp"], "fn": counter["fn"],
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4)}


def run_sweep(model: YOLO, images_dir: Path, labels_dir: Path, names: dict[int, str],
              train_args: dict, thresholds: list[float], min_precision: float) -> dict:
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        return {"skipped": f"no images in {images_dir}"}
    truth: dict[str, list[tuple[int, list[float]]]] = {}
    for image in images:
        label = labels_dir / f"{image.stem}.txt"
        if label.is_file():
            truth[image.name] = read_yolo_boxes(label)
    if not truth:
        return {"skipped": f"no labels in {labels_dir}"}

    rows: list[dict] = []
    for threshold in thresholds:
        per_class: dict[int, Counter] = {}
        for result in model.predict(source=[str(p) for p in images],
                                    imgsz=train_args["imgsz"], device=train_args["device"],
                                    conf=threshold, iou=0.7, verbose=False, stream=True):
            name = Path(result.path).name
            gts = truth.get(name, [])
            height, width = result.orig_shape
            preds: list[tuple[int, float, list[float]]] = []
            if result.boxes is not None and len(result.boxes):
                xyxy = result.boxes.xyxy.cpu().tolist()
                clss = result.boxes.cls.cpu().tolist()
                confs = result.boxes.conf.cpu().tolist()
                for coords, cls, conf in zip(xyxy, clss, confs):
                    cid = int(cls)
                    per_class.setdefault(cid, Counter())["pred"] += 1
                    preds.append((cid, float(conf), [
                        coords[0] / width, coords[1] / height,
                        coords[2] / width, coords[3] / height,
                    ]))
            for cid in {c for c, _ in gts}:
                per_class.setdefault(cid, Counter())
            count_matches(preds, gts, per_class)
        detail = {names.get(cid, str(cid)): _rates(counter) for cid, counter in sorted(per_class.items())}
        total = Counter()
        for counter in per_class.values():
            total.update(counter)
        overall = _rates(total)
        macro_f1 = round(sum(v["f1"] for v in detail.values()) / len(detail), 4) if detail else 0.0
        rows.append({"conf": threshold, "perClass": detail, "overall": overall, "macroF1": macro_f1})
        print(f"  conf {threshold:<5} P={overall['precision']:.3f} R={overall['recall']:.3f} "
              f"F1={overall['f1']:.3f} macroF1={macro_f1:.3f}")

    best = max(rows, key=lambda r: (r["macroF1"], r["overall"]["f1"]))
    safe = [r for r in rows if r["overall"]["precision"] >= min_precision]
    high_precision = max(safe, key=lambda r: r["conf"]) if safe else None
    return {
        "split": "val",
        "matchIou": MATCH_IOU,
        "minPrecision": min_precision,
        "rows": rows,
        "recommended": {
            "conf": best["conf"],
            "reason": "highest macro F1 on val",
            "precision": best["overall"]["precision"],
            "recall": best["overall"]["recall"],
        },
        "citizenSafe": ({
            "conf": high_precision["conf"],
            "reason": f"highest threshold keeping precision >= {min_precision}",
            "precision": high_precision["overall"]["precision"],
            "recall": high_precision["overall"]["recall"],
        } if high_precision else None),
    }


def resolve_run_dir(model: YOLO, train_args: dict) -> Path:
    trainer = getattr(model, "trainer", None)
    save_dir = getattr(trainer, "save_dir", None)
    if save_dir:
        return Path(save_dir).resolve()
    return (Path(train_args["project"]) / train_args["name"]).resolve()


def export_model(model: YOLO, config: dict, imgsz: int, run_dir: Path) -> Path | None:
    export_cfg = config.get("export") or {}
    fmt = export_cfg.get("format", "onnx")
    kwargs: dict = {"format": fmt, "imgsz": imgsz}
    if fmt == "onnx":
        kwargs["opset"] = export_cfg.get("opset", 12)
        kwargs["simplify"] = export_cfg.get("simplify", True)
        if export_cfg.get("int8"):
            kwargs["int8"] = True
    print(f"[export] {kwargs}")
    try:
        path = model.export(**kwargs)
        print(f"[export] wrote {path}")
        return Path(path).resolve()
    except Exception as exc:
        print(f"[export] FAILED: {exc}")
        return None


def write_summary(payload: dict, run_dir: Path) -> Path:
    target = run_dir / "training_summary.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[summary] wrote {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO11n on the 6 toll-road classes")
    parser.add_argument("--config", default="configs/train.yaml")
    parser.add_argument("--data")
    parser.add_argument("--model")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--device", help="auto | cpu | 0 | mps")
    parser.add_argument("--name")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--eval-test", action="store_true", help="also report the test split")
    parser.add_argument("--sweep-conf", action="store_true", help="sweep the decision threshold on val")
    parser.add_argument("--smoke", action="store_true", help="2 epochs, tiny batch, pipeline check only")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    if args.data:
        config["data"] = args.data
    if args.model:
        config["model"] = args.model

    overrides: dict = {}
    for key in ("epochs", "batch", "imgsz", "device", "name"):
        value = getattr(args, key)
        if value is not None:
            overrides[key] = value
    if args.smoke:
        overrides.update({"epochs": 2, "batch": 2, "imgsz": 320, "workers": 0})
        config["name"] = f"{config.get('name', 'toll6')}_smoke"
        print("[smoke] 2 epochs, batch 2, imgsz 320, workers 0")

    train_args = build_train_args(config, overrides)
    train_args["device"] = detect_device(train_args["device"])

    # استخدام NVIDIA GPU مع تفعيل AMP، وإجبار Windows على workers=0
    if isinstance(train_args["device"], int):
        train_args["amp"] = True
        train_args["workers"] = 0
        print(f"[gpu] NVIDIA: {torch.cuda.get_device_name(train_args['device'])}")
    else:
        train_args["amp"] = False

    print(f"[env] python {platform.python_version()} torch {torch.__version__} "
          f"device {train_args['device']} cores {os.cpu_count()}")

    if args.resume:
        last = Path(train_args["project"]) / config.get("name", "toll6") / "weights" / "last.pt"
        if not last.is_file():
            raise SystemExit(f"[resume] checkpoint not found: {last}")
        train_args["resume"] = str(last)
        print(f"[resume] {last}")

    run_preflight(config, args.skip_preflight)
    root, raw, names = load_dataset(Path(config["data"]))
    print("[train] args:")
    for key, value in sorted(train_args.items()):
        print(f"        {key} = {value}")

    started = time.time()
    model = YOLO(config.get("model", "yolo11n.pt"))
    model.train(**train_args)
    duration = time.time() - started

    run_dir = resolve_run_dir(model, train_args)
    print(f"\n[done] run directory: {run_dir}")
    best = run_dir / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit(f"[done] best.pt not produced in {run_dir}")
    trained = YOLO(str(best))

    failures: list[str] = []
    report: dict[str, dict] = {}
    val_plots: dict[str, list[str]] = {}

    for split in ("val", "test") if args.eval_test else ("val",):
        if not raw.get("val" if split == "val" else "test"):
            print(f"[eval] {split} split missing in data yaml, skipped")
            continue
        instances = split_instance_counts(root, raw, split, names)
        table, val_dir = per_class_metrics(trained, train_args["data"], train_args["imgsz"],
                                           train_args["device"], split, names, instances,
                                           run_dir)
        report[split] = table
        if val_dir.is_dir():
            val_plots[split] = sorted(p.name for p in val_dir.glob("*.png"))
        print(f"\n[eval] per-class metrics on {split}")
        print(f"  {'class':<30}{'inst':>6}{'P':>8}{'R':>8}{'mAP50':>8}{'mAP50-95':>10}")
        for name, row in table.items():
            print(f"  {name:<30}{row['instances']:>6}{row['precision']:>8.3f}"
                  f"{row['recall']:>8.3f}{row['map50']:>8.3f}{row['map5095']:>10.3f}"
                  f"{'  (no instances)' if row.get('noInstances') else ''}")
        failures += check_targets(table, normalise_targets(config.get("recall_targets") or {}), split)
        failures += check_targets(table, normalise_targets(config.get("precision_targets") or {}), split)

    sweep: dict = {}
    if args.sweep_conf:
        val_images = root / raw["val"]
        val_labels = val_images.parent.parent / "labels" / Path(raw["val"]).name
        sweep_cfg = config.get("conf_sweep") or {}
        sweep = run_sweep(trained, val_images, val_labels, names, train_args,
                          sweep_cfg.get("thresholds") or DEFAULT_THRESHOLDS,
                          float(sweep_cfg.get("min_precision", 0.95)))

    exported = None if args.no_export else export_model(trained, config, train_args["imgsz"], run_dir)

    payload = {
        "finishedAt": utc_now(),
        "gitCommit": git_commit(),
        "durationSeconds": round(duration, 1),
        "config": config,
        "trainArgs": train_args,
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "ultralytics": __import__("ultralytics").__version__,
            "cudaAvailable": torch.cuda.is_available(),
            "platform": platform.platform(),
            "cpuCount": os.cpu_count(),
        },
        "history": read_history(run_dir),
        "perSplit": report,
        "targetFailures": failures,
        "confSweep": sweep,
        "bestWeights": str(best),
        "lastWeights": str(run_dir / "weights" / "last.pt"),
        "exportedModel": str(exported) if exported else None,
        "evalPlots": val_plots,
        "trainPlots": sorted(p.name for p in run_dir.glob("*.png")),
    }
    write_summary(payload, run_dir)

    print("\n" + "=" * 72)
    if failures:
        print("TRAINING FINISHED BUT TARGETS MISSED:")
        for failure in failures:
            print(f"  - {failure}")
        print("Levers, in order: add data for the failing class, then lr0, then")
        print("freeze, then imgsz, then a larger checkpoint. conf only moves the")
        print("precision/recall trade-off, it does not fix a missing class.")
    else:
        print("TRAINING FINISHED - ALL TARGETS MET")
    print("=" * 72)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
