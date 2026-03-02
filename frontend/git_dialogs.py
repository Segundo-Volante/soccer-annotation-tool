"""Git collaboration workflow dialogs for the football annotation tool.

Provides dialogs for initializing, cloning, and connecting Git repos,
along with settings, history viewing, and error handling for missing Git.
"""

import os
import platform
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QGroupBox, QCheckBox, QComboBox, QFrame, QScrollArea,
    QWidget, QStackedWidget, QSpinBox, QTextEdit, QListWidget, QListWidgetItem,
)


# ── Shared dark theme ──────────────────────────────────────────────

DARK_STYLE = """
    QDialog { background: #1E1E2E; }
    QLabel { color: #E8E8F0; font-size: 12px; }
    QLineEdit, QComboBox, QSpinBox {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        border-radius: 4px; padding: 6px; font-size: 12px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #F5A623; }
    QLineEdit:read-only {
        background: #232334; color: #AAAAC0;
    }
    QPushButton {
        background: #404060; color: #E8E8F0; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: none;
    }
    QPushButton:hover { background: #505070; }
    QPushButton:disabled { background: #333348; color: #666680; }
    QGroupBox {
        color: #8888A0; font-size: 11px; border: 1px solid #404060;
        border-radius: 6px; margin-top: 8px; padding-top: 16px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
    QCheckBox { color: #E8E8F0; font-size: 11px; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QScrollArea { border: none; background: transparent; }
    QTextEdit {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        border-radius: 4px; font-family: monospace; font-size: 11px;
    }
    QListWidget {
        background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
        border-radius: 4px; font-size: 12px;
    }
    QListWidget::item { padding: 4px 8px; }
    QListWidget::item:selected { background: #404060; }
"""

ACCENT_BTN_STYLE = """
    QPushButton {
        background: #F5A623; color: #1E1E2E; font-size: 13px;
        font-weight: bold; padding: 10px 24px; border-radius: 6px;
    }
    QPushButton:hover { background: #FFB833; }
    QPushButton:disabled { background: #555560; color: #888890; }
"""

CARD_STYLE = """
    QFrame {{
        background: #2A2A3C; border: 2px solid {border};
        border-radius: 8px; padding: 16px;
    }}
    QFrame:hover {{
        border-color: #F5A623; background: #2E2E42;
    }}
"""

DANGER_BTN_STYLE = """
    QPushButton {
        background: #D9534F; color: #FFFFFF; font-size: 12px;
        font-weight: bold; padding: 8px 16px; border-radius: 4px;
    }
    QPushButton:hover { background: #E06560; }
"""


def _make_section_label(text: str) -> QLabel:
    """Create a small, muted section header label."""
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
    return lbl


def _make_separator() -> QFrame:
    """Create a horizontal line separator."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("color: #404060;")
    return sep


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 10) -> tuple[bool, str]:
    """Run a git command and return (success, output).

    Returns:
        Tuple of (success_bool, stdout_or_stderr_text).
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or result.stdout.strip()
    except FileNotFoundError:
        return False, "Git is not installed or not found in PATH."
    except subprocess.TimeoutExpired:
        return False, "Git command timed out."
    except Exception as e:
        return False, str(e)


def _is_git_installed() -> bool:
    """Check whether git is available on the system."""
    ok, _ = _run_git(["--version"])
    return ok


# ═══════════════════════════════════════════════════════════════════
# 1. GitSetupDialog
# ═══════════════════════════════════════════════════════════════════

