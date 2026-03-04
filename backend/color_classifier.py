"""Team color sampling and automatic jersey color classification.

Uses OpenCV HSV color analysis to:
1. Sample a team's jersey color from a user click on the frame
2. Classify bounding box crops as home/away/referee based on color distance

No API calls or pretrained models — pure color histogram analysis.
"""

import cv2
import numpy as np
from typing import Optional

# Grass mask thresholds (HSV)
_GRASS_H_LOW, _GRASS_H_HIGH = 35, 85
_GRASS_S_MIN = 40
_GRASS_V_MIN = 40

# Minimum non-grass pixels required for a valid sample
_MIN_PIXELS_SAMPLE = 20
_MIN_PIXELS_CLASSIFY = 50

# Classification confidence threshold
_RATIO_THRESHOLD = 0.7  # closest must be < 70% of second-closest

# Default referee HSV colors (bright yellow, black, fluorescent green)
DEFAULT_REFEREE_HSV = [
    np.array([25, 200, 200], dtype=np.float64),   # bright yellow
    np.array([0, 0, 40], dtype=np.float64),        # black
    np.array([42, 180, 220], dtype=np.float64),    # fluorescent green
]


def sample_jersey_color(
    image_bgr: np.ndarray,
    click_x: int,
    click_y: int,
    sample_radius: int = 15,
) -> Optional[tuple[np.ndarray, np.ndarray, str]]:
    """Sample jersey color from a click point on the image.

    Args:
        image_bgr: Full frame image (BGR numpy array).
        click_x, click_y: Click coordinates in image space.
        sample_radius: Half-size of the sampling region (default 15 -> 30x30).

    Returns:
        Tuple of (median_hsv, swatch_bgr, color_name) or None if bad sample.
        - median_hsv: numpy array [H, S, V] (H in 0-180, S/V in 0-255)
        - swatch_bgr: 40x40 BGR swatch image for UI display
        - color_name: approximate color name string
    """
    h, w = image_bgr.shape[:2]

    # Clamp region to image bounds
    x1 = max(0, click_x - sample_radius)
    y1 = max(0, click_y - sample_radius)
    x2 = min(w, click_x + sample_radius)
    y2 = min(h, click_y + sample_radius)

    if x2 - x1 < 3 or y2 - y1 < 3:
        return None

    region = image_bgr[y1:y2, x1:x2]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    # Mask grass pixels
    non_grass = _get_non_grass_pixels(hsv)

    if len(non_grass) < _MIN_PIXELS_SAMPLE:
        return None

    median_hsv = np.median(non_grass, axis=0).astype(np.float64)

    # Generate swatch and color name
    color_name = _color_name(median_hsv)
    swatch_bgr = _make_swatch(median_hsv)

    return median_hsv, swatch_bgr, color_name


def classify_box_by_color(
    crop_bgr: np.ndarray,
    home_hsv: np.ndarray,
    away_hsv: np.ndarray,
    referee_hsv: Optional[np.ndarray] = None,
) -> tuple[str, float]:
    """Classify a bounding box crop as home/away/referee/uncertain.

    Args:
        crop_bgr: Cropped bounding box image (BGR numpy array).
        home_hsv: numpy array [H, S, V] — home team reference color.
        away_hsv: numpy array [H, S, V] — away team reference color.
        referee_hsv: numpy array [H, S, V] or None — referee reference color.

    Returns:
        (classification, confidence) where classification is
        "home" | "away" | "referee" | "uncertain" and confidence is 0.0-1.0.
    """
    if crop_bgr.size == 0 or crop_bgr.shape[0] < 3 or crop_bgr.shape[1] < 3:
        return ("uncertain", 0.0)

    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)

    # Exclude grass pixels
    non_grass = _get_non_grass_pixels(hsv)

    if len(non_grass) < _MIN_PIXELS_CLASSIFY:
        return ("uncertain", 0.0)

    median_color = np.median(non_grass, axis=0).astype(np.float64)

    # Calculate distance to each reference color
    dist_home = _hsv_distance(median_color, home_hsv)
    dist_away = _hsv_distance(median_color, away_hsv)

    distances = {"home": dist_home, "away": dist_away}

    if referee_hsv is not None:
        dist_ref = _hsv_distance(median_color, referee_hsv)
        distances["referee"] = dist_ref

    # Find closest and second-closest
    sorted_dists = sorted(distances.items(), key=lambda x: x[1])
    closest_label, closest_dist = sorted_dists[0]
    _second_label, second_dist = sorted_dists[1]

    # Only classify if closest is significantly better than second
    if second_dist > 0 and closest_dist < second_dist * _RATIO_THRESHOLD:
        confidence = 1.0 - (closest_dist / second_dist)
        return (closest_label, min(confidence, 0.95))
    else:
        return ("uncertain", 0.0)


def _hsv_distance(color1: np.ndarray, color2: np.ndarray) -> float:
    """Compute weighted distance between two HSV colors.

    Hue is circular (0-180 wraps around), so we handle wraparound.
    Weights: Hue x2, Saturation x1, Value x0.5.
    """
    h_diff = abs(float(color1[0]) - float(color2[0]))
    h_diff = min(h_diff, 180.0 - h_diff)  # circular distance

    s_diff = abs(float(color1[1]) - float(color2[1]))
    v_diff = abs(float(color1[2]) - float(color2[2]))

    return (h_diff * 2.0) + (s_diff * 1.0) + (v_diff * 0.5)


def _get_non_grass_pixels(hsv: np.ndarray) -> np.ndarray:
    """Return HSV pixels that are NOT grass-colored."""
    grass_lower = np.array([_GRASS_H_LOW, _GRASS_S_MIN, _GRASS_V_MIN])
    grass_upper = np.array([_GRASS_H_HIGH, 255, 255])
    grass_mask = cv2.inRange(hsv, grass_lower, grass_upper)
    non_grass_mask = cv2.bitwise_not(grass_mask)
    return hsv[non_grass_mask > 0]


def _color_name(hsv: np.ndarray) -> str:
    """Approximate color name from HSV values."""
    h, s, v = float(hsv[0]), float(hsv[1]), float(hsv[2])

    # Low saturation + high value = White
    if s < 30 and v > 200:
        return "White"
    # Low saturation + low value = Black
    if s < 50 and v < 60:
        return "Black"
    # Low value = Dark/Black regardless of hue
    if v < 40:
        return "Black"

    # High saturation — classify by hue
    if s > 50 and v > 50:
        if h <= 10 or h >= 170:
            return "Red"
        if 10 < h <= 25:
            return "Orange"
        if 25 < h <= 35:
            return "Yellow"
        if 35 < h <= 85:
            return "Green"
        if 85 < h <= 130:
            return "Blue"
        if 130 < h < 170:
            return "Purple"

    # Gray (moderate saturation, moderate value)
    if s < 50:
        return "Gray"

    return "Unknown"


def _make_swatch(hsv: np.ndarray, size: int = 40) -> np.ndarray:
    """Create a solid-color swatch image from HSV values."""
    swatch_hsv = np.full((size, size, 3), hsv, dtype=np.uint8)
    swatch_bgr = cv2.cvtColor(swatch_hsv, cv2.COLOR_HSV2BGR)
    return swatch_bgr
