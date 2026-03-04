import json
import os
import tempfile

import cv2
import numpy as np
import pytest

from backend.annotation_store import AnnotationStore
from backend.exporter import Exporter, _ascii_normalize, _extract_lastname
from backend.models import BoxStatus, Category, FrameStatus, Occlusion


def test_ascii_normalize():
    assert _ascii_normalize("Álvarez") == "Alvarez"
    assert _ascii_normalize("Griezmann") == "Griezmann"


def test_extract_lastname():
    assert _extract_lastname("Julián Álvarez") == "Alvarez"
    assert _extract_lastname("Koke") == "Koke"
    assert _extract_lastname("") == "Unknown"


@pytest.fixture
def export_env():
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:
        # Create a sample image
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.imwrite(os.path.join(input_dir, "frame_001.png"), img)

        # Create annotation store
        store = AnnotationStore(input_dir)

        # Session metadata
        session_meta = {
            "source": "LaLiga",
            "match_round": "R15",
            "opponent": "Real Madrid",
            "weather": "clear",
            "lighting": "floodlight",
        }

        # Create frame annotation
        store.ensure_frame("frame_001.png", session_meta=session_meta)
        store.set_frame_dimensions("frame_001.png", 1920, 1080)
        store.save_frame_metadata(
            "frame_001.png",
            shot_type="wide",
            camera_motion="static",
            ball_status="visible",
            game_situation="open_play",
            pitch_zone="middle_third",
            frame_quality="clean",
        )
        store.add_box("frame_001.png", 100, 200, 50, 80, Category.HOME_PLAYER,
                       jersey_number=19, player_name="Julián Álvarez")
        store.add_box("frame_001.png", 500, 300, 40, 70, Category.OPPONENT)
        store.add_box("frame_001.png", 800, 400, 20, 20, Category.BALL)

        exporter = Exporter(store, input_dir, output_dir)
        frame = store.get_frame_annotation("frame_001.png")

        yield {
            "store": store, "exporter": exporter, "frame": frame,
            "input_dir": input_dir, "output_dir": output_dir,
        }


def test_validate_metadata(export_env):
    env = export_env
    # With all metadata set, should be valid
    assert env["exporter"].validate_metadata(env["frame"]) is None


def test_validate_metadata_missing(export_env):
    env = export_env
    frame = env["frame"]
    frame.shot_type = None
    error = env["exporter"].validate_metadata(frame)
    assert error is not None
    assert "shot type" in error.lower()


def test_export_frame(export_env):
    env = export_env
    exported_name = env["exporter"].export_frame(env["frame"], "frame_001.png")

    # All boxes are finalized → goes to complete/ subfolder
    complete_dir = os.path.join(env["output_dir"], "complete")

    # Check renamed frame exists
    assert os.path.exists(os.path.join(complete_dir, "frames", exported_name))
    assert "LaLiga" in exported_name
    assert "R15" in exported_name

    # V2 naming includes weather, lighting, shot, camera, situation
    assert "clear" in exported_name
    assert "floodlight" in exported_name
    assert "wide" in exported_name
    assert "static" in exported_name

    # Check JSON annotation exists
    json_name = exported_name.replace(".png", ".json")
    json_path = os.path.join(complete_dir, "annotations", json_name)
    assert os.path.exists(json_path)
    with open(json_path) as f:
        data = json.load(f)
    assert len(data["annotations"]) == 3
    assert data["annotations"][0]["category_name"] == "home_player"

    # Check frame_metadata in COCO JSON
    assert "frame_metadata" in data
    assert data["frame_metadata"]["source"] == "LaLiga"
    assert data["frame_metadata"]["opponent"] == "Real Madrid"
    assert data["frame_metadata"]["weather"] == "clear"
    assert data["frame_metadata"]["shot_type"] == "wide"

    # Check crops — home players use home_ prefix
    alvarez_crops = os.path.join(complete_dir, "crops", "home_19_Alvarez")
    assert os.path.isdir(alvarez_crops)
    assert len(os.listdir(alvarez_crops)) == 1

    # Opponents without roster go to away/ folder
    opp_crops = os.path.join(complete_dir, "crops", "away")
    assert os.path.isdir(opp_crops)

    ball_crops = os.path.join(complete_dir, "crops", "ball")
    assert os.path.isdir(ball_crops)

    # Check combined dataset
    dataset_path = os.path.join(complete_dir, "coco_dataset.json")
    assert os.path.exists(dataset_path)

    # Check summary
    summary_path = os.path.join(env["output_dir"], "summary.json")
    assert os.path.exists(summary_path)


