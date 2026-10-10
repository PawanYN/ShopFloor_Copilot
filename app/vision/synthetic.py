"""Generate mock part images with a known defect, measurement and stamped ID.

    python -m app.vision.synthetic --out data/images --per-category 3 --seed 7
"""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from app.vision import spec

IMAGE_SIZE = (640, 480)
BACKGROUND = 45
PLATE = 175


def _plate(rng: np.random.Generator, width_px: int, height_px: int) -> np.ndarray:
    plate = np.full((height_px, width_px), PLATE, dtype=np.float32)
    plate += rng.normal(0, 3, (height_px, 1))  # brushed-metal streaks
    return plate


def _stamp_id(plate: np.ndarray, part_id: str) -> None:
    height, width = plate.shape
    origin = (int(0.07 * width), int(0.90 * height))
    cv2.putText(plate, part_id, origin, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 60, 2, cv2.LINE_AA)


def _defect_area(plate: np.ndarray) -> tuple[float, float, float, float]:
    height, width = plate.shape
    return 0.08 * width, 0.10 * height, 0.92 * width, 0.62 * height


def _inside(points: np.ndarray, area: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = area
    return bool(
        (points[:, 0] > x0).all() and (points[:, 0] < x1).all()
        and (points[:, 1] > y0).all() and (points[:, 1] < y1).all()
    )


def _extent_px(points: np.ndarray) -> float:
    return float(max(cv2.minAreaRect(points.astype(np.float32))[1]))


def _draw_scratch(plate: np.ndarray, rng: np.random.Generator) -> float:
    area = _defect_area(plate)
    while True:
        length = rng.uniform(60, 200)
        angle = rng.uniform(0, math.pi)
        centre = np.array([rng.uniform(area[0], area[2]), rng.uniform(area[1], area[3])])
        half = 0.5 * length * np.array([math.cos(angle), math.sin(angle)])
        points = np.array([centre - half, centre + half])
        if _inside(points, area):
            break
    start, end = points.round().astype(int)
    cv2.line(plate, tuple(map(int, start)), tuple(map(int, end)), 235, 2, cv2.LINE_AA)
    return length


def _walk(rng: np.random.Generator, start: np.ndarray, heading: float, steps: int) -> np.ndarray:
    points = [start]
    for _ in range(steps):
        heading += rng.uniform(-0.7, 0.7)
        step = rng.uniform(12, 22)
        points.append(points[-1] + step * np.array([math.cos(heading), math.sin(heading)]))
    return np.array(points)


def _draw_crack(plate: np.ndarray, rng: np.random.Generator) -> float:
    area = _defect_area(plate)
    while True:
        start = np.array([rng.uniform(area[0], area[2]), rng.uniform(area[1], area[3])])
        heading = rng.uniform(0, 2 * math.pi)
        trunk = _walk(rng, start, heading, int(rng.integers(6, 11)))
        fork = trunk[len(trunk) // 2]
        branch = _walk(rng, fork, heading + rng.choice([-1, 1]) * rng.uniform(0.7, 1.2), 3)
        points = np.vstack([trunk, branch])
        # A crack must wander; a walk that happens to stay straight is redrawn.
        if _inside(points, area) and min(cv2.minAreaRect(points.astype(np.float32))[1]) > 14:
            break
    for line in (trunk, branch):
        cv2.polylines(plate, [line.round().astype(np.int32)], False, 55, 3, cv2.LINE_AA)
    return _extent_px(points)


def make_image(category: str, rng: np.random.Generator, hard: bool = False) -> tuple[np.ndarray, dict]:
    width_mm = spec.NOMINAL_WIDTH_MM + rng.uniform(-0.2, 0.2)
    height_mm = spec.NOMINAL_HEIGHT_MM + rng.uniform(-0.2, 0.2)
    if category == "dimensional_deviation":
        delta = rng.choice([-1, 1]) * rng.uniform(2.5, 6.0)
        if rng.random() < 0.5:
            width_mm += delta
        else:
            height_mm += delta
    width_px = round(width_mm * spec.PX_PER_MM)
    height_px = round(height_mm * spec.PX_PER_MM)

    plate = _plate(rng, width_px, height_px)
    part_id = f"WO-{rng.integers(10000, 100000)}"
    _stamp_id(plate, part_id)

    deviation_mm = max(
        abs(width_px / spec.PX_PER_MM - spec.NOMINAL_WIDTH_MM),
        abs(height_px / spec.PX_PER_MM - spec.NOMINAL_HEIGHT_MM),
    )
    measurement = {"name": "deviation_mm", "value": round(deviation_mm, 2)}
    if category == "surface_scratch":
        measurement = {"name": "length_mm", "value": round(_draw_scratch(plate, rng) / spec.PX_PER_MM, 2)}
    elif category == "crack":
        measurement = {"name": "length_mm", "value": round(_draw_crack(plate, rng) / spec.PX_PER_MM, 2)}

    image_width, image_height = IMAGE_SIZE
    image = np.full((image_height, image_width), BACKGROUND, dtype=np.float32)
    top, left = (image_height - height_px) // 2, (image_width - width_px) // 2
    image[top:top + height_px, left:left + width_px] = plate

    max_angle = 5.0 if hard else 2.0
    rotation = cv2.getRotationMatrix2D((image_width / 2, image_height / 2), rng.uniform(-max_angle, max_angle), 1.0)
    image = cv2.warpAffine(image, rotation, IMAGE_SIZE, flags=cv2.INTER_LINEAR, borderValue=BACKGROUND)

    # Uneven lighting across the frame, then sensor noise.
    ramp = np.linspace(-0.5, 0.5, image_width, dtype=np.float32)[None, :]
    image *= 1 + (0.45 if hard else 0.2) * rng.choice([-1, 1]) * ramp
    image += rng.normal(0, 14 if hard else 6, image.shape)
    image = np.clip(image, 0, 255).astype(np.uint8)
    if hard:
        image = cv2.GaussianBlur(image, (3, 3), 0)

    return image, {"category": category, "measurement": measurement, "id": part_id}


def generate_set(per_category: int, seed: int, hard: bool = False) -> list[tuple[str, np.ndarray, dict]]:
    rng = np.random.default_rng(seed)
    items = []
    for category in spec.CATEGORIES:
        for index in range(1, per_category + 1):
            image, label = make_image(category, rng, hard)
            items.append((f"{category}_{index:02d}.png", image, label))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-category", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hard", action="store_true", help="stronger noise, lighting and rotation")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = {}
    for name, image, label in generate_set(args.per_category, args.seed, args.hard):
        cv2.imwrite(str(out / name), image)
        labels[name] = label
    (out / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    print(f"wrote {len(labels)} images to {out}")


if __name__ == "__main__":
    main()
