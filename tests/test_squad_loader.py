"""Tests for backend/squad_loader.py."""

import json
import os
import tempfile

import pytest

from backend.models import Player
from backend.roster_manager import RosterManager
from backend.squad_loader import (
    SquadData, TeamSquad, load_squad_json, squad_from_roster, find_squad_json,
    scan_squad_list_folder, find_squad_list_folder, generate_squad_json,
)


@pytest.fixture
def squad_json_data():
    """Sample squad.json data."""
    return {
        "home_team": {
            "name": "Atlético de Madrid",
            "formation": "4-4-2",
            "players": [
                {"number": 13, "name": "Oblak", "position": "GK"},
                {"number": 4, "name": "Molina", "position": "RB"},
                {"number": 15, "name": "Savić", "position": "CB"},
                {"number": 7, "name": "Griezmann", "position": "ST"},
                {"number": 19, "name": "Álvarez", "position": "ST"},
            ],
        },
        "away_team": {
            "name": "Getafe CF",
            "players": [
                {"number": 1, "name": "Soria", "position": "GK"},
                {"number": 6, "name": "Alderete", "position": "CB"},
            ],
        },
    }


def test_load_squad_json(squad_json_data):
    """Test loading a valid squad.json file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "squad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(squad_json_data, f, ensure_ascii=False)

        squad = load_squad_json(path)
        assert squad is not None
        assert squad.is_loaded

        # Home team
        assert squad.home_team.name == "Atlético de Madrid"
        assert squad.home_team.formation == "4-4-2"
        assert len(squad.home_team.players) == 5
        # Should be sorted by jersey number
        assert squad.home_team.players[0].jersey_number == 4
        assert squad.home_team.players[0].name == "Molina"
        assert squad.home_team.players[0].position == "RB"
        assert squad.home_team.players[-1].jersey_number == 19

        # Away team
        assert squad.away_team.name == "Getafe CF"
        assert len(squad.away_team.players) == 2
        assert squad.away_team.players[0].jersey_number == 1


def test_load_squad_json_nonexistent():
    """Test loading a non-existent file returns None."""
    result = load_squad_json("/nonexistent/path/squad.json")
    assert result is None


def test_load_squad_json_invalid():
    """Test loading an invalid JSON file returns None."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not valid json {{{")
        path = f.name
    try:
        result = load_squad_json(path)
        assert result is None
    finally:
        os.unlink(path)


def test_load_squad_json_empty_teams():
    """Test loading squad.json with empty/missing teams."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "squad.json")
        with open(path, "w") as f:
            json.dump({"home_team": {"name": "Test", "players": []}}, f)

        squad = load_squad_json(path)
        assert squad is not None
        assert not squad.is_loaded  # No players = not loaded


def test_load_squad_json_home_only(squad_json_data):
    """Test loading squad.json with only home team."""
    del squad_json_data["away_team"]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "squad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(squad_json_data, f, ensure_ascii=False)

        squad = load_squad_json(path)
        assert squad.is_loaded
        assert len(squad.home_team.players) == 5
        assert len(squad.away_team.players) == 0


def test_squad_from_roster():
    """Test converting a CSV RosterManager to SquadData."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "roster.csv")
        with open(csv_path, "w") as f:
            f.write("team,season,number,name\n")
            f.write("TestTeam,2024-25,7,Griezmann\n")
            f.write("TestTeam,2024-25,19,Álvarez\n")

        roster = RosterManager(csv_path)
        squad = squad_from_roster(roster, "home")

        assert squad.is_loaded
        assert squad.home_team.name == "TestTeam"
        assert len(squad.home_team.players) == 2
        assert squad.home_team.players[0].jersey_number == 7
        assert squad.home_team.players[0].name == "Griezmann"
        assert len(squad.away_team.players) == 0


def test_squad_from_roster_away():
    """Test converting roster as away team."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "roster.csv")
        with open(csv_path, "w") as f:
            f.write("team,season,number,name\n")
            f.write("AwayTeam,2024-25,1,Soria\n")

        roster = RosterManager(csv_path)
        squad = squad_from_roster(roster, "away")

        assert squad.is_loaded
        assert len(squad.home_team.players) == 0
        assert squad.away_team.name == "AwayTeam"
        assert len(squad.away_team.players) == 1


def test_squad_from_roster_none():
    """Test with None roster."""
    squad = squad_from_roster(None)
    assert not squad.is_loaded


def test_find_squad_json():
    """Test auto-detecting squad.json in session folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # No squad.json
        assert find_squad_json(tmpdir) is None

        # Create squad.json in folder
        squad_path = os.path.join(tmpdir, "squad.json")
        with open(squad_path, "w") as f:
            json.dump({"home_team": {"players": []}}, f)

        found = find_squad_json(tmpdir)
        assert found is not None
        assert str(found).endswith("squad.json")


