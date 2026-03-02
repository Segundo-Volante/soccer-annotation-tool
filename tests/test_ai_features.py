"""Tests for AI-assisted annotation features."""
import os
import json
import tempfile

import pytest

from backend.database import DatabaseManager
from backend.models import (
    BoundingBox, BoxSource, BoxStatus, Category, FrameStatus, Occlusion,
)


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    manager = DatabaseManager(path)
    yield manager
    manager.close()
    os.unlink(path)


# ── Model enums ──

def test_box_source_enum():
    assert BoxSource.MANUAL.value == "manual"
    assert BoxSource.AI_DETECTED.value == "ai_detected"


def test_box_status_enum():
    assert BoxStatus.PENDING.value == "pending"
    assert BoxStatus.FINALIZED.value == "finalized"


def test_bounding_box_ai_defaults():
    box = BoundingBox(id=None, frame_id=1, x=10, y=20, width=30, height=40,
                      category=Category.HOME_PLAYER)
    assert box.source == BoxSource.MANUAL
    assert box.box_status == BoxStatus.FINALIZED
    assert box.confidence is None
    assert box.detected_class is None


def test_bounding_box_ai_fields():
    box = BoundingBox(id=None, frame_id=1, x=10, y=20, width=30, height=40,
                      category=Category.OPPONENT,
                      source=BoxSource.AI_DETECTED,
                      box_status=BoxStatus.PENDING,
                      confidence=0.92,
                      detected_class="player")
    assert box.source == BoxSource.AI_DETECTED
    assert box.box_status == BoxStatus.PENDING
    assert box.confidence == 0.92
    assert box.detected_class == "player"


# ── Database AI methods ──

def test_create_session_ai_mode(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15",
                            annotation_mode="ai_assisted",
                            model_name="football-yolo11s",
                            model_confidence=0.35)
    assert sid is not None
    mode = db.get_session_mode(sid)
    assert mode == "ai_assisted"


def test_create_session_manual_mode_default(db):
    sid = db.create_session("/tmp/frames", "UCL", "GS3")
    mode = db.get_session_mode(sid)
    assert mode == "manual"