class GitSetupDialog(QDialog):
    """Main setup screen when user selects the Git collaboration workflow.

    Shows three workflow options as clickable cards and collects the
    user's name and email for git identity configuration.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git Collaboration Setup")
        self.setFixedSize(560, 520)
        self.setStyleSheet(DARK_STYLE)

        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Git Collaboration Setup")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        subtitle = QLabel("Version-control your annotations so your team can collaborate.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8888A0; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(_make_separator())

        # Identity fields
        identity_group = QGroupBox("Your Identity (used for git commits)")
        id_layout = QVBoxLayout(identity_group)

        id_layout.addWidget(_make_section_label("Your name"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Jason Liu")
        id_layout.addWidget(self._name_input)

        id_layout.addWidget(_make_section_label("Email"))
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("e.g. jason@example.com")
        id_layout.addWidget(self._email_input)

        layout.addWidget(identity_group)

        # Pre-fill from global git config if available
        self._prefill_identity()

        layout.addWidget(_make_separator())

        # Option cards
        layout.addWidget(_make_section_label("Choose how to get started"))

        self._init_card = self._make_option_card(
            "\U0001F4C1  Initialize new Git repo",
            "Set up Git from scratch in your project folder.",
            self._on_init_clicked,
        )
        layout.addWidget(self._init_card)

        self._clone_card = self._make_option_card(
            "\U0001F4E5  Clone existing repo",
            "Download your team's existing annotation repository.",
            self._on_clone_clicked,
        )
        layout.addWidget(self._clone_card)

        self._connect_card = self._make_option_card(
            "\U0001F517  Connect existing local repo",
            "This folder is already a Git repo - just connect it.",
            self._on_connect_clicked,
        )
        layout.addWidget(self._connect_card)

        layout.addStretch()

        # Cancel button
        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

    # ── Helpers ──

    def _prefill_identity(self):
        """Try to read name/email from global git config."""
        ok_name, name = _run_git(["config", "--global", "user.name"])
        if ok_name and name:
            self._name_input.setText(name)
        ok_email, email = _run_git(["config", "--global", "user.email"])
        if ok_email and email:
            self._email_input.setText(email)

    def _make_option_card(self, title: str, description: str,
                          callback) -> QFrame:
        """Build a clickable option card."""
        card = QFrame()
        card.setStyleSheet(CARD_STYLE.format(border="#404060"))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFixedHeight(62)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #E8E8F0; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #8888A0; font-size: 11px; background: transparent; border: none;")
        card_layout.addWidget(desc_lbl)

        card.mousePressEvent = lambda _event, cb=callback: cb()
        return card

    def _validate_identity(self) -> bool:
        """Ensure name and email are filled in."""
        if not self._name_input.text().strip():
            self._name_input.setFocus()
            self._name_input.setStyleSheet(
                "background: #2A2A3C; color: #E8E8F0; border: 2px solid #D9534F; "
                "border-radius: 4px; padding: 6px; font-size: 12px;"
            )
            return False
        if not self._email_input.text().strip():
            self._email_input.setFocus()
            self._email_input.setStyleSheet(
                "background: #2A2A3C; color: #E8E8F0; border: 2px solid #D9534F; "
                "border-radius: 4px; padding: 6px; font-size: 12px;"
            )
            return False
        # Reset borders
        for inp in (self._name_input, self._email_input):
            inp.setStyleSheet("")
        return True

    # ── Card callbacks ──

    def _on_init_clicked(self):
        if not self._validate_identity():
            return
        folder = QFileDialog.getExistingDirectory(self, "Select project folder")
        if not folder:
            return
        dlg = GitInitDialog(folder, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._result = {
                "action": "init",
                "name": self._name_input.text().strip(),
                "email": self._email_input.text().strip(),
                "remote_url": dlg.remote_url(),
                "clone_url": "",
                "clone_dest": "",
                "project_path": folder,
            }
            self.accept()

    def _on_clone_clicked(self):
        if not self._validate_identity():
            return
        dlg = GitCloneDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            self._result = {
                "action": "clone",
                "name": self._name_input.text().strip(),
                "email": self._email_input.text().strip(),
                "remote_url": "",
                "clone_url": result["clone_url"],
                "clone_dest": result["clone_dest"],
                "project_path": result["clone_dest"],
            }
            self.accept()

    def _on_connect_clicked(self):
        if not self._validate_identity():
            return
        dlg = GitConnectDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            self._result = {
                "action": "connect",
                "name": self._name_input.text().strip(),
                "email": self._email_input.text().strip(),
                "remote_url": result.get("remote_url", ""),
                "clone_url": "",
                "clone_dest": "",
                "project_path": result["project_path"],
            }
            self.accept()

    def get_result(self) -> dict:
        """Return the setup result dictionary.

        Keys: action, name, email, remote_url, clone_url, clone_dest, project_path.
        """
        return self._result


# ═══════════════════════════════════════════════════════════════════
# 2. GitInitDialog
# ═══════════════════════════════════════════════════════════════════

class GitInitDialog(QDialog):
    """Multi-step wizard to initialize a new git repository.

    Steps:
        1. Explain what will happen, then run git init + .gitignore + initial commit.
        2. Optionally add a remote URL.
        3. Show success summary.
    """

    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self._project_path = project_path
        self._remote_url_value = ""

        self.setWindowTitle("Initialize Git Repository")
        self.setFixedSize(500, 400)
        self.setStyleSheet(DARK_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Initialize Git Repository")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        # Step pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        self._build_step1()
        self._build_step2()
        self._build_step3()

        # Navigation buttons
        nav_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        nav_row.addWidget(self._cancel_btn)
        nav_row.addStretch()

        self._action_btn = QPushButton("Initialize \u2192")
        self._action_btn.setStyleSheet(ACCENT_BTN_STYLE)
        self._action_btn.clicked.connect(self._on_action)
        nav_row.addWidget(self._action_btn)

        self._skip_btn = QPushButton("Skip")
        self._skip_btn.clicked.connect(self._on_skip)
        self._skip_btn.setVisible(False)
        nav_row.addWidget(self._skip_btn)

        layout.addLayout(nav_row)

    def _build_step1(self):
        """Step 1: Explain what will happen."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(10)

        info = QLabel(
            f"This will set up Git in:\n{self._project_path}\n\n"
            "The following actions will be performed:\n\n"
            "  1. git init   \u2014  Initialize a new repository\n"
            "  2. Create .gitignore  (ignores temp files, caches, etc.)\n"
            "  3. Initial commit  \u2014  Commit the .gitignore file\n\n"
            "Your existing files will NOT be modified or deleted."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #E8E8F0; font-size: 12px; background: #2A2A3C; "
            "border-radius: 6px; padding: 16px; line-height: 1.6;"
        )
        page_layout.addWidget(info)

        self._step1_status = QLabel("")
        self._step1_status.setWordWrap(True)
        self._step1_status.setStyleSheet("color: #8888A0; font-size: 11px;")
        page_layout.addWidget(self._step1_status)

        page_layout.addStretch()
        self._stack.addWidget(page)

    def _build_step2(self):
        """Step 2: Optional remote URL input."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(10)

        page_layout.addWidget(_make_section_label(
            "Add a remote repository (optional)"
        ))

        desc = QLabel(
            "If your team has a shared repository (GitHub, GitLab, etc.), "
            "enter its URL below. You can also add this later from Settings."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8888A0; font-size: 11px;")
        page_layout.addWidget(desc)

        page_layout.addWidget(_make_section_label("Remote URL"))
        self._remote_input = QLineEdit()
        self._remote_input.setPlaceholderText("e.g. https://github.com/team/annotations.git")
        # IMPORTANT: Never pre-fill remote URL
        page_layout.addWidget(self._remote_input)

        self._step2_status = QLabel("")
        self._step2_status.setWordWrap(True)
        self._step2_status.setStyleSheet("color: #8888A0; font-size: 11px;")
        page_layout.addWidget(self._step2_status)

        page_layout.addStretch()
        self._stack.addWidget(page)

    def _build_step3(self):
        """Step 3: Success summary."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(10)

        success_icon = QLabel("\u2705")
        success_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_icon.setStyleSheet("font-size: 36px; background: transparent;")
        page_layout.addWidget(success_icon)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setStyleSheet(
            "color: #E8E8F0; font-size: 13px; background: #2A2A3C; "
            "border-radius: 6px; padding: 16px;"
        )
        page_layout.addWidget(self._summary_label)

        page_layout.addStretch()
        self._stack.addWidget(page)

    # ── Actions ──

    def _on_action(self):
        step = self._stack.currentIndex()
        if step == 0:
            self._do_init()
        elif step == 1:
            self._do_add_remote()
        elif step == 2:
            self.accept()

    def _on_skip(self):
        """Skip the remote URL step."""
        self._remote_url_value = ""
        self._go_to_step3()

    def _do_init(self):
        """Run git init, create .gitignore, and make initial commit."""
        self._action_btn.setEnabled(False)
        self._step1_status.setText("Initializing...")
        self._step1_status.setStyleSheet("color: #F5A623; font-size: 11px;")

        path = self._project_path

        # git init
        ok, msg = _run_git(["init"], cwd=path)
        if not ok:
            self._step1_status.setText(f"Error: {msg}")
            self._step1_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            self._action_btn.setEnabled(True)
            return

        # Create .gitignore
        gitignore_path = Path(path) / ".gitignore"
        if not gitignore_path.exists():
            gitignore_content = (
                "# Annotation tool temp files\n"
                "*.pyc\n"
                "__pycache__/\n"
                ".DS_Store\n"
                "Thumbs.db\n"
                "*.tmp\n"
                "*.bak\n"
                ".locks/\n"
                "*.log\n"
                "\n"
                "# Large media files (add specific video extensions if needed)\n"
                "*.mp4\n"
                "*.avi\n"
                "*.mov\n"
            )
            try:
                gitignore_path.write_text(gitignore_content, encoding="utf-8")
            except OSError as e:
                self._step1_status.setText(f"Error writing .gitignore: {e}")
                self._step1_status.setStyleSheet("color: #D9534F; font-size: 11px;")
                self._action_btn.setEnabled(True)
                return

        # git add .gitignore && git commit
        ok, msg = _run_git(["add", ".gitignore"], cwd=path)
        if not ok:
            self._step1_status.setText(f"Error staging .gitignore: {msg}")
            self._step1_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            self._action_btn.setEnabled(True)
            return

        ok, msg = _run_git(["commit", "-m", "Initial commit: add .gitignore"], cwd=path)
        if not ok:
            self._step1_status.setText(f"Error committing: {msg}")
            self._step1_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            self._action_btn.setEnabled(True)
            return

        # Success - move to step 2
        self._step1_status.setText("Repository initialized successfully.")
        self._step1_status.setStyleSheet("color: #43A047; font-size: 11px;")

        self._stack.setCurrentIndex(1)
        self._action_btn.setText("Add Remote \u2192")
        self._skip_btn.setVisible(True)
        self._action_btn.setEnabled(True)

    def _do_add_remote(self):
        """Add the remote URL to the repo."""
        url = self._remote_input.text().strip()
        if not url:
            self._step2_status.setText("Please enter a URL or click Skip.")
            self._step2_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            return

        self._action_btn.setEnabled(False)
        ok, msg = _run_git(["remote", "add", "origin", url], cwd=self._project_path)
        if not ok:
            # Remote might already exist
            if "already exists" in msg.lower():
                _run_git(["remote", "set-url", "origin", url], cwd=self._project_path)
                self._remote_url_value = url
                self._go_to_step3()
                return
            self._step2_status.setText(f"Error: {msg}")
            self._step2_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            self._action_btn.setEnabled(True)
            return

        self._remote_url_value = url
        self._go_to_step3()

    def _go_to_step3(self):
        """Navigate to the success summary step."""
        remote_text = self._remote_url_value or "(none - can be added later)"
        self._summary_label.setText(
            f"Repository initialized!\n\n"
            f"Location: {self._project_path}\n"
            f"Remote: {remote_text}\n\n"
            f"You're ready to start annotating."
        )
        self._stack.setCurrentIndex(2)
        self._action_btn.setText("Start \u2192")
        self._action_btn.setEnabled(True)
        self._skip_btn.setVisible(False)
        self._cancel_btn.setVisible(False)

    def remote_url(self) -> str:
        """Return the remote URL that was configured (may be empty)."""
        return self._remote_url_value


