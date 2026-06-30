"""Tests for the FIFA Annex C third-place seeding fix.

Background
----------
The Round-of-32 matches that pit a group winner against one of the eight best
third-placed teams must follow FIFA's pre-published "Annex C" combination table
(all 495 possible combinations of which eight groups produce a qualifying
third). Several different assignments can all satisfy the per-slot allowed-group
constraints (``3rd(A/B/C/D/F)`` …), so a plain constraint search can pick a
*valid but wrong* bracket.

For the real tournament the qualifying third-place groups are
``{B, D, E, F, I, J, K, L}`` and the official pairings are::

    1A (MEX) vs 3E (ECU)  -> M79
    1B (SUI) vs 3J (ALG)  -> M85
    1D (USA) vs 3B (BIH)  -> M81
    1E (GER) vs 3D (PAR)  -> M74
    1G (BEL) vs 3I (SEN)  -> M82
    1I (FRA) vs 3F (SWE)  -> M77
    1K (COL) vs 3L (GHA)  -> M87
    1L (ENG) vs 3K (COD)  -> M80

The pre-fix builder rotated four thirds (M74 BIH, M77 PAR, M81 ALG, M85 SWE),
which left the already-played GER-PAR octavo (the M74 fixture read {GER, BIH})
unmatched by ``reconcile_results`` and stuck on ``match_id: null``.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import update_qualified as uq  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
ANNEX_C_PATH = os.path.join(BASE_DIR, "data", "annex_c_third_place.json")
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")

# Real tournament combination and its official Annex C pairings.
REAL_THIRD_GROUPS = sorted("BDEFIJKL")
# Group-winner slot label -> group whose third-placed team plays there.
EXPECTED_SLOT_TO_GROUP = {
    "1A": "E", "1B": "J", "1D": "B", "1E": "D",
    "1G": "I", "1I": "F", "1K": "L", "1L": "K",
}
# Round-of-32 match_id -> group whose third-placed team plays there.
EXPECTED_MATCH_TO_GROUP = {
    "79": "E", "85": "J", "81": "B", "74": "D",
    "82": "I", "77": "F", "87": "L", "80": "K",
}
# The eight group-winner R32 slots that host a third-placed team -> match_id.
SLOT_LABEL_MATCH_ID = {
    "1A": 79, "1B": 85, "1D": 81, "1E": 74,
    "1G": 82, "1I": 77, "1K": 87, "1L": 80,
}


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Annex C data file integrity
# --------------------------------------------------------------------------- #

def test_annex_c_file_has_all_495_combinations():
    data = _load_json(ANNEX_C_PATH)
    combos = data["combinations"]
    assert len(combos) == 495
    assert data["_slot_order"] == ["1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"]


def test_annex_c_every_combination_is_a_valid_bijection():
    combos = _load_json(ANNEX_C_PATH)["combinations"]
    for key, row in combos.items():
        # Key is 8 distinct sorted group letters.
        assert len(key) == 8
        assert list(key) == sorted(key)
        # Exactly the 8 group-winner slots are filled.
        assert set(row.keys()) == {"1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"}
        # The assigned third-groups are exactly the qualifying groups (bijection):
        # every qualifying group is used once, no group from outside the set.
        assert sorted(row.values()) == sorted(key)


def test_annex_c_real_combination_row():
    combos = _load_json(ANNEX_C_PATH)["combinations"]
    assert combos["".join(REAL_THIRD_GROUPS)] == EXPECTED_SLOT_TO_GROUP


# --------------------------------------------------------------------------- #
# assign_third_slots on the real bracket uses Annex C verbatim
# --------------------------------------------------------------------------- #

def test_assign_third_slots_matches_annex_c_on_real_bracket():
    tournament = _load_json(TOURNAMENT_PATH)
    bracket = tournament["knockout_bracket"]
    assignment = uq.assign_third_slots(bracket, REAL_THIRD_GROUPS)
    assert assignment == EXPECTED_MATCH_TO_GROUP


def test_germany_third_place_opponent_is_group_D_not_group_B():
    """Regression: the M74 (1E) slot must take group D's third (PAR), not B (BIH)."""
    tournament = _load_json(TOURNAMENT_PATH)
    bracket = tournament["knockout_bracket"]
    assignment = uq.assign_third_slots(bracket, REAL_THIRD_GROUPS)
    assert assignment["74"] == "D"      # Paraguay's group
    assert assignment["74"] != "B"      # not Bosnia & Herzegovina's group


