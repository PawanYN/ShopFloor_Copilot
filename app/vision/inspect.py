"""Classical defect classification and ID reading for one part photo."""

import re
from dataclasses import asdict, dataclass

import cv2
import numpy as np
import pytesseract

from app.vision import spec

# A line defect must be at least this long to count.
MIN_LINE_LENGTH_PX = 30
# How far a line may spread sideways and still be a straight scratch; beyond it, a crack.
MAX_SCRATCH_SPREAD_PX = 8
# Brightness difference from the surrounding surface that counts as a mark.
MARK_THRESHOLD = 22


@dataclass
class VisionResult:
    defect_category: str
    confidence: float
    measurement: dict
    part_width_mm: float
    part_height_mm: float
    part_id: str | None
    ocr_text: str

    def to_dict(self) -> dict:
        return asdict(self)


def _order_corners(box: np.ndarray) -> np.ndarray:
    """Top-left, top-right, bottom-right, bottom-left."""
    total = box.sum(axis=1)
    difference = np.diff(box, axis=1).ravel()
    return np.array(
        [box[total.argmin()], box[difference.argmin()], box[total.argmax()], box[difference.argmax()]],
        dtype=np.float32,
    )


def find_part(gray: np.ndarray) -> np.ndarray:
    """Locate the part against the darker background and return it squared up."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("no part found in the image")
    outline = max(contours, key=cv2.contourArea)
    # Too small is clutter; filling the frame means there was no background to separate from.
    if not 0.05 * gray.size < cv2.contourArea(outline) < 0.95 * gray.size:
        raise ValueError("no part found in the image")

    corners = _order_corners(cv2.boxPoints(cv2.minAreaRect(outline)))
    top_left, top_right, bottom_right, bottom_left = corners
    width = (np.linalg.norm(top_right - top_left) + np.linalg.norm(bottom_right - bottom_left)) / 2
    height = (np.linalg.norm(bottom_left - top_left) + np.linalg.norm(bottom_right - top_right)) / 2
    size = (round(width), round(height))
    target = np.array([[0, 0], [size[0] - 1, 0], [size[0] - 1, size[1] - 1], [0, size[1] - 1]], dtype=np.float32)
    return cv2.warpPerspective(gray, cv2.getPerspectiveTransform(corners, target), size)


def _id_zone(part: np.ndarray) -> tuple[int, int, int, int]:
    height, width = part.shape
    left, top, right, bottom = spec.ID_ZONE
    return int(left * width), int(top * height), int(right * width), int(bottom * height)


def find_line_defect(part: np.ndarray) -> tuple[float, float] | None:
    """Return (length, sideways spread) in pixels of the longest mark on the surface."""
    smooth = cv2.GaussianBlur(part, (3, 3), 0)
    surface = cv2.medianBlur(smooth, 31)
    marks = (cv2.absdiff(smooth, surface) > MARK_THRESHOLD).astype(np.uint8)

    left, top, right, bottom = _id_zone(part)
    marks[top:bottom, left:right] = 0
    border = 8
    marks[:border], marks[-border:], marks[:, :border], marks[:, -border:] = 0, 0, 0, 0

    marks = cv2.morphologyEx(marks, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(marks, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    longest = None
    for contour in contours:
        if cv2.contourArea(contour) < 25:
            continue
        sides = cv2.minAreaRect(contour)[1]
        if max(sides) >= MIN_LINE_LENGTH_PX and (longest is None or max(sides) > longest[0]):
            longest = (max(sides), min(sides))
    return longest


def _confidence(margin: float) -> float:
    """Heuristic: 0.5 at a decision threshold, rising to 1.0 one threshold-width away."""
    return round(0.5 + 0.5 * min(1.0, max(0.0, margin)), 2)


def classify(part: np.ndarray) -> tuple[str, float, dict]:
    width_off = part.shape[1] / spec.PX_PER_MM - spec.NOMINAL_WIDTH_MM
    height_off = part.shape[0] / spec.PX_PER_MM - spec.NOMINAL_HEIGHT_MM
    worst = width_off if abs(width_off) >= abs(height_off) else height_off
    deviation_mm = abs(worst)

    line = find_line_defect(part)
    if line is not None:
        length_px, spread_px = line
        measurement = {"name": "length_mm", "value": round(length_px / spec.PX_PER_MM, 2)}
        margin = abs(spread_px - MAX_SCRATCH_SPREAD_PX) / MAX_SCRATCH_SPREAD_PX
        category = "surface_scratch" if spread_px <= MAX_SCRATCH_SPREAD_PX else "crack"
        return category, _confidence(margin), measurement

    measurement = {
        "name": "deviation_mm",
        "value": round(deviation_mm, 2),
        "direction": "oversize" if worst > 0 else "undersize",
    }
    margin = abs(deviation_mm - spec.MEASUREMENT_PRECISION_MM) / spec.MEASUREMENT_PRECISION_MM
    category = "dimensional_deviation" if deviation_mm > spec.MEASUREMENT_PRECISION_MM else "no_defect"
    return category, _confidence(margin), measurement


def read_id(part: np.ndarray) -> tuple[str | None, str]:
    """Return (validated ID or None, raw text read)."""
    left, top, right, bottom = _id_zone(part)
    zone = cv2.resize(part[top:bottom, left:right], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    zone = cv2.GaussianBlur(zone, (5, 5), 0)
    _, binary = cv2.threshold(zone, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(binary, config=f"--psm 7 -c tessedit_char_whitelist={spec.ID_ALPHABET}").strip()
    # The whole text must be an ID: a partial match inside a longer misread is not accepted.
    candidate = text.replace(" ", "")
    return (candidate if re.fullmatch(spec.ID_PATTERN, candidate) else None), text


def inspect_image(image_bytes: bytes) -> VisionResult:
    gray = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("the file is not a readable image")
    return inspect_array(gray)


def inspect_array(gray: np.ndarray) -> VisionResult:
    part = find_part(gray)
    category, confidence, measurement = classify(part)
    part_id, ocr_text = read_id(part)
    return VisionResult(
        defect_category=category,
        confidence=confidence,
        measurement=measurement,
        part_width_mm=round(part.shape[1] / spec.PX_PER_MM, 2),
        part_height_mm=round(part.shape[0] / spec.PX_PER_MM, 2),
        part_id=part_id,
        ocr_text=ocr_text,
    )
