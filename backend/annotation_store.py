"""Per-frame JSON annotation storage — single source of truth for annotation data.

Each frame's annotations are stored as an individual JSON file in the
``annotations/`` subdirectory next to the image folder.  This design enables
team collaboration (different annotators write different files) and makes
diffing and version-control trivial.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from backend.models import (
    BoundingBox, BoxSource, BoxStatus, Category, FrameAnnotation,
    FrameStatus, Occlusion,
)

SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
#  Serialization helpers
# ---------------------------------------------------------------------------

def _box_to_dict(box: BoundingBox) -> dict:
    d = {
        "id": box.id if box.id else str(uuid.uuid4())[:8],
        "x": box.x,
        "y": box.y,
        "width": box.width,
        "height": box.height,
        "category": box.category.value,
        "jersey_number": box.jersey_number,
        "player_name": box.player_name,
        "occlusion": box.occlusion.value,
        "truncated": box.truncated,
        "source": box.source.value,
        "box_status": box.box_status.value,
        "confidence": box.confidence,
        "detected_class": box.detected_class,
        "unsure_note": box.unsure_note,
    }
    return d


def _dict_to_box(d: dict, frame_id: Optional[int] = None) -> BoundingBox:
    return BoundingBox(
        id=d.get("id"),
        frame_id=frame_id or 0,
        x=d["x"],
        y=d["y"],
        width=d["width"],
        height=d["height"],
        category=Category(d["category"]),
        jersey_number=d.get("jersey_number"),
        player_name=d.get("player_name"),
        occlusion=Occlusion(d["occlusion"]) if d.get("occlusion") else Occlusion.VISIBLE,
        truncated=bool(d.get("truncated", False)),
        source=BoxSource(d["source"]) if d.get("source") else BoxSource.MANUAL,
        box_status=BoxStatus(d["box_status"]) if d.get("box_status") else BoxStatus.FINALIZED,
        confidence=d.get("confidence"),
        detected_class=d.get("detected_class"),
        unsure_note=d.get("unsure_note"),
    )


def _frame_to_dict(frame: FrameAnnotation) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "frame_filename": frame.original_filename,
        "image_width": frame.image_width,
        "image_height": frame.image_height,
        "status": frame.status.value,
        "annotator": getattr(frame, "annotator", None),
        "created_at": getattr(frame, "created_at", None),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": dict(frame.metadata),
        "session_metadata": {
            "source": frame.source,
            "match_round": frame.match_round,
            "opponent": frame.opponent,
            "weather": frame.weather,
            "lighting": frame.lighting,
        },
        "boxes": [_box_to_dict(b) for b in frame.boxes],
        "skip_reason": getattr(frame, "skip_reason", None),
    }


def _dict_to_frame(d: dict) -> FrameAnnotation:
    sess = d.get("session_metadata", {})
    frame = FrameAnnotation(
        id=None,
        original_filename=d.get("frame_filename", ""),
        image_width=d.get("image_width", 0),
        image_height=d.get("image_height", 0),
        source=sess.get("source", ""),
        match_round=sess.get("match_round", ""),
        opponent=sess.get("opponent", ""),
        weather=sess.get("weather", "clear"),
        lighting=sess.get("lighting", "floodlight"),
        metadata=d.get("metadata", {}),
        status=FrameStatus(d.get("status", "unviewed")),
        exported_filename=d.get("exported_filename"),
    )
    frame.annotator = d.get("annotator")
    frame.created_at = d.get("created_at")
    frame.skip_reason = d.get("skip_reason")
    frame.boxes = [_dict_to_box(bd) for bd in d.get("boxes", [])]
    return frame


# ---------------------------------------------------------------------------
#  AnnotationStore
# ---------------------------------------------------------------------------

class AnnotationStore:
    """Read / write per-frame JSON files.

    Each frame corresponds to a file  ``annotations/{stem}.json``.
    """

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.annotations_dir = self.project_root / "annotations"
        self.annotations_dir.mkdir(parents=True, exist_ok=True)

    # -- path helpers -------------------------------------------------------

    def _json_path(self, filename: str) -> Path:
        return self.annotations_dir / (Path(filename).stem + ".json")

    def _atomic_write(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(path))

    # -- Frame-level operations ---------------------------------------------

    def get_frame_annotation(self, filename: str) -> Optional[FrameAnnotation]:
        """Load the annotation for *filename*.  Returns ``None`` if no JSON exists."""
        path = self._json_path(filename)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return _dict_to_frame(data)

    def save_frame_annotation(self, filename: str, frame: FrameAnnotation) -> None:
        """Persist the full frame annotation (atomic write)."""
        frame.original_filename = filename
        data = _frame_to_dict(frame)
        self._atomic_write(self._json_path(filename), data)

    def save_frame_metadata(self, filename: str, **kwargs) -> None:
        """Update only metadata keys on an existing frame JSON."""
        path = self._json_path(filename)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "schema_version": SCHEMA_VERSION,
                "frame_filename": filename,
                "image_width": 0, "image_height": 0,
                "status": "unviewed",
                "metadata": {},
                "session_metadata": {},
                "boxes": [],
            }
        meta = data.setdefault("metadata", {})
        meta.update({k: v for k, v in kwargs.items() if v is not None})
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)

    def set_frame_status(self, filename: str, status: FrameStatus,
                         skip_reason: Optional[str] = None) -> None:
        path = self._json_path(filename)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "schema_version": SCHEMA_VERSION,
                "frame_filename": filename,
                "image_width": 0, "image_height": 0,
                "status": "unviewed",
                "metadata": {},
                "session_metadata": {},
                "boxes": [],
            }
        data["status"] = status.value
        if skip_reason is not None:
            data["skip_reason"] = skip_reason
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)

    def set_frame_dimensions(self, filename: str, width: int, height: int) -> None:
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["image_width"] = width
        data["image_height"] = height
        self._atomic_write(path, data)

    def set_exported_filename(self, filename: str, exported: str) -> None:
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["exported_filename"] = exported
        self._atomic_write(path, data)

    # -- Box-level operations -----------------------------------------------

    def add_box(self, filename: str, x: int, y: int, width: int, height: int,
                category: Category, jersey_number: Optional[int] = None,
                player_name: Optional[str] = None,
                occlusion: Occlusion = Occlusion.VISIBLE,
                truncated: bool = False,
                source: str = "manual",
                box_status: str = "finalized",
                confidence: Optional[float] = None,
                detected_class: Optional[str] = None) -> str:
        """Add a box and return its generated string ID."""
        box_id = str(uuid.uuid4())[:8]
        box_dict = {
            "id": box_id,
            "x": x, "y": y, "width": width, "height": height,
            "category": category.value,
            "jersey_number": jersey_number,
            "player_name": player_name,
            "occlusion": occlusion.value if isinstance(occlusion, Occlusion) else occlusion,
            "truncated": truncated,
            "source": source,
            "box_status": box_status,
            "confidence": confidence,
            "detected_class": detected_class,
        }
        path = self._json_path(filename)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {
                "schema_version": SCHEMA_VERSION,
                "frame_filename": filename,
                "image_width": 0, "image_height": 0,
                "status": "in_progress",
                "metadata": {},
                "session_metadata": {},
                "boxes": [],
            }
        data.setdefault("boxes", []).append(box_dict)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)
        return box_id

    def update_box(self, filename: str, box_id: str, **kwargs) -> None:
        """Update fields of a box identified by *box_id*."""
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for box_d in data.get("boxes", []):
            if str(box_d.get("id")) == str(box_id):
                for k, v in kwargs.items():
                    if k == "category" and isinstance(v, Category):
                        v = v.value
                    elif k == "occlusion" and isinstance(v, Occlusion):
                        v = v.value
                    elif k == "box_status" and isinstance(v, BoxStatus):
                        v = v.value
                    elif k == "truncated" and isinstance(v, bool):
                        v = v  # keep bool
                    box_d[k] = v
                break
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)

    def delete_box(self, filename: str, box_id: str) -> None:
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["boxes"] = [b for b in data.get("boxes", []) if str(b.get("id")) != str(box_id)]
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)

    def get_boxes(self, filename: str) -> list[BoundingBox]:
        frame = self.get_frame_annotation(filename)
        return frame.boxes if frame else []

    # -- Bulk AI operations -------------------------------------------------

    def get_pending_box_count(self, filename: str) -> int:
        path = self._json_path(filename)
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        return sum(1 for b in data.get("boxes", []) if b.get("box_status") == "pending")

    def delete_ai_pending_boxes(self, filename: str) -> None:
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["boxes"] = [
            b for b in data.get("boxes", [])
            if not (b.get("source") == "ai_detected" and b.get("box_status") == "pending")
        ]
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)

    def bulk_assign_pending(self, filename: str, category: Category,
                            exclude_detected_class: Optional[str] = None) -> int:
        path = self._json_path(filename)
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for box_d in data.get("boxes", []):
            if box_d.get("box_status") != "pending":
                continue
            if exclude_detected_class and box_d.get("detected_class") == exclude_detected_class:
                continue
            box_d["category"] = category.value
            box_d["box_status"] = "finalized"
            count += 1
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_write(path, data)
        return count

    # -- Aggregation --------------------------------------------------------

    def iter_all_frames(self) -> Iterator[FrameAnnotation]:
        """Yield every frame annotation from disk."""
        for p in sorted(self.annotations_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                yield _dict_to_frame(data)
            except (json.JSONDecodeError, KeyError):
                continue

    def get_all_frame_summaries(self) -> list[dict]:
        """Return lightweight ``{filename, status, box_count}`` dicts."""
        summaries = []
        for p in sorted(self.annotations_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                summaries.append({
                    "filename": data.get("frame_filename", p.stem),
                    "status": data.get("status", "unviewed"),
                    "box_count": len(data.get("boxes", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return summaries

    def get_session_stats(self) -> dict:
        """Aggregate status counts across all annotations."""
        stats = {"total": 0, "annotated": 0, "skipped": 0, "unviewed": 0, "in_progress": 0}
        for p in self.annotations_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                status = data.get("status", "unviewed")
                stats[status] = stats.get(status, 0) + 1
                stats["total"] += 1
            except (json.JSONDecodeError, KeyError):
                continue
        return stats

    def get_next_seq(self) -> int:
        """Return the next sequence number for export (count of annotated + 1)."""
        count = 0
        for p in self.annotations_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("status") == "annotated":
                    count += 1
            except (json.JSONDecodeError, KeyError):
                continue
        return count + 1

    def has_annotations(self) -> bool:
        """Return True if any JSON files exist."""
        return any(self.annotations_dir.glob("*.json"))

    def ensure_frame(self, filename: str, session_meta: Optional[dict] = None) -> None:
        """Create an empty annotation file for a frame if it doesn't exist yet."""
        path = self._json_path(filename)
        if path.exists():
            return
        data = {
            "schema_version": SCHEMA_VERSION,
            "frame_filename": filename,
            "image_width": 0,
            "image_height": 0,
            "status": "unviewed",
            "annotator": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
            "session_metadata": session_meta or {},
            "boxes": [],
            "skip_reason": None,
        }
        self._atomic_write(path, data)

    def update_session_metadata(self, filename: str, session_meta: dict) -> None:
        """Update session-level metadata (source, round, opponent, etc.)."""
        path = self._json_path(filename)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["session_metadata"] = session_meta
        self._atomic_write(path, data)
