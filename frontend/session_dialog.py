import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QButtonGroup, QRadioButton, QGroupBox, QGridLayout,
    QFrame, QSlider,
)

try:
    from backend.model_manager import AI_AVAILABLE
except ImportError:
    AI_AVAILABLE = False

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
        self._roster_info.setStyleSheet("color: #F5A623; font-size: 11px;")
        layout.addWidget(self._roster_info)

        # Squad JSON row
        self._squad_label = QLabel("Squad File (squad.json)")
        self._squad_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._squad_label)
        squad_row = QHBoxLayout()
        self._squad_input = QLineEdit()
        self._squad_input.setPlaceholderText("Auto-detected or browse...")
        self._squad_input.setReadOnly(True)
        squad_row.addWidget(self._squad_input, stretch=1)
        self._browse_squad_btn = QPushButton(t("button.browse"))
        self._browse_squad_btn.clicked.connect(self._browse_squad)
        squad_row.addWidget(self._browse_squad_btn)
        self._generate_squad_btn = QPushButton("Generate from SquadList")
        self._generate_squad_btn.setToolTip(
            "Scan a SquadList folder of player headshot images\n"
            "and auto-generate squad.json from the filenames.\n"
            "Image names should be: {number}_{Name}.png"
        )
        self._generate_squad_btn.setStyleSheet("""
            QPushButton {
                background: #2D5A27; color: #A8E6A1; padding: 8px 12px;
                border-radius: 4px; font-size: 11px; border: none;
            }
            QPushButton:hover { background: #3A7A32; }
        """)
        self._generate_squad_btn.clicked.connect(self._generate_squad_from_folder)
        squad_row.addWidget(self._generate_squad_btn)
        layout.addLayout(squad_row)

        self._squad_info = QLabel("")
        self._squad_info.setStyleSheet("color: #F5A623; font-size: 11px;")
        layout.addWidget(self._squad_info)
        self._squad_path = ""

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

        # ── Annotation Mode ──
        self._mode_label = QLabel(t("session.annotation_mode_label"))
        self._mode_label.setStyleSheet("color: #8888A0; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._mode_label)

        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._manual_radio = QRadioButton(t("session.mode_manual"))
        self._manual_radio.setChecked(True)
        self._ai_radio = QRadioButton(t("session.mode_ai_assisted"))
        if not AI_AVAILABLE:
            self._ai_radio.setEnabled(False)
            self._ai_radio.setToolTip(t("session.ai_unavailable_tooltip"))
        self._mode_group.addButton(self._manual_radio, 0)
        self._mode_group.addButton(self._ai_radio, 1)
        mode_row.addWidget(self._manual_radio)
        mode_row.addWidget(self._ai_radio)
        layout.addLayout(mode_row)

        # Model selection
        model_row = QHBoxLayout()
        self._model_label = QLabel(t("session.model_label"))
        model_row.addWidget(self._model_label)
        self._model_combo = QComboBox()
        self._model_items = [
            # (display_name, model_key, group)
            ("Football — RF-DETR-n  (fast)", "football-rfdetr-n", "football"),
            ("Football — RF-DETR-s  (balanced)", "football-rfdetr-s", "football"),
            ("Football — RF-DETR-m  (accurate)", "football-rfdetr-m", "football"),
            ("Football — YOLO11n  (fast)", "football-yolo11n", "football"),
            ("Football — YOLO11s  (balanced)", "football-yolo11s", "football"),
            ("Football — YOLO11m  (accurate)", "football-yolo11m", "football"),
            ("COCO — YOLOv8n  (fast, 80 classes)", "yolov8n", "coco"),
            ("COCO — YOLOv8s  (balanced, 80 classes)", "yolov8s", "coco"),
            ("COCO — YOLOv8m  (accurate, 80 classes)", "yolov8m", "coco"),
            ("Custom model...", "custom", "custom"),
        ]
        for display, _key, _group in self._model_items:
            self._model_combo.addItem(display)
        # Default: Football — YOLO11s (index 4)
        self._model_combo.setCurrentIndex(4)
        self._model_combo.setEnabled(False)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_row.addWidget(self._model_combo, stretch=1)
        layout.addLayout(model_row)

        # Model description line
        self._model_desc = QLabel(t("session.model_desc_football"))
        self._model_desc.setStyleSheet("color: #6A6A8A; font-size: 10px; padding-left: 4px;")
        self._model_desc.setWordWrap(True)
        self._model_desc.setVisible(False)
        layout.addWidget(self._model_desc)

        # Custom model file picker (hidden by default)
        custom_row = QHBoxLayout()
        self._custom_model_input = QLineEdit()
        self._custom_model_input.setPlaceholderText(t("session.custom_model_placeholder"))
        self._custom_model_input.setReadOnly(True)
        self._custom_model_input.setVisible(False)
        custom_row.addWidget(self._custom_model_input, stretch=1)
        self._browse_model_btn = QPushButton(t("button.browse"))
        self._browse_model_btn.setVisible(False)
        self._browse_model_btn.clicked.connect(self._browse_custom_model)
        custom_row.addWidget(self._browse_model_btn)
        layout.addLayout(custom_row)

        # Confidence slider
        conf_row = QHBoxLayout()
        self._conf_label = QLabel(t("session.confidence_label"))
        conf_row.addWidget(self._conf_label)
        self._conf_slider = QSlider(Qt.Orientation.Horizontal)
        self._conf_slider.setRange(10, 90)
        self._conf_slider.setValue(30)
        self._conf_slider.setEnabled(False)
        self._conf_slider.setFixedWidth(200)
        self._conf_value_label = QLabel("0.30")
        self._conf_value_label.setFixedWidth(35)
        self._conf_slider.valueChanged.connect(
            lambda v: self._conf_value_label.setText(f"{v / 100:.2f}")
        )
        conf_row.addWidget(self._conf_slider)
        conf_row.addWidget(self._conf_value_label)
        conf_row.addStretch()
        layout.addLayout(conf_row)

        # Connect mode toggle
        self._mode_group.idToggled.connect(self._on_mode_toggled)

        # Separator before session defaults
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("color: #404060;")
        layout.addWidget(sep3)

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
        self._browse_squad_btn.setText(t("button.browse"))
        self._source_label.setText(t("session.source_label"))
        self._source_combo.lineEdit().setPlaceholderText(t("session.source_placeholder"))
        self._round_label.setText(t("session.round_label"))
        self._round_input.setPlaceholderText(t("session.round_placeholder"))
        self._opponent_label.setText(t("session.opponent_label"))
        self._opponent_combo.lineEdit().setPlaceholderText(t("session.opponent_placeholder"))
        self._defaults_label.setText(t("session.defaults_label"))
        self._mode_label.setText(t("session.annotation_mode_label"))
        self._manual_radio.setText(t("session.mode_manual"))
        self._ai_radio.setText(t("session.mode_ai_assisted"))
        if not AI_AVAILABLE:
            self._ai_radio.setToolTip(t("session.ai_unavailable_tooltip"))
        self._model_label.setText(t("session.model_label"))
        self._conf_label.setText(t("session.confidence_label"))
        self._custom_model_input.setPlaceholderText(t("session.custom_model_placeholder"))
        # Update model description if visible
        if self._model_desc.isVisible():
            self._on_model_changed(self._model_combo.currentIndex())
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

    # ── Annotation Mode ──

    def _on_mode_toggled(self, id: int, checked: bool):
        ai_mode = self._ai_radio.isChecked()
        self._model_combo.setEnabled(ai_mode)
        self._conf_slider.setEnabled(ai_mode)
        self._model_desc.setVisible(ai_mode)
        if ai_mode:
            self._on_model_changed(self._model_combo.currentIndex())

    def _on_model_changed(self, index: int):
        if index < 0 or index >= len(self._model_items):
            return
        _display, _key, group = self._model_items[index]
        is_custom = (group == "custom")
        self._custom_model_input.setVisible(is_custom)
        self._browse_model_btn.setVisible(is_custom)
        # Update description
        if group == "football":
            self._model_desc.setText(t("session.model_desc_football"))
        elif group == "coco":
            self._model_desc.setText(t("session.model_desc_coco"))
        else:
            self._model_desc.setText(t("session.model_desc_custom"))

    def _browse_custom_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("dialog.select_model"), "",
            "PyTorch Models (*.pt);;All Files (*)",
        )
        if path:
            self._custom_model_input.setText(path)

    # ── File browsing ──

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, t("dialog.select_folder"))
        if folder:
            self._folder_path = folder
            self._folder_input.setText(folder)
            # Auto-detect squad.json in selected folder
            self._auto_detect_squad(folder)

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

    def _browse_squad(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Squad File",
            str(Path(self._folder_path) if self._folder_path else Path.home()),
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self._squad_path = path
            self._squad_input.setText(path)
            self._preview_squad(Path(path))

    def _generate_squad_from_folder(self):
        """Generate squad.json from a SquadList folder of player images."""
        from backend.squad_loader import (
            find_squad_list_folder, generate_squad_json, _IMAGE_EXTS,
        )

        # Try to find SquadList folder automatically first
        sl_folder = None
        if self._folder_path:
            sl_folder = find_squad_list_folder(self._folder_path)

        if not sl_folder:
            # Let user browse for it
            chosen = QFileDialog.getExistingDirectory(
                self, "Select SquadList Folder",
                str(Path(self._folder_path) if self._folder_path else Path.home()),
            )
            if not chosen:
                return
            sl_folder = Path(chosen)

        # Count valid images
        image_count = sum(
            1 for f in sl_folder.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
            and "_" in f.stem
        )
        if image_count == 0:
            self._squad_info.setText(
                "No valid player images found. Files should be named: {number}_{Name}.png"
            )
            self._squad_info.setStyleSheet("color: #E74C3C; font-size: 11px;")
            return

        # Determine output path: put squad.json next to the SquadList folder
        output_dir = sl_folder.parent
        output_path = output_dir / "squad.json"

        # Get team name from project config or roster
        team_name = ""
        if self._project_config and self._project_config.exists:
            team_name = self._project_config.team_name

        result = generate_squad_json(sl_folder, output_path, team_name=team_name)
        if result:
            self._squad_path = str(result)
            self._squad_input.setText(str(result))
            self._preview_squad(result)
            self._squad_info.setStyleSheet("color: #27AE60; font-size: 11px;")
            info_text = self._squad_info.text()
            self._squad_info.setText(
                f"Generated from {image_count} images in SquadList/  |  {info_text}"
            )
        else:
            self._squad_info.setText("Failed to generate squad.json — no valid images found")
            self._squad_info.setStyleSheet("color: #E74C3C; font-size: 11px;")

    def _auto_detect_squad(self, folder: str):
        """Auto-detect squad.json or SquadList folder in the session folder."""
        from backend.squad_loader import find_squad_json, find_squad_list_folder, _IMAGE_EXTS

        # 1. Try to find existing squad.json
        found = find_squad_json(folder)
        if found:
            self._squad_path = str(found)
            self._squad_input.setText(str(found))
            self._preview_squad(found)
            return

        # 2. Check for SquadList folder and show hint
        sl_folder = find_squad_list_folder(folder)
        if sl_folder:
            image_count = sum(
                1 for f in sl_folder.iterdir()
                if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
                and "_" in f.stem
            )
            if image_count > 0:
                self._squad_path = ""
                self._squad_input.setText("")
                self._squad_info.setText(
                    f"SquadList/ found ({image_count} images) — "
                    f"click \"Generate from SquadList\" to create squad.json"
                )
                self._squad_info.setStyleSheet("color: #3498DB; font-size: 11px;")
                return

        # Nothing found
        self._squad_path = ""
        self._squad_input.setText("")
        self._squad_info.setText("")

    def _preview_squad(self, path: Path):
        """Show a brief preview of the squad.json contents."""
        from backend.squad_loader import load_squad_json
        squad = load_squad_json(path)
        if squad and squad.is_loaded:
            parts = []
            if squad.home_team.players:
                parts.append(f"Home: {squad.home_team.name or 'Team'} ({len(squad.home_team.players)} players)")
            if squad.away_team.players:
                parts.append(f"Away: {squad.away_team.name or 'Team'} ({len(squad.away_team.players)} players)")
            self._squad_info.setText(" | ".join(parts))
        else:
            self._squad_info.setText("Invalid squad.json file")

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
            "squad_json": self._squad_path,
            "source": self._source_combo.currentText(),
            "round": self._round_input.text().strip(),
            "opponent": self._opponent_combo.currentText().strip(),
            "language": self._selected_lang,
        }
        # AI-Assisted mode settings
        if self._ai_radio.isChecked():
            model_idx = self._model_combo.currentIndex()
            _display, model_key, _group = self._model_items[model_idx]
            self._result["annotation_mode"] = "ai_assisted"
            if model_key == "custom":
                self._result["model_name"] = "custom"
                self._result["custom_model_path"] = self._custom_model_input.text()
            else:
                self._result["model_name"] = model_key
            self._result["model_confidence"] = self._conf_slider.value() / 100.0
        else:
            self._result["annotation_mode"] = "manual"
            self._result["model_name"] = ""
            self._result["model_confidence"] = 0.30

        # Collect session-level values from dynamic radio groups
        defaults = {"weather": "clear", "lighting": "floodlight"}
        for key, group in self._session_groups.items():
            btn = group.checkedButton()
            self._result[key] = btn.property("value") if btn else defaults.get(key, "")
        self.accept()

    def get_result(self) -> dict:
        return self._result
