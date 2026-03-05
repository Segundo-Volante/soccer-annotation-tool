"""Formation Editor Dialog — 3-step wizard for setting up team formations.

Step 1: Choose defender/striker counts (midfielders auto-derived).
Step 2: Place midfielders on a visual mini-pitch grid.
Step 3: Assign players to position slots and save.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QPixmap, QPainterPath,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QStackedWidget, QButtonGroup, QRadioButton,
    QScrollArea, QFrame, QSizePolicy, QGridLayout,
)

from backend.models import Player
from backend.squad_loader import SquadData, TeamSquad, save_squad_json
from backend.formation_editor import (
    generate_defender_positions,
    generate_striker_positions,
    validate_formation_config,
    expand_mid_positions,
    build_formation_slots,
    try_auto_fill_from_squad,
    MIDFIELDER_CHOICES,
    FormationSlot,
)
from backend.formation_utils import derive_formation_string

# ── Design tokens (matches squad_panel.py) ──
_BG = "#1E1E2E"
_CARD = "#2A2A3C"
_BORDER = "#404060"
_TEXT = "#E8E8F0"
_MUTED = "#8888A0"
_ACCENT = "#F5A623"
_HOME_COLOR = "#E74C3C"
_AWAY_COLOR = "#3498DB"
_CHECK_COLOR = "#27AE60"
_HOVER_BG = "#33334C"
_PITCH_GREEN = "#2D5A27"
_PITCH_LINE = "#3A7A33"
_SLOT_INACTIVE = "#505050"
_SLOT_ACTIVE = "#F5A623"
_SLOT_HOVER = "#FFD080"
_SELECTED_BORDER = "#FF6B6B"

_DIALOG_STYLE = f"""
    QDialog {{ background: {_BG}; }}
    QLabel {{ color: {_TEXT}; font-size: 12px; }}
    QPushButton {{
        background: {_CARD}; color: {_TEXT}; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: 1px solid {_BORDER};
    }}
    QPushButton:hover {{ background: {_HOVER_BG}; border-color: {_ACCENT}; }}
    QPushButton:disabled {{ color: {_MUTED}; background: #222233; }}
    QRadioButton {{ color: {_TEXT}; font-size: 12px; spacing: 6px; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; }}
    QScrollArea {{ background: {_BG}; border: none; }}
    QScrollBar:vertical {{
        background: {_CARD}; width: 6px; border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: #505070; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


# ═══════════════════════════════════════════════════════════════
#  MidPitchGrid — visual mini-pitch widget for midfielder placement
# ═══════════════════════════════════════════════════════════════

# Position circle layout on the pitch (relative coordinates 0-1)
# x=0 is left, x=1 is right, y=0 is top (attacking), y=1 is bottom (defensive)
_PITCH_POSITIONS: dict[str, tuple[float, float]] = {
    "LW":  (0.15, 0.15),
    "CAM": (0.50, 0.15),
    "RW":  (0.85, 0.15),
    "LM":  (0.15, 0.50),
    "CM":  (0.50, 0.50),
    "RM":  (0.85, 0.50),
    "CDM": (0.50, 0.82),
}

_CIRCLE_RADIUS = 24


class MidPitchGrid(QWidget):
    """Interactive mini-pitch for placing midfielders at positions.

    Click a position circle to increment its count. Right-click to decrement.
    """

    changed = pyqtSignal()  # emitted when any count changes

    def __init__(self, target_count: int = 4, parent=None):
        super().__init__(parent)
        self._target_count = target_count
        self._counts: dict[str, int] = {pos: 0 for pos in _PITCH_POSITIONS}
        self._hover_pos: Optional[str] = None
        self.setMinimumSize(340, 220)
        self.setFixedHeight(220)
        self.setMouseTracking(True)

    def set_target_count(self, count: int):
        """Set how many midfielders must be placed."""
        self._target_count = count
        # If current total exceeds new target, reset
        if self.total_placed() > count:
            self._counts = {pos: 0 for pos in _PITCH_POSITIONS}
            self.changed.emit()
        self.update()

    def set_counts(self, counts: dict[str, int]):
        """Pre-fill position counts (for auto-fill)."""
        self._counts = {pos: 0 for pos in _PITCH_POSITIONS}
        for pos, cnt in counts.items():
            if pos in self._counts:
                self._counts[pos] = cnt
        self.changed.emit()
        self.update()

    def total_placed(self) -> int:
        return sum(self._counts.values())

    def is_complete(self) -> bool:
        return self.total_placed() == self._target_count

    def get_positions(self) -> list[str]:
        """Get flat list of chosen position codes."""
        return expand_mid_positions(self._counts)

    def get_counts(self) -> dict[str, int]:
        """Get position → count mapping (non-zero only)."""
        return {k: v for k, v in self._counts.items() if v > 0}

    def _pos_rect(self, pos: str) -> QRectF:
        """Get the screen rectangle for a position circle."""
        rx, ry = _PITCH_POSITIONS[pos]
        # Leave padding for labels
        pad_x, pad_y = 30, 20
        w = self.width() - 2 * pad_x
        h = self.height() - 2 * pad_y
        cx = pad_x + rx * w
        cy = pad_y + ry * h
        r = _CIRCLE_RADIUS
        return QRectF(cx - r, cy - r, 2 * r, 2 * r)

    def _hit_test(self, point: QPointF) -> Optional[str]:
        """Return position code if point is inside a circle, else None."""
        for pos in _PITCH_POSITIONS:
            rect = self._pos_rect(pos)
            center = rect.center()
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            if math.sqrt(dx * dx + dy * dy) <= _CIRCLE_RADIUS:
                return pos
        return None

    def mousePressEvent(self, event):
        pos = self._hit_test(QPointF(event.position()))
        if pos is None:
            return super().mousePressEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            if self.total_placed() < self._target_count:
                self._counts[pos] += 1
                self.changed.emit()
            elif self._counts[pos] > 0:
                # Already at target — clicking an active pos decrements
                self._counts[pos] -= 1
                self.changed.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            if self._counts[pos] > 0:
                self._counts[pos] -= 1
                self.changed.emit()

        self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self._hit_test(QPointF(event.position()))
        if pos != self._hover_pos:
            self._hover_pos = pos
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pitch background
        painter.fillRect(self.rect(), QColor(_PITCH_GREEN))

        # Pitch lines (simplified)
        pen = QPen(QColor(_PITCH_LINE), 1.5)
        painter.setPen(pen)
        # Center line
        cy = self.height() // 2
        painter.drawLine(0, cy, self.width(), cy)
        # Center circle
        r = min(self.width(), self.height()) // 6
        painter.drawEllipse(self.width() // 2 - r, cy - r, 2 * r, 2 * r)

        # Draw position circles
        for pos in _PITCH_POSITIONS:
            rect = self._pos_rect(pos)
            count = self._counts[pos]
            is_hover = (pos == self._hover_pos)
            is_active = count > 0

            # Circle fill
            if is_active:
                fill = QColor(_SLOT_ACTIVE)
                fill.setAlpha(220)
            elif is_hover:
                fill = QColor(_SLOT_HOVER)
                fill.setAlpha(100)
            else:
                fill = QColor(_SLOT_INACTIVE)
                fill.setAlpha(120)

            painter.setBrush(QBrush(fill))

            # Circle border
            if is_active:
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
            elif is_hover:
                painter.setPen(QPen(QColor(_ACCENT), 1.5))
            else:
                painter.setPen(QPen(QColor("#888888"), 1))

            painter.drawEllipse(rect)

            # Position label
            font = QFont()
            font.setPixelSize(11)
            font.setBold(is_active)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF") if is_active else QColor("#CCCCCC"))

            if is_active and count > 1:
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{pos}\n\u00d7{count}")
            else:
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, pos)

        painter.end()


# ═══════════════════════════════════════════════════════════════
#  PlayerSlotWidget — clickable slot in the formation assignment view
# ═══════════════════════════════════════════════════════════════

_SLOT_SIZE = 60
_CROP_SIZE = 32


class PlayerSlotWidget(QWidget):
    """A clickable formation slot that can have a player assigned to it."""

    clicked = pyqtSignal(int)  # slot_index

    def __init__(self, slot_index: int, position: str, team_color: str, parent=None):
        super().__init__(parent)
        self._slot_index = slot_index
        self._position = position
        self._team_color = team_color
        self._player: Optional[Player] = None
        self._selected = False
        self._crop_pixmap: Optional[QPixmap] = None

        self.setFixedSize(_SLOT_SIZE, 70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._update_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Crop/placeholder
        self._crop_label = QLabel()
        self._crop_label.setFixedSize(_CROP_SIZE, _CROP_SIZE)
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_placeholder()
        layout.addWidget(self._crop_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Player name or "?"
        self._name_label = QLabel("?")
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 8px; border: none;")
        layout.addWidget(self._name_label)

        # Position label
        self._pos_label = QLabel(f"({self._position})")
        self._pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pos_label.setStyleSheet(f"color: {_MUTED}; font-size: 7px; border: none;")
        layout.addWidget(self._pos_label)

    def _set_placeholder(self):
        pm = QPixmap(_CROP_SIZE, _CROP_SIZE)
        pm.fill(QColor("#404060"))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = _CROP_SIZE // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#606080")))
        painter.drawEllipse(c - 5, 4, 10, 10)
        painter.drawEllipse(c - 8, 16, 16, 12)
        painter.end()
        self._crop_label.setPixmap(pm)

    def set_player(self, player: Optional[Player], pixmap: Optional[QPixmap] = None):
        """Assign or unassign a player to this slot."""
        self._player = player
        if player:
            parts = player.name.split() if player.name else []
            display = parts[-1] if parts else f"#{player.jersey_number}"
            max_chars = max(4, _SLOT_SIZE // 7)
            if len(display) > max_chars:
                display = display[:max_chars - 1] + "\u2026"
            self._name_label.setText(f"#{player.jersey_number} {display}")
            self._name_label.setStyleSheet(
                f"color: {self._team_color}; font-size: 8px; font-weight: bold; border: none;"
            )
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    _CROP_SIZE, _CROP_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._crop_label.setPixmap(scaled)
                self._crop_pixmap = pixmap
            elif self._crop_pixmap is None:
                self._set_placeholder()
        else:
            self._name_label.setText("?")
            self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 8px; border: none;")
            self._set_placeholder()
            self._crop_pixmap = None
        self._update_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    @property
    def player(self) -> Optional[Player]:
        return self._player

    @property
    def position(self) -> str:
        return self._position

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(
                f"PlayerSlotWidget {{ background: rgba(245, 166, 35, 0.3);"
                f" border: 2px solid {_SELECTED_BORDER}; border-radius: 6px; }}"
            )
        elif self._player:
            self.setStyleSheet(
                f"PlayerSlotWidget {{ background: rgba(39, 174, 96, 0.2);"
                f" border: 1px solid {_CHECK_COLOR}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(
                f"PlayerSlotWidget {{ background: {_CARD};"
                f" border: 1px solid {_BORDER}; border-radius: 6px; }}"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._slot_index)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════
#  AvailablePlayerWidget — compact player card in the available list
# ═══════════════════════════════════════════════════════════════

class AvailablePlayerWidget(QWidget):
    """Compact player card shown in the available players list."""

    clicked = pyqtSignal(int)  # jersey_number

    def __init__(self, player: Player, team_color: str, parent=None):
        super().__init__(parent)
        self._player = player
        self._team_color = team_color
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"AvailablePlayerWidget {{ background: {_CARD};"
            f" border: 1px solid {_BORDER}; border-radius: 4px; }}"
            f"AvailablePlayerWidget:hover {{ background: {_HOVER_BG};"
            f" border-color: {_ACCENT}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        num = QLabel(str(player.jersey_number))
        num.setStyleSheet(
            f"color: {team_color}; font-weight: bold; font-size: 11px; border: none;"
        )
        num.setFixedWidth(24)
        layout.addWidget(num)

        name = QLabel(player.name)
        name.setStyleSheet(f"color: {_TEXT}; font-size: 11px; border: none;")
        layout.addWidget(name, stretch=1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._player.jersey_number)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════
#  FormationEditorDialog — main 3-step wizard
# ═══════════════════════════════════════════════════════════════


class FormationEditorDialog(QDialog):
    """Formation Editor — 3-step wizard for setting up a team formation.

    Step 1: Choose defender/striker counts.
    Step 2: Place midfielders on mini-pitch grid.
    Step 3: Assign players to position slots and save.

    Emits ``formation_saved`` with updated SquadData on success.
    """

    formation_saved = pyqtSignal(object)  # SquadData

    def __init__(
        self,
        squad_data: SquadData,
        squad_json_path: str,
        team_side: str = "home",
        parent=None,
    ):
        super().__init__(parent)
        self._squad_data = squad_data
        self._squad_json_path = squad_json_path
        self._team_side = team_side
        self._team = (
            squad_data.home_team if team_side == "home" else squad_data.away_team
        )
        self._team_color = _HOME_COLOR if team_side == "home" else _AWAY_COLOR

        # State
        self._def_count = 4
        self._str_count = 2
        self._formation_slots: list[FormationSlot] = []
        self._slot_widgets: list[PlayerSlotWidget] = []
        self._selected_slot_index: Optional[int] = None
        self._available_player_widgets: list[AvailablePlayerWidget] = []

        self.setWindowTitle(f"Set Up Formation — {self._team.name or team_side.title()}")
        self.setFixedSize(450, 620)
        self.setStyleSheet(_DIALOG_STYLE)

        self._build_ui()
        self._try_auto_fill()

    # ── UI Construction ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel(f"Set Up Formation — {self._team.name or 'Team'}")
        title.setStyleSheet(
            f"color: {self._team_color}; font-size: 14px; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Step indicator
        self._step_label = QLabel("Step 1 of 3: Formation Structure")
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(self._step_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        # Stacked pages
        self._stack = QStackedWidget()
        self._build_page1()
        self._build_page2()
        self._build_page3()
        layout.addWidget(self._stack, stretch=1)

        # Navigation buttons
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self._back_btn = QPushButton("\u2190 Back")
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)
        nav.addWidget(self._back_btn)

        nav.addStretch()

        self._next_btn = QPushButton("Next \u2192")
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._next_btn)

        self._save_btn = QPushButton("Save to squad.json")
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {_CHECK_COLOR}; color: white;"
            f" padding: 8px 20px; border-radius: 4px; font-weight: bold;"
            f" font-size: 12px; border: none; }}"
            f"QPushButton:hover {{ background: #2ECC71; }}"
            f"QPushButton:disabled {{ background: #555; color: {_MUTED}; }}"
        )
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setVisible(False)
        nav.addWidget(self._save_btn)

        layout.addLayout(nav)

    # ── Page 1: Formation Structure ──

    def _build_page1(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        # Defenders
        def_label = QLabel("Defenders:")
        def_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: bold;")
        layout.addWidget(def_label)

        self._def_group = QButtonGroup(self)
        def_row = QHBoxLayout()
        def_row.setSpacing(8)
        for count in (3, 4, 5):
            rb = QRadioButton(str(count))
            rb.setChecked(count == self._def_count)
            self._def_group.addButton(rb, count)
            def_row.addWidget(rb)
        def_row.addStretch()
        layout.addLayout(def_row)
        self._def_group.idClicked.connect(self._on_formation_count_changed)

        # Strikers
        str_label = QLabel("Strikers:")
        str_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: bold;")
        layout.addWidget(str_label)

        self._str_group = QButtonGroup(self)
        str_row = QHBoxLayout()
        str_row.setSpacing(8)
        for count in (1, 2, 3):
            rb = QRadioButton(str(count))
            rb.setChecked(count == self._str_count)
            self._str_group.addButton(rb, count)
            str_row.addWidget(rb)
        str_row.addStretch()
        layout.addLayout(str_row)
        self._str_group.idClicked.connect(self._on_formation_count_changed)

        # Midfielders (auto-calculated)
        self._mid_label = QLabel()
        self._mid_label.setStyleSheet(f"color: {_ACCENT}; font-size: 13px; font-weight: bold;")
        layout.addWidget(self._mid_label)

        # Derived info
        self._p1_info = QLabel()
        self._p1_info.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        self._p1_info.setWordWrap(True)
        layout.addWidget(self._p1_info)

        layout.addStretch()
        self._stack.addWidget(page)
        self._update_page1_info()

    def _on_formation_count_changed(self, _id):
        self._def_count = self._def_group.checkedId()
        self._str_count = self._str_group.checkedId()
        self._update_page1_info()

    def _update_page1_info(self):
        mid = 10 - self._def_count - self._str_count
        self._mid_label.setText(f"Midfielders: {mid} (auto-calculated)")

        def_pos = generate_defender_positions(self._def_count)
        str_pos = generate_striker_positions(self._str_count)
        self._p1_info.setText(
            f"GK + {', '.join(def_pos)} + {mid} midfielders + {', '.join(str_pos)} = 11\n\n"
            f"Defender positions are auto-assigned based on count.\n"
            f"You'll choose midfielder positions in the next step."
        )

    # ── Page 2: Midfielder Pitch Grid ──

    def _build_page2(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        hint = QLabel(
            "Click positions to place midfielders.\n"
            "Right-click to remove. Click active position at max to decrement."
        )
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 10px;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self._pitch_grid = MidPitchGrid(target_count=4)
        self._pitch_grid.changed.connect(self._on_pitch_changed)
        layout.addWidget(self._pitch_grid)

        self._p2_status = QLabel()
        self._p2_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._p2_status.setStyleSheet(f"color: {_ACCENT}; font-size: 12px; font-weight: bold;")
        layout.addWidget(self._p2_status)

        self._p2_formation = QLabel()
        self._p2_formation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._p2_formation.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        layout.addWidget(self._p2_formation)

        layout.addStretch()
        self._stack.addWidget(page)

    def _on_pitch_changed(self):
        total = self._pitch_grid.total_placed()
        mid_count = 10 - self._def_count - self._str_count

        if total == mid_count:
            self._p2_status.setText(f"Placed: {total}/{mid_count} \u2713")
            self._p2_status.setStyleSheet(
                f"color: {_CHECK_COLOR}; font-size: 12px; font-weight: bold;"
            )
        else:
            self._p2_status.setText(f"Placed: {total}/{mid_count}")
            self._p2_status.setStyleSheet(
                f"color: {_ACCENT}; font-size: 12px; font-weight: bold;"
            )

        # Show derived formation
        if total > 0:
            mid_positions = self._pitch_grid.get_positions()
            formation = derive_formation_string(
                self._def_count, mid_positions, self._str_count,
            )
            self._p2_formation.setText(f"Formation: {formation}")
        else:
            self._p2_formation.setText("")

        self._next_btn.setEnabled(self._pitch_grid.is_complete())

    # ── Page 3: Player Assignment ──

    def _build_page3(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Formation preview label
        self._p3_formation_label = QLabel()
        self._p3_formation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._p3_formation_label.setStyleSheet(
            f"color: {self._team_color}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self._p3_formation_label)

        # Scroll area for formation slots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._slots_container = QWidget()
        self._slots_layout = QVBoxLayout(self._slots_container)
        self._slots_layout.setContentsMargins(4, 4, 4, 4)
        self._slots_layout.setSpacing(2)
        scroll.setWidget(self._slots_container)
        layout.addWidget(scroll, stretch=3)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        # Available players label
        avail_label = QLabel("Available players (click to assign):")
        avail_label.setStyleSheet(f"color: {_MUTED}; font-size: 10px;")
        layout.addWidget(avail_label)

        # Available players scroll
        avail_scroll = QScrollArea()
        avail_scroll.setWidgetResizable(True)
        avail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        avail_scroll.setMaximumHeight(160)

        self._avail_container = QWidget()
        self._avail_layout = QVBoxLayout(self._avail_container)
        self._avail_layout.setContentsMargins(4, 2, 4, 2)
        self._avail_layout.setSpacing(2)
        avail_scroll.setWidget(self._avail_container)
        layout.addWidget(avail_scroll, stretch=1)

        self._stack.addWidget(page)

    def _populate_page3(self):
        """Build formation slot widgets and available player list."""
        # Clear existing
        self._slot_widgets.clear()
        self._available_player_widgets.clear()
        self._selected_slot_index = None

        while self._slots_layout.count():
            item = self._slots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

        while self._avail_layout.count():
            item = self._avail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Build formation slots
        mid_positions = self._pitch_grid.get_positions()
        self._formation_slots = build_formation_slots(
            self._def_count, mid_positions, self._str_count,
        )

        formation_str = derive_formation_string(
            self._def_count, mid_positions, self._str_count,
        )
        self._p3_formation_label.setText(
            f"\u2014\u2014 {self._team.name or 'Team'} ({formation_str}) \u2014\u2014"
        )

        # Group slots by row_group and depth for display
        from backend.formation_utils import _DEPTH_ORDER, _LATERAL_ORDER

        # Build display rows: GK, defense, midfield rows (by depth), forward
        # Reversed for display: forwards at top, GK at bottom
        display_rows: list[tuple[str, list[int]]] = []  # (label, [slot_indices])

        # Forward
        fwd_indices = [i for i, s in enumerate(self._formation_slots)
                       if s.row_group == "forward"]
        if fwd_indices:
            display_rows.append(("Strikers", fwd_indices))

        # Midfield — group by depth, highest depth first (attacking → defensive)
        mid_indices = [i for i, s in enumerate(self._formation_slots)
                       if s.row_group == "midfield"]
        if mid_indices:
            depth_groups: dict[int, list[int]] = {}
            for idx in mid_indices:
                pos = self._formation_slots[idx].position
                depth = _DEPTH_ORDER.get(pos.upper(), 1)
                depth_groups.setdefault(depth, []).append(idx)
            for depth_key in sorted(depth_groups.keys(), reverse=True):
                indices = depth_groups[depth_key]
                # Sort by lateral order within depth
                indices.sort(
                    key=lambda i: _LATERAL_ORDER.get(
                        self._formation_slots[i].position.upper(), 1
                    )
                )
                display_rows.append(("Midfield", indices))

        # Defense
        def_indices = [i for i, s in enumerate(self._formation_slots)
                       if s.row_group == "defense"]
        if def_indices:
            def_indices.sort(
                key=lambda i: _LATERAL_ORDER.get(
                    self._formation_slots[i].position.upper(), 1
                )
            )
            display_rows.append(("Defenders", def_indices))

        # GK
        gk_indices = [i for i, s in enumerate(self._formation_slots)
                      if s.row_group == "gk"]
        if gk_indices:
            display_rows.append(("GK", gk_indices))

        # Create slot widgets per row
        for label, indices in display_rows:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.setSpacing(4)

            # Calculate node width
            n = len(indices)
            available_w = 420 - 16  # dialog width - margins
            node_w = min(_SLOT_SIZE, (available_w - (n - 1) * 4) // max(n, 1))

            for idx in indices:
                slot = self._formation_slots[idx]
                sw = PlayerSlotWidget(idx, slot.position, self._team_color)
                sw.setFixedSize(node_w, 70)
                sw.clicked.connect(self._on_slot_clicked)
                self._slot_widgets.append(sw)
                row_layout.addWidget(sw)

            self._slots_layout.addWidget(row_widget)

        self._slots_layout.addStretch()

        # Try to auto-assign players with existing matching positions
        self._auto_assign_players()

        # Build available players list
        self._rebuild_available_list()

    def _auto_assign_players(self):
        """Pre-assign players who already have matching positions."""
        assigned_jerseys: set[int] = set()

        for i, slot in enumerate(self._formation_slots):
            # Find a player with matching position
            for player in self._team.players:
                if player.jersey_number in assigned_jerseys:
                    continue
                if player.position and player.position.upper() == slot.position.upper():
                    slot.player = player
                    assigned_jerseys.add(player.jersey_number)
                    # Update widget
                    for sw in self._slot_widgets:
                        if sw._slot_index == i:
                            pixmap = self._get_player_pixmap(player)
                            sw.set_player(player, pixmap)
                            break
                    break

    def _get_player_pixmap(self, player: Player) -> Optional[QPixmap]:
        """Try to load a player's headshot image."""
        key = (self._team_side, player.jersey_number)
        if self._squad_data.headshot_images:
            img_path = self._squad_data.headshot_images.get(key)
            if img_path and img_path.exists():
                pm = QPixmap(str(img_path))
                if not pm.isNull():
                    return pm
        return None

    def _on_slot_clicked(self, slot_index: int):
        """Handle clicking a formation slot."""
        slot = self._formation_slots[slot_index]

        if self._selected_slot_index == slot_index:
            # Deselect
            self._selected_slot_index = None
            for sw in self._slot_widgets:
                sw.set_selected(False)
            return

        if slot.player and self._selected_slot_index is None:
            # Unassign player
            slot.player = None
            for sw in self._slot_widgets:
                if sw._slot_index == slot_index:
                    sw.set_player(None)
                    break
            self._rebuild_available_list()
            self._update_save_enabled()
            return

        # Select this slot
        self._selected_slot_index = slot_index
        for sw in self._slot_widgets:
            sw.set_selected(sw._slot_index == slot_index)

    def _on_available_player_clicked(self, jersey_number: int):
        """Handle clicking an available player to assign to selected slot."""
        if self._selected_slot_index is None:
            # Auto-select first empty slot
            for i, slot in enumerate(self._formation_slots):
                if slot.player is None:
                    self._selected_slot_index = i
                    for sw in self._slot_widgets:
                        sw.set_selected(sw._slot_index == i)
                    break
            if self._selected_slot_index is None:
                return

        # Find the player
        player = None
        for p in self._team.players:
            if p.jersey_number == jersey_number:
                player = p
                break
        if not player:
            return

        # Assign to selected slot
        slot = self._formation_slots[self._selected_slot_index]
        slot.player = player
        pixmap = self._get_player_pixmap(player)
        for sw in self._slot_widgets:
            if sw._slot_index == self._selected_slot_index:
                sw.set_player(player, pixmap)
                sw.set_selected(False)
                break

        # Auto-advance to next empty slot
        self._selected_slot_index = None
        for i, s in enumerate(self._formation_slots):
            if s.player is None:
                self._selected_slot_index = i
                for sw in self._slot_widgets:
                    sw.set_selected(sw._slot_index == i)
                break

        if self._selected_slot_index is None:
            for sw in self._slot_widgets:
                sw.set_selected(False)

        self._rebuild_available_list()
        self._update_save_enabled()

    def _rebuild_available_list(self):
        """Rebuild the available players list, excluding assigned ones."""
        # Clear
        self._available_player_widgets.clear()
        while self._avail_layout.count():
            item = self._avail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        assigned_jerseys = {
            s.player.jersey_number
            for s in self._formation_slots
            if s.player is not None
        }

        for player in self._team.players:
            if player.jersey_number in assigned_jerseys:
                continue
            pw = AvailablePlayerWidget(player, self._team_color)
            pw.clicked.connect(self._on_available_player_clicked)
            self._available_player_widgets.append(pw)
            self._avail_layout.addWidget(pw)

        self._avail_layout.addStretch()

    def _update_save_enabled(self):
        """Enable save button only when all slots are filled."""
        all_filled = all(s.player is not None for s in self._formation_slots)
        self._save_btn.setEnabled(all_filled)

    # ── Navigation ──

    def _go_next(self):
        current = self._stack.currentIndex()
        if current == 0:
            # Moving to page 2: update pitch grid target
            mid_count = 10 - self._def_count - self._str_count
            self._pitch_grid.set_target_count(mid_count)
            self._on_pitch_changed()  # update status
            self._stack.setCurrentIndex(1)
            self._step_label.setText("Step 2 of 3: Midfielder Positions")
            self._back_btn.setVisible(True)
            self._next_btn.setEnabled(self._pitch_grid.is_complete())
        elif current == 1:
            # Moving to page 3: build assignment UI
            self._populate_page3()
            self._update_save_enabled()
            self._stack.setCurrentIndex(2)
            self._step_label.setText("Step 3 of 3: Assign Players")
            self._next_btn.setVisible(False)
            self._save_btn.setVisible(True)

    def _go_back(self):
        current = self._stack.currentIndex()
        if current == 1:
            self._stack.setCurrentIndex(0)
            self._step_label.setText("Step 1 of 3: Formation Structure")
            self._back_btn.setVisible(False)
            self._next_btn.setEnabled(True)
        elif current == 2:
            self._stack.setCurrentIndex(1)
            self._step_label.setText("Step 2 of 3: Midfielder Positions")
            self._next_btn.setVisible(True)
            self._save_btn.setVisible(False)
            self._next_btn.setEnabled(self._pitch_grid.is_complete())

    # ── Auto-fill ──

    def _try_auto_fill(self):
        """Try to pre-populate from existing position data."""
        def_count, str_count, mid_counts, group_players = try_auto_fill_from_squad(
            self._team.players,
        )
        if def_count is None:
            return  # start fresh

        # Set def/str counts
        self._def_count = def_count
        self._str_count = str_count

        # Update radio buttons
        btn = self._def_group.button(def_count)
        if btn:
            btn.setChecked(True)
        btn = self._str_group.button(str_count)
        if btn:
            btn.setChecked(True)

        self._update_page1_info()

        # Pre-fill pitch grid
        if mid_counts:
            self._pitch_grid.set_target_count(10 - def_count - str_count)
            self._pitch_grid.set_counts(mid_counts)

    # ── Save ──

    def _on_save(self):
        """Save formation and positions back to squad.json."""
        mid_positions = self._pitch_grid.get_positions()
        formation_str = derive_formation_string(
            self._def_count, mid_positions, self._str_count,
        )

        # Update team formation string
        self._team.formation = formation_str

        # Update player positions from slot assignments
        assigned_positions: dict[int, str] = {}
        for slot in self._formation_slots:
            if slot.player:
                assigned_positions[slot.player.jersey_number] = slot.position

        for player in self._team.players:
            if player.jersey_number in assigned_positions:
                player.position = assigned_positions[player.jersey_number]

        # Save to disk
        save_squad_json(self._squad_json_path, self._squad_data)

        self.formation_saved.emit(self._squad_data)
        self.accept()


# ── Helpers ──

def _clear_layout(layout):
    """Recursively clear a QLayout."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())