def test_opponent_crops_with_roster():
    """When opponent roster is loaded, opponent crops use away_{num}_{name}/ folders."""
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:
        # Create a sample image
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.imwrite(os.path.join(input_dir, "frame_002.png"), img)

        store = AnnotationStore(input_dir)

        session_meta = {
            "source": "LaLiga",
            "match_round": "R15",
            "opponent": "Real Madrid",
            "weather": "clear",
            "lighting": "floodlight",
        }

        store.ensure_frame("frame_002.png", session_meta=session_meta)
        store.set_frame_dimensions("frame_002.png", 1920, 1080)
        store.save_frame_metadata(
            "frame_002.png",
            shot_type="wide", camera_motion="static",
            ball_status="visible", game_situation="open_play",
            pitch_zone="middle_third", frame_quality="clean",
        )
        store.add_box("frame_002.png", 300, 200, 60, 90, Category.OPPONENT,
                       jersey_number=7, player_name="Vinicius Jr")

        exporter = Exporter(store, input_dir, output_dir, has_opponent_roster=True)
        frame = store.get_frame_annotation("frame_002.png")
        exporter.export_frame(frame, "frame_002.png")

        # Named opponent folder with away_ prefix (in complete/ since no unsure boxes)
        opp_folder = os.path.join(output_dir, "complete", "crops", "away_07_Jr")
        assert os.path.isdir(opp_folder)
        assert len(os.listdir(opp_folder)) == 1