def test_add_box_with_ai_fields(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    bid = db.add_box(fid, 100, 200, 50, 80, Category.OPPONENT,
                     source="ai_detected", box_status="pending",
                     confidence=0.87, detected_class="player")
    boxes = db.get_boxes(fid)
    assert len(boxes) == 1
    box = boxes[0]
    assert box.source == BoxSource.AI_DETECTED
    assert box.box_status == BoxStatus.PENDING
    assert box.confidence == 0.87
    assert box.detected_class == "player"


def test_add_box_manual_defaults(db):
    """Manual boxes have correct defaults for new AI fields."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.add_box(fid, 100, 200, 50, 80, Category.HOME_PLAYER,
               jersey_number=7, player_name="Griezmann")
    boxes = db.get_boxes(fid)
    box = boxes[0]
    assert box.source == BoxSource.MANUAL
    assert box.box_status == BoxStatus.FINALIZED
    assert box.confidence is None
    assert box.detected_class is None


def test_get_pending_box_count(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    # Add 3 pending and 2 finalized boxes
    db.add_box(fid, 10, 20, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending")
    db.add_box(fid, 50, 60, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending")
    db.add_box(fid, 90, 100, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending")
    db.add_box(fid, 200, 300, 20, 20, Category.BALL,
               source="ai_detected", box_status="finalized")
    db.add_box(fid, 400, 500, 50, 80, Category.HOME_PLAYER)  # manual

    assert db.get_pending_box_count(fid) == 3


def test_delete_ai_pending_boxes(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    # Add mix of boxes
    db.add_box(fid, 10, 20, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending")
    db.add_box(fid, 50, 60, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending")
    db.add_box(fid, 200, 300, 20, 20, Category.BALL,
               source="ai_detected", box_status="finalized")  # finalized AI
    db.add_box(fid, 400, 500, 50, 80, Category.HOME_PLAYER)  # manual

    db.delete_ai_pending_boxes(fid)
    boxes = db.get_boxes(fid)
    # Only the finalized AI box and manual box should remain
    assert len(boxes) == 2
    assert all(b.box_status == BoxStatus.FINALIZED for b in boxes)


def test_bulk_assign_pending(db):
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.add_box(fid, 10, 20, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending",
               detected_class="player")
    db.add_box(fid, 50, 60, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending",
               detected_class="player")
    db.add_box(fid, 90, 100, 30, 40, Category.HOME_PLAYER)  # manual, not pending

    count = db.bulk_assign_pending(fid, Category.OPPONENT)
    assert count == 2

    boxes = db.get_boxes(fid)
    pending = [b for b in boxes if b.box_status == BoxStatus.PENDING]
    assert len(pending) == 0

    assigned = [b for b in boxes if b.source == BoxSource.AI_DETECTED]
    for b in assigned:
        assert b.category == Category.OPPONENT
        assert b.box_status == BoxStatus.FINALIZED


def test_bulk_assign_pending_exclude_detected_class(db):
    """Ctrl+2 with football model should skip goalkeeper-detected boxes."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0)
    db.add_box(fid, 10, 20, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending",
               detected_class="player")
    db.add_box(fid, 50, 60, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending",
               detected_class="goalkeeper")
    db.add_box(fid, 90, 100, 30, 40, Category.OPPONENT,
               source="ai_detected", box_status="pending",
               detected_class="player")

    count = db.bulk_assign_pending(fid, Category.OPPONENT,
                                   exclude_detected_class="goalkeeper")
    assert count == 2

    boxes = db.get_boxes(fid)
    pending = [b for b in boxes if b.box_status == BoxStatus.PENDING]
    assert len(pending) == 1
    assert pending[0].detected_class == "goalkeeper"


# ── Model manager ──

def test_model_manager_ai_available_flag():
    """AI_AVAILABLE should be importable (True if ultralytics installed, False otherwise)."""
    from backend.model_manager import AI_AVAILABLE
    assert isinstance(AI_AVAILABLE, bool)


def test_model_manager_registry():
    from backend.model_manager import MODEL_REGISTRY
    assert "football-yolo11s" in MODEL_REGISTRY
    assert "yolov8n" in MODEL_REGISTRY
    assert MODEL_REGISTRY["football-yolo11s"]["type"] == "football"
    assert MODEL_REGISTRY["yolov8n"]["type"] == "coco"


def test_model_manager_class_mappings():
    from backend.model_manager import FOOTBALL_CLASS_MAPPING, COCO_CLASS_MAPPING
    # Football: referee and ball auto-assign, player and goalkeeper are PENDING
    assert FOOTBALL_CLASS_MAPPING["referee"] == 4
    assert FOOTBALL_CLASS_MAPPING["ball"] == 5
    assert FOOTBALL_CLASS_MAPPING["player"] is None
    assert FOOTBALL_CLASS_MAPPING["goalkeeper"] is None
    # COCO: sports ball auto-assigns, person is PENDING
    assert COCO_CLASS_MAPPING["sports ball"] == 5
    assert COCO_CLASS_MAPPING["person"] is None


def test_model_manager_confidence_clamping():
    from backend.model_manager import AI_AVAILABLE
    if not AI_AVAILABLE:
        pytest.skip("ultralytics not installed")
    from backend.model_manager import ModelManager
    mm = ModelManager(confidence=0.05)
    assert mm.confidence == 0.10  # clamped to min
    mm.confidence = 0.95
    assert mm.confidence == 0.90  # clamped to max


# ── Exporter with AI fields ──

def test_exporter_source_field_in_coco(db):
    """COCO export includes source field for each annotation."""
    sid = db.create_session("/tmp/frames", "LaLiga", "R15")
    fid = db.add_frame(sid, "frame_001.png", 0, 1920, 1080)
    db.save_frame_metadata(fid,
                           shot_type="wide", camera_motion="static",
                           ball_status="visible", game_situation="open_play",
                           pitch_zone="middle_third", frame_quality="clean")
    db.add_box(fid, 100, 200, 50, 80, Category.HOME_PLAYER,
               jersey_number=7, player_name="Test")
    db.add_box(fid, 300, 400, 40, 60, Category.OPPONENT,
               source="ai_detected", box_status="finalized",
               confidence=0.85, detected_class="player")

    frame = db.get_frame(fid)
    from backend.exporter import Exporter
    # Build COCO JSON directly (without file I/O)
    exporter = Exporter.__new__(Exporter)
    exporter._meta_config = [{"key": k, "in_filename": False} for k in
                             ["shot_type", "camera_motion", "ball_status",
                              "game_situation", "pitch_zone", "frame_quality"]]
    coco = exporter._build_coco_json(frame, "test.png")

    # Check source field
    assert coco["annotations"][0]["source"] == "manual"
    assert coco["annotations"][1]["source"] == "ai_detected"
    assert coco["annotations"][1]["confidence"] == 0.85
    assert "confidence" not in coco["annotations"][0]  # None → not included