def test_find_squad_json_parent():
    """Test auto-detecting squad.json in parent folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        subfolder = os.path.join(tmpdir, "frames")
        os.makedirs(subfolder)

        # Put squad.json in parent
        squad_path = os.path.join(tmpdir, "squad.json")
        with open(squad_path, "w") as f:
            json.dump({"home_team": {"players": []}}, f)

        found = find_squad_json(subfolder)
        assert found is not None
        assert str(found).endswith("squad.json")


def test_squad_data_is_loaded():
    """Test is_loaded property."""
    empty = SquadData()
    assert not empty.is_loaded

    with_home = SquadData(
        home_team=TeamSquad(players=[Player(7, "Test")]),
    )
    assert with_home.is_loaded

    with_away = SquadData(
        away_team=TeamSquad(players=[Player(1, "GK")]),
    )
    assert with_away.is_loaded


# ── SquadList folder scanning tests ──

def _create_squad_list_images(folder, files):
    """Helper: create dummy image files (0-byte) in a SquadList folder."""
    sl_dir = os.path.join(folder, "SquadList")
    os.makedirs(sl_dir, exist_ok=True)
    for name in files:
        open(os.path.join(sl_dir, name), "w").close()
    return sl_dir


def test_scan_squad_list_folder_basic():
    """Test scanning a SquadList folder with standard filenames."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "7_Antoine Griezmann.png",
            "13_JanOblak.jpeg",
            "19_JulianAlvarez.png",
        ])

        squad = scan_squad_list_folder(sl_dir, "home", "Atlético")
        assert squad is not None
        assert squad.is_loaded
        assert squad.home_team.name == "Atlético"
        assert len(squad.home_team.players) == 3

        # Sorted by jersey number
        assert squad.home_team.players[0].jersey_number == 7
        assert squad.home_team.players[0].name == "Antoine Griezmann"
        assert squad.home_team.players[1].jersey_number == 13
        assert squad.home_team.players[1].name == "Jan Oblak"  # CamelCase split
        assert squad.home_team.players[2].jersey_number == 19
        assert squad.home_team.players[2].name == "Julian Alvarez"

        # Headshot images mapped
        assert ("home", 7) in squad.headshot_images
        assert ("home", 13) in squad.headshot_images
        assert ("home", 19) in squad.headshot_images
        assert len(squad.away_team.players) == 0


def test_scan_squad_list_folder_away_team():
    """Test scanning as away team."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "1_Soria.png",
        ])

        squad = scan_squad_list_folder(sl_dir, "away", "Getafe")
        assert squad is not None
        assert len(squad.away_team.players) == 1
        assert squad.away_team.name == "Getafe"
        assert squad.away_team.players[0].name == "Soria"
        assert ("away", 1) in squad.headshot_images


def test_scan_squad_list_folder_camelcase_split():
    """Test CamelCase name splitting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "23_ReinildoMandava.png",
            "24_RobinLeNormand.png",
        ])

        squad = scan_squad_list_folder(sl_dir)
        assert squad is not None
        names = {p.name for p in squad.home_team.players}
        assert "Reinildo Mandava" in names
        assert "Robin Le Normand" in names


def test_scan_squad_list_folder_ignores_non_images():
    """Test that non-image files are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "7_Griezmann.png",
            "readme.txt",
            "notes.md",
            "13_Oblak.json",  # not an image extension
        ])

        squad = scan_squad_list_folder(sl_dir)
        assert squad is not None
        assert len(squad.home_team.players) == 1
        assert squad.home_team.players[0].jersey_number == 7


def test_scan_squad_list_folder_ignores_bad_names():
    """Test that files without valid number prefixes are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "abc_Griezmann.png",  # not a number
            "7.png",  # no underscore
            "7_Griezmann.png",  # valid
        ])

        squad = scan_squad_list_folder(sl_dir)
        assert squad is not None
        assert len(squad.home_team.players) == 1


def test_scan_squad_list_folder_empty():
    """Test scanning an empty folder returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = os.path.join(tmpdir, "SquadList")
        os.makedirs(sl_dir)
        result = scan_squad_list_folder(sl_dir)
        assert result is None


def test_scan_squad_list_folder_nonexistent():
    """Test scanning a non-existent folder returns None."""
    result = scan_squad_list_folder("/nonexistent/path/SquadList")
    assert result is None


def test_find_squad_list_folder_direct():
    """Test finding SquadList in the session folder itself."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = os.path.join(tmpdir, "SquadList")
        os.makedirs(sl_dir)
        found = find_squad_list_folder(tmpdir)
        assert found is not None
        assert found.name == "SquadList"


