import csv
from pathlib import Path
from typing import Optional

from backend.models import Player


class RosterManager:
    """Loads a team roster from a CSV file.

    CSV format (4 columns):
        team,season,number,name
        Atletico de Madrid,2024-25,7,Antoine Griezmann
    """

    def __init__(self, roster_path: str | Path | None = None):
        self.roster_path: Optional[Path] = Path(roster_path) if roster_path else None
        self.team_name: str = ""
        self.season: str = ""
        self.players: dict[int, Player] = {}
        if self.roster_path:
            self.load()

    def load(self):
        if not self.roster_path or not self.roster_path.exists():
            return
        self.players.clear()
        with open(self.roster_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                number = int(row["number"])
                name = row["name"].strip()
                # Read team/season from the first data row (all rows should match)
                if not self.team_name:
                    self.team_name = row.get("team", "").strip()
                    self.season = row.get("season", "").strip()
                self.players[number] = Player(jersey_number=number, name=name)

    def lookup_by_number(self, number: int) -> Optional[Player]:
        return self.players.get(number)

    def get_all_players(self) -> list[Player]:
        return sorted(self.players.values(), key=lambda p: p.jersey_number)
