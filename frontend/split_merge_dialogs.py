"""Split & Merge collaboration dialogs.

Provides dialogs for splitting annotation work among team members
and merging completed annotations back together.
"""

import os
import platform
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Dark theme constants (matching project palette)
# ---------------------------------------------------------------------------

DARK_STYLE = """
    QDialog { background: #1E1E2E; }
    QLabel { color: #E8E8F0; font-size: 12px; }
    QLineEdit, QComboBox {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        border-radius: 4px; padding: 6px; font-size: 12px;
    }
    QLineEdit:focus, QComboBox:focus { border-color: #F5A623; }
    QPushButton {
        background: #404060; color: #E8E8F0; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: none;
    }
    QPushButton:hover { background: #505070; }
    QGroupBox {
        color: #8888A0; font-size: 11px; border: 1px solid #404060;
        border-radius: 6px; margin-top: 8px; padding-top: 16px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
    QRadioButton { color: #E8E8F0; font-size: 11px; spacing: 6px; }
    QRadioButton::indicator { width: 14px; height: 14px; }
    QCheckBox { color: #E8E8F0; font-size: 11px; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QScrollArea { border: none; background: transparent; }
    QSpinBox {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        border-radius: 4px; padding: 4px 6px; font-size: 12px;
    }
    QSpinBox:focus { border-color: #F5A623; }
    QTableWidget {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        gridline-color: #404060; font-size: 12px;
    }
    QTableWidget::item { padding: 4px; }
    QTableWidget::item:selected { background: #3A3A5C; }
    QHeaderView::section {
        background: #33334C; color: #8888A0; border: 1px solid #404060;
        padding: 4px 8px; font-size: 11px; font-weight: bold;
    }
"""

_ACCENT = "#F5A623"
_ACCENT_HOVER = "#FFBE4A"
_ERROR_COLOR = "#E05555"
_SUCCESS_COLOR = "#55C878"
_MUTED_TEXT = "#8888A0"
_CARD_BG = "#2A2A3C"
_INPUT_BORDER = "#404060"

_DEMO_NAMES = ["Jason", "John Doe", "Jack Smith", "Jane Roe", "Jane Smith"]


def _open_folder_in_explorer(folder: str) -> None:
    """Open *folder* in the platform file manager."""
    folder = os.path.realpath(folder)
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", folder])
    elif system == "Windows":
        os.startfile(folder)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", folder])


def _accent_button(text: str) -> QPushButton:
    """Return a QPushButton styled with the project accent colour."""
    btn = QPushButton(text)
    btn.setStyleSheet(
        f"QPushButton {{ background: {_ACCENT}; color: #1E1E2E; padding: 8px 24px;"
        f" border-radius: 4px; font-weight: bold; font-size: 12px; border: none; }}"
        f"QPushButton:hover {{ background: {_ACCENT_HOVER}; }}"
    )
    return btn


def _cancel_button(text: str = "Cancel") -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(
        "QPushButton { background: #404060; color: #E8E8F0; padding: 8px 20px;"
        " border-radius: 4px; font-size: 12px; border: none; }"
        "QPushButton:hover { background: #505070; }"
    )
    return btn


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {_MUTED_TEXT};")
    return lbl


def _error_label() -> QLabel:
    lbl = QLabel("")
    lbl.setStyleSheet(f"color: {_ERROR_COLOR}; font-size: 11px;")
    lbl.setWordWrap(True)
    lbl.hide()
    return lbl


# ═══════════════════════════════════════════════════════════════════════════
# 1. SplitSetupDialog
# ═══════════════════════════════════════════════════════════════════════════

