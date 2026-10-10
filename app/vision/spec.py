"""The part being inspected and the camera scale. One part type, one fixed camera."""

CATEGORIES = ("no_defect", "surface_scratch", "crack", "dimensional_deviation")

PX_PER_MM = 4.0

NOMINAL_WIDTH_MM = 120.0
NOMINAL_HEIGHT_MM = 80.0
# Smallest size difference the camera setup can reliably see. Not an acceptance limit: those live in the SOP.
MEASUREMENT_PRECISION_MM = 0.5

ID_PATTERN = r"WO-\d{5}"
ID_ALPHABET = "WO-0123456789"

# Where the ID is stamped, as fractions of the part: (left, top, right, bottom).
ID_ZONE = (0.04, 0.74, 0.50, 0.96)
