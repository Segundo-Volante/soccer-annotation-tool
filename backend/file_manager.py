from pathlib import Path
from typing import Optional

import cv2
import numpy as np

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
