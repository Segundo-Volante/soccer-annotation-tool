"""Tests for backend/color_classifier.py — jersey color sampling and classification."""

import numpy as np
import pytest
import cv2

from backend.color_classifier import (
    sample_jersey_color,
    classify_box_by_color,
    _hsv_distance,
    _color_name,
    _get_non_grass_pixels,
    DEFAULT_REFEREE_HSV,
)


# ── Helpers ──

def _solid_bgr(bgr_color, w=100, h=100):
    """Create a solid-color BGR image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = bgr_color
    return img


def _grass_bgr(w=100, h=100):
    """Create a green grass-like image."""
    # Green in BGR: (0, 128, 0) → HSV roughly (60, 255, 128)
    return _solid_bgr((0, 128, 0), w, h)


def _hsv_to_bgr_pixel(h, s, v):
    """Convert HSV values to BGR tuple."""
    hsv = np.array([[[h, s, v]]], dtype=np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return tuple(int(x) for x in bgr[0, 0])


# ── Tests for sample_jersey_color ──

class TestSampleJerseyColor:
    def test_solid_red_jersey(self):
        """Sample from a solid red region should return Red."""
        img = _solid_bgr((0, 0, 200))  # BGR red
        result = sample_jersey_color(img, 50, 50)
        assert result is not None
        hsv, swatch, name = result
        assert name == "Red"
        assert swatch.shape == (40, 40, 3)

    def test_solid_blue_jersey(self):
        """Sample from a solid blue region should return Blue."""
        img = _solid_bgr((200, 0, 0))  # BGR blue
        result = sample_jersey_color(img, 50, 50)
        assert result is not None
        hsv, swatch, name = result
        assert name == "Blue"

    def test_solid_yellow(self):
        img = _solid_bgr((0, 255, 255))  # BGR yellow
        result = sample_jersey_color(img, 50, 50)
        assert result is not None
        _, _, name = result
        assert name == "Yellow"

    def test_solid_white(self):
        img = _solid_bgr((255, 255, 255))
        result = sample_jersey_color(img, 50, 50)
        assert result is not None
        _, _, name = result
        assert name == "White"

    def test_all_grass_returns_none(self):
        """Sampling pure grass should return None (all pixels masked)."""
        img = _grass_bgr()
        result = sample_jersey_color(img, 50, 50)
        assert result is None

    def test_click_near_edge(self):
        """Sampling near the image edge should clamp correctly."""
        img = _solid_bgr((0, 0, 200), 30, 30)  # small image
        result = sample_jersey_color(img, 2, 2, sample_radius=15)
        assert result is not None
        _, _, name = result
        assert name == "Red"

    def test_click_out_of_bounds_still_works(self):
        """Click coordinates beyond image should clamp to valid region."""
        img = _solid_bgr((200, 0, 0), 50, 50)
        result = sample_jersey_color(img, 48, 48, sample_radius=15)
        assert result is not None

    def test_mixed_grass_and_jersey(self):
        """Image with both grass and jersey pixels should exclude grass."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        # Top half: grass green
        img[:50, :] = (0, 128, 0)  # BGR green
        # Bottom half: red jersey
        img[50:, :] = (0, 0, 200)  # BGR red
        # Sample from center — gets both grass and red
        result = sample_jersey_color(img, 50, 50, sample_radius=40)
        assert result is not None
        _, _, name = result
        assert name == "Red"

    def test_returns_correct_hsv_shape(self):
        img = _solid_bgr((0, 0, 200))
        result = sample_jersey_color(img, 50, 50)
        assert result is not None
        hsv, _, _ = result
        assert hsv.shape == (3,)
        assert hsv.dtype == np.float64


# ── Tests for classify_box_by_color ──

class TestClassifyBoxByColor:
    def test_red_vs_blue_home(self):
        """Red crop should classify as home when home=red, away=blue."""
        crop = _solid_bgr((0, 0, 200))  # red
        home_hsv = np.array([0, 200, 200], dtype=np.float64)  # red
        away_hsv = np.array([120, 200, 200], dtype=np.float64)  # blue
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "home"
        assert conf > 0.3

    def test_blue_vs_red_away(self):
        """Blue crop should classify as away when home=red, away=blue."""
        crop = _solid_bgr((200, 0, 0))  # blue
        home_hsv = np.array([0, 200, 200], dtype=np.float64)
        away_hsv = np.array([120, 200, 200], dtype=np.float64)
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "away"
        assert conf > 0.3

    def test_referee_classification(self):
        """Yellow crop should classify as referee when referee=yellow."""
        crop = _solid_bgr((0, 255, 255))  # yellow
        home_hsv = np.array([0, 200, 200], dtype=np.float64)   # red
        away_hsv = np.array([120, 200, 200], dtype=np.float64)  # blue
        ref_hsv = np.array([25, 200, 200], dtype=np.float64)   # yellow
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv, ref_hsv)
        assert label == "referee"
        assert conf > 0.3

    def test_similar_colors_uncertain(self):
        """When home and away are very similar, result should be uncertain."""
        crop = _solid_bgr((0, 0, 200))  # red
        home_hsv = np.array([0, 200, 200], dtype=np.float64)   # red
        away_hsv = np.array([5, 200, 200], dtype=np.float64)   # also red-ish
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "uncertain"

    def test_all_grass_crop_uncertain(self):
        """Pure grass crop should return uncertain."""
        crop = _grass_bgr(50, 50)
        home_hsv = np.array([0, 200, 200], dtype=np.float64)
        away_hsv = np.array([120, 200, 200], dtype=np.float64)
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "uncertain"
        assert conf == 0.0

    def test_tiny_crop_uncertain(self):
        """Very small crop should return uncertain."""
        crop = np.zeros((2, 2, 3), dtype=np.uint8)
        home_hsv = np.array([0, 200, 200], dtype=np.float64)
        away_hsv = np.array([120, 200, 200], dtype=np.float64)
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "uncertain"

    def test_empty_crop_uncertain(self):
        """Empty crop should return uncertain."""
        crop = np.zeros((0, 0, 3), dtype=np.uint8)
        home_hsv = np.array([0, 200, 200], dtype=np.float64)
        away_hsv = np.array([120, 200, 200], dtype=np.float64)
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert label == "uncertain"

    def test_confidence_capped_at_095(self):
        """Confidence should never exceed 0.95."""
        # Very distinct colors should have high but capped confidence
        crop = _solid_bgr((0, 0, 200))  # strong red
        home_hsv = np.array([0, 255, 255], dtype=np.float64)
        away_hsv = np.array([120, 255, 255], dtype=np.float64)
        _, conf = classify_box_by_color(crop, home_hsv, away_hsv)
        assert conf <= 0.95

    def test_no_referee_still_works(self):
        """Classification works without referee reference."""
        crop = _solid_bgr((200, 0, 0))  # blue
        home_hsv = np.array([0, 200, 200], dtype=np.float64)
        away_hsv = np.array([120, 200, 200], dtype=np.float64)
        label, conf = classify_box_by_color(crop, home_hsv, away_hsv, referee_hsv=None)
        assert label == "away"


