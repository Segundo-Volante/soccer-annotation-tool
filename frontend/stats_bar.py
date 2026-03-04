"""Real-time statistics bar widget displayed below the progress bar.

Shows annotation speed, ETA, session elapsed time, today's count,
and a toggleable keyboard shortcut reference.
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

from backend.i18n import t
from backend.session_stats import SessionStats


class ShortcutsBar(QWidget):
    """Compact collapsible shortcut reference displayed below the stats bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #22223A; border-top: 1px solid #333350;")
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.setSpacing(4)

        # Row 1: Category + Occlusion
        row1 = QHBoxLayout()
        row1.setSpacing(24)
        row1.addWidget(self._section("Category",
            "<span style='color:#E74C3C'>1</span> Home  "
            "<span style='color:#3498DB'>2</span> Opp  "
            "<span style='color:#E67E22'>3</span> GK  "
            "<span style='color:#2980B9'>4</span> OppGK  "
            "<span style='color:#F1C40F'>5</span> Ref  "
            "<span style='color:#2ECC71'>6</span> Ball"
        ))
        row1.addWidget(self._sep_v())
        row1.addWidget(self._section("Occlusion",
            "<span style='color:#CCC'>F</span> Visible  "
            "<span style='color:#CCC'>G</span> Partial  "
            "<span style='color:#CCC'>H</span> Heavy  "
            "<span style='color:#CCC'>T</span> Trunc  "
            "<span style='color:#FF6B35'>U</span> Unsure"
        ))
        row1.addWidget(self._sep_v())
        row1.addWidget(self._section("Metadata",
            "<span style='color:#F5A623'>Tab</span> Next dim  "
            "<span style='color:#F5A623'>Shift+Tab</span> Prev dim  "
            "<span style='color:#CCC'>1-9</span> Option"
        ))
        row1.addStretch()
        outer.addLayout(row1)

        # Row 2: Navigation + Zoom + Tools
        row2 = QHBoxLayout()
        row2.setSpacing(24)
        row2.addWidget(self._section("Navigate",
            "<span style='color:#4A90D9'>Enter</span> Export  "
            "<span style='color:#D94A4A'>Esc</span> Skip  "
            "<span style='color:#CCC'>\u2190\u2192</span> Prev/Next  "
            "<span style='color:#CCC'>Ctrl+Z</span> Undo  "
            "<span style='color:#CCC'>Del</span> Delete"
        ))
        row2.addWidget(self._sep_v())
        row2.addWidget(self._section("View",
            "<span style='color:#CCC'>Scroll</span> Zoom  "
            "<span style='color:#CCC'>0</span> Reset  "
            "<span style='color:#CCC'>\u2191\u2193\u2190\u2192</span> Pan  "
            "<span style='color:#9B59B6'>B</span> Box vis"
        ))
        row2.addWidget(self._sep_v())
        row2.addWidget(self._section("Tools",
            "<span style='color:#CCC'>Ctrl+H</span> Health  "
            "<span style='color:#CCC'>Ctrl+R</span> Review  "
            "<span style='color:#CCC'>Ctrl+E</span> Export  "
            "<span style='color:#CCC'>Ctrl+S</span> Save  "
            "<span style='color:#CCC'>Ctrl+Shift+S</span> Swap Teams"
        ))
        row2.addStretch()
        outer.addLayout(row2)

    @staticmethod
    def _section(title: str, shortcuts: str) -> QLabel:
        lbl = QLabel(f"<b style='color:#8888A0'>{title}:</b> {shortcuts}")
        lbl.setStyleSheet("color: #C0C0D0; font-size: 10px; border: none;")
        return lbl

    @staticmethod
    def _sep_v() -> QWidget:
        w = QWidget()
        w.setFixedWidth(1)
        w.setStyleSheet("background: #404060;")
        return w


class StatsBar(QWidget):
    """Compact stats bar showing real-time annotation metrics."""

    shortcuts_toggled = pyqtSignal(bool)

    def __init__(self, stats: SessionStats, parent=None):
        super().__init__(parent)
        self._stats = stats
        self.setFixedHeight(24)
        self.setStyleSheet("background: #2A2A3C; border-top: 1px solid #404060;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(16)

        self._speed_label = QLabel()
        self._speed_label.setStyleSheet("color: #8AD98A; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._speed_label)

        self._eta_label = QLabel()
        self._eta_label.setStyleSheet("color: #D9C84A; font-size: 11px;")
        layout.addWidget(self._eta_label)

        self._elapsed_label = QLabel()
        self._elapsed_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._elapsed_label)

        # Shortcuts toggle button (right of elapsed)
        self._shortcuts_btn = QPushButton("? Shortcuts")
        self._shortcuts_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._shortcuts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shortcuts_btn.setFixedHeight(18)
        self._shortcuts_visible = False
        self._shortcuts_btn.setStyleSheet("""
            QPushButton {
                background: #333350; color: #8888A0; font-size: 10px;
                padding: 1px 8px; border-radius: 9px; border: 1px solid #444468;
            }
            QPushButton:hover { background: #404068; color: #C0C0D0; }
        """)
        self._shortcuts_btn.clicked.connect(self._toggle_shortcuts)
        layout.addWidget(self._shortcuts_btn)

        layout.addStretch()

        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color: #7EB8DA; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._zoom_label)

        self._box_vis_label = QLabel("Boxes: Full")
        self._box_vis_label.setStyleSheet("color: #A0A0C0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._box_vis_label)

        self._today_label = QLabel()
        self._today_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._today_label)

        # Auto-refresh every second
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

        self.refresh()

    def _toggle_shortcuts(self):
        self._shortcuts_visible = not self._shortcuts_visible
        if self._shortcuts_visible:
            self._shortcuts_btn.setStyleSheet("""
                QPushButton {
                    background: #F5A623; color: #1E1E2E; font-size: 10px;
                    padding: 1px 8px; border-radius: 9px; border: none;
                    font-weight: bold;
                }
                QPushButton:hover { background: #FFB833; }
            """)
        else:
            self._shortcuts_btn.setStyleSheet("""
                QPushButton {
                    background: #333350; color: #8888A0; font-size: 10px;
                    padding: 1px 8px; border-radius: 9px; border: 1px solid #444468;
                }
                QPushButton:hover { background: #404068; color: #C0C0D0; }
            """)
        self.shortcuts_toggled.emit(self._shortcuts_visible)

    def set_box_visibility_label(self, text: str):
        """Update the box visibility mode indicator."""
        self._box_vis_label.setText(text)

    def set_zoom_label(self, percent: int):
        """Update the zoom level indicator."""
        self._zoom_label.setText(f"{percent}%")

    def refresh(self):
        """Update all stat labels from the SessionStats object."""
        s = self._stats.get_summary()

        speed = s["frames_per_minute"]
        if speed > 0:
            self._speed_label.setText(
                t("stats.speed", speed=f"{speed:.1f}",
                  avg=f"{s['avg_seconds']:.1f}")
            )
        else:
            self._speed_label.setText(t("stats.speed_idle"))

        self._eta_label.setText(t("stats.eta", eta=s["eta"]))
        self._elapsed_label.setText(t("stats.elapsed", elapsed=s["elapsed"]))
        self._today_label.setText(t("stats.today", count=s["today_count"]))
