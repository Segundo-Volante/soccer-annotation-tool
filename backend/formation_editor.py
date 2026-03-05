"""Formation editor logic — pure functions for building and validating formations.

Provides helpers for the Formation Editor dialog: generating defender/striker
positions, validating formation configurations, and building formation slot
structures for player assignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.models import Player


# ── Position constants ──

DEF_POSITIONS = {"CB", "LB", "RB", "LWB", "RWB"}
MID_POSITIONS = {"CDM", "CM", "CAM", "LM", "RM", "LW", "RW"}
STR_POSITIONS = {"ST", "CF"}

# Available midfielder choices for the pitch grid
MIDFIELDER_CHOICES = ["CDM", "CM", "CAM", "LM", "RM", "LW", "RW"]


@dataclass
class FormationSlot:
    """A single position slot in the formation."""

    position: str           # e.g. "LB", "CDM", "ST"
    row_group: str          # "gk", "defense", "midfield", "forward"
    player: Optional[Player] = None  # assigned player


def generate_defender_positions(count: int) -> list[str]:
    """Generate defender position codes based on count.

    Args:
        count: Number of defenders (3, 4, or 5).

    Returns:
        List of position codes sorted left-to-right.

    Examples::

        generate_defender_positions(3) → ["CB", "CB", "CB"]
        generate_defender_positions(4) → ["LB", "CB", "CB", "RB"]
        generate_defender_positions(5) → ["LB", "CB", "CB", "CB", "RB"]
    """
    if count == 3:
        return ["CB", "CB", "CB"]
    if count == 4:
        return ["LB", "CB", "CB", "RB"]
    if count == 5:
        return ["LB", "CB", "CB", "CB", "RB"]
    # Fallback for unusual counts: center-backs with optional fullbacks
    if count <= 2:
        return ["CB"] * count
    # count >= 6: LB + (count-2)*CB + RB
    return ["LB"] + ["CB"] * (count - 2) + ["RB"]


def generate_striker_positions(count: int) -> list[str]:
    """Generate striker position codes.

    Always returns ``count`` copies of ``"ST"``.
    """
    return ["ST"] * count


def validate_formation_config(
    def_count: int,
    mid_count: int,
    str_count: int,
) -> tuple[bool, str]:
    """Validate that a formation configuration is valid.

    Checks:
    - def_count + mid_count + str_count == 10
    - def_count in [3, 5]
    - str_count in [1, 3]
    - mid_count >= 1

    Returns:
        ``(is_valid, error_message)``
    """
    total = def_count + mid_count + str_count
    if total != 10:
        return False, f"Total must be 10, got {total}"
    if def_count < 3 or def_count > 5:
        return False, f"Defenders must be 3-5, got {def_count}"
    if str_count < 1 or str_count > 3:
        return False, f"Strikers must be 1-3, got {str_count}"
    if mid_count < 1:
        return False, f"Need at least 1 midfielder, got {mid_count}"
    return True, ""


def expand_mid_positions(mid_counts: dict[str, int]) -> list[str]:
    """Expand a position→count mapping into a flat list.

    Args:
        mid_counts: e.g. ``{"CDM": 2, "CAM": 1, "LW": 1, "RW": 1}``

    Returns:
        Flat list: ``["CDM", "CDM", "CAM", "LW", "RW"]``
    """
    positions: list[str] = []
    for pos, count in mid_counts.items():
        positions.extend([pos] * count)
    return positions


def build_formation_slots(
    def_count: int,
    mid_positions: list[str],
    str_count: int,
) -> list[FormationSlot]:
    """Build the full list of formation slots (GK + DEF + MID + FWD).

    Args:
        def_count: Number of defenders.
        mid_positions: List of midfielder position codes.
        str_count: Number of strikers.

    Returns:
        List of FormationSlot objects in order: GK, defenders, midfielders, strikers.
    """
    slots: list[FormationSlot] = []

    # GK
    slots.append(FormationSlot(position="GK", row_group="gk"))

    # Defenders
    for pos in generate_defender_positions(def_count):
        slots.append(FormationSlot(position=pos, row_group="defense"))

    # Midfielders
    for pos in mid_positions:
        slots.append(FormationSlot(position=pos, row_group="midfield"))

    # Strikers
    for pos in generate_striker_positions(str_count):
        slots.append(FormationSlot(position=pos, row_group="forward"))

    return slots


def try_auto_fill_from_squad(
    players: list[Player],
) -> tuple[Optional[int], Optional[int], Optional[dict[str, int]], dict[str, list[Player]]]:
    """Try to detect formation structure from existing player positions.

    Examines the players' position fields and tries to determine:
    - Defender count
    - Striker count
    - Midfielder position counts
    - Player-to-position-group mapping

    Returns:
        ``(def_count, str_count, mid_counts, group_players)``
        or ``(None, None, None, {})`` if not enough data.

        ``group_players`` maps ``"gk"/"defense"/"midfield"/"forward"``
        to the list of players with matching positions.
    """
    group_players: dict[str, list[Player]] = {
        "gk": [],
        "defense": [],
        "midfield": [],
        "forward": [],
    }

    for p in players:
        pos = p.position.upper() if p.position else ""
        if pos == "GK":
            group_players["gk"].append(p)
        elif pos in DEF_POSITIONS:
            group_players["defense"].append(p)
        elif pos in MID_POSITIONS:
            group_players["midfield"].append(p)
        elif pos in STR_POSITIONS:
            group_players["forward"].append(p)

    def_count = len(group_players["defense"])
    str_count = len(group_players["forward"])
    mid_players = group_players["midfield"]
    mid_count = len(mid_players)

    # Check if we have a valid formation
    total = def_count + mid_count + str_count
    if total != 10:
        return None, None, None, {}
    if def_count < 3 or def_count > 5:
        return None, None, None, {}
    if str_count < 1 or str_count > 3:
        return None, None, None, {}

    # Build mid_counts from actual positions
    mid_counts: dict[str, int] = {}
    for p in mid_players:
        pos = p.position.upper()
        mid_counts[pos] = mid_counts.get(pos, 0) + 1

    return def_count, str_count, mid_counts, group_players
