import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class Category(Enum):
    HOME_PLAYER = 0
    OPPONENT = 1
    HOME_GK = 2
    OPPONENT_GK = 3
    REFEREE = 4
    BALL = 5


CATEGORY_NAMES = {
    Category.HOME_PLAYER: "home_player",
    Category.OPPONENT: "opponent",
    Category.HOME_GK: "home_gk",
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


def load_metadata_keys(config_path: Optional[Path] = None) -> list[str]:
    """Load frame-level metadata dimension keys from metadata_options.json."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "metadata_options.json"
    if not config_path.exists():
        return ["shot_type", "camera_motion", "ball_status",
                "game_situation", "pitch_zone", "frame_quality"]
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return [dim["key"] for dim in data.get("frame_level", [])]


# Default keys (loaded once at import for backward compatibility)
METADATA_KEYS = load_metadata_keys()


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
    # Frame-level metadata stored as a dict (dynamic dimensions)
    metadata: dict = field(default_factory=dict)
    # State
    status: FrameStatus = FrameStatus.UNVIEWED
    exported_filename: Optional[str] = None
    boxes: list[BoundingBox] = field(default_factory=list)

    # Backward-compatible property accessors for the 6 default dimensions
    @property
    def shot_type(self) -> Optional[str]:
        return self.metadata.get("shot_type")

    @shot_type.setter
    def shot_type(self, value):
        self.metadata["shot_type"] = value

    @property
    def camera_motion(self) -> Optional[str]:
        return self.metadata.get("camera_motion")

    @camera_motion.setter
    def camera_motion(self, value):
        self.metadata["camera_motion"] = value

    @property
    def ball_status(self) -> Optional[str]:
        return self.metadata.get("ball_status")

    @ball_status.setter
    def ball_status(self, value):
        self.metadata["ball_status"] = value

    @property
    def game_situation(self) -> Optional[str]:
        return self.metadata.get("game_situation")

    @game_situation.setter
    def game_situation(self, value):
        self.metadata["game_situation"] = value

    @property
    def pitch_zone(self) -> Optional[str]:
        return self.metadata.get("pitch_zone")

    @pitch_zone.setter
    def pitch_zone(self, value):
        self.metadata["pitch_zone"] = value

    @property
    def frame_quality(self) -> Optional[str]:
        return self.metadata.get("frame_quality")

    @frame_quality.setter
    def frame_quality(self, value):
        self.metadata["frame_quality"] = value


@dataclass
class Player:
    jersey_number: int
    name: str