def test_annex_c_assignment_respects_each_slot_constraint():
    """Sanity: FIFA's pairings still satisfy the bracket's allowed-group lists."""
    tournament = _load_json(TOURNAMENT_PATH)
    bracket = tournament["knockout_bracket"]
    allowed_by_mid = {}
    for m in bracket:
        allowed = uq._allowed_groups(m.get("away_slot")) or uq._allowed_groups(m.get("home_slot"))
        if allowed:
            allowed_by_mid[str(m["match_id"])] = set(allowed)
    assignment = uq.assign_third_slots(bracket, REAL_THIRD_GROUPS)
    for mid, grp in assignment.items():
        assert grp in allowed_by_mid[mid], f"M{mid} got {grp} outside {allowed_by_mid[mid]}"


# --------------------------------------------------------------------------- #
# Resolved tournament.json reflects the official R32 third-place pairings
# --------------------------------------------------------------------------- #

def test_resolved_bracket_r32_third_place_pairings():
    tournament = _load_json(TOURNAMENT_PATH)
    qualified = tournament["qualified"]
    by_group = qualified["by_group"]

    # Map the 8 group-winner slots to {winner_team, third_team} expected pairs.
    expected_pairs = {}
    for slot_label, third_grp in EXPECTED_SLOT_TO_GROUP.items():
        winner_grp = slot_label[1]            # "1E" -> "E"
        winner = by_group[winner_grp]["1st"]
        third = by_group[third_grp]["3rd"]
        expected_pairs[SLOT_LABEL_MATCH_ID[slot_label]] = {winner, third}

    bracket = {m["match_id"]: m for m in tournament["knockout_bracket"]}
    for mid, expected in expected_pairs.items():
        got = {bracket[mid]["home_team"], bracket[mid]["away_team"]}
        assert got == expected, f"M{mid}: expected {expected}, got {got}"

    # Spot-check the marquee fixture explicitly.
    assert {bracket[74]["home_team"], bracket[74]["away_team"]} == {"GER", "PAR"}


# --------------------------------------------------------------------------- #
# The played GER-PAR result reconciles onto M74 (the whole point of the fix)
# --------------------------------------------------------------------------- #

def _find_result(team_pair):
    for filepath in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        data = _load_json(filepath)
        matches = data if isinstance(data, list) else data.get("matches", [])
        for m in matches:
            if {m.get("home_team"), m.get("away_team")} == team_pair:
                return m
    return None


def test_ger_par_result_is_reconciled_to_match_74():
    res = _find_result({"GER", "PAR"})
    assert res is not None, "GER-PAR result not found"
    assert res["match_id"] == 74
    assert res["stage"] == "R32"
    # Orientation matches the bracket fixture (winner slot 1E is home).
    assert res["home_team"] == "GER"
    assert res["away_team"] == "PAR"


# --------------------------------------------------------------------------- #
# The constraint-satisfaction fallback still works for synthetic brackets
# --------------------------------------------------------------------------- #

def test_fallback_used_when_bracket_lacks_real_winner_labels():
    # Synthetic bracket with placeholder winner slots ("1X") -> Annex C cannot
    # be indexed, so the deterministic backtracking fallback fills the slots.
    constraints = {
        "74": "A/B/C/D/F", "77": "C/D/F/G/H", "79": "C/E/F/H/I", "80": "E/H/I/J/K",
        "81": "B/E/F/I/J", "82": "A/E/H/I/J", "85": "E/F/G/I/J", "87": "D/E/I/J/L",
    }
    bracket = [
        {"match_id": int(mid), "home_slot": "1X", "away_slot": f"3rd({groups})"}
        for mid, groups in constraints.items()
    ]
    groups = list("BDEFIJKL")
    assignment = uq.assign_third_slots(bracket, groups)
    assert len(assignment) == 8
    assert sorted(assignment.values()) == groups            # bijection
    for mid, grp in assignment.items():
        assert grp in constraints[mid].split("/")            # respects constraints
