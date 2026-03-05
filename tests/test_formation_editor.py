"""Tests for backend/formation_editor.py and derive_formation_string()."""

import json
import pytest
from pathlib import Path

from backend.models import Player
from backend.squad_loader import TeamSquad, SquadData, save_squad_json, load_squad_json
from backend.formation_utils import derive_formation_string, parse_formation
from backend.formation_editor import (
    generate_defender_positions,
    generate_striker_positions,
    validate_formation_config,
    expand_mid_positions,
    build_formation_slots,
    try_auto_fill_from_squad,
)


# ═══════════════════════════════════════════════════════════
#  derive_formation_string
# ═══════════════════════════════════════════════════════════


class TestDeriveFormationString:
    """Tests for derive_formation_string()."""

    def test_442_flat_midfield(self):
        result = derive_formation_string(4, ["LM", "CM", "CM", "RM"], 2)
        assert result == "4-4-2"

    def test_4231_two_depth_levels(self):
        result = derive_formation_string(4, ["CDM", "CDM", "LW", "CAM", "RW"], 1)
        assert result == "4-2-3-1"

    def test_4141_cdm_plus_flat_mid(self):
        result = derive_formation_string(4, ["CDM", "LM", "CM", "CM", "RM"], 1)
        assert result == "4-1-4-1"

    def test_433_three_strikers(self):
        result = derive_formation_string(4, ["CM", "CM", "CM"], 3)
        assert result == "4-3-3"

    def test_352_single_mid_row(self):
        result = derive_formation_string(3, ["LM", "CM", "CM", "CM", "RM"], 2)
        assert result == "3-5-2"

    def test_3_depth_levels(self):
        # CDM + CM,CM + CAM,LW,RW → 3-1-2-3-1
        result = derive_formation_string(3, ["CDM", "CM", "CM", "CAM", "LW", "RW"], 1)
        assert result == "3-1-2-3-1"

    def test_all_cam_depth2(self):
        result = derive_formation_string(4, ["CAM", "CAM", "CAM"], 3)
        assert result == "4-3-3"

    def test_all_cdm_depth0(self):
        result = derive_formation_string(5, ["CDM", "CDM", "CDM"], 2)
        assert result == "5-3-2"

    def test_derived_formation_is_parseable(self):
        """Every derived formation string should be valid for parse_formation()."""
        test_cases = [
            (4, ["LM", "CM", "CM", "RM"], 2),
            (4, ["CDM", "CDM", "LW", "CAM", "RW"], 1),
            (3, ["CDM", "CM", "CM", "CAM", "LW", "RW"], 1),
            (5, ["CM", "CM", "CM"], 2),
            (4, ["CM", "CM", "CM", "CM", "CM", "CM"], 0),  # extreme: 4-6-0 → invalid
        ]
        for def_count, mid_pos, str_count in test_cases:
            result = derive_formation_string(def_count, mid_pos, str_count)
            total = def_count + len(mid_pos) + str_count
            if total == 10:
                parsed = parse_formation(result)
                assert parsed != [], f"Failed to parse {result}"
                assert sum(parsed) == 10


# ═══════════════════════════════════════════════════════════
#  generate_defender_positions
# ═══════════════════════════════════════════════════════════


class TestGenerateDefenderPositions:
    """Tests for generate_defender_positions()."""

    def test_3_defenders(self):
        assert generate_defender_positions(3) == ["CB", "CB", "CB"]

    def test_4_defenders(self):
        assert generate_defender_positions(4) == ["LB", "CB", "CB", "RB"]

    def test_5_defenders(self):
        assert generate_defender_positions(5) == ["LB", "CB", "CB", "CB", "RB"]

    def test_2_defenders_edge(self):
        assert generate_defender_positions(2) == ["CB", "CB"]

    def test_6_defenders_edge(self):
        result = generate_defender_positions(6)
        assert result[0] == "LB"
        assert result[-1] == "RB"
        assert len(result) == 6


# ═══════════════════════════════════════════════════════════
#  generate_striker_positions
# ═══════════════════════════════════════════════════════════


class TestGenerateStrikerPositions:
    def test_1_striker(self):
        assert generate_striker_positions(1) == ["ST"]

    def test_2_strikers(self):
        assert generate_striker_positions(2) == ["ST", "ST"]

    def test_3_strikers(self):
        assert generate_striker_positions(3) == ["ST", "ST", "ST"]


# ═══════════════════════════════════════════════════════════
#  validate_formation_config
# ═══════════════════════════════════════════════════════════


class TestValidateFormationConfig:

    def test_valid_442(self):
        ok, msg = validate_formation_config(4, 4, 2)
        assert ok
        assert msg == ""

    def test_valid_352(self):
        ok, msg = validate_formation_config(3, 5, 2)
        assert ok

    def test_valid_541(self):
        ok, msg = validate_formation_config(5, 4, 1)
        assert ok

    def test_total_not_10(self):
        ok, msg = validate_formation_config(4, 4, 3)
        assert not ok
        assert "11" in msg or "Total" in msg

    def test_def_too_low(self):
        ok, msg = validate_formation_config(2, 6, 2)
        assert not ok

    def test_def_too_high(self):
        ok, msg = validate_formation_config(6, 3, 1)
        assert not ok

    def test_str_too_low(self):
        ok, msg = validate_formation_config(4, 6, 0)
        assert not ok

    def test_str_too_high(self):
        ok, msg = validate_formation_config(3, 3, 4)
        assert not ok


# ═══════════════════════════════════════════════════════════
#  expand_mid_positions
# ═══════════════════════════════════════════════════════════


