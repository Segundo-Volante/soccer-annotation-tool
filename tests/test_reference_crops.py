"""Tests for FileManager reference crop functionality."""

import os
import tempfile

import cv2
import numpy as np
import pytest

from backend.file_manager import FileManager, REFERENCE_CROP_SIZE


@pytest.fixture
def sample_image():
    """Create a sample image for testing."""
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


def test_reference_crop_filename():
    """Test reference crop filename generation."""
    assert FileManager.reference_crop_filename("home", 7) == "home_07.jpg"
    assert FileManager.reference_crop_filename("away", 13) == "away_13.jpg"
    assert FileManager.reference_crop_filename("home", 1) == "home_01.jpg"


def test_get_reference_crops_dir():
    """Test reference crops directory creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        crops_dir = FileManager.get_reference_crops_dir(tmpdir)
        assert crops_dir.exists()
        assert crops_dir.name == "reference_crops"


def test_save_reference_crop(sample_image):
    """Test saving a reference crop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = FileManager.save_reference_crop(
            sample_image, 100, 200, 50, 80, tmpdir, "home", 7,
        )
        assert result is not None
        assert result.exists()
        assert result.name == "home_07.jpg"

        # Check the saved image is the right size
        saved = cv2.imread(str(result))
        assert saved is not None
        assert saved.shape[0] == REFERENCE_CROP_SIZE
        assert saved.shape[1] == REFERENCE_CROP_SIZE


def test_save_reference_crop_replaces_smaller(sample_image):
    """Test that a larger crop replaces a smaller one."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # First crop: small (20x30)
        result1 = FileManager.save_reference_crop(
            sample_image, 100, 200, 20, 30, tmpdir, "home", 7,
        )
        assert result1 is not None

        # Second crop: larger (80x120) → should replace
        result2 = FileManager.save_reference_crop(
            sample_image, 100, 200, 80, 120, tmpdir, "home", 7,
        )
        assert result2 is not None

        # Read the meta to confirm it was updated
        meta_path = result2.parent / "home_07.meta"
        assert meta_path.exists()
        assert int(meta_path.read_text().strip()) == 80 * 120


def test_save_reference_crop_keeps_larger(sample_image):
    """Test that a smaller crop doesn't replace a larger one."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # First crop: large (80x120)
        FileManager.save_reference_crop(
            sample_image, 100, 200, 80, 120, tmpdir, "home", 7,
        )

        # Second crop: smaller (20x30) → should NOT replace
        result = FileManager.save_reference_crop(
            sample_image, 100, 200, 20, 30, tmpdir, "home", 7,
        )
        assert result is not None

        # Meta should still have the original larger area
        meta_path = result.parent / "home_07.meta"
        assert int(meta_path.read_text().strip()) == 80 * 120


def test_load_reference_crop(sample_image):
    """Test loading an existing reference crop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save first
        FileManager.save_reference_crop(
            sample_image, 100, 200, 50, 80, tmpdir, "away", 13,
        )

        # Load
        path = FileManager.load_reference_crop(tmpdir, "away", 13)
        assert path is not None
        assert path.exists()
        assert path.name == "away_13.jpg"


def test_load_reference_crop_not_found():
    """Test loading a non-existent reference crop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = FileManager.load_reference_crop(tmpdir, "home", 99)
        assert path is None


def test_save_reference_crop_empty():
    """Test saving a crop with zero area."""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Out-of-bounds crop
        result = FileManager.save_reference_crop(
            img, 200, 200, 0, 0, tmpdir, "home", 7,
        )
        assert result is None