def test_unsure_export_to_needs_review():
    """Frames with unsure boxes go to needs_review/ with review_manifest.json."""
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.imwrite(os.path.join(input_dir, "frame_003.png"), img)

        store = AnnotationStore(input_dir)
        session_meta = {
            "source": "LaLiga", "match_round": "R15", "opponent": "Rival",
            "weather": "clear", "lighting": "floodlight",
        }
        store.ensure_frame("frame_003.png", session_meta=session_meta)
        store.set_frame_dimensions("frame_003.png", 1920, 1080)
        store.save_frame_metadata(
            "frame_003.png",
            shot_type="wide", camera_motion="static",
            ball_status="visible", game_situation="open_play",
            pitch_zone="middle_third", frame_quality="clean",
        )

        # Add a finalized box and an unsure box
        store.add_box("frame_003.png", 100, 200, 50, 80, Category.HOME_PLAYER,
                       jersey_number=10, player_name="Test Player")
        unsure_id = store.add_box("frame_003.png", 300, 200, 50, 80, Category.OPPONENT)
        store.update_box("frame_003.png", unsure_id,
                         box_status="unsure", unsure_note="blocked by defender")

        exporter = Exporter(store, input_dir, output_dir)
        frame = store.get_frame_annotation("frame_003.png")

        # Verify unsure box loaded correctly
        unsure_boxes = [b for b in frame.boxes if b.box_status == BoxStatus.UNSURE]
        assert len(unsure_boxes) == 1
        assert unsure_boxes[0].unsure_note == "blocked by defender"

        exported = exporter.export_frame(frame, "frame_003.png")

        # Frame should go to needs_review/ (not complete/)
        review_dir = os.path.join(output_dir, "needs_review")
        complete_dir = os.path.join(output_dir, "complete")

        # Frame image in needs_review/
        assert os.path.exists(os.path.join(review_dir, "frames", exported))
        assert not os.path.exists(os.path.join(complete_dir, "frames", exported))

        # Annotation JSON in needs_review/
        json_name = exported.replace(".png", ".json")
        json_path = os.path.join(review_dir, "annotations", json_name)
        assert os.path.exists(json_path)
        with open(json_path) as f:
            data = json.load(f)
        assert len(data["annotations"]) == 2
        # Check box_status and unsure_note in COCO JSON
        unsure_ann = [a for a in data["annotations"] if a.get("box_status") == "unsure"]
        assert len(unsure_ann) == 1
        assert unsure_ann[0]["unsure_note"] == "blocked by defender"

        # Crops in needs_review/
        home_crops = os.path.join(review_dir, "crops", "home_10_Player")
        assert os.path.isdir(home_crops)
        opp_crops = os.path.join(review_dir, "crops", "away")
        assert os.path.isdir(opp_crops)

        # Combined dataset in needs_review/
        assert os.path.exists(os.path.join(review_dir, "coco_dataset.json"))

        # Review manifest
        manifest_path = os.path.join(review_dir, "review_manifest.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert len(manifest["frames_needing_review"]) == 1
        entry = manifest["frames_needing_review"][0]
        assert entry["unsure_boxes_count"] == 1
        assert entry["assigned_boxes_count"] == 1
        assert entry["unsure_boxes"][0]["note"] == "blocked by defender"

        # Summary at top level
        assert os.path.exists(os.path.join(output_dir, "summary.json"))


def test_mixed_export_both_folders():
    """Export finalized frame to complete/ and unsure frame to needs_review/."""
    with tempfile.TemporaryDirectory() as input_dir, \
         tempfile.TemporaryDirectory() as output_dir:
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.imwrite(os.path.join(input_dir, "frame_a.png"), img)
        cv2.imwrite(os.path.join(input_dir, "frame_b.png"), img)

        store = AnnotationStore(input_dir)
        session_meta = {
            "source": "Test", "match_round": "R01", "opponent": "Rival",
            "weather": "clear", "lighting": "daylight",
        }

        # Frame A: all finalized
        store.ensure_frame("frame_a.png", session_meta=session_meta)
        store.set_frame_dimensions("frame_a.png", 1920, 1080)
        store.save_frame_metadata("frame_a.png",
            shot_type="wide", camera_motion="static",
            ball_status="visible", game_situation="open_play",
            pitch_zone="middle_third", frame_quality="clean",
        )
        store.add_box("frame_a.png", 100, 200, 50, 80, Category.HOME_PLAYER,
                       jersey_number=7, player_name="Player A")

        # Frame B: has unsure box
        store.ensure_frame("frame_b.png", session_meta=session_meta)
        store.set_frame_dimensions("frame_b.png", 1920, 1080)
        store.save_frame_metadata("frame_b.png",
            shot_type="wide", camera_motion="static",
            ball_status="visible", game_situation="open_play",
            pitch_zone="middle_third", frame_quality="clean",
        )
        bid = store.add_box("frame_b.png", 200, 200, 60, 80, Category.OPPONENT)
        store.update_box("frame_b.png", bid, box_status="unsure", unsure_note="not sure")

        exporter = Exporter(store, input_dir, output_dir)

        # Export frame A (finalized) — mark annotated after, like real workflow
        frame_a = store.get_frame_annotation("frame_a.png")
        exported_a = exporter.export_frame(frame_a, "frame_a.png")
        store.set_frame_status("frame_a.png", FrameStatus.ANNOTATED)

        # Export frame B (unsure)
        frame_b = store.get_frame_annotation("frame_b.png")
        exported_b = exporter.export_frame(frame_b, "frame_b.png")
        store.set_frame_status("frame_b.png", FrameStatus.ANNOTATED)

        # Different sequence numbers → different filenames
        assert exported_a != exported_b

        # Frame A → complete/
        assert os.path.exists(os.path.join(output_dir, "complete", "frames", exported_a))

        # Frame B → needs_review/
        assert os.path.exists(os.path.join(output_dir, "needs_review", "frames", exported_b))

        # Both have their own coco_dataset.json
        assert os.path.exists(os.path.join(output_dir, "complete", "coco_dataset.json"))
        assert os.path.exists(os.path.join(output_dir, "needs_review", "coco_dataset.json"))
