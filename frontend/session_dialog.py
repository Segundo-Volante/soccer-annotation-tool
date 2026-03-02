import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QButtonGroup, QRadioButton, QGroupBox, QGridLayout,
    QFrame,
)


class SessionDialog(QDialog):
    """Startup dialog: folder, roster CSV, session defaults (weather, lighting)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Soccer Annotation Tool")
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

        self._folder_path = ""
        self._roster_path = ""
        self._result = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("Soccer Annotation Tool")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        # Folder row
        folder_label = QLabel("Screenshot Folder")
        folder_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(folder_label)
        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("Select screenshot folder...")
        self._folder_input.setReadOnly(True)
        folder_row.addWidget(self._folder_input, stretch=1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Roster CSV row
        roster_label = QLabel("Team Roster CSV")
        roster_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(roster_label)
        roster_row = QHBoxLayout()
        self._roster_input = QLineEdit()
        self._roster_input.setPlaceholderText("Select roster CSV file...")
        self._roster_input.setReadOnly(True)
        roster_row.addWidget(self._roster_input, stretch=1)
        roster_btn = QPushButton("Browse...")
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
        grid.addWidget(QLabel("Source"), 0, 0)
        self._source_combo = QComboBox()
        self._source_combo.setEditable(True)
        self._source_combo.lineEdit().setPlaceholderText("Select or type...")
        self._source_combo.addItems([
            # --- Spain ---
            "LaLiga", "LaLiga2", "CopadelRey", "Supercopa",
            # --- England ---
            "EPL", "EFL_Championship", "FA_Cup", "EFL_Cup",
            # --- France ---
            "Ligue1", "Ligue2", "CoupeDeFrance", "TropheeDesChampions",
            # --- Italy ---
            "SerieA", "SerieB", "CoppaItalia", "SupercoppaItaliana",
            # --- Germany ---
            "Bundesliga", "Bundesliga2", "DFB_Pokal", "DFL_Supercup",
            # --- Portugal ---
            "LigaPortugal", "LigaPortugal2", "TacaDePortugal", "Supertaca",
            # --- Netherlands ---
            "Eredivisie", "EersteDivisie", "KNVB_Beker", "JohanCruyffSchaal",
            # --- Continental ---
            "UCL", "UEL", "UECL",
            # --- Other ---
            "Friendly",
        ])
        grid.addWidget(self._source_combo, 0, 1)

        grid.addWidget(QLabel("Round"), 0, 2)
        self._round_input = QLineEdit()
        self._round_input.setPlaceholderText("R15, QF, GS3...")
        grid.addWidget(self._round_input, 0, 3)

        grid.addWidget(QLabel("Opponent"), 1, 0)
        self._opponent_input = QLineEdit()
        self._opponent_input.setPlaceholderText("e.g. Real Madrid")
        grid.addWidget(self._opponent_input, 1, 1, 1, 3)
        layout.addLayout(grid)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #404060;")
        layout.addWidget(sep2)

        session_label = QLabel("Session Defaults (apply to all frames)")
        session_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(session_label)

        # Weather radio buttons
        weather_opts = self._meta_opts["session_level"]["weather"]["options"]
        self._weather_group = QButtonGroup(self)
        weather_box = QGroupBox("Weather")
        wl = QHBoxLayout(weather_box)
        for i, opt in enumerate(weather_opts):
            rb = QRadioButton(opt.replace("_", " ").title())
            rb.setProperty("value", opt)
            self._weather_group.addButton(rb, i)
            wl.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        layout.addWidget(weather_box)

        # Lighting radio buttons
        lighting_opts = self._meta_opts["session_level"]["lighting"]["options"]
        self._lighting_group = QButtonGroup(self)
        lighting_box = QGroupBox("Lighting")
        ll = QHBoxLayout(lighting_box)
        for i, opt in enumerate(lighting_opts):
            rb = QRadioButton(opt.replace("_", " ").title())
            rb.setProperty("value", opt)
            self._lighting_group.addButton(rb, i)
            ll.addWidget(rb)
            if opt == "floodlight":
                rb.setChecked(True)
        layout.addWidget(lighting_box)

        # Start button
        layout.addSpacing(8)
        self._start_btn = QPushButton("Start Annotating")
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

        # Pre-fill roster with default if it exists
        default_roster = Path(__file__).parent.parent / "rosters" / "atletico_madrid_2024-25.csv"
        if default_roster.exists():
            self._roster_path = str(default_roster)
            self._roster_input.setText(str(default_roster))
            self._preview_roster(default_roster)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Screenshot Folder")
        if folder:
            self._folder_path = folder
            self._folder_input.setText(folder)

    def _browse_roster(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Roster CSV",
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
                    self._roster_info.setText(f"{team} | {season} | {count} players")
                else:
                    self._roster_info.setText("Empty CSV")
        except Exception:
            self._roster_info.setText("Could not read CSV")

    def _on_start(self):
        if not self._folder_path or not self._round_input.text().strip():
            return
        weather_btn = self._weather_group.checkedButton()
        lighting_btn = self._lighting_group.checkedButton()
        self._result = {
            "folder": self._folder_path,
            "roster": self._roster_path,
            "source": self._source_combo.currentText(),
            "round": self._round_input.text().strip(),
            "opponent": self._opponent_input.text().strip(),
            "weather": weather_btn.property("value") if weather_btn else "clear",
            "lighting": lighting_btn.property("value") if lighting_btn else "floodlight",
        }
        self.accept()

    def get_result(self) -> dict:
        return self._result
