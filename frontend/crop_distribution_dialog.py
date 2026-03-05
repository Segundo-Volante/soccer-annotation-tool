"""Crop Distribution Panel — shows per-player crop distribution before export.

Displays a table of players × shot_types with gap indicators,
and optionally generates a resample_request.json for the Screenshotter.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSpinBox, QDoubleSpinBox, QWidget,
)

# ── Design tokens (unified with project palette) ──
_BG = "#1E1E2E"
_CARD = "#2A2A3C"
_BORDER = "#404060"
_ACCENT = "#F5A623"
_ACCENT_HOVER = "#FFB833"
_TEXT = "#E8E8F0"
_MUTED = "#8888A0"
_GREEN = "#27AE60"
_AMBER = "#F5A623"
_BTN_BG = "#404060"
_BTN_HOVER = "#505070"

_DIALOG_STYLE = f"""
    QDialog {{ background: {_BG}; }}
    QLabel {{ color: {_TEXT}; font-size: 12px; }}
    QTableWidget {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        font-size: 12px; gridline-color: {_BORDER};
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QTableWidget::item:selected {{ background: #3A5A3A; }}
    QHeaderView::section {{
        background: {_CARD}; color: {_MUTED};
        border: 1px solid {_BORDER}; padding: 4px 8px;
        font-size: 11px; font-weight: bold;
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 3px;
        padding: 2px 4px; font-size: 12px;
    }}
    QPushButton {{
        background: {_BTN_BG}; color: {_TEXT}; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: none;
    }}
    QPushButton:hover {{ background: {_BTN_HOVER}; }}
"""


class CropDistributionDialog(QDialog):
    """Shows crop distribution analysis and optionally generates resample request."""

    RESULT_CANCEL = 0
    RESULT_EXPORT = 1
    RESULT_EXPORT_AND_RESAMPLE = 2

    def __init__(self, distribution: dict, has_sequence_data: bool,
                 reid_targets: dict, resample_thresholds: dict,
                 parent=None):
        super().__init__(parent)
        self._distribution = distribution
        self._has_sequence_data = has_sequence_data
        self._reid_targets = dict(reid_targets)
        self._resample_thresholds = dict(resample_thresholds)
        self._result_action = self.RESULT_CANCEL

        match_id = distribution.get("match_id", "")
        self.setWindowTitle(f"Export Preview \u2014 {match_id}")
        self.setMinimumSize(720, 520)
        self.resize(780, 600)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Title ──
        title = QLabel(f"EXPORT PREVIEW \u2014 {match_id}")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {_ACCENT};")
        layout.addWidget(title)

        # ── Section header ──
        section = QLabel("CROP DISTRIBUTION")
        section.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {_TEXT}; margin-top: 4px;")
        layout.addWidget(section)

        # ── Table ──
        players = distribution.get("players", [])
        self._table = QTableWidget()
        if has_sequence_data:
            self._table.setColumnCount(6)
            self._table.setHorizontalHeaderLabels(
                ["Player", "Wide", "Medium", "Closeup", "Total", "Status"]
            )
        else:
            self._table.setColumnCount(3)
            self._table.setHorizontalHeaderLabels(["Player", "Total", "Status"])

        self._table.setRowCount(len(players))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self._populate_table()
        layout.addWidget(self._table)

        # ── Summary line ──
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        self._update_summary_label()
        layout.addWidget(self._summary_label)

        # ── Advanced: Adjust Targets (collapsed) ──
        self._advanced_frame = QFrame()
        self._advanced_frame.setVisible(False)
        adv_layout = QVBoxLayout(self._advanced_frame)
        adv_layout.setContentsMargins(8, 8, 8, 8)
        adv_layout.setSpacing(8)

        # Targets row
        targets_row = QHBoxLayout()
        targets_row.addWidget(QLabel("Per-player crop targets:"))
        targets_row.addStretch()
        adv_layout.addLayout(targets_row)

        target_inputs = QHBoxLayout()
        target_inputs.addWidget(QLabel("Wide:"))
        self._wide_target = QSpinBox()
        self._wide_target.setRange(0, 9999)
        self._wide_target.setValue(reid_targets.get("wide", 150))
        self._wide_target.valueChanged.connect(self._on_targets_changed)
        target_inputs.addWidget(self._wide_target)
        target_inputs.addSpacing(12)
        target_inputs.addWidget(QLabel("Medium:"))
        self._med_target = QSpinBox()
        self._med_target.setRange(0, 9999)
        self._med_target.setValue(reid_targets.get("medium", 60))
        self._med_target.valueChanged.connect(self._on_targets_changed)
        target_inputs.addWidget(self._med_target)
        target_inputs.addSpacing(12)
        target_inputs.addWidget(QLabel("Closeup:"))
        self._close_target = QSpinBox()
        self._close_target.setRange(0, 9999)
        self._close_target.setValue(reid_targets.get("closeup", 20))
        self._close_target.valueChanged.connect(self._on_targets_changed)
        target_inputs.addWidget(self._close_target)
        target_inputs.addStretch()
        adv_layout.addLayout(target_inputs)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        adv_layout.addWidget(sep)

        # Thresholds
        thresh_label = QLabel("Resample selection thresholds:")
        thresh_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: bold;")
        adv_layout.addWidget(thresh_label)

        t1 = QHBoxLayout()
        t1.addWidget(QLabel("Wide: player visible in \u2265"))
        self._wide_ratio = QDoubleSpinBox()
        self._wide_ratio.setRange(0, 1)
        self._wide_ratio.setSingleStep(0.1)
        self._wide_ratio.setDecimals(2)
        self._wide_ratio.setValue(resample_thresholds.get("wide_min_player_ratio", 0.5))
        t1.addWidget(self._wide_ratio)
        t1.addWidget(QLabel("of frames"))
        t1.addStretch()
        adv_layout.addLayout(t1)

        t2 = QHBoxLayout()
        t2.addWidget(QLabel("Medium: player visible in \u2265"))
        self._med_min = QSpinBox()
        self._med_min.setRange(1, 100)
        self._med_min.setValue(resample_thresholds.get("medium_min_player_frames", 1))
        t2.addWidget(self._med_min)
        t2.addWidget(QLabel("frame(s) (non-occluded)"))
        t2.addStretch()
        adv_layout.addLayout(t2)

        t3 = QHBoxLayout()
        t3.addWidget(QLabel("Closeup: player visible in \u2265"))
        self._close_min = QSpinBox()
        self._close_min.setRange(1, 100)
        self._close_min.setValue(resample_thresholds.get("closeup_min_player_frames", 1))
        t3.addWidget(self._close_min)
        t3.addWidget(QLabel("frame(s)"))
        t3.addStretch()
        adv_layout.addLayout(t3)

        t4 = QHBoxLayout()
        t4.addWidget(QLabel("Min. sequence length:"))
        self._min_seq = QSpinBox()
        self._min_seq.setRange(1, 100)
        self._min_seq.setValue(resample_thresholds.get("min_sequence_length", 3))
        t4.addWidget(self._min_seq)
        t4.addWidget(QLabel("frames"))
        t4.addStretch()
        adv_layout.addLayout(t4)

        t5 = QHBoxLayout()
        t5.addWidget(QLabel("Default resample interval estimate:"))
        self._resample_interval = QDoubleSpinBox()
        self._resample_interval.setRange(0.1, 10.0)
        self._resample_interval.setSingleStep(0.1)
        self._resample_interval.setDecimals(1)
        self._resample_interval.setValue(resample_thresholds.get("estimated_resample_interval", 0.3))
        t5.addWidget(self._resample_interval)
        t5.addWidget(QLabel("sec"))
        t5.addStretch()
        adv_layout.addLayout(t5)

        # Defaults buttons
        defaults_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        defaults_row.addWidget(reset_btn)
        save_btn = QPushButton("Save as Project Defaults")
        save_btn.clicked.connect(self._save_project_defaults)
        defaults_row.addWidget(save_btn)
        defaults_row.addStretch()
        adv_layout.addLayout(defaults_row)

        layout.addWidget(self._advanced_frame)

        # ── Toggle button for advanced ──
        self._adv_toggle = QPushButton("\u25b8 Advanced: Adjust Targets")
        self._adv_toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_MUTED};"
            f" border: none; font-size: 12px; text-align: left; padding: 4px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; }}"
        )
        self._adv_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._adv_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._adv_toggle)

        # ── Bottom buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_MUTED};"
            f" padding: 10px 20px; border: 1px solid {_BORDER};"
            f" border-radius: 6px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {_CARD}; color: {_TEXT}; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        export_btn = QPushButton("Export")
        export_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: {_BG}; padding: 10px 24px;"
            f" border-radius: 6px; font-weight: bold; font-size: 13px; border: none; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER}; }}"
        )
        export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(export_btn)

        self._resample_btn = QPushButton("Export + Generate Resample Request")
        self._resample_btn.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: white; padding: 10px 20px;"
            f" border-radius: 6px; font-weight: bold; font-size: 12px; border: none; }}"
            f"QPushButton:hover {{ background: #2ECC71; }}"
        )
        self._resample_btn.clicked.connect(self._on_export_and_resample)
        btn_layout.addWidget(self._resample_btn)

        if not has_sequence_data:
            self._resample_btn.setEnabled(False)
            self._resample_btn.setToolTip(
                "Requires sequence metadata from Screenshotter."
            )

        layout.addLayout(btn_layout)

    # ── Table population ──

    def _populate_table(self):
        """Fill or refresh the table rows using current targets."""
        players = self._distribution.get("players", [])
        targets = self.get_targets() if hasattr(self, "_wide_target") else self._reid_targets

        for row, player in enumerate(players):
            name = player.get("name", "")
            number = player.get("jersey_number", "")
            player_label = f"#{number} {name}" if number else name
            self._table.setItem(row, 0, QTableWidgetItem(player_label))

            if self._has_sequence_data:
                by_type = player.get("crops_by_shot_type", {})
                wide_count = by_type.get("wide", 0)
                med_count = by_type.get("medium", 0)
                close_count = by_type.get("closeup", 0)
                total = player.get("total_crops", 0)

                # Recalculate gaps based on current targets
                gap_types = set()
                if wide_count < targets.get("wide", 150):
                    gap_types.add("wide")
                if med_count < targets.get("medium", 60):
                    gap_types.add("medium")
                if close_count < targets.get("closeup", 20):
                    gap_types.add("closeup")

                wide_item = QTableWidgetItem(str(wide_count))
                wide_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if "wide" in gap_types:
                    wide_item.setForeground(QColor(_AMBER))
                else:
                    wide_item.setForeground(QColor(_TEXT))
                self._table.setItem(row, 1, wide_item)

                med_item = QTableWidgetItem(str(med_count))
                med_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if "medium" in gap_types:
                    med_item.setForeground(QColor(_AMBER))
                else:
                    med_item.setForeground(QColor(_TEXT))
                self._table.setItem(row, 2, med_item)

                close_item = QTableWidgetItem(str(close_count))
                close_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if "closeup" in gap_types:
                    close_item.setForeground(QColor(_AMBER))
                else:
                    close_item.setForeground(QColor(_TEXT))
                self._table.setItem(row, 3, close_item)

                total_item = QTableWidgetItem(str(total))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 4, total_item)

                # Status
                if gap_types:
                    abbr = []
                    if "wide" in gap_types:
                        abbr.append("W")
                    if "medium" in gap_types:
                        abbr.append("M")
                    if "closeup" in gap_types:
                        abbr.append("C")
                    status_text = "\u26a0\ufe0f " + ",".join(abbr)
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(QColor(_AMBER))
                else:
                    status_item = QTableWidgetItem("\u2705")
                    status_item.setForeground(QColor(_GREEN))
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 5, status_item)
            else:
                total = player.get("total_crops", 0)
                total_item = QTableWidgetItem(str(total))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 1, total_item)

                status_item = QTableWidgetItem("\u2705")
                status_item.setForeground(QColor(_GREEN))
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2, status_item)

    def _update_summary_label(self):
        """Recalculate and update the summary line based on current targets."""
        players = self._distribution.get("players", [])
        targets = self.get_targets() if hasattr(self, "_wide_target") else self._reid_targets

        gap_count = 0
        for player in players:
            if self._has_sequence_data:
                by_type = player.get("crops_by_shot_type", {})
                has_gap = False
                for shot_type, target_val in targets.items():
                    if by_type.get(shot_type, 0) < target_val:
                        has_gap = True
                        break
                if has_gap:
                    gap_count += 1
            # Without sequence data, no gaps can be detected
        ok_count = len(players) - gap_count
        self._summary_label.setText(
            f"{len(players)} players | {ok_count} OK | {gap_count} with gaps"
        )

    def _on_targets_changed(self):
        """Called when any target spinbox value changes — live recalculate."""
        self._populate_table()
        self._update_summary_label()

    # ── UI actions ──

    def _toggle_advanced(self):
        visible = not self._advanced_frame.isVisible()
        self._advanced_frame.setVisible(visible)
        arrow = "\u25be" if visible else "\u25b8"
        self._adv_toggle.setText(f"{arrow} Advanced: Adjust Targets")

    def _reset_defaults(self):
        self._wide_target.setValue(150)
        self._med_target.setValue(60)
        self._close_target.setValue(20)
        self._wide_ratio.setValue(0.5)
        self._med_min.setValue(1)
        self._close_min.setValue(1)
        self._min_seq.setValue(3)
        self._resample_interval.setValue(0.3)

    def _save_project_defaults(self):
        """Mark that user wants to save current settings as project defaults."""
        self._saved_defaults = True

    def _on_export(self):
        self._result_action = self.RESULT_EXPORT
        self.accept()

    def _on_export_and_resample(self):
        self._result_action = self.RESULT_EXPORT_AND_RESAMPLE
        self.accept()

    def get_result_action(self) -> int:
        return self._result_action

    def get_targets(self) -> dict[str, int]:
        return {
            "wide": self._wide_target.value(),
            "medium": self._med_target.value(),
            "closeup": self._close_target.value(),
        }

    def get_thresholds(self) -> dict:
        return {
            "wide_min_player_ratio": self._wide_ratio.value(),
            "medium_min_player_frames": self._med_min.value(),
            "closeup_min_player_frames": self._close_min.value(),
            "min_sequence_length": self._min_seq.value(),
            "estimated_resample_interval": self._resample_interval.value(),
        }

    def should_save_defaults(self) -> bool:
        return getattr(self, "_saved_defaults", False)
