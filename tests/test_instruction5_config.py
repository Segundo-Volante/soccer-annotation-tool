import json
import os
import tempfile
from pathlib import Path

import pytest

from backend.project_config import ProjectConfig
from backend.annotation_store import AnnotationStore
from backend.exporter import Exporter


# ── ReID targets ──────────────────────────────────────────────────────────


def test_reid_targets_default():
    """ProjectConfig with no reid_targets in JSON returns defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = {"team_name": "Test FC", "season": "2024-25"}
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        config = ProjectConfig(tmpdir)
        targets = config.get_reid_targets()

        assert targets == {"wide": 150, "medium": 60, "closeup": 20}


def test_reid_targets_custom():
    """ProjectConfig with reid_targets in JSON returns custom values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_targets = {"wide": 200, "medium": 80, "closeup": 30}
        project = {
            "team_name": "Test FC",
            "season": "2024-25",
            "reid_targets": custom_targets,
        }
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        config = ProjectConfig(tmpdir)
        targets = config.get_reid_targets()

        assert targets == custom_targets


# ── Resample thresholds ──────────────────────────────────────────────────


def test_resample_thresholds_default():
    """Returns defaults when resample_thresholds is not in JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = {"team_name": "Test FC", "season": "2024-25"}
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        config = ProjectConfig(tmpdir)
        thresholds = config.get_resample_thresholds()

        assert thresholds == {
            "wide_min_player_ratio": 0.5,
            "medium_min_player_frames": 1,
            "closeup_min_player_frames": 1,
            "min_sequence_length": 3,
            "estimated_resample_interval": 0.3,
        }


def test_resample_thresholds_custom():
    """Returns custom values when resample_thresholds is in JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_thresholds = {
            "wide_min_player_ratio": 0.7,
            "medium_min_player_frames": 3,
            "closeup_min_player_frames": 2,
            "min_sequence_length": 5,
            "estimated_resample_interval": 0.5,
        }
        project = {
            "team_name": "Test FC",
            "season": "2024-25",
            "resample_thresholds": custom_thresholds,
        }
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        config = ProjectConfig(tmpdir)
        thresholds = config.get_resample_thresholds()

        assert thresholds == custom_thresholds


# ── save_reid_settings ───────────────────────────────────────────────────


def test_save_reid_settings():
    """Saving reid_targets and thresholds persists to project.json correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = {"team_name": "Test FC", "season": "2024-25"}
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        config = ProjectConfig(tmpdir)

        new_targets = {"wide": 300, "medium": 100, "closeup": 50}
        new_thresholds = {
            "wide_min_player_ratio": 0.9,
            "medium_min_player_frames": 5,
            "closeup_min_player_frames": 4,
            "min_sequence_length": 10,
            "estimated_resample_interval": 1.0,
        }
        config.save_reid_settings(new_targets, new_thresholds)

        # Re-read from disk to confirm persistence
        with open(os.path.join(tmpdir, "project.json"), "r") as f:
            saved = json.load(f)

        assert saved["reid_targets"] == new_targets
        assert saved["resample_thresholds"] == new_thresholds
        # Original fields should still be present
        assert saved["team_name"] == "Test FC"
        assert saved["season"] == "2024-25"


def test_save_reid_settings_no_existing_data():
    """When ProjectConfig has no existing project.json, save creates a new file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # No project.json written -- config.exists should be False
        config = ProjectConfig(tmpdir)
        assert not config.exists

        new_targets = {"wide": 250, "medium": 90, "closeup": 40}
        new_thresholds = {
            "wide_min_player_ratio": 0.6,
            "medium_min_player_frames": 2,
            "closeup_min_player_frames": 1,
            "min_sequence_length": 4,
            "estimated_resample_interval": 0.4,
        }
        config.save_reid_settings(new_targets, new_thresholds)

        # File should now exist on disk
        project_path = os.path.join(tmpdir, "project.json")
        assert os.path.exists(project_path)

        with open(project_path, "r") as f:
            saved = json.load(f)

        assert saved["reid_targets"] == new_targets
        assert saved["resample_thresholds"] == new_thresholds


# ── Crops metadata deduplication ─────────────────────────────────────────


def test_crops_metadata_deduplication():
    """Re-exporting the same frame should NOT create duplicate crop entries."""
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:

        store = AnnotationStore(input_dir)
        exporter = Exporter(
            store=store,
            input_folder=input_dir,
            output_folder=output_dir,
            team_name="Home Team",
            has_opponent_roster=False,
            session_meta=None,
            frame_metadata=None,
            bundle_metadata_raw=None,
        )

        # Use the "complete" target dir created by the Exporter constructor
        target_dir = Path(output_dir) / "complete"

        crop_entries = [
            {
                "crop_file": "player_001.png",
                "player_name": "Alice",
                "jersey_number": 10,
                "category": "home_player",
            },
            {
                "crop_file": "player_002.png",
                "player_name": "Bob",
                "jersey_number": 7,
                "category": "home_player",
            },
        ]

        # First export
        exporter._update_crops_metadata(crop_entries, target_dir)

        # Second export with the same crop_file values (simulates re-export)
        updated_entries = [
            {
                "crop_file": "player_001.png",
                "player_name": "Alice Updated",
                "jersey_number": 10,
                "category": "home_player",
            },
            {
                "crop_file": "player_002.png",
                "player_name": "Bob Updated",
                "jersey_number": 7,
                "category": "home_player",
            },
        ]
        exporter._update_crops_metadata(updated_entries, target_dir)

        # Read the resulting metadata
        meta_path = target_dir / "crops" / "crops_metadata.json"
        assert meta_path.exists()

        data = json.loads(meta_path.read_text(encoding="utf-8"))
        crops = data["crops"]

        # Should have exactly 2 entries, not 4 (no duplicates)
        assert len(crops) == 2

        # The entries should reflect the latest (updated) values
        crop_files = [c["crop_file"] for c in crops]
        assert crop_files.count("player_001.png") == 1
        assert crop_files.count("player_002.png") == 1

        # Verify the updated names are present (latest write wins)
        names = {c["crop_file"]: c["player_name"] for c in crops}
        assert names["player_001.png"] == "Alice Updated"
        assert names["player_002.png"] == "Bob Updated"

        # total_crops in export_info should also reflect the deduplicated count
        assert data["export_info"]["total_crops"] == 2
