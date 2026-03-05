import os

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QObject, QThread
from PyQt6.QtGui import QPixmap, QColor, QIcon, QPainter, QFont, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QHBoxLayout, QPushButton,
)

from backend.i18n import t
from backend.file_manager import FileManager

STATUS_COLORS = {
    "unviewed": QColor("#E0E0E0"),
    "annotated": QColor("#4A90D9"),
    "skipped": QColor("#D94A4A"),
    "in_progress": QColor("#D9C84A"),
}

SEQ_PURPOSE_COLORS = {
    "annotation_context": QColor("#F5A623"),
    "reid_training": QColor("#3498DB"),
}

THUMB_WIDTH = 100
THUMB_HEIGHT = 56


# ---------------------------------------------------------------------------
# Placeholder pixmap (lazy-init singleton)
# ---------------------------------------------------------------------------

_PLACEHOLDER_PIXMAP: QPixmap | None = None


def _get_placeholder() -> QPixmap:
    """Return a reusable grey placeholder thumbnail."""
    global _PLACEHOLDER_PIXMAP
    if _PLACEHOLDER_PIXMAP is None:
        _PLACEHOLDER_PIXMAP = QPixmap(THUMB_WIDTH, THUMB_HEIGHT)
        _PLACEHOLDER_PIXMAP.fill(QColor("#3A3A3A"))
    return _PLACEHOLDER_PIXMAP


# ---------------------------------------------------------------------------
# Background thumbnail loader (runs on QThread)
# ---------------------------------------------------------------------------

