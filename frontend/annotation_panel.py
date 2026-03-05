from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel, QPushButton,
    QFrame, QSplitter,
)

from backend.i18n import t
from backend.models import BoundingBox, BoxStatus, Category, CATEGORY_NAMES, Occlusion
from frontend.squad_panel import SquadPanel

CATEGORY_COLORS = {
    Category.HOME_PLAYER: QColor("#E74C3C"),
    Category.OPPONENT: QColor("#3498DB"),
    Category.HOME_GK: QColor("#E67E22"),
    Category.OPPONENT_GK: QColor("#2980B9"),
    Category.REFEREE: QColor("#F1C40F"),
    Category.BALL: QColor("#2ECC71"),
}


class AnnotationPanel(QWidget):
    box_clicked = pyqtSignal(int)  # box index
    box_double_clicked = pyqtSignal(int)
    delete_requested = pyqtSignal()
    sequence_badge_clicked = pyqtSignal(str)  # sequence_id - emitted when badge clicked
    accept_all_inherited = pyqtSignal()
    clear_inherited = pyqtSignal()
    show_out_of_frame_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # ── Vertical Splitter: Squad Panel (top) | Box List (bottom) ──
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet("""
            QSplitter::handle {
                background: #404060; border-radius: 2px;
            }
            QSplitter::handle:hover {
                background: #F5A623;
            }
        """)

        # ── Top section: Squad Panel ──
        self._squad_panel = SquadPanel()
        self._splitter.addWidget(self._squad_panel)

        # ── Bottom section: Box List + Controls ──
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        bottom_layout.setSpacing(4)

        self._title = QLabel(t("panel.annotations_title"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("color: #E8E8F0; font-weight: bold; font-size: 12px;")
        bottom_layout.addWidget(self._title)

        # Sequence badge (visible only when frame belongs to a sequence)
        self._seq_badge = QPushButton("")
        self._seq_badge.setVisible(False)
        self._seq_badge.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._seq_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._seq_badge.setStyleSheet("""
            QPushButton { background: #2A2A3C; color: #F5A623; border: 1px solid #F5A623;
                          border-radius: 3px; font-size: 10px; padding: 2px 6px; }
            QPushButton:hover { background: #3A3A4C; }
        """)
        self._seq_badge.clicked.connect(self._on_seq_badge_clicked)
        bottom_layout.addWidget(self._seq_badge)

        self._current_seq_id: str = ""

        # Pending counter (visible only when pending/unsure boxes exist)
        self._pending_counter = QLabel("")
        self._pending_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_counter.setStyleSheet(
            "color: #F5A623; font-weight: bold; font-size: 10px; padding: 2px;"
        )
        self._pending_counter.setVisible(False)
        bottom_layout.addWidget(self._pending_counter)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background: #2A2A3C; border: 1px solid #404060; border-radius: 4px; }
            QListWidget::item { padding: 3px; border-radius: 3px; margin: 1px; font-size: 11px; }
            QListWidget::item:selected { background: #3A5A3A; border: 1px solid #5A5; }
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        bottom_layout.addWidget(self._list)

        self._delete_btn = QPushButton(t("button.delete_selected"))
        self._delete_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._delete_btn.setStyleSheet("""
            QPushButton { background: #C0392B; color: white; padding: 5px;
                          border-radius: 3px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #E74C3C; }
        """)
        self._delete_btn.clicked.connect(self.delete_requested.emit)
        bottom_layout.addWidget(self._delete_btn)

        # Inheritance controls (visible only when inherited boxes exist)
        self._inherit_frame = QFrame()
        self._inherit_frame.setVisible(False)
        inherit_layout = QHBoxLayout(self._inherit_frame)
        inherit_layout.setContentsMargins(0, 4, 0, 0)
        inherit_layout.setSpacing(4)

        self._accept_all_btn = QPushButton("Accept All")
        self._accept_all_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accept_all_btn.setStyleSheet("""
            QPushButton { background: #27AE60; color: white; padding: 4px 8px;
                          border-radius: 3px; font-size: 10px; font-weight: bold; }
            QPushButton:hover { background: #2ECC71; }
        """)
        self._accept_all_btn.clicked.connect(self.accept_all_inherited.emit)
        inherit_layout.addWidget(self._accept_all_btn)

        self._clear_inherit_btn = QPushButton("Clear Inherited")
        self._clear_inherit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._clear_inherit_btn.setStyleSheet("""
            QPushButton { background: #7F8C8D; color: white; padding: 4px 8px;
                          border-radius: 3px; font-size: 10px; font-weight: bold; }
            QPushButton:hover { background: #95A5A6; }
        """)
        self._clear_inherit_btn.clicked.connect(self.clear_inherited.emit)
        inherit_layout.addWidget(self._clear_inherit_btn)

        bottom_layout.addWidget(self._inherit_frame)

        # Out-of-frame toggle
        self._oof_toggle = QPushButton("Show Out-of-Frame")
        self._oof_toggle.setCheckable(True)
        self._oof_toggle.setVisible(False)
        self._oof_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._oof_toggle.setStyleSheet("""
            QPushButton { background: #2A2A3C; color: #888; border: 1px solid #404060;
                          border-radius: 3px; font-size: 10px; padding: 3px 6px; }
            QPushButton:checked { background: #3A3A4C; color: #CCC; border-color: #F5A623; }
        """)
        self._oof_toggle.toggled.connect(self.show_out_of_frame_toggled.emit)
        bottom_layout.addWidget(self._oof_toggle)

        self._splitter.addWidget(bottom)

        # Set initial sizes: 60% squad, 40% box list
        self._splitter.setSizes([360, 240])

        layout.addWidget(self._splitter)

    @property
    def squad_panel(self) -> SquadPanel:
        """Access the squad panel for direct wiring in MainWindow."""
        return self._squad_panel

    def retranslate_ui(self):
        """Refresh all translatable labels after language change."""
        self._title.setText(t("panel.annotations_title"))
        self._delete_btn.setText(t("button.delete_selected"))

    def update_boxes(self, boxes: list[BoundingBox]):
        self._list.blockSignals(True)
        self._list.clear()
        pending_count = 0
        unsure_count = 0
        auto_count = 0
        finalized_count = 0
        inherited_count = 0
        oof_count = 0
        for box in boxes:
            if box.box_status == BoxStatus.PENDING:
                pending_count += 1
                cls = box.detected_class or "person"
                conf = f" ({float(box.confidence):.2f})" if box.confidence else ""
                label = f"? {cls}{conf}"
                item = QListWidgetItem(label)
                item.setForeground(QColor("#F5A623"))
            elif box.box_status == BoxStatus.UNSURE:
                unsure_count += 1
                if box.jersey_number is not None and box.player_name:
                    parts = box.player_name.split()
                    short = parts[-1] if parts else ""
                    label = f"? #{box.jersey_number} {short}"
                elif box.category is not None:
                    cat_name = CATEGORY_NAMES.get(box.category, "unknown")
                    label = f"? {cat_name}"
                else:
                    label = "? unsure"
                if box.unsure_note:
                    note_preview = box.unsure_note[:20]
                    label += f" [{note_preview}]"
                item = QListWidgetItem(label)
                item.setForeground(QColor("#FF6B35"))
            elif box.box_status == BoxStatus.AUTO:
                auto_count += 1
                cat_name = CATEGORY_NAMES.get(box.category, "unknown")
                conf = f" ({float(box.confidence):.2f})" if box.confidence else ""
                label = f"[auto] {cat_name}{conf}"
                item = QListWidgetItem(label)
                color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                item.setForeground(color)
            else:
                finalized_count += 1
                if box.inherited:
                    inherited_count += 1
                    label = self._format_box(box) + "  [Inherited]"
                    item = QListWidgetItem(label)
                    color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                    inherited_color = QColor(color)
                    inherited_color.setAlpha(180)
                    item.setForeground(inherited_color)
                elif box.out_of_frame:
                    oof_count += 1
                    label = self._format_box(box) + "  [OOF]"
                    item = QListWidgetItem(label)
                    item.setForeground(QColor("#666"))
                else:
                    label = self._format_box(box)
                    item = QListWidgetItem(label)
                    color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                    item.setForeground(color)
            self._list.addItem(item)
        self._list.blockSignals(False)

        # Update pending/unsure/auto counter
        if pending_count > 0 or unsure_count > 0 or auto_count > 0:
            parts = []
            if pending_count > 0:
                parts.append(f"{pending_count} pending")
            if auto_count > 0:
                parts.append(f"{auto_count} auto")
            if unsure_count > 0:
                parts.append(f"{unsure_count} unsure")
            counter_text = f"{len(boxes)} total \u2014 {', '.join(parts)}, {finalized_count} assigned"
            self._pending_counter.setText(counter_text)
            self._pending_counter.setVisible(True)
        else:
            self._pending_counter.setVisible(False)

        # Update squad panel check marks
        self._squad_panel.update_assignments(boxes)

        # Show/hide inheritance controls
        self._inherit_frame.setVisible(inherited_count > 0)
        self._oof_toggle.setVisible(oof_count > 0)

    def select_row(self, row: int):
        self._list.blockSignals(True)
        self._list.setCurrentRow(row)
        self._list.blockSignals(False)

    def _format_box(self, box: BoundingBox) -> str:
        cat = box.category
        if cat in (Category.HOME_PLAYER, Category.HOME_GK):
            num = box.jersey_number or "?"
            name = box.player_name or ""
            parts = name.split()
            short = parts[-1] if parts else ""
            line = f"#{num} {short}"
        else:
            line = CATEGORY_NAMES.get(cat, "unknown")

        occ = t(f"occlusion.{box.occlusion.value}")
        if box.truncated:
            occ += " [T]"
        return f"{line}  ({occ})"

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.box_clicked.emit(row)

    def _on_double_click(self, item):
        row = self._list.row(item)
        if row >= 0:
            self.box_double_clicked.emit(row)

    def update_sequence_badge(self, sequence_id: str, position: int, length: int):
        """Show or hide the sequence badge."""
        if sequence_id:
            self._current_seq_id = sequence_id
            self._seq_badge.setText(f"\U0001f517 {sequence_id} ({position}/{length})")
            self._seq_badge.setVisible(True)
        else:
            self._current_seq_id = ""
            self._seq_badge.setVisible(False)

    def _on_seq_badge_clicked(self):
        if self._current_seq_id:
            self.sequence_badge_clicked.emit(self._current_seq_id)
