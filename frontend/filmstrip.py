from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QColor, QIcon, QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
)

from backend.i18n import t

STATUS_COLORS = {
    "unviewed": QColor("#E0E0E0"),
    "annotated": QColor("#4A90D9"),
    "skipped": QColor("#D94A4A"),
    "in_progress": QColor("#D9C84A"),
}

THUMB_WIDTH = 100
THUMB_HEIGHT = 56


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

    def load_frames(self, frames: list[dict], folder_path: str):
        self._list.blockSignals(True)
        self._list.clear()
        self._filenames.clear()
        self._original_pixmaps.clear()

        for f in frames:
            item = QListWidgetItem()
            filename = f.get("original_filename") or f.get("filename", "")
            item.setText(filename)
            item.setForeground(QColor("#EEE"))
            status = f.get("status", "unviewed")
            bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
            item.setBackground(bg)

            # Load thumbnail
            import os
            img_path = os.path.join(folder_path, filename)
            pix = QPixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(THUMB_WIDTH, THUMB_HEIGHT,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                self._original_pixmaps.append(QPixmap(pix))  # store a copy
                item.setIcon(QIcon(pix))
            else:
                self._original_pixmaps.append(QPixmap())

            item.setSizeHint(QSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 24))
            self._list.addItem(item)
            self._filenames.append(filename)

        self._count_label.setText(t("filmstrip.frame_count", count=len(frames)))
        self._list.blockSignals(False)

    def select_row(self, row: int):
        self._list.blockSignals(True)
        self._list.setCurrentRow(row)
        self._list.blockSignals(False)
        item = self._list.item(row)
        if item:
            self._list.scrollToItem(item)

    def update_status(self, row: int, status: str):
        item = self._list.item(row)
        if item:
            bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
            item.setBackground(bg)

    def update_dot(self, row: int, dot_color: QColor = None):
        """Paint a colored status dot on the thumbnail at the given row."""
        if row < 0 or row >= len(self._original_pixmaps):
            return
        item = self._list.item(row)
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
        for i in range(self._list.count()):
            item = self._list.item(i)
            if i == row:
                item.setBackground(STATUS_COLORS["in_progress"])

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._filenames):
            self.frame_selected.emit(self._filenames[row])

    def get_filename(self, row: int) -> str:
        if 0 <= row < len(self._filenames):
            return self._filenames[row]
        return ""

    def current_row(self) -> int:
        return self._list.currentRow()

    def count(self) -> int:
        return self._list.count()
