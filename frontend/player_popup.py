from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

from backend.i18n import t
from backend.roster_manager import RosterManager


class PlayerPopup(QDialog):
    def __init__(self, roster: RosterManager, parent=None, pos=None):
        super().__init__(parent)
        self.setWindowTitle(t("popup.player_id_title"))
        self.setFixedSize(280, 140)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog { background: #2A2A2A; border: 2px solid #4A90D9; border-radius: 6px; }
            QLabel { color: #EEE; font-size: 12px; }
            QLineEdit {
                background: #444; color: white; border: 1px solid #666;
                border-radius: 3px; padding: 4px; font-size: 14px;
            }
            QPushButton {
                padding: 6px 16px; border-radius: 3px; font-weight: bold;
            }
        """)

        if pos:
            self.move(pos)

        self._roster = roster
        self._jersey_number = None
        self._player_name = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Jersey number row
        num_row = QHBoxLayout()
        num_row.addWidget(QLabel(t("popup.jersey_number_label")))
        self._num_input = QLineEdit()
        self._num_input.setMaxLength(3)
        self._num_input.setFixedWidth(60)
        self._num_input.textChanged.connect(self._on_number_changed)
        num_row.addWidget(self._num_input)
        num_row.addStretch()
        layout.addLayout(num_row)

        # Player name row
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(t("popup.player_label")))
        self._name_label = QLabel("—")
        self._name_label.setStyleSheet("color: #4A90D9; font-weight: bold;")
        self._name_input = QLineEdit()
        self._name_input.setVisible(False)
        self._name_input.setPlaceholderText(t("popup.player_name_placeholder"))
        name_row.addWidget(self._name_label)
        name_row.addWidget(self._name_input)
        name_row.addStretch()
        layout.addLayout(name_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        confirm_btn = QPushButton(t("button.confirm"))
        confirm_btn.setStyleSheet("background: #27AE60; color: white;")
        confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton(t("button.cancel"))
        cancel_btn.setStyleSheet("background: #C0392B; color: white;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._num_input.setFocus()

    def _on_number_changed(self, text: str):
        if not text.isdigit():
            return
        num = int(text)
        player = self._roster.lookup_by_number(num)
        if player:
            self._name_label.setText(player.name)
            self._name_label.setVisible(True)
            self._name_input.setVisible(False)
        else:
            self._name_label.setText("")
            self._name_label.setVisible(False)
            self._name_input.setVisible(True)
            self._name_input.setFocus()

    def _confirm(self):
        text = self._num_input.text().strip()
        if not text.isdigit():
            return
        self._jersey_number = int(text)
        player = self._roster.lookup_by_number(self._jersey_number)
        if player:
            self._player_name = player.name
        else:
            self._player_name = self._name_input.text().strip() or f"Player {self._jersey_number}"
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._confirm()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def get_result(self):
        return self._jersey_number, self._player_name
