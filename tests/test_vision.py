import re

import cv2
import numpy as np
import pytest

from app.vision import spec
from app.vision.inspect import inspect_array, inspect_image
from app.vision.synthetic import generate_set


def test_generator_is_repeatable():
    first = generate_set(per_category=1, seed=3)
    second = generate_set(per_category=1, seed=3)
    assert all(np.array_equal(a[1], b[1]) and a[2] == b[2] for a, b in zip(first, second))


def test_each_category_is_classified_with_a_measurement():
    for name, image, label in generate_set(per_category=3, seed=3):
        result = inspect_array(image)
        assert result.defect_category == label["category"], name
        assert result.measurement["name"] == label["measurement"]["name"], name
        assert abs(result.measurement["value"] - label["measurement"]["value"]) < 3.0, name
        assert 0.5 <= result.confidence <= 1.0


def test_part_id_is_a_full_match_or_none():
    for _, image, _ in generate_set(per_category=3, seed=5, hard=True):
        part_id = inspect_array(image).part_id
        assert part_id is None or re.fullmatch(spec.ID_PATTERN, part_id)


def test_png_bytes_are_accepted_and_garbage_is_rejected():
    _, image, label = generate_set(per_category=1, seed=3)[0]
    encoded = cv2.imencode(".png", image)[1].tobytes()
    assert inspect_image(encoded).defect_category == label["category"]

    with pytest.raises(ValueError):
        inspect_image(b"not-a-real-image")


def test_image_without_a_part_is_rejected():
    with pytest.raises(ValueError):
        inspect_array(np.full((480, 640), 45, dtype=np.uint8))
