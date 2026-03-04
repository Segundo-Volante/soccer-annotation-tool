"""Load squad.json files and SquadList image folders for match squad data.

squad.json structure:
{
  "home_team": {
    "name": "Atlético de Madrid",
    "formation": "4-4-2",
    "players": [
      {"number": 13, "name": "Oblak", "position": "GK"},
      ...
    ]
  },
  "away_team": {
    "name": "Getafe CF",
    "players": [
      {"number": 1, "name": "Soria", "position": "GK"},
      ...
    ]
  }
}

SquadList folder: contains player headshot images named {number}_{Name}.png
  e.g. 7_Antoine Griezmann.png, 13_JanOblak.jpeg
  Jersey number is parsed from the prefix before the first underscore.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.models import Player

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass
class TeamSquad:
    """One team's squad data from squad.json."""
    name: str = ""
    formation: str = ""
    players: list[Player] = field(default_factory=list)


@dataclass
class SquadData:
    """Full match squad data (both teams)."""
    home_team: TeamSquad = field(default_factory=TeamSquad)
    away_team: TeamSquad = field(default_factory=TeamSquad)
    # Mapping: (side, jersey_number) → image path  (from SquadList folder)
    headshot_images: dict[tuple[str, int], Path] = field(default_factory=dict)

    @property
    def is_loaded(self) -> bool:
        return bool(self.home_team.players) or bool(self.away_team.players)


def load_squad_json(path: str | Path) -> Optional[SquadData]:
    """Load squad data from a squad.json file.

    Returns SquadData or None if the file doesn't exist or is invalid.
    """
    p = Path(path)
    if not p.exists():
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    squad = SquadData()

    # Parse home team
    home = data.get("home_team", {})
    if home:
        squad.home_team.name = home.get("name", "")
        squad.home_team.formation = home.get("formation", "")
        for p_data in home.get("players", []):
            squad.home_team.players.append(Player(
                jersey_number=int(p_data.get("number", 0)),
                name=p_data.get("name", "Unknown"),
                position=p_data.get("position", ""),
            ))
        # Sort by jersey number
        squad.home_team.players.sort(key=lambda p: p.jersey_number)

    # Parse away team
    away = data.get("away_team", {})
    if away:
        squad.away_team.name = away.get("name", "")
        squad.away_team.formation = away.get("formation", "")
        for p_data in away.get("players", []):
            squad.away_team.players.append(Player(
                jersey_number=int(p_data.get("number", 0)),
                name=p_data.get("name", "Unknown"),
                position=p_data.get("position", ""),
            ))
        squad.away_team.players.sort(key=lambda p: p.jersey_number)

    return squad


def squad_from_roster(roster_manager, team_side: str = "home") -> SquadData:
    """Convert an existing RosterManager (CSV-based) into SquadData.

    This provides backward compatibility — if only a CSV roster is loaded
    but no squad.json, we can still populate the squad sheet.
    """
    squad = SquadData()
    if roster_manager is None:
        return squad

    team = TeamSquad()
    team.name = roster_manager.team_name
    for player in roster_manager.get_all_players():
        team.players.append(Player(
            jersey_number=player.jersey_number,
            name=player.name,
            position=player.position if player.position else "",
        ))
    team.players.sort(key=lambda p: p.jersey_number)

    if team_side == "home":
        squad.home_team = team
    else:
        squad.away_team = team

    return squad


