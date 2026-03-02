"""AI model manager for object detection in football annotation.

Supports two model families:
  - Football-specific models (from Roboflow): 4 classes (player, goalkeeper, referee, ball)
  - COCO generic models (via ultralytics): 80 classes, we use person + sports ball

This module is optional; the app works without it when ultralytics is not installed.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

MODELS_CACHE_DIR = Path.home() / ".cache" / "football-annotation-tool" / "models"

# ── Model registry ──

MODEL_REGISTRY = {
    # Football-specific (Roboflow): 4 classes — player, goalkeeper, referee, ball
    "football-rfdetr-n": {"file": "football-rfdetr-n.pt", "type": "football"},
    "football-rfdetr-s": {"file": "football-rfdetr-s.pt", "type": "football"},
    "football-rfdetr-m": {"file": "football-rfdetr-m.pt", "type": "football"},
    "football-yolo11n":  {"file": "football-yolo11n.pt",  "type": "football"},
    "football-yolo11s":  {"file": "football-yolo11s.pt",  "type": "football"},
    "football-yolo11m":  {"file": "football-yolo11m.pt",  "type": "football"},
    # COCO generic: 80 classes — we filter to person (0) + sports ball (32)
    "yolov8n": {"file": "yolov8n.pt", "type": "coco"},
    "yolov8s": {"file": "yolov8s.pt", "type": "coco"},
    "yolov8m": {"file": "yolov8m.pt", "type": "coco"},
}

# ── Class mappings ──

# Football models: 4 classes from Roboflow training
FOOTBALL_CLASS_MAPPING = {
    "player":     None,   # PENDING — user assigns home_player or opponent
    "goalkeeper":  None,   # PENDING — user assigns home_gk or opponent_gk
    "referee":     4,      # Auto-assign as REFEREE (Category.REFEREE = 4)
    "ball":        5,      # Auto-assign as BALL (Category.BALL = 5)
}

# COCO models: 80 classes, we only care about 2
COCO_CLASS_IDS = [0, 32]  # person, sports ball
COCO_CLASS_MAPPING = {
    "person":       None,  # PENDING
    "sports ball":  5,     # Auto-assign as BALL
}

# Roboflow project info for football model downloads
ROBOFLOW_WORKSPACE = "roboflow-jvuqo"
ROBOFLOW_PROJECT = "football-players-detection-3zvbc"
ROBOFLOW_VERSION = 17


class ModelManager:
    """Loads and runs object detection models for AI-assisted annotation."""

    def __init__(self, model_name: str = "football-yolo11s",
                 confidence: float = 0.30,
                 custom_model_path: Optional[str] = None):
        if not AI_AVAILABLE:
            raise RuntimeError(
                "ultralytics is not installed. "
                "Install with: pip install -r requirements-ai.txt"
            )

        self._confidence = max(0.10, min(0.90, confidence))
        self._model_name = model_name
        self._model = None
        self._custom_model_path = custom_model_path

        # Determine model type and path
        if custom_model_path:
            self._model_path = custom_model_path
            self._model_type = "custom"
        elif model_name in MODEL_REGISTRY:
            info = MODEL_REGISTRY[model_name]
            self._model_type = info["type"]
            if self._model_type == "coco":
                # COCO models auto-download via ultralytics
                self._model_path = info["file"]
            else:
                # Football models need explicit download
                MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                self._model_path = str(MODELS_CACHE_DIR / info["file"])
        else:
            # Fallback to treating as ultralytics model name
            self._model_path = model_name
            self._model_type = "custom"

    def load(self, progress_callback=None):
        """Load the model. Downloads weights on first use.

        Args:
            progress_callback: Optional callable(message: str) for status updates.
        """
        if self._model_type == "football" and not Path(self._model_path).exists():
            self._download_football_model(progress_callback)

        if progress_callback:
            progress_callback(f"Loading {self._model_name}...")

        self._model = YOLO(self._model_path)

    def _download_football_model(self, progress_callback=None):
        """Download football-specific model from Roboflow Universe."""
        if progress_callback:
            progress_callback(f"Downloading {self._model_name} from Roboflow...")

        # Determine which format to download based on model name
        if "rfdetr" in self._model_name:
            model_format = "rfdetr"
        else:
            model_format = "yolov11"

        # Determine size variant
        if self._model_name.endswith("n"):
            size = "n"
        elif self._model_name.endswith("m"):
            size = "m"
        else:
            size = "s"

        try:
            from roboflow import Roboflow
            rf = Roboflow()
            project = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)
            version = project.version(ROBOFLOW_VERSION)

            # Download model weights
            downloaded = version.download(model_format, location=str(MODELS_CACHE_DIR))
            # The downloaded weights should be at the expected path
            logger.info("Football model downloaded to %s", self._model_path)
        except ImportError:
            raise RuntimeError(
                f"Cannot auto-download football model '{self._model_name}'. "
                "Install the roboflow package (pip install roboflow) or "
                "download weights manually and use 'Custom model...' option."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to download football model: {e}\n"
                "You can download weights manually from Roboflow Universe and "
                "use 'Custom model...' option."
            )

    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float):
        self._confidence = max(0.10, min(0.90, value))

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_type(self) -> str:
        """Return 'football', 'coco', or 'custom'."""
        return self._model_type

    @property
    def is_football_model(self) -> bool:
        return self._model_type == "football"

    def is_loaded(self) -> bool:
        return self._model is not None

    def detect(self, image_path: str) -> list[dict]:
        """Run detection on a single image.

        Returns list of dicts:
            {
                "bbox": (x, y, w, h),      # top-left corner + size, image pixels
                "confidence": float,
                "class_name": str,          # "player", "goalkeeper", "person", etc.
                "class_id": int,            # raw model class id
                "auto_category": int|None,  # Category value if auto-assignable, else None
            }
        """
        if not self._model:
            self.load()

        # For COCO models, filter to only person + sports ball
        predict_kwargs = {
            "conf": self._confidence,
            "verbose": False,
        }
        if self._model_type == "coco":
            predict_kwargs["classes"] = COCO_CLASS_IDS

        results = self._model.predict(image_path, **predict_kwargs)

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                cls_name = result.names[cls_id]

                # Determine auto-category from class mapping
                if self._model_type == "football":
                    mapping = FOOTBALL_CLASS_MAPPING
                elif self._model_type == "coco":
                    mapping = COCO_CLASS_MAPPING
                else:
                    # Custom model: treat all detections as PENDING
                    mapping = {}

                auto_cat = mapping.get(cls_name)

                detections.append({
                    "bbox": (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                    "confidence": round(conf, 3),
                    "class_name": cls_name,
                    "class_id": cls_id,
                    "auto_category": auto_cat,
                })

        return detections

    def get_model_info(self) -> dict:
        """Return model metadata for display."""
        return {
            "name": self._model_name,
            "type": self._model_type,
            "confidence": self._confidence,
            "loaded": self.is_loaded(),
        }
