"""Tests for Crop Distribution analysis and Resample Request generation.

TEST_CD_001 - Distribution with full sequence/frame_metadata
TEST_CD_002 - Distribution without frame_metadata (total counts only)
TEST_CD_005 - Resample request generation for players with gaps
TEST_CD_006 - Resample request selection filtering (threshold exclusion)
TEST_CD_007 - Min sequence length filter
TEST_CD_008 - Export without resample (distribution written, no resample file)
"""

import json
import os
import tempfile

import pytest

from backend.annotation_store import AnnotationStore
from backend.exporter import Exporter, _camera_angle_to_shot_type
from backend.models import Category, FrameStatus, Occlusion


# ---------------------------------------------------------------------------
#  Constants used across tests
# ---------------------------------------------------------------------------

DEFAULT_TARGETS = {"wide": 5, "medium": 3, "closeup": 2}

DEFAULT_THRESHOLDS = {
    "wide_min_player_ratio": 0.5,
    "medium_min_player_frames": 1,
    "closeup_min_player_frames": 1,
    "min_sequence_length": 3,
    "estimated_resample_interval": 0.3,
}

SESSION_META = {
    "source": "LaLiga",
    "match_round": "R10",
    "opponent": "Real Madrid",
    "weather": "clear",
    "lighting": "floodlight",
}

# Frame filenames
FRAME_1 = "frame_001.png"
FRAME_2 = "frame_002.png"
FRAME_3 = "frame_003.png"


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_frame_metadata():
    """Build frame_metadata dict mapping filenames to camera/sequence info.

    Layout:
      frame_001 & frame_002 -> seq_wide_001 (WIDE_CENTER)
      frame_003             -> seq_medium_001 (MEDIUM)
    """
    return {
        FRAME_1: {
            "file_name": FRAME_1,
            "camera_angle": "WIDE_CENTER",
            "sequence_id": "seq_wide_001",
            "sequence_type": "wide_center",
            "sequence_purpose": "gameplay",
            "sequence_position": 0,
            "sequence_length": 5,
            "video_time": 10.0,
            "match_id": "match_test_001",
            "is_resample": False,
            "resample_of": None,
        },
        FRAME_2: {
            "file_name": FRAME_2,
            "camera_angle": "WIDE_CENTER",
            "sequence_id": "seq_wide_001",
            "sequence_type": "wide_center",
            "sequence_purpose": "gameplay",
            "sequence_position": 1,
            "sequence_length": 5,
            "video_time": 11.0,
            "match_id": "match_test_001",
            "is_resample": False,
            "resample_of": None,
        },
        FRAME_3: {
            "file_name": FRAME_3,
            "camera_angle": "MEDIUM",
            "sequence_id": "seq_medium_001",
            "sequence_type": "medium",
            "sequence_purpose": "gameplay",
            "sequence_position": 0,
            "sequence_length": 4,
            "video_time": 30.0,
            "match_id": "match_test_001",
            "is_resample": False,
            "resample_of": None,
        },
    }


def _make_bundle_metadata_raw():
    """Build bundle_metadata_raw with session_info and sequence_summary.

    Two sequences:
      seq_wide_001  - 5 frames, wide_center, 10s-15s
      seq_medium_001 - 4 frames, medium, 30s-34s
    """
    return {
        "session_info": {
            "match_id": "match_test_001",
            "match_url": "https://example.com/match/001",
            "sequence_profiles_used": {
                "wide_center": {"interval_sec": 1.0},
                "medium": {"interval_sec": 0.5},
            },
        },
        "sequence_summary": [
            {
                "sequence_id": "seq_wide_001",
                "sequence_type": "wide_center",
                "frame_count": 5,
                "video_time_start": 10.0,
                "video_time_end": 15.0,
                "camera_angle": "WIDE_CENTER",
            },
            {
                "sequence_id": "seq_medium_001",
                "sequence_type": "medium",
                "frame_count": 4,
                "video_time_start": 30.0,
                "video_time_end": 34.0,
                "camera_angle": "MEDIUM",
            },
        ],
        "frames": [],
    }