# ═══════════════════════════════════════════════════════════════════
# 3. GitCloneDialog
# ═══════════════════════════════════════════════════════════════════

class GitCloneDialog(QDialog):
    """Dialog to clone an existing remote repository."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clone Repository")
        self.setFixedSize(500, 320)
        self.setStyleSheet(DARK_STYLE)

        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Clone Existing Repository")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        desc = QLabel(
            "Enter the URL of your team's annotation repository and choose "
            "where to clone it on your machine."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(_make_separator())

        # Repo URL
        layout.addWidget(_make_section_label("Repository URL"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("e.g. https://github.com/team/annotations.git")
        # IMPORTANT: Never pre-fill the URL
        layout.addWidget(self._url_input)

        # Clone destination
        layout.addWidget(_make_section_label("Clone destination"))
        dest_row = QHBoxLayout()
        self._dest_input = QLineEdit()
        self._dest_input.setPlaceholderText("Select folder...")
        self._dest_input.setReadOnly(True)
        dest_row.addWidget(self._dest_input, stretch=1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dest)
        dest_row.addWidget(browse_btn)
        layout.addLayout(dest_row)

        # Status / progress
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        self._clone_btn = QPushButton("Clone \u2192")
        self._clone_btn.setStyleSheet(ACCENT_BTN_STYLE)
        self._clone_btn.clicked.connect(self._do_clone)
        btn_row.addWidget(self._clone_btn)
        layout.addLayout(btn_row)

    def _browse_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Select clone destination")
        if folder:
            self._dest_input.setText(folder)

    def _do_clone(self):
        url = self._url_input.text().strip()
        dest = self._dest_input.text().strip()

        if not url:
            self._status_label.setText("Please enter a repository URL.")
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")
            return
        if not dest:
            self._status_label.setText("Please select a destination folder.")
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")
            return

        self._clone_btn.setEnabled(False)
        self._status_label.setText("Cloning... This may take a moment.")
        self._status_label.setStyleSheet("color: #F5A623; font-size: 11px;")

        # Force UI update before blocking call
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        ok, msg = _run_git(["clone", url, dest], timeout=60)
        if ok:
            self._status_label.setText("Clone successful!")
            self._status_label.setStyleSheet("color: #43A047; font-size: 11px;")
            self._result = {
                "clone_url": url,
                "clone_dest": dest,
            }
            self.accept()
        else:
            self._status_label.setText(f"Clone failed: {msg}")
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")
            self._clone_btn.setEnabled(True)

    def get_result(self) -> dict:
        """Return clone_url and clone_dest."""
        return self._result


# ═══════════════════════════════════════════════════════════════════
# 4. GitConnectDialog
# ═══════════════════════════════════════════════════════════════════

class GitConnectDialog(QDialog):
    """Connect an existing local Git repository to the annotation tool.

    Validates that the selected folder is a git repo and checks for
    expected project structure.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Existing Repository")
        self.setFixedSize(520, 420)
        self.setStyleSheet(DARK_STYLE)

        self._result: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Connect Existing Repository")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        desc = QLabel(
            "Select a folder that is already a Git repository. "
            "We'll validate its structure and connect it."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(_make_separator())

        # Folder picker
        layout.addWidget(_make_section_label("Repository folder"))
        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("Select folder...")
        self._folder_input.setReadOnly(True)
        folder_row.addWidget(self._folder_input, stretch=1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Validation results
        layout.addWidget(_make_section_label("Validation"))

        self._check_git = QLabel("\u2B1C  Is a Git repository?")
        self._check_git.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(self._check_git)

        self._check_remote = QLabel("\u2B1C  Has remote configured?")
        self._check_remote.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(self._check_remote)

        self._check_annotations = QLabel("\u2B1C  Has annotations/ directory?")
        self._check_annotations.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(self._check_annotations)

        self._check_project = QLabel("\u2B1C  Has project.json?")
        self._check_project.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(self._check_project)

        self._remote_display = QLabel("")
        self._remote_display.setStyleSheet("color: #8888A0; font-size: 11px; padding-left: 20px;")
        self._remote_display.setWordWrap(True)
        layout.addWidget(self._remote_display)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        self._connect_btn = QPushButton("Connect \u2192")
        self._connect_btn.setStyleSheet(ACCENT_BTN_STYLE)
        self._connect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self._connect_btn)
        layout.addLayout(btn_row)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select repository folder")
        if folder:
            self._folder_input.setText(folder)
            self._validate(folder)

    def _validate(self, folder: str):
        """Run validation checks on the selected folder."""
        path = Path(folder)
        all_pass = True
        remote_url = ""

        # Check: is git repo?
        ok, _ = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=folder)
        if ok:
            self._check_git.setText("\u2705  Is a Git repository")
        else:
            self._check_git.setText("\u274C  Not a Git repository")
            all_pass = False

        # Check: has remote?
        ok_remote, remote_out = _run_git(["remote", "get-url", "origin"], cwd=folder)
        if ok_remote and remote_out:
            self._check_remote.setText("\u2705  Has remote configured")
            self._remote_display.setText(f"Remote: {remote_out}")
            remote_url = remote_out
        else:
            self._check_remote.setText("\u274C  No remote configured")
            self._remote_display.setText("(You can add a remote later in Settings)")
            # Not a hard failure - remote is optional

        # Check: annotations/ dir
        if (path / "annotations").is_dir():
            self._check_annotations.setText("\u2705  Has annotations/ directory")
        else:
            self._check_annotations.setText("\u274C  No annotations/ directory found")
            # Not a hard failure

        # Check: project.json
        has_project = (
            (path / "project.json").is_file()
            or (path / "config" / "project.json").is_file()
        )
        if has_project:
            self._check_project.setText("\u2705  Has project.json")
        else:
            self._check_project.setText("\u274C  No project.json found")
            # Not a hard failure

        # Enable connect if at least it's a git repo
        is_git = "\u2705" in self._check_git.text()
        self._connect_btn.setEnabled(is_git)

        if is_git and not all_pass:
            self._status_label.setText(
                "Some optional items are missing, but you can still connect."
            )
            self._status_label.setStyleSheet("color: #F5A623; font-size: 11px;")
        elif is_git:
            self._status_label.setText("All checks passed!")
            self._status_label.setStyleSheet("color: #43A047; font-size: 11px;")
        else:
            self._status_label.setText(
                "This folder is not a Git repository. Please select a valid repo."
            )
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")

        # Store remote for result
        self._detected_remote = remote_url

    def _on_connect(self):
        folder = self._folder_input.text().strip()
        if folder:
            self._result = {
                "project_path": folder,
                "remote_url": getattr(self, "_detected_remote", ""),
            }
            self.accept()

    def get_result(self) -> dict:
        """Return project_path and remote_url."""
        return self._result