def test_find_squad_list_folder_parent():
    """Test finding SquadList in the parent folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session = os.path.join(tmpdir, "frames")
        os.makedirs(session)
        sl_dir = os.path.join(tmpdir, "SquadList")
        os.makedirs(sl_dir)
        found = find_squad_list_folder(session)
        assert found is not None
        assert found.name == "SquadList"


def test_find_squad_list_folder_project_root():
    """Test finding SquadList at project root (marked by .git)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project structure: root/.git, root/data/session/frames
        os.makedirs(os.path.join(tmpdir, ".git"))
        os.makedirs(os.path.join(tmpdir, "SquadList"))
        session = os.path.join(tmpdir, "data", "session", "frames")
        os.makedirs(session)

        found = find_squad_list_folder(session)
        assert found is not None
        assert found.name == "SquadList"


def test_find_squad_list_folder_not_found():
    """Test returns None when no SquadList exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        assert find_squad_list_folder(tmpdir) is None


# ── generate_squad_json tests ──

def test_generate_squad_json_basic():
    """Test generating squad.json from a SquadList folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "7_Antoine Griezmann.png",
            "13_JanOblak.jpeg",
            "19_JulianAlvarez.png",
        ])
        output = os.path.join(tmpdir, "squad.json")
        result = generate_squad_json(sl_dir, output, team_name="Atlético")

        assert result is not None
        assert os.path.exists(output)

        # Verify JSON content
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert "home_team" in data
        assert data["home_team"]["name"] == "Atlético"
        players = data["home_team"]["players"]
        assert len(players) == 3
        # Should be sorted by jersey number
        assert players[0]["number"] == 7
        assert players[0]["name"] == "Antoine Griezmann"
        assert players[1]["number"] == 13
        assert players[1]["name"] == "Jan Oblak"  # CamelCase split
        assert players[2]["number"] == 19
        assert players[2]["name"] == "Julian Alvarez"


def test_generate_squad_json_away_team():
    """Test generating as away team."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "1_Soria.png",
            "6_Alderete.png",
        ])
        output = os.path.join(tmpdir, "squad.json")
        result = generate_squad_json(sl_dir, output, team_name="Getafe", team_side="away")

        assert result is not None
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert "away_team" in data
        assert "home_team" not in data
        assert data["away_team"]["name"] == "Getafe"
        assert len(data["away_team"]["players"]) == 2


def test_generate_squad_json_roundtrip():
    """Test that generated squad.json can be loaded back correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "7_Griezmann.png",
            "19_Alvarez.png",
        ])
        output = os.path.join(tmpdir, "squad.json")
        generate_squad_json(sl_dir, output, team_name="TestTeam")

        # Load it back
        squad = load_squad_json(output)
        assert squad is not None
        assert squad.is_loaded
        assert squad.home_team.name == "TestTeam"
        assert len(squad.home_team.players) == 2
        assert squad.home_team.players[0].jersey_number == 7
        assert squad.home_team.players[0].name == "Griezmann"
        assert squad.home_team.players[1].jersey_number == 19


def test_generate_squad_json_empty_folder():
    """Test with a folder containing no valid images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = os.path.join(tmpdir, "SquadList")
        os.makedirs(sl_dir)
        # Only non-image files
        open(os.path.join(sl_dir, "readme.txt"), "w").close()

        output = os.path.join(tmpdir, "squad.json")
        result = generate_squad_json(sl_dir, output)
        assert result is None
        assert not os.path.exists(output)


def test_generate_squad_json_nonexistent_folder():
    """Test with a non-existent folder."""
    result = generate_squad_json("/nonexistent/SquadList", "/tmp/out.json")
    assert result is None


def test_generate_squad_json_ignores_bad_files():
    """Test that non-image and badly-named files are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sl_dir = _create_squad_list_images(tmpdir, [
            "7_Griezmann.png",      # valid
            "abc_Player.png",       # invalid number
            "13_Oblak.json",        # non-image extension
            "readme.txt",           # no underscore, not an image
            "19.png",               # no underscore
        ])
        output = os.path.join(tmpdir, "squad.json")
        result = generate_squad_json(sl_dir, output)

        assert result is not None
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["home_team"]["players"]) == 1
        assert data["home_team"]["players"][0]["number"] == 7