def _setup_store_with_players(input_dir):
    """Create an AnnotationStore with 3 frames and 3 home players.

    Players:
      #10 Lionel Messi   - appears in all 3 frames (2 wide + 1 medium = 3 crops)
      #7  Antoine Griezmann - appears in frame_001 only (1 wide crop)
      #19 Julian Alvarez - appears in frame_002 and frame_003 (1 wide + 1 medium = 2 crops)

    Against DEFAULT_TARGETS (wide=5, medium=3, closeup=2):
      Messi:     wide=2 (gap 3), medium=1 (gap 2), closeup=0 (gap 2) => status "gap"
      Griezmann: wide=1 (gap 4), medium=0 (gap 3), closeup=0 (gap 2) => status "gap"
      Alvarez:   wide=1 (gap 4), medium=1 (gap 2), closeup=0 (gap 2) => status "gap"
    """
    store = AnnotationStore(input_dir)

    for fname in [FRAME_1, FRAME_2, FRAME_3]:
        store.ensure_frame(fname, session_meta=SESSION_META)
        store.set_frame_dimensions(fname, 1920, 1080)
        store.save_frame_metadata(
            fname,
            shot_type="wide",
            camera_motion="static",
            ball_status="visible",
            game_situation="open_play",
            pitch_zone="middle_third",
            frame_quality="clean",
        )

    # ---- Frame 1: Messi + Griezmann ----
    store.add_box(FRAME_1, 100, 200, 50, 80, Category.HOME_PLAYER,
                  jersey_number=10, player_name="Lionel Messi")
    store.add_box(FRAME_1, 300, 250, 45, 75, Category.HOME_PLAYER,
                  jersey_number=7, player_name="Antoine Griezmann")
    # Also add an opponent (should be ignored by distribution)
    store.add_box(FRAME_1, 600, 300, 40, 70, Category.OPPONENT)

    # ---- Frame 2: Messi + Alvarez ----
    store.add_box(FRAME_2, 150, 210, 55, 85, Category.HOME_PLAYER,
                  jersey_number=10, player_name="Lionel Messi")
    store.add_box(FRAME_2, 400, 260, 48, 78, Category.HOME_PLAYER,
                  jersey_number=19, player_name="Julian Alvarez")

    # ---- Frame 3: Messi + Alvarez (medium sequence) ----
    store.add_box(FRAME_3, 200, 180, 60, 90, Category.HOME_PLAYER,
                  jersey_number=10, player_name="Lionel Messi")
    store.add_box(FRAME_3, 500, 300, 55, 85, Category.HOME_PLAYER,
                  jersey_number=19, player_name="Julian Alvarez")

    # Mark all frames as ANNOTATED so they are counted
    for fname in [FRAME_1, FRAME_2, FRAME_3]:
        store.set_frame_status(fname, FrameStatus.ANNOTATED)

    return store


# ---------------------------------------------------------------------------
#  Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def crop_dist_env():
    """Set up a full environment with 3 frames, 3 players, frame_metadata,
    and bundle_metadata_raw suitable for crop distribution and resample tests.
    """
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:

        store = _setup_store_with_players(input_dir)
        frame_metadata = _make_frame_metadata()
        bundle_metadata_raw = _make_bundle_metadata_raw()

        exporter = Exporter(
            store,
            input_dir,
            output_dir,
            team_name="Atletico Madrid",
            has_opponent_roster=False,
            session_meta=SESSION_META,
            frame_metadata=frame_metadata,
            bundle_metadata_raw=bundle_metadata_raw,
        )

        yield {
            "store": store,
            "exporter": exporter,
            "input_dir": input_dir,
            "output_dir": output_dir,
            "frame_metadata": frame_metadata,
            "bundle_metadata_raw": bundle_metadata_raw,
        }


# ---------------------------------------------------------------------------
#  Unit test for the _camera_angle_to_shot_type helper
# ---------------------------------------------------------------------------

