import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}

# Reference crop size (stored at this size, displayed smaller in Squad Sheet)
REFERENCE_CROP_SIZE = 64


class FileManager:
    @staticmethod
    def scan_folder(path: str | Path) -> list[str]:
        folder = Path(path)
        if not folder.is_dir():
            return []
        files = [
            f.name for f in sorted(folder.iterdir())
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return files

    @staticmethod
    def create_output_dirs(output_path: str | Path):
        base = Path(output_path)
        (base / "frames").mkdir(parents=True, exist_ok=True)
        (base / "annotations").mkdir(parents=True, exist_ok=True)
        (base / "crops").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_image(path: str | Path) -> Optional[np.ndarray]:
        img = cv2.imread(str(path))
        return img

    @staticmethod
    def crop_region(image: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        h_img, w_img = image.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)
        return image[y1:y2, x1:x2].copy()

    @staticmethod
    def save_image(image: np.ndarray, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p), image)

    # ── Reference Crop Management ──

    @staticmethod
    def get_reference_crops_dir(session_folder: str | Path) -> Path:
        """Return the reference_crops/ directory in the session folder."""
        d = Path(session_folder) / "reference_crops"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def reference_crop_filename(side: str, jersey_number: int) -> str:
        """Generate filename for a reference crop: home_07.jpg or away_03.jpg."""
        return f"{side}_{jersey_number:02d}.jpg"

    @staticmethod
    def save_reference_crop(
        image: np.ndarray, x: int, y: int, w: int, h: int,
        session_folder: str | Path, side: str, jersey_number: int,
    ) -> Optional[Path]:
        """Crop, resize to 64x64, and save as a reference crop.

        Returns the path where it was saved, or None on failure.
        Only replaces an existing crop if the new one has a larger area (better resolution).
        """
        crop = FileManager.crop_region(image, x, y, w, h)
        if crop.size == 0:
            return None

        crops_dir = FileManager.get_reference_crops_dir(session_folder)
        fname = FileManager.reference_crop_filename(side, jersey_number)
        path = crops_dir / fname

        new_area = w * h

        # Check if we should replace existing crop
        if path.exists():
            # Read metadata file that stores the area
            meta_path = crops_dir / f"{side}_{jersey_number:02d}.meta"
            if meta_path.exists():
                try:
                    old_area = int(meta_path.read_text().strip())
                    if new_area <= old_area:
                        return path  # Existing crop is better, keep it
                except (ValueError, OSError):
                    pass  # Replace on error

        # Resize to REFERENCE_CROP_SIZE x REFERENCE_CROP_SIZE
        resized = cv2.resize(crop, (REFERENCE_CROP_SIZE, REFERENCE_CROP_SIZE),
                             interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(path), resized, [cv2.IMWRITE_JPEG_QUALITY, 90])

        # Save area metadata for future comparison
        meta_path = crops_dir / f"{side}_{jersey_number:02d}.meta"
        meta_path.write_text(str(new_area))

        return path

    @staticmethod
    def load_reference_crop(session_folder: str | Path, side: str,
                            jersey_number: int) -> Optional[Path]:
        """Return path to reference crop if it exists."""
        crops_dir = Path(session_folder) / "reference_crops"
        fname = FileManager.reference_crop_filename(side, jersey_number)
        path = crops_dir / fname
        return path if path.exists() else None

    # ── Screenshotter Bundle Support ──

    @staticmethod
    def is_screenshotter_bundle(folder_path: str | Path) -> bool:
        """Check if folder is a screenshotter annotation bundle.

        Checks the folder itself and also the parent folder (in case the
        user selected the frames/ subfolder directly).
        """
        folder = Path(folder_path)
        has_match = (folder / "match.json").exists()
        has_metadata = (folder / "frame_metadata.json").exists()
        if has_match and has_metadata:
            return True
        # Also check parent (user may have selected frames/ subfolder)
        parent = folder.parent
        has_match_parent = (parent / "match.json").exists()
        has_metadata_parent = (parent / "frame_metadata.json").exists()
        return has_match_parent and has_metadata_parent

    @staticmethod
    def get_bundle_root(folder_path: str | Path) -> Path:
        """Return the bundle root directory (containing match.json).

        If folder_path itself contains match.json, returns it.
        If the parent contains match.json (user selected frames/ subfolder),
        returns the parent.
        """
        folder = Path(folder_path)
        if (folder / "match.json").exists():
            return folder
        parent = folder.parent
        if (parent / "match.json").exists():
            return parent
        return folder

    @staticmethod
    def load_match_json(folder_path: str | Path) -> Optional[dict]:
        """Load match.json from a screenshotter bundle. Returns None on failure."""
        match_path = Path(folder_path) / "match.json"
        if not match_path.exists():
            return None
        try:
            return json.loads(match_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read match.json: %s", e)
            return None

    @staticmethod
    def load_frame_metadata(bundle_path: str | Path) -> dict[str, dict]:
        """Load frame_metadata.json and return dict keyed by filename for O(1) lookup.

        Returns empty dict on failure.
        """
        metadata_path = Path(bundle_path) / "frame_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            return {f["file_name"]: f for f in data.get("frames", [])}
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
            logger.warning("Failed to read frame_metadata.json: %s", e)
            return {}

    @staticmethod
    def load_frame_metadata_raw(bundle_path: str | Path) -> dict:
        """Load frame_metadata.json and return the full raw JSON dict.

        Returns empty dict on failure.  Includes session_info, sequence_summary, etc.
        """
        metadata_path = Path(bundle_path) / "frame_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read frame_metadata.json: %s", e)
            return {}

    @staticmethod
    def sort_frames_by_priority(
        filenames: list[str],
        frame_metadata: dict[str, dict],
    ) -> list[dict]:
        """Sort frames by annotation priority using camera_angle from metadata.

        Priority order (highest first):
        1. WIDE_CENTER frames (sorted by video_time ascending)
        2. WIDE_LEFT and WIDE_RIGHT frames (sorted by video_time)
        3. MEDIUM frames (sorted by video_time)
        4. Everything else / unknown (sorted by video_time)

        Returns list of dicts: [{filename, priority_group, video_time, camera_angle, ...}]
        """
        PRIORITY = {
            "WIDE_CENTER": 0,
            "WIDE_LEFT": 1,
            "WIDE_RIGHT": 1,
            "MEDIUM": 2,
        }

        enriched = []
        for fname in filenames:
            meta = frame_metadata.get(fname, {})
            camera_angle = meta.get("camera_angle", "UNKNOWN")
            video_time = meta.get("video_time", 99999.0)
            priority = PRIORITY.get(camera_angle, 3)
            enriched.append({
                "filename": fname,
                "original_filename": fname,
                "camera_angle": camera_angle,
                "video_time": video_time,
                "priority_group": priority,
            })

        enriched.sort(key=lambda x: (x["priority_group"], x["video_time"]))
        return enriched

    @staticmethod
    def format_video_time(seconds: float) -> str:
        """Convert seconds (e.g. 601.42) to mm:ss format (e.g. '10:01')."""
        try:
            total_secs = int(seconds)
            mins = total_secs // 60
            secs = total_secs % 60
            return f"{mins}:{secs:02d}"
        except (TypeError, ValueError):
            return "?:??"

    @staticmethod
    def get_priority_group_label(group: int) -> str:
        """Return a human-readable label for a priority group number."""
        labels = {
            0: "Wide Center",
            1: "Wide Left/Right",
            2: "Medium",
            3: "Other",
        }
        return labels.get(group, "Other")
