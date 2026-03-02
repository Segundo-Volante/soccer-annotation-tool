from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QColor, QIcon
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
    frame_selected = pyqtSignal(int)  # emits frame DB id

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

        self._frame_ids: list[int] = []

    def load_frames(self, frames: list[dict], folder_path: str):
        self._list.blockSignals(True)
        self._list.clear()
        self._frame_ids.clear()

        for f in frames:
            item = QListWidgetItem()
            item.setText(f["original_filename"])
            item.setForeground(QColor("#EEE"))
            status = f.get("status", "unviewed")
            bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
            item.setBackground(bg)

            # Load thumbnail
            import os
            img_path = os.path.join(folder_path, f["original_filename"])
            pix = QPixmap(img_path)
            if not pix.isNull():
                pix = pix.scaled(THUMB_WIDTH, THUMB_HEIGHT,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                item.setIcon(QIcon(pix))

            item.setSizeHint(QSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 24))
            self._list.addItem(item)
            self._frame_ids.append(f["id"])

        self._count_label.setText(t("filmstrip.frame_count", count=len(frames)))
        self._list.blockSignals(False)

    def select_row(self, row: int):
        self._list.blockSignals(True)
        self._list.setCurrentRow(row)
        self._list.blockSignals(False)
        self._list.scrollToItem(self._list.item(row))

    def update_status(self, row: int, status: str):
        item = self._list.item(row)
        if item:
            bg = STATUS_COLORS.get(status, STATUS_COLORS["unviewed"])
            item.setBackground(bg)

    def set_current_highlight(self, row: int):
        # Highlight current row as in-progress (yellow)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if i == row:
                item.setBackground(STATUS_COLORS["in_progress"])

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._frame_ids):
            self.frame_selected.emit(self._frame_ids[row])

    def get_frame_id(self, row: int) -> int:
        if 0 <= row < len(self._frame_ids):
            return self._frame_ids[row]
        return -1

    def current_row(self) -> int:
        return self._list.currentRow()

    def count(self) -> int:
        return self._list.count()
