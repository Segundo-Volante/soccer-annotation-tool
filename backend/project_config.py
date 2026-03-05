import json
from pathlib import Path
from typing import Optional


class ProjectConfig:
    """Loads and provides access to config/project.json and team config."""

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)
        self._project_path = self.config_dir / "project.json"
        self._data: Optional[dict] = None
        if self._project_path.exists():
            self._data = json.loads(self._project_path.read_text(encoding="utf-8"))

    @property
    def exists(self) -> bool:
        return self._data is not None

    @property
    def team_name(self) -> str:
        if not self._data:
            return "Home Team"
        return self._data.get("team_name", "Home Team")

    @property
    def season(self) -> str:
        if not self._data:
            return ""
        return self._data.get("season", "")

    @property
    def language(self) -> str:
        if not self._data:
            return "en"
        return self._data.get("language", "en")

    def get_competitions(self) -> list[str]:
        if not self._data:
            return []
        return self._data.get("competitions", [])

    def get_categories(self) -> list[dict]:
        """Return raw category definitions from project.json."""
        if not self._data:
            return []
        return self._data.get("categories", [])

    def get_resolved_categories(self) -> list[dict]:
        """Return categories with {home} replaced by team_name."""
        categories = self.get_categories()
        team = self.team_name
        resolved = []
        for cat in categories:
            entry = dict(cat)
            entry["label"] = entry["label"].replace("{home}", team)
            resolved.append(entry)
        return resolved

    def get_category_colors(self) -> dict[int, str]:
        """Return {category_id: hex_color}."""
        return {cat["id"]: cat["color"] for cat in self.get_categories()}

    def get_category_roster_type(self, category_id: int) -> str:
        """Return roster type for a category: 'home', 'opponent_auto', or 'none'."""
        for cat in self.get_categories():
            if cat["id"] == category_id:
                return cat.get("roster", "none")
        return "none"

    def get_home_roster_path(self) -> Optional[Path]:
        """Read config/teams/home.json and resolve the roster CSV path."""
        home_json = self.config_dir / "teams" / "home.json"
        if not home_json.exists():
            return None
        try:
            data = json.loads(home_json.read_text(encoding="utf-8"))
            csv_path = data.get("roster_csv", "")
            if not csv_path:
                return None
            resolved = (home_json.parent / csv_path).resolve()
            return resolved if resolved.exists() else None
        except Exception:
            return None

    def list_opponent_csvs(self) -> list[Path]:
        """List all CSV files in config/teams/opponents/."""
        opp_dir = self.config_dir / "teams" / "opponents"
        if not opp_dir.exists():
            return []
        return sorted(opp_dir.glob("*.csv"))

    def get_opponent_names(self) -> list[str]:
        """Extract opponent names from CSV filenames (stem, underscores to spaces)."""
        return [p.stem.replace("_", " ") for p in self.list_opponent_csvs()]

    def get_opponent_roster_path(self, opponent_name: str) -> Optional[Path]:
        """Find a matching opponent CSV by name (case-insensitive)."""
        normalized = opponent_name.lower().replace(" ", "_")
        for csv_path in self.list_opponent_csvs():
            if csv_path.stem.lower() == normalized:
                return csv_path
        return None

    def set_language(self, lang: str):
        """Update language in project.json."""
        if self._data:
            self._data["language"] = lang
            self.save(self._data)

    def save(self, data: dict):
        """Write project.json."""
        self._project_path.parent.mkdir(parents=True, exist_ok=True)
        self._project_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._data = data

    # ── ReID targets & resample thresholds ──

    _DEFAULT_REID_TARGETS = {"wide": 150, "medium": 60, "closeup": 20}
    _DEFAULT_RESAMPLE_THRESHOLDS = {
        "wide_min_player_ratio": 0.5,
        "medium_min_player_frames": 1,
        "closeup_min_player_frames": 1,
        "min_sequence_length": 3,
        "estimated_resample_interval": 0.3,
    }

    def get_reid_targets(self) -> dict[str, int]:
        if not self._data:
            return dict(self._DEFAULT_REID_TARGETS)
        return self._data.get("reid_targets", dict(self._DEFAULT_REID_TARGETS))

    def get_resample_thresholds(self) -> dict:
        if not self._data:
            return dict(self._DEFAULT_RESAMPLE_THRESHOLDS)
        return self._data.get("resample_thresholds", dict(self._DEFAULT_RESAMPLE_THRESHOLDS))

    def save_reid_settings(self, targets: dict[str, int], thresholds: dict):
        """Persist reid_targets and resample_thresholds to project.json."""
        if not self._data:
            self._data = {}
        self._data["reid_targets"] = targets
        self._data["resample_thresholds"] = thresholds
        self.save(self._data)

    def save_home_team(self, team_name: str, roster_csv_path: str):
        """Write config/teams/home.json."""
        home_json = self.config_dir / "teams" / "home.json"
        home_json.parent.mkdir(parents=True, exist_ok=True)
        data = {"team_name": team_name, "roster_csv": roster_csv_path}
        home_json.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