def scan_squad_list_folder(
    folder_path: str | Path,
    team_side: str = "home",
    team_name: str = "",
) -> Optional[SquadData]:
    """Scan a SquadList-style folder and build SquadData from image filenames.

    Each image file is named ``{jersey_number}_{PlayerName}.{ext}``.
    The jersey number is the integer prefix before the first underscore.
    The player name is derived from the portion after the underscore
    (with CamelCase split into words if no spaces are present).

    Args:
        folder_path: Path to the folder containing player headshot images.
        team_side: Which team these players belong to ("home" or "away").
        team_name: Display name for the team (optional).

    Returns:
        SquadData with players populated, or None if the folder is empty/invalid.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return None

    players: list[Player] = []
    headshots: dict[tuple[str, int], Path] = {}

    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _IMAGE_EXTS:
            continue
        stem = f.stem  # e.g. "7_Antoine Griezmann" or "13_JanOblak"
        parts = stem.split("_", 1)
        if len(parts) < 2:
            continue
        try:
            jersey = int(parts[0])
        except ValueError:
            continue

        raw_name = parts[1]
        # If name has no spaces, split CamelCase: "JanOblak" → "Jan Oblak"
        if " " not in raw_name:
            raw_name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw_name)
            raw_name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", raw_name)
        name = raw_name.strip()

        players.append(Player(jersey_number=jersey, name=name))
        headshots[(team_side, jersey)] = f

    if not players:
        return None

    players.sort(key=lambda p: p.jersey_number)
    team = TeamSquad(name=team_name, players=players)
    squad = SquadData(headshot_images=headshots)
    if team_side == "home":
        squad.home_team = team
    else:
        squad.away_team = team
    return squad


def find_squad_list_folder(session_folder: str | Path) -> Optional[Path]:
    """Look for a SquadList image folder near the session folder.

    Search order:
    1. ``session_folder/SquadList/``
    2. ``session_folder/../SquadList/`` (parent)
    3. Walk up to the project root (containing ``config/`` or ``.git``)
       and check ``project_root/SquadList/``
    """
    folder = Path(session_folder).resolve()

    # 1. Direct child
    candidate = folder / "SquadList"
    if candidate.is_dir():
        return candidate

    # 2. Sibling (parent's child)
    candidate = folder.parent / "SquadList"
    if candidate.is_dir():
        return candidate

    # 3. Walk up until we find a project root marker
    current = folder.parent.parent
    for _ in range(10):  # safety limit
        if not current or current == current.parent:
            break
        sq = current / "SquadList"
        if sq.is_dir():
            return sq
        # Stop if we've reached a likely project root
        if (current / ".git").exists() or (current / "config").is_dir():
            break
        current = current.parent

    return None


def generate_squad_json(
    squad_list_folder: str | Path,
    output_path: str | Path,
    team_name: str = "",
    team_side: str = "home",
) -> Optional[Path]:
    """Generate a squad.json file from a SquadList image folder.

    Scans the folder for images named ``{number}_{Name}.{ext}``, parses
    jersey numbers and player names, and writes a valid squad.json.

    Args:
        squad_list_folder: Path to the SquadList folder with player images.
        output_path: Where to write the generated squad.json file.
        team_name: Display name for the team (e.g. "Atlético de Madrid").
        team_side: Which team the players belong to ("home" or "away").

    Returns:
        Path to the generated file, or None if no valid images were found.
    """
    folder = Path(squad_list_folder)
    if not folder.is_dir():
        return None

    players_data: list[dict] = []

    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _IMAGE_EXTS:
            continue
        stem = f.stem
        parts = stem.split("_", 1)
        if len(parts) < 2:
            continue
        try:
            jersey = int(parts[0])
        except ValueError:
            continue

        raw_name = parts[1]
        # If name has no spaces, split CamelCase: "JanOblak" → "Jan Oblak"
        if " " not in raw_name:
            raw_name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw_name)
            raw_name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", raw_name)
        name = raw_name.strip()

        players_data.append({"number": jersey, "name": name})

    if not players_data:
        return None

    # Sort by jersey number
    players_data.sort(key=lambda p: p["number"])

    # Build the JSON structure
    team_obj = {"name": team_name, "players": players_data}
    data: dict = {}
    if team_side == "home":
        data["home_team"] = team_obj
    else:
        data["away_team"] = team_obj

    out = Path(output_path)
    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def find_squad_json(session_folder: str | Path) -> Optional[Path]:
    """Look for squad.json in the session folder or parent."""
    folder = Path(session_folder)
    # Check directly in session folder
    candidate = folder / "squad.json"
    if candidate.exists():
        return candidate
    # Check one level up (e.g., match folder containing frame folder)
    parent_candidate = folder.parent / "squad.json"
    if parent_candidate.exists():
        return parent_candidate
    return None
