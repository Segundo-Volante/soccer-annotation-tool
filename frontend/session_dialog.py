import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QButtonGroup, QRadioButton, QGroupBox, QGridLayout,
    QFrame,
)

from backend.i18n import I18n, t

# Language options with country flag emoji and native "Language" label
LANGUAGE_OPTIONS = [
    ("en", "\U0001F1EC\U0001F1E7  Language", "English"),
    ("es", "\U0001F1EA\U0001F1F8  Idioma", "Espa\u00f1ol"),
    ("it", "\U0001F1EE\U0001F1F9  Lingua", "Italiano"),
    ("de", "\U0001F1E9\U0001F1EA  Sprache", "Deutsch"),
    ("pt", "\U0001F1F5\U0001F1F9  Idioma", "Portugu\u00eas"),
    ("fr", "\U0001F1EB\U0001F1F7  Langue", "Fran\u00e7ais"),
]


class SessionDialog(QDialog):
    """Startup dialog: language selector, folder, roster CSV, session defaults."""

    def __init__(self, parent=None, project_config=None):
        super().__init__(parent)
        self.setWindowTitle(t("session.window_title"))
        self.setFixedWidth(560)
        self.setStyleSheet("""
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
        """)

        # Load metadata options
        opts_path = Path(__file__).parent.parent / "config" / "metadata_options.json"
        self._meta_opts = json.loads(opts_path.read_text(encoding="utf-8"))

        self._project_config = project_config
        self._folder_path = ""
        self._roster_path = ""
        self._result = {}
        self._selected_lang = I18n.lang()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        self._title_label = QLabel(t("main.window_title"))
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        layout.addWidget(self._title_label)

        # ── Language selector row ──
        lang_row = QHBoxLayout()
        lang_row.setSpacing(6)

        # Build the label from all languages' word for "Language"
        lang_header_parts = []
        for code, native_word, _name in LANGUAGE_OPTIONS:
            # Extract just the flag + word (e.g. "🇬🇧 Language")
            lang_header_parts.append(native_word)
        lang_header = QLabel("  /  ".join(lang_header_parts))
        lang_header.setStyleSheet(
            "color: #8888A0; font-size: 10px; font-weight: bold;"
        )
        lang_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lang_header)

        # Language buttons row
        lang_btn_row = QHBoxLayout()
        lang_btn_row.setSpacing(4)
        lang_btn_row.addStretch()
        self._lang_buttons: list[QPushButton] = []
        for code, native_word, display_name in LANGUAGE_OPTIONS:
            # Extract just the flag emoji (first 4 chars)
            flag = native_word.split("  ")[0]
            btn = QPushButton(f"{flag} {display_name}")
            btn.setProperty("lang_code", code)
            btn.setFixedHeight(30)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _checked, c=code: self._on_language_changed(c))
            self._lang_buttons.append(btn)
            lang_btn_row.addWidget(btn)
        lang_btn_row.addStretch()
        layout.addLayout(lang_btn_row)
        self._update_lang_buttons()

        # Separator after language
        lang_sep = QFrame()
        lang_sep.setFrameShape(QFrame.Shape.HLine)
        lang_sep.setStyleSheet("color: #404060;")
        layout.addWidget(lang_sep)

        # Folder row
        self._folder_label = QLabel(t("session.folder_label"))
        self._folder_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._folder_label)
        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText(t("session.folder_placeholder"))
        self._folder_input.setReadOnly(True)
        folder_row.addWidget(self._folder_input, stretch=1)
        self._browse_folder_btn = QPushButton(t("button.browse"))
        self._browse_folder_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._browse_folder_btn)
        layout.addLayout(folder_row)

        # Roster CSV row
        self._roster_label = QLabel(t("session.roster_label"))
        self._roster_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._roster_label)
        roster_row = QHBoxLayout()
        self._roster_input = QLineEdit()
        self._roster_input.setPlaceholderText(t("session.roster_placeholder"))
        self._roster_input.setReadOnly(True)
        roster_row.addWidget(self._roster_input, stretch=1)
        self._browse_roster_btn = QPushButton(t("button.browse"))
        self._browse_roster_btn.clicked.connect(self._browse_roster)
        roster_row.addWidget(self._browse_roster_btn)
        layout.addLayout(roster_row)

        # Roster info label (shows team + season after selecting CSV)
        self._roster_info = QLabel("")
        self._roster_info.setStyleSheet("color: #4A90D9; font-size: 11px;")
        layout.addWidget(self._roster_info)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #404060;")
        layout.addWidget(sep1)

        # Source / Round / Opponent row
        grid = QGridLayout()
        grid.setSpacing(8)
        self._source_label = QLabel(t("session.source_label"))
        grid.addWidget(self._source_label, 0, 0)
        self._source_combo = QComboBox()
        self._source_combo.setEditable(True)
        self._source_combo.lineEdit().setPlaceholderText(t("session.source_placeholder"))
        # Load competitions from project config, fallback to defaults
        if self._project_config and self._project_config.exists:
            competitions = self._project_config.get_competitions()
        else:
            competitions = [
                "LaLiga", "LaLiga2", "CopadelRey", "Supercopa",
                "EPL", "EFL_Championship", "FA_Cup", "EFL_Cup",
                "Ligue1", "Ligue2", "CoupeDeFrance", "TropheeDesChampions",
                "SerieA", "SerieB", "CoppaItalia", "SupercoppaItaliana",
                "Bundesliga", "Bundesliga2", "DFB_Pokal", "DFL_Supercup",
                "LigaPortugal", "LigaPortugal2", "TacaDePortugal", "Supertaca",
                "Eredivisie", "EersteDivisie", "KNVB_Beker", "JohanCruyffSchaal",
                "UCL", "UEL", "UECL", "Friendly",
            ]
        self._source_combo.addItems(competitions)
        grid.addWidget(self._source_combo, 0, 1)

        self._round_label = QLabel(t("session.round_label"))
        grid.addWidget(self._round_label, 0, 2)
        self._round_input = QLineEdit()
        self._round_input.setPlaceholderText(t("session.round_placeholder"))
        grid.addWidget(self._round_input, 0, 3)

        self._opponent_label = QLabel(t("session.opponent_label"))
        grid.addWidget(self._opponent_label, 1, 0)
        self._opponent_combo = QComboBox()
        self._opponent_combo.setEditable(True)
        self._opponent_combo.lineEdit().setPlaceholderText(t("session.opponent_placeholder"))
        # Populate with known opponents from CSV files
        if self._project_config and self._project_config.exists:
            opponent_names = self._project_config.get_opponent_names()
            if opponent_names:
                self._opponent_combo.addItems(opponent_names)
        grid.addWidget(self._opponent_combo, 1, 1, 1, 3)
        layout.addLayout(grid)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #404060;")
        layout.addWidget(sep2)

        self._defaults_label = QLabel(t("session.defaults_label"))
        self._defaults_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._defaults_label)

        # Build session-level radio groups dynamically from config array
        self._session_groups: dict[str, QButtonGroup] = {}
        self._session_boxes: list[QGroupBox] = []
        for dim in self._meta_opts.get("session_level", []):
            key = dim["key"]
            label = t(f"meta.label.{key}")
            options = dim.get("options", [])
            group = QButtonGroup(self)
            box = QGroupBox(label)
            box.setProperty("meta_key", key)
            box_layout = QHBoxLayout(box)
            for i, opt in enumerate(options):
                rb = QRadioButton(t(f"meta.opt.{opt}"))
                rb.setProperty("value", opt)
                group.addButton(rb, i)
                box_layout.addWidget(rb)
                if i == 0:
                    rb.setChecked(True)
            self._session_groups[key] = group
            self._session_boxes.append(box)
            layout.addWidget(box)

        # Set better defaults for known keys
        if "lighting" in self._session_groups:
            for btn in self._session_groups["lighting"].buttons():
                if btn.property("value") == "floodlight":
                    btn.setChecked(True)
                    break

        # Start button
        layout.addSpacing(8)
        self._start_btn = QPushButton(t("button.start_annotating"))
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: #F5A623; color: #1E1E2E; font-size: 14px;
                font-weight: bold; padding: 12px; border-radius: 6px;
            }
            QPushButton:hover { background: #FFB833; }
            QPushButton:disabled { background: #404060; color: #666; }
        """)
        self._start_btn.clicked.connect(self._on_start)
        layout.addWidget(self._start_btn)

        # Pre-fill roster from project config or fallback to default
        default_roster = None
        if self._project_config and self._project_config.exists:
            default_roster = self._project_config.get_home_roster_path()
        if not default_roster:
            fallback = Path(__file__).parent.parent / "rosters" / "atletico_madrid_2024-25.csv"
            if fallback.exists():
                default_roster = fallback
        if default_roster:
            self._roster_path = str(default_roster)
            self._roster_input.setText(str(default_roster))
            self._preview_roster(default_roster)

    # ── Language switching ──

    def _update_lang_buttons(self):
        """Highlight the active language button."""
        for btn in self._lang_buttons:
            code = btn.property("lang_code")
            if code == self._selected_lang:
                btn.setStyleSheet(
                    "QPushButton { background: #F5A623; color: #1E1E2E; "
                    "font-weight: bold; font-size: 11px; border-radius: 4px; "
                    "padding: 4px 10px; border: none; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #333348; color: #AAAACC; "
                    "font-size: 11px; border-radius: 4px; "
                    "padding: 4px 10px; border: 1px solid #555570; }"
                    "QPushButton:hover { background: #3A3A50; }"
                )

    def _on_language_changed(self, lang_code: str):
        """Reload i18n and update all translatable labels."""
        if lang_code == self._selected_lang:
            return
        self._selected_lang = lang_code
        config_dir = Path(__file__).parent.parent / "config"
        I18n.load(lang_code, config_dir)

        # Update all translatable text in the dialog
        self.setWindowTitle(t("session.window_title"))
        self._title_label.setText(t("main.window_title"))
        self._folder_label.setText(t("session.folder_label"))
        self._folder_input.setPlaceholderText(t("session.folder_placeholder"))
        self._browse_folder_btn.setText(t("button.browse"))
        self._roster_label.setText(t("session.roster_label"))
        self._roster_input.setPlaceholderText(t("session.roster_placeholder"))
        self._browse_roster_btn.setText(t("button.browse"))
        self._source_label.setText(t("session.source_label"))
        self._source_combo.lineEdit().setPlaceholderText(t("session.source_placeholder"))
        self._round_label.setText(t("session.round_label"))
        self._round_input.setPlaceholderText(t("session.round_placeholder"))
        self._opponent_label.setText(t("session.opponent_label"))
        self._opponent_combo.lineEdit().setPlaceholderText(t("session.opponent_placeholder"))
        self._defaults_label.setText(t("session.defaults_label"))
        self._start_btn.setText(t("button.start_annotating"))

        # Update session-level radio group labels and option text
        for box in self._session_boxes:
            key = box.property("meta_key")
            box.setTitle(t(f"meta.label.{key}"))
        for key, group in self._session_groups.items():
            for btn in group.buttons():
                opt_val = btn.property("value")
                btn.setText(t(f"meta.opt.{opt_val}"))

        self._update_lang_buttons()

        # Save language preference to project config
        if self._project_config and self._project_config.exists:
            self._project_config.set_language(lang_code)

    # ── File browsing ──

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, t("dialog.select_folder"))
        if folder:
            self._folder_path = folder
            self._folder_input.setText(folder)

    def _browse_roster(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("dialog.select_roster"),
            str(Path(__file__).parent.parent / "rosters"),
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self._roster_path = path
            self._roster_input.setText(path)
            self._preview_roster(Path(path))

    def _preview_roster(self, path: Path):
        """Read first row of CSV to show team + season info."""
        import csv
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if row:
                    team = row.get("team", "?")
                    season = row.get("season", "?")
                    # Count players
                    count = 1
                    for _ in reader:
                        count += 1
                    self._roster_info.setText(t("session.roster_preview",
                                                team=team, season=season, count=count))
                else:
                    self._roster_info.setText(t("session.roster_empty"))
        except Exception:
            self._roster_info.setText(t("session.roster_error"))

    def _on_start(self):
        if not self._folder_path or not self._round_input.text().strip():
            return
        self._result = {
            "folder": self._folder_path,
            "roster": self._roster_path,
            "source": self._source_combo.currentText(),
            "round": self._round_input.text().strip(),
            "opponent": self._opponent_combo.currentText().strip(),
            "language": self._selected_lang,
        }
        # Collect session-level values from dynamic radio groups
        defaults = {"weather": "clear", "lighting": "floodlight"}
        for key, group in self._session_groups.items():
            btn = group.checkedButton()
            self._result[key] = btn.property("value") if btn else defaults.get(key, "")
        self.accept()

    def get_result(self) -> dict:
        return self._result