class TestCameraAngleMapping:
    def test_wide_center(self):
        assert _camera_angle_to_shot_type("WIDE_CENTER") == "wide"

    def test_wide_left(self):
        assert _camera_angle_to_shot_type("WIDE_LEFT") == "wide"

    def test_wide_right(self):
        assert _camera_angle_to_shot_type("WIDE_RIGHT") == "wide"

    def test_medium(self):
        assert _camera_angle_to_shot_type("MEDIUM") == "medium"

    def test_closeup(self):
        assert _camera_angle_to_shot_type("CLOSEUP") == "closeup"

    def test_unknown_returns_other(self):
        assert _camera_angle_to_shot_type("TACTICAL") == "other"

    def test_empty_returns_other(self):
        assert _camera_angle_to_shot_type("") == "other"


# ---------------------------------------------------------------------------
#  TEST_CD_001 - Distribution with full sequence data
# ---------------------------------------------------------------------------

class TestCD001_DistributionWithFullData:
    """Verify that compute_crop_distribution returns correct per-shot_type
    counts, gaps, and status when frame_metadata is provided."""

    def test_returns_all_three_players(self, crop_dist_env):
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        assert len(dist["players"]) == 3

    def test_player_names_present(self, crop_dist_env):
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        names = {p["name"] for p in dist["players"]}
        assert "Lionel Messi" in names
        assert "Antoine Griezmann" in names
        assert "Julian Alvarez" in names

    def test_messi_shot_type_counts(self, crop_dist_env):
        """Messi appears in frame_001 (wide), frame_002 (wide), frame_003 (medium).
        Expected: wide=2, medium=1."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        assert messi["crops_by_shot_type"].get("wide", 0) == 2
        assert messi["crops_by_shot_type"].get("medium", 0) == 1
        assert messi["total_crops"] == 3

    def test_griezmann_shot_type_counts(self, crop_dist_env):
        """Griezmann appears only in frame_001 (wide). Expected: wide=1."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        griezmann = next(p for p in dist["players"] if p["name"] == "Antoine Griezmann")
        assert griezmann["crops_by_shot_type"].get("wide", 0) == 1
        assert griezmann["total_crops"] == 1

    def test_alvarez_shot_type_counts(self, crop_dist_env):
        """Alvarez appears in frame_002 (wide) and frame_003 (medium).
        Expected: wide=1, medium=1."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        alvarez = next(p for p in dist["players"] if p["name"] == "Julian Alvarez")
        assert alvarez["crops_by_shot_type"].get("wide", 0) == 1
        assert alvarez["crops_by_shot_type"].get("medium", 0) == 1
        assert alvarez["total_crops"] == 2

    def test_all_players_have_gap_status(self, crop_dist_env):
        """With targets wide=5/medium=3/closeup=2, none of the players meet
        all targets so every player should have status='gap'."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        for player in dist["players"]:
            assert player["status"] == "gap", (
                f"Expected 'gap' for {player['name']}, got '{player['status']}'"
            )

    def test_gaps_include_all_deficit_shot_types(self, crop_dist_env):
        """Each player's gaps list should cover every shot_type where
        current < target."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        gap_types = {g["shot_type"] for g in messi["gaps"]}
        # Messi: wide=2 < 5, medium=1 < 3, closeup=0 < 2
        assert "wide" in gap_types
        assert "medium" in gap_types
        assert "closeup" in gap_types

    def test_gap_deficit_values(self, crop_dist_env):
        """Verify deficit = target - current for each gap entry."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        gaps_by_type = {g["shot_type"]: g for g in messi["gaps"]}
        assert gaps_by_type["wide"]["deficit"] == 3   # 5 - 2
        assert gaps_by_type["medium"]["deficit"] == 2  # 3 - 1
        assert gaps_by_type["closeup"]["deficit"] == 2  # 2 - 0

    def test_summary_counts(self, crop_dist_env):
        """Summary should report total_players=3, all with gaps, none ok."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        summary = dist["summary"]
        assert summary["total_players"] == 3
        assert summary["players_with_gaps"] == 3
        assert summary["players_ok"] == 0

    def test_summary_largest_gap(self, crop_dist_env):
        """The largest single deficit is Griezmann's wide gap (deficit=4).
        The summary should reflect the player with the largest gap."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        summary = dist["summary"]
        # Griezmann has wide deficit=4; Alvarez also has wide deficit=4.
        # Both are tied; the code picks the last one encountered by max_deficit.
        # Since players are sorted by key (07_Griezmann < 10_Messi < 19_Alvarez),
        # Alvarez (deficit=4) replaces Griezmann (deficit=4) as it is processed later.
        assert summary["largest_gap_player"] in ("Antoine Griezmann", "Julian Alvarez")
        assert summary["largest_gap_type"] == "wide"

    def test_match_id_from_bundle(self, crop_dist_env):
        """match_id should come from bundle_metadata_raw's session_info."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        assert dist["match_id"] == "match_test_001"

    def test_targets_echoed(self, crop_dist_env):
        """The targets dict should be echoed back in the distribution."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        assert dist["targets"] == DEFAULT_TARGETS

    def test_opponents_excluded(self, crop_dist_env):
        """Opponent boxes should NOT appear in the distribution players list."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        for player in dist["players"]:
            # All players should have jersey numbers from our home set
            assert player["jersey_number"] in (7, 10, 19)

    def test_player_with_enough_crops_shows_ok(self, crop_dist_env):
        """If targets are low enough that a player meets them, status='ok'."""
        env = crop_dist_env
        low_targets = {"wide": 1, "medium": 0, "closeup": 0}
        dist = env["exporter"].compute_crop_distribution(low_targets)
        # Messi has wide=2 >= 1, medium=1 >= 0, closeup=0 >= 0 => ok
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        assert messi["status"] == "ok"
        assert messi["gaps"] == []


# ---------------------------------------------------------------------------
#  TEST_CD_002 - Distribution without frame_metadata
# ---------------------------------------------------------------------------

class TestCD002_DistributionWithoutMetadata:
    """When no frame_metadata is provided, shot_type breakdowns are not
    available. The distribution should show total counts with shot_type
    'unknown' and no gaps (since shot_type cannot be determined)."""

    @pytest.fixture
    def no_metadata_env(self):
        """Environment with the same annotations but no frame_metadata."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = _setup_store_with_players(input_dir)

            exporter = Exporter(
                store,
                input_dir,
                output_dir,
                team_name="Atletico Madrid",
                has_opponent_roster=False,
                session_meta=SESSION_META,
                frame_metadata=None,  # No metadata
                bundle_metadata_raw=None,
            )

            yield {
                "store": store,
                "exporter": exporter,
                "output_dir": output_dir,
            }

    def test_total_counts_correct(self, no_metadata_env):
        """Total crop counts should still be correct even without metadata."""
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        assert messi["total_crops"] == 3

    def test_shot_type_is_unknown(self, no_metadata_env):
        """Without frame_metadata, all crops should be under 'unknown'."""
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        assert "unknown" in messi["crops_by_shot_type"]
        assert messi["crops_by_shot_type"]["unknown"] == 3

    def test_no_shot_type_breakdown(self, no_metadata_env):
        """Without metadata, 'wide'/'medium'/'closeup' keys should not exist."""
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        messi = next(p for p in dist["players"] if p["name"] == "Lionel Messi")
        assert "wide" not in messi["crops_by_shot_type"]
        assert "medium" not in messi["crops_by_shot_type"]
        assert "closeup" not in messi["crops_by_shot_type"]

    def test_no_gaps_without_metadata(self, no_metadata_env):
        """Gaps require shot_type breakdown; without metadata, gaps list
        should be empty and status should be 'ok'."""
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        for player in dist["players"]:
            assert player["gaps"] == [], (
                f"Expected no gaps for {player['name']} without metadata"
            )
            assert player["status"] == "ok"

    def test_all_players_present(self, no_metadata_env):
        """All 3 home players should still be in the distribution."""
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        assert len(dist["players"]) == 3

    def test_summary_no_gaps(self, no_metadata_env):
        env = no_metadata_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        assert dist["summary"]["players_with_gaps"] == 0
        assert dist["summary"]["players_ok"] == 3


