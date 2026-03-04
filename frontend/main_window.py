import os
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QMessageBox, QApplication, QDialog, QLabel, QPushButton,
    QProgressBar, QGraphicsOpacityEffect, QMenuBar, QMenu,
)

from pathlib import Path

from backend.annotation_store import AnnotationStore
from backend.backup_manager import BackupManager
from backend.batch_operations import BatchOperations
from backend.collaboration_manager import CollaborationManager
from backend.health_analyzer import HealthAnalyzer
from backend.session_stats import SessionStats
from backend.state_db import StateDB
from backend.exporter import Exporter
from backend.file_manager import FileManager
from backend.i18n import I18n, t
from backend.models import (
    BoundingBox, BoxStatus, Category, CATEGORY_NAMES, FrameAnnotation,
    FrameStatus, Occlusion, METADATA_KEYS,
)
from backend.project_config import ProjectConfig
from backend.roster_manager import RosterManager
from frontend.annotation_panel import AnnotationPanel
from frontend.canvas import AnnotationCanvas
from frontend.filmstrip import Filmstrip
from frontend.git_toolbar import GitToolbar
from frontend.health_dashboard import HealthDashboard
from frontend.metadata_bar import MetadataBar
from frontend.player_popup import PlayerPopup
from frontend.progress_bar import ProgressBarWidget
from frontend.review_panel import ReviewPanel
from frontend.session_dialog import SessionDialog
from frontend.session_summary_dialog import SessionSummaryDialog
from frontend.setup_wizard import SetupWizard
from frontend.shortcuts import ShortcutHandler
from frontend.stats_bar import StatsBar
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

        # Backend — per-frame JSON store + local state DB
        self._store: Optional[AnnotationStore] = None
        self._state_db: Optional[StateDB] = None
        self._roster: Optional[RosterManager] = None
        self._opponent_roster: Optional[RosterManager] = None
        self._exporter: Optional[Exporter] = None

        # Session state
        self._session_id: Optional[int] = None
        self._folder_path: Optional[str] = None
        self._frames: list[dict] = []           # [{filename, status, sort_order}, ...]
        self._current_row: int = -1
        self._current_frame: Optional[FrameAnnotation] = None
        self._current_filename: Optional[str] = None
        self._pending_box: Optional[tuple] = None  # (x, y, w, h) waiting for category
        self._undo_stack: list[tuple] = []  # (filename, box_id) pairs for undo

        # AI-Assisted mode state
        self._annotation_mode: str = "manual"
        self._model_manager = None  # Optional ModelManager instance
        self._ai_status_label: Optional[QLabel] = None
        self._ai_redetect_btn: Optional[QPushButton] = None
        self._detection_thread: Optional[QThread] = None
        self._detection_worker: Optional[_DetectionWorker] = None
        self._detecting: bool = False  # True while detection is running
        self._detecting_filename: Optional[str] = None

        # Phase 2-7: New subsystem instances
        self._backup_manager: Optional[BackupManager] = None
        self._session_stats: Optional[SessionStats] = None
        self._stats_bar: Optional[StatsBar] = None
        self._backup_timer: Optional[QTimer] = None

        # Collaboration
        self._collab_manager: Optional[CollaborationManager] = None
        self._git_toolbar: Optional[GitToolbar] = None
        self._team_panel = None  # Optional TeamPanel widget
        self._workflow: str = "solo"
        self._annotator_name: str = ""

        # Session metadata (carried from SessionDialog)
        self._session_meta: dict = {}

        # Build UI
        self._build_ui()
        self._build_menu_bar()
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

        # Reset space-held when window loses focus (prevents stuck state)
        if event.type() == QEvent.Type.WindowDeactivate:
            self._canvas.set_space_held(False)

        # Track Space key for pan mode (press and release)
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._canvas.set_space_held(True)
            return True
        if event.type() == QEvent.Type.KeyRelease and event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._canvas.set_space_held(False)
            return True

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

    def _build_menu_bar(self):
        """Build the application menu bar with Project menu."""
        menu_bar = self.menuBar()
        # Force menu bar inside the window (macOS defaults to native system bar)
        menu_bar.setNativeMenuBar(False)
        menu_bar.setStyleSheet("""
            QMenuBar {
                background: #1A1A2A; color: #E8E8F0; font-size: 12px;
                border-bottom: 1px solid #333350;
            }
            QMenuBar::item:selected { background: #2A2A3C; }
            QMenu {
                background: #1E1E2E; color: #E8E8F0; border: 1px solid #404060;
                font-size: 12px;
            }
            QMenu::item:selected { background: #F5A623; color: #1E1E2E; }
            QMenu::separator { background: #404060; height: 1px; margin: 4px 8px; }
        """)

        # ── Project Menu ──
        project_menu = menu_bar.addMenu("Project")

        # Collaboration Settings
        collab_action = QAction("Collaboration Settings...", self)
        collab_action.triggered.connect(self._open_collaboration_settings)
        project_menu.addAction(collab_action)

        project_menu.addSeparator()

        # Split Frames (Split & Merge workflow)
        self._split_action = QAction("Split Frames...", self)
        self._split_action.triggered.connect(self._open_split_dialog)
        project_menu.addAction(self._split_action)

        # Merge Annotations (Split & Merge workflow)
        self._merge_action = QAction("Merge Annotations...", self)
        self._merge_action.triggered.connect(self._open_merge_dialog)
        project_menu.addAction(self._merge_action)

        project_menu.addSeparator()

        # Git Settings (Git workflow)
        self._git_settings_action = QAction("Git Settings...", self)
        self._git_settings_action.triggered.connect(self._open_git_settings)
        project_menu.addAction(self._git_settings_action)

        project_menu.addSeparator()

        # Open Project Folder
        open_folder_action = QAction("Open Project Folder", self)
        open_folder_action.triggered.connect(self._open_project_folder)
        project_menu.addAction(open_folder_action)

        # ── Tools Menu ──
        tools_menu = menu_bar.addMenu("Tools")

        health_action = QAction("Dataset Health Dashboard\tCtrl+H", self)
        health_action.triggered.connect(self._open_health_dashboard)
        tools_menu.addAction(health_action)

        review_action = QAction("Quick Review && Batch Edit\tCtrl+R", self)
        review_action.triggered.connect(self._open_review_panel)
        tools_menu.addAction(review_action)

        export_action = QAction("Export Preview\tCtrl+E", self)
        export_action.triggered.connect(self._open_export_preview)
        tools_menu.addAction(export_action)

        # Update menu visibility based on workflow
        self._update_menu_visibility()

    def _update_menu_visibility(self):
        """Show/hide menu items based on active workflow."""
        is_split = self._workflow == "split_merge"
        is_git = self._workflow == "git"
        is_custom = self._workflow == "custom"

        self._split_action.setVisible(is_split or is_custom)
        self._merge_action.setVisible(is_split or is_custom)
        self._git_settings_action.setVisible(is_git or is_custom)

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

        # Dashboard / Review / Export Preview
        self._shortcuts.open_health.connect(self._open_health_dashboard)
        self._shortcuts.open_review.connect(self._open_review_panel)
        self._shortcuts.open_export_preview.connect(self._open_export_preview)

        # Box visibility toggle
        self._shortcuts.cycle_box_visibility.connect(self._cycle_box_visibility)

        # Zoom
        self._shortcuts.zoom_in.connect(self._canvas.zoom_in_step)
        self._shortcuts.zoom_out.connect(self._canvas.zoom_out_step)
        self._shortcuts.reset_zoom.connect(self._reset_zoom)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)

        # Arrow-key panning (when zoomed in)
        pan_step = 80  # pixels per arrow key press
        self._shortcuts.pan_left.connect(lambda: self._canvas.pan_by(pan_step, 0))
        self._shortcuts.pan_right.connect(lambda: self._canvas.pan_by(-pan_step, 0))
        self._shortcuts.pan_up.connect(lambda: self._canvas.pan_by(0, pan_step))
        self._shortcuts.pan_down.connect(lambda: self._canvas.pan_by(0, -pan_step))

        # Tell shortcuts handler how to check zoom state
        self._shortcuts._is_zoomed_fn = lambda: self._canvas.zoom_level > 1.0

    def keyPressEvent(self, event):
        if not self._shortcuts.handle_key(event):
            super().keyPressEvent(event)

    def _cycle_box_visibility(self):
        from frontend.canvas import BoxVisibilityMode
        self._canvas.cycle_box_visibility()
        mode = self._canvas.box_visibility
        labels = {
            BoxVisibilityMode.FULL: "Boxes: Full",
            BoxVisibilityMode.SUBTLE: "Boxes: Subtle",
            BoxVisibilityMode.CLEAN: "Boxes: Hidden",
        }
        label = labels[mode]
        if self._stats_bar:
            self._stats_bar.set_box_visibility_label(label)
        if hasattr(self, '_toast') and self._toast:
            self._toast.show_message(label, "info", 1500)

    def _reset_zoom(self):
        self._canvas.reset_zoom()

    def _on_zoom_changed(self, percent: int):
        if self._stats_bar:
            self._stats_bar.set_zoom_label(percent)

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

        # Session-level metadata to embed in every frame JSON
        self._session_meta = {
            "source": source,
            "match_round": match_round,
            "opponent": opponent,
            "weather": weather,
            "lighting": lighting,
        }

        # ── Check for migration from old SQLite format ──
        old_db_path = Path(folder) / "annotations.db"
        annotations_dir = Path(folder) / "annotations"
        if old_db_path.exists() and not (annotations_dir.exists() and any(annotations_dir.glob("*.json"))):
            self._offer_migration(old_db_path, folder)

        # ── Per-frame JSON store (new source of truth) ──
        self._store = AnnotationStore(folder)

        # ── Local state DB (session info, UI state) ──
        state_db_path = Path(folder) / "local_state.db"
        self._state_db = StateDB(state_db_path)

        existing = self._state_db.find_session_by_folder(folder)
        if existing:
            self._session_id = existing
            self._state_db.get_session(existing)  # updates last_opened
        else:
            self._session_id = self._state_db.create_session(
                folder, source, match_round, opponent, weather, lighting,
                annotation_mode=annotation_mode,
                model_name=model_name,
                model_confidence=model_confidence,
            )

        # ── Scan frames and ensure JSON files exist ──
        filenames = FileManager.scan_folder(folder)
        if not filenames:
            QMessageBox.warning(self, t("error.title"), t("error.no_images_found"))
            return

        # Build the frames list from scanned files + annotation status
        annotation_status = {}
        for summary in self._store.get_all_frame_summaries():
            annotation_status[summary["filename"]] = summary["status"]

        self._frames = []
        for i, fname in enumerate(filenames):
            status = annotation_status.get(fname, "unviewed")
            self._frames.append({
                "filename": fname,
                "original_filename": fname,  # compat key for filmstrip
                "status": status,
                "sort_order": i,
            })
            # Ensure each frame has a JSON annotation file
            self._store.ensure_frame(fname, session_meta=self._session_meta)

        # Initialize AI model if in AI-assisted mode
        self._model_manager = None
        if self._annotation_mode == "ai_assisted":
            self._init_model_manager(model_name, model_confidence, custom_model_path)

        # Setup exporter
        output_path = os.path.join(folder, "output")
        team_name = self._project_config.team_name if self._project_config.exists else "Home Team"
        self._exporter = Exporter(
            self._store, folder, output_path, team_name=team_name,
            has_opponent_roster=self._opponent_roster is not None,
        )

        # Load filmstrip
        self._filmstrip.load_frames(self._frames, folder)

        self.setWindowTitle(t("main.window_title_with_team",
                              team_name=team_name, folder_name=os.path.basename(folder)))

        # Add AI status bar if in AI mode
        if self._annotation_mode == "ai_assisted":
            self._setup_ai_status_bar()

        # ── Phase 2: Auto Backup ──
        self._backup_manager = BackupManager(folder)
        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._check_backup)
        self._backup_timer.start(60_000)  # check every 60s

        # ── Phase 3: Session Statistics ──
        self._session_stats = SessionStats(total_frames=len(self._frames))
        stats = self._store.get_session_stats()
        self._session_stats.update_counts(
            stats["annotated"], stats["skipped"], len(self._frames),
        )
        self._session_stats.start_session()
        self._setup_stats_bar()

        # Mark clean exit as False (will set True on close)
        if self._state_db:
            self._state_db.save_clean_exit(False)

        # Jump to first unviewed frame
        first_unviewed = 0
        for i, f in enumerate(self._frames):
            if f["status"] == "unviewed":
                first_unviewed = i
                break
        self._load_frame_at_row(first_unviewed)

    def _offer_migration(self, old_db_path: Path, folder: str):
        """Offer to migrate from old SQLite format to per-frame JSON."""
        reply = QMessageBox.question(
            self,
            "Migrate Project",
            "This project uses the old annotation format (SQLite).\n\n"
            "Migrate to the new per-frame JSON format?\n"
            "(Required for team collaboration features)\n\n"
            "Your old database will be backed up as annotations.db.backup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backend.migration import MigrationTool
                migrator = MigrationTool(old_db_path, folder)
                result = migrator.migrate()
                QMessageBox.information(
                    self,
                    "Migration Complete",
                    f"Migrated {result['frames_migrated']} frames "
                    f"and {result['boxes_migrated']} boxes.\n\n"
                    f"Old database backed up as annotations.db.backup.",
                )
            except Exception as e:
                logger.error("Migration failed: %s", e, exc_info=True)
                QMessageBox.critical(
                    self, "Migration Failed",
                    f"Migration failed: {e}\n\nYou can try again later.",
                )

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
        ai_bar.setStyleSheet("background: #2A2A3C; border-top: 1px solid #404060;")
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
            "QPushButton { background: #404060; color: #F5A623; padding: 4px 12px;"
            " border-radius: 3px; font-weight: bold; border: none; }"
            "QPushButton:hover { background: #505070; }"
        )
        self._ai_redetect_btn.clicked.connect(self._re_detect)
        bar_layout.addWidget(self._ai_redetect_btn)

        # Insert after progress bar (index 1)
        root.insertWidget(1, ai_bar)

    def _setup_stats_bar(self):
        """Add the real-time statistics bar below the progress bar."""
        if not self._session_stats:
            return
        central = self.centralWidget()
        root = central.layout()
        self._stats_bar = StatsBar(self._session_stats)
        # Insert after progress bar (and AI bar if present)
        insert_idx = 1
        if self._annotation_mode == "ai_assisted":
            insert_idx = 2
        root.insertWidget(insert_idx, self._stats_bar)

    def _check_backup(self):
        """Called by timer — triggers auto-backup if time interval reached."""
        if self._backup_manager:
            result = self._backup_manager.check_time_trigger()
            if result:
                self._toast.show_message(t("backup.auto"), "info", 2000)
                if self._state_db:
                    count = len(list(
                        (Path(self._folder_path) / "annotations").glob("*.json")
                    )) if self._folder_path else 0
                    self._state_db.record_backup(result, count)

    def _notify_backup_on_save(self):
        """Called after exporting a frame — may trigger backup by frame count."""
        if self._backup_manager:
            result = self._backup_manager.notify_frame_saved()
            if result:
                self._toast.show_message(t("backup.auto"), "info", 2000)

    # ── Menu Actions (Health, Review, Export Preview) ──

    def _open_health_dashboard(self):
        """Open the Dataset Health Dashboard."""
        if not self._store:
            return
        analyzer = HealthAnalyzer(self._store)
        dialog = HealthDashboard(analyzer, self)
        dialog.exec()

    def _open_review_panel(self):
        """Open the Quick Review & Batch Edit panel."""
        if not self._store:
            return
        batch_ops = BatchOperations(self._store)
        dialog = ReviewPanel(batch_ops, self)
        dialog.navigate_to_frame.connect(self._navigate_to_filename)
        dialog.exec()

    def _navigate_to_filename(self, filename: str):
        """Navigate to a specific frame by filename (from review panel)."""
        for i, f in enumerate(self._frames):
            if f["filename"] == filename:
                self._load_frame_at_row(i)
                return

    def _open_export_preview(self):
        """Open the Export Preview dialog for batch export."""
        if not self._store or not self._folder_path:
            return
        from frontend.export_preview_dialog import ExportPreviewDialog
        default_output = self._folder_path
        dialog = ExportPreviewDialog(
            self._store, self._folder_path, default_output, self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result["format"] == "yolo":
                self._run_yolo_export(result["output_folder"])
            # COCO export uses the existing per-frame export flow

    def _run_yolo_export(self, output_folder: str):
        """Run YOLO format export."""
        try:
            from backend.yolo_exporter import YOLOExporter
            exporter = YOLOExporter(
                self._store, self._folder_path,
                os.path.join(output_folder, "output_yolo"),
            )
            result = exporter.export()
            self._toast.show_message(
                t("export.yolo_complete",
                  frames=result["frames_exported"],
                  labels=result["labels_exported"]),
                "success", 4000,
            )
        except ImportError:
            self._toast.show_message(
                "YOLO export requires PyYAML — pip install pyyaml",
                "warning", 4000,
            )
        except Exception as e:
            logger.error("YOLO export failed: %s", e, exc_info=True)
            self._toast.show_message(f"Export failed: {e}", "warning", 4000)

    # ── Frame navigation ──

    def _load_frame_at_row(self, row: int):
        if not self._frames or row < 0 or row >= len(self._frames):
            return

        # Track stats: start timing for this frame
        if self._session_stats:
            self._session_stats.start_frame()

        # Save current metadata for inheritance to next unviewed frame
        prev_meta = self._metadata_bar.get_metadata() if self._current_frame else None

        self._current_row = row
        filename = self._frames[row]["filename"]
        self._current_filename = filename

        # Load frame annotation from JSON store
        self._current_frame = self._store.get_frame_annotation(filename)
        if not self._current_frame:
            # Create a minimal frame object for brand-new frames
            self._current_frame = FrameAnnotation(
                id=None, original_filename=filename,
                image_width=0, image_height=0,
                source=self._session_meta.get("source", ""),
                match_round=self._session_meta.get("match_round", ""),
                opponent=self._session_meta.get("opponent", ""),
                weather=self._session_meta.get("weather", "clear"),
                lighting=self._session_meta.get("lighting", "floodlight"),
            )

        # Load image
        img_path = os.path.join(self._folder_path, filename)
        self._canvas.set_image(img_path)

        # Set frame dimensions if not yet set
        if self._current_frame.image_width == 0 and self._canvas._pixmap:
            w = self._canvas._pixmap.width()
            h = self._canvas._pixmap.height()
            self._store.set_frame_dimensions(filename, w, h)
            self._current_frame.image_width = w
            self._current_frame.image_height = h

        # Load boxes
        self._canvas.set_boxes(self._current_frame.boxes)
        self._annotation_panel.update_boxes(self._current_frame.boxes)

        # Metadata inheritance: if frame is unviewed and we have previous metadata,
        # copy it to this frame so consecutive similar frames share metadata.
        if self._current_frame.status == FrameStatus.UNVIEWED and prev_meta:
            self._store.save_frame_metadata(filename, **prev_meta)
            for k, v in prev_meta.items():
                self._current_frame.metadata[k] = v

        # Set metadata bar from frame's dynamic metadata dict
        self._metadata_bar.set_metadata(**self._current_frame.metadata)

        # Update filmstrip selection
        self._filmstrip.select_row(row)

        # Mark in-progress
        if self._current_frame.status == FrameStatus.UNVIEWED:
            self._store.set_frame_status(filename, FrameStatus.IN_PROGRESS)
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

    def _on_filmstrip_select(self, filename: str):
        for i, f in enumerate(self._frames):
            if f["filename"] == filename:
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
        if not self._current_frame or not self._store or not self._current_filename:
            return
        self._save_metadata()
        display = value.replace("_", " ")
        self._toast.show_message(t("toast.auto_skip", display=display), "skip")
        self._store.set_frame_status(self._current_filename, FrameStatus.SKIPPED,
                                     skip_reason=value)
        self._frames[self._current_row]["status"] = "skipped"
        self._filmstrip.update_status(self._current_row, "skipped")
        QTimer.singleShot(400, self._advance_to_next_unviewed)

    def _save_metadata(self):
        if not self._current_frame or not self._store or not self._current_filename:
            return
        meta = self._metadata_bar.get_metadata()
        self._store.save_frame_metadata(self._current_filename, **meta)
        # Keep frame object in sync
        for k, v in meta.items():
            self._current_frame.metadata[k] = v

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
        if not self._pending_box or not self._current_frame or not self._current_filename:
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
            box_id = self._store.add_box(
                self._current_filename, x, y, w, h, category,
                jersey_number=jersey, player_name=name,
            )
        else:
            box_id = self._store.add_box(
                self._current_filename, x, y, w, h, category,
            )

        self._undo_stack.append((self._current_filename, box_id))
        self._reload_boxes()
        self._toast.show_message(t("toast.box_added_hint"), "success")

    # ── Occlusion / truncated ──

    def _set_occlusion(self, occ: Occlusion):
        idx = self._canvas.get_selected_index()
        if idx < 0 or not self._current_frame:
            # Apply to last added box
            if self._current_frame and self._current_frame.boxes:
                box = self._current_frame.boxes[-1]
                self._store.update_box(self._current_filename, box.id, occlusion=occ)
                self._reload_boxes()
            return
        box = self._current_frame.boxes[idx]
        self._store.update_box(self._current_filename, box.id, occlusion=occ)
        self._reload_boxes()

    def _toggle_truncated(self):
        idx = self._canvas.get_selected_index()
        if not self._current_frame or not self._current_filename:
            return
        if idx < 0:
            if self._current_frame.boxes:
                box = self._current_frame.boxes[-1]
                self._store.update_box(self._current_filename, box.id,
                                       truncated=not box.truncated)
                self._reload_boxes()
            return
        box = self._current_frame.boxes[idx]
        self._store.update_box(self._current_filename, box.id,
                               truncated=not box.truncated)
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
                self._store.update_box(self._current_filename, box.id,
                                       jersey_number=jersey, player_name=name)
                self._reload_boxes()

    def _on_box_moved(self, idx, x, y, w, h):
        if not self._current_frame or idx >= len(self._current_frame.boxes):
            return
        box = self._current_frame.boxes[idx]
        self._store.update_box(self._current_filename, box.id, x=x, y=y)
        self._reload_boxes()

    def _on_box_resized(self, idx, x, y, w, h):
        if not self._current_frame or idx >= len(self._current_frame.boxes):
            return
        box = self._current_frame.boxes[idx]
        self._store.update_box(self._current_filename, box.id,
                               x=x, y=y, width=w, height=h)
        self._reload_boxes()

    def _delete_selected_box(self):
        idx = self._canvas.get_selected_index()
        if idx < 0 or not self._current_frame or not self._current_filename:
            return
        box = self._current_frame.boxes[idx]
        self._store.delete_box(self._current_filename, box.id)
        self._canvas.clear_selection()
        self._reload_boxes()

    def _undo_last_box(self):
        if not self._undo_stack:
            return
        filename, box_id = self._undo_stack.pop()
        self._store.delete_box(filename, box_id)
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

        img_path = os.path.join(self._folder_path, self._current_filename)
        logger.info("Starting AI detection on: %s", img_path)
        self._detecting = True
        self._detecting_filename = self._current_filename

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
        if not self._current_filename or self._current_filename != self._detecting_filename:
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
                self._store.add_box(
                    self._current_filename, x, y, w, h, category,
                    source="ai_detected", box_status="finalized",
                    confidence=conf, detected_class=cls_name,
                )
            else:
                self._store.add_box(
                    self._current_filename, x, y, w, h, Category.OPPONENT,
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
            self._store.update_box(
                self._current_filename, box.id,
                category=category, box_status="finalized",
                jersey_number=jersey, player_name=name,
            )
        else:
            self._store.update_box(
                self._current_filename, box.id,
                category=category, box_status="finalized",
            )

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
        if self._annotation_mode != "ai_assisted" or not self._current_filename:
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

        count = self._store.bulk_assign_pending(
            self._current_filename, category, exclude_detected_class=exclude_cls,
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
        if self._annotation_mode != "ai_assisted" or not self._current_filename:
            return

        pending = self._store.get_pending_box_count(self._current_filename)
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
            count = self._store.bulk_assign_pending(
                self._current_filename, Category.OPPONENT,
            )
            self._reload_boxes()
            from backend.models import CATEGORY_NAMES
            cat_name = CATEGORY_NAMES.get(Category.OPPONENT, "Opponent")
            self._toast.show_message(
                t("ai.bulk_assigned", count=count, category=cat_name), "success",
            )

    def _re_detect(self):
        """Delete pending AI boxes and re-run detection."""
        if not self._current_filename or not self._model_manager or self._detecting:
            return
        self._store.delete_ai_pending_boxes(self._current_filename)
        self._reload_boxes()
        self._run_ai_detection()

    # ── Export / Skip ──

    def _export_and_advance(self):
        if not self._current_frame or not self._exporter or not self._current_filename:
            return

        # AI mode: block export if pending boxes remain
        if self._annotation_mode == "ai_assisted":
            pending = self._store.get_pending_box_count(self._current_filename)
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

        # Reload boxes from store
        self._current_frame.boxes = self._store.get_boxes(self._current_filename)

        exported = self._exporter.export_frame(self._current_frame, self._current_filename)
        self._store.set_frame_status(self._current_filename, FrameStatus.ANNOTATED)
        self._store.set_exported_filename(self._current_filename, exported)
        self._frames[self._current_row]["status"] = "annotated"
        self._filmstrip.update_status(self._current_row, "annotated")
        self._toast.show_message(t("toast.exported", exported=exported), "success")

        # Track stats + backup
        if self._session_stats:
            self._session_stats.finish_frame(was_annotated=True)
        self._notify_backup_on_save()

        self._update_progress()
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _skip_and_advance(self):
        if not self._current_filename or not self._store:
            return
        self._store.set_frame_status(self._current_filename, FrameStatus.SKIPPED,
                                     skip_reason="manual")
        self._frames[self._current_row]["status"] = "skipped"
        self._filmstrip.update_status(self._current_row, "skipped")
        self._toast.show_message(t("toast.frame_skipped"), "skip")

        # Track stats
        if self._session_stats:
            self._session_stats.finish_frame(was_annotated=False)
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _force_save(self):
        self._save_metadata()
        self._toast.show_message(t("toast.saved"), "info")

    # ── Helpers ──

    def _reload_boxes(self):
        if not self._current_filename or not self._store:
            return
        self._current_frame.boxes = self._store.get_boxes(self._current_filename)
        self._canvas.set_boxes(self._current_frame.boxes)
        self._annotation_panel.update_boxes(self._current_frame.boxes)

    def _update_progress(self):
        if not self._store:
            return
        stats = self._store.get_session_stats()
        # Include frames without JSON (brand new) as unviewed
        total_from_scan = len(self._frames)
        unviewed = total_from_scan - stats["total"] + stats.get("unviewed", 0)
        remaining = unviewed + stats.get("in_progress", 0)
        self._progress.update_progress(
            self._current_row + 1, total_from_scan,
            stats["annotated"], stats["skipped"], remaining,
        )

    def _show_completion_dialog(self):
        # Show the rich session summary dialog if stats available
        if self._session_stats:
            dialog = SessionSummaryDialog(self._session_stats, self)
            dialog.exec()
        else:
            output_path = os.path.join(self._folder_path, "output")
            stats = self._store.get_session_stats()
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

    # ── Collaboration ──

    def _open_collaboration_settings(self):
        """Open the Workflow Selection dialog."""
        from frontend.workflow_dialog import WorkflowSelectionDialog
        dialog = WorkflowSelectionDialog(
            current_workflow=self._workflow,
            current_annotator=self._annotator_name,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                old_workflow = self._workflow
                self._workflow = result["workflow"]
                self._annotator_name = result["annotator"]

                # Setup collaboration manager if we have a store
                if self._store and self._folder_path:
                    if not self._collab_manager:
                        self._collab_manager = CollaborationManager(
                            self._store, self._folder_path,
                        )
                    self._collab_manager.workflow = self._workflow
                    self._collab_manager.annotator = self._annotator_name

                # Handle workflow-specific setup
                self._on_workflow_changed(old_workflow)

    def _on_workflow_changed(self, old_workflow: str):
        """React to workflow change — show/hide UI, open setup dialogs."""
        self._update_menu_visibility()

        # Remove old workflow UI
        if old_workflow == "git" and self._git_toolbar:
            self._git_toolbar.stop_timers()
            self._git_toolbar.setParent(None)
            self._git_toolbar.deleteLater()
            self._git_toolbar = None

        if old_workflow == "shared_folder" and self._team_panel:
            self._team_panel.setParent(None)
            self._team_panel.deleteLater()
            self._team_panel = None

        # Setup new workflow UI
        if self._workflow == "solo":
            from frontend.workflow_dialog import SoloConfirmDialog
            SoloConfirmDialog(self).exec()

        elif self._workflow == "split_merge":
            self._toast.show_message("Split & Merge mode active. Use Project → Split Frames.", "info", 3000)

        elif self._workflow == "shared_folder":
            self._setup_shared_folder_workflow()

        elif self._workflow == "git":
            self._setup_git_workflow()

        elif self._workflow == "custom":
            from frontend.workflow_dialog import CustomWorkflowDialog
            dialog = CustomWorkflowDialog(
                project_dir=self._folder_path or "",
                parent=self,
            )
            dialog.exec()

        self._toast.show_message(
            f"Workflow: {self._workflow.replace('_', ' ').title()}", "success", 2000
        )

    def _setup_git_workflow(self):
        """Initialize Git workflow — show setup dialog if needed, add toolbar."""
        if not self._folder_path:
            return

        # Check if git is installed
        import subprocess, shutil
        if not shutil.which("git"):
            from frontend.git_dialogs import GitNotFoundDialog
            dialog = GitNotFoundDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._workflow = "solo"
                self._update_menu_visibility()
                return

        # Check if already a git repo
        project_root = Path(self._folder_path)
        is_git_repo = (project_root / ".git").exists()

        if not is_git_repo:
            from frontend.git_dialogs import GitSetupDialog
            dialog = GitSetupDialog(parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = dialog.get_result()
                if result:
                    self._annotator_name = result.get("name", self._annotator_name)
            else:
                # User cancelled — stay on previous workflow
                return

        # Add Git toolbar to the UI
        self._add_git_toolbar()

    def _add_git_toolbar(self):
        """Insert the Git toolbar into the main window layout."""
        if self._git_toolbar or not self._folder_path:
            return

        self._git_toolbar = GitToolbar(self._folder_path, self._annotator_name)
        self._git_toolbar.toast_message.connect(
            lambda msg, style, dur: self._toast.show_message(msg, style, dur)
        )

        # Insert after stats bar (or AI bar, or progress bar)
        central = self.centralWidget()
        root = central.layout()
        insert_idx = 1
        if self._annotation_mode == "ai_assisted":
            insert_idx = 2
        if self._stats_bar:
            insert_idx += 1
        root.insertWidget(insert_idx, self._git_toolbar)

    def _setup_shared_folder_workflow(self):
        """Initialize Shared Folder workflow — show setup dialog, add team panel."""
        from frontend.shared_folder_dialogs import SharedFolderSetupDialog
        dialog = SharedFolderSetupDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                self._annotator_name = result.get("annotator", self._annotator_name)
                if self._collab_manager:
                    self._collab_manager.annotator = self._annotator_name
                self._add_team_panel()

    def _add_team_panel(self):
        """Add the Team Panel to the main window for shared folder workflow."""
        if self._team_panel or not self._collab_manager:
            return
        try:
            from frontend.shared_folder_dialogs import TeamPanel
            self._team_panel = TeamPanel(self._collab_manager, self)
            # Insert into the middle layout (before filmstrip)
            central = self.centralWidget()
            root = central.layout()
            # Find the mid layout (index after progress/ai/stats bars)
            # The team panel works best as a floating dock or alongside filmstrip
            # For simplicity, add it to the left of the filmstrip area
            mid_layout = root.itemAt(root.count() - 2)  # The stretch layout before metadata
            if mid_layout and mid_layout.layout():
                mid_layout.layout().insertWidget(0, self._team_panel)
        except Exception as e:
            logger.error("Failed to add team panel: %s", e)

    def _open_split_dialog(self):
        """Open Split Setup dialog."""
        if not self._store or not self._folder_path:
            self._toast.show_message("Open a project first", "warning", 2000)
            return
        try:
            from frontend.split_merge_dialogs import SplitSetupDialog
            dialog = SplitSetupDialog(
                total_frames=len(self._frames),
                project_root=self._folder_path,
                parent=self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = dialog.get_result()
                if result and self._collab_manager:
                    members = result["members"]
                    annotators = [m["name"] for m in members]
                    filenames = [f["filename"] for f in self._frames]
                    assignments = self._collab_manager.split_frames(
                        filenames, annotators, strategy="contiguous"
                    )
                    self._toast.show_message(
                        f"Split {len(filenames)} frames among {len(annotators)} annotators",
                        "success", 3000,
                    )
        except ImportError as e:
            logger.error("Split dialog import error: %s", e)

    def _open_merge_dialog(self):
        """Open Merge dialog."""
        try:
            from frontend.split_merge_dialogs import MergeDialog
            dialog = MergeDialog(self)
            dialog.exec()
        except ImportError as e:
            logger.error("Merge dialog import error: %s", e)

    def _open_git_settings(self):
        """Open Git Settings dialog."""
        if not self._folder_path:
            return
        try:
            from frontend.git_dialogs import GitSettingsDialog
            dialog = GitSettingsDialog(
                project_path=self._folder_path,
                parent=self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = dialog.get_settings()
                if result:
                    name = result.get("name", self._annotator_name)
                    if name:
                        self._annotator_name = name
                    if self._git_toolbar:
                        self._git_toolbar.set_annotator(self._annotator_name)
                        self._git_toolbar.refresh_status()
        except (ImportError, Exception) as e:
            logger.error("Git settings error: %s", e)

    def _open_project_folder(self):
        """Open the project folder in the system file manager."""
        import subprocess, sys
        folder = self._folder_path or str(Path(__file__).parent.parent)
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", folder])
            elif sys.platform == "win32":
                subprocess.run(["explorer", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            logger.error("Failed to open folder: %s", e)

    def closeEvent(self, event):
        # Stop any running detection thread
        if self._detection_thread and self._detection_thread.isRunning():
            self._detection_thread.quit()
            self._detection_thread.wait(3000)
        # Stop backup timer
        if self._backup_timer:
            self._backup_timer.stop()
        # Stop git toolbar timers
        if self._git_toolbar:
            self._git_toolbar.stop_timers()
        # Create final backup on close
        if self._backup_manager:
            self._backup_manager.create_backup(reason="session_close")
        # Mark clean exit
        if self._state_db:
            self._state_db.save_clean_exit(True)
            self._state_db.close()
        super().closeEvent(event)
