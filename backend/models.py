from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Category(Enum):
    ATLETICO_PLAYER = 0
    OPPONENT = 1
    ATLETICO_GK = 2
    OPPONENT_GK = 3
    REFEREE = 4
    BALL = 5


CATEGORY_NAMES = {
    Category.ATLETICO_PLAYER: "atletico_player",
    Category.OPPONENT: "opponent",
    Category.ATLETICO_GK: "atletico_gk",
    Category.OPPONENT_GK: "opponent_gk",
    Category.REFEREE: "referee",
    Category.BALL: "ball",
}


class Occlusion(Enum):
    VISIBLE = "visible"
    PARTIAL = "partial"
    HEAVY = "heavy"


class FrameStatus(Enum):
    UNVIEWED = "unviewed"
    IN_PROGRESS = "in_progress"
    ANNOTATED = "annotated"
    SKIPPED = "skipped"


# 6 frame-level metadata dimension keys (order matters for Tab cycling)
METADATA_KEYS = [
    "shot_type", "camera_motion", "ball_status",
    "game_situation", "pitch_zone", "frame_quality",
]


@dataclass
class BoundingBox:
    id: Optional[int]
    frame_id: int
    x: int
    y: int
    width: int
    height: int
    category: Category
    jersey_number: Optional[int] = None
    player_name: Optional[str] = None
    occlusion: Occlusion = Occlusion.VISIBLE
    truncated: bool = False


@dataclass
class FrameAnnotation:
    id: Optional[int]
    original_filename: str
    image_width: int
    image_height: int
    # Session-inherited
    source: str
    match_round: str
    opponent: str
    weather: str
    lighting: str
    # Frame-level metadata (6 dimensions)
    shot_type: Optional[str] = None
    camera_motion: Optional[str] = None
    ball_status: Optional[str] = None
    game_situation: Optional[str] = None
    pitch_zone: Optional[str] = None
    frame_quality: Optional[str] = None
    # State
    status: FrameStatus = FrameStatus.UNVIEWED
    exported_filename: Optional[str] = None
    boxes: list[BoundingBox] = field(default_factory=list)


@dataclass
class Player:
    jersey_number: int
    name: str
