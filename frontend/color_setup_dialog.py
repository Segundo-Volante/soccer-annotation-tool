"""Team Color Setup Dialog — click-to-sample team jersey colors.

Multi-step dialog shown at AI-Assisted session start. User clicks on
player jerseys in the first frame to sample home, away, and optionally
referee colors. Colors are used for automatic box classification.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QWheelEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QSizePolicy,
)

from backend.color_classifier import sample_jersey_color, DEFAULT_REFEREE_HSV

# ── Design tokens (match app theme) ──
_BG = "#1E1E2E"
_CARD = "#2A2A3C"
_BORDER = "#404060"
_TEXT = "#E8E8F0"
_MUTED = "#8888A0"
_ACCENT = "#F5A623"
_HOME_COLOR = "#E74C3C"
_AWAY_COLOR = "#3498DB"
_REF_COLOR = "#F1C40F"

_STYLE = f"""
    QDialog {{
        background: {_BG};
    }}
    QLabel {{
        color: {_TEXT};
        border: none;
    }}
    QPushButton {{
        background: {_CARD}; color: {_TEXT}; padding: 8px 18px;
        border-radius: 6px; border: 1px solid {_BORDER};
        font-size: 12px; font-weight: bold;
    }}
    QPushButton:hover {{
        background: #33334C; border-color: {_ACCENT};
    }}