# ---------------------------------------------------------------------------
#  TEST_CD_005 - Resample request generation
# ---------------------------------------------------------------------------

class TestCD005_ResampleRequestGeneration:
    """Verify that generate_resample_request produces a valid JSON for
    players with gaps, listing sequences that can be resampled."""

    def test_resample_request_generated(self, crop_dist_env):
        """A resample request file should be created when players have gaps."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        assert result_path is not None
        assert os.path.exists(result_path)

    def test_resample_request_json_structure(self, crop_dist_env):
        """The generated JSON should have required top-level keys."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        assert "generated_at" in request
        assert "source_bundle" in request
        assert "match_info" in request
        assert "resample_targets" in request
        assert "summary" in request
        assert "generation_settings" in request

    def test_resample_targets_contain_gap_players(self, crop_dist_env):
        """All players with gaps that have qualifying sequences should appear
        in resample_targets."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        target_names = {
            t["target_player"]["name"] for t in request["resample_targets"]
        }
        # Messi appears in seq_wide_001 (2 of 5 frames => ratio 0.4 < 0.5 threshold)
        # so the wide sequence may not qualify for Messi depending on ratio.
        # Messi is in medium seq_medium_001 (1 frame, vis >= 1 threshold met).
        # All players have gaps, but only those meeting sequence thresholds appear.
        assert len(target_names) >= 1

    def test_resample_sequence_has_required_fields(self, crop_dist_env):
        """Each sequence entry should contain the expected fields."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        assert len(request["resample_targets"]) > 0
        seq = request["resample_targets"][0]["sequences"][0]
        required_fields = [
            "sequence_id", "sequence_type", "video_time_start",
            "video_time_end", "camera_angle", "original_frame_count",
            "players_visible", "player_frame_count", "player_frame_ratio",
            "expected_new_frames",
        ]
        for field in required_fields:
            assert field in seq, f"Missing field '{field}' in sequence entry"

    def test_resample_match_info(self, crop_dist_env):
        """match_info should reflect session metadata."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        mi = request["match_info"]
        assert mi["match_id"] == "match_test_001"
        assert mi["home_team"] == "Atletico Madrid"

    def test_resample_summary_stats(self, crop_dist_env):
        """Summary should have player count and sequence counts."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        summary = request["summary"]
        assert summary["total_players_with_gaps"] > 0
        assert summary["total_sequences_to_resample"] > 0
        assert "total_expected_new_frames" in summary
        assert "estimated_resample_time_minutes" in summary

    def test_resample_filename_includes_match_id(self, crop_dist_env):
        """Output filename should contain the match_id."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        filename = os.path.basename(result_path)
        assert "match_test_001" in filename
        assert filename.startswith("resample_request_")
        assert filename.endswith(".json")

    def test_target_player_includes_gap_shot_types(self, crop_dist_env):
        """Each target_player entry should list gap_shot_types."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)
        for target in request["resample_targets"]:
            tp = target["target_player"]
            assert "gap_shot_types" in tp
            assert len(tp["gap_shot_types"]) > 0
            assert "current_crops" in tp
            assert "target_crops" in tp


