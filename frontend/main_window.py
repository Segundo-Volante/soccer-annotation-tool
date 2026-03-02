import os
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QMessageBox, QApplication, QDialog, QLabel, QPushButton,
    QProgressBar, QGraphicsOpacityEffect,
)

from pathlib import Path

from backend.database import DatabaseManager
from backend.exporter import Exporter
from backend.file_manager import FileManager
from backend.i18n import I18n, t
from backend.models import (
    BoundingBox, BoxStatus, Category, FrameAnnotation, FrameStatus,
    Occlusion, METADATA_KEYS,
)
from backend.project_config import ProjectConfig
from backend.roster_manager import RosterManager
from frontend.annotation_panel import AnnotationPanel
from frontend.canvas import AnnotationCanvas
from frontend.filmstrip import Filmstrip
from frontend.metadata_bar import MetadataBar
from frontend.player_popup import PlayerPopup
from frontend.progress_bar import ProgressBarWidget
from frontend.session_dialog import SessionDialog
from frontend.setup_wizard import SetupWizard
from frontend.shortcuts import ShortcutHandler
from frontend.toast import Toast

logger = logging.getLogger(__name__)


class _DetectionOverlay(QWidget):
    """Full-canvas dark overlay with progress bar shown during AI detection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)

        # Dark semi-transparent background covering the entire canvas
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(0, 0, 0, 160))
        self.setPalette(palette)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Container card
        card = QWidget()
        card.setFixedSize(360, 130)
        card.setStyleSheet(
            "QWidget { background: #1E1E2E; border: 2px solid #F5A623;"
            " border-radius: 14px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 18, 24, 18)
        card_layout.setSpacing(12)

        # Status label
        self._label = QLabel("Detecting objects...")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #F5A623; font-size: 15px; font-weight: bold;"
            " background: transparent; border: none;"
        )
        card_layout.addWidget(self._label)

        # Indeterminate progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #2A2A3C; border: none; border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F5A623, stop:0.5 #FFD580, stop:1 #F5A623
                );
                border-radius: 4px;
            }
        """)
        card_layout.addWidget(self._progress)

        # Elapsed time label
        self._time_label = QLabel("0.0s")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setStyleSheet(
            "color: #8888A0; font-size: 12px; background: transparent; border: none;"
        )
        card_layout.addWidget(self._time_label)

        layout.addWidget(card)

        # Elapsed timer
        self._elapsed_ms = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self, model_name: str = ""):
        self._elapsed_ms = 0
        if model_name:
            self._label.setText(f"Detecting with {model_name}...")
        else:
            self._label.setText("Detecting objects...")
        self._time_label.setText("0.0s")
        self._timer.start(100)
        # Match parent size
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._elapsed_ms += 100
        secs = self._elapsed_ms / 1000
        if secs < 10:
            self._time_label.setText(f"{secs:.1f}s")
        else:
            self._time_label.setText(f"{secs:.0f}s — model loading, please wait...")


