"""Formation parsing and player-to-position mapping utilities.

Parses formation strings (e.g. "4-4-2") into row structures, classifies
players by their positional code, and assigns them to formation slots for
the Formation View display in the Squad Sheet panel.
"""

from __future__ import annotations

from backend.models import Player
from backend.squad_loader import TeamSquad


# ── Position → row classification ──

POSITION_TO_ROW: dict[str, str] = {
    "GK": "gk",
    # Defenders
    "RB": "defense", "CB": "defense", "LB": "defense",
    "RWB": "defense", "LWB": "defense",
    # Midfielders
    "CDM": "midfield", "CM": "midfield", "CAM": "midfield",
    "RM": "midfield", "LM": "midfield",
    "RW": "midfield", "LW": "midfield",
    # Forwards
    "ST": "forward", "CF": "forward",
}

# Lateral sort order within a row: left → center → right
_LATERAL_ORDER: dict[str, int] = {
    # Left = 0
    "LB": 0, "LWB": 0, "LM": 0, "LW": 0,
    # Center = 1
    "GK": 1, "CB": 1, "CDM": 1, "CM": 1, "CAM": 1, "CF": 1, "ST": 1,
    # Right = 2
    "RB": 2, "RWB": 2, "RM": 2, "RW": 2,
}

# Depth order within midfield: defensive mids → central → attacking mids
# Used to distribute midfield players across multiple midfield rows
# (e.g. in 4-2-3-1: first midfield row gets CDMs, second gets CAM/RW/LW)
_DEPTH_ORDER: dict[str, int] = {
    "CDM": 0,
    "CM": 1, "RM": 1, "LM": 1,
    "CAM": 2, "RW": 2, "LW": 2,
}

SUPPORTED_FORMATIONS = [
    "4-4-2", "4-3-3", "4-2-3-1", "3-5-2", "3-4-3",
    "5-3-2", "5-4-1", "4-1-4-1", "4-5-1", "4-4-1-1", "3-4-1-2",
]


def derive_formation_string(
    def_count: int,
    mid_positions: list[str],
    str_count: int,
) -> str:
    """Derive a formation string from defender count, midfielder positions, and striker count.

    Groups midfielders by ``_DEPTH_ORDER`` depth level; each non-empty group
    becomes one formation segment between the defense and forward segments.

    Examples::

        derive_formation_string(4, ["CDM","CDM","LW","CAM","RW"], 1) → "4-2-3-1"
        derive_formation_string(4, ["LM","CM","CM","RM"], 2)         → "4-4-2"
        derive_formation_string(4, ["CDM","LM","CM","CM","RM"], 2)   → "4-1-4-2"
        derive_formation_string(3, ["CDM","CM","CM","CAM","LW","RW"], 1) → "3-1-2-3-1"

    Returns:
        Formation string like ``"4-2-3-1"``.
    """
    # Group midfielders by depth
    depth_groups: dict[int, list[str]] = {}
    for pos in mid_positions:
        depth = _DEPTH_ORDER.get(pos.upper(), 1)  # default to CM depth
        depth_groups.setdefault(depth, []).append(pos)

    # Build segments: defense + midfield depth groups (sorted) + forward
    segments: list[int] = [def_count]
    for depth_key in sorted(depth_groups.keys()):
        segments.append(len(depth_groups[depth_key]))
    segments.append(str_count)

    return "-".join(str(s) for s in segments)


def parse_formation(formation_str: str) -> list[int]:
    """Parse a formation string like ``"4-4-2"`` into row sizes.

    Returns a list of integers from defense to forward.
    The GK row is implicit (always 1) and **not** included.

    Examples::

        parse_formation("4-4-2")   → [4, 4, 2]
        parse_formation("4-2-3-1") → [4, 2, 3, 1]
        parse_formation("")        → []

    Returns an empty list for invalid/empty strings.
    """
    s = formation_str.strip()
    if not s:
        return []
    parts = s.split("-")
    try:
        rows = [int(p) for p in parts]
    except ValueError:
        return []
    if not rows or any(r < 0 for r in rows):
        return []
    if sum(rows) != 10:
        return []
    return rows


def assign_players_to_formation(
    team: TeamSquad,
) -> tuple[list[list[Player]], list[Player]]:
    """Assign players to formation rows based on position and formation string.

    Returns:
        ``(formation_rows, substitutes)``

        *formation_rows*: list of lists.  Index 0 is the GK row (max 1 player),
        indices 1‥N correspond to defense→forward rows from the formation string.
        Each inner list is sorted left → centre → right.

        *substitutes*: players that don't fit into the starting-XI slots.
    """
    row_sizes = parse_formation(team.formation)
    if not row_sizes:
        return [], list(team.players)

    # Bucket players by positional row
    buckets: dict[str, list[Player]] = {
        "gk": [], "defense": [], "midfield": [], "forward": [],
    }

    for player in team.players:
        row_name = POSITION_TO_ROW.get(player.position.upper(), "") if player.position else ""
        if row_name:
            buckets[row_name].append(player)
        # players with no/unknown position are NOT bucketed → become subs

    # Sort each bucket.
    # - Midfield: by depth (CDM first → CM → CAM/RW/LW), then lateral, then jersey
    #   This ensures CDMs go to the first midfield row in formations like 4-2-3-1.
    # - Other rows: by lateral (left → centre → right), then jersey number
    for key in buckets:
        if key == "midfield":
            buckets[key].sort(
                key=lambda p: (
                    _DEPTH_ORDER.get(p.position.upper(), 1),
                    _LATERAL_ORDER.get(p.position.upper(), 1),
                    p.jersey_number,
                )
            )
        else:
            buckets[key].sort(
                key=lambda p: (_LATERAL_ORDER.get(p.position.upper(), 1), p.jersey_number)
            )

    # Map each formation segment to a position bucket name
    row_names = _formation_row_names(row_sizes)

    # Build formation rows, starting with GK
    used: set[int] = set()  # track by jersey_number (assumed unique per team)

    gk_row = buckets["gk"][:1]
    for p in gk_row:
        used.add(p.jersey_number)

    formation_rows: list[list[Player]] = [gk_row]

    for size, rname in zip(row_sizes, row_names):
        available = [p for p in buckets[rname] if p.jersey_number not in used]
        chosen = available[:size]
        for p in chosen:
            used.add(p.jersey_number)
        # Re-sort chosen by lateral order for left-to-right display
        chosen.sort(
            key=lambda p: (_LATERAL_ORDER.get(p.position.upper(), 1), p.jersey_number)
        )
        formation_rows.append(chosen)

    # Substitutes = everyone not placed
    substitutes = [p for p in team.players if p.jersey_number not in used]

    return formation_rows, substitutes


def _formation_row_names(row_sizes: list[int]) -> list[str]:
    """Map each formation segment to a position bucket name.

    General rule: first segment = defense, last = forward,
    everything in between = midfield.

    ``[4, 4, 2]``   → ``["defense", "midfield", "forward"]``
    ``[4, 2, 3, 1]`` → ``["defense", "midfield", "midfield", "forward"]``
    """
    n = len(row_sizes)
    if n == 0:
        return []
    if n == 1:
        return ["defense"]
    names: list[str] = []
    for i in range(n):
        if i == 0:
            names.append("defense")
        elif i == n - 1:
            names.append("forward")
        else:
            names.append("midfield")
    return names
