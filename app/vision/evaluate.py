"""Measure the classifier and ID reader against images with known answers.

    python -m app.vision.evaluate --dir data/images
    python -m app.vision.evaluate --per-category 25 --seed 11 [--hard]
"""

import argparse
import json
from pathlib import Path

import cv2

from app.vision import spec
from app.vision.inspect import inspect_array
from app.vision.synthetic import generate_set


def load_set(directory: str) -> list[tuple[str, object, dict]]:
    folder = Path(directory)
    labels = json.loads((folder / "labels.json").read_text())
    return [(name, cv2.imread(str(folder / name), cv2.IMREAD_GRAYSCALE), label) for name, label in labels.items()]


def evaluate(items: list[tuple[str, object, dict]]) -> dict:
    confusion = {truth: {predicted: 0 for predicted in spec.CATEGORIES} for truth in spec.CATEGORIES}
    errors, ids_right, misses = [], 0, []
    for name, image, label in items:
        result = inspect_array(image)
        confusion[label["category"]][result.defect_category] += 1
        if result.defect_category == label["category"]:
            errors.append(abs(result.measurement["value"] - label["measurement"]["value"]))
        else:
            misses.append(f"{name}: expected {label['category']}, got {result.defect_category}")
        if result.part_id == label["id"]:
            ids_right += 1
        else:
            misses.append(f"{name}: expected ID {label['id']}, read {result.ocr_text!r}")
    return {
        "total": len(items),
        "confusion": confusion,
        "measurement_error_mm": sum(errors) / len(errors) if errors else None,
        "ids_right": ids_right,
        "misses": misses,
    }


def report(result: dict) -> None:
    confusion = result["confusion"]
    width = max(len(category) for category in spec.CATEGORIES)
    correct = sum(confusion[category][category] for category in spec.CATEGORIES)

    print(f"{'actual / predicted':<{width}}  " + "  ".join(f"{c[:9]:>9}" for c in spec.CATEGORIES) + "   accuracy")
    for truth in spec.CATEGORIES:
        row = confusion[truth]
        count = sum(row.values())
        accuracy = f"{row[truth] / count:.0%}" if count else "n/a"
        print(f"{truth:<{width}}  " + "  ".join(f"{row[c]:>9}" for c in spec.CATEGORIES) + f"   {accuracy:>8}")

    print(f"\ncategory accuracy : {correct}/{result['total']} ({correct / result['total']:.0%})")
    if result["measurement_error_mm"] is not None:
        print(f"measurement error : {result['measurement_error_mm']:.2f} mm average, on correctly classified images")
    print(f"ID exact match    : {result['ids_right']}/{result['total']} ({result['ids_right'] / result['total']:.0%})")
    for miss in result["misses"]:
        print(f"  miss  {miss}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", help="folder of images with a labels.json")
    parser.add_argument("--per-category", type=int, default=25)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--hard", action="store_true")
    args = parser.parse_args()

    items = load_set(args.dir) if args.dir else generate_set(args.per_category, args.seed, args.hard)
    report(evaluate(items))


if __name__ == "__main__":
    main()
