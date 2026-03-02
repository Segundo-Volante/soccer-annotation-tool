import csv
import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QGroupBox, QCheckBox, QGridLayout, QFrame,
    QStackedWidget, QWidget, QScrollArea,
)

from backend.i18n import t

# Competitions grouped by country
COMPETITION_GROUPS = {
    "Spain": ["LaLiga", "LaLiga2", "CopadelRey", "Supercopa"],
    "England": ["EPL", "EFL_Championship", "FA_Cup", "EFL_Cup"],
    "France": ["Ligue1", "Ligue2", "CoupeDeFrance", "TropheeDesChampions"],
    "Italy": ["SerieA", "SerieB", "CoppaItalia", "SupercoppaItaliana"],
    "Germany": ["Bundesliga", "Bundesliga2", "DFB_Pokal", "DFL_Supercup"],
    "Portugal": ["LigaPortugal", "LigaPortugal2", "TacaDePortugal", "Supertaca"],
    "Netherlands": ["Eredivisie", "EersteDivisie", "KNVB_Beker", "JohanCruyffSchaal"],
    "Europe": ["UCL", "UEL", "UECL"],
    "Other": ["Friendly"],
}

LANGUAGES = [
    ("en", "English"),
    ("it", "Italiano"),
    ("de", "Deutsch"),
    ("pt", "Português"),
    ("fr", "Français"),
]

# Default categories (always used)
DEFAULT_CATEGORIES = [
    {"id": 0, "key": "home_player", "label": "{home} Player", "color": "#E53935", "roster": "home"},
    {"id": 1, "key": "opponent", "label": "Opponent", "color": "#1E88E5", "roster": "opponent_auto"},
    {"id": 2, "key": "home_gk", "label": "{home} GK", "color": "#FF9800", "roster": "home"},
    {"id": 3, "key": "opponent_gk", "label": "Opponent GK", "color": "#0D47A1", "roster": "opponent_auto"},
    {"id": 4, "key": "referee", "label": "Referee", "color": "#FDD835", "roster": "none"},
    {"id": 5, "key": "ball", "label": "Ball", "color": "#43A047", "roster": "none"},
]

DARK_STYLE = """
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
    QCheckBox { color: #E8E8F0; font-size: 11px; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QScrollArea { border: none; background: transparent; }
"""


