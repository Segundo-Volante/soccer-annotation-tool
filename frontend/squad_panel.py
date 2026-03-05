"""Squad Sheet panel — shows both teams' players with reference crops.

Supports click-to-assign: select a bounding box on canvas, then click a player
row to instantly assign that player to the box.

Two display modes:
  - **List View** (default): vertical scrollable list of all players.
  - **Formation View**: tactical formation diagram for the home team, with
    substitutes and a compact away-team list below.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QTimer
from PyQt6.QtGui import QColor, QPixmap, QIcon, QPainter, QBrush, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QTabWidget, QGridLayout, QCheckBox,
)

from backend.models import BoundingBox, Category, Player
from backend.squad_loader import SquadData, TeamSquad


# ── Design tokens ──
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
_DISABLED_TEXT = "#555570"

_CROP_DISPLAY_SIZE = 36  # px in the squad sheet
_ENLARGE_SIZE = 160  # px for hover popup
_PLACEHOLDER_COLOR = "#404060"

_NODE_CROP_SIZE = 32  # px for formation node crop
_NODE_DEFAULT_WIDTH = 60
_NODE_HEIGHT = 70


class CropPopup(QLabel):
    """Floating popup that shows an enlarged player photo on hover."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setFixedSize(_ENLARGE_SIZE, _ENLARGE_SIZE)
        self.setStyleSheet(
            f"background: {_CARD}; border: 2px solid {_ACCENT}; border-radius: 6px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def show_for(self, pixmap: QPixmap, global_pos: QPoint):
        """Display the enlarged pixmap near the given global position."""
        scaled = pixmap.scaled(
            _ENLARGE_SIZE - 4, _ENLARGE_SIZE - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        # Position to the left of the panel, offset up so it's near the row
        self.move(global_pos.x() - _ENLARGE_SIZE - 12, global_pos.y() - _ENLARGE_SIZE // 2)
        self.show()


class PlayerRow(QWidget):
    """A single player row in the squad sheet."""

    clicked = pyqtSignal(str, int, str, str)  # side, jersey_number, name, position

    def __init__(self, player: Player, side: str, team_color: str, parent=None):
        super().__init__(parent)
        self._player = player
        self._side = side  # "home" or "away"
        self._team_color = team_color
        self._assigned = False
        self._enabled_for_click = True
        self._crop_pixmap: Optional[QPixmap] = None

        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        # Reference crop / placeholder
        self._crop_label = QLabel()
        self._crop_label.setFixedSize(_CROP_DISPLAY_SIZE, _CROP_DISPLAY_SIZE)
        self._crop_label.setStyleSheet(
            f"background: {_PLACEHOLDER_COLOR}; border-radius: 4px; border: none;"
        )
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_placeholder_crop()
        layout.addWidget(self._crop_label)

        # Jersey number (bold, larger font)
        self._number_label = QLabel(str(player.jersey_number))
        self._number_label.setFixedWidth(28)
        self._number_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._number_label.setStyleSheet(
            f"color: {team_color}; font-weight: bold; font-size: 14px; border: none;"
        )
        layout.addWidget(self._number_label)

        # Player name + position
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        self._name_label = QLabel(player.name)
        self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 12px; border: none;")
        info_layout.addWidget(self._name_label)

        if player.position:
            self._pos_label = QLabel(player.position)
            self._pos_label.setStyleSheet(f"color: {_MUTED}; font-size: 10px; border: none;")
            info_layout.addWidget(self._pos_label)
        else:
            self._pos_label = None

        layout.addLayout(info_layout, stretch=1)

        # Check mark (visible when assigned on current frame)
        self._check_label = QLabel("")
        self._check_label.setFixedWidth(20)
        self._check_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check_label.setStyleSheet(
            f"color: {_CHECK_COLOR}; font-size: 16px; font-weight: bold; border: none;"
        )
        layout.addWidget(self._check_label)

    def _set_placeholder_crop(self):
        """Draw a generic silhouette placeholder."""
        pm = QPixmap(_CROP_DISPLAY_SIZE, _CROP_DISPLAY_SIZE)
        pm.fill(QColor(_PLACEHOLDER_COLOR))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Simple person icon
        c = _CROP_DISPLAY_SIZE // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#606080")))
        # Head
        painter.drawEllipse(c - 6, 6, 12, 12)
        # Body
        painter.drawEllipse(c - 10, 20, 20, 14)
        painter.end()
        self._crop_label.setPixmap(pm)

    def set_reference_crop(self, pixmap: QPixmap):
        """Set the reference crop image."""
        self._crop_pixmap = pixmap
        scaled = pixmap.scaled(
            _CROP_DISPLAY_SIZE, _CROP_DISPLAY_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_label.setPixmap(scaled)
        self._crop_label.setStyleSheet(
            f"border-radius: 4px; border: 1px solid {_BORDER};"
        )

    def has_crop(self) -> bool:
        """Return True if this row has a reference crop/headshot image."""
        return self._crop_pixmap is not None and not self._crop_pixmap.isNull()

    def set_assigned(self, assigned: bool):
        """Mark or unmark this player as assigned on the current frame."""
        self._assigned = assigned
        self._check_label.setText("\u2713" if assigned else "")
        # Gray out if already assigned (prevent double-assigning)
        if assigned:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._name_label.setStyleSheet(f"color: {_DISABLED_TEXT}; font-size: 12px; border: none;")
            self._number_label.setStyleSheet(
                f"color: {_DISABLED_TEXT}; font-weight: bold; font-size: 14px; border: none;"
            )
            if self._pos_label:
                self._pos_label.setStyleSheet(f"color: {_DISABLED_TEXT}; font-size: 10px; border: none;")
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 12px; border: none;")
            self._number_label.setStyleSheet(
                f"color: {self._team_color}; font-weight: bold; font-size: 14px; border: none;"
            )
            if self._pos_label:
                self._pos_label.setStyleSheet(f"color: {_MUTED}; font-size: 10px; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._assigned:
            self.clicked.emit(
                self._side,
                self._player.jersey_number,
                self._player.name,
                self._player.position,
            )
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._assigned:
            self.setStyleSheet(f"PlayerRow {{ background: {_HOVER_BG}; border-radius: 4px; }}")
        # Show enlarged crop popup
        if self._crop_pixmap and not self._crop_pixmap.isNull():
            panel = self._find_squad_panel()
            if panel:
                panel.show_crop_popup(self._crop_pixmap, self.mapToGlobal(QPoint(0, self.height() // 2)))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("")
        panel = self._find_squad_panel()
        if panel:
            panel.hide_crop_popup()
        super().leaveEvent(event)

    def _find_squad_panel(self) -> Optional["SquadPanel"]:
        """Walk up the parent chain to find the owning SquadPanel."""
        w = self.parent()
        while w is not None:
            if isinstance(w, SquadPanel):
                return w
            w = w.parent()
        return None

    @property
    def jersey_number(self) -> int:
        return self._player.jersey_number

    @property
    def side(self) -> str:
        return self._side


# ═══════════════════════════════════════════════════════════════
#  FormationNode — compact player card for the Formation View
# ═══════════════════════════════════════════════════════════════


class FormationNode(QWidget):
    """A compact clickable player node for the formation overlay view."""

    clicked = pyqtSignal(str, int, str, str)  # side, jersey_number, name, position

    def __init__(
        self, player: Player, side: str, team_color: str,
        node_width: int = _NODE_DEFAULT_WIDTH, parent=None,
    ):
        super().__init__(parent)
        self._player = player
        self._side = side
        self._team_color = team_color
        self._assigned = False
        self._crop_pixmap: Optional[QPixmap] = None
        self._node_width = node_width

        self.setFixedSize(node_width, _NODE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._update_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Crop image
        self._crop_label = QLabel()
        self._crop_label.setFixedSize(_NODE_CROP_SIZE, _NODE_CROP_SIZE)
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_placeholder_crop()
        layout.addWidget(self._crop_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Jersey number (bold)
        self._number_label = QLabel(str(self._player.jersey_number))
        self._number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._number_label.setStyleSheet(
            f"color: {self._team_color}; font-weight: bold; font-size: 11px; border: none;"
        )
        layout.addWidget(self._number_label)

        # Player surname (compact)
        parts = self._player.name.split() if self._player.name else []
        display_name = parts[-1] if parts else ""
        # Truncate if too long for the node width
        max_chars = max(4, self._node_width // 7)
        if len(display_name) > max_chars:
            display_name = display_name[:max_chars - 1] + "\u2026"
        self._name_label = QLabel(display_name)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 8px; border: none;")
        layout.addWidget(self._name_label)

        # Position (dimmed, tiny)
        if self._player.position:
            self._pos_label = QLabel(f"({self._player.position})")
            self._pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._pos_label.setStyleSheet(f"color: {_MUTED}; font-size: 7px; border: none;")
            layout.addWidget(self._pos_label)
        else:
            self._pos_label = None

    def _set_placeholder_crop(self):
        """Draw a generic silhouette placeholder."""
        pm = QPixmap(_NODE_CROP_SIZE, _NODE_CROP_SIZE)
        pm.fill(QColor(_PLACEHOLDER_COLOR))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = _NODE_CROP_SIZE // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#606080")))
        painter.drawEllipse(c - 5, 4, 10, 10)   # Head
        painter.drawEllipse(c - 8, 16, 16, 12)  # Body
        painter.end()
        self._crop_label.setPixmap(pm)

    def _update_style(self):
        """Apply visual style based on assignment state."""
        if self._assigned:
            self.setStyleSheet(
                f"FormationNode {{ background: rgba(39, 174, 96, 0.2);"
                f" border: 1px solid {_CHECK_COLOR}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(
                f"FormationNode {{ background: {_CARD};"
                f" border: 1px solid {_ACCENT}; border-radius: 6px; }}"
            )

    def set_reference_crop(self, pixmap: QPixmap):
        """Set the reference crop image."""
        self._crop_pixmap = pixmap
        scaled = pixmap.scaled(
            _NODE_CROP_SIZE, _NODE_CROP_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_label.setPixmap(scaled)
        self._crop_label.setStyleSheet(
            f"border-radius: 4px; border: 1px solid {_BORDER};"
        )

    def has_crop(self) -> bool:
        return self._crop_pixmap is not None and not self._crop_pixmap.isNull()

    def set_assigned(self, assigned: bool):
        """Mark or unmark this player as assigned on the current frame."""
        self._assigned = assigned
        self._update_style()
        if assigned:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._number_label.setStyleSheet(
                f"color: {_CHECK_COLOR}; font-weight: bold; font-size: 11px; border: none;"
            )
            self._name_label.setStyleSheet(f"color: {_DISABLED_TEXT}; font-size: 8px; border: none;")
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._number_label.setStyleSheet(
                f"color: {self._team_color}; font-weight: bold; font-size: 11px; border: none;"
            )
            self._name_label.setStyleSheet(f"color: {_TEXT}; font-size: 8px; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._assigned:
            self.clicked.emit(
                self._side,
                self._player.jersey_number,
                self._player.name,
                self._player.position,
            )
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._assigned:
            self.setStyleSheet(
                f"FormationNode {{ background: {_HOVER_BG};"
                f" border: 1px solid {_ACCENT}; border-radius: 6px; }}"
            )
        if self._crop_pixmap and not self._crop_pixmap.isNull():
            panel = self._find_squad_panel()
            if panel:
                panel.show_crop_popup(self._crop_pixmap, self.mapToGlobal(QPoint(0, self.height() // 2)))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style()
        panel = self._find_squad_panel()
        if panel:
            panel.hide_crop_popup()
        super().leaveEvent(event)

    def _find_squad_panel(self) -> Optional["SquadPanel"]:
        """Walk up the parent chain to find the owning SquadPanel."""
        w = self.parent()
        while w is not None:
            if isinstance(w, SquadPanel):
                return w
            w = w.parent()
        return None

    @property
    def jersey_number(self) -> int:
        return self._player.jersey_number

    @property
    def side(self) -> str:
        return self._side


# ═══════════════════════════════════════════════════════════════
#  FormationView — tactical formation diagram tab
# ═══════════════════════════════════════════════════════════════

_SCROLL_STYLE = f"""
    QScrollArea {{ background: {_BG}; border: none; }}
    QScrollBar:vertical {{
        background: {_CARD}; width: 6px; border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: #505070; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
"""

_QUICK_BTN_STYLE = f"""
    QPushButton {{
        background: {_CARD}; color: {_TEXT};
        padding: 6px 8px; border-radius: 4px;
        font-size: 11px; border: 1px solid {_BORDER};
        text-align: left;
    }}
    QPushButton:hover {{ background: {_HOVER_BG}; border-color: {_ACCENT}; }}
"""


class FormationView(QWidget):
    """Formation overlay view showing the home team in tactical formation."""

    player_clicked = pyqtSignal(str, int, str, str)
    quick_assign_clicked = pyqtSignal(str)
    edit_formation_requested = pyqtSignal(str)  # team_side ("home" or "away")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._formation_nodes: list[FormationNode] = []
        self._away_nodes: list[FormationNode] = []
        self._squad_data: Optional[SquadData] = None
        self._session_folder: Optional[str] = None
        self._show_opponent: bool = True
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_SCROLL_STYLE)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(4)

        self._placeholder = QLabel("No formation data available")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {_MUTED}; font-size: 11px; padding: 20px;")
        self._placeholder.setWordWrap(True)
        self._content_layout.addWidget(self._placeholder)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, stretch=1)

    def load_formation(self, squad_data: SquadData, session_folder: str,
                       show_opponent: bool = True):
        """Build the formation view from squad data."""
        self._squad_data = squad_data
        self._session_folder = session_folder
        self._show_opponent = show_opponent
        self._formation_nodes.clear()
        self._away_nodes.clear()

        # Clear existing content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # recursively clear sublayouts
                self._clear_layout(item.layout())

        from backend.formation_utils import assign_players_to_formation

        formation_rows, substitutes = assign_players_to_formation(
            squad_data.home_team,
        )

        available_width = 248  # 260px panel - 2×4px margins - scroll bar

        if not formation_rows:
            # Show setup prompt with button
            self._add_setup_prompt("home", squad_data.home_team, available_width)

            # Away team section (if opponent visible and has players)
            if show_opponent and squad_data.away_team.players:
                self._add_separator()
                self._add_away_section(squad_data, available_width)

            # Quick Assign buttons
            self._add_separator()
            self._add_quick_assign_section()
            self._content_layout.addStretch()
            return

        # ── Dynamic node width ──
        max_row_size = max(len(row) for row in formation_rows)
        if max_row_size > 1:
            node_width = min(
                _NODE_DEFAULT_WIDTH,
                (available_width - (max_row_size - 1) * 4) // max_row_size,
            )
        else:
            node_width = _NODE_DEFAULT_WIDTH

        # ── Formation header with Edit button ──
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        name = squad_data.home_team.name or "Home Team"
        header = QLabel(f"\u2014\u2014 {name} ({squad_data.home_team.formation}) \u2014\u2014")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"color: {_HOME_COLOR}; font-weight: bold; font-size: 11px; padding: 4px 0;"
        )
        header_layout.addWidget(header, stretch=1)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedSize(36, 20)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(
            f"QPushButton {{ background: {_CARD}; color: {_MUTED}; font-size: 9px;"
            f" border: 1px solid {_BORDER}; border-radius: 3px; padding: 0; }}"
            f"QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}"
        )
        edit_btn.clicked.connect(lambda: self.edit_formation_requested.emit("home"))
        header_layout.addWidget(edit_btn)

        self._content_layout.addWidget(header_widget)

        # ── Formation rows (reversed: forwards at top, GK at bottom) ──
        for row_players in reversed(formation_rows):
            if not row_players:
                continue
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.setSpacing(4)

            for player in row_players:
                node = FormationNode(player, "home", _HOME_COLOR, node_width=node_width)
                node.clicked.connect(self._on_node_clicked)
                self._formation_nodes.append(node)
                row_layout.addWidget(node)

            self._content_layout.addWidget(row_widget)

        # ── Substitutes section ──
        if substitutes:
            self._add_separator()
            sub_header = QLabel("\u2014\u2014 Substitutes \u2014\u2014")
            sub_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_header.setStyleSheet(
                f"color: {_MUTED}; font-weight: bold; font-size: 10px; padding: 2px 0;"
            )
            self._content_layout.addWidget(sub_header)

            sub_widget = QWidget()
            cols = max(3, available_width // (node_width + 4))
            sub_grid = QGridLayout(sub_widget)
            sub_grid.setSpacing(4)
            sub_grid.setContentsMargins(0, 0, 0, 0)

            for i, player in enumerate(substitutes):
                row_idx, col_idx = divmod(i, cols)
                node = FormationNode(player, "home", _HOME_COLOR, node_width=node_width)
                node.clicked.connect(self._on_node_clicked)
                self._formation_nodes.append(node)
                sub_grid.addWidget(node, row_idx, col_idx, Qt.AlignmentFlag.AlignCenter)

            self._content_layout.addWidget(sub_widget)

        # ── Away team section ──
        if show_opponent and squad_data.away_team.players:
            self._add_separator()
            self._add_away_section(squad_data, available_width)

        # ── Quick Assign buttons ──
        self._add_separator()
        self._add_quick_assign_section()

        self._content_layout.addStretch()

        # Load reference crops
        self._load_reference_crops()

    def _add_setup_prompt(self, side: str, team: TeamSquad, available_width: int):
        """Show a 'Set Up Formation' prompt for a team with no formation."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(8)

        team_name = team.name or (side.title() + " Team")
        name_label = QLabel(f"\u2014\u2014 {team_name} \u2014\u2014")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = _HOME_COLOR if side == "home" else _AWAY_COLOR
        name_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px; padding: 4px 0;"
        )
        container_layout.addWidget(name_label)

        # Check why formation is missing
        has_formation_str = bool(team.formation.strip() if team.formation else False)
        has_positions = any(p.position for p in team.players)

        if not has_formation_str and not has_positions:
            reason = "No formation or positions configured."
        elif has_formation_str and not has_positions:
            reason = "Formation set but players have no positions."
        else:
            reason = "Formation data incomplete."

        reason_label = QLabel(reason)
        reason_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reason_label.setStyleSheet(f"color: {_MUTED}; font-size: 10px;")
        reason_label.setWordWrap(True)
        container_layout.addWidget(reason_label)

        setup_btn = QPushButton("  Set Up Formation  ")
        setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        setup_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_ACCENT}; color: #FFFFFF;"
            f" padding: 8px 16px; border-radius: 4px; font-weight: bold;"
            f" font-size: 11px; border: none; min-height: 20px; }}"
            f"QPushButton:hover {{ background-color: #FFB84D; }}"
        )
        setup_btn.clicked.connect(lambda: self.edit_formation_requested.emit(side))
        container_layout.addWidget(setup_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._content_layout.addWidget(container)

    def _add_away_section(self, squad_data: SquadData, available_width: int):
        """Add the away team section — in formation if available, grid otherwise."""
        from backend.formation_utils import assign_players_to_formation

        away_name = squad_data.away_team.name or "Away Team"

        # Try to render away team in formation
        away_rows, away_subs = assign_players_to_formation(squad_data.away_team)

        if away_rows:
            # Away team has formation — render in tactical rows
            max_row_size = max(len(row) for row in away_rows)
            if max_row_size > 1:
                node_width = min(
                    _NODE_DEFAULT_WIDTH,
                    (available_width - (max_row_size - 1) * 4) // max_row_size,
                )
            else:
                node_width = _NODE_DEFAULT_WIDTH

            # Header with Edit button
            header_widget = QWidget()
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(4)

            header = QLabel(
                f"\u2014\u2014 {away_name} ({squad_data.away_team.formation}) \u2014\u2014"
            )
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(
                f"color: {_AWAY_COLOR}; font-weight: bold; font-size: 10px; padding: 2px 0;"
            )
            header_layout.addWidget(header, stretch=1)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedSize(36, 20)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setStyleSheet(
                f"QPushButton {{ background: {_CARD}; color: {_MUTED}; font-size: 9px;"
                f" border: 1px solid {_BORDER}; border-radius: 3px; padding: 0; }}"
                f"QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}"
            )
            edit_btn.clicked.connect(lambda: self.edit_formation_requested.emit("away"))
            header_layout.addWidget(edit_btn)

            self._content_layout.addWidget(header_widget)

            # Formation rows (reversed: forwards top, GK bottom)
            for row_players in reversed(away_rows):
                if not row_players:
                    continue
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 2, 0, 2)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                row_layout.setSpacing(4)

                for player in row_players:
                    node = FormationNode(player, "away", _AWAY_COLOR, node_width=node_width)
                    node.clicked.connect(self._on_node_clicked)
                    self._away_nodes.append(node)
                    row_layout.addWidget(node)

                self._content_layout.addWidget(row_widget)

            # Away substitutes
            if away_subs:
                sub_header = QLabel("\u2014\u2014 Away Subs \u2014\u2014")
                sub_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sub_header.setStyleSheet(
                    f"color: {_MUTED}; font-weight: bold; font-size: 9px; padding: 2px 0;"
                )
                self._content_layout.addWidget(sub_header)

                sub_widget = QWidget()
                cols = max(3, available_width // (node_width + 4))
                sub_grid = QGridLayout(sub_widget)
                sub_grid.setSpacing(4)
                sub_grid.setContentsMargins(0, 0, 0, 0)

                for i, player in enumerate(away_subs):
                    row_idx, col_idx = divmod(i, cols)
                    node = FormationNode(player, "away", _AWAY_COLOR, node_width=node_width)
                    node.clicked.connect(self._on_node_clicked)
                    self._away_nodes.append(node)
                    sub_grid.addWidget(node, row_idx, col_idx, Qt.AlignmentFlag.AlignCenter)

                self._content_layout.addWidget(sub_widget)

        elif squad_data.away_team.players:
            # No away formation — show setup prompt or flat grid
            has_formation_str = bool(
                squad_data.away_team.formation.strip()
                if squad_data.away_team.formation else False
            )
            if not has_formation_str:
                # Show setup button for away team
                self._add_setup_prompt("away", squad_data.away_team, available_width)
            else:
                # Has formation string but assignment failed — flat grid fallback
                away_header = QLabel(f"\u2014\u2014 {away_name} \u2014\u2014")
                away_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                away_header.setStyleSheet(
                    f"color: {_AWAY_COLOR}; font-weight: bold; font-size: 10px; padding: 2px 0;"
                )
                self._content_layout.addWidget(away_header)

                node_width = _NODE_DEFAULT_WIDTH
                away_widget = QWidget()
                away_grid = QGridLayout(away_widget)
                away_grid.setSpacing(4)
                away_grid.setContentsMargins(0, 0, 0, 0)
                away_cols = max(3, available_width // (node_width + 4))

                for i, player in enumerate(squad_data.away_team.players):
                    row_idx, col_idx = divmod(i, away_cols)
                    node = FormationNode(player, "away", _AWAY_COLOR, node_width=node_width)
                    node.clicked.connect(self._on_node_clicked)
                    self._away_nodes.append(node)
                    away_grid.addWidget(node, row_idx, col_idx, Qt.AlignmentFlag.AlignCenter)

                self._content_layout.addWidget(away_widget)

    def _on_node_clicked(self, side: str, jersey: int, name: str, position: str):
        self.player_clicked.emit(side, jersey, name, position)

    def _add_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {_BORDER};")
        self._content_layout.addWidget(sep)

    def _add_quick_assign_section(self):
        """Add quick-assign buttons (same as List View)."""
        header = QLabel("\u2014\u2014 Quick Assign \u2014\u2014")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"color: {_MUTED}; font-weight: bold; font-size: 11px; padding: 4px 0;"
        )
        self._content_layout.addWidget(header)

        buttons = [
            ("Unknown Home Player", "unknown_home"),
            ("Unknown Away Player", "unknown_away"),
            ("Referee", "referee"),
            ("Ball", "ball"),
        ]
        for label, key in buttons:
            btn = QPushButton(f"  {label}")
            btn.setStyleSheet(_QUICK_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _checked, k=key: self.quick_assign_clicked.emit(k))
            self._content_layout.addWidget(btn)

    def update_assignments(self, boxes: list[BoundingBox]):
        """Update check marks / assignment state on all nodes."""
        assigned_set: set[tuple[str, int]] = set()
        for box in boxes:
            if box.jersey_number is not None and box.box_status.value != "pending":
                if box.category in (Category.HOME_PLAYER, Category.HOME_GK):
                    assigned_set.add(("home", box.jersey_number))
                elif box.category in (Category.OPPONENT, Category.OPPONENT_GK):
                    assigned_set.add(("away", box.jersey_number))

        for node in self._formation_nodes:
            node.set_assigned((node.side, node.jersey_number) in assigned_set)
        for node in self._away_nodes:
            node.set_assigned((node.side, node.jersey_number) in assigned_set)

    def update_reference_crop(self, side: str, jersey_number: int, crop_path: Path):
        """Update a single player node's reference crop."""
        if self._squad_data and self._squad_data.headshot_images:
            key = (side, jersey_number)
            if key in self._squad_data.headshot_images:
                return
        for node in self._formation_nodes + self._away_nodes:
            if node.side == side and node.jersey_number == jersey_number:
                pm = QPixmap(str(crop_path))
                if not pm.isNull():
                    node.set_reference_crop(pm)
                break

    def _load_reference_crops(self):
        """Load player images for all formation nodes."""
        if not self._squad_data:
            return
        headshot_loaded: set[tuple[str, int]] = set()

        # 1. SquadList headshots (primary)
        if self._squad_data.headshot_images:
            for node in self._formation_nodes + self._away_nodes:
                key = (node.side, node.jersey_number)
                img_path = self._squad_data.headshot_images.get(key)
                if img_path and img_path.exists():
                    pm = QPixmap(str(img_path))
                    if not pm.isNull():
                        node.set_reference_crop(pm)
                        headshot_loaded.add(key)

        # 2. Session reference crops (fallback)
        if not self._session_folder:
            return
        from backend.file_manager import FileManager
        for node in self._formation_nodes + self._away_nodes:
            key = (node.side, node.jersey_number)
            if key in headshot_loaded:
                continue
            crop_path = FileManager.load_reference_crop(
                self._session_folder, node.side, node.jersey_number,
            )
            if crop_path:
                pm = QPixmap(str(crop_path))
                if not pm.isNull():
                    node.set_reference_crop(pm)

    @staticmethod
    def _clear_layout(layout):
        """Recursively clear a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                FormationView._clear_layout(item.layout())


# ═══════════════════════════════════════════════════════════════
#  SquadPanel — main container with List View / Formation tabs
# ═══════════════════════════════════════════════════════════════


class SquadPanel(QWidget):
    """Squad Sheet panel showing both teams' players with click-to-assign."""

    # Emitted when a named player row is clicked: (side, jersey_number, name, position)
    player_clicked = pyqtSignal(str, int, str, str)
    # Emitted when a quick-assign button is clicked: (category_name,)
    quick_assign_clicked = pyqtSignal(str)
    # Emitted when user wants to edit formation: (team_side,)
    edit_formation_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._squad_data: Optional[SquadData] = None
        self._session_folder: Optional[str] = None
        self._player_rows: list[PlayerRow] = []
        self._assignment_mode = False  # True when a box is selected on canvas
        self._crop_popup: Optional[CropPopup] = None
        self._show_opponent = True
        self._away_widgets: list[QWidget] = []  # widgets to toggle for opponent visibility
        self._team_mode: str = "one_team"  # "one_team" or "all_team"

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title row with opponent toggle
        title_row = QHBoxLayout()
        title_row.setContentsMargins(4, 2, 4, 2)
        title_row.setSpacing(4)

        self._title = QLabel("Squad Sheet")
        self._title.setStyleSheet(
            f"color: {_ACCENT}; font-weight: bold; font-size: 12px;"
        )
        title_row.addWidget(self._title)
        title_row.addStretch()

        self._opponent_toggle = QCheckBox("Away")
        self._opponent_toggle.setChecked(True)
        self._opponent_toggle.setToolTip("Show/hide opponent squad")
        self._opponent_toggle.setStyleSheet(
            f"QCheckBox {{ color: {_AWAY_COLOR}; font-size: 10px; spacing: 3px; }}"
            f" QCheckBox::indicator {{ width: 12px; height: 12px; }}"
        )
        self._opponent_toggle.toggled.connect(self._on_opponent_toggled)
        title_row.addWidget(self._opponent_toggle)

        title_container = QWidget()
        title_container.setFixedHeight(24)
        title_container.setStyleSheet(f"background: {_CARD};")
        title_container.setLayout(title_row)
        outer.addWidget(title_container)

        # Assignment mode indicator
        self._mode_label = QLabel("")
        self._mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_label.setFixedHeight(18)
        self._mode_label.setStyleSheet(
            f"color: {_CHECK_COLOR}; font-size: 10px; font-weight: bold;"
            f" background: {_BG}; border: none;"
        )
        self._mode_label.setVisible(False)
        outer.addWidget(self._mode_label)

        # ── Tab Widget ──
        self._tab_widget = QTabWidget()
        self._tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none; background: {_BG};
            }}
            QTabBar::tab {{
                background: {_CARD}; color: {_MUTED};
                padding: 4px 12px; font-size: 10px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                margin-right: 1px;
            }}
            QTabBar::tab:selected {{
                background: {_ACCENT}; color: {_BG}; font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{ background: #404060; color: {_TEXT}; }}
            QTabBar::tab:disabled {{ color: {_DISABLED_TEXT}; background: #222233; }}
        """)

        # ── Tab 0: List View (existing behavior) ──
        self._list_view = QWidget()
        list_layout = QVBoxLayout(self._list_view)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(_SCROLL_STYLE)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(2)

        # Placeholder when no squad is loaded
        self._no_squad_label = QLabel(
            "No squad loaded\nAdd images to SquadList/ folder,\nload a squad.json, or use\nkeyboard shortcuts to annotate"
        )
        self._no_squad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_squad_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px; padding: 20px;")
        self._no_squad_label.setWordWrap(True)
        self._content_layout.addWidget(self._no_squad_label)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        list_layout.addWidget(self._scroll, stretch=1)

        self._tab_widget.addTab(self._list_view, "List View")

        # ── Tab 1: Formation View ──
        self._formation_view = FormationView()
        self._formation_view.player_clicked.connect(self._on_player_row_clicked)
        self._formation_view.quick_assign_clicked.connect(
            lambda key: self.quick_assign_clicked.emit(key)
        )
        self._formation_view.edit_formation_requested.connect(
            lambda side: self.edit_formation_requested.emit(side)
        )
        self._tab_widget.addTab(self._formation_view, "Formation")

        # Formation tab enabled when squad is loaded (shows setup prompt if no formation)
        self._tab_widget.setTabEnabled(1, False)
        self._tab_widget.setTabToolTip(
            1, "Load squad data to enable this view",
        )

        outer.addWidget(self._tab_widget, stretch=1)

    def load_squad(self, squad_data: SquadData, session_folder: str,
                   team_mode: str = "one_team"):
        """Load squad data and build the player list.

        Args:
            squad_data: SquadData with home and away team info.
            session_folder: Path to the session folder.
            team_mode: "one_team" (club analyst) or "all_team" (match analyst).
        """
        self._squad_data = squad_data
        self._session_folder = session_folder
        self._team_mode = team_mode

        # In All Team Mode, always show both teams and hide the opponent toggle
        if team_mode == "all_team":
            self._show_opponent = True
            self._opponent_toggle.setChecked(True)
            self._opponent_toggle.setVisible(False)
        else:
            self._opponent_toggle.setVisible(True)

        self._rebuild_player_list()

        # Formation view — always enabled when squad data is loaded
        if squad_data.is_loaded:
            self._tab_widget.setTabEnabled(1, True)
            self._formation_view.load_formation(
                squad_data, session_folder, show_opponent=self._show_opponent,
            )
            has_formation = bool(
                squad_data.home_team.formation.strip()
                if squad_data.home_team.formation else False
            )
            if has_formation:
                self._tab_widget.setTabToolTip(
                    1, f"Formation: {squad_data.home_team.formation}",
                )
            else:
                self._tab_widget.setTabToolTip(
                    1, "Click to set up formation",
                )
        else:
            self._tab_widget.setTabEnabled(1, False)
            self._tab_widget.setTabToolTip(
                1, "Load squad data to enable this view",
            )

    def _on_opponent_toggled(self, checked: bool):
        """Show or hide the away team section in both list view and formation view."""
        self._show_opponent = checked
        for w in self._away_widgets:
            w.setVisible(checked)
        # Also refresh formation view to show/hide away team
        if self._squad_data and self._squad_data.is_loaded:
            self._formation_view.load_formation(
                self._squad_data, self._session_folder,
                show_opponent=checked,
            )

    def _rebuild_player_list(self):
        """Clear and rebuild the player row list from squad data."""
        # Clear existing content
        self._player_rows.clear()
        self._away_widgets.clear()
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._squad_data or not self._squad_data.is_loaded:
            self._no_squad_label = QLabel(
                "No squad loaded\nAdd images to SquadList/ folder,\nload a squad.json, or use\nkeyboard shortcuts to annotate"
            )
            self._no_squad_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._no_squad_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px; padding: 20px;")
            self._no_squad_label.setWordWrap(True)
            self._content_layout.addWidget(self._no_squad_label)
            self._content_layout.addStretch()
            return

        # ── Home Team ──
        if self._squad_data.home_team.players:
            self._add_team_section(
                self._squad_data.home_team, "home", _HOME_COLOR,
            )

        # ── Away Team ──
        if self._squad_data.away_team.players:
            if self._squad_data.home_team.players:
                away_sep = self._add_separator()
                self._away_widgets.append(away_sep)
            self._add_team_section(
                self._squad_data.away_team, "away", _AWAY_COLOR,
                track_widgets=self._away_widgets,
            )
            # Show/hide based on current toggle state
            if not self._show_opponent:
                for w in self._away_widgets:
                    w.setVisible(False)

        # ── Quick Assign Buttons ──
        self._add_separator()
        self._add_quick_assign_section()

        self._content_layout.addStretch()

        # Load existing reference crops
        self._load_reference_crops()

    def _add_team_section(self, team: TeamSquad, side: str, color: str,
                          track_widgets: list[QWidget] | None = None):
        """Add a team header and all player rows."""
        # Team header — in All Team Mode use "Team 1" / "Team 2" fallback
        if team.name:
            header_text = f"\u2014\u2014 {team.name} \u2014\u2014"
        elif self._team_mode == "all_team":
            header_text = f"\u2014\u2014 {'Team 1' if side == 'home' else 'Team 2'} \u2014\u2014"
        else:
            header_text = f"\u2014\u2014 {side.title()} Team \u2014\u2014"
        header = QLabel(header_text)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; padding: 4px 0;")
        self._content_layout.addWidget(header)
        if track_widgets is not None:
            track_widgets.append(header)

        # Player rows
        for player in team.players:
            row = PlayerRow(player, side, color)
            row.clicked.connect(self._on_player_row_clicked)
            self._player_rows.append(row)
            self._content_layout.addWidget(row)
            if track_widgets is not None:
                track_widgets.append(row)

    def _add_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {_BORDER};")
        self._content_layout.addWidget(sep)
        return sep

    def _add_quick_assign_section(self):
        """Add quick-assign buttons for Unknown Home/Away, Referee, Ball."""
        header = QLabel("\u2014\u2014 Quick Assign \u2014\u2014")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"color: {_MUTED}; font-weight: bold; font-size: 11px; padding: 4px 0;")
        self._content_layout.addWidget(header)

        buttons = [
            ("Unknown Home Player", "unknown_home"),
            ("Unknown Away Player", "unknown_away"),
            ("Referee", "referee"),
            ("Ball", "ball"),
        ]

        for label, key in buttons:
            btn = QPushButton(f"  {label}")
            btn.setStyleSheet(_QUICK_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _checked, k=key: self.quick_assign_clicked.emit(k))
            self._content_layout.addWidget(btn)

    def _on_player_row_clicked(self, side: str, jersey: int, name: str, position: str):
        """Forward player click to parent."""
        self.player_clicked.emit(side, jersey, name, position)

    def _load_reference_crops(self):
        """Load player images: SquadList headshots are primary, session crops fill gaps."""
        headshot_loaded: set[tuple[str, int]] = set()

        # 1. Load headshot images from SquadList folder (primary — these are clear portraits)
        if self._squad_data and self._squad_data.headshot_images:
            for row in self._player_rows:
                key = (row.side, row.jersey_number)
                img_path = self._squad_data.headshot_images.get(key)
                if img_path and img_path.exists():
                    pm = QPixmap(str(img_path))
                    if not pm.isNull():
                        row.set_reference_crop(pm)
                        headshot_loaded.add(key)

        # 2. Fill gaps with session-specific reference crops (only for players without headshots)
        if not self._session_folder:
            return
        from backend.file_manager import FileManager
        for row in self._player_rows:
            key = (row.side, row.jersey_number)
            if key in headshot_loaded:
                continue  # Don't override SquadList headshots
            crop_path = FileManager.load_reference_crop(
                self._session_folder, row.side, row.jersey_number,
            )
            if crop_path:
                pm = QPixmap(str(crop_path))
                if not pm.isNull():
                    row.set_reference_crop(pm)

    def update_reference_crop(self, side: str, jersey_number: int, crop_path: Path):
        """Update a single player's reference crop after saving a new one.

        Only updates if the player has no SquadList headshot (headshots are better
        quality portraits and should remain the primary image).
        """
        # Don't override SquadList headshots with small bounding-box crops
        if self._squad_data and self._squad_data.headshot_images:
            key = (side, jersey_number)
            if key in self._squad_data.headshot_images:
                return
        for row in self._player_rows:
            if row.side == side and row.jersey_number == jersey_number:
                pm = QPixmap(str(crop_path))
                if not pm.isNull():
                    row.set_reference_crop(pm)
                break

        # Also update formation view
        if self._tab_widget.isTabEnabled(1):
            self._formation_view.update_reference_crop(side, jersey_number, crop_path)

    def update_assignments(self, boxes: list[BoundingBox]):
        """Update check marks based on boxes on the current frame."""
        # Build a set of (side, jersey_number) that are assigned on this frame
        assigned_set: set[tuple[str, int]] = set()
        for box in boxes:
            if box.jersey_number is not None and box.box_status.value != "pending":
                if box.category in (Category.HOME_PLAYER, Category.HOME_GK):
                    assigned_set.add(("home", box.jersey_number))
                elif box.category in (Category.OPPONENT, Category.OPPONENT_GK):
                    assigned_set.add(("away", box.jersey_number))

        for row in self._player_rows:
            row.set_assigned((row.side, row.jersey_number) in assigned_set)

        # Also update formation view
        if self._tab_widget.isTabEnabled(1):
            self._formation_view.update_assignments(boxes)

    def set_assignment_mode(self, active: bool):
        """Show/hide the assignment mode indicator."""
        self._assignment_mode = active
        if active:
            self._mode_label.setText("\u25B6 Click a player to assign")
            self._mode_label.setVisible(True)
        else:
            self._mode_label.setVisible(False)

    def show_crop_popup(self, pixmap: QPixmap, global_pos: QPoint):
        """Show enlarged crop popup at the given position."""
        if self._crop_popup is None:
            self._crop_popup = CropPopup()
        self._crop_popup.show_for(pixmap, global_pos)

    def hide_crop_popup(self):
        """Hide the enlarged crop popup."""
        if self._crop_popup is not None:
            self._crop_popup.hide()

    @property
    def has_squad(self) -> bool:
        return self._squad_data is not None and self._squad_data.is_loaded
