import pytest
from backend.models import (
    BoundingBox, Category, CATEGORY_NAMES, FrameAnnotation,
    FrameStatus, Occlusion, Player, METADATA_KEYS,
)


def test_category_values():
    assert Category.HOME_PLAYER.value == 0
    assert Category.BALL.value == 5


def test_category_names():
    assert CATEGORY_NAMES[Category.HOME_PLAYER] == "home_player"
    assert CATEGORY_NAMES[Category.BALL] == "ball"


def test_bounding_box_defaults():
    box = BoundingBox(id=None, frame_id=1, x=10, y=20, width=30, height=40,
                      category=Category.HOME_PLAYER)
    assert box.jersey_number is None
    assert box.occlusion == Occlusion.VISIBLE
    assert box.truncated is False


def test_frame_annotation_defaults():
    frame = FrameAnnotation(id=None, original_filename="test.png",
                            image_width=1920, image_height=1080,
                            source="LaLiga", match_round="R15",
                            opponent="Real Madrid", weather="clear",
                            lighting="floodlight")
    assert frame.status == FrameStatus.UNVIEWED
    assert frame.boxes == []
    assert frame.shot_type is None
    assert frame.opponent == "Real Madrid"
    assert frame.weather == "clear"
    assert frame.lighting == "floodlight"


def test_player():
    p = Player(jersey_number=7, name="Antoine Griezmann")
    assert p.jersey_number == 7
    assert p.name == "Antoine Griezmann"


def test_metadata_keys():
    assert len(METADATA_KEYS) == 6
    assert "shot_type" in METADATA_KEYS
    assert "camera_motion" in METADATA_KEYS
    assert "ball_status" in METADATA_KEYS
    assert "game_situation" in METADATA_KEYS
    assert "pitch_zone" in METADATA_KEYS
    assert "frame_quality" in METADATA_KEYS


def test_frame_status_enum():
    assert FrameStatus.ANNOTATED.value == "annotated"
    assert FrameStatus.SKIPPED.value == "skipped"
    assert FrameStatus.UNVIEWED.value == "unviewed"
    assert FrameStatus.IN_PROGRESS.value == "in_progress"