class SetupWizard(QDialog):
    """First-run setup wizard that creates config/project.json."""

    def __init__(self, config_dir: str | Path, parent=None):
        super().__init__(parent)
        self.config_dir = Path(config_dir)
        self.setWindowTitle(t("wizard.window_title"))
        self.setFixedSize(620, 560)
        self.setStyleSheet(DARK_STYLE)

        self._roster_path = ""
        self._result = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel(t("wizard.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5A623;")
        layout.addWidget(title)

        subtitle = QLabel(t("wizard.subtitle"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8888A0; font-size: 12px;")
        layout.addWidget(subtitle)

        # Stacked pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        self._build_page1()
        self._build_page2()
        self._build_page3()

        # Navigation buttons
        nav_row = QHBoxLayout()
        self._back_btn = QPushButton(t("button.back"))
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)
        nav_row.addWidget(self._back_btn)
        nav_row.addStretch()

        self._next_btn = QPushButton(t("button.next"))
        self._next_btn.setStyleSheet("""
            QPushButton {
                background: #F5A623; color: #1E1E2E; font-size: 13px;
                font-weight: bold; padding: 10px 24px; border-radius: 6px;
            }
            QPushButton:hover { background: #FFB833; }
        """)
        self._next_btn.clicked.connect(self._go_next)
        nav_row.addWidget(self._next_btn)
        layout.addLayout(nav_row)

    def _build_page1(self):
        """Page 1: Team name, season, language, roster."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # Team name
        layout.addWidget(self._make_label(t("wizard.team_name")))
        self._team_input = QLineEdit()
        self._team_input.setPlaceholderText(t("wizard.team_name_placeholder"))
        layout.addWidget(self._team_input)

        # Season
        layout.addWidget(self._make_label(t("wizard.season")))
        self._season_input = QLineEdit()
        self._season_input.setPlaceholderText(t("wizard.season_placeholder"))
        layout.addWidget(self._season_input)

        # Language
        layout.addWidget(self._make_label(t("wizard.language")))
        self._lang_combo = QComboBox()
        for code, name in LANGUAGES:
            self._lang_combo.addItem(name, code)
        layout.addWidget(self._lang_combo)

        # Roster CSV
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #404060;")
        layout.addWidget(sep)

        layout.addWidget(self._make_label(t("wizard.roster_csv")))
        roster_row = QHBoxLayout()
        self._roster_input = QLineEdit()
        self._roster_input.setPlaceholderText(t("wizard.roster_placeholder"))
        self._roster_input.setReadOnly(True)
        roster_row.addWidget(self._roster_input, stretch=1)
        browse_btn = QPushButton(t("button.browse"))
        browse_btn.clicked.connect(self._browse_roster)
        roster_row.addWidget(browse_btn)
        layout.addLayout(roster_row)

        self._roster_info = QLabel("")
        self._roster_info.setStyleSheet("color: #4A90D9; font-size: 11px;")
        layout.addWidget(self._roster_info)

        layout.addStretch()
        self._stack.addWidget(page)

    def _build_page2(self):
        """Page 2: Competitions checklist."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        layout.addWidget(self._make_label(t("wizard.competitions_title")))
        hint = QLabel(t("wizard.competitions_hint"))
        hint.setStyleSheet("color: #8888A0; font-size: 11px;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)

        self._comp_checkboxes: dict[str, QCheckBox] = {}
        for country, comps in COMPETITION_GROUPS.items():
            group = QGroupBox(country)
            grid = QGridLayout(group)
            grid.setSpacing(4)
            for i, comp in enumerate(comps):
                cb = QCheckBox(comp.replace("_", " "))
                cb.setProperty("comp_key", comp)
                self._comp_checkboxes[comp] = cb
                grid.addWidget(cb, i // 2, i % 2)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, stretch=1)

        # Quick select buttons
        btn_row = QHBoxLayout()
        select_all = QPushButton(t("button.select_all"))
        select_all.clicked.connect(lambda: self._toggle_all_comps(True))
        btn_row.addWidget(select_all)
        clear_all = QPushButton(t("button.clear_all"))
        clear_all.clicked.connect(lambda: self._toggle_all_comps(False))
        btn_row.addWidget(clear_all)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._stack.addWidget(page)

    def _build_page3(self):
        """Page 3: Summary / confirmation."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(self._make_label(t("wizard.summary_title")))

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            "color: #E8E8F0; font-size: 12px; background: #2A2A3C; "
            "border-radius: 6px; padding: 16px; line-height: 1.6;"
        )
        layout.addWidget(self._summary_label)

        layout.addStretch()

        self._stack.addWidget(page)

    # ── Navigation ──

    def _go_next(self):
        current = self._stack.currentIndex()
        if current == 0:
            if not self._team_input.text().strip():
                return
            self._stack.setCurrentIndex(1)
            self._back_btn.setVisible(True)
        elif current == 1:
            self._update_summary()
            self._stack.setCurrentIndex(2)
            self._next_btn.setText(t("button.finish"))
        elif current == 2:
            self._finish()

    def _go_back(self):
        current = self._stack.currentIndex()
        if current > 0:
            self._stack.setCurrentIndex(current - 1)
            self._next_btn.setText(t("button.next"))
        if self._stack.currentIndex() == 0:
            self._back_btn.setVisible(False)

    def _finish(self):
        team_name = self._team_input.text().strip()
        season = self._season_input.text().strip()
        lang = self._lang_combo.currentData()

        competitions = [
            comp for comp, cb in self._comp_checkboxes.items()
            if cb.isChecked()
        ]

        project_data = {
            "team_name": team_name,
            "season": season,
            "language": lang,
            "competitions": competitions,
            "categories": DEFAULT_CATEGORIES,
        }

        # Save project.json
        from backend.project_config import ProjectConfig
        config = ProjectConfig(self.config_dir)
        config.save(project_data)

        # Save home.json if roster provided
        if self._roster_path:
            roster_rel = str(Path(self._roster_path))
            config.save_home_team(team_name, roster_rel)

        # Create opponents directory
        opp_dir = self.config_dir / "teams" / "opponents"
        opp_dir.mkdir(parents=True, exist_ok=True)

        self._result = project_data
        self.accept()

    # ── Helpers ──

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        return lbl

    def _browse_roster(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("dialog.select_roster"), "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self._roster_path = path
            self._roster_input.setText(path)
            self._preview_roster(Path(path))

    def _preview_roster(self, path: Path):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                if row:
                    team = row.get("team", "?")
                    season = row.get("season", "?")
                    count = 1
                    for _ in reader:
                        count += 1
                    self._roster_info.setText(
                        t("session.roster_preview", team=team, season=season, count=count))
                else:
                    self._roster_info.setText(t("wizard.roster_empty"))
        except Exception:
            self._roster_info.setText(t("wizard.roster_error"))

    def _toggle_all_comps(self, checked: bool):
        for cb in self._comp_checkboxes.values():
            cb.setChecked(checked)

    def _update_summary(self):
        team = self._team_input.text().strip() or "(not set)"
        season = self._season_input.text().strip() or "(not set)"
        lang_name = self._lang_combo.currentText()
        comps = [comp for comp, cb in self._comp_checkboxes.items() if cb.isChecked()]
        comp_text = ", ".join(comps[:8])
        if len(comps) > 8:
            comp_text += f" (+{len(comps) - 8} more)"
        if not comps:
            comp_text = "(none selected)"
        roster_text = Path(self._roster_path).name if self._roster_path else "(none)"

        self._summary_label.setText(
            f"Team: {team}\n"
            f"Season: {season}\n"
            f"Language: {lang_name}\n"
            f"Roster: {roster_text}\n"
            f"Competitions: {comp_text}\n\n"
            + t("wizard.summary_info")
        )

    def get_result(self) -> dict:
        return self._result
