"""Shared Folder collaboration workflow dialogs.

Provides UI for setting up and managing shared-folder-based
team annotation workflows (Google Drive, OneDrive, Dropbox, etc.).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QFrame,
    QWidget,
    QScrollArea,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QProgressBar,
    QSizePolicy,
)

logger = logging.getLogger(__name__)

# ── Dark Theme Constants ──

DARK_BG = "#1E1E2E"
CARD_BG = "#2A2A3C"
TEXT_COLOR = "#E8E8F0"
ACCENT = "#F5A623"
MUTED = "#8888A0"
BORDER = "#404060"
HOVER_BG = "#505070"
BUTTON_BG = "#404060"

DARK_STYLE = f"""
    QDialog {{ background: {DARK_BG}; }}
    QLabel {{ color: {TEXT_COLOR}; font-size: 12px; }}
    QLineEdit {{
        background: {CARD_BG}; color: {TEXT_COLOR}; border: 1px solid {BORDER};
        border-radius: 4px; padding: 6px; font-size: 12px;
    }}
    QLineEdit:focus {{ border-color: {ACCENT}; }}
    QPushButton {{
        background: {BUTTON_BG}; color: {TEXT_COLOR}; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: none;
    }}
    QPushButton:hover {{ background: {HOVER_BG}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QFrame {{ background: transparent; }}
"""

ACCENT_BUTTON_STYLE = f"""
    QPushButton {{
        background: {ACCENT}; color: {DARK_BG}; font-size: 13px;
        font-weight: bold; padding: 10px 24px; border-radius: 6px; border: none;
    }}
    QPushButton:hover {{ background: #FFB833; }}
    QPushButton:disabled {{ background: {BORDER}; color: {MUTED}; }}
"""

CARD_STYLE = f"""
    QFrame {{
        background: {CARD_BG}; border: 2px solid {BORDER};
        border-radius: 8px; padding: 16px;
    }}
    QFrame:hover {{ border-color: {ACCENT}; }}
"""

CARD_STYLE_SELECTED = f"""
    QFrame {{
        background: {CARD_BG}; border: 2px solid {ACCENT};
        border-radius: 8px; padding: 16px;
    }}
"""


def _make_section_label(text: str) -> QLabel:
    """Create a muted section label."""
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; font-size: 11px; font-weight: bold;")
    return label


def _make_title_label(text: str) -> QLabel:
    """Create an accent-coloured title label."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ACCENT};")
    return label


def _make_subtitle_label(text: str) -> QLabel:
    """Create a centred muted subtitle."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
    return label


# ──────────────────────────────────────────────────────────────────────
# 1. SharedFolderSetupDialog
# ──────────────────────────────────────────────────────────────────────


class SharedFolderSetupDialog(QDialog):
    """Initial setup when the user selects the Shared Folder workflow.

    Presents two cards:
      - Connect to an existing shared folder
      - Set up a new shared folder (shows a guide)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shared Folder Setup")
        self.setFixedSize(540, 440)
        self.setStyleSheet(DARK_STYLE)

        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Title
        layout.addWidget(_make_title_label("Shared Folder Collaboration"))
        layout.addWidget(
            _make_subtitle_label(
                "Work on the same project with your team via a synced folder."
            )
        )
        layout.addSpacing(4)

        # Name input
        layout.addWidget(_make_section_label("YOUR NAME"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Jason")
        layout.addWidget(self._name_edit)

        layout.addSpacing(8)

        # ── Card: Connect to existing ──
        self._connect_card = self._build_card(
            "\U0001F4C2  Connect to existing shared folder",
            "I already have a Google Drive / OneDrive / Dropbox folder\n"
            "that my team can access.",
        )
        self._connect_card.mousePressEvent = lambda _e: self._open_connect_dialog()
        layout.addWidget(self._connect_card)

        # ── Card: Setup guide ──
        self._guide_card = self._build_card(
            "\U0001F4D6  I need to set up a shared folder first",
            "Show me how to create one.",
        )
        self._guide_card.mousePressEvent = lambda _e: self._open_guide_dialog()
        layout.addWidget(self._guide_card)

        layout.addStretch()

    # ── helpers ──

    def _build_card(self, title: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(4)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: bold;")
        card_layout.addWidget(t_lbl)

        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        s_lbl.setWordWrap(True)
        card_layout.addWidget(s_lbl)

        return card

    def _open_connect_dialog(self):
        name = self._name_edit.text().strip()
        dlg = SharedFolderConnectDialog(annotator_name=name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._result = dlg.get_result()
            self.accept()

    def _open_guide_dialog(self):
        name = self._name_edit.text().strip()
        dlg = SharedFolderGuideDialog(annotator_name=name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Guide dialog hands back a folder path; open the connect dialog
            folder = dlg.get_selected_folder()
            if folder:
                cdlg = SharedFolderConnectDialog(
                    annotator_name=name, initial_path=folder, parent=self
                )
                if cdlg.exec() == QDialog.DialogCode.Accepted:
                    self._result = cdlg.get_result()
                    self.accept()

    # ── public API ──

    def get_result(self) -> dict:
        """Return ``{"annotator": str, "folder_path": str}`` or ``{}``."""
        return self._result


# ──────────────────────────────────────────────────────────────────────
# 2. SharedFolderConnectDialog
# ──────────────────────────────────────────────────────────────────────


class SharedFolderConnectDialog(QDialog):
    """Connect to an existing shared folder and validate its structure."""

    def __init__(
        self,
        annotator_name: str = "",
        initial_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Connect to Shared Folder")
        self.setFixedSize(560, 480)
        self.setStyleSheet(DARK_STYLE)

        self._folder_path = initial_path
        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        layout.addWidget(_make_title_label("Connect to Shared Folder"))
        layout.addSpacing(4)

        # Folder browser row
        layout.addWidget(_make_section_label("SHARED FOLDER"))
        folder_row = QHBoxLayout()
        self._path_edit = QLineEdit(initial_path)
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("Select a folder...")
        folder_row.addWidget(self._path_edit, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Validation checklist
        layout.addSpacing(6)
        layout.addWidget(_make_section_label("VALIDATION"))

        self._checks_frame = QFrame()
        self._checks_frame.setStyleSheet(
            f"QFrame {{ background: {CARD_BG}; border-radius: 6px; padding: 10px; }}"
        )
        checks_layout = QVBoxLayout(self._checks_frame)
        checks_layout.setSpacing(6)
        checks_layout.setContentsMargins(12, 10, 12, 10)

        self._chk_folder = QLabel()
        self._chk_annotations = QLabel()
        self._chk_frames = QLabel()
        self._chk_project = QLabel()
        for w in (self._chk_folder, self._chk_annotations, self._chk_frames, self._chk_project):
            w.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
            checks_layout.addWidget(w)

        layout.addWidget(self._checks_frame)

        # Name field
        layout.addSpacing(6)
        layout.addWidget(_make_section_label("YOUR NAME"))
        self._name_edit = QLineEdit(annotator_name)
        self._name_edit.setPlaceholderText("e.g. Jason")
        self._name_edit.textChanged.connect(self._refresh_connect_state)
        layout.addWidget(self._name_edit)

        layout.addStretch()

        # Bottom buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        self._connect_btn = QPushButton("Connect  \u2192")
        self._connect_btn.setStyleSheet(ACCENT_BUTTON_STYLE)
        self._connect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self._connect_btn)
        layout.addLayout(btn_row)

        # Run initial validation if a path was provided
        if initial_path:
            self._validate_folder()

    # ── folder browser ──

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Shared Folder", str(Path.home())
        )
        if path:
            self._folder_path = path
            self._path_edit.setText(path)
            self._validate_folder()

    # ── validation ──

    def _validate_folder(self):
        root = Path(self._folder_path) if self._folder_path else None
        self._valid = False

        if not root or not root.is_dir():
            self._set_check(self._chk_folder, False, "Folder found")
            self._set_check(self._chk_annotations, False, "annotations/ directory")
            self._set_check(self._chk_frames, False, "frames/ directory")
            self._set_check(self._chk_project, False, "project.json found")
            self._refresh_connect_state()
            return

        self._set_check(self._chk_folder, True, "Folder found")

        # annotations/
        ann_dir = root / "annotations"
        if ann_dir.is_dir():
            n_ann = len(list(ann_dir.glob("*.json")))
            self._set_check(
                self._chk_annotations,
                True,
                f"annotations/ directory exists ({n_ann} files)",
            )
        else:
            # Attempt to create it
            try:
                ann_dir.mkdir(parents=True, exist_ok=True)
                self._set_check(
                    self._chk_annotations,
                    True,
                    "annotations/ directory created (0 files)",
                )
            except OSError:
                self._set_check(
                    self._chk_annotations, False, "annotations/ directory missing"
                )

        # frames/
        frames_dir = root / "frames"
        if frames_dir.is_dir():
            n_frames = len(
                [
                    f
                    for f in frames_dir.iterdir()
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
                ]
            )
            self._set_check(
                self._chk_frames,
                True,
                f"frames/ directory exists ({n_frames} files)",
            )
        else:
            self._set_check(self._chk_frames, False, "frames/ directory missing")

        # project.json
        proj = root / "project.json"
        if proj.is_file():
            self._set_check(self._chk_project, True, "project.json found")
        else:
            self._set_check(self._chk_project, False, "project.json not found")

        # Overall validity: folder + frames must exist at minimum
        folder_ok = root.is_dir()
        frames_ok = (root / "frames").is_dir()
        self._valid = folder_ok and frames_ok

        self._refresh_connect_state()

    @staticmethod
    def _set_check(label: QLabel, ok: bool, text: str):
        icon = "\u2705" if ok else "\u274C"
        label.setText(f"{icon}  {text}")

    def _refresh_connect_state(self):
        has_name = bool(self._name_edit.text().strip())
        valid = getattr(self, "_valid", False)
        self._connect_btn.setEnabled(has_name and valid)

    # ── connect ──

    def _on_connect(self):
        root = Path(self._folder_path)

        # Ensure annotations/ exists
        (root / "annotations").mkdir(parents=True, exist_ok=True)

        # Ensure .claims/ directory exists for team tracking
        (root / "annotations" / ".claims").mkdir(parents=True, exist_ok=True)

        self._result = {
            "annotator": self._name_edit.text().strip(),
            "folder_path": self._folder_path,
        }
        self.accept()

    def get_result(self) -> dict:
        """Return ``{"annotator": str, "folder_path": str}`` or ``{}``."""
        return self._result


# ──────────────────────────────────────────────────────────────────────
# 3. SharedFolderGuideDialog
# ──────────────────────────────────────────────────────────────────────

_GUIDE_GOOGLE_DRIVE = """\
Step 1 - Open Google Drive
    Go to drive.google.com in your browser and sign in.

Step 2 - Create a project folder
    Click "+ New" > "New folder".
    Name it something like "team_annotation_project".

Step 3 - Share with your team
    Right-click the folder > "Share".
    Add each teammate's email address.
    Set permission to "Editor" so they can add/edit files.

Step 4 - Install Google Drive for Desktop
    Each team member downloads Google Drive for Desktop:
      https://www.google.com/drive/download/

Step 5 - Locate the synced folder on your computer
    After installation the shared folder appears in your file system:

    macOS:   ~/Library/CloudStorage/GoogleDrive-<email>/Shared drives/
             or ~/Google Drive/My Drive/team_annotation_project
    Windows: G:\\My Drive\\team_annotation_project
    Linux:   Google Drive for Desktop is not officially available on Linux.
             Consider using a tool like rclone or Insync.

Step 6 - Add project frames
    Copy your video frames (images) into a "frames/" subfolder:
      team_annotation_project/
        frames/
          frame_0001.jpg
          frame_0002.jpg
          ...
        project.json   (created by the annotation tool)
        annotations/   (created automatically)
"""

_GUIDE_ONEDRIVE = """\
Step 1 - Open OneDrive
    Go to onedrive.live.com and sign in with your Microsoft account.

Step 2 - Create a project folder
    Click "+ New" > "Folder".
    Name it "team_annotation_project".

Step 3 - Share with your team
    Right-click the folder > "Share".
    Enter teammates' email addresses.
    Choose "Can edit" permission.

Step 4 - Install OneDrive sync client
    OneDrive is built into Windows 10/11.
    macOS: Download from the Mac App Store.

Step 5 - Locate the synced folder
    macOS:   ~/Library/CloudStorage/OneDrive-<account>/team_annotation_project
    Windows: C:\\Users\\<you>\\OneDrive\\team_annotation_project

Step 6 - Add project frames
    Copy your video frames into a "frames/" subfolder inside the shared folder.
    The annotation tool will create the annotations/ directory automatically.
"""

_GUIDE_DROPBOX = """\
Step 1 - Open Dropbox
    Go to dropbox.com and sign in.

Step 2 - Create a shared folder
    Click "Create" > "Shared folder" > "New shared folder".
    Name it "team_annotation_project".

Step 3 - Invite your team
    Enter teammates' email addresses.
    Set permission to "Can edit".

Step 4 - Install Dropbox Desktop App
    Download from https://www.dropbox.com/install

Step 5 - Locate the synced folder
    macOS:   ~/Dropbox/team_annotation_project
    Windows: C:\\Users\\<you>\\Dropbox\\team_annotation_project
    Linux:   ~/Dropbox/team_annotation_project

Step 6 - Add project frames
    Copy your video frames into a "frames/" subfolder.
    The annotation tool handles the rest.
"""

_GUIDE_OTHER = """\
Any folder that is synced across your team's computers will work.

Requirements:
  - All team members can read/write to the folder.
  - The folder contains a "frames/" subfolder with image files.
  - (Optional) A project.json created by the annotation tool.

Suggested structure:
  shared_folder/
    frames/
      frame_0001.jpg
      frame_0002.jpg
      ...
    annotations/        (auto-created)
    project.json        (auto-created)

Cloud services that work:
  - Google Drive for Desktop
  - Microsoft OneDrive
  - Dropbox
  - Syncthing (self-hosted)
  - Nextcloud (self-hosted)
  - Any mounted network drive (SMB, NFS)

After setting up the shared folder, click "Connect to Folder" below.
"""

_GUIDES = {
    "Google Drive": _GUIDE_GOOGLE_DRIVE,
    "OneDrive": _GUIDE_ONEDRIVE,
    "Dropbox": _GUIDE_DROPBOX,
    "Other": _GUIDE_OTHER,
}


class SharedFolderGuideDialog(QDialog):
    """In-app setup guide for creating a shared folder."""

    def __init__(self, annotator_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Up a Shared Folder")
        self.setFixedSize(600, 520)
        self.setStyleSheet(DARK_STYLE)

        self._annotator_name = annotator_name
        self._selected_folder: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        layout.addWidget(_make_title_label("Set Up a Shared Folder"))
        layout.addWidget(
            _make_subtitle_label("Follow the steps for your cloud service.")
        )
        layout.addSpacing(4)

        # Platform tabs (row of buttons)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)
        self._tab_buttons: list[QPushButton] = []
        self._current_tab = "Google Drive"

        for name in ("Google Drive", "OneDrive", "Dropbox", "Other"):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._switch_tab(n))
            tab_row.addWidget(btn)
            self._tab_buttons.append(btn)

        layout.addLayout(tab_row)

        # Scrollable guide text
        self._guide_area = QScrollArea()
        self._guide_area.setWidgetResizable(True)
        self._guide_label = QLabel()
        self._guide_label.setWordWrap(True)
        self._guide_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._guide_label.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 12px; padding: 10px; "
            f"background: {CARD_BG}; border-radius: 6px;"
        )
        self._guide_label.setTextFormat(Qt.TextFormat.PlainText)
        self._guide_area.setWidget(self._guide_label)
        layout.addWidget(self._guide_area, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        back_btn = QPushButton("\u2190  Back")
        back_btn.clicked.connect(self.reject)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()

        connect_btn = QPushButton("Connect to Folder  \u2192")
        connect_btn.setStyleSheet(ACCENT_BUTTON_STYLE)
        connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(connect_btn)
        layout.addLayout(btn_row)

        # Show initial tab
        self._switch_tab("Google Drive")

    def _switch_tab(self, name: str):
        self._current_tab = name
        self._guide_label.setText(_GUIDES.get(name, ""))

        # Update button styles to highlight active tab
        for btn in self._tab_buttons:
            if btn.text() == name:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {ACCENT}; color: {DARK_BG}; "
                    f"font-weight: bold; padding: 8px 16px; border-radius: 4px; border: none; }}"
                    f"QPushButton:hover {{ background: #FFB833; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {BUTTON_BG}; color: {TEXT_COLOR}; "
                    f"padding: 8px 16px; border-radius: 4px; border: none; }}"
                    f"QPushButton:hover {{ background: {HOVER_BG}; }}"
                )

    def _on_connect(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Shared Folder", str(Path.home())
        )
        if path:
            self._selected_folder = path
            self.accept()

    def get_selected_folder(self) -> str:
        return self._selected_folder


# ──────────────────────────────────────────────────────────────────────
# 4. TeamPanel
# ──────────────────────────────────────────────────────────────────────


class TeamPanel(QWidget):
    """Collapsible side panel showing team status during Shared Folder workflow.

    Reads ``.claims/`` directory inside the project's ``annotations/`` folder
    to discover team members and their claimed frames.
    """

    REFRESH_INTERVAL_MS = 30_000  # 30 seconds

    def __init__(self, collaboration_manager, parent=None):
        super().__init__(parent)
        self._collab = collaboration_manager
        self._collapsed = False

        self.setStyleSheet(f"background: {DARK_BG};")
        self.setFixedWidth(260)

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(8, 8, 8, 8)
        self._outer_layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        header_label = QLabel("TEAM")
        header_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: bold;"
        )
        header_row.addWidget(header_label)
        header_row.addStretch()

        self._collapse_btn = QPushButton("\u2212")  # minus sign
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setStyleSheet(
            f"QPushButton {{ background: {BUTTON_BG}; color: {TEXT_COLOR}; "
            f"border-radius: 4px; font-size: 14px; font-weight: bold; border: none; padding: 0; }}"
            f"QPushButton:hover {{ background: {HOVER_BG}; }}"
        )
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_row.addWidget(self._collapse_btn)
        self._outer_layout.addLayout(header_row)

        # Content area (collapsible)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)

        # Scrollable member list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border: none; background: transparent;")
        self._members_widget = QWidget()
        self._members_layout = QVBoxLayout(self._members_widget)
        self._members_layout.setContentsMargins(0, 0, 0, 0)
        self._members_layout.setSpacing(4)
        self._members_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._members_widget)
        self._content_layout.addWidget(self._scroll, stretch=1)

        # Unclaimed frames label
        self._unclaimed_label = QLabel()
        self._unclaimed_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self._content_layout.addWidget(self._unclaimed_label)

        # Action buttons
        self._claim_btn = QPushButton("Claim Frames")
        self._claim_btn.setStyleSheet(ACCENT_BUTTON_STYLE)
        self._claim_btn.clicked.connect(self._open_claim_dialog)
        self._content_layout.addWidget(self._claim_btn)

        self._refresh_btn = QPushButton("Refresh Team Status")
        self._refresh_btn.clicked.connect(self.refresh)
        self._content_layout.addWidget(self._refresh_btn)

        self._outer_layout.addWidget(self._content, stretch=1)

        # Auto-refresh timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self.REFRESH_INTERVAL_MS)

        # Initial load
        self.refresh()

    # ── collapse ──

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._collapse_btn.setText("+" if self._collapsed else "\u2212")
        if self._collapsed:
            self.setFixedWidth(260)
        else:
            self.setFixedWidth(260)

    # ── refresh ──

    def refresh(self):
        """Re-read .claims/ directory and update the member list."""
        # Clear existing member widgets
        while self._members_layout.count():
            item = self._members_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        claims_dir = self._collab.project_root / "annotations" / ".claims"
        if not claims_dir.is_dir():
            self._unclaimed_label.setText("No claims directory found.")
            return

        now = time.time()
        all_claimed_frames: set[str] = set()
        members: list[dict] = []

        for claim_file in sorted(claims_dir.glob("*.json")):
            try:
                data = json.loads(claim_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read claim file: %s", claim_file)
                continue

            name = data.get("annotator", claim_file.stem)
            frames = data.get("frames", [])
            annotated = data.get("annotated", 0)
            last_active = data.get("last_active", 0)

            all_claimed_frames.update(frames)

            # Determine status
            age = now - last_active if last_active else float("inf")
            if age < 300:  # active within 5 minutes
                status = "\U0001F7E2"  # green circle
            elif age < 3600:  # within 1 hour
                status = "\u26A0\uFE0F"  # warning
            else:
                status = "\u2B1C"  # white square (inactive)

            members.append(
                {
                    "name": name,
                    "frames": frames,
                    "annotated": annotated,
                    "total": len(frames),
                    "status": status,
                }
            )

        current_user = self._collab.annotator

        for m in members:
            widget = self._build_member_widget(m, is_you=(m["name"] == current_user))
            self._members_layout.addWidget(widget)

        # Calculate unclaimed frames
        try:
            frames_dir = self._collab.project_root / "frames"
            if frames_dir.is_dir():
                all_frames = {
                    f.name
                    for f in frames_dir.iterdir()
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
                }
                unclaimed = all_frames - all_claimed_frames
                self._unclaimed_label.setText(
                    f"{len(unclaimed)} unclaimed frame{'s' if len(unclaimed) != 1 else ''}"
                )
            else:
                self._unclaimed_label.setText("frames/ directory not found")
        except OSError:
            self._unclaimed_label.setText("Could not read frames directory")

    def _build_member_widget(self, member: dict, is_you: bool) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {CARD_BG}; border-radius: 6px; padding: 6px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Top row: status + name
        top_row = QHBoxLayout()
        status_lbl = QLabel(member["status"])
        status_lbl.setFixedWidth(20)
        status_lbl.setStyleSheet("font-size: 12px;")
        top_row.addWidget(status_lbl)

        name_text = member["name"]
        if is_you:
            name_text += "  (you)"
        name_lbl = QLabel(name_text)
        name_lbl.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 12px; font-weight: bold;"
        )
        top_row.addWidget(name_lbl)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Claimed range
        frames = member["frames"]
        if frames:
            range_text = f"Frames: {frames[0]} \u2013 {frames[-1]}" if len(frames) > 1 else f"Frame: {frames[0]}"
            range_lbl = QLabel(range_text)
            range_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            layout.addWidget(range_lbl)

        # Progress bar
        total = member["total"]
        annotated = member["annotated"]
        if total > 0:
            progress = QProgressBar()
            progress.setRange(0, total)
            progress.setValue(annotated)
            progress.setTextVisible(True)
            progress.setFormat(f"{annotated}/{total}")
            progress.setFixedHeight(14)
            progress.setStyleSheet(
                f"""
                QProgressBar {{
                    background: {DARK_BG}; border: 1px solid {BORDER};
                    border-radius: 4px; text-align: center;
                    color: {TEXT_COLOR}; font-size: 10px;
                }}
                QProgressBar::chunk {{
                    background: {ACCENT}; border-radius: 3px;
                }}
                """
            )
            layout.addWidget(progress)

        return frame

    # ── claim dialog ──

    def _open_claim_dialog(self):
        try:
            frames_dir = self._collab.project_root / "frames"
            if not frames_dir.is_dir():
                return

            all_frames = sorted(
                f.name
                for f in frames_dir.iterdir()
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
            )

            # Determine which frames are already claimed
            claims_dir = self._collab.project_root / "annotations" / ".claims"
            claimed: set[str] = set()
            if claims_dir.is_dir():
                for cf in claims_dir.glob("*.json"):
                    try:
                        data = json.loads(cf.read_text(encoding="utf-8"))
                        claimed.update(data.get("frames", []))
                    except (json.JSONDecodeError, OSError):
                        pass

            available = [f for f in all_frames if f not in claimed]
            if not available:
                return

            dlg = ClaimDialog(available_frames=available, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                result = dlg.get_result()
                frames_to_claim = result.get("frames", [])
                if frames_to_claim:
                    self._save_claim(frames_to_claim)
                    self.refresh()
        except OSError as e:
            logger.error("Error opening claim dialog: %s", e)

    def _save_claim(self, frames: list[str]):
        """Write/update a claim file for the current annotator."""
        claims_dir = self._collab.project_root / "annotations" / ".claims"
        claims_dir.mkdir(parents=True, exist_ok=True)

        name = self._collab.annotator
        claim_path = claims_dir / f"{name}.json"

        existing_frames: list[str] = []
        existing_annotated = 0
        if claim_path.exists():
            try:
                data = json.loads(claim_path.read_text(encoding="utf-8"))
                existing_frames = data.get("frames", [])
                existing_annotated = data.get("annotated", 0)
            except (json.JSONDecodeError, OSError):
                pass

        merged = existing_frames + [f for f in frames if f not in existing_frames]

        claim_data = {
            "annotator": name,
            "frames": merged,
            "annotated": existing_annotated,
            "last_active": time.time(),
        }
        claim_path.write_text(
            json.dumps(claim_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


# ──────────────────────────────────────────────────────────────────────
# 5. ClaimDialog
# ──────────────────────────────────────────────────────────────────────


class ClaimDialog(QDialog):
    """Dialog for claiming unclaimed frames."""

    def __init__(self, available_frames: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claim Frames")
        self.setFixedSize(420, 360)
        self.setStyleSheet(DARK_STYLE)

        self._available = available_frames
        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        layout.addWidget(_make_title_label("Claim Frames"))

        # Info
        n = len(available_frames)
        if n > 1:
            range_text = f"{n} unclaimed frames available  ({available_frames[0]} \u2013 {available_frames[-1]})"
        elif n == 1:
            range_text = f"1 unclaimed frame available  ({available_frames[0]})"
        else:
            range_text = "No unclaimed frames available"

        info_label = QLabel(range_text)
        info_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(4)

        # Radio options
        self._btn_group = QButtonGroup(self)

        # Option 1: Next N frames
        opt1_row = QHBoxLayout()
        self._radio_next_n = QRadioButton("Next")
        self._radio_next_n.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
        self._radio_next_n.setChecked(True)
        self._btn_group.addButton(self._radio_next_n, 0)
        opt1_row.addWidget(self._radio_next_n)

        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, n)
        self._spin_count.setValue(min(10, n))
        self._spin_count.setFixedWidth(70)
        self._spin_count.setStyleSheet(
            f"QSpinBox {{ background: {CARD_BG}; color: {TEXT_COLOR}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; padding: 4px; font-size: 12px; }}"
            f"QSpinBox:focus {{ border-color: {ACCENT}; }}"
        )
        opt1_row.addWidget(self._spin_count)

        frames_label = QLabel("frames")
        frames_label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
        opt1_row.addWidget(frames_label)
        opt1_row.addStretch()
        layout.addLayout(opt1_row)

        # Option 2: Custom range
        self._radio_custom = QRadioButton("Custom range")
        self._radio_custom.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
        self._btn_group.addButton(self._radio_custom, 1)
        layout.addWidget(self._radio_custom)

        range_row = QHBoxLayout()
        range_row.setContentsMargins(24, 0, 0, 0)

        start_label = QLabel("Start:")
        start_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        range_row.addWidget(start_label)

        self._start_edit = QLineEdit()
        self._start_edit.setPlaceholderText(available_frames[0] if available_frames else "")
        self._start_edit.setFixedWidth(140)
        range_row.addWidget(self._start_edit)

        end_label = QLabel("End:")
        end_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        range_row.addWidget(end_label)

        self._end_edit = QLineEdit()
        self._end_edit.setPlaceholderText(available_frames[-1] if available_frames else "")
        self._end_edit.setFixedWidth(140)
        range_row.addWidget(self._end_edit)

        range_row.addStretch()
        layout.addLayout(range_row)

        # Option 3: All remaining
        self._radio_all = QRadioButton(f"All remaining ({n} frames)")
        self._radio_all.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
        self._btn_group.addButton(self._radio_all, 2)
        layout.addWidget(self._radio_all)

        layout.addStretch()

        # Bottom buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        claim_btn = QPushButton("Claim  \u2192")
        claim_btn.setStyleSheet(ACCENT_BUTTON_STYLE)
        claim_btn.clicked.connect(self._on_claim)
        btn_row.addWidget(claim_btn)
        layout.addLayout(btn_row)

    def _on_claim(self):
        selected_id = self._btn_group.checkedId()
        frames: list[str] = []

        if selected_id == 0:
            # Next N frames
            count = self._spin_count.value()
            frames = self._available[:count]

        elif selected_id == 1:
            # Custom range
            start_name = self._start_edit.text().strip()
            end_name = self._end_edit.text().strip()

            if not start_name or not end_name:
                # Fall back: use placeholders if empty
                start_name = start_name or (self._available[0] if self._available else "")
                end_name = end_name or (self._available[-1] if self._available else "")

            try:
                start_idx = self._available.index(start_name)
                end_idx = self._available.index(end_name)
                if start_idx > end_idx:
                    start_idx, end_idx = end_idx, start_idx
                frames = self._available[start_idx : end_idx + 1]
            except ValueError:
                # If names not found, try numeric matching
                frames = self._resolve_custom_range(start_name, end_name)

        elif selected_id == 2:
            # All remaining
            frames = list(self._available)

        if frames:
            self._result = {"frames": frames}
            self.accept()

    def _resolve_custom_range(self, start: str, end: str) -> list[str]:
        """Try to resolve a custom range even if exact names don't match.

        Matches filenames that are lexicographically between *start* and *end*.
        """
        result = [
            f for f in self._available if start <= f <= end
        ]
        return result

    def get_result(self) -> dict:
        """Return ``{"frames": [str]}`` -- list of filenames to claim."""
        return self._result
