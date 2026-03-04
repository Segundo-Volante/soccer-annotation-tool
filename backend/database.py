import json
import sqlite3
from pathlib import Path
from typing import Optional

from backend.models import (
    BoundingBox, BoxSource, BoxStatus, Category, FrameAnnotation,
    FrameStatus, Occlusion,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path TEXT NOT NULL,
    source TEXT NOT NULL,
    match_round TEXT NOT NULL,
    opponent TEXT,
    weather TEXT NOT NULL,
    lighting TEXT NOT NULL,
    opponent_roster_path TEXT,
    annotation_mode TEXT DEFAULT 'manual',
    model_name TEXT,
    model_confidence REAL DEFAULT 0.30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_opened TIMESTAMP
);

CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    original_filename TEXT NOT NULL,
    image_width INTEGER,
    image_height INTEGER,
    -- Legacy individual metadata columns (kept for backward compat)
    shot_type TEXT DEFAULT 'wide',
    camera_motion TEXT DEFAULT 'static',
    ball_status TEXT DEFAULT 'visible',
    game_situation TEXT DEFAULT 'open_play',
    pitch_zone TEXT DEFAULT 'middle_third',
    frame_quality TEXT DEFAULT 'clean',
    -- New JSON blob for dynamic metadata
    metadata_json TEXT DEFAULT '{}',
    -- State
    status TEXT DEFAULT 'unviewed',
    exported_filename TEXT,
    sort_order INTEGER,
    UNIQUE(session_id, original_filename)
);

CREATE TABLE IF NOT EXISTS boxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    category INTEGER NOT NULL,
    jersey_number INTEGER,
    player_name TEXT,
    occlusion TEXT DEFAULT 'visible',
    truncated INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    box_status TEXT DEFAULT 'finalized',
    confidence REAL,
    detected_class TEXT,
    unsure_note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_frames_session ON frames(session_id);
