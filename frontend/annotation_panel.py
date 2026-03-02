from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel, QPushButton,
    QScrollArea, QFrame,
)

from backend.i18n import t
from backend.models import BoundingBox, BoxStatus, Category, CATEGORY_NAMES, Occlusion

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._title = QLabel(t("panel.annotations_title"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("color: #EEE; font-weight: bold; font-size: 13px;")
        layout.addWidget(self._title)

        # Pending counter (visible only in AI mode when pending boxes exist)
        self._pending_counter = QLabel("")
        self._pending_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_counter.setStyleSheet(
            "color: #F5A623; font-weight: bold; font-size: 11px; padding: 2px;"
        )
        self._pending_counter.setVisible(False)
        layout.addWidget(self._pending_counter)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background: #2A2A2A; border: none; }
            QListWidget::item { padding: 4px; border-radius: 3px; margin: 1px; }
            QListWidget::item:selected { background: #3A5A3A; border: 1px solid #5A5; }
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        self._delete_btn = QPushButton(t("button.delete_selected"))
        self._delete_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._delete_btn.setStyleSheet("""
            QPushButton { background: #C0392B; color: white; padding: 6px;
                          border-radius: 3px; font-weight: bold; }
            QPushButton:hover { background: #E74C3C; }
        """)
        self._delete_btn.clicked.connect(self.delete_requested.emit)
        layout.addWidget(self._delete_btn)

        # ── Keyboard shortcut reference ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #555;")
        layout.addWidget(sep)

        self._help_label = QLabel()
        self._help_label.setWordWrap(True)
        self._help_label.setStyleSheet("color: #999; font-size: 11px; padding: 4px;")
        layout.addWidget(self._help_label)

        self._update_help_text()

    def retranslate_ui(self):
        """Refresh all translatable labels after language change."""
        self._title.setText(t("panel.annotations_title"))
        self._delete_btn.setText(t("button.delete_selected"))
        self._update_help_text()

    def _update_help_text(self):
        self._help_label.setText(
            f"<b style='color:#FFA500;'>{t('help.shortcuts_title')}</b><br>"
            "<br>"
            f"<b style='color:#AAA;'>{t('help.category_label')}</b><br>"
            f"<span style='color:#E74C3C;'>1</span> {t('help.category_home_player')}<br>"
            f"<span style='color:#3498DB;'>2</span> {t('help.category_opponent')}<br>"
            f"<span style='color:#E67E22;'>3</span> {t('help.category_home_gk')}<br>"
            f"<span style='color:#2980B9;'>4</span> {t('help.category_opponent_gk')}<br>"
            f"<span style='color:#F1C40F;'>5</span> {t('help.category_referee')}<br>"
            f"<span style='color:#2ECC71;'>6</span> {t('help.category_ball')}<br>"
            "<br>"
            f"<b style='color:#AAA;'>{t('help.metadata_label')}</b><br>"
            f"<span style='color:#F5A623;'>Tab</span> {t('help.next_dimension')}<br>"
            f"<span style='color:#F5A623;'>Shift+Tab</span> {t('help.prev_dimension')}<br>"
            f"<span style='color:#CCC;'>1-9</span> {t('help.select_option')}<br>"
            "<br>"
            f"<b style='color:#AAA;'>{t('help.occlusion_label')}</b><br>"
            f"<span style='color:#CCC;'>F</span> {t('help.occlusion_visible')} &nbsp;"
            f"<span style='color:#CCC;'>G</span> {t('help.occlusion_partial')} &nbsp;"
            f"<span style='color:#CCC;'>H</span> {t('help.occlusion_heavy')}<br>"
            f"<span style='color:#CCC;'>T</span> {t('help.toggle_truncated')}<br>"
            "<br>"
            f"<b style='color:#AAA;'>{t('help.navigation_label')}</b><br>"
            f"<span style='color:#4A90D9;'>Enter</span> {t('help.export_next')}<br>"
            f"<span style='color:#D94A4A;'>Esc</span> {t('help.skip_next')}<br>"
            f"<span style='color:#CCC;'>\u2190 \u2192</span> {t('help.prev_next_frame')}<br>"
            f"<span style='color:#CCC;'>Ctrl+Z</span> {t('help.undo_last_box')}<br>"
            f"<span style='color:#CCC;'>Del</span> {t('help.delete_selected')}"
        )

    def update_boxes(self, boxes: list[BoundingBox]):
        self._list.blockSignals(True)
        self._list.clear()
        pending_count = 0
        finalized_count = 0
        for box in boxes:
            if box.box_status == BoxStatus.PENDING:
                pending_count += 1
                cls = box.detected_class or "person"
                conf = f" ({float(box.confidence):.2f})" if box.confidence else ""
                label = f"? {cls}{conf}"
                item = QListWidgetItem(label)
                item.setForeground(QColor("#F5A623"))
            else:
                finalized_count += 1
                label = self._format_box(box)
                item = QListWidgetItem(label)
                color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                item.setForeground(color)
            self._list.addItem(item)
        self._list.blockSignals(False)

        # Update pending counter
        if pending_count > 0:
            self._pending_counter.setText(
                t("ai.pending_counter",
                  total=len(boxes), pending=pending_count, assigned=finalized_count)
            )
            self._pending_counter.setVisible(True)
        else:
            self._pending_counter.setVisible(False)

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