class SplitSetupDialog(QDialog):
    """Setup dialog for splitting frames among team members."""

    def __init__(self, total_frames: int, project_root: str, parent=None):
        super().__init__(parent)
        self._total_frames = max(total_frames, 1)
        self._project_root = project_root
        self._result: dict | None = None

        self.setWindowTitle("Split & Merge \u2014 Divide Frames")
        self.setMinimumSize(640, 620)
        self.setStyleSheet(DARK_STYLE)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scroll area wrapping all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        scroll.setWidget(container)

        # --- Title ---
        title = QLabel("\U0001F4C2 Split & Merge \u2014 Divide Frames")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {_ACCENT};")
        layout.addWidget(title)

        # --- Frame count ---
        frames_lbl = QLabel(f"Total frames in project: {self._total_frames}")
        frames_lbl.setStyleSheet("color: #E8E8F0; font-size: 13px;")
        layout.addWidget(frames_lbl)

        # --- Team members ---
        layout.addWidget(_section_title("TEAM MEMBERS"))
        self._build_members_table(layout)

        # --- Split method ---
        layout.addWidget(_section_title("SPLIT METHOD"))
        self._build_split_method(layout)

        # --- Overlap ---
        layout.addWidget(_section_title("OVERLAP"))
        self._build_overlap_section(layout)

        # --- Package type ---
        layout.addWidget(_section_title("PACKAGE TYPE"))
        self._build_package_type(layout)

        # --- Output location ---
        layout.addWidget(_section_title("OUTPUT LOCATION"))
        self._build_output_section(layout)

        # --- Validation error ---
        self._error_lbl = _error_label()
        layout.addWidget(self._error_lbl)

        layout.addStretch()

        # --- Buttons (outside scroll) ---
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(24, 10, 24, 16)
        btn_layout.addStretch()

        cancel_btn = _cancel_button()
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        create_btn = _accent_button("Create Splits \u2192")
        create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(create_btn)

        root_layout.addLayout(btn_layout)

        # Initialise with one row and auto-calc
        self._add_member_row("Jason")
        self._recalculate_ranges()

    # ----- members table -----

    def _build_members_table(self, parent_layout: QVBoxLayout) -> None:
        self._members_table = QTableWidget(0, 4)
        self._members_table.setHorizontalHeaderLabels(
            ["Name", "Frame Range Start", "Frame Range End", ""]
        )
        header = self._members_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 130)
        header.resizeSection(2, 130)
        header.resizeSection(3, 60)
        self._members_table.verticalHeader().setVisible(False)
        self._members_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._members_table.setMaximumHeight(200)
        parent_layout.addWidget(self._members_table)

        add_btn = QPushButton("+ Add Member")
        add_btn.setStyleSheet(
            f"QPushButton {{ color: {_ACCENT}; background: transparent;"
            " border: none; font-size: 12px; padding: 4px; text-align: left; }}"
            f"QPushButton:hover {{ color: {_ACCENT_HOVER}; }}"
        )
        add_btn.clicked.connect(self._on_add_member)
        parent_layout.addWidget(add_btn)

    def _next_demo_name(self) -> str:
        used = set()
        for r in range(self._members_table.rowCount()):
            w = self._members_table.cellWidget(r, 0)
            if isinstance(w, QLineEdit):
                used.add(w.text().strip())
        for name in _DEMO_NAMES:
            if name not in used:
                return name
        return f"Member {self._members_table.rowCount() + 1}"

    def _add_member_row(self, name: str = "") -> None:
        row = self._members_table.rowCount()
        self._members_table.insertRow(row)

        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Name")
        name_edit.setStyleSheet(
            "background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;"
            " border-radius: 4px; padding: 4px 6px; font-size: 12px;"
        )
        self._members_table.setCellWidget(row, 0, name_edit)

        start_edit = QLineEdit("0")
        start_edit.setValidator(QIntValidator(0, self._total_frames - 1))
        start_edit.setStyleSheet(
            "background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;"
            " border-radius: 4px; padding: 4px 6px; font-size: 12px;"
        )
        self._members_table.setCellWidget(row, 1, start_edit)

        end_edit = QLineEdit("0")
        end_edit.setValidator(QIntValidator(0, self._total_frames - 1))
        end_edit.setStyleSheet(
            "background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;"
            " border-radius: 4px; padding: 4px 6px; font-size: 12px;"
        )
        self._members_table.setCellWidget(row, 2, end_edit)

        remove_btn = QPushButton("\u2715")
        remove_btn.setFixedSize(QSize(32, 28))
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_ERROR_COLOR};"
            " border: none; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #FF7777; }}"
        )
        remove_btn.clicked.connect(lambda _, r=row: self._remove_member_row(r))
        self._members_table.setCellWidget(row, 3, remove_btn)

        self._update_range_editability()
        self._recalculate_ranges()

    def _remove_member_row(self, row: int) -> None:
        if self._members_table.rowCount() <= 1:
            return
        self._members_table.removeRow(row)
        # Rewire remove buttons to correct row indices
        for r in range(self._members_table.rowCount()):
            btn = self._members_table.cellWidget(r, 3)
            if isinstance(btn, QPushButton):
                btn.clicked.disconnect()
                btn.clicked.connect(lambda _, r=r: self._remove_member_row(r))
        self._recalculate_ranges()

    def _on_add_member(self) -> None:
        self._add_member_row(self._next_demo_name())

    # ----- split method -----

    def _build_split_method(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox()
        gl = QVBoxLayout(group)

        self._method_group = QButtonGroup(self)
        self._even_radio = QRadioButton("Even split (auto-calculate ranges)")
        self._even_radio.setChecked(True)
        self._custom_radio = QRadioButton("Custom ranges")
        self._method_group.addButton(self._even_radio, 0)
        self._method_group.addButton(self._custom_radio, 1)
        gl.addWidget(self._even_radio)
        gl.addWidget(self._custom_radio)

        parent_layout.addWidget(group)

        self._method_group.buttonClicked.connect(lambda _: self._on_method_changed())

    def _on_method_changed(self) -> None:
        self._update_range_editability()
        if self._even_radio.isChecked():
            self._recalculate_ranges()

    def _update_range_editability(self) -> None:
        editable = self._custom_radio.isChecked()
        for r in range(self._members_table.rowCount()):
            for c in (1, 2):
                w = self._members_table.cellWidget(r, c)
                if isinstance(w, QLineEdit):
                    w.setReadOnly(not editable)
                    if editable:
                        w.setStyleSheet(
                            "background: #2A2A3C; color: #E8E8F0;"
                            " border: 1px solid #404060; border-radius: 4px;"
                            " padding: 4px 6px; font-size: 12px;"
                        )
                    else:
                        w.setStyleSheet(
                            "background: #252538; color: #8888A0;"
                            " border: 1px solid #353550; border-radius: 4px;"
                            " padding: 4px 6px; font-size: 12px;"
                        )

    def _recalculate_ranges(self) -> None:
        if not self._even_radio.isChecked():
            return
        n = self._members_table.rowCount()
        if n == 0:
            return
        chunk = self._total_frames // n
        remainder = self._total_frames % n
        start = 0
        for r in range(n):
            size = chunk + (1 if r < remainder else 0)
            end = start + size - 1
            sw = self._members_table.cellWidget(r, 1)
            ew = self._members_table.cellWidget(r, 2)
            if isinstance(sw, QLineEdit):
                sw.setText(str(start))
            if isinstance(ew, QLineEdit):
                ew.setText(str(end))
            start = end + 1

    # ----- overlap -----

    def _build_overlap_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox()
        gl = QHBoxLayout(group)

        self._overlap_cb = QCheckBox("Add overlap frames for cross-validation")
        gl.addWidget(self._overlap_cb)

        gl.addSpacing(12)

        ol_label = QLabel("Overlap size:")
        ol_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        gl.addWidget(ol_label)

        self._overlap_spin = QSpinBox()
        self._overlap_spin.setRange(1, self._total_frames // 2 if self._total_frames > 2 else 1)
        self._overlap_spin.setValue(20)
        self._overlap_spin.setEnabled(False)
        gl.addWidget(self._overlap_spin)
        gl.addStretch()

        self._overlap_cb.toggled.connect(self._overlap_spin.setEnabled)
        parent_layout.addWidget(group)

    # ----- package type -----

    def _build_package_type(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox()
        gl = QVBoxLayout(group)

        self._pkg_group = QButtonGroup(self)
        self._copy_radio = QRadioButton("Copy frames into each split")
        self._copy_radio.setChecked(True)
        self._ref_radio = QRadioButton("Reference only")
        self._pkg_group.addButton(self._copy_radio, 0)
        self._pkg_group.addButton(self._ref_radio, 1)
        gl.addWidget(self._copy_radio)
        gl.addWidget(self._ref_radio)

        parent_layout.addWidget(group)

    # ----- output location -----

    def _build_output_section(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        default_out = str(Path(self._project_root) / "team_splits")
        self._output_edit = QLineEdit(default_out)
        self._output_edit.setStyleSheet(
            "background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;"
            " border-radius: 4px; padding: 6px; font-size: 12px;"
        )
        row.addWidget(self._output_edit, stretch=1)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_output)
        row.addWidget(browse_btn)

        parent_layout.addLayout(row)

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", self._output_edit.text()
        )
        if folder:
            self._output_edit.setText(folder)

    # ----- validation & result -----

    def _read_members(self) -> list[dict]:
        members = []
        for r in range(self._members_table.rowCount()):
            name_w = self._members_table.cellWidget(r, 0)
            start_w = self._members_table.cellWidget(r, 1)
            end_w = self._members_table.cellWidget(r, 2)
            name = name_w.text().strip() if isinstance(name_w, QLineEdit) else ""
            try:
                start = int(start_w.text()) if isinstance(start_w, QLineEdit) else 0
            except ValueError:
                start = -1
            try:
                end = int(end_w.text()) if isinstance(end_w, QLineEdit) else 0
            except ValueError:
                end = -1
            members.append({"name": name, "start": start, "end": end})
        return members

    def _validate(self) -> str | None:
        """Return an error string, or None if valid."""
        members = self._read_members()
        if not members:
            return "At least one team member is required."

        # Check names non-empty and unique
        names: list[str] = []
        for m in members:
            if not m["name"]:
                return "All member names must be non-empty."
            if m["name"] in names:
                return f"Duplicate member name: \"{m['name']}\". Names must be unique."
            names.append(m["name"])

        # Check ranges valid
        for m in members:
            if m["start"] < 0 or m["end"] < 0:
                return f"Invalid frame range for \"{m['name']}\"."
            if m["start"] > m["end"]:
                return f"Start frame cannot exceed end frame for \"{m['name']}\"."
            if m["end"] >= self._total_frames:
                return (
                    f"End frame {m['end']} for \"{m['name']}\" exceeds"
                    f" total frames ({self._total_frames})."
                )

        # Sort by start to check coverage / overlaps
        sorted_members = sorted(members, key=lambda m: m["start"])
        overlap_enabled = self._overlap_cb.isChecked()

        # Check for gaps
        expected_start = 0
        for m in sorted_members:
            if m["start"] > expected_start:
                return (
                    f"Gap detected: frames {expected_start}\u2013{m['start'] - 1}"
                    " are not assigned to any member."
                )
            expected_start = max(expected_start, m["end"] + 1)

        if expected_start < self._total_frames:
            return (
                f"Gap detected: frames {expected_start}\u2013{self._total_frames - 1}"
                " are not assigned to any member."
            )

        # Check for unintended overlaps
        if not overlap_enabled:
            for i in range(len(sorted_members) - 1):
                curr_end = sorted_members[i]["end"]
                next_start = sorted_members[i + 1]["start"]
                if next_start <= curr_end:
                    return (
                        f"Overlapping ranges detected between"
                        f" \"{sorted_members[i]['name']}\" and"
                        f" \"{sorted_members[i + 1]['name']}\"."
                        " Enable overlap checkbox or fix ranges."
                    )

        # Check output folder
        out = self._output_edit.text().strip()
        if not out:
            return "Output location cannot be empty."

        return None

    def _on_create(self) -> None:
        error = self._validate()
        if error:
            self._error_lbl.setText(error)
            self._error_lbl.show()
            return

        self._error_lbl.hide()
        members = self._read_members()
        overlap = self._overlap_spin.value() if self._overlap_cb.isChecked() else 0
        copy_frames = self._copy_radio.isChecked()
        output_folder = self._output_edit.text().strip()

        self._result = {
            "members": members,
            "overlap": overlap,
            "copy_frames": copy_frames,
            "output_folder": output_folder,
        }
        self.accept()

    def get_result(self) -> dict | None:
        """Return split configuration or None if cancelled."""
        return self._result


# ═══════════════════════════════════════════════════════════════════════════
# 2. SplitSuccessDialog
# ═══════════════════════════════════════════════════════════════════════════

class SplitSuccessDialog(QDialog):
    """Confirmation dialog shown after splits are successfully created."""

    def __init__(self, splits: list[dict], output_folder: str, parent=None):
        super().__init__(parent)
        self._output_folder = output_folder

        self.setWindowTitle("Splits Created")
        self.setMinimumSize(480, 340)
        self.setStyleSheet(DARK_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("\u2705  Splits Created Successfully")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {_SUCCESS_COLOR};")
        layout.addWidget(title)

        # Instruction
        instr = QLabel(
            "Distribute the folders below to each team member. "
            "When they finish annotating, collect the folders "
            "and use Merge to combine the results."
        )
        instr.setWordWrap(True)
        instr.setStyleSheet("color: #B0B0C8; font-size: 12px;")
        layout.addWidget(instr)

        # Scroll area for splits
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)
        scroll.setWidget(scroll_widget)

        for s in splits:
            card = self._make_split_card(s)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        layout.addWidget(scroll, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        open_btn = QPushButton("Open Containing Folder")
        open_btn.clicked.connect(self._open_folder)
        btn_layout.addWidget(open_btn)

        done_btn = _accent_button("Done")
        done_btn.clicked.connect(self.accept)
        btn_layout.addWidget(done_btn)

        layout.addLayout(btn_layout)

    def _make_split_card(self, split_info: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            f"background: {_CARD_BG}; border: 1px solid {_INPUT_BORDER};"
            " border-radius: 6px;"
        )
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)

        name = split_info.get("name", "Unknown")
        start = split_info.get("start", 0)
        end = split_info.get("end", 0)
        count = end - start + 1
        folder = split_info.get("folder", "")

        info_layout = QVBoxLayout()
        name_lbl = QLabel(f"{name}")
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #E8E8F0; border: none;")
        info_layout.addWidget(name_lbl)

        detail_lbl = QLabel(f"Frames {start}\u2013{end}  ({count} frames)")
        detail_lbl.setStyleSheet(f"font-size: 11px; color: {_MUTED_TEXT}; border: none;")
        info_layout.addWidget(detail_lbl)

        cl.addLayout(info_layout, stretch=1)

        copy_btn = QPushButton("\U0001F4CB Copy path")
        copy_btn.setStyleSheet(
            f"QPushButton {{ color: {_ACCENT}; background: transparent;"
            " border: none; font-size: 11px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ color: {_ACCENT_HOVER}; }}"
        )
        copy_btn.clicked.connect(lambda _, f=folder: self._copy_to_clipboard(f))
        cl.addWidget(copy_btn)

        return card

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def _open_folder(self) -> None:
        folder = self._output_folder
        if os.path.isdir(folder):
            _open_folder_in_explorer(folder)
        else:
            QMessageBox.warning(
                self, "Folder not found",
                f"The folder does not exist:\n{folder}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. MergeDialog
# ═══════════════════════════════════════════════════════════════════════════

class MergeDialog(QDialog):
    """Dialog for merging split annotations back together."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: dict | None = None
        self._split_entries: list[dict] = []  # {"path": str, "widget": QWidget, ...}

        self.setWindowTitle("Merge Team Annotations")
        self.setMinimumSize(620, 560)
        self.setStyleSheet(DARK_STYLE)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        scroll.setWidget(container)

        # Title
        title = QLabel("\U0001F4C2 Merge Team Annotations")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {_ACCENT};")
        layout.addWidget(title)

        # Add folder button
        add_btn = QPushButton("+ Add Split Folder")
        add_btn.setStyleSheet(
            f"QPushButton {{ color: {_ACCENT}; background: transparent;"
            " border: 1px dashed #404060; border-radius: 6px;"
            " font-size: 12px; padding: 10px; }}"
            f"QPushButton:hover {{ border-color: {_ACCENT}; background: #252538; }}"
        )
        add_btn.clicked.connect(self._on_add_folder)
        layout.addWidget(add_btn)

        # Folder list area
        self._folders_layout = QVBoxLayout()
        self._folders_layout.setSpacing(8)
        layout.addLayout(self._folders_layout)

        # Summary
        layout.addWidget(_section_title("SUMMARY"))
        self._summary_lbl = QLabel("No split folders added yet.")
        self._summary_lbl.setStyleSheet("color: #B0B0C8; font-size: 12px;")
        self._summary_lbl.setWordWrap(True)
        layout.addWidget(self._summary_lbl)

        # Conflict resolution
        layout.addWidget(_section_title("OVERLAP CONFLICTS"))
        self._build_conflict_section(layout)

        # Output
        layout.addWidget(_section_title("OUTPUT LOCATION"))
        self._build_merge_output(layout)

        # Validation error
        self._error_lbl = _error_label()
        layout.addWidget(self._error_lbl)

        layout.addStretch()

        # Buttons (outside scroll)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(24, 10, 24, 16)
        btn_layout.addStretch()

        cancel_btn = _cancel_button()
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        merge_btn = _accent_button("Preview Merge \u2192")
        merge_btn.clicked.connect(self._on_merge)
        btn_layout.addWidget(merge_btn)

        root_layout.addLayout(btn_layout)

    # ----- conflict resolution -----

    def _build_conflict_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox()
        gl = QVBoxLayout(group)

        desc = QLabel(
            "When multiple annotators have annotated the same frame, "
            "how should conflicts be resolved?"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {_MUTED_TEXT}; font-size: 11px;")
        gl.addWidget(desc)

        self._conflict_group = QButtonGroup(self)
        options = [
            ("keep_first", "Keep first annotator's version"),
            ("keep_most_boxes", "Keep version with more bounding boxes"),
            ("flag_review", "Flag for manual review"),
        ]
        for i, (value, label) in enumerate(options):
            rb = QRadioButton(label)
            rb.setProperty("conflict_value", value)
            if i == 0:
                rb.setChecked(True)
            self._conflict_group.addButton(rb, i)
            gl.addWidget(rb)

        parent_layout.addWidget(group)

    # ----- output -----

    def _build_merge_output(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self._merge_output_edit = QLineEdit("")
        self._merge_output_edit.setPlaceholderText("Select output folder for merged annotations")
        self._merge_output_edit.setStyleSheet(
            "background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;"
            " border-radius: 4px; padding: 6px; font-size: 12px;"
        )
        row.addWidget(self._merge_output_edit, stretch=1)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_merge_output)
        row.addWidget(browse_btn)

        parent_layout.addLayout(row)

    def _browse_merge_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", self._merge_output_edit.text()
        )
        if folder:
            self._merge_output_edit.setText(folder)

    # ----- adding / validating folders -----

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Split Folder")
        if not folder:
            return

        # Prevent duplicates
        for entry in self._split_entries:
            if entry["path"] == folder:
                return

        validation = self._validate_split_folder(folder)
        entry_data: dict = {
            "path": folder,
            "valid": validation["valid"],
            "name": validation.get("name", Path(folder).name),
            "annotated": validation.get("annotated", 0),
            "total": validation.get("total", 0),
        }

        card = self._make_folder_card(entry_data)
        entry_data["widget"] = card
        self._split_entries.append(entry_data)
        self._folders_layout.addWidget(card)
        self._refresh_summary()

    @staticmethod
    def _validate_split_folder(folder: str) -> dict:
        """Check that *folder* looks like a valid split package."""
        p = Path(folder)
        info_file = p / "split_info.json"
        annotations_dir = p / "annotations"

        valid = True
        name = p.name
        annotated = 0
        total = 0
        error = ""

        if not info_file.exists():
            valid = False
            error = "Missing split_info.json"
        if not annotations_dir.is_dir():
            valid = False
            error = error + ("; " if error else "") + "Missing annotations/ folder"

        # If info file exists, try to read metadata
        if info_file.exists():
            try:
                import json

                info = json.loads(info_file.read_text(encoding="utf-8"))
                name = info.get("member_name", name)
                total = info.get("total_frames", 0)
            except Exception:
                pass

        # Count annotation files
        if annotations_dir.is_dir():
            annotated = sum(
                1 for f in annotations_dir.iterdir()
                if f.suffix in (".json", ".txt", ".xml")
            )

        return {
            "valid": valid,
            "name": name,
            "annotated": annotated,
            "total": total,
            "error": error,
        }

    def _make_folder_card(self, entry: dict) -> QWidget:
        card = QWidget()
        border_color = _INPUT_BORDER if entry["valid"] else _ERROR_COLOR
        card.setStyleSheet(
            f"background: {_CARD_BG}; border: 1px solid {border_color};"
            " border-radius: 6px;"
        )
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)

        # Info column
        info_layout = QVBoxLayout()
        name_lbl = QLabel(entry["name"])
        name_lbl.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #E8E8F0; border: none;"
        )
        info_layout.addWidget(name_lbl)

        total = entry["total"]
        annotated = entry["annotated"]
        pct = round(annotated / total * 100) if total > 0 else 0
        detail_text = f"{annotated} / {total} annotated  ({pct}%)" if total > 0 else f"{annotated} annotations found"
        detail_lbl = QLabel(detail_text)
        detail_lbl.setStyleSheet(f"font-size: 11px; color: {_MUTED_TEXT}; border: none;")
        info_layout.addWidget(detail_lbl)

        if not entry["valid"]:
            err_lbl = QLabel("\u26a0 Invalid split folder")
            err_lbl.setStyleSheet(f"font-size: 10px; color: {_ERROR_COLOR}; border: none;")
            info_layout.addWidget(err_lbl)

        cl.addLayout(info_layout, stretch=1)

        # Progress indicator
        if total > 0:
            pct_lbl = QLabel(f"{pct}%")
            color = _SUCCESS_COLOR if pct >= 100 else _ACCENT if pct >= 50 else _ERROR_COLOR
            pct_lbl.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {color}; border: none;"
            )
            cl.addWidget(pct_lbl)

        # Remove button
        remove_btn = QPushButton("\u2715")
        remove_btn.setFixedSize(QSize(28, 28))
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_ERROR_COLOR};"
            " border: none; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #FF7777; }}"
        )
        remove_btn.clicked.connect(lambda _, p=entry["path"]: self._remove_folder(p))
        cl.addWidget(remove_btn)

        return card

    def _remove_folder(self, path: str) -> None:
        for i, entry in enumerate(self._split_entries):
            if entry["path"] == path:
                w = entry["widget"]
                self._folders_layout.removeWidget(w)
                w.deleteLater()
                self._split_entries.pop(i)
                break
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if not self._split_entries:
            self._summary_lbl.setText("No split folders added yet.")
            return

        total_folders = len(self._split_entries)
        valid_folders = sum(1 for e in self._split_entries if e["valid"])
        total_annotated = sum(e["annotated"] for e in self._split_entries)
        total_frames = sum(e["total"] for e in self._split_entries)

        parts = [f"{total_folders} split folder(s) added"]
        if valid_folders < total_folders:
            parts.append(f"{total_folders - valid_folders} invalid")
        parts.append(f"{total_annotated} total annotations")
        if total_frames > 0:
            parts.append(f"{total_frames} total frames across splits")

        self._summary_lbl.setText("  \u2022  ".join(parts))

    # ----- validation & result -----

    def _on_merge(self) -> None:
        error = self._validate_merge()
        if error:
            self._error_lbl.setText(error)
            self._error_lbl.show()
            return

        self._error_lbl.hide()

        checked = self._conflict_group.checkedButton()
        conflict_resolution = (
            checked.property("conflict_value") if checked else "keep_first"
        )

        self._result = {
            "split_folders": [e["path"] for e in self._split_entries],
            "conflict_resolution": conflict_resolution,
            "output_folder": self._merge_output_edit.text().strip(),
        }
        self.accept()

    def _validate_merge(self) -> str | None:
        if not self._split_entries:
            return "Add at least one split folder."

        invalid = [e["name"] for e in self._split_entries if not e["valid"]]
        if invalid:
            return (
                f"The following split folder(s) are invalid: {', '.join(invalid)}. "
                "Remove them or select valid folders."
            )

        out = self._merge_output_edit.text().strip()
        if not out:
            return "Output location cannot be empty."

        return None

    def get_result(self) -> dict | None:
        """Return merge configuration or None if cancelled."""
        return self._result