# ---------------------------------------------------------------------------
#  TEST_CD_006 - Resample request selection filtering
# ---------------------------------------------------------------------------

class TestCD006_ResampleSelectionFiltering:
    """Verify that sequences not meeting thresholds are excluded from the
    resample request."""

    def test_wide_ratio_threshold_excludes_low_visibility(self, crop_dist_env):
        """Messi appears in 2 of 5 frames in seq_wide_001 (ratio 0.4).
        With wide_min_player_ratio=0.5, this sequence should NOT qualify
        for Messi's wide gap."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
        )
        with open(result_path) as f:
            request = json.load(f)

        # Find Messi's target entry
        messi_target = None
        for t in request["resample_targets"]:
            if t["target_player"]["name"] == "Lionel Messi":
                messi_target = t
                break

        if messi_target is not None:
            # If Messi is included, check that seq_wide_001 is not listed
            # for wide (his ratio in wide seq is 2/5 = 0.4 < 0.5)
            wide_seqs = [
                s for s in messi_target["sequences"]
                if s["sequence_id"] == "seq_wide_001"
                and "wide" in s["sequence_type"]
            ]
            assert len(wide_seqs) == 0, (
                "seq_wide_001 should be excluded for Messi (ratio 0.4 < 0.5)"
            )

    def test_strict_thresholds_reduce_targets(self, crop_dist_env):
        """With very strict thresholds, fewer sequences should qualify."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)

        strict_thresholds = {
            "wide_min_player_ratio": 0.9,    # Very high
            "medium_min_player_frames": 10,   # Very high
            "closeup_min_player_frames": 10,  # Very high
            "min_sequence_length": 3,
            "estimated_resample_interval": 0.3,
        }
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, strict_thresholds,
        )
        # With thresholds this strict, no sequence should qualify
        assert result_path is None

    def test_relaxed_thresholds_include_more(self, crop_dist_env):
        """With very relaxed thresholds, more sequences should qualify."""
        env = crop_dist_env
        dist = env["exporter"].compute_crop_distribution(DEFAULT_TARGETS)

        relaxed_thresholds = {
            "wide_min_player_ratio": 0.1,
            "medium_min_player_frames": 1,
            "closeup_min_player_frames": 1,
            "min_sequence_length": 1,
            "estimated_resample_interval": 0.3,
        }
        result_path = env["exporter"].generate_resample_request(
            dist, DEFAULT_TARGETS, relaxed_thresholds,
        )
        assert result_path is not None
        with open(result_path) as f:
            request = json.load(f)
        # With relaxed thresholds, we expect more targets and sequences
        total_seqs = sum(
            len(t["sequences"]) for t in request["resample_targets"]
        )
        assert total_seqs >= 1

    def test_no_resample_without_frame_metadata(self):
        """generate_resample_request should return None when there is no
        frame_metadata, since sequence mapping is impossible."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = _setup_store_with_players(input_dir)
            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Atletico Madrid",
                session_meta=SESSION_META,
                frame_metadata=None,
                bundle_metadata_raw=None,
            )
            dist = exporter.compute_crop_distribution(DEFAULT_TARGETS)
            result = exporter.generate_resample_request(
                dist, DEFAULT_TARGETS, DEFAULT_THRESHOLDS,
            )
            assert result is None


# ---------------------------------------------------------------------------
#  TEST_CD_007 - Min sequence length filter
# ---------------------------------------------------------------------------

class TestCD007_MinSequenceLengthFilter:
    """Verify that sequences shorter than min_sequence_length are excluded
    from the resample request."""

    def test_short_sequences_excluded(self):
        """Create a scenario where the only sequence has frame_count < min_sequence_length.
        The resample request should be None since no sequences qualify."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = AnnotationStore(input_dir)

            # One frame in a short sequence
            fname = "frame_short.png"
            store.ensure_frame(fname, session_meta=SESSION_META)
            store.set_frame_dimensions(fname, 1920, 1080)
            store.save_frame_metadata(
                fname,
                shot_type="wide", camera_motion="static",
                ball_status="visible", game_situation="open_play",
                pitch_zone="middle_third", frame_quality="clean",
            )
            store.add_box(fname, 100, 200, 50, 80, Category.HOME_PLAYER,
                          jersey_number=10, player_name="Lionel Messi")
            store.set_frame_status(fname, FrameStatus.ANNOTATED)

            frame_metadata = {
                fname: {
                    "file_name": fname,
                    "camera_angle": "WIDE_CENTER",
                    "sequence_id": "seq_short",
                    "sequence_type": "wide_center",
                    "sequence_purpose": "gameplay",
                    "sequence_position": 0,
                    "sequence_length": 2,
                    "video_time": 5.0,
                    "match_id": "match_short",
                },
            }

            # Sequence with only 2 frames (below default min_sequence_length=3)
            bundle_metadata_raw = {
                "session_info": {
                    "match_id": "match_short",
                    "match_url": "",
                    "sequence_profiles_used": {},
                },
                "sequence_summary": [
                    {
                        "sequence_id": "seq_short",
                        "sequence_type": "wide_center",
                        "frame_count": 2,  # Below threshold of 3
                        "video_time_start": 5.0,
                        "video_time_end": 6.0,
                        "camera_angle": "WIDE_CENTER",
                    },
                ],
                "frames": [],
            }

            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Atletico Madrid",
                session_meta=SESSION_META,
                frame_metadata=frame_metadata,
                bundle_metadata_raw=bundle_metadata_raw,
            )

            targets = {"wide": 5, "medium": 3, "closeup": 2}
            dist = exporter.compute_crop_distribution(targets)
            # Messi has wide=1 < 5, so has gaps
            assert dist["players"][0]["status"] == "gap"

            thresholds = {
                "wide_min_player_ratio": 0.1,
                "medium_min_player_frames": 1,
                "closeup_min_player_frames": 1,
                "min_sequence_length": 3,   # seq_short has only 2 frames
                "estimated_resample_interval": 0.3,
            }
            result_path = exporter.generate_resample_request(
                dist, targets, thresholds,
            )
            assert result_path is None, (
                "Short sequence (2 frames) should be excluded by "
                "min_sequence_length=3"
            )

    def test_long_sequences_included(self):
        """Sequences meeting min_sequence_length should be included."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = AnnotationStore(input_dir)

            fname = "frame_long.png"
            store.ensure_frame(fname, session_meta=SESSION_META)
            store.set_frame_dimensions(fname, 1920, 1080)
            store.save_frame_metadata(
                fname,
                shot_type="wide", camera_motion="static",
                ball_status="visible", game_situation="open_play",
                pitch_zone="middle_third", frame_quality="clean",
            )
            store.add_box(fname, 100, 200, 50, 80, Category.HOME_PLAYER,
                          jersey_number=10, player_name="Lionel Messi")
            store.set_frame_status(fname, FrameStatus.ANNOTATED)

            frame_metadata = {
                fname: {
                    "file_name": fname,
                    "camera_angle": "WIDE_CENTER",
                    "sequence_id": "seq_long",
                    "sequence_type": "wide_center",
                    "sequence_purpose": "gameplay",
                    "sequence_position": 0,
                    "sequence_length": 10,
                    "video_time": 5.0,
                    "match_id": "match_long",
                },
            }

            bundle_metadata_raw = {
                "session_info": {
                    "match_id": "match_long",
                    "match_url": "",
                    "sequence_profiles_used": {
                        "wide_center": {"interval_sec": 1.0},
                    },
                },
                "sequence_summary": [
                    {
                        "sequence_id": "seq_long",
                        "sequence_type": "wide_center",
                        "frame_count": 10,  # Above threshold
                        "video_time_start": 5.0,
                        "video_time_end": 15.0,
                        "camera_angle": "WIDE_CENTER",
                    },
                ],
                "frames": [],
            }

            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Atletico Madrid",
                session_meta=SESSION_META,
                frame_metadata=frame_metadata,
                bundle_metadata_raw=bundle_metadata_raw,
            )

            targets = {"wide": 5, "medium": 3, "closeup": 2}
            dist = exporter.compute_crop_distribution(targets)

            thresholds = {
                "wide_min_player_ratio": 0.05,  # Messi: 1/10 = 0.1 >= 0.05
                "medium_min_player_frames": 1,
                "closeup_min_player_frames": 1,
                "min_sequence_length": 3,  # seq_long has 10 frames
                "estimated_resample_interval": 0.3,
            }
            result_path = exporter.generate_resample_request(
                dist, targets, thresholds,
            )
            assert result_path is not None, (
                "Sequence with 10 frames should pass min_sequence_length=3"
            )
            with open(result_path) as f:
                request = json.load(f)
            assert len(request["resample_targets"]) >= 1


# ---------------------------------------------------------------------------
#  TEST_CD_008 - Export without resample
# ---------------------------------------------------------------------------

class TestCD008_ExportWithoutResample:
    """Verify that generate_crop_distribution writes crop_distribution.json
    and that when no resample is needed, no resample_request file is produced."""

    def test_distribution_json_written(self, crop_dist_env):
        """generate_crop_distribution should write crop_distribution.json."""
        env = crop_dist_env
        dist = env["exporter"].generate_crop_distribution(DEFAULT_TARGETS)
        dist_path = os.path.join(env["output_dir"], "crop_distribution.json")
        assert os.path.exists(dist_path)

    def test_distribution_json_content_matches(self, crop_dist_env):
        """The written JSON should match what generate_crop_distribution returns."""
        env = crop_dist_env
        dist = env["exporter"].generate_crop_distribution(DEFAULT_TARGETS)
        dist_path = os.path.join(env["output_dir"], "crop_distribution.json")
        with open(dist_path) as f:
            written = json.load(f)
        # Compare key structural elements (generated_at may differ slightly)
        assert written["match_id"] == dist["match_id"]
        assert written["targets"] == dist["targets"]
        assert len(written["players"]) == len(dist["players"])
        assert written["summary"] == dist["summary"]

    def test_no_resample_when_targets_met(self):
        """When all players meet targets, generate_resample_request should
        return None and no resample file should be created."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = _setup_store_with_players(input_dir)
            frame_metadata = _make_frame_metadata()
            bundle_metadata_raw = _make_bundle_metadata_raw()

            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Atletico Madrid",
                session_meta=SESSION_META,
                frame_metadata=frame_metadata,
                bundle_metadata_raw=bundle_metadata_raw,
            )

            # Set targets so low that everyone meets them
            easy_targets = {"wide": 1, "medium": 0, "closeup": 0}
            dist = exporter.generate_crop_distribution(easy_targets)

            # All players should be "ok"
            for player in dist["players"]:
                assert player["status"] == "ok"

            result_path = exporter.generate_resample_request(
                dist, easy_targets, DEFAULT_THRESHOLDS,
            )
            assert result_path is None

            # Verify no resample_request file was created
            resample_files = [
                f for f in os.listdir(output_dir)
                if f.startswith("resample_request_")
            ]
            assert len(resample_files) == 0

    def test_distribution_written_but_no_resample_file(self):
        """When there are no gaps, crop_distribution.json should exist
        but no resample_request file."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = _setup_store_with_players(input_dir)
            frame_metadata = _make_frame_metadata()
            bundle_metadata_raw = _make_bundle_metadata_raw()

            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Atletico Madrid",
                session_meta=SESSION_META,
                frame_metadata=frame_metadata,
                bundle_metadata_raw=bundle_metadata_raw,
            )

            # Very easy targets
            easy_targets = {"wide": 0, "medium": 0, "closeup": 0}
            dist = exporter.generate_crop_distribution(easy_targets)

            # Distribution file should exist
            dist_path = os.path.join(output_dir, "crop_distribution.json")
            assert os.path.exists(dist_path)

            # No resample needed
            result = exporter.generate_resample_request(
                dist, easy_targets, DEFAULT_THRESHOLDS,
            )
            assert result is None

            # Only crop_distribution.json should exist (plus output subdirs)
            top_level_jsons = [
                f for f in os.listdir(output_dir)
                if f.endswith(".json")
            ]
            assert "crop_distribution.json" in top_level_jsons
            assert not any(
                f.startswith("resample_request_") for f in top_level_jsons
            )

    def test_unannotated_frames_excluded(self):
        """Frames not marked ANNOTATED should not be counted in distribution."""
        with tempfile.TemporaryDirectory() as input_dir, \
             tempfile.TemporaryDirectory() as output_dir:

            store = AnnotationStore(input_dir)
            store.ensure_frame("frame_a.png", session_meta=SESSION_META)
            store.set_frame_dimensions("frame_a.png", 1920, 1080)
            store.save_frame_metadata(
                "frame_a.png",
                shot_type="wide", camera_motion="static",
                ball_status="visible", game_situation="open_play",
                pitch_zone="middle_third", frame_quality="clean",
            )
            store.add_box("frame_a.png", 100, 200, 50, 80, Category.HOME_PLAYER,
                          jersey_number=10, player_name="Lionel Messi")
            # Do NOT mark as ANNOTATED -- should be excluded

            exporter = Exporter(
                store, input_dir, output_dir,
                team_name="Test",
                session_meta=SESSION_META,
            )
            dist = exporter.compute_crop_distribution(DEFAULT_TARGETS)
            assert len(dist["players"]) == 0