# ═══════════════════════════════════════════════════════════════════
# 5. GitSettingsDialog
# ═══════════════════════════════════════════════════════════════════

class GitSettingsDialog(QDialog):
    """Settings page for Git collaboration, accessible from the menu.

    Sections: Identity, Remote, Automation, Branch, Advanced.
    """

    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self._project_path = project_path

        self.setWindowTitle("Git Settings")
        self.setFixedSize(560, 620)
        self.setStyleSheet(DARK_STYLE)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(8)

        # Title
        title = QLabel("Git Settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        main_layout.addWidget(title)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(10)

        # ── Identity section ──
        identity_group = QGroupBox("Identity")
        id_layout = QVBoxLayout(identity_group)

        id_layout.addWidget(_make_section_label("Name"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Your name")
        id_layout.addWidget(self._name_input)

        id_layout.addWidget(_make_section_label("Email"))
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("Your email")
        id_layout.addWidget(self._email_input)

        layout.addWidget(identity_group)

        # Pre-fill identity from repo-level or global config
        self._load_identity()

        # ── Remote section ──
        remote_group = QGroupBox("Remote")
        remote_layout = QVBoxLayout(remote_group)

        remote_layout.addWidget(_make_section_label("Remote URL"))
        self._remote_display = QLineEdit()
        self._remote_display.setReadOnly(True)
        self._remote_display.setPlaceholderText("(no remote configured)")
        remote_layout.addWidget(self._remote_display)

        remote_btn_row = QHBoxLayout()
        self._test_remote_btn = QPushButton("Test Connection")
        self._test_remote_btn.clicked.connect(self._test_remote)
        remote_btn_row.addWidget(self._test_remote_btn)

        self._change_remote_btn = QPushButton("Change Remote")
        self._change_remote_btn.clicked.connect(self._change_remote)
        remote_btn_row.addWidget(self._change_remote_btn)

        self._remove_remote_btn = QPushButton("Remove Remote")
        self._remove_remote_btn.setStyleSheet(DANGER_BTN_STYLE)
        self._remove_remote_btn.clicked.connect(self._remove_remote)
        remote_btn_row.addWidget(self._remove_remote_btn)

        remote_layout.addLayout(remote_btn_row)

        self._remote_status = QLabel("")
        self._remote_status.setWordWrap(True)
        self._remote_status.setStyleSheet("color: #8888A0; font-size: 11px;")
        remote_layout.addWidget(self._remote_status)

        layout.addWidget(remote_group)

        self._load_remote()

        # ── Automation section ──
        auto_group = QGroupBox("Automation")
        auto_layout = QVBoxLayout(auto_group)

        auto_commit_row = QHBoxLayout()
        self._auto_commit_cb = QCheckBox("Auto-commit every")
        auto_commit_row.addWidget(self._auto_commit_cb)
        self._auto_commit_frames = QSpinBox()
        self._auto_commit_frames.setRange(5, 500)
        self._auto_commit_frames.setValue(50)
        self._auto_commit_frames.setSuffix(" frames")
        self._auto_commit_frames.setFixedWidth(120)
        auto_commit_row.addWidget(self._auto_commit_frames)
        auto_commit_row.addStretch()
        auto_layout.addLayout(auto_commit_row)

        self._commit_reminder_cb = QCheckBox(
            "Show commit reminder when closing with unsaved changes"
        )
        self._commit_reminder_cb.setChecked(True)
        auto_layout.addWidget(self._commit_reminder_cb)

        layout.addWidget(auto_group)

        # ── Branch section ──
        branch_group = QGroupBox("Branch")
        branch_layout = QVBoxLayout(branch_group)

        branch_layout.addWidget(_make_section_label("Current branch"))
        self._branch_display = QLabel("...")
        self._branch_display.setStyleSheet(
            "color: #F5A623; font-size: 13px; font-weight: bold;"
        )
        branch_layout.addWidget(self._branch_display)

        branch_btn_row = QHBoxLayout()

        branch_btn_row.addWidget(_make_section_label("Switch to:"))
        self._branch_combo = QComboBox()
        self._branch_combo.setMinimumWidth(160)
        branch_btn_row.addWidget(self._branch_combo)

        self._switch_branch_btn = QPushButton("Switch Branch")
        self._switch_branch_btn.clicked.connect(self._switch_branch)
        branch_btn_row.addWidget(self._switch_branch_btn)

        branch_btn_row.addStretch()
        branch_layout.addLayout(branch_btn_row)

        new_branch_row = QHBoxLayout()
        self._new_branch_input = QLineEdit()
        self._new_branch_input.setPlaceholderText("new-branch-name")
        new_branch_row.addWidget(self._new_branch_input, stretch=1)
        self._create_branch_btn = QPushButton("Create New Branch")
        self._create_branch_btn.clicked.connect(self._create_branch)
        new_branch_row.addWidget(self._create_branch_btn)
        branch_layout.addLayout(new_branch_row)

        self._branch_status = QLabel("")
        self._branch_status.setWordWrap(True)
        self._branch_status.setStyleSheet("color: #8888A0; font-size: 11px;")
        branch_layout.addWidget(self._branch_status)

        layout.addWidget(branch_group)

        self._load_branches()

        # ── Advanced section ──
        advanced_group = QGroupBox("Advanced")
        adv_layout = QHBoxLayout(advanced_group)

        history_btn = QPushButton("View Commit History")
        history_btn.clicked.connect(self._view_history)
        adv_layout.addWidget(history_btn)

        terminal_btn = QPushButton("Open in Terminal")
        terminal_btn.clicked.connect(self._open_terminal)
        adv_layout.addWidget(terminal_btn)

        adv_layout.addStretch()
        layout.addWidget(advanced_group)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(ACCENT_BTN_STYLE)
        save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(save_btn)
        main_layout.addLayout(btn_row)

    # ── Loading ──

    def _load_identity(self):
        """Load name/email from local repo config, fallback to global."""
        ok, name = _run_git(["config", "user.name"], cwd=self._project_path)
        if not ok:
            ok, name = _run_git(["config", "--global", "user.name"])
        if ok and name:
            self._name_input.setText(name)

        ok, email = _run_git(["config", "user.email"], cwd=self._project_path)
        if not ok:
            ok, email = _run_git(["config", "--global", "user.email"])
        if ok and email:
            self._email_input.setText(email)

    def _load_remote(self):
        """Load current remote URL."""
        ok, url = _run_git(["remote", "get-url", "origin"], cwd=self._project_path)
        if ok and url:
            self._remote_display.setText(url)
        else:
            self._remote_display.setText("")

    def _load_branches(self):
        """Load branch list and current branch."""
        ok, branch = _run_git(["branch", "--show-current"], cwd=self._project_path)
        if ok:
            self._branch_display.setText(branch or "(detached HEAD)")
        else:
            self._branch_display.setText("(unknown)")

        ok, branches_raw = _run_git(["branch", "--list", "--format=%(refname:short)"],
                                     cwd=self._project_path)
        self._branch_combo.clear()
        if ok and branches_raw:
            branches = [b.strip() for b in branches_raw.split("\n") if b.strip()]
            self._branch_combo.addItems(branches)

    # ── Remote actions ──

    def _test_remote(self):
        url = self._remote_display.text().strip()
        if not url:
            self._remote_status.setText("No remote configured.")
            self._remote_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            return

        self._remote_status.setText("Testing connection...")
        self._remote_status.setStyleSheet("color: #F5A623; font-size: 11px;")
        self._test_remote_btn.setEnabled(False)

        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        ok, msg = _run_git(["ls-remote", "--exit-code", url], cwd=self._project_path,
                           timeout=15)
        if ok:
            self._remote_status.setText("Connection successful!")
            self._remote_status.setStyleSheet("color: #43A047; font-size: 11px;")
        else:
            self._remote_status.setText(f"Connection failed: {msg}")
            self._remote_status.setStyleSheet("color: #D9534F; font-size: 11px;")
        self._test_remote_btn.setEnabled(True)

    def _change_remote(self):
        """Prompt for a new remote URL and set it."""
        # Use a simple inline input approach
        from PyQt6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(
            self, "Change Remote URL",
            "Enter new remote URL:",
            QLineEdit.EchoMode.Normal, "",
        )
        if ok and url.strip():
            current = self._remote_display.text().strip()
            if current:
                success, msg = _run_git(["remote", "set-url", "origin", url.strip()],
                                         cwd=self._project_path)
            else:
                success, msg = _run_git(["remote", "add", "origin", url.strip()],
                                         cwd=self._project_path)
            if success:
                self._remote_display.setText(url.strip())
                self._remote_status.setText("Remote updated.")
                self._remote_status.setStyleSheet("color: #43A047; font-size: 11px;")
            else:
                self._remote_status.setText(f"Error: {msg}")
                self._remote_status.setStyleSheet("color: #D9534F; font-size: 11px;")

    def _remove_remote(self):
        """Remove the origin remote."""
        ok, msg = _run_git(["remote", "remove", "origin"], cwd=self._project_path)
        if ok:
            self._remote_display.setText("")
            self._remote_status.setText("Remote removed.")
            self._remote_status.setStyleSheet("color: #43A047; font-size: 11px;")
        else:
            self._remote_status.setText(f"Error: {msg}")
            self._remote_status.setStyleSheet("color: #D9534F; font-size: 11px;")

    # ── Branch actions ──

    def _switch_branch(self):
        branch = self._branch_combo.currentText().strip()
        if not branch:
            return
        ok, msg = _run_git(["checkout", branch], cwd=self._project_path)
        if ok:
            self._branch_display.setText(branch)
            self._branch_status.setText(f"Switched to branch '{branch}'.")
            self._branch_status.setStyleSheet("color: #43A047; font-size: 11px;")
        else:
            self._branch_status.setText(f"Error: {msg}")
            self._branch_status.setStyleSheet("color: #D9534F; font-size: 11px;")

    def _create_branch(self):
        name = self._new_branch_input.text().strip()
        if not name:
            self._branch_status.setText("Please enter a branch name.")
            self._branch_status.setStyleSheet("color: #D9534F; font-size: 11px;")
            return
        ok, msg = _run_git(["checkout", "-b", name], cwd=self._project_path)
        if ok:
            self._branch_display.setText(name)
            self._new_branch_input.clear()
            self._load_branches()
            self._branch_status.setText(f"Created and switched to branch '{name}'.")
            self._branch_status.setStyleSheet("color: #43A047; font-size: 11px;")
        else:
            self._branch_status.setText(f"Error: {msg}")
            self._branch_status.setStyleSheet("color: #D9534F; font-size: 11px;")

    # ── Advanced ──

    def _view_history(self):
        dlg = GitHistoryDialog(self._project_path, parent=self)
        dlg.exec()

    def _open_terminal(self):
        """Open the system terminal at the project path."""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(
                    ["open", "-a", "Terminal", self._project_path],
                    start_new_session=True,
                )
            elif system == "Windows":
                subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", f"cd /d {self._project_path}"],
                    start_new_session=True,
                )
            else:
                # Linux: try common terminals
                for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
                    try:
                        subprocess.Popen(
                            [term, "--working-directory", self._project_path],
                            start_new_session=True,
                        )
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass  # Silently fail if no terminal can be opened

    # ── Save ──

    def _save_settings(self):
        """Save identity to local repo git config."""
        name = self._name_input.text().strip()
        email = self._email_input.text().strip()

        if name:
            _run_git(["config", "user.name", name], cwd=self._project_path)
        if email:
            _run_git(["config", "user.email", email], cwd=self._project_path)

        self.accept()

    def get_settings(self) -> dict:
        """Return the current settings values."""
        return {
            "name": self._name_input.text().strip(),
            "email": self._email_input.text().strip(),
            "auto_commit_enabled": self._auto_commit_cb.isChecked(),
            "auto_commit_frames": self._auto_commit_frames.value(),
            "commit_reminder": self._commit_reminder_cb.isChecked(),
        }


# ═══════════════════════════════════════════════════════════════════
# 6. GitHistoryDialog
# ═══════════════════════════════════════════════════════════════════

class GitHistoryDialog(QDialog):
    """Shows recent git commit history in a formatted list."""

    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self._project_path = project_path

        self.setWindowTitle("Commit History")
        self.setFixedSize(560, 420)
        self.setStyleSheet(DARK_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Commit History")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        # Branch info
        ok, branch = _run_git(["branch", "--show-current"], cwd=project_path)
        branch_text = branch if ok and branch else "(unknown)"
        branch_label = QLabel(f"Current branch: {branch_text}")
        branch_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(branch_label)

        layout.addWidget(_make_separator())

        # Commit list
        self._commit_list = QListWidget()
        self._commit_list.setAlternatingRowColors(False)
        layout.addWidget(self._commit_list, stretch=1)

        self._load_history()

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_history)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load_history(self):
        """Load git log and populate the list."""
        self._commit_list.clear()

        ok, output = _run_git(
            ["log", "--oneline", "--all", "-20",
             "--format=%h  %s  (%ar, %an)"],
            cwd=self._project_path,
        )

        if not ok:
            self._status_label.setText(f"Could not load history: {output}")
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")
            return

        if not output:
            self._status_label.setText("No commits yet.")
            self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")
            return

        lines = output.strip().split("\n")
        for line in lines:
            item = QListWidgetItem(line)
            # Color the commit hash part (first segment before space)
            item.setForeground(
                self._commit_list.palette().text().color()
            )
            self._commit_list.addItem(item)

        self._status_label.setText(f"Showing {len(lines)} most recent commits.")
        self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")


# ═══════════════════════════════════════════════════════════════════
# 7. GitNotFoundDialog
# ═══════════════════════════════════════════════════════════════════

class GitNotFoundDialog(QDialog):
    """Error dialog shown when Git is not installed on the system.

    Shows platform-specific installation instructions and offers
    a [Check Again] button to re-test.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git Not Found")
        self.setFixedSize(480, 400)
        self.setStyleSheet(DARK_STYLE)

        self._chose_different = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Error icon and title
        error_icon = QLabel("\u26A0\uFE0F")
        error_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_icon.setStyleSheet("font-size: 36px; background: transparent;")
        layout.addWidget(error_icon)

        title = QLabel("Git Not Found")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #D9534F;")
        layout.addWidget(title)

        desc = QLabel(
            "Git is required for the collaboration workflow but was not found "
            "on your system. Please install Git and try again."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(_make_separator())

        # Platform-specific instructions
        instructions = self._get_install_instructions()
        instructions_label = QLabel(instructions)
        instructions_label.setWordWrap(True)
        instructions_label.setStyleSheet(
            "color: #E8E8F0; font-size: 12px; background: #2A2A3C; "
            "border-radius: 6px; padding: 16px; line-height: 1.5;"
        )
        instructions_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(instructions_label)

        layout.addStretch()

        # Status label for check-again results
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()

        back_btn = QPushButton("\u2190 Choose Different Workflow")
        back_btn.clicked.connect(self._on_choose_different)
        btn_row.addWidget(back_btn)

        btn_row.addStretch()

        check_btn = QPushButton("Check Again")
        check_btn.setStyleSheet(ACCENT_BTN_STYLE)
        check_btn.clicked.connect(self._on_check_again)
        btn_row.addWidget(check_btn)

        layout.addLayout(btn_row)

    @staticmethod
    def _get_install_instructions() -> str:
        """Return platform-specific Git installation instructions."""
        system = platform.system()

        mac_instructions = (
            "macOS:\n"
            "  Option 1:  Open Terminal and run:\n"
            "    xcode-select --install\n\n"
            "  Option 2:  Install via Homebrew:\n"
            "    brew install git\n\n"
            "  Option 3:  Download from https://git-scm.com/download/mac"
        )

        windows_instructions = (
            "Windows:\n"
            "  Option 1:  Download the installer from:\n"
            "    https://git-scm.com/download/win\n\n"
            "  Option 2:  Install via winget:\n"
            "    winget install Git.Git\n\n"
            "  After installing, restart this application."
        )

        linux_instructions = (
            "Linux:\n"
            "  Debian/Ubuntu:   sudo apt install git\n"
            "  Fedora:          sudo dnf install git\n"
            "  Arch:            sudo pacman -S git\n"
            "  openSUSE:        sudo zypper install git"
        )

        if system == "Darwin":
            return mac_instructions
        elif system == "Windows":
            return windows_instructions
        elif system == "Linux":
            return linux_instructions
        else:
            return (
                f"{mac_instructions}\n\n"
                f"{windows_instructions}\n\n"
                f"{linux_instructions}"
            )

    def _on_check_again(self):
        """Re-check if git is now available."""
        if _is_git_installed():
            self._status_label.setText("Git found! You can proceed.")
            self._status_label.setStyleSheet("color: #43A047; font-size: 12px; font-weight: bold;")
            # Auto-close after a brief moment
            QTimer.singleShot(1000, self.accept)
        else:
            self._status_label.setText(
                "Git is still not found. Please install it and try again."
            )
            self._status_label.setStyleSheet("color: #D9534F; font-size: 11px;")

    def _on_choose_different(self):
        """Signal that the user wants to go back to workflow selection."""
        self._chose_different = True
        self.reject()

    def chose_different_workflow(self) -> bool:
        """Return True if the user clicked 'Choose Different Workflow'."""
        return self._chose_different