class _DetectionWorker(QObject):
    """Runs YOLO inference in a background thread."""
    finished = pyqtSignal(list)   # list of detection dicts
    error = pyqtSignal(str)       # error message

    def __init__(self, model_manager, image_path: str):
        super().__init__()
        self._model_manager = model_manager
        self._image_path = image_path

    def run(self):
        try:
            detections = self._model_manager.detect(self._image_path)
            self.finished.emit(detections)
        except Exception as e:
            logger.error("AI detection failed: %s", e, exc_info=True)
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Load project config
        config_dir = Path(__file__).parent.parent / "config"
        self._project_config = ProjectConfig(config_dir)

        # Load i18n
        lang = self._project_config.language if self._project_config.exists else "en"
        I18n.load(lang, config_dir)

        self.setWindowTitle(t("main.window_title"))
        self.setMinimumSize(1200, 700)
        self.resize(1600, 900)
        self.setStyleSheet("background: #1E1E1E;")

        # Backend
        self._db: Optional[DatabaseManager] = None
        self._roster: Optional[RosterManager] = None
        self._opponent_roster: Optional[RosterManager] = None
        self._exporter: Optional[Exporter] = None

        # Session state
        self._session_id: Optional[int] = None
        self._folder_path: Optional[str] = None
        self._frames: list[dict] = []
        self._current_row: int = -1
        self._current_frame: Optional[FrameAnnotation] = None
        self._pending_box: Optional[tuple] = None  # (x, y, w, h) waiting for category
        self._undo_stack: list[int] = []  # box IDs for undo

        # AI-Assisted mode state
        self._annotation_mode: str = "manual"
        self._model_manager = None  # Optional ModelManager instance
        self._ai_status_label: Optional[QLabel] = None
        self._ai_redetect_btn: Optional[QPushButton] = None
        self._detection_thread: Optional[QThread] = None
        self._detection_worker: Optional[_DetectionWorker] = None
        self._detecting: bool = False  # True while detection is running
        self._detecting_frame_id: Optional[int] = None

        # Build UI
        self._build_ui()
        self._build_shortcuts()

        # Install app-level event filter so shortcuts work regardless of focus
        QApplication.instance().installEventFilter(self)
        # Also watch canvas for resize events (to keep detection overlay sized)
        self._canvas.installEventFilter(self)

        # Show session dialog on start
        QTimer.singleShot(100, self._show_session_dialog)

    def eventFilter(self, obj, event):
        """Capture all key presses app-wide so shortcuts work even when
        buttons or other widgets have focus."""
        # Keep detection overlay sized to canvas
        if obj is self._canvas and event.type() == QEvent.Type.Resize:
            self._detection_overlay.setGeometry(self._canvas.rect())

        if event.type() == QEvent.Type.KeyPress:
            # Skip shortcuts when a dialog is active (session dialog, popups, etc.)
            active_window = QApplication.instance().activeWindow()
            if active_window is not self:
                return False
            if self._shortcuts._popup_open:
                return False
            from PyQt6.QtWidgets import QLineEdit, QComboBox
            focused = QApplication.instance().focusWidget()
            if isinstance(focused, (QLineEdit, QComboBox)):
                return False
            if self._shortcuts.handle_key(event):
                return True
        return super().eventFilter(obj, event)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Progress bar
        self._progress = ProgressBarWidget()
        root.addWidget(self._progress)

        # Middle section: filmstrip | canvas | annotation panel
        mid = QHBoxLayout()
        mid.setSpacing(0)

        self._filmstrip = Filmstrip()
        self._filmstrip.frame_selected.connect(self._on_filmstrip_select)
        mid.addWidget(self._filmstrip)

        # Canvas with detection overlay stacked on top
        canvas_container = QWidget()
        canvas_stack = QVBoxLayout(canvas_container)
        canvas_stack.setContentsMargins(0, 0, 0, 0)
        canvas_stack.setSpacing(0)

        self._canvas = AnnotationCanvas()
        self._canvas.box_drawn.connect(self._on_box_drawn)
        self._canvas.box_selected.connect(self._on_canvas_box_selected)
        self._canvas.box_deselected.connect(self._on_canvas_box_deselected)
        self._canvas.box_moved.connect(self._on_box_moved)
        self._canvas.box_resized.connect(self._on_box_resized)
        canvas_stack.addWidget(self._canvas)

        # Detection overlay (lives on top of canvas)
        self._detection_overlay = _DetectionOverlay(self._canvas)
        self._detection_overlay.hide()

        mid.addWidget(canvas_container, stretch=1)

        self._annotation_panel = AnnotationPanel()
        self._annotation_panel.box_clicked.connect(self._on_panel_box_clicked)
        self._annotation_panel.box_double_clicked.connect(self._on_panel_box_double_clicked)
        self._annotation_panel.delete_requested.connect(self._delete_selected_box)
        mid.addWidget(self._annotation_panel)

        root.addLayout(mid, stretch=1)

        # Metadata bar (Tab+Number system)
        self._metadata_bar = MetadataBar()
        self._metadata_bar.metadata_changed.connect(self._on_metadata_changed)
        self._metadata_bar.auto_skip_triggered.connect(self._on_auto_skip)
        root.addWidget(self._metadata_bar)

        # Toast (overlay notification)
        self._toast = Toast(self)

    def _build_shortcuts(self):
        self._shortcuts = ShortcutHandler(self)

        # Number keys → route to pending box or metadata
        self._shortcuts.number_pressed.connect(self._on_number_key)

        # Tab cycling for metadata dimensions
        self._shortcuts.cycle_dimension.connect(self._metadata_bar.cycle_dim)

        # Occlusion
        self._shortcuts.occlusion_visible.connect(lambda: self._set_occlusion(Occlusion.VISIBLE))
        self._shortcuts.occlusion_partial.connect(lambda: self._set_occlusion(Occlusion.PARTIAL))
        self._shortcuts.occlusion_heavy.connect(lambda: self._set_occlusion(Occlusion.HEAVY))
        self._shortcuts.truncated_toggle.connect(self._toggle_truncated)

        # Navigation
        self._shortcuts.export_advance.connect(self._export_and_advance)
        self._shortcuts.skip_advance.connect(self._skip_and_advance)
        self._shortcuts.prev_frame.connect(self._go_prev)
        self._shortcuts.next_frame.connect(self._go_next)

        # Edit
        self._shortcuts.undo.connect(self._undo_last_box)
        self._shortcuts.delete_box.connect(self._delete_selected_box)
        self._shortcuts.force_save.connect(self._force_save)

        # AI bulk operations
        self._shortcuts.bulk_assign.connect(self._on_bulk_assign)
        self._shortcuts.accept_all.connect(self._on_accept_all)

    def keyPressEvent(self, event):
        if not self._shortcuts.handle_key(event):
            super().keyPressEvent(event)

    # ── Session management ──

    def _show_session_dialog(self):
        try:
            self._show_session_dialog_impl()
        except Exception as e:
            logger.error("Session dialog error: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to start session:\n{e}")

    def _show_session_dialog_impl(self):
        # First-run: show setup wizard if project.json doesn't exist
        if not self._project_config.exists:
            config_dir = Path(__file__).parent.parent / "config"
            wizard = SetupWizard(config_dir, self)
            if wizard.exec() != QDialog.DialogCode.Accepted:
                return
            # Reload config after wizard
            self._project_config = ProjectConfig(config_dir)

        lang_before = I18n.lang()
        dialog = SessionDialog(self, project_config=self._project_config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()

            # If language changed in session dialog, refresh all UI strings
            if result.get("language", lang_before) != lang_before:
                self._retranslate_ui()

            # Load home roster from session result or project config
            roster_path = result.get("roster", "")
            if not roster_path and self._project_config.exists:
                config_roster = self._project_config.get_home_roster_path()
                if config_roster:
                    roster_path = str(config_roster)
            self._roster = RosterManager(roster_path if roster_path else None)
            # Load opponent roster if available
            opponent = result.get("opponent", "")
            opp_csv = self._project_config.get_opponent_roster_path(opponent) if opponent else None
            self._opponent_roster = RosterManager(str(opp_csv)) if opp_csv else None
            self._start_session(
                result["folder"],
                result["source"],
                result["round"],
                opponent,
                result.get("weather", "clear"),
                result.get("lighting", "floodlight"),
                annotation_mode=result.get("annotation_mode", "manual"),
                model_name=result.get("model_name", ""),
                model_confidence=result.get("model_confidence", 0.30),
                custom_model_path=result.get("custom_model_path", ""),
            )

    def _retranslate_ui(self):
        """Refresh all translatable strings in main window and child widgets."""
        self.setWindowTitle(t("main.window_title"))
        self._annotation_panel.retranslate_ui()
        self._metadata_bar.retranslate_ui()
        # Canvas uses t() in paintEvent, so just repaint
        self._canvas.update()

    def _start_session(self, folder: str, source: str, match_round: str,
                       opponent: str = "", weather: str = "clear",
                       lighting: str = "floodlight",
                       annotation_mode: str = "manual",
                       model_name: str = "",
                       model_confidence: float = 0.30,
                       custom_model_path: str = ""):
        self._folder_path = folder
        self._annotation_mode = annotation_mode
        db_path = os.path.join(folder, "annotations.db")
        self._db = DatabaseManager(db_path)

        existing = self._db.find_session_by_folder(folder)
        if existing:
            self._session_id = existing
            session_data = self._db.get_session(existing)  # update last_opened
            # Always use the mode the user selected in the dialog (not stored mode)
        else:
            self._session_id = self._db.create_session(
                folder, source, match_round, opponent, weather, lighting,
                annotation_mode=annotation_mode,
                model_name=model_name,
                model_confidence=model_confidence,
            )
            # Scan and add frames
            filenames = FileManager.scan_folder(folder)
            if not filenames:
                QMessageBox.warning(self, t("error.title"), t("error.no_images_found"))
                return
            for i, fname in enumerate(filenames):
                self._db.add_frame(self._session_id, fname, i)

        # Initialize AI model if in AI-assisted mode
        self._model_manager = None
        if self._annotation_mode == "ai_assisted":
            self._init_model_manager(model_name, model_confidence, custom_model_path)

        # Setup exporter
        output_path = os.path.join(folder, "output")
        team_name = self._project_config.team_name if self._project_config.exists else "Home Team"
        self._exporter = Exporter(
            self._db, folder, output_path, team_name=team_name,
            has_opponent_roster=self._opponent_roster is not None,
        )

        # Load frames
        self._frames = self._db.get_session_frames(self._session_id)
        self._filmstrip.load_frames(self._frames, folder)

        self.setWindowTitle(t("main.window_title_with_team",
                              team_name=team_name, folder_name=os.path.basename(folder)))

        # Add AI status bar if in AI mode
        if self._annotation_mode == "ai_assisted":
            self._setup_ai_status_bar()

        # Jump to first unviewed frame
        first_unviewed = 0
        for i, f in enumerate(self._frames):
            if f["status"] == "unviewed":
                first_unviewed = i
                break
        self._load_frame_at_row(first_unviewed)

    def _init_model_manager(self, model_name: str, confidence: float,
                            custom_model_path: str = ""):
        """Create the AI model manager. Model loads lazily on first detect()."""
        logger.info("Initializing AI model: name=%s, conf=%.2f, custom=%s",
                     model_name, confidence, custom_model_path)
        try:
            from backend.model_manager import ModelManager, AI_AVAILABLE
            if not AI_AVAILABLE:
                logger.warning("AI not available — ultralytics not installed")
                self._toast.show_message(
                    "AI not available — install ultralytics", "warning", 5000)
                return
            self._model_manager = ModelManager(
                model_name=model_name or "yolov8n",
                confidence=confidence,
                custom_model_path=custom_model_path if custom_model_path else None,
            )
            # Model loads lazily on first detect() call (in background thread)
            logger.info("AI model manager created: %s (type=%s)",
                         self._model_manager.model_name, self._model_manager.model_type)
        except Exception as e:
            logger.error("Failed to create AI model manager: %s", e, exc_info=True)
            self._toast.show_message(f"Model init failed: {e}", "warning", 5000)
            self._model_manager = None

    def _setup_ai_status_bar(self):
        """Add an AI status bar below the progress bar."""
        central = self.centralWidget()
        root = central.layout()

        ai_bar = QWidget()
        ai_bar.setStyleSheet("background: #2A2A2A; border-top: 1px solid #444;")
        bar_layout = QHBoxLayout(ai_bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(8)

        model_name = self._model_manager.model_name if self._model_manager else "none"
        conf = self._model_manager.confidence if self._model_manager else 0.0
        self._ai_status_label = QLabel(
            t("ai.status_bar", model=model_name, conf=f"{conf:.2f}")
        )
        self._ai_status_label.setStyleSheet("color: #F5A623; font-size: 12px; font-weight: bold;")
        bar_layout.addWidget(self._ai_status_label)

        bar_layout.addStretch()

        self._ai_redetect_btn = QPushButton(t("ai.redetect"))
        self._ai_redetect_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ai_redetect_btn.setStyleSheet(
            "QPushButton { background: #3A3A3A; color: #F5A623; padding: 4px 12px;"
            " border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background: #4A4A4A; }"
        )
        self._ai_redetect_btn.clicked.connect(self._re_detect)
        bar_layout.addWidget(self._ai_redetect_btn)

        # Insert after progress bar (index 1)
        root.insertWidget(1, ai_bar)

    # ── Frame navigation ──

    def _load_frame_at_row(self, row: int):
        if not self._frames or row < 0 or row >= len(self._frames):
            return

        # Save current metadata for inheritance to next unviewed frame
        prev_meta = self._metadata_bar.get_metadata() if self._current_frame else None

        self._current_row = row
        frame_id = self._frames[row]["id"]
        self._current_frame = self._db.get_frame(frame_id)
        if not self._current_frame:
            return

        # Load image
        img_path = os.path.join(self._folder_path, self._current_frame.original_filename)
        self._canvas.set_image(img_path)

        # Set frame dimensions if not yet set
        if self._current_frame.image_width == 0 and self._canvas._pixmap:
            w = self._canvas._pixmap.width()
            h = self._canvas._pixmap.height()
            self._db.set_frame_dimensions(self._current_frame.id, w, h)
            self._current_frame.image_width = w
            self._current_frame.image_height = h

        # Load boxes
        self._canvas.set_boxes(self._current_frame.boxes)
        self._annotation_panel.update_boxes(self._current_frame.boxes)

        # Metadata inheritance: if frame is unviewed and we have previous metadata,
        # copy it to this frame so consecutive similar frames share metadata.
        if self._current_frame.status == FrameStatus.UNVIEWED and prev_meta:
            self._db.save_frame_metadata(self._current_frame.id, **prev_meta)
            for k, v in prev_meta.items():
                setattr(self._current_frame, k, v)

        # Set metadata bar from frame's dynamic metadata dict
        self._metadata_bar.set_metadata(**self._current_frame.metadata)

        # Update filmstrip selection
        self._filmstrip.select_row(row)

        # Mark in-progress
        if self._current_frame.status == FrameStatus.UNVIEWED:
            self._db.set_frame_status(self._current_frame.id, FrameStatus.IN_PROGRESS)
            self._current_frame.status = FrameStatus.IN_PROGRESS
            self._frames[row]["status"] = "in_progress"
            self._filmstrip.update_status(row, "in_progress")

        # Clear pending state
        self._pending_box = None
        self._canvas.clear_pending_box()
        self._undo_stack.clear()

        # AI detection: auto-detect on frames with no existing AI-detected boxes
        if self._annotation_mode == "ai_assisted" and self._model_manager:
            from backend.models import BoxSource
            has_ai_boxes = any(b.source == BoxSource.AI_DETECTED for b in self._current_frame.boxes)
            if (self._current_frame.status in (FrameStatus.UNVIEWED, FrameStatus.IN_PROGRESS)
                    and not has_ai_boxes):
                self._run_ai_detection()

        # Update progress
        self._update_progress()

    def _on_filmstrip_select(self, frame_id: int):
        for i, f in enumerate(self._frames):
            if f["id"] == frame_id:
                self._load_frame_at_row(i)
                return

    def _go_prev(self):
        if self._current_row > 0:
            self._load_frame_at_row(self._current_row - 1)

    def _go_next(self):
        if self._current_row < len(self._frames) - 1:
            self._load_frame_at_row(self._current_row + 1)

    def _advance_to_next_unviewed(self):
        for i in range(self._current_row + 1, len(self._frames)):
            if self._frames[i]["status"] in ("unviewed", "in_progress"):
                self._load_frame_at_row(i)
                return
        # No more unviewed — check if all done
        remaining = sum(1 for f in self._frames if f["status"] in ("unviewed", "in_progress"))
        if remaining == 0:
            self._show_completion_dialog()
        elif self._current_row < len(self._frames) - 1:
            self._load_frame_at_row(self._current_row + 1)

    # ── Number key routing ──

    def _on_number_key(self, n: int):
        """Route number key: pending box → category, selected AI box → assign, else → metadata."""
        categories = [
            Category.HOME_PLAYER,
            Category.OPPONENT,
            Category.HOME_GK,
            Category.OPPONENT_GK,
            Category.REFEREE,
            Category.BALL,
        ]
        # 1) Manual pending box (just drawn) → assign category
        if self._pending_box and 1 <= n <= 6:
            self._assign_category(categories[n - 1])
            return

        # 2) Selected AI PENDING box on canvas → assign category
        if 1 <= n <= 6 and self._current_frame:
            idx = self._canvas.get_selected_index()
            if idx >= 0 and idx < len(self._current_frame.boxes):
                box = self._current_frame.boxes[idx]
                if box.box_status == BoxStatus.PENDING:
                    self._assign_pending_ai_box(idx, categories[n - 1])
                    return

        # 3) Otherwise → metadata option
        self._metadata_bar.select_option(n)

    # ── Metadata ──

    def _on_metadata_changed(self, key: str, value: str):
        """Called when user selects a metadata option via number key."""
        self._save_metadata()

    def _on_auto_skip(self, key: str, value: str):
        """Called when a metadata value triggers auto-skip (e.g. replay, broadcast)."""
        if not self._current_frame or not self._db:
            return
        self._save_metadata()
        display = value.replace("_", " ")
        self._toast.show_message(t("toast.auto_skip", display=display), "skip")
        self._db.set_frame_status(self._current_frame.id, FrameStatus.SKIPPED)
        self._frames[self._current_row]["status"] = "skipped"
        self._filmstrip.update_status(self._current_row, "skipped")
        QTimer.singleShot(400, self._advance_to_next_unviewed)

    def _save_metadata(self):
        if not self._current_frame or not self._db:
            return
        meta = self._metadata_bar.get_metadata()
        self._db.save_frame_metadata(self._current_frame.id, **meta)
        # Keep frame object in sync
        for k, v in meta.items():
            setattr(self._current_frame, k, v)

    # ── Box drawing ──

    def _on_box_drawn(self, x, y, w, h):
        self._pending_box = (x, y, w, h)
        self._canvas.set_pending_box(x, y, w, h)
        self._toast.show_message(t("toast.press_category"), "info", 3000)

    def _get_roster_for_category(self, category: Category) -> Optional[RosterManager]:
        """Return the appropriate roster for a category, or None."""
        roster_type = self._project_config.get_category_roster_type(category.value)
        if roster_type == "home":
            return self._roster
        elif roster_type == "opponent_auto" and self._opponent_roster:
            return self._opponent_roster
        return None

    def _assign_category(self, category: Category):
        if not self._pending_box or not self._current_frame:
            return
        x, y, w, h = self._pending_box
        self._pending_box = None
        self._canvas.clear_pending_box()

        roster = self._get_roster_for_category(category)
        if roster:
            popup = PlayerPopup(roster, self)
            self._shortcuts.set_popup_open(True)
            result = popup.exec()
            self._shortcuts.set_popup_open(False)
            if result != PlayerPopup.DialogCode.Accepted:
                self._toast.show_message(t("toast.box_cancelled"), "warning")
                return
            jersey, name = popup.get_result()
            box_id = self._db.add_box(
                self._current_frame.id, x, y, w, h, category,
                jersey_number=jersey, player_name=name,
            )
        else:
            box_id = self._db.add_box(
                self._current_frame.id, x, y, w, h, category,
            )

        self._undo_stack.append(box_id)
        self._reload_boxes()
        self._toast.show_message(t("toast.box_added_hint"), "success")

    # ── Occlusion / truncated ──

    def _set_occlusion(self, occ: Occlusion):
        idx = self._canvas.get_selected_index()
        if idx < 0 or not self._current_frame:
            # Apply to last added box
            if self._current_frame and self._current_frame.boxes:
                box = self._current_frame.boxes[-1]
                self._db.update_box(box.id, occlusion=occ)
                self._reload_boxes()
            return
        box = self._current_frame.boxes[idx]
        self._db.update_box(box.id, occlusion=occ)
        self._reload_boxes()

    def _toggle_truncated(self):
        idx = self._canvas.get_selected_index()
        if not self._current_frame:
            return
        if idx < 0:
            if self._current_frame.boxes:
                box = self._current_frame.boxes[-1]
                self._db.update_box(box.id, truncated=not box.truncated)
                self._reload_boxes()
            return
        box = self._current_frame.boxes[idx]
        self._db.update_box(box.id, truncated=not box.truncated)
        self._reload_boxes()

    # ── Box selection / manipulation ──

    def _on_canvas_box_selected(self, index: int):
        self._annotation_panel.select_row(index)

    def _on_canvas_box_deselected(self):
        self._annotation_panel.select_row(-1)

    def _on_panel_box_clicked(self, index: int):
        self._canvas.select_box(index)

    def _on_panel_box_double_clicked(self, index: int):
        """Double-click a box in the panel to edit player info."""
        if not self._current_frame or index >= len(self._current_frame.boxes):
            return
        box = self._current_frame.boxes[index]
        roster = self._get_roster_for_category(box.category)
        if roster:
            popup = PlayerPopup(roster, self)
            self._shortcuts.set_popup_open(True)
            result = popup.exec()
            self._shortcuts.set_popup_open(False)
            if result == PlayerPopup.DialogCode.Accepted:
                jersey, name = popup.get_result()
                self._db.update_box(box.id, jersey_number=jersey, player_name=name)
                self._reload_boxes()

    def _on_box_moved(self, idx, x, y, w, h):
        if not self._current_frame or idx >= len(self._current_frame.boxes):
            return
        box = self._current_frame.boxes[idx]
        self._db.update_box(box.id, x=x, y=y)
        self._reload_boxes()

    def _on_box_resized(self, idx, x, y, w, h):
        if not self._current_frame or idx >= len(self._current_frame.boxes):
            return
        box = self._current_frame.boxes[idx]
        self._db.update_box(box.id, x=x, y=y, width=w, height=h)
        self._reload_boxes()

    def _delete_selected_box(self):
        idx = self._canvas.get_selected_index()
        if idx < 0 or not self._current_frame:
            return
        box = self._current_frame.boxes[idx]
        self._db.delete_box(box.id)
        self._canvas.clear_selection()
        self._reload_boxes()

    def _undo_last_box(self):
        if not self._undo_stack:
            return
        box_id = self._undo_stack.pop()
        self._db.delete_box(box_id)
        self._reload_boxes()

    # ── AI-Assisted mode ──

    def _run_ai_detection(self):
        """Run model detection in a background thread."""
        try:
            self._run_ai_detection_impl()
        except Exception as e:
            logger.error("AI detection setup error: %s", e, exc_info=True)
            self._detecting = False
            self._detection_overlay.stop()

    def _run_ai_detection_impl(self):
        if not self._model_manager or not self._current_frame:
            logger.warning("AI detection skipped: model=%s, frame=%s",
                           self._model_manager is not None,
                           self._current_frame is not None)
            return
        if self._detecting:
            logger.info("AI detection already in progress, skipping")
            return

        img_path = os.path.join(self._folder_path, self._current_frame.original_filename)
        logger.info("Starting AI detection on: %s", img_path)
        self._detecting = True
        self._detecting_frame_id = self._current_frame.id

        # Show progress overlay
        model_name = self._model_manager.model_name if self._model_manager else ""
        self._detection_overlay.setGeometry(self._canvas.rect())
        self._detection_overlay.start(model_name)

        # Create worker + thread
        self._detection_thread = QThread()
        self._detection_worker = _DetectionWorker(self._model_manager, img_path)
        self._detection_worker.moveToThread(self._detection_thread)

        # Connect signals
        self._detection_thread.started.connect(self._detection_worker.run)
        self._detection_worker.finished.connect(self._on_detection_finished)
        self._detection_worker.error.connect(self._on_detection_error)
        self._detection_worker.finished.connect(self._detection_thread.quit)
        self._detection_worker.error.connect(self._detection_thread.quit)
        self._detection_thread.finished.connect(self._cleanup_detection_thread)

        self._detection_thread.start()

    def _on_detection_finished(self, detections: list):
        """Handle detection results on main thread."""
        try:
            self._on_detection_finished_impl(detections)
        except Exception as e:
            logger.error("Detection result handling error: %s", e, exc_info=True)
            self._detecting = False
            self._detection_overlay.stop()

    def _on_detection_finished_impl(self, detections: list):
        self._detecting = False
        self._detection_overlay.stop()
        # Verify we're still on the same frame
        if not self._current_frame or self._current_frame.id != self._detecting_frame_id:
            logger.info("Frame changed during detection, discarding results")
            return

        logger.info("AI detection found %d objects", len(detections))
        pending_count = 0
        for det in detections:
            x, y, w, h = det["bbox"]
            auto_cat = det["auto_category"]
            cls_name = det["class_name"]
            conf = det["confidence"]

            if auto_cat is not None:
                category = Category(auto_cat)
                self._db.add_box(
                    self._current_frame.id, x, y, w, h, category,
                    source="ai_detected", box_status="finalized",
                    confidence=conf, detected_class=cls_name,
                )
            else:
                self._db.add_box(
                    self._current_frame.id, x, y, w, h, Category.OPPONENT,
                    source="ai_detected", box_status="pending",
                    confidence=conf, detected_class=cls_name,
                )
                pending_count += 1

        self._reload_boxes()
        total = len(detections)
        self._toast.show_message(
            t("ai.detection_complete", count=total, pending=pending_count),
            "info", 3000,
        )

    def _on_detection_error(self, error_msg: str):
        """Handle detection error on main thread."""
        self._detecting = False
        self._detection_overlay.stop()
        self._toast.show_message(f"Detection failed: {error_msg}", "warning", 3000)

    def _cleanup_detection_thread(self):
        """Clean up thread objects after detection completes."""
        if self._detection_worker:
            self._detection_worker.deleteLater()
            self._detection_worker = None
        if self._detection_thread:
            self._detection_thread.deleteLater()
            self._detection_thread = None

    def _assign_pending_ai_box(self, index: int, category: Category):
        """Assign a category to a selected PENDING AI box."""
        if not self._current_frame or index >= len(self._current_frame.boxes):
            return

        box = self._current_frame.boxes[index]
        if box.box_status != BoxStatus.PENDING:
            return

        # For categories that need a roster popup (home player, home gk, etc.)
        roster = self._get_roster_for_category(category)
        if roster:
            popup = PlayerPopup(roster, self)
            self._shortcuts.set_popup_open(True)
            result = popup.exec()
            self._shortcuts.set_popup_open(False)
            if result != PlayerPopup.DialogCode.Accepted:
                self._toast.show_message(t("toast.box_cancelled"), "warning")
                return
            jersey, name = popup.get_result()
            self._db.update_box(
                box.id, category=category, box_status="finalized",
                jersey_number=jersey, player_name=name,
            )
        else:
            self._db.update_box(box.id, category=category, box_status="finalized")

        self._reload_boxes()
        self._toast.show_message(t("ai.box_assigned"), "success")

        # Auto-select next pending box
        self._select_next_pending()

    def _select_next_pending(self):
        """Select the next PENDING box on canvas after assigning one."""
        if not self._current_frame:
            return
        for i, box in enumerate(self._current_frame.boxes):
            if box.box_status == BoxStatus.PENDING:
                self._canvas.select_box(i)
                self._annotation_panel.select_row(i)
                return

    def _on_bulk_assign(self, n: int):
        """Ctrl+N: bulk-assign all pending boxes to category N."""
        if self._annotation_mode != "ai_assisted" or not self._current_frame:
            return
        if n < 1 or n > 6:
            return

        categories = [
            Category.HOME_PLAYER, Category.OPPONENT, Category.HOME_GK,
            Category.OPPONENT_GK, Category.REFEREE, Category.BALL,
        ]
        category = categories[n - 1]

        # With football model and Ctrl+2 (Opponent), skip goalkeeper-detected boxes
        exclude_cls = None
        if (self._model_manager and self._model_manager.is_football_model
                and category == Category.OPPONENT):
            exclude_cls = "goalkeeper"

        count = self._db.bulk_assign_pending(
            self._current_frame.id, category, exclude_detected_class=exclude_cls,
        )
        if count > 0:
            from backend.models import CATEGORY_NAMES
            cat_name = CATEGORY_NAMES.get(category, "unknown")
            self._reload_boxes()
            self._toast.show_message(
                t("ai.bulk_assigned", count=count, category=cat_name), "success",
            )
        else:
            self._toast.show_message("No pending boxes to assign", "info")

    def _on_accept_all(self):
        """Ctrl+A: accept all pending boxes as Opponent after confirmation."""
        if self._annotation_mode != "ai_assisted" or not self._current_frame:
            return

        pending = self._db.get_pending_box_count(self._current_frame.id)
        if pending == 0:
            self._toast.show_message("No pending boxes", "info")
            return

        reply = QMessageBox.question(
            self,
            t("ai.accept_all_title"),
            t("ai.accept_all_message", count=pending),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = self._db.bulk_assign_pending(
                self._current_frame.id, Category.OPPONENT,
            )
            self._reload_boxes()
            from backend.models import CATEGORY_NAMES
            cat_name = CATEGORY_NAMES.get(Category.OPPONENT, "Opponent")
            self._toast.show_message(
                t("ai.bulk_assigned", count=count, category=cat_name), "success",
            )

    def _re_detect(self):
        """Delete pending AI boxes and re-run detection."""
        if not self._current_frame or not self._model_manager or self._detecting:
            return
        self._db.delete_ai_pending_boxes(self._current_frame.id)
        self._reload_boxes()
        self._run_ai_detection()

    # ── Export / Skip ──

    def _export_and_advance(self):
        if not self._current_frame or not self._exporter:
            return

        # AI mode: block export if pending boxes remain
        if self._annotation_mode == "ai_assisted" and self._db:
            pending = self._db.get_pending_box_count(self._current_frame.id)
            if pending > 0:
                self._toast.show_message(
                    t("ai.pending_blocks_export", count=pending), "warning", 3000,
                )
                return

        # Save metadata from bar
        self._save_metadata()

        # Validate metadata
        error = self._exporter.validate_metadata(self._current_frame)
        if error:
            self._toast.show_message(error, "warning")
            return

        # Reload boxes from DB
        self._current_frame.boxes = self._db.get_boxes(self._current_frame.id)

        exported = self._exporter.export_frame(self._current_frame, self._session_id)
        self._frames[self._current_row]["status"] = "annotated"
        self._filmstrip.update_status(self._current_row, "annotated")
        self._toast.show_message(t("toast.exported", exported=exported), "success")
        self._update_progress()
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _skip_and_advance(self):
        if not self._current_frame or not self._db:
            return
        self._db.set_frame_status(self._current_frame.id, FrameStatus.SKIPPED)
        self._frames[self._current_row]["status"] = "skipped"
        self._filmstrip.update_status(self._current_row, "skipped")
        self._toast.show_message(t("toast.frame_skipped"), "skip")
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _force_save(self):
        self._save_metadata()
        self._toast.show_message(t("toast.saved"), "info")

    # ── Helpers ──

    def _reload_boxes(self):
        if not self._current_frame:
            return
        self._current_frame.boxes = self._db.get_boxes(self._current_frame.id)
        self._canvas.set_boxes(self._current_frame.boxes)
        self._annotation_panel.update_boxes(self._current_frame.boxes)

    def _update_progress(self):
        if not self._db or not self._session_id:
            return
        stats = self._db.get_session_stats(self._session_id)
        remaining = stats["unviewed"] + stats["in_progress"]
        self._progress.update_progress(
            self._current_row + 1, stats["total"],
            stats["annotated"], stats["skipped"], remaining,
        )

    def _show_completion_dialog(self):
        output_path = os.path.join(self._folder_path, "output")
        stats = self._db.get_session_stats(self._session_id)
        msg = QMessageBox(self)
        msg.setWindowTitle(t("dialog.completion_title"))
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(t("dialog.completion_message"))
        msg.setInformativeText(
            t("completion.annotated", annotated=stats["annotated"], skipped=stats["skipped"])
            + "\n\n"
            + t("completion.output_path", path=output_path)
            + "\n\n"
            + t("completion.folder_list")
        )
        msg.setStyleSheet("QMessageBox { background: #2A2A2A; } "
                          "QLabel { color: #EEE; font-size: 13px; }")
        msg.exec()

    def closeEvent(self, event):
        # Stop any running detection thread
        if self._detection_thread and self._detection_thread.isRunning():
            self._detection_thread.quit()
            self._detection_thread.wait(3000)
        if self._db:
            self._db.close()
        super().closeEvent(event)