class _ThumbnailLoader(QObject):
    """Loads and scales thumbnail images on a background thread.

    Uses QImage (thread-safe) for loading/scaling.  Results are emitted in
    batches so the main thread can update the UI progressively.
    """
    batch_ready = pyqtSignal(list)   # list of (filename, QImage) tuples
    finished = pyqtSignal()

    BATCH_SIZE = 20  # emit results every N images

    def __init__(self, requests: list[tuple[str, str]]):
        """
        Args:
            requests: list of (filename, full_path) pairs to load.
        """
        super().__init__()
        self._requests = requests
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        batch: list[tuple[str, QImage]] = []
        for filename, full_path in self._requests:
            if self._cancelled:
                break
            img = QImage(full_path)
            if not img.isNull():
                img = img.scaled(
                    THUMB_WIDTH, THUMB_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            batch.append((filename, img))
            if len(batch) >= self.BATCH_SIZE:
                self.batch_ready.emit(batch)
                batch = []
        if batch and not self._cancelled:
            self.batch_ready.emit(batch)
        self.finished.emit()


# ---------------------------------------------------------------------------
# Filmstrip widget
# ---------------------------------------------------------------------------

class Filmstrip(QWidget):
    frame_selected = pyqtSignal(str)  # emits filename (was int DB id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._count_label = QLabel(t("filmstrip.frame_count", count=0))
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setStyleSheet("color: #CCC; font-weight: bold;")
        layout.addWidget(self._count_label)

        # Sequence toggle buttons
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(2)

        self._btn_all = QPushButton("All")
        self._btn_all.setFixedHeight(22)
        self._btn_all.setCheckable(True)
        self._btn_all.setChecked(True)
        self._btn_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_all.clicked.connect(lambda: self._set_view_mode("all"))
        toggle_row.addWidget(self._btn_all)

        self._btn_sequences = QPushButton("Sequences")
        self._btn_sequences.setFixedHeight(22)
        self._btn_sequences.setCheckable(True)
        self._btn_sequences.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_sequences.clicked.connect(lambda: self._set_view_mode("sequences"))
        toggle_row.addWidget(self._btn_sequences)

        layout.addLayout(toggle_row)

        self._btn_all.setStyleSheet("""
            QPushButton { background: #3A3A4A; color: #CCC; border: none;
                          border-radius: 3px; font-size: 10px; padding: 2px 6px; }
            QPushButton:checked { background: #F5A623; color: #1E1E1E; font-weight: bold; }
        """)
        self._btn_sequences.setStyleSheet("""
            QPushButton { background: #3A3A4A; color: #CCC; border: none;
                          border-radius: 3px; font-size: 10px; padding: 2px 6px; }
            QPushButton:checked { background: #F5A623; color: #1E1E1E; font-weight: bold; }
            QPushButton:disabled { background: #2A2A2A; color: #555; }
        """)

        self._list = QListWidget()
        self._list.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self._list.setSpacing(2)
        self._list.setStyleSheet("""
            QListWidget { background: #2A2A2A; border: none; }
            QListWidget::item { padding: 2px; border-radius: 3px; }
            QListWidget::item:selected { border: 2px solid #FFA500; }
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list)

        self._filenames: list[str] = []
        self._original_pixmaps: list[QPixmap] = []  # store originals for dot overlay
        self._view_mode: str = "all"  # "all" or "sequences"
        self._all_frames: list[dict] = []  # stored frames for rebuild
        self._all_folder_path: str = ""
        self._frame_metadata: dict[str, dict] = {}
        self._sequences: dict[str, list[dict]] = {}  # seq_id -> [frame dicts]
        self._collapsed: set[str] = set()  # collapsed sequence IDs
        self._ungrouped_collapsed: bool = True  # ungrouped section collapsed by default

        # -- Performance: thumbnail cache & async loader --
        self._thumbnail_cache: dict[str, QPixmap] = {}  # filename -> scaled QPixmap
        self._loader_thread: QThread | None = None
        self._loader_worker: _ThumbnailLoader | None = None
        self._dot_colors: dict[int, QColor | None] = {}  # frame_row -> pending dot color

        self.destroyed.connect(self._cancel_thumbnail_load)

    # ── Public API ──────────────────────────────────────────────────────────

    def load_frames(self, frames: list[dict], folder_path: str,
                    frame_metadata: dict[str, dict] | None = None):
        """Load frames into the filmstrip.  Thumbnails are loaded asynchronously
        in a background thread; the list populates instantly with placeholders."""
        # Cancel any in-progress background load
        self._cancel_thumbnail_load()

        # Clear cache if folder changed (new session / new bundle)
        if folder_path != self._all_folder_path:
            self._thumbnail_cache.clear()

        self._all_frames = list(frames)
        self._all_folder_path = folder_path
        self._frame_metadata = frame_metadata or {}
        self._dot_colors.clear()

        self._list.blockSignals(True)
        self._list.clear()
        self._filenames.clear()
        self._original_pixmaps.clear()

        to_load: list[tuple[str, str]] = []
        placeholder = _get_placeholder()

        # Track priority groups for section dividers
        current_group = None
        group_counts: dict[int, int] = {}
        if frame_metadata:
            for f in frames:
                g = f.get("priority_group")
                if g is not None:
                    group_counts[g] = group_counts.get(g, 0) + 1

        for f in frames:
            filename = f.get("original_filename") or f.get("filename", "")

            # Insert section divider if priority group changed
            priority_group = f.get("priority_group")
            if frame_metadata and priority_group is not None and priority_group != current_group:
                current_group = priority_group
                self._add_divider_item(priority_group, group_counts.get(priority_group, 0))

            item = self._make_frame_item(filename, f)

            # Thumbnail: cache check
            cached = self._thumbnail_cache.get(filename)
            if cached is not None:
                self._original_pixmaps.append(QPixmap(cached))
                item.setIcon(QIcon(cached))
            else:
                self._original_pixmaps.append(QPixmap())  # empty — filled by async loader
                item.setIcon(QIcon(placeholder))
                to_load.append((filename, os.path.join(folder_path, filename)))

            item.setSizeHint(QSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 24))
            self._list.addItem(item)
            self._filenames.append(filename)

        self._count_label.setText(t("filmstrip.frame_count", count=len(frames)))
        self._list.blockSignals(False)

        # Build sequence groups from frame_metadata
        self._sequences.clear()
        if frame_metadata:
            for f in frames:
                fname = f.get("original_filename") or f.get("filename", "")
                meta = frame_metadata.get(fname, {})
                seq_id = meta.get("sequence_id")
                if seq_id:
                    if seq_id not in self._sequences:
                        self._sequences[seq_id] = []
                    entry = dict(f)
                    entry["_seq_meta"] = meta
                    self._sequences[seq_id].append(entry)

        # Update Sequences button state
        self._btn_sequences.setEnabled(bool(self._sequences))
        if not self._sequences:
            self._btn_sequences.setToolTip("No sequence data available.")
        else:
            self._btn_sequences.setToolTip("")

        # Dispatch background loading for uncached thumbnails
        if to_load:
            self._start_thumbnail_load(to_load)

    def select_row(self, row: int):
        list_row = self._frame_row_to_list_row(row)
        self._list.blockSignals(True)
        self._list.setCurrentRow(list_row)
        self._list.blockSignals(False)
        item = self._list.item(list_row)
        if item:
            self._list.scrollToItem(item)

    def update_status(self, row: int, status: str):
        list_row = self._frame_row_to_list_row(row)
        item = self._list.item(list_row)
        if item:
            bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
            item.setBackground(bg)

    def update_dot(self, row: int, dot_color: QColor = None):
        """Paint a colored status dot on the thumbnail at the given row."""
        # Track dot color so it can be re-applied when async thumbnail arrives
        self._dot_colors[row] = dot_color

        if row < 0 or row >= len(self._original_pixmaps):
            return
        list_row = self._frame_row_to_list_row(row)
        item = self._list.item(list_row)
        if not item:
            return
        orig = self._original_pixmaps[row]
        if orig.isNull():
            return
        pix = QPixmap(orig)  # copy original
        if dot_color:
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(dot_color)
            p.setPen(Qt.PenStyle.NoPen)
            dot_size = 10
            p.drawEllipse(pix.width() - dot_size - 3, 3, dot_size, dot_size)
            p.end()
        item.setIcon(QIcon(pix))

    def set_current_highlight(self, row: int):
        # Highlight current row as in-progress (yellow)
        list_row = self._frame_row_to_list_row(row)
        item = self._list.item(list_row)
        if item:
            item.setBackground(STATUS_COLORS["in_progress"])

    def get_filename(self, row: int) -> str:
        if 0 <= row < len(self._filenames):
            return self._filenames[row]
        return ""

    def current_row(self) -> int:
        """Return current frame index (not list widget row)."""
        list_row = self._list.currentRow()
        frame_row = self._list_row_to_frame_row(list_row)
        return frame_row if frame_row >= 0 else 0

    def count(self) -> int:
        """Return number of frames (not including dividers)."""
        return len(self._filenames)

    def scroll_to_sequence_header(self, sequence_id: str) -> bool:
        """Scroll to a sequence header in the list. Returns True if found."""
        target = f"__seq_header__{sequence_id}"
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == target:
                self._list.scrollToItem(item)
                return True
        return False

    def remove_frame(self, frame_row: int):
        """Remove a frame from the filmstrip by frame index.

        Updates the list widget, internal filename list, pixmap list,
        dot-colors dict, thumbnail cache, and the stored _all_frames list.
        """
        if frame_row < 0 or frame_row >= len(self._filenames):
            return

        filename = self._filenames[frame_row]

        # Remove from list widget
        list_row = self._frame_row_to_list_row(frame_row)
        self._list.blockSignals(True)
        item = self._list.takeItem(list_row)
        del item
        self._list.blockSignals(False)

        # Remove from internal lists
        self._filenames.pop(frame_row)
        if frame_row < len(self._original_pixmaps):
            self._original_pixmaps.pop(frame_row)

        # Remove from dot colors (shift indices above the removed row)
        new_dots: dict[int, QColor | None] = {}
        for idx, color in self._dot_colors.items():
            if idx < frame_row:
                new_dots[idx] = color
            elif idx > frame_row:
                new_dots[idx - 1] = color
        self._dot_colors = new_dots

        # Remove from _all_frames
        self._all_frames = [f for f in self._all_frames
                            if (f.get("original_filename") or f.get("filename", "")) != filename]

        # Remove from sequences
        for seq_id in list(self._sequences.keys()):
            self._sequences[seq_id] = [
                sf for sf in self._sequences[seq_id]
                if (sf.get("original_filename") or sf.get("filename", "")) != filename
            ]
            if not self._sequences[seq_id]:
                del self._sequences[seq_id]

        # Remove from thumbnail cache
        self._thumbnail_cache.pop(filename, None)

        # Update count label
        self._count_label.setText(t("filmstrip.frame_count", count=len(self._filenames)))

        # Update Sequences button state
        self._btn_sequences.setEnabled(bool(self._sequences))

    # ── Row conversion helpers ──────────────────────────────────────────────

    def _frame_row_to_list_row(self, frame_row: int) -> int:
        """Convert a frame index (0-based in self._filenames) to a list widget row,
        accounting for divider items inserted in the list."""
        if frame_row < 0 or frame_row >= len(self._filenames):
            return frame_row
        target_fname = self._filenames[frame_row]
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == target_fname:
                return i
        return frame_row  # fallback

    def _list_row_to_frame_row(self, list_row: int) -> int:
        """Convert a list widget row to a frame index, skipping dividers."""
        item = self._list.item(list_row)
        if not item:
            return -1
        fname = item.data(Qt.ItemDataRole.UserRole)
        if fname == "__divider__" or fname is None:
            return -1
        try:
            return self._filenames.index(fname)
        except ValueError:
            return -1

    # ── View mode switching ─────────────────────────────────────────────────

    def _set_view_mode(self, mode: str):
        """Switch between 'all' and 'sequences' view."""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._btn_all.setChecked(mode == "all")
        self._btn_sequences.setChecked(mode == "sequences")
        if mode == "all":
            self._build_all_view()
        else:
            self._build_sequence_view()

    def _on_row_changed(self, list_row: int):
        item = self._list.item(list_row)
        if not item:
            return
        fname = item.data(Qt.ItemDataRole.UserRole)
        # Skip divider items — jump to next real frame
        if fname == "__divider__" or fname is None:
            if list_row + 1 < self._list.count():
                self._list.blockSignals(True)
                self._list.setCurrentRow(list_row + 1)
                self._list.blockSignals(False)
                self._on_row_changed(list_row + 1)
            return
        # Handle sequence header clicks — toggle collapse
        if isinstance(fname, str) and fname.startswith("__seq_header__"):
            seq_id = fname[len("__seq_header__"):]
            if seq_id == "ungrouped":
                self._ungrouped_collapsed = not self._ungrouped_collapsed
            elif seq_id in self._collapsed:
                self._collapsed.discard(seq_id)
            else:
                self._collapsed.add(seq_id)
            if self._view_mode == "sequences":
                self._build_sequence_view()
            return
        if fname in self._filenames:
            self.frame_selected.emit(fname)

    # ── Build "All" view (uses cache, no disk I/O) ─────────────────────────

    def _build_all_view(self):
        """Rebuild the 'all frames' view using cached thumbnails.

        This avoids re-reading metadata and re-parsing sequences — those
        are already stored in self._all_frames, self._frame_metadata, etc.
        """
        self._cancel_thumbnail_load()

        self._list.blockSignals(True)
        self._list.clear()
        self._filenames.clear()
        self._original_pixmaps.clear()
        self._dot_colors.clear()

        to_load: list[tuple[str, str]] = []
        placeholder = _get_placeholder()

        current_group = None
        group_counts: dict[int, int] = {}
        if self._frame_metadata:
            for f in self._all_frames:
                g = f.get("priority_group")
                if g is not None:
                    group_counts[g] = group_counts.get(g, 0) + 1

        for f in self._all_frames:
            filename = f.get("original_filename") or f.get("filename", "")

            priority_group = f.get("priority_group")
            if self._frame_metadata and priority_group is not None and priority_group != current_group:
                current_group = priority_group
                self._add_divider_item(priority_group, group_counts.get(priority_group, 0))

            item = self._make_frame_item(filename, f)

            cached = self._thumbnail_cache.get(filename)
            if cached is not None:
                self._original_pixmaps.append(QPixmap(cached))
                item.setIcon(QIcon(cached))
            else:
                self._original_pixmaps.append(QPixmap())
                item.setIcon(QIcon(placeholder))
                to_load.append((filename, os.path.join(self._all_folder_path, filename)))

            item.setSizeHint(QSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 24))
            self._list.addItem(item)
            self._filenames.append(filename)

        self._count_label.setText(t("filmstrip.frame_count", count=len(self._filenames)))
        self._list.blockSignals(False)

        if to_load:
            self._start_thumbnail_load(to_load)

    # ── Build "Sequences" view (uses cache, no disk I/O) ───────────────────

    def _build_sequence_view(self):
        """Build the filmstrip with sequence grouping."""
        self._cancel_thumbnail_load()

        self._list.blockSignals(True)
        self._list.clear()
        self._filenames.clear()
        self._original_pixmaps.clear()
        self._dot_colors.clear()

        to_load: list[tuple[str, str]] = []
        grouped_fnames: set[str] = set()

        # Sort sequences by first frame's video_time
        sorted_seqs = sorted(
            self._sequences.items(),
            key=lambda kv: kv[1][0].get("_seq_meta", {}).get("video_time", 99999),
        )

        for seq_id, seq_frames in sorted_seqs:
            meta0 = seq_frames[0].get("_seq_meta", {})
            purpose = meta0.get("sequence_purpose", "")
            border_color = SEQ_PURPOSE_COLORS.get(purpose, QColor("#888"))
            collapsed = seq_id in self._collapsed
            arrow = "\u25b8" if collapsed else "\u25be"

            # Sequence header
            header_text = f"{arrow} {seq_id} ({len(seq_frames)}fr)"
            header = QListWidgetItem(header_text)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            header.setForeground(border_color)
            header.setBackground(QColor("#1A1A2A"))
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            header.setFont(font)
            header.setSizeHint(QSize(THUMB_WIDTH + 20, 22))
            header.setData(Qt.ItemDataRole.UserRole, f"__seq_header__{seq_id}")
            self._list.addItem(header)

            if not collapsed:
                for sf in seq_frames:
                    fname = sf.get("original_filename") or sf.get("filename", "")
                    grouped_fnames.add(fname)
                    self._add_frame_item(fname, sf, self._all_folder_path, to_load)
            else:
                for sf in seq_frames:
                    fname = sf.get("original_filename") or sf.get("filename", "")
                    grouped_fnames.add(fname)

        # Ungrouped frames
        ungrouped = [f for f in self._all_frames
                     if (f.get("original_filename") or f.get("filename", ""))
                     not in grouped_fnames]
        if ungrouped:
            arrow = "\u25b8" if self._ungrouped_collapsed else "\u25be"
            header_text = f"\u2014 Ungrouped ({len(ungrouped)}fr) \u2014"
            header = QListWidgetItem(header_text)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setForeground(QColor("#888"))
            header.setBackground(QColor("#1A1A2A"))
            font = QFont()
            font.setPointSize(8)
            font.setItalic(True)
            header.setFont(font)
            header.setSizeHint(QSize(THUMB_WIDTH + 20, 18))
            header.setData(Qt.ItemDataRole.UserRole, "__seq_header__ungrouped")
            self._list.addItem(header)

            if not self._ungrouped_collapsed:
                for f in ungrouped:
                    fname = f.get("original_filename") or f.get("filename", "")
                    self._add_frame_item(fname, f, self._all_folder_path, to_load)

        self._count_label.setText(t("filmstrip.frame_count", count=len(self._filenames)))
        self._list.blockSignals(False)

        if to_load:
            self._start_thumbnail_load(to_load)

    # ── Item creation helpers ───────────────────────────────────────────────

    def _add_divider_item(self, priority_group: int, count: int):
        """Insert a non-selectable priority-group divider into the list."""
        label = FileManager.get_priority_group_label(priority_group)
        divider = QListWidgetItem(f"\u2014 {label} ({count}) \u2014")
        divider.setFlags(Qt.ItemFlag.NoItemFlags)
        divider.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        divider.setForeground(QColor("#8888A0"))
        divider.setBackground(QColor("#1A1A2A"))
        font = QFont()
        font.setPointSize(8)
        font.setItalic(True)
        divider.setFont(font)
        divider.setSizeHint(QSize(THUMB_WIDTH + 20, 18))
        divider.setData(Qt.ItemDataRole.UserRole, "__divider__")
        self._list.addItem(divider)

    def _make_frame_item(self, filename: str, frame_data: dict) -> QListWidgetItem:
        """Create a QListWidgetItem with text, tooltip, and background color.

        Does NOT set the icon or add it to the list — caller handles that.
        """
        item = QListWidgetItem()
        item.setText(filename)
        item.setForeground(QColor("#EEE"))
        status = frame_data.get("status", "unviewed")
        bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
        item.setBackground(bg)

        meta = self._frame_metadata.get(filename, {})
        video_time = meta.get("video_time")
        if video_time is not None:
            time_str = FileManager.format_video_time(video_time)
            item.setToolTip(f"{filename} \u2014 {time_str}")
        else:
            item.setToolTip(filename)

        item.setData(Qt.ItemDataRole.UserRole, filename)
        return item

    def _add_frame_item(self, filename: str, frame_data: dict, folder_path: str,
                        to_load: list[tuple[str, str]] | None = None):
        """Add a single frame item to the list widget, using the thumbnail cache."""
        item = self._make_frame_item(filename, frame_data)

        cached = self._thumbnail_cache.get(filename)
        if cached is not None:
            self._original_pixmaps.append(QPixmap(cached))
            item.setIcon(QIcon(cached))
        else:
            self._original_pixmaps.append(QPixmap())
            item.setIcon(QIcon(_get_placeholder()))
            if to_load is not None:
                to_load.append((filename, os.path.join(folder_path, filename)))
            else:
                # Synchronous fallback (safety net — should rarely run)
                pix = QPixmap(os.path.join(folder_path, filename))
                if not pix.isNull():
                    pix = pix.scaled(THUMB_WIDTH, THUMB_HEIGHT,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    self._thumbnail_cache[filename] = pix
                    self._original_pixmaps[-1] = QPixmap(pix)
                    item.setIcon(QIcon(pix))

        item.setSizeHint(QSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 24))
        self._list.addItem(item)
        self._filenames.append(filename)

    # ── Background thumbnail loading ────────────────────────────────────────

    def _start_thumbnail_load(self, requests: list[tuple[str, str]]):
        """Start background loading for uncached thumbnails."""
        self._loader_thread = QThread()
        self._loader_worker = _ThumbnailLoader(requests)
        self._loader_worker.moveToThread(self._loader_thread)

        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.batch_ready.connect(self._on_thumbnails_ready)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_thread.finished.connect(self._cleanup_loader)

        self._loader_thread.start()

    def _cancel_thumbnail_load(self):
        """Cancel any in-progress background thumbnail loading.

        Ensures the background thread is fully stopped before any
        objects are deleted, preventing 'QThread: Destroyed while
        thread is still running' crashes.
        """
        if self._loader_worker:
            self._loader_worker.cancel()

        if self._loader_thread is None:
            self._loader_worker = None  # safety
            return

        # Disconnect ALL signals FIRST to prevent:
        #  - batch_ready arriving during teardown
        #  - finished -> quit -> finished cascade
        #  - _cleanup_loader being called a second time via thread.finished
        try:
            self._loader_worker.batch_ready.disconnect(self._on_thumbnails_ready)
        except (TypeError, RuntimeError):
            pass
        try:
            self._loader_worker.finished.disconnect(self._loader_thread.quit)
        except (TypeError, RuntimeError):
            pass
        try:
            self._loader_thread.finished.disconnect(self._cleanup_loader)
        except (TypeError, RuntimeError):
            pass

        if self._loader_thread.isRunning():
            self._loader_thread.quit()
            # Worker checks cancel flag between each image load (~100-500ms
            # per image).  Block until fully stopped to guarantee safe
            # deletion.  In practice this returns almost instantly once
            # the current QImage load finishes.
            if not self._loader_thread.wait(10000):  # 10s generous safety timeout
                # Extremely unlikely — thread stuck in I/O.  Leak rather than crash.
                self._loader_worker = None
                self._loader_thread = None
                return

        # Thread is guaranteed stopped — safe to schedule deletion
        self._loader_worker.deleteLater()
        self._loader_worker = None
        self._loader_thread.deleteLater()
        self._loader_thread = None

    def _cleanup_loader(self):
        """Clean up loader after *natural* completion (all images loaded).

        Only called via ``_loader_thread.finished`` signal — never during
        an explicit cancel (``_cancel_thumbnail_load`` disconnects the
        signal before cleanup).
        """
        if self._loader_worker:
            self._loader_worker.deleteLater()
            self._loader_worker = None
        if self._loader_thread:
            self._loader_thread.deleteLater()
            self._loader_thread = None

    def _on_thumbnails_ready(self, batch: list):
        """Receive a batch of loaded thumbnails from the background thread.

        Converts QImage -> QPixmap (must happen on main thread) and updates
        the list widget items.
        """
        for filename, qimage in batch:
            if qimage.isNull():
                continue

            # Convert QImage -> QPixmap on the main thread
            pix = QPixmap.fromImage(qimage)

            # Store in persistent cache
            self._thumbnail_cache[filename] = pix

            # Update the list item icon if this filename is currently displayed
            if filename not in self._filenames:
                continue

            # Find ALL occurrences of this filename (in case of duplicates)
            for frame_idx, fn in enumerate(self._filenames):
                if fn != filename:
                    continue

                list_row = self._frame_row_to_list_row(frame_idx)
                item = self._list.item(list_row)
                if item:
                    item.setIcon(QIcon(pix))

                # Update _original_pixmaps for dot overlay support
                if 0 <= frame_idx < len(self._original_pixmaps):
                    self._original_pixmaps[frame_idx] = QPixmap(pix)

                # Re-apply any pending dot color
                if frame_idx in self._dot_colors and self._dot_colors[frame_idx] is not None:
                    self.update_dot(frame_idx, self._dot_colors[frame_idx])
