import json
import os
import tempfile

import pytest

from backend.project_config import ProjectConfig


@pytest.fixture
def config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project.json
        project = {
            "team_name": "Test FC",
            "season": "2024-25",
            "language": "en",
            "competitions": ["LaLiga", "UCL", "Friendly"],
            "categories": [
                {"id": 0, "key": "home_player", "label": "{home} Player", "color": "#E53935", "roster": "home"},
                {"id": 1, "key": "opponent", "label": "Opponent", "color": "#1E88E5", "roster": "opponent_auto"},
                {"id": 2, "key": "home_gk", "label": "{home} GK", "color": "#FF9800", "roster": "home"},
                {"id": 3, "key": "opponent_gk", "label": "Opponent GK", "color": "#0D47A1", "roster": "opponent_auto"},
                {"id": 4, "key": "referee", "label": "Referee", "color": "#FDD835", "roster": "none"},
                {"id": 5, "key": "ball", "label": "Ball", "color": "#43A047", "roster": "none"},
            ],
        }
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project, f)

        # Create teams directories
        teams_dir = os.path.join(tmpdir, "teams")
        os.makedirs(os.path.join(teams_dir, "opponents"), exist_ok=True)

        # Create home.json with roster pointing to a CSV
        roster_csv = os.path.join(tmpdir, "roster.csv")
        with open(roster_csv, "w") as f:
            f.write("team,season,number,name\nTest FC,2024-25,9,Test Player\n")
        home = {"team_name": "Test FC", "roster_csv": "../roster.csv"}
        with open(os.path.join(teams_dir, "home.json"), "w") as f:
            json.dump(home, f)

        # Create an opponent CSV
        opp_csv = os.path.join(teams_dir, "opponents", "Real_Madrid.csv")
        with open(opp_csv, "w") as f:
            f.write("team,season,number,name\nReal Madrid,2024-25,7,Vinicius Jr\n")

        yield tmpdir


def test_load_project_json(config_dir):
    config = ProjectConfig(config_dir)
    assert config.exists
    assert config.team_name == "Test FC"
    assert config.season == "2024-25"
    assert config.language == "en"


def test_missing_project_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ProjectConfig(tmpdir)
        assert not config.exists
        assert config.team_name == "Home Team"
        assert config.season == ""


def test_get_competitions(config_dir):
    config = ProjectConfig(config_dir)
    comps = config.get_competitions()
    assert "LaLiga" in comps
    assert "UCL" in comps
    assert len(comps) == 3


def test_placeholder_resolution(config_dir):
    config = ProjectConfig(config_dir)
    cats = config.get_resolved_categories()
    assert cats[0]["label"] == "Test FC Player"
    assert cats[2]["label"] == "Test FC GK"
    # Non-home categories unchanged
    assert cats[1]["label"] == "Opponent"
    assert cats[4]["label"] == "Referee"


def test_get_category_colors(config_dir):
    config = ProjectConfig(config_dir)
    colors = config.get_category_colors()
    assert colors[0] == "#E53935"
    assert colors[5] == "#43A047"
    assert len(colors) == 6


def test_get_category_roster_type(config_dir):
    config = ProjectConfig(config_dir)
    assert config.get_category_roster_type(0) == "home"
    assert config.get_category_roster_type(1) == "opponent_auto"
    assert config.get_category_roster_type(4) == "none"
    assert config.get_category_roster_type(99) == "none"


def test_get_home_roster_path(config_dir):
    config = ProjectConfig(config_dir)
    path = config.get_home_roster_path()
    assert path is not None
    assert path.name == "roster.csv"


def test_list_opponent_csvs(config_dir):
    config = ProjectConfig(config_dir)
    csvs = config.list_opponent_csvs()
    assert len(csvs) == 1
    assert csvs[0].stem == "Real_Madrid"


def test_get_opponent_names(config_dir):
    config = ProjectConfig(config_dir)
    names = config.get_opponent_names()
    assert "Real Madrid" in names


def test_get_opponent_roster_path(config_dir):
    config = ProjectConfig(config_dir)
    path = config.get_opponent_roster_path("Real Madrid")
    assert path is not None
    assert path.stem == "Real_Madrid"
    # Case insensitive
    assert config.get_opponent_roster_path("real madrid") is not None
    # Non-existent
    assert config.get_opponent_roster_path("Barcelona") is None
