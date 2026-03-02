import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from backend.i18n import t


class MetadataBar(QWidget):
    """Tab+Number metadata bar with 6 dimensions.

    Row 1: dimension pills (SHOT, CAMERA, BALL, SITUATION, ZONE, QUALITY)
    Row 2: numbered options for the active dimension
    Row 3: keyboard hint line
    """

    metadata_changed = pyqtSignal(str, str)       # key, value
    auto_skip_triggered = pyqtSignal(str, str)     # key, value that triggers skip

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(90)
        self.setStyleSheet("background: #2A2A3C;")

        # Load config
        opts_path = Path(__file__).parent.parent / "config" / "metadata_options.json"
        self._config = json.loads(opts_path.read_text(encoding="utf-8"))
        self._dimensions = self._config["frame_level"]

        # State
        self._active_dim = 0
        self._values: dict[str, str] = {}
        for dim in self._dimensions:
            self._values[dim["key"]] = dim["default"]

        # Build UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Row 1: dimension pills
        pill_row = QHBoxLayout()
        pill_row.setSpacing(4)
        self._pills: list[QPushButton] = []
        for i, dim in enumerate(self._dimensions):
            pill = QPushButton(f"{dim['label']}: {dim['default']}")
            pill.setCheckable(False)
            pill.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            pill.setFixedHeight(24)
            pill.clicked.connect(lambda _checked, idx=i: self._set_active(idx))
            self._pills.append(pill)
            pill_row.addWidget(pill)
        pill_row.addStretch()
        layout.addLayout(pill_row)

        # Row 2: options container
        self._options_container = QWidget()
        self._options_layout = QHBoxLayout(self._options_container)
        self._options_layout.setContentsMargins(0, 0, 0, 0)
        self._options_layout.setSpacing(4)
        layout.addWidget(self._options_container)

        # Row 3: keyboard hint
        self._hint = QLabel(t("metadata.keyboard_hint"))
        self._hint.setStyleSheet("color: #666680; font-size: 10px;")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint)

        self._update_pills()
        self._update_options()

    # ── Public API ──

    def cycle_dim(self, forward: bool = True):
        """Called by Tab / Shift+Tab."""
        if forward:
            self._active_dim = (self._active_dim + 1) % len(self._dimensions)
        else:
            self._active_dim = (self._active_dim - 1) % len(self._dimensions)
        self._update_pills()
        self._update_options()

    def select_option(self, number: int):
        """Select option by number (1-based). Called by number key press."""
        dim = self._dimensions[self._active_dim]
        options = dim["options"]
        idx = number - 1
        if 0 <= idx < len(options):
            value = options[idx]
            self._values[dim["key"]] = value
            self._update_pills()
            self._update_options()
            self.metadata_changed.emit(dim["key"], value)
            # Check auto-skip
            if value in dim.get("auto_skip", []):
                self.auto_skip_triggered.emit(dim["key"], value)

    def set_metadata(self, **kwargs):
        """Set all dimension values at once (when loading a frame)."""
        for key, value in kwargs.items():
            if value is not None and key in self._values:
                self._values[key] = value
        self._update_pills()
        self._update_options()

    def get_metadata(self) -> dict:
        """Return dict of all 6 dimension key→value pairs."""
        return dict(self._values)

    # ── Internal ──

    def _set_active(self, index: int):
        self._active_dim = index % len(self._dimensions)
        self._update_pills()
        self._update_options()

    def _update_pills(self):
        for i, (pill, dim) in enumerate(zip(self._pills, self._dimensions)):
            key = dim["key"]
            val = self._values.get(key, dim["default"])
            display_val = val.replace("_", " ")
            pill.setText(f"{dim['label']}: {display_val}")
            if i == self._active_dim:
                pill.setStyleSheet(
                    "QPushButton {"
                    "  background: #3A3A50; color: #F5A623; font-size: 11px;"
                    "  font-weight: bold; border: 2px solid #F5A623;"
                    "  border-radius: 4px; padding: 2px 8px;"
                    "}"
                )
            else:
                pill.setStyleSheet(
                    "QPushButton {"
                    "  background: #333348; color: #AAAACC; font-size: 11px;"
                    "  border: 1px solid #555570; border-radius: 4px;"
                    "  padding: 2px 8px;"
                    "}"
                    "QPushButton:hover { background: #3A3A50; }"
                )

    def _update_options(self):
        # Clear existing
        while self._options_layout.count():
            item = self._options_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        dim = self._dimensions[self._active_dim]
        current_val = self._values.get(dim["key"], dim["default"])

        for i, opt in enumerate(dim["options"]):
            num = i + 1
            display = opt.replace("_", " ")
            is_selected = (opt == current_val)
            is_skip = opt in dim.get("auto_skip", [])

            text = f"[{num}] {display}" if is_selected else f" {num}  {display}"
            lbl = QLabel(text)

            if is_selected:
                lbl.setStyleSheet(
                    "color: #F5A623; font-weight: bold; font-size: 11px; "
                    "background: #3A3A50; border-radius: 3px; padding: 2px 6px;"
                )
            elif is_skip:
                lbl.setStyleSheet(
                    "color: #D94A4A; font-size: 11px; padding: 2px 6px;"
                )
            else:
                lbl.setStyleSheet(
                    "color: #CCCCDD; font-size: 11px; padding: 2px 6px;"
                )

            self._options_layout.addWidget(lbl)

        self._options_layout.addStretch()
