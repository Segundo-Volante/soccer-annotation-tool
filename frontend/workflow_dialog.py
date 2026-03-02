"""Workflow selection dialogs for team collaboration.

Provides:
- WorkflowSelectionDialog  -- choose how the team collaborates
- SoloConfirmDialog        -- simple confirmation for solo mode
- CustomWorkflowDialog     -- shows project structure and code snippet
"""

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.i18n import t

# ---------------------------------------------------------------------------
# Theme constants
# ---------------------------------------------------------------------------

BG_PRIMARY = "#1E1E2E"
BG_CARD = "#2A2A3C"
BG_CARD_HOVER = "#303048"
BORDER_DEFAULT = "#404060"
BORDER_ACCENT = "#F5A623"
TEXT_PRIMARY = "#E8E8F0"
TEXT_SECONDARY = "#8888A0"
ACCENT = "#F5A623"
ACCENT_HOVER = "#FFB833"

DIALOG_STYLE = f"""
    QDialog {{
        background: {BG_PRIMARY};
    }}
    QLabel {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
    }}
    QLineEdit {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 4px;
        padding: 6px;
        font-size: 12px;
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
    }}
    QPushButton {{
        background: #404060;
        color: {TEXT_PRIMARY};
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 12px;
        border: none;
    }}
    QPushButton:hover {{
        background: #505070;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
"""

CARD_STYLE = """
    QFrame {{
        background: {bg};
        border: 2px solid {border_color};
        border-radius: 8px;
        padding: 12px;
    }}
    QFrame:hover {{
        border-color: {accent};
        background: {bg_hover};
    }}
"""

PRIMARY_BTN_STYLE = f"""
    QPushButton {{
        background: {ACCENT};
        color: {BG_PRIMARY};
        font-size: 13px;
        font-weight: bold;
        padding: 10px 24px;
        border-radius: 6px;
    }}
    QPushButton:hover {{
        background: {ACCENT_HOVER};
    }}
    QPushButton:disabled {{
        background: #404060;
        color: #666;
    }}
"""

CANCEL_BTN_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_SECONDARY};
        font-size: 12px;
        padding: 8px 16px;
        border: 1px solid {BORDER_DEFAULT};
        border-radius: 4px;
    }}
    QPushButton:hover {{
        background: #2A2A3C;
        color: {TEXT_PRIMARY};
    }}
"""

# ---------------------------------------------------------------------------
# Workflow card definitions
# ---------------------------------------------------------------------------

WORKFLOW_CARDS = [
    {
        "key": "solo",
        "icon": "\U0001F464",
        "title": "Solo",
        "description": "One person annotates everything. Simplest setup.",
    },
    {
        "key": "split_merge",
        "icon": "\U0001F4C2",
        "title": "Split & Merge",
        "description": (
            "Divide frames among team members. Each person works on "
            "their own copy. Merge when done."
        ),
    },
    {
        "key": "shared_folder",
        "icon": "\u2601\uFE0F",
        "title": "Shared Folder",
        "description": (
            "Team shares one project folder. Everyone works on the "
            "same folder, claiming different frames."
        ),
    },
    {
        "key": "git",
        "icon": "\U0001F500",
        "title": "Git",
        "description": "Version-controlled annotations. Best for developers.",
    },
    {
        "key": "custom",
        "icon": "\u2699\uFE0F",
        "title": "Custom",
        "description": "Full control. Configure everything yourself.",
    },
]

# ---------------------------------------------------------------------------
# Code snippet shown in CustomWorkflowDialog
# ---------------------------------------------------------------------------

CODE_SNIPPET = '''\
import json
from pathlib import Path

project = Path("my_project/annotations")

for json_file in sorted(project.glob("frame_*.json")):
    data = json.loads(json_file.read_text())
    frame_idx = data.get("frame_index")
    boxes = data.get("annotations", [])
    print(f"Frame {frame_idx}: {len(boxes)} annotations")
    for ann in boxes:
        cat = ann["category"]
        bbox = ann["bbox"]  # [x, y, w, h]
        print(f"  {cat}: {bbox}")
'''

PROJECT_TREE = """\
my_project/
  frames/
    frame_000001.jpg
    frame_000002.jpg
    ...
  annotations/
    frame_000001.json
    frame_000002.json
    ...
  rosters/
    home.csv
    opponent.csv
  config/
    project.json
