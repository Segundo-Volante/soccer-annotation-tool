"""Squad Sheet panel — shows both teams' players with reference crops.

Supports click-to-assign: select a bounding box on canvas, then click a player
row to instantly assign that player to the box.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QTimer
from PyQt6.QtGui import QColor, QPixmap, QIcon, QPainter, QBrush, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
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


class SquadPanel(QWidget):
    """Squad Sheet panel showing both teams' players with click-to-assign."""

    # Emitted when a named player row is clicked: (side, jersey_number, name, position)
    player_clicked = pyqtSignal(str, int, str, str)
    # Emitted when a quick-assign button is clicked: (category_name,)
    quick_assign_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._squad_data: Optional[SquadData] = None
        self._session_folder: Optional[str] = None
        self._player_rows: list[PlayerRow] = []
        self._assignment_mode = False  # True when a box is selected on canvas
        self._crop_popup: Optional[CropPopup] = None

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title
        self._title = QLabel("Squad Sheet")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setFixedHeight(24)
        self._title.setStyleSheet(
            f"color: {_ACCENT}; font-weight: bold; font-size: 12px;"
            f" background: {_CARD}; padding: 2px;"
        )
        outer.addWidget(self._title)

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

        # Scrollable content area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
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
        """)

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
        outer.addWidget(self._scroll, stretch=1)

    def load_squad(self, squad_data: SquadData, session_folder: str):
        """Load squad data and build the player list."""
        self._squad_data = squad_data
        self._session_folder = session_folder
        self._rebuild_player_list()

    def _rebuild_player_list(self):
        """Clear and rebuild the player row list from squad data."""
        # Clear existing content
        self._player_rows.clear()
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
                self._add_separator()
            self._add_team_section(
                self._squad_data.away_team, "away", _AWAY_COLOR,
            )

        # ── Quick Assign Buttons ──
        self._add_separator()
        self._add_quick_assign_section()

        self._content_layout.addStretch()

        # Load existing reference crops
        self._load_reference_crops()

    def _add_team_section(self, team: TeamSquad, side: str, color: str):
        """Add a team header and all player rows."""
        # Team header
        header_text = f"\u2014\u2014 {team.name} \u2014\u2014" if team.name else f"\u2014\u2014 {side.title()} Team \u2014\u2014"
        header = QLabel(header_text)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; padding: 4px 0;")
        self._content_layout.addWidget(header)

        # Player rows
        for player in team.players:
            row = PlayerRow(player, side, color)
            row.clicked.connect(self._on_player_row_clicked)
            self._player_rows.append(row)
            self._content_layout.addWidget(row)

    def _add_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {_BORDER};")
        self._content_layout.addWidget(sep)

    def _add_quick_assign_section(self):
        """Add quick-assign buttons for Unknown Home/Away, Referee, Ball."""
        header = QLabel("\u2014\u2014 Quick Assign \u2014\u2014")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"color: {_MUTED}; font-weight: bold; font-size: 11px; padding: 4px 0;")
        self._content_layout.addWidget(header)

        btn_style = f"""
            QPushButton {{
                background: {_CARD}; color: {_TEXT};
                padding: 6px 8px; border-radius: 4px;
                font-size: 11px; border: 1px solid {_BORDER};
                text-align: left;
            }}
            QPushButton:hover {{ background: {_HOVER_BG}; border-color: {_ACCENT}; }}
        """

        buttons = [
            ("Unknown Home Player", "unknown_home"),
            ("Unknown Away Player", "unknown_away"),
            ("Referee", "referee"),
            ("Ball", "ball"),
        ]

        for label, key in buttons:
            btn = QPushButton(f"  {label}")
            btn.setStyleSheet(btn_style)
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
