from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)


class UnsurePopup(QDialog):
    """Popup for entering/editing an unsure note on a bounding box."""

    def __init__(self, existing_note: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unsure Note")
        self.setFixedSize(320, 120)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog { background: #2A2A2A; border: 2px solid #FF6B35; border-radius: 6px; }
            QLabel { color: #EEE; font-size: 12px; }
            QLineEdit {
                background: #444; color: white; border: 1px solid #666;
                border-radius: 3px; padding: 4px; font-size: 13px;
            }
            QPushButton {
                padding: 6px 16px; border-radius: 3px; font-weight: bold;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Title
        title = QLabel("Mark as Unsure")
        title.setStyleSheet("color: #FF6B35; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # Note input
        self._note_input = QLineEdit()
        self._note_input.setText(existing_note)
        self._note_input.setPlaceholderText("Optional note (e.g., blocked by defender)")
        layout.addWidget(self._note_input)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("background: #FF6B35; color: white;")
        ok_btn.clicked.connect(self.accept)
        skip_btn = QPushButton("Skip")
        skip_btn.setStyleSheet("background: #555; color: #CCC;")
        skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        self._note_input.setFocus()
        self._skipped = False

    def _skip(self):
        self._skipped = True
        self.accept()

    def get_note(self) -> str:
        if self._skipped:
            return ""
        return self._note_input.text().strip()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