"""


# ===================================================================
# Helper: clickable card widget
# ===================================================================

class _WorkflowCard(QFrame):
    """A single clickable workflow card."""

    clicked = pyqtSignal(str)  # emits the workflow key

    def __init__(self, card_def: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self._key = card_def["key"]
        self._selected = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(card_def["icon"])
        icon_label.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        icon_label.setFixedWidth(36)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_label = QLabel(card_def["title"])
        title_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(title_label)

        desc_label = QLabel(card_def["description"])
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_SECONDARY}; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(desc_label)

        layout.addLayout(text_col, stretch=1)

        self._apply_style()

    # -- visual state -------------------------------------------------------

    @property
    def key(self) -> str:
        return self._key

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool):
        self._selected = value
        self._apply_style()

    def _apply_style(self):
        border = BORDER_ACCENT if self._selected else BORDER_DEFAULT
        self.setStyleSheet(
            CARD_STYLE.format(
                bg=BG_CARD,
                border_color=border,
                accent=BORDER_ACCENT,
                bg_hover=BG_CARD_HOVER,
            )
        )

    # -- interaction --------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


# ===================================================================
# 1. WorkflowSelectionDialog
# ===================================================================

class WorkflowSelectionDialog(QDialog):
    """Main dialog for choosing a team collaboration workflow.

    Shown from *Project -> Collaboration Settings* or during project creation.
    Call ``exec()`` then ``get_result()`` to obtain the user's choice.
    """

    def __init__(self, parent: QWidget | None = None, *,
                 current_workflow: str = "solo",
                 current_annotator: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Collaboration Workflow")
        self.setFixedWidth(520)
        self.setStyleSheet(DIALOG_STYLE)

        self._result: dict | None = None
        self._selected_workflow = current_workflow

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(28, 24, 28, 24)

        # -- Title ----------------------------------------------------------
        title = QLabel("How will your team work on this project?")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT};"
        )
        root.addWidget(title)

        # -- Annotator name -------------------------------------------------
        name_label = QLabel("Your name")
        name_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        root.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Alex")
        self._name_input.setText(current_annotator)
        root.addWidget(self._name_input)

        # -- Separator ------------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_DEFAULT};")
        root.addWidget(sep)

        # -- Scrollable card area -------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        card_container = QWidget()
        card_layout = QVBoxLayout(card_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(8)

        self._cards: list[_WorkflowCard] = []
        for cdef in WORKFLOW_CARDS:
            card = _WorkflowCard(cdef)
            card.clicked.connect(self._on_card_clicked)
            card_layout.addWidget(card)
            self._cards.append(card)

        card_layout.addStretch()
        scroll.setWidget(card_container)
        root.addWidget(scroll, stretch=1)

        # Apply initial selection
        self._sync_card_selection()

        # -- Bottom buttons -------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet(CANCEL_BTN_STYLE)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        btn_row.addStretch()

        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self._confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._confirm_btn)

        root.addLayout(btn_row)

    # -- internal -----------------------------------------------------------

    def _on_card_clicked(self, key: str):
        self._selected_workflow = key
        self._sync_card_selection()

    def _sync_card_selection(self):
        for card in self._cards:
            card.selected = (card.key == self._selected_workflow)

    def _on_confirm(self):
        self._result = {
            "workflow": self._selected_workflow,
            "annotator": self._name_input.text().strip(),
        }
        self.accept()

    # -- public API ---------------------------------------------------------

    def get_result(self) -> dict | None:
        """Return the user selection or ``None`` if cancelled.

        Returns ``{"workflow": str, "annotator": str}``.
        """
        return self._result


# ===================================================================
# 2. SoloConfirmDialog
# ===================================================================

class SoloConfirmDialog(QDialog):
    """Simple confirmation when the user picks Solo mode.

    Displays a short message explaining solo mode and offers a single
    Confirm button.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Solo Mode")
        self.setFixedWidth(400)
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 24, 28, 24)

        # Icon + title
        header = QLabel("\U0001F464  Solo Mode")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {ACCENT};"
        )
        layout.addWidget(header)

        # Body text
        body = QLabel(
            "You will be the only annotator on this project.\n\n"
            "All frames will be assigned to you and no merge step is "
            "needed. You can switch to a team workflow later from "
            "Project \u2192 Collaboration Settings."
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; line-height: 1.5;")
        layout.addWidget(body)

        layout.addSpacing(8)

        # Confirm button
        confirm_btn = QPushButton("Confirm")
        confirm_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        confirm_btn.clicked.connect(self.accept)
        layout.addWidget(confirm_btn, alignment=Qt.AlignmentFlag.AlignCenter)


# ===================================================================
# 3. CustomWorkflowDialog
# ===================================================================

class CustomWorkflowDialog(QDialog):
    """Shows project directory structure and a Python code snippet.

    Intended for advanced users who want to integrate the annotation
    data into their own pipeline.
    """

    def __init__(self, project_dir: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._project_dir = project_dir
        self.setWindowTitle("Custom Workflow")
        self.setFixedSize(560, 540)
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 24, 28, 24)

        # Title
        title = QLabel("\u2699\uFE0F  Custom Workflow")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ACCENT};"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Your project folder is structured like this. "
            "Use the code below to read annotation data."
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(subtitle)

        # -- Project tree ---------------------------------------------------
        tree_label = QLabel("Project structure")
        tree_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(tree_label)

        tree_view = QTextEdit()
        tree_view.setReadOnly(True)
        tree_view.setPlainText(PROJECT_TREE)
        tree_view.setFixedHeight(140)
        tree_view.setFont(QFont("Courier", 11))
        tree_view.setStyleSheet(
            f"QTextEdit {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: 6px; "
            "padding: 8px; }}"
        )
        layout.addWidget(tree_view)

        # -- Code snippet ---------------------------------------------------
        code_header = QHBoxLayout()
        code_label = QLabel("Read annotations (Python)")
        code_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        code_header.addWidget(code_label)
        code_header.addStretch()

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setFixedWidth(60)
        self._copy_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_CARD}; color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: 4px; "
            "padding: 4px 8px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; background: #363650; }}"
        )
        self._copy_btn.clicked.connect(self._copy_snippet)
        code_header.addWidget(self._copy_btn)
        layout.addLayout(code_header)

        self._code_view = QTextEdit()
        self._code_view.setReadOnly(True)
        self._code_view.setPlainText(CODE_SNIPPET)
        self._code_view.setFont(QFont("Courier", 11))
        self._code_view.setStyleSheet(
            f"QTextEdit {{ background: {BG_CARD}; color: #A8D8A8; "
            f"border: 1px solid {BORDER_DEFAULT}; border-radius: 6px; "
            "padding: 8px; }}"
        )
        layout.addWidget(self._code_view, stretch=1)

        # -- Bottom buttons -------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._open_folder_btn = QPushButton("Open project folder")
        self._open_folder_btn.setStyleSheet(CANCEL_BTN_STYLE)
        self._open_folder_btn.clicked.connect(self._open_folder)
        if not self._project_dir:
            self._open_folder_btn.setEnabled(False)
        btn_row.addWidget(self._open_folder_btn)

        btn_row.addStretch()

        start_btn = QPushButton("Start")
        start_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        start_btn.clicked.connect(self.accept)
        btn_row.addWidget(start_btn)

        layout.addLayout(btn_row)

    # -- actions ------------------------------------------------------------

    def _copy_snippet(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(CODE_SNIPPET)
        self._copy_btn.setText("Copied!")
        # Reset label after a short delay (using a singleShot timer)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._copy_btn.setText("Copy"))

    def _open_folder(self):
        folder = Path(self._project_dir)
        if not folder.is_dir():
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