CREATE INDEX IF NOT EXISTS idx_frames_status ON frames(status);
CREATE INDEX IF NOT EXISTS idx_boxes_frame ON boxes(frame_id);
"""

# Legacy individual column names for migration
_LEGACY_META_COLS = [
    "shot_type", "camera_motion", "ball_status",
    "game_situation", "pitch_zone", "frame_quality",
]


class DatabaseManager:
    def __init__(self, db_path: str | Path = "annotations.db"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Add columns that may not exist in older databases."""
        # Sessions table migrations
        existing = {r[1] for r in self.conn.execute("PRAGMA table_info(sessions)").fetchall()}
        for col, default in [
            ("opponent", "''"),
            ("weather", "'clear'"),
            ("lighting", "'floodlight'"),
            ("opponent_roster_path", "NULL"),
        ]:
            if col not in existing:
                self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT DEFAULT {default}")

        # Frames table migrations
        existing = {r[1] for r in self.conn.execute("PRAGMA table_info(frames)").fetchall()}
        for col, default in [
            ("ball_status", "'visible'"), ("game_situation", "'open_play'"),
            ("pitch_zone", "'middle_third'"), ("frame_quality", "'clean'"),
        ]:
            if col not in existing:
                self.conn.execute(f"ALTER TABLE frames ADD COLUMN {col} TEXT DEFAULT {default}")

        # Add metadata_json column if missing
        if "metadata_json" not in existing:
            self.conn.execute("ALTER TABLE frames ADD COLUMN metadata_json TEXT DEFAULT '{}'")
            # Migrate existing individual columns into JSON blob
            self._migrate_metadata_to_json()

        # Rename old columns if they exist
        if "ball_visible" in existing and "ball_status" not in existing:
            self.conn.execute("ALTER TABLE frames ADD COLUMN ball_status TEXT DEFAULT 'visible'")

        # Sessions table: AI-assisted mode columns
        existing_sess = {r[1] for r in self.conn.execute("PRAGMA table_info(sessions)").fetchall()}
        for col, sql_default in [
            ("annotation_mode", "'manual'"),
            ("model_name", "NULL"),
            ("model_confidence", "0.30"),
        ]:
            if col not in existing_sess:
                self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT DEFAULT {sql_default}")

        # Boxes table: AI-assisted mode columns
        existing_box = {r[1] for r in self.conn.execute("PRAGMA table_info(boxes)").fetchall()}
        for col, sql_default in [
            ("source", "'manual'"),
            ("box_status", "'finalized'"),
            ("confidence", "NULL"),
            ("detected_class", "NULL"),
            ("unsure_note", "NULL"),
        ]:
            if col not in existing_box:
                self.conn.execute(f"ALTER TABLE boxes ADD COLUMN {col} TEXT DEFAULT {sql_default}")

    def _migrate_metadata_to_json(self):
        """Batch-migrate legacy individual metadata columns into metadata_json."""
        rows = self.conn.execute(
            "SELECT id, shot_type, camera_motion, ball_status, "
            "game_situation, pitch_zone, frame_quality FROM frames "
            "WHERE metadata_json IS NULL OR metadata_json = '{}'"
        ).fetchall()
        for row in rows:
            meta = {}
            for col in _LEGACY_META_COLS:
                val = row[col]
                if val is not None:
                    meta[col] = val
            if meta:
                self.conn.execute(
                    "UPDATE frames SET metadata_json = ? WHERE id = ?",
                    (json.dumps(meta), row["id"]),
                )

    def close(self):
        self.conn.close()

    # ── Session operations ──

    def create_session(self, folder_path: str, source: str, match_round: str,
                       opponent: str = "", weather: str = "clear",
                       lighting: str = "floodlight",
                       opponent_roster_path: str = "",
                       annotation_mode: str = "manual",
                       model_name: str = "",
                       model_confidence: float = 0.30) -> int:
        cur = self.conn.execute(
            "INSERT INTO sessions (folder_path, source, match_round, opponent, "
            "weather, lighting, opponent_roster_path, annotation_mode, "
            "model_name, model_confidence, last_opened) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (folder_path, source, match_round, opponent, weather, lighting,
             opponent_roster_path or None, annotation_mode,
             model_name or None, model_confidence),
        )
        self.conn.commit()
        return cur.lastrowid

    def find_session_by_folder(self, folder_path: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM sessions WHERE folder_path = ? ORDER BY created_at DESC LIMIT 1",
            (folder_path,),
        ).fetchone()
        return row["id"] if row else None

    def get_session(self, session_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE sessions SET last_opened = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,),
            )
            self.conn.commit()
            return dict(row)
        return None

    # ── Frame operations ──

    def add_frame(self, session_id: int, filename: str, sort_order: int,
                  image_width: int = 0, image_height: int = 0) -> int:
        cur = self.conn.execute(
            "INSERT INTO frames (session_id, original_filename, sort_order, "
            "image_width, image_height) VALUES (?, ?, ?, ?, ?)",
            (session_id, filename, sort_order, image_width, image_height),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_frame(self, frame_id: int) -> Optional[FrameAnnotation]:
        row = self.conn.execute(
            "SELECT f.*, s.source, s.match_round, s.opponent, s.weather, s.lighting "
            "FROM frames f JOIN sessions s ON f.session_id = s.id WHERE f.id = ?",
            (frame_id,),
        ).fetchone()
        if not row:
            return None
        frame = self._row_to_frame(row)
        frame.boxes = self.get_boxes(frame_id)
        return frame

    def get_session_frames(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, original_filename, status, sort_order FROM frames "
            "WHERE session_id = ? ORDER BY sort_order",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_frame_metadata(self, frame_id: int, **kwargs):
        """Save metadata as JSON blob. Also updates legacy columns for compatibility."""
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if not updates:
            return
        # Read existing metadata_json and merge
        row = self.conn.execute(
            "SELECT metadata_json FROM frames WHERE id = ?", (frame_id,)
        ).fetchone()
        existing = {}
        if row and row["metadata_json"]:
            try:
                existing = json.loads(row["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing.update(updates)
        # Save JSON blob
        self.conn.execute(
            "UPDATE frames SET metadata_json = ? WHERE id = ?",
            (json.dumps(existing), frame_id),
        )
        # Also update legacy columns that exist
        legacy_updates = {k: v for k, v in updates.items() if k in set(_LEGACY_META_COLS)}
        if legacy_updates:
            set_clause = ", ".join(f"{k} = ?" for k in legacy_updates)
            self.conn.execute(
                f"UPDATE frames SET {set_clause} WHERE id = ?",
                (*legacy_updates.values(), frame_id),
            )
        self.conn.commit()

    def set_frame_status(self, frame_id: int, status: FrameStatus):
        self.conn.execute(
            "UPDATE frames SET status = ? WHERE id = ?",
            (status.value, frame_id),
        )
        self.conn.commit()

    def set_frame_dimensions(self, frame_id: int, width: int, height: int):
        self.conn.execute(
            "UPDATE frames SET image_width = ?, image_height = ? WHERE id = ?",
            (width, height, frame_id),
        )
        self.conn.commit()

    def set_exported_filename(self, frame_id: int, filename: str):
        self.conn.execute(
            "UPDATE frames SET exported_filename = ? WHERE id = ?",
            (filename, frame_id),
        )
        self.conn.commit()

    # ── Box operations ──

    def add_box(self, frame_id: int, x: int, y: int, width: int, height: int,
                category: Category, jersey_number: Optional[int] = None,
                player_name: Optional[str] = None,
                occlusion: Occlusion = Occlusion.VISIBLE,
                truncated: bool = False,
                source: str = "manual",
                box_status: str = "finalized",
                confidence: Optional[float] = None,
                detected_class: Optional[str] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO boxes (frame_id, x, y, width, height, category, "
            "jersey_number, player_name, occlusion, truncated, "
            "source, box_status, confidence, detected_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (frame_id, x, y, width, height, category.value,
             jersey_number, player_name, occlusion.value, int(truncated),
             source, box_status, confidence, detected_class),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_box(self, box_id: int, **kwargs):
        allowed = {"x", "y", "width", "height", "category", "jersey_number",
                    "player_name", "occlusion", "truncated",
                    "source", "box_status", "confidence", "detected_class",
                    "unsure_note"}
        updates = {}
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k == "category" and isinstance(v, Category):
                v = v.value
            elif k == "occlusion" and isinstance(v, Occlusion):
                v = v.value
            elif k == "truncated" and isinstance(v, bool):
                v = int(v)
            updates[k] = v
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE boxes SET {set_clause} WHERE id = ?",
            (*updates.values(), box_id),
        )
        self.conn.commit()

    def delete_box(self, box_id: int):
        self.conn.execute("DELETE FROM boxes WHERE id = ?", (box_id,))
        self.conn.commit()

    def get_boxes(self, frame_id: int) -> list[BoundingBox]:
        rows = self.conn.execute(
            "SELECT * FROM boxes WHERE frame_id = ? ORDER BY created_at",
            (frame_id,),
        ).fetchall()
        return [self._row_to_box(r) for r in rows]

    # ── AI-Assisted mode operations ──

    def get_pending_box_count(self, frame_id: int) -> int:
        """Count boxes awaiting category assignment on a frame."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM boxes "
            "WHERE frame_id = ? AND box_status = 'pending'",
            (frame_id,),
        ).fetchone()
        return row["cnt"]

    def delete_ai_pending_boxes(self, frame_id: int):
        """Remove all AI-detected pending boxes (for re-detect). Keeps finalized and manual boxes."""
        self.conn.execute(
            "DELETE FROM boxes WHERE frame_id = ? "
            "AND source = 'ai_detected' AND box_status = 'pending'",
            (frame_id,),
        )
        self.conn.commit()

    def bulk_assign_pending(self, frame_id: int, category: Category,
                            exclude_detected_class: Optional[str] = None) -> int:
        """Assign all pending boxes on a frame to a given category.

        Args:
            exclude_detected_class: If set, skip boxes with this detected class
                (e.g. 'goalkeeper' should not be bulk-assigned as opponent).

        Returns:
            Number of boxes updated.
        """
        if exclude_detected_class:
            cursor = self.conn.execute(
                "UPDATE boxes SET category = ?, box_status = 'finalized' "
                "WHERE frame_id = ? AND box_status = 'pending' "
                "AND (detected_class IS NULL OR detected_class != ?)",
                (category.value, frame_id, exclude_detected_class),
            )
        else:
            cursor = self.conn.execute(
                "UPDATE boxes SET category = ?, box_status = 'finalized' "
                "WHERE frame_id = ? AND box_status = 'pending'",
                (category.value, frame_id),
            )
        self.conn.commit()
        return cursor.rowcount

    def get_session_mode(self, session_id: int) -> str:
        """Return the annotation_mode for a session."""
        row = self.conn.execute(
            "SELECT annotation_mode FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return row["annotation_mode"] if row and row["annotation_mode"] else "manual"

    # ── Stats ──

    def get_session_stats(self, session_id: int) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM frames "
            "WHERE session_id = ? GROUP BY status",
            (session_id,),
        ).fetchall()
        stats = {"total": 0, "annotated": 0, "skipped": 0, "unviewed": 0, "in_progress": 0}
        for r in rows:
            stats[r["status"]] = r["cnt"]
            stats["total"] += r["cnt"]
        return stats

    def get_next_seq(self, session_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM frames "
            "WHERE session_id = ? AND status = 'annotated'",
            (session_id,),
        ).fetchone()
        return row["cnt"] + 1

    # ── Helpers ──

    def _row_to_frame(self, row) -> FrameAnnotation:
        # Build metadata dict: start with legacy columns, then overlay JSON blob
        metadata = {}
        keys = row.keys()

        # Read legacy individual columns as base defaults
        for col in _LEGACY_META_COLS:
            if col in keys:
                val = row[col]
                if val is not None:
                    metadata[col] = val

        # Overlay with metadata_json (takes priority over legacy columns)
        metadata_json_str = row["metadata_json"] if "metadata_json" in keys else None
        if metadata_json_str and metadata_json_str != "{}":
            try:
                json_meta = json.loads(metadata_json_str)
                metadata.update(json_meta)
            except (json.JSONDecodeError, TypeError):
                pass

        return FrameAnnotation(
            id=row["id"],
            original_filename=row["original_filename"],
            image_width=row["image_width"] or 0,
            image_height=row["image_height"] or 0,
            source=row["source"],
            match_round=row["match_round"],
            opponent=row["opponent"] or "",
            weather=row["weather"] or "clear",
            lighting=row["lighting"] or "floodlight",
            metadata=metadata,
            status=FrameStatus(row["status"]),
            exported_filename=row["exported_filename"],
        )

    def _row_to_box(self, row) -> BoundingBox:
        keys = row.keys()
        return BoundingBox(
            id=row["id"],
            frame_id=row["frame_id"],
            x=row["x"],
            y=row["y"],
            width=row["width"],
            height=row["height"],
            category=Category(row["category"]),
            jersey_number=row["jersey_number"],
            player_name=row["player_name"],
            occlusion=Occlusion(row["occlusion"]) if row["occlusion"] else Occlusion.VISIBLE,
            truncated=bool(row["truncated"]),
            source=BoxSource(row["source"]) if "source" in keys and row["source"] else BoxSource.MANUAL,
            box_status=BoxStatus(row["box_status"]) if "box_status" in keys and row["box_status"] else BoxStatus.FINALIZED,
            confidence=row["confidence"] if "confidence" in keys else None,
            detected_class=row["detected_class"] if "detected_class" in keys else None,
            unsure_note=row["unsure_note"] if "unsure_note" in keys else None,
        )