"""


class ZoomableImageWidget(QWidget):
    """Image display widget with scroll-to-zoom and space+drag panning."""

    clicked = pyqtSignal(int, int)  # image-space x, y

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background: #111122; border: 1px solid {_BORDER};")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap = QPixmap(image_path)
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._panning = False
        self._pan_start = QPoint()
        self._space_held = False

        # Fit image initially
        self._fit_to_widget()

    def _fit_to_widget(self):
        if self._pixmap.isNull():
            return
        w_ratio = self.width() / self._pixmap.width()
        h_ratio = self.height() / self._pixmap.height()
        self._scale = min(w_ratio, h_ratio) * 0.95
        # Center
        sw = self._pixmap.width() * self._scale
        sh = self._pixmap.height() * self._scale
        self._offset = QPointF(
            (self.width() - sw) / 2,
            (self.height() - sh) / 2,
        )

    def resizeEvent(self, event):
        self._fit_to_widget()
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def wheelEvent(self, event: QWheelEvent):
        """Scroll wheel zoom centered on cursor."""
        old_scale = self._scale
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_scale = max(0.1, min(old_scale * factor, 10.0))

        # Zoom centered on cursor position
        cursor_pos = event.position()
        # Image point under cursor before zoom
        img_x = (cursor_pos.x() - self._offset.x()) / old_scale
        img_y = (cursor_pos.y() - self._offset.y()) / old_scale

        self._scale = new_scale

        # Adjust offset so the same image point stays under cursor
        self._offset = QPointF(
            cursor_pos.x() - img_x * new_scale,
            cursor_pos.y() - img_y * new_scale,
        )
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_held = False
            self.setCursor(Qt.CursorShape.CrossCursor)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._space_held:
                self._panning = True
                self._pan_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                # Convert click to image coordinates
                img_x = (event.position().x() - self._offset.x()) / self._scale
                img_y = (event.position().y() - self._offset.y()) / self._scale
                if (0 <= img_x < self._pixmap.width() and
                        0 <= img_y < self._pixmap.height()):
                    self.clicked.emit(int(img_x), int(img_y))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._offset += QPointF(delta.x(), delta.y())
            self._pan_start = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._space_held
                else Qt.CursorShape.CrossCursor
            )
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._fit_to_widget()


class _SamplingPage(QWidget):
    """One step in the color sampling flow (Home / Away / Referee)."""

    color_confirmed = pyqtSignal(np.ndarray, str)  # hsv, color_name
    skipped = pyqtSignal()

    def __init__(self, image_path: str, team_label: str, team_color: str,
                 allow_skip: bool = False, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._team_label = team_label
        self._team_color = team_color
        self._allow_skip = allow_skip
        self._sampled_hsv: Optional[np.ndarray] = None
        self._image_bgr: Optional[np.ndarray] = None

        # Load BGR for sampling
        self._image_bgr = cv2.imread(image_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Instruction
        self._instruction = QLabel(
            f"Click on a <b style='color:{team_color}'>{team_label}</b> "
            f"player's jersey to sample their color"
        )
        self._instruction.setStyleSheet(f"color: {_TEXT}; font-size: 14px;")
        self._instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._instruction)

        # Zoomable image
        self._image_widget = ZoomableImageWidget(image_path)
        self._image_widget.clicked.connect(self._on_click)
        layout.addWidget(self._image_widget, stretch=1)

        # Result row (swatch + color name)
        result_row = QHBoxLayout()
        result_row.setSpacing(10)

        self._swatch = QLabel()
        self._swatch.setFixedSize(40, 40)
        self._swatch.setStyleSheet(
            f"background: {_CARD}; border: 2px solid {_BORDER}; border-radius: 4px;"
        )
        result_row.addWidget(self._swatch)

        self._result_label = QLabel("Click on the image to sample a color")
        self._result_label.setStyleSheet(f"color: {_MUTED}; font-size: 13px;")
        result_row.addWidget(self._result_label, stretch=1)

        layout.addLayout(result_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        if allow_skip:
            self._skip_btn = QPushButton("Skip (use defaults)")
            self._skip_btn.setStyleSheet(
                f"QPushButton {{ background: {_CARD}; color: {_MUTED}; }}"
                f"QPushButton:hover {{ color: {_TEXT}; }}"
            )
            self._skip_btn.clicked.connect(self._on_skip)
            btn_row.addWidget(self._skip_btn)

        self._retry_btn = QPushButton("\u21BB Retry")
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.setVisible(False)
        btn_row.addWidget(self._retry_btn)

        self._confirm_btn = QPushButton("\u2713 Confirm")
        self._confirm_btn.setStyleSheet(
            f"QPushButton {{ background: #27AE60; color: white; border: none; }}"
            f"QPushButton:hover {{ background: #2ECC71; }}"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._confirm_btn.setEnabled(False)
        btn_row.addWidget(self._confirm_btn)

        layout.addLayout(btn_row)

    def _on_click(self, img_x: int, img_y: int):
        if self._image_bgr is None:
            return
        result = sample_jersey_color(self._image_bgr, img_x, img_y)
        if result is None:
            self._result_label.setText(
                "Could not sample — too much grass. Try clicking directly on the jersey."
            )
            self._result_label.setStyleSheet(f"color: {_ACCENT}; font-size: 13px;")
            return

        hsv, swatch_bgr, color_name = result
        self._sampled_hsv = hsv

        # Display swatch
        h, w = swatch_bgr.shape[:2]
        rgb = cv2.cvtColor(swatch_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        self._swatch.setPixmap(QPixmap.fromImage(qimg))
        self._swatch.setStyleSheet(
            f"border: 2px solid {self._team_color}; border-radius: 4px;"
        )

        self._result_label.setText(f"Detected: <b>{color_name}</b>")
        self._result_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        self._confirm_btn.setEnabled(True)
        self._retry_btn.setVisible(True)

    def _on_retry(self):
        self._sampled_hsv = None
        self._swatch.clear()
        self._swatch.setStyleSheet(
            f"background: {_CARD}; border: 2px solid {_BORDER}; border-radius: 4px;"
        )
        self._result_label.setText("Click on the image to sample a color")
        self._result_label.setStyleSheet(f"color: {_MUTED}; font-size: 13px;")
        self._confirm_btn.setEnabled(False)
        self._retry_btn.setVisible(False)

    def _on_confirm(self):
        if self._sampled_hsv is not None:
            name = self._result_label.text().replace("Detected: <b>", "").replace("</b>", "")
            self.color_confirmed.emit(self._sampled_hsv, name)

    def _on_skip(self):
        self.skipped.emit()


class _SummaryPage(QWidget):
    """Final summary showing all sampled colors with [Change] buttons."""

    change_requested = pyqtSignal(int)  # page index to go back to
    start_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._swatches: list[QLabel] = []
        self._names: list[QLabel] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Team Colors Configured")
        title.setStyleSheet(f"color: {_ACCENT}; font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(12)

        teams = [
            ("Home", _HOME_COLOR, 0),
            ("Away", _AWAY_COLOR, 1),
            ("Referee", _REF_COLOR, 2),
        ]

        for label, color, idx in teams:
            row = QHBoxLayout()
            row.setSpacing(12)

            team_lbl = QLabel(f"{label}:")
            team_lbl.setFixedWidth(70)
            team_lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 14px;"
            )
            row.addWidget(team_lbl)

            swatch = QLabel()
            swatch.setFixedSize(36, 36)
            swatch.setStyleSheet(
                f"background: {_CARD}; border: 2px solid {color}; border-radius: 4px;"
            )
            self._swatches.append(swatch)
            row.addWidget(swatch)

            name_lbl = QLabel("—")
            name_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
            self._names.append(name_lbl)
            row.addWidget(name_lbl, stretch=1)

            change_btn = QPushButton("Change")
            change_btn.setFixedWidth(80)
            change_btn.clicked.connect(lambda _checked, i=idx: self.change_requested.emit(i))
            row.addWidget(change_btn)

            layout.addLayout(row)

        layout.addStretch()

        # Start button
        start_btn = QPushButton("Start Annotating")
        start_btn.setFixedHeight(40)
        start_btn.setStyleSheet(
            f"QPushButton {{ background: #27AE60; color: white; font-size: 14px;"
            f" border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: #2ECC71; }}"
        )
        start_btn.clicked.connect(self.start_requested.emit)
        layout.addWidget(start_btn)

    def update_color(self, index: int, swatch_bgr: Optional[np.ndarray], name: str):
        """Update a team's swatch and name on the summary page."""
        if swatch_bgr is not None:
            h, w = swatch_bgr.shape[:2]
            rgb = cv2.cvtColor(swatch_bgr, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            self._swatches[index].setPixmap(QPixmap.fromImage(qimg))
        self._names[index].setText(name)


class ColorSetupDialog(QDialog):
    """Multi-step dialog for sampling team jersey colors."""

    def __init__(self, first_frame_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Team Color Setup")
        self.setMinimumSize(800, 600)
        self.setStyleSheet(_STYLE)

        self._result: Optional[dict] = None
        self._colors: list[Optional[np.ndarray]] = [None, None, None]  # home, away, ref
        self._color_names: list[str] = ["—", "—", "—"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Step indicator
        self._step_label = QLabel()
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_label.setFixedHeight(32)
        self._step_label.setStyleSheet(
            f"background: {_CARD}; color: {_MUTED}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self._step_label)

        # Stacked pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        # Page 0: Home color sampling
        self._home_page = _SamplingPage(
            first_frame_path, "HOME", _HOME_COLOR
        )
        self._home_page.color_confirmed.connect(
            lambda hsv, name: self._on_color_confirmed(0, hsv, name)
        )
        self._stack.addWidget(self._home_page)

        # Page 1: Away color sampling
        self._away_page = _SamplingPage(
            first_frame_path, "AWAY", _AWAY_COLOR
        )
        self._away_page.color_confirmed.connect(
            lambda hsv, name: self._on_color_confirmed(1, hsv, name)
        )
        self._stack.addWidget(self._away_page)

        # Page 2: Referee color sampling (skippable)
        self._ref_page = _SamplingPage(
            first_frame_path, "REFEREE", _REF_COLOR, allow_skip=True
        )
        self._ref_page.color_confirmed.connect(
            lambda hsv, name: self._on_color_confirmed(2, hsv, name)
        )
        self._ref_page.skipped.connect(self._on_referee_skipped)
        self._stack.addWidget(self._ref_page)

        # Page 3: Summary
        self._summary_page = _SummaryPage()
        self._summary_page.change_requested.connect(self._go_to_page)
        self._summary_page.start_requested.connect(self._on_start)
        self._stack.addWidget(self._summary_page)

        self._update_step_label()

    def _update_step_label(self):
        idx = self._stack.currentIndex()
        labels = [
            "Step 1 of 3 — Sample Home Team Color",
            "Step 2 of 3 — Sample Away Team Color",
            "Step 3 of 3 — Sample Referee Color (Optional)",
            "Summary — Review & Start",
        ]
        self._step_label.setText(labels[min(idx, len(labels) - 1)])

    def _on_color_confirmed(self, index: int, hsv: np.ndarray, name: str):
        from backend.color_classifier import _make_swatch
        self._colors[index] = hsv
        self._color_names[index] = name
        swatch = _make_swatch(hsv)
        self._summary_page.update_color(index, swatch, name)

        # Advance to next page
        if index < 2:
            self._go_to_page(index + 1)
        else:
            self._go_to_page(3)  # summary

    def _on_referee_skipped(self):
        # Use default referee color (bright yellow)
        self._colors[2] = DEFAULT_REFEREE_HSV[0].copy()
        self._color_names[2] = "Yellow (default)"
        from backend.color_classifier import _make_swatch
        swatch = _make_swatch(self._colors[2])
        self._summary_page.update_color(2, swatch, "Yellow (default)")
        self._go_to_page(3)

    def _go_to_page(self, page_index: int):
        self._stack.setCurrentIndex(page_index)
        self._update_step_label()

    def _on_start(self):
        if self._colors[0] is None or self._colors[1] is None:
            return  # Should not happen, but guard
        self._result = {
            "home_hsv": self._colors[0].tolist(),
            "away_hsv": self._colors[1].tolist(),
            "referee_hsv": self._colors[2].tolist() if self._colors[2] is not None else None,
        }
        self.accept()

    def get_result(self) -> Optional[dict]:
        """Return sampled colors dict, or None if cancelled."""
        return self._result