# ── Tests for _hsv_distance ──

class TestHSVDistance:
    def test_identical_colors_zero_distance(self):
        c = np.array([90, 128, 128], dtype=np.float64)
        assert _hsv_distance(c, c) == 0.0

    def test_hue_wraparound(self):
        """Red at H=5 and H=175 should be close (distance ~10, not ~340)."""
        c1 = np.array([5, 200, 200], dtype=np.float64)
        c2 = np.array([175, 200, 200], dtype=np.float64)
        dist = _hsv_distance(c1, c2)
        # Hue diff = min(170, 180-170) = 10, weighted x2 = 20
        assert dist == 20.0

    def test_hue_wraparound_small_gap(self):
        """H=0 and H=179 should be very close."""
        c1 = np.array([0, 200, 200], dtype=np.float64)
        c2 = np.array([179, 200, 200], dtype=np.float64)
        dist = _hsv_distance(c1, c2)
        # Hue diff = min(179, 180-179) = 1, weighted x2 = 2
        assert dist == 2.0

    def test_saturation_distance(self):
        c1 = np.array([90, 100, 200], dtype=np.float64)
        c2 = np.array([90, 200, 200], dtype=np.float64)
        dist = _hsv_distance(c1, c2)
        assert dist == 100.0  # S diff = 100, weight 1.0

    def test_value_distance(self):
        c1 = np.array([90, 200, 100], dtype=np.float64)
        c2 = np.array([90, 200, 200], dtype=np.float64)
        dist = _hsv_distance(c1, c2)
        assert dist == 50.0  # V diff = 100, weight 0.5

    def test_combined_distance(self):
        c1 = np.array([10, 100, 100], dtype=np.float64)
        c2 = np.array([20, 150, 200], dtype=np.float64)
        dist = _hsv_distance(c1, c2)
        # H: 10*2=20, S: 50*1=50, V: 100*0.5=50 → total=120
        assert dist == 120.0


# ── Tests for _color_name ──

class TestColorName:
    @pytest.mark.parametrize("hsv,expected", [
        (np.array([0, 200, 200]), "Red"),
        (np.array([175, 200, 200]), "Red"),
        (np.array([5, 200, 200]), "Red"),
        (np.array([15, 200, 200]), "Orange"),
        (np.array([30, 200, 200]), "Yellow"),
        (np.array([60, 200, 200]), "Green"),
        (np.array([100, 200, 200]), "Blue"),
        (np.array([120, 200, 200]), "Blue"),
        (np.array([150, 200, 200]), "Purple"),
        (np.array([0, 10, 240]), "White"),
        (np.array([0, 20, 30]), "Black"),
        (np.array([90, 30, 128]), "Gray"),
    ])
    def test_color_names(self, hsv, expected):
        assert _color_name(hsv) == expected


# ── Tests for _get_non_grass_pixels ──

class TestGetNonGrassPixels:
    def test_all_grass_returns_empty(self):
        """All grass pixels should be filtered out."""
        hsv = np.full((10, 10, 3), [60, 128, 128], dtype=np.uint8)
        result = _get_non_grass_pixels(hsv)
        assert len(result) == 0

    def test_no_grass_returns_all(self):
        """Non-grass pixels should all pass through."""
        hsv = np.full((10, 10, 3), [0, 200, 200], dtype=np.uint8)  # red
        result = _get_non_grass_pixels(hsv)
        assert len(result) == 100  # 10x10

    def test_mixed_filters_correctly(self):
        hsv = np.zeros((10, 10, 3), dtype=np.uint8)
        hsv[:5, :] = [60, 128, 128]  # grass (top half)
        hsv[5:, :] = [0, 200, 200]   # red (bottom half)
        result = _get_non_grass_pixels(hsv)
        assert len(result) == 50  # only bottom half


# ── Tests for DEFAULT_REFEREE_HSV ──

class TestDefaultRefereeHSV:
    def test_defaults_exist(self):
        assert len(DEFAULT_REFEREE_HSV) == 3

    def test_defaults_are_numpy_arrays(self):
        for ref in DEFAULT_REFEREE_HSV:
            assert isinstance(ref, np.ndarray)
            assert ref.shape == (3,)
