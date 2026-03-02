import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QButtonGroup, QRadioButton, QGroupBox, QGridLayout,
    QFrame,
)

from backend.i18n import t


class SessionDialog(QDialog):
    """Startup dialog: folder, roster CSV, session defaults (weather, lighting)."""

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

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel(t("main.window_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        # Folder row
        folder_label = QLabel(t("session.folder_label"))
        folder_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(folder_label)
        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText(t("session.folder_placeholder"))
        self._folder_input.setReadOnly(True)
        folder_row.addWidget(self._folder_input, stretch=1)
        browse_btn = QPushButton(t("button.browse"))
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Roster CSV row
        roster_label = QLabel(t("session.roster_label"))
        roster_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(roster_label)
        roster_row = QHBoxLayout()
        self._roster_input = QLineEdit()
        self._roster_input.setPlaceholderText(t("session.roster_placeholder"))
        self._roster_input.setReadOnly(True)
        roster_row.addWidget(self._roster_input, stretch=1)
        roster_btn = QPushButton(t("button.browse"))
        roster_btn.clicked.connect(self._browse_roster)
        roster_row.addWidget(roster_btn)
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
        grid.addWidget(QLabel(t("session.source_label")), 0, 0)
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

        grid.addWidget(QLabel(t("session.round_label")), 0, 2)
        self._round_input = QLineEdit()
        self._round_input.setPlaceholderText(t("session.round_placeholder"))
        grid.addWidget(self._round_input, 0, 3)

        grid.addWidget(QLabel(t("session.opponent_label")), 1, 0)
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

        session_label = QLabel(t("session.defaults_label"))
        session_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(session_label)

        # Build session-level radio groups dynamically from config array
        self._session_groups: dict[str, QButtonGroup] = {}
        for dim in self._meta_opts.get("session_level", []):
            key = dim["key"]
            label = dim.get("label", key.replace("_", " ").title())
            options = dim.get("options", [])
            group = QButtonGroup(self)
            box = QGroupBox(label)
            box_layout = QHBoxLayout(box)
            for i, opt in enumerate(options):
                rb = QRadioButton(opt.replace("_", " ").title())
                rb.setProperty("value", opt)
                group.addButton(rb, i)
                box_layout.addWidget(rb)
                if i == 0:
                    rb.setChecked(True)
            self._session_groups[key] = group
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
        }
        # Collect session-level values from dynamic radio groups
        defaults = {"weather": "clear", "lighting": "floodlight"}
        for key, group in self._session_groups.items():
            btn = group.checkedButton()
            self._result[key] = btn.property("value") if btn else defaults.get(key, "")
        self.accept()

    def get_result(self) -> dict:
        return self._result
