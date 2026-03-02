import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QMessageBox, QApplication, QDialog,
)

from backend.database import DatabaseManager
from backend.exporter import Exporter
from backend.file_manager import FileManager
from backend.models import (
    BoundingBox, Category, FrameAnnotation, FrameStatus,
    Occlusion, METADATA_KEYS,
)
from backend.roster_manager import RosterManager
from frontend.annotation_panel import AnnotationPanel
from frontend.canvas import AnnotationCanvas
from frontend.filmstrip import Filmstrip
from frontend.metadata_bar import MetadataBar
from frontend.player_popup import PlayerPopup
from frontend.progress_bar import ProgressBarWidget
from frontend.session_dialog import SessionDialog
from frontend.shortcuts import ShortcutHandler
from frontend.toast import Toast


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Soccer Annotation Tool")
        self.setMinimumSize(1200, 700)
        self.resize(1600, 900)
        self.setStyleSheet("background: #1E1E1E;")

        # Backend
        self._db: Optional[DatabaseManager] = None
        self._roster: Optional[RosterManager] = None
        self._exporter: Optional[Exporter] = None

        # Session state
        self._session_id: Optional[int] = None
        self._folder_path: Optional[str] = None
        self._frames: list[dict] = []
        self._current_row: int = -1
        self._current_frame: Optional[FrameAnnotation] = None
        self._pending_box: Optional[tuple] = None  # (x, y, w, h) waiting for category
        self._undo_stack: list[int] = []  # box IDs for undo

        # Build UI
        self._build_ui()
        self._build_shortcuts()

        # Install app-level event filter so shortcuts work regardless of focus
        QApplication.instance().installEventFilter(self)

        # Show session dialog on start
        QTimer.singleShot(100, self._show_session_dialog)

    def eventFilter(self, obj, event):
        """Capture all key presses app-wide so shortcuts work even when
        buttons or other widgets have focus."""
        if event.type() == QEvent.Type.KeyPress:
            if self._shortcuts._popup_open:
                return False
            from PyQt6.QtWidgets import QLineEdit
            focused = QApplication.instance().focusWidget()
            if isinstance(focused, QLineEdit):
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

        self._canvas = AnnotationCanvas()
        self._canvas.box_drawn.connect(self._on_box_drawn)
        self._canvas.box_selected.connect(self._on_canvas_box_selected)
        self._canvas.box_deselected.connect(self._on_canvas_box_deselected)
        self._canvas.box_moved.connect(self._on_box_moved)
        self._canvas.box_resized.connect(self._on_box_resized)
        mid.addWidget(self._canvas, stretch=1)

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

    def keyPressEvent(self, event):
        if not self._shortcuts.handle_key(event):
            super().keyPressEvent(event)

    # ── Session management ──

    def _show_session_dialog(self):
        dialog = SessionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            # Load roster from selected CSV
            roster_path = result.get("roster", "")
            self._roster = RosterManager(roster_path if roster_path else None)
            self._start_session(
                result["folder"],
                result["source"],
                result["round"],
                result.get("opponent", ""),
                result.get("weather", "clear"),
                result.get("lighting", "floodlight"),
            )

    def _start_session(self, folder: str, source: str, match_round: str,
                       opponent: str = "", weather: str = "clear",
                       lighting: str = "floodlight"):
        self._folder_path = folder
        db_path = os.path.join(folder, "annotations.db")
        self._db = DatabaseManager(db_path)

        existing = self._db.find_session_by_folder(folder)
        if existing:
            self._session_id = existing
            self._db.get_session(existing)  # update last_opened
        else:
            self._session_id = self._db.create_session(
                folder, source, match_round, opponent, weather, lighting,
            )
            # Scan and add frames
            filenames = FileManager.scan_folder(folder)
            if not filenames:
                QMessageBox.warning(self, "Error", "No images found in the selected folder.")
                return
            for i, fname in enumerate(filenames):
                self._db.add_frame(self._session_id, fname, i)

        # Setup exporter
        output_path = os.path.join(folder, "output")
        self._exporter = Exporter(self._db, folder, output_path)

        # Load frames
        self._frames = self._db.get_session_frames(self._session_id)
        self._filmstrip.load_frames(self._frames, folder)

        self.setWindowTitle(f"Soccer Annotation Tool — {os.path.basename(folder)}")

        # Jump to first unviewed frame
        first_unviewed = 0
        for i, f in enumerate(self._frames):
            if f["status"] == "unviewed":
                first_unviewed = i
                break
        self._load_frame_at_row(first_unviewed)

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

        # Set metadata bar from frame
        self._metadata_bar.set_metadata(
            shot_type=self._current_frame.shot_type,
            camera_motion=self._current_frame.camera_motion,
            ball_status=self._current_frame.ball_status,
            game_situation=self._current_frame.game_situation,
            pitch_zone=self._current_frame.pitch_zone,
            frame_quality=self._current_frame.frame_quality,
        )

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
        """Route number key: pending box → category assignment, else → metadata option."""
        if self._pending_box and 1 <= n <= 6:
            categories = [
                Category.ATLETICO_PLAYER,
                Category.OPPONENT,
                Category.ATLETICO_GK,
                Category.OPPONENT_GK,
                Category.REFEREE,
                Category.BALL,
            ]
            self._assign_category(categories[n - 1])
        else:
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
        self._toast.show_message(f"Auto-skip: {display}", "skip")
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
        self._toast.show_message("Press 1-6 for category", "info", 3000)

    def _assign_category(self, category: Category):
        if not self._pending_box or not self._current_frame:
            return
        x, y, w, h = self._pending_box
        self._pending_box = None
        self._canvas.clear_pending_box()

        if category in (Category.ATLETICO_PLAYER, Category.ATLETICO_GK):
            popup = PlayerPopup(self._roster, self)
            self._shortcuts.set_popup_open(True)
            result = popup.exec()
            self._shortcuts.set_popup_open(False)
            if result != PlayerPopup.DialogCode.Accepted:
                self._toast.show_message("Box cancelled", "warning")
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
        self._toast.show_message("Box added — F/G/H occlusion, T truncated", "success")

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
        if box.category in (Category.ATLETICO_PLAYER, Category.ATLETICO_GK):
            popup = PlayerPopup(self._roster, self)
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

    # ── Export / Skip ──

    def _export_and_advance(self):
        if not self._current_frame or not self._exporter:
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
        self._toast.show_message(f"Exported: {exported}", "success")
        self._update_progress()
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _skip_and_advance(self):
        if not self._current_frame or not self._db:
            return
        self._db.set_frame_status(self._current_frame.id, FrameStatus.SKIPPED)
        self._frames[self._current_row]["status"] = "skipped"
        self._filmstrip.update_status(self._current_row, "skipped")
        self._toast.show_message("Frame skipped", "skip")
        QTimer.singleShot(300, self._advance_to_next_unviewed)

    def _force_save(self):
        self._save_metadata()
        self._toast.show_message("Saved", "info")

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
        msg.setWindowTitle("All Done!")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("All frames have been processed!")
        msg.setInformativeText(
            f"Annotated: {stats['annotated']}    Skipped: {stats['skipped']}\n\n"
            f"Output saved to:\n{output_path}\n\n"
            f"  frames/         — Clean renamed images\n"
            f"  annotations/  — COCO JSON per frame\n"
            f"  crops/            — Cropped player images\n"
            f"  coco_dataset.json  — Combined dataset\n"
            f"  summary.json           — Statistics"
        )
        msg.setStyleSheet("QMessageBox { background: #2A2A2A; } "
                          "QLabel { color: #EEE; font-size: 13px; }")
        msg.exec()

    def closeEvent(self, event):
        if self._db:
            self._db.close()
        super().closeEvent(event)
