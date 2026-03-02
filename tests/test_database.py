import os
import tempfile

import pytest

from backend.database import DatabaseManager
from backend.models import Category, FrameStatus, Occlusion


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    manager = DatabaseManager(path)
    yield manager
    manager.close()
    os.unlink(path)


def test_create_session(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15",
                            opponent="Real Madrid", weather="clear",
                            lighting="floodlight")
    assert sid is not None
    session = db.get_session(sid)
    assert session["source"] == "LaLiga"
    assert session["match_round"] == "R15"
    assert session["opponent"] == "Real Madrid"
    assert session["weather"] == "clear"
    assert session["lighting"] == "floodlight"


def test_create_session_defaults(db):
    sid = db.create_session("/tmp/frames", "UCL", "GS3")
    session = db.get_session(sid)
    assert session["opponent"] == ""
    assert session["weather"] == "clear"
    assert session["lighting"] == "floodlight"


def test_find_session_by_folder(db):
    db.create_session("/tmp/frames", "LaLiga", "R15")
    found = db.find_session_by_folder("/tmp/frames")
    assert found is not None
    assert db.find_session_by_folder("/tmp/other") is None


def test_add_and_get_frame(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15",
                            opponent="Sevilla", weather="overcast",
                            lighting="daylight_natural")
    fid = db.add_frame(sid, "frame_001.png", 0, 1920, 1080)
    frame = db.get_frame(fid)
    assert frame is not None
    assert frame.original_filename == "frame_001.png"
    assert frame.image_width == 1920
    assert frame.source == "LaLiga"
    assert frame.opponent == "Sevilla"
    assert frame.weather == "overcast"
    assert frame.lighting == "daylight_natural"
    assert frame.status == FrameStatus.UNVIEWED
    # Frame-level defaults
    assert frame.shot_type == "wide"
    assert frame.camera_motion == "static"
    assert frame.ball_status == "visible"
    assert frame.game_situation == "open_play"
    assert frame.pitch_zone == "middle_third"
    assert frame.frame_quality == "clean"


def test_save_frame_metadata(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.save_frame_metadata(fid,
                           shot_type="medium",
                           camera_motion="pan",
                           ball_status="occluded",
                           game_situation="corner",
                           pitch_zone="attacking_third",
                           frame_quality="motion_blur")
    frame = db.get_frame(fid)
    assert frame.shot_type == "medium"
    assert frame.camera_motion == "pan"
    assert frame.ball_status == "occluded"
    assert frame.game_situation == "corner"
    assert frame.pitch_zone == "attacking_third"
    assert frame.frame_quality == "motion_blur"


def test_save_frame_metadata_partial(db):
    """Only update some dimensions, others keep defaults."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.save_frame_metadata(fid, shot_type="tight", ball_status="in_air")
    frame = db.get_frame(fid)
    assert frame.shot_type == "tight"
    assert frame.ball_status == "in_air"
    # Unchanged defaults
    assert frame.camera_motion == "static"
    assert frame.game_situation == "open_play"


def test_save_frame_metadata_extra_keys(db):
    """Extra keys are stored in the metadata JSON blob."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.save_frame_metadata(fid, custom_field="foo", shot_type="wide")
    frame = db.get_frame(fid)
    assert frame.shot_type == "wide"
    assert frame.metadata.get("custom_field") == "foo"


def test_set_frame_status(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.set_frame_status(fid, FrameStatus.ANNOTATED)
    frame = db.get_frame(fid)
    assert frame.status == FrameStatus.ANNOTATED


def test_add_and_get_boxes(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    bid = db.add_box(fid, 100, 200, 50, 80, Category.HOME_PLAYER,
                     jersey_number=19, player_name="Julian Alvarez")
    assert bid is not None
    boxes = db.get_boxes(fid)
    assert len(boxes) == 1
    assert boxes[0].category == Category.HOME_PLAYER
    assert boxes[0].jersey_number == 19


def test_update_box(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    bid = db.add_box(fid, 100, 200, 50, 80, Category.OPPONENT)
    db.update_box(bid, occlusion=Occlusion.PARTIAL, x=150)
    boxes = db.get_boxes(fid)
    assert boxes[0].occlusion == Occlusion.PARTIAL
    assert boxes[0].x == 150


def test_delete_box(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    bid = db.add_box(fid, 100, 200, 50, 80, Category.BALL)
    db.delete_box(bid)
    assert len(db.get_boxes(fid)) == 0


def test_session_stats(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    db.add_frame(sid, "f1.png", 0)
    db.add_frame(sid, "f2.png", 1)
    fid3 = db.add_frame(sid, "f3.png", 2)
    db.set_frame_status(fid3, FrameStatus.ANNOTATED)
    stats = db.get_session_stats(sid)
    assert stats["total"] == 3
    assert stats["annotated"] == 1
    assert stats["unviewed"] == 2


def test_session_frames(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    db.add_frame(sid, "a.png", 0)
    db.add_frame(sid, "b.png", 1)
    frames = db.get_session_frames(sid)
    assert len(frames) == 2
    assert frames[0]["original_filename"] == "a.png"


def test_get_next_seq(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "f1.png", 0)
    assert db.get_next_seq(sid) == 1
    db.set_frame_status(fid, FrameStatus.ANNOTATED)
    assert db.get_next_seq(sid) == 2


def test_metadata_json_blob(db):
    """Metadata is stored as JSON blob and round-trips correctly."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.save_frame_metadata(fid,
                           shot_type="tight",
                           camera_motion="zoom_in",
                           ball_status="in_air",
                           game_situation="penalty",
                           pitch_zone="attacking_third",
                           frame_quality="clean")
    frame = db.get_frame(fid)
    assert frame.metadata["shot_type"] == "tight"
    assert frame.metadata["camera_motion"] == "zoom_in"
    assert frame.metadata["ball_status"] == "in_air"
    assert frame.metadata["game_situation"] == "penalty"
    assert frame.metadata["pitch_zone"] == "attacking_third"
    assert frame.metadata["frame_quality"] == "clean"


def test_metadata_json_merge(db):
    """Saving metadata merges with existing values."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.save_frame_metadata(fid, shot_type="wide", ball_status="visible")
    db.save_frame_metadata(fid, shot_type="tight")
    frame = db.get_frame(fid)
    assert frame.metadata["shot_type"] == "tight"
    assert frame.metadata["ball_status"] == "visible"
