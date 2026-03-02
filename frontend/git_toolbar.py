"""Git toolbar widget for the main annotation window.

Displays commit/push/pull buttons, branch indicator, and remote status.
Only visible when Git workflow is active.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QDialog,
    QVBoxLayout, QTextEdit, QLineEdit, QMessageBox,
)

logger = logging.getLogger(__name__)

TOOLBAR_STYLE = """
    QWidget#git_toolbar {
        background: #1A1A2A;
        border-bottom: 1px solid #333350;
    }
    QPushButton {
        background: #2A2A3C;
        color: #E8E8F0;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
        border: 1px solid #404060;
    }
    QPushButton:hover {
        background: #3A3A50;
        border-color: #F5A623;
    }
    QPushButton:disabled {
        background: #222230;
        color: #666680;
        border-color: #333350;
    }
    QLabel {
        color: #E8E8F0;
        font-size: 12px;
    }
"""


class GitCommitDialog(QDialog):
    """Inline popup for committing annotations."""

    def __init__(self, uncommitted_count: int, auto_message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Commit Annotations")
        self.setFixedWidth(420)
        self.setStyleSheet("""
            QDialog { background: #1E1E2E; }
            QLabel { color: #E8E8F0; font-size: 12px; }
            QLineEdit {
                background: #2A2A3C; color: #E8E8F0; border: 1px solid #404060;
                border-radius: 4px; padding: 8px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #F5A623; }
            QPushButton {
                background: #404060; color: #E8E8F0; padding: 8px 16px;
                border-radius: 4px; font-size: 12px; border: none;
            }
            QPushButton:hover { background: #505070; }
            QPushButton#commit_btn {
                background: #F5A623; color: #1E1E2E; font-weight: bold;
            }
            QPushButton#commit_btn:hover { background: #FFB833; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"Commit {uncommitted_count} annotation{'s' if uncommitted_count != 1 else ''}")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Message:"))
        self._message = QLineEdit(auto_message)
        layout.addWidget(self._message)

        hint = QLabel("(auto-generated, edit if you want)")
        hint.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        commit = QPushButton("Commit ✓")
        commit.setObjectName("commit_btn")
        commit.clicked.connect(self.accept)
        btn_row.addWidget(commit)
        layout.addLayout(btn_row)

    def get_message(self) -> str:
        return self._message.text().strip()


class GitToolbar(QWidget):
    """Git toolbar with Commit/Push/Pull buttons and branch indicator."""

    # Emitted when a toast message should be shown
    toast_message = pyqtSignal(str, str, int)  # message, type, duration_ms

    def __init__(self, project_root: str, annotator: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("git_toolbar")
        self._project_root = Path(project_root)
        self._annotator = annotator
        self._uncommitted = 0
        self._branch = "main"
        self._new_from_remote = 0

        self.setStyleSheet(TOOLBAR_STYLE)
        self._build_ui()

        # Background check for remote changes every 60 seconds
        self._remote_timer = QTimer(self)
        self._remote_timer.timeout.connect(self._check_remote)
        self._remote_timer.start(60_000)

        # Initial status refresh
        QTimer.singleShot(500, self.refresh_status)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Commit button with badge
        self._commit_btn = QPushButton("Commit")
        self._commit_btn.clicked.connect(self._on_commit)
        layout.addWidget(self._commit_btn)

        # Push button
        self._push_btn = QPushButton("Push ↑")
        self._push_btn.clicked.connect(self._on_push)
        layout.addWidget(self._push_btn)

        # Pull button
        self._pull_btn = QPushButton("Pull ↓")
        self._pull_btn.clicked.connect(self._on_pull)
        layout.addWidget(self._pull_btn)

        # Separator
        sep = QLabel("│")
        sep.setStyleSheet("color: #404060; font-size: 14px;")
        layout.addWidget(sep)

        # Branch indicator
        self._branch_label = QLabel("main")
        self._branch_label.setStyleSheet("color: #A0A0C0; font-size: 12px;")
        layout.addWidget(self._branch_label)

        # Remote status indicator
        self._remote_label = QLabel("")
        self._remote_label.setStyleSheet("color: #F5A623; font-size: 12px; font-weight: bold;")
        self._remote_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remote_label.mousePressEvent = lambda _: self._on_pull()
        layout.addWidget(self._remote_label)

        layout.addStretch()

        # Quick sync shortcut hint
        hint = QLabel("Ctrl+Shift+S: Quick Sync")
        hint.setStyleSheet("color: #666680; font-size: 11px;")
        layout.addWidget(hint)

    def set_annotator(self, name: str):
        self._annotator = name

    def refresh_status(self):
        """Refresh git status (branch, uncommitted count)."""
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                self._branch = result.stdout.strip() or "HEAD"
                self._branch_label.setText(self._branch)

            # Count uncommitted annotation changes
            result = subprocess.run(
                ["git", "status", "--porcelain", "annotations/"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                self._uncommitted = len(lines)
            else:
                self._uncommitted = 0

            self._update_commit_button()

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("Git status check failed: %s", e)

    def _update_commit_button(self):
        if self._uncommitted > 0:
            self._commit_btn.setText(f"Commit ({self._uncommitted})")
            self._commit_btn.setEnabled(True)
        else:
            self._commit_btn.setText("Commit")
            self._commit_btn.setEnabled(False)

    def _check_remote(self):
        """Background check for new remote commits."""
        try:
            # Fetch without merging
            subprocess.run(
                ["git", "fetch", "--quiet"],
                cwd=str(self._project_root),
                capture_output=True, timeout=15,
            )
            # Count new commits from remote
            result = subprocess.run(
                ["git", "rev-list", f"HEAD..origin/{self._branch}", "--count"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                count = int(result.stdout.strip())
                self._new_from_remote = count
                if count > 0:
                    self._remote_label.setText(f"↓{count} new from team")
                else:
                    self._remote_label.setText("")
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, OSError):
            pass  # Silently fail — network might be unavailable

    def _on_commit(self):
        """Open commit dialog and commit annotations."""
        if self._uncommitted == 0:
            return

        # Generate auto-message
        auto_msg = self._generate_commit_message()

        dialog = GitCommitDialog(self._uncommitted, auto_msg, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            message = dialog.get_message() or auto_msg
            self._do_commit(message)

    def _generate_commit_message(self) -> str:
        """Generate an auto commit message from staged annotation files."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "annotations/"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return f"{self._annotator}: annotated frames"

            files = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    # Extract filename from status line
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        fname = parts[-1].replace("annotations/", "").replace(".json", "")
                        files.append(fname)

            if files:
                files.sort()
                first = files[0]
                last = files[-1]
                name = self._annotator or "annotator"
                return f"{name}: annotated frames {first}-{last} ({len(files)} frames)"
            return f"{self._annotator}: annotated frames"
        except Exception:
            return f"{self._annotator}: annotated frames"

    def _do_commit(self, message: str):
        """Run git add + commit."""
        try:
            # Stage annotation changes
            result = subprocess.run(
                ["git", "add", "annotations/"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                self.toast_message.emit(f"Git add failed: {result.stderr}", "warning", 4000)
                return

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self.toast_message.emit(
                    f"Committed {self._uncommitted} annotations", "success", 3000
                )
                self._uncommitted = 0
                self._update_commit_button()
            else:
                self.toast_message.emit(f"Commit failed: {result.stderr}", "warning", 4000)

        except subprocess.TimeoutExpired:
            self.toast_message.emit("Commit timed out", "warning", 3000)
        except FileNotFoundError:
            self.toast_message.emit("Git not found", "warning", 3000)

    def _on_push(self):
        """Push to remote."""
        # Check for uncommitted changes first
        if self._uncommitted > 0:
            reply = QMessageBox.question(
                self,
                "Uncommitted Changes",
                f"You have {self._uncommitted} uncommitted changes.\n"
                "Commit first before pushing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                auto_msg = self._generate_commit_message()
                self._do_commit(auto_msg)
            else:
                return

        self._push_btn.setEnabled(False)
        self._push_btn.setText("Pushing...")

        try:
            result = subprocess.run(
                ["git", "push", "origin", self._branch],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                self.toast_message.emit("Pushed to origin", "success", 3000)
            else:
                stderr = result.stderr.strip()
                if "rejected" in stderr.lower():
                    reply = QMessageBox.question(
                        self,
                        "Push Rejected",
                        "Push rejected — remote has new changes.\n"
                        "Pull first, then push again?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self._on_pull()
                        # Auto-retry push after pull
                        QTimer.singleShot(1000, self._on_push)
                elif "authentication" in stderr.lower() or "denied" in stderr.lower():
                    QMessageBox.warning(
                        self, "Authentication Failed",
                        "Git push authentication failed.\n"
                        "Check your credentials or SSH key setup."
                    )
                elif "no remote" in stderr.lower() or "No configured push destination" in stderr:
                    QMessageBox.warning(
                        self, "No Remote",
                        "No remote repository configured.\n"
                        "Go to Project → Git Settings to add a remote."
                    )
                else:
                    self.toast_message.emit(f"Push failed: {stderr[:100]}", "warning", 4000)

        except subprocess.TimeoutExpired:
            self.toast_message.emit("Push timed out", "warning", 3000)
        except FileNotFoundError:
            self.toast_message.emit("Git not found", "warning", 3000)
        finally:
            self._push_btn.setEnabled(True)
            self._push_btn.setText("Push ↑")

    def _on_pull(self):
        """Pull from remote."""
        # Check for uncommitted changes
        if self._uncommitted > 0:
            reply = QMessageBox.question(
                self,
                "Uncommitted Changes",
                f"You have {self._uncommitted} uncommitted changes.\n"
                "Commit first before pulling?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                auto_msg = self._generate_commit_message()
                self._do_commit(auto_msg)
            else:
                return

        self._pull_btn.setEnabled(False)
        self._pull_btn.setText("Pulling...")

        try:
            result = subprocess.run(
                ["git", "pull", "origin", self._branch],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Already up to date" in output:
                    self.toast_message.emit("Already up to date", "info", 2000)
                else:
                    # Count how many annotation files changed
                    self.toast_message.emit(
                        "Pulled new annotations from teammates", "success", 3000
                    )
                self._new_from_remote = 0
                self._remote_label.setText("")
            else:
                stderr = result.stderr.strip()
                if "CONFLICT" in stderr or "conflict" in result.stdout:
                    self._handle_merge_conflict()
                else:
                    self.toast_message.emit(f"Pull failed: {stderr[:100]}", "warning", 4000)

        except subprocess.TimeoutExpired:
            self.toast_message.emit("Pull timed out", "warning", 3000)
        except FileNotFoundError:
            self.toast_message.emit("Git not found", "warning", 3000)
        finally:
            self._pull_btn.setEnabled(True)
            self._pull_btn.setText("Pull ↓")
            self.refresh_status()

    def _handle_merge_conflict(self):
        """Handle git merge conflicts in annotation files."""
        try:
            # Find conflicting files
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=5,
            )
            conflicts = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]

            if not conflicts:
                return

            for conflict_file in conflicts:
                reply = QMessageBox.question(
                    self,
                    "⚠️ Merge Conflict",
                    f"Conflict in: {conflict_file}\n\n"
                    "This means two people annotated the same frame.\n\n"
                    "Keep your version or the remote version?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # Keep ours
                    subprocess.run(
                        ["git", "checkout", "--ours", conflict_file],
                        cwd=str(self._project_root), capture_output=True, timeout=5,
                    )
                else:
                    # Keep theirs
                    subprocess.run(
                        ["git", "checkout", "--theirs", conflict_file],
                        cwd=str(self._project_root), capture_output=True, timeout=5,
                    )
                subprocess.run(
                    ["git", "add", conflict_file],
                    cwd=str(self._project_root), capture_output=True, timeout=5,
                )

            # Complete the merge
            subprocess.run(
                ["git", "commit", "-m", "Resolved merge conflicts in annotations"],
                cwd=str(self._project_root), capture_output=True, timeout=10,
            )
            self.toast_message.emit("Merge conflicts resolved", "success", 3000)

        except Exception as e:
            logger.error("Merge conflict resolution failed: %s", e)
            self.toast_message.emit("Conflict resolution failed", "warning", 4000)

    def quick_sync(self):
        """Ctrl+Shift+S: commit (auto-message) + push in one action."""
        if self._uncommitted > 0:
            auto_msg = self._generate_commit_message()
            self._do_commit(auto_msg)

        # Push (even if commit had nothing new)
        try:
            result = subprocess.run(
                ["git", "push", "origin", self._branch],
                cwd=str(self._project_root),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                self.toast_message.emit("Committed & pushed annotations", "success", 3000)
            else:
                self.toast_message.emit(
                    "Committed annotations (push failed — try again later)", "warning", 4000
                )
        except Exception:
            self.toast_message.emit(
                "Committed annotations (push failed — try again later)", "warning", 4000
            )

    def stop_timers(self):
        """Stop background timers (call on close)."""
        self._remote_timer.stop()