class TestExpandMidPositions:

    def test_simple(self):
        result = expand_mid_positions({"CDM": 2, "CAM": 1})
        assert sorted(result) == ["CAM", "CDM", "CDM"]

    def test_empty(self):
        assert expand_mid_positions({}) == []

    def test_single(self):
        assert expand_mid_positions({"CM": 3}) == ["CM", "CM", "CM"]


# ═══════════════════════════════════════════════════════════
#  build_formation_slots
# ═══════════════════════════════════════════════════════════


class TestBuildFormationSlots:

    def test_442_slots(self):
        slots = build_formation_slots(4, ["LM", "CM", "CM", "RM"], 2)
        assert len(slots) == 11
        assert slots[0].position == "GK"
        assert slots[0].row_group == "gk"
        # Defenders
        def_slots = [s for s in slots if s.row_group == "defense"]
        assert len(def_slots) == 4
        # Midfielders
        mid_slots = [s for s in slots if s.row_group == "midfield"]
        assert len(mid_slots) == 4
        # Forwards
        fwd_slots = [s for s in slots if s.row_group == "forward"]
        assert len(fwd_slots) == 2

    def test_4231_slots(self):
        slots = build_formation_slots(4, ["CDM", "CDM", "LW", "CAM", "RW"], 1)
        assert len(slots) == 11
        mid_slots = [s for s in slots if s.row_group == "midfield"]
        assert len(mid_slots) == 5
        mid_positions = sorted(s.position for s in mid_slots)
        assert mid_positions == ["CAM", "CDM", "CDM", "LW", "RW"]


# ═══════════════════════════════════════════════════════════
#  try_auto_fill_from_squad
# ═══════════════════════════════════════════════════════════


class TestTryAutoFillFromSquad:

    def test_full_442_squad(self):
        players = [
            Player(1, "GK", "GK"),
            Player(2, "RB", "RB"), Player(3, "CB1", "CB"),
            Player(4, "CB2", "CB"), Player(5, "LB", "LB"),
            Player(6, "RM", "RM"), Player(7, "CM1", "CM"),
            Player(8, "CM2", "CM"), Player(9, "LM", "LM"),
            Player(10, "ST1", "ST"), Player(11, "ST2", "ST"),
        ]
        def_count, str_count, mid_counts, groups = try_auto_fill_from_squad(players)
        assert def_count == 4
        assert str_count == 2
        assert mid_counts == {"RM": 1, "CM": 2, "LM": 1}
        assert len(groups["gk"]) == 1
        assert len(groups["defense"]) == 4
        assert len(groups["midfield"]) == 4
        assert len(groups["forward"]) == 2

    def test_no_positions(self):
        players = [Player(i, f"P{i}", "") for i in range(1, 12)]
        def_count, str_count, mid_counts, groups = try_auto_fill_from_squad(players)
        assert def_count is None  # can't auto-fill

    def test_partial_positions(self):
        players = [
            Player(1, "GK", "GK"),
            Player(2, "CB", "CB"),
            Player(3, "P3", ""),  # missing
        ]
        def_count, str_count, mid_counts, groups = try_auto_fill_from_squad(players)
        assert def_count is None  # total != 10


# ═══════════════════════════════════════════════════════════
#  save_squad_json
# ═══════════════════════════════════════════════════════════


class TestSaveSquadJson:

    def test_round_trip(self, tmp_path):
        """Save and reload should produce the same data."""
        squad = SquadData()
        squad.home_team = TeamSquad(
            name="Test FC",
            formation="4-4-2",
            players=[
                Player(1, "GK1", "GK"),
                Player(2, "CB1", "CB"),
            ],
        )
        path = tmp_path / "squad.json"
        save_squad_json(path, squad)

        loaded = load_squad_json(path)
        assert loaded is not None
        assert loaded.home_team.name == "Test FC"
        assert loaded.home_team.formation == "4-4-2"
        assert len(loaded.home_team.players) == 2
        assert loaded.home_team.players[0].position == "GK"

    def test_preserves_extra_fields(self, tmp_path):
        """Extra fields like 'appeared' should be preserved."""
        path = tmp_path / "squad.json"
        # Write initial data with extra field
        initial = {
            "home_team": {
                "name": "Test FC",
                "formation": "",
                "players": [
                    {"number": 1, "name": "GK1", "position": "", "appeared": True},
                    {"number": 2, "name": "CB1", "position": "", "appeared": False},
                ],
            }
        }
        path.write_text(json.dumps(initial), encoding="utf-8")

        # Load, update, save
        squad = load_squad_json(path)
        squad.home_team.formation = "4-4-2"
        squad.home_team.players[0].position = "GK"
        save_squad_json(path, squad)

        # Verify extra fields preserved
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["home_team"]["formation"] == "4-4-2"
        assert data["home_team"]["players"][0]["position"] == "GK"
        assert data["home_team"]["players"][0]["appeared"] is True
        assert data["home_team"]["players"][1]["appeared"] is False

    def test_preserves_away_team(self, tmp_path):
        """Away team data should be preserved when saving."""
        path = tmp_path / "squad.json"
        initial = {
            "home_team": {
                "name": "Home FC",
                "formation": "",
                "players": [{"number": 1, "name": "GK1", "position": ""}],
            },
            "away_team": {
                "name": "Away FC",
                "players": [{"number": 1, "name": "GK2", "position": "GK"}],
            },
        }
        path.write_text(json.dumps(initial), encoding="utf-8")

        squad = load_squad_json(path)
        squad.home_team.formation = "4-4-2"
        save_squad_json(path, squad)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "away_team" in data
        assert data["away_team"]["name"] == "Away FC"
