from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar

from backend.i18n import t


class ProgressBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background: #333;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(12)

        self._frame_label = QLabel(t("progress.frame_label", current=0, total=0))
        self._frame_label.setStyleSheet("color: #EEE; font-weight: bold; font-size: 12px;")
        layout.addWidget(self._frame_label)

        self._bar = QProgressBar()
        self._bar.setFixedHeight(16)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet("""
            QProgressBar {
                background: #555; border: none; border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #4A90D9; border-radius: 3px;
            }
        """)
        layout.addWidget(self._bar, stretch=1)

        self._stats_label = QLabel(t("progress.stats", annotated=0, skipped=0, remaining=0))
        self._stats_label.setStyleSheet("color: #CCC; font-size: 11px;")
        layout.addWidget(self._stats_label)

    def update_progress(self, current: int, total: int, annotated: int,
                        skipped: int, remaining: int):
        self._frame_label.setText(t("progress.frame_label", current=current, total=total))
        self._bar.setMaximum(total if total > 0 else 1)
        self._bar.setValue(annotated + skipped)
        self._stats_label.setText(
            t("progress.stats", annotated=annotated, skipped=skipped, remaining=remaining)
        )
