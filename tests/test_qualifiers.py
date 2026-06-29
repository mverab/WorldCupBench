"""Tests for scripts/qualifiers.py and score.score_qualifiers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import qualifiers as q  # noqa: E402
import score  # noqa: E402


def _tournament():
    return {
        "groups": [
            {"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]},
            {"group": "B", "teams": ["CAN", "BIH", "QAT", "SUI"]},
        ]
    }


def _match(mid, group, home, away, hs, as_):
    return {
        "match_id": mid,
        "group": group,
        "home_team": home,
        "away_team": away,
        "score": {"home": hs, "away": as_},
        "outcome": "home" if hs > as_ else ("away" if as_ > hs else "draw"),
        "stage": "GROUP_STAGE",
    }


def _full_group_a():
    # MEX wins all (9), RSA 4, KOR 3, CZE 1 — mirrors the real data.
    return [
        _match(1, "GROUP_A", "MEX", "RSA", 2, 0),
        _match(2, "GROUP_A", "KOR", "CZE", 2, 1),
        _match(3, "GROUP_A", "MEX", "KOR", 1, 0),
        _match(4, "GROUP_A", "CZE", "RSA", 1, 1),
        _match(5, "GROUP_A", "CZE", "MEX", 0, 3),
        _match(6, "GROUP_A", "RSA", "KOR", 1, 0),
    ]


def test_group_standings_points_and_order():
    matches = _full_group_a()
    out = q.compute_qualified(matches, _tournament())
    table = out["standings"]["A"]
    assert [r["team"] for r in table] == ["MEX", "RSA", "KOR", "CZE"]
    assert table[0]["points"] == 9
    assert out["by_group"]["A"] == {"1st": "MEX", "2nd": "RSA", "3rd": "KOR"}


def test_goal_difference_tiebreak():
    # Two teams tie on points; higher goal difference ranks first.
    tourn = {"groups": [{"group": "A", "teams": ["AAA", "BBB", "CCC", "DDD"]}]}
    matches = [
        _match(1, "GROUP_A", "AAA", "DDD", 5, 0),  # AAA +5
        _match(2, "GROUP_A", "BBB", "DDD", 1, 0),  # BBB +1
        _match(3, "GROUP_A", "AAA", "CCC", 0, 0),
        _match(4, "GROUP_A", "BBB", "CCC", 0, 0),
        _match(5, "GROUP_A", "CCC", "DDD", 0, 0),
        _match(6, "GROUP_A", "AAA", "BBB", 0, 0),
    ]
    out = q.compute_qualified(matches, tourn)
    table = out["standings"]["A"]
    # AAA and BBB both 5 pts; AAA has better GD.
    assert table[0]["team"] == "AAA"
    assert table[1]["team"] == "BBB"


def test_head_to_head_tiebreak():
    # All equal on points/GD/GF overall; head-to-head decides.
    tourn = {"groups": [{"group": "A", "teams": ["AAA", "BBB", "CCC", "DDD"]}]}
    matches = [
        # AAA, BBB, CCC each beat DDD by the same margin -> equal overall.
        _match(1, "GROUP_A", "AAA", "DDD", 2, 0),
        _match(2, "GROUP_A", "BBB", "DDD", 2, 0),
        _match(3, "GROUP_A", "CCC", "DDD", 2, 0),
        # Head-to-head: AAA beat BBB, BBB beat CCC, CCC beat AAA -> still cyclic,
        # but AAA>BBB>CCC by mini-table goals; make AAA dominate h2h.
        _match(4, "GROUP_A", "AAA", "BBB", 1, 0),
        _match(5, "GROUP_A", "AAA", "CCC", 1, 0),
        _match(6, "GROUP_A", "BBB", "CCC", 1, 0),
    ]
    out = q.compute_qualified(matches, tourn)
    table = out["standings"]["A"]
    assert table[0]["team"] == "AAA"  # won both h2h
    assert table[3]["team"] == "DDD"  # lost everything


def test_incomplete_group_not_qualified():
    # Only 1 match played -> group not complete -> no qualifiers.
    matches = [_match(1, "GROUP_A", "MEX", "RSA", 2, 0)]
    out = q.compute_qualified(matches, _tournament())
    assert out["all_groups_complete"] is False
    assert out["teams"] == []


QUALIFIED = {
    "teams": {"MEX", "RSA", "KOR", "SUI", "CAN", "BIH"},
    "positions": {"MEX": "1st", "RSA": "2nd", "KOR": "3rd",
                  "SUI": "1st", "CAN": "2nd", "BIH": "3rd"},
    "best_thirds": {"KOR", "BIH"},
    "ready": True,
}


def _prediction(first, second, thirds):
    return {
        "group_qualifiers": {
            "first_place": [{"team_code": t} for t in first],
            "second_place": [{"team_code": t} for t in second],
            "best_third_place": [{"team_code": t} for t in thirds],
        }
    }


def test_score_qualifiers_perfect():
    pred = _prediction(["MEX", "SUI"], ["RSA", "CAN"], ["KOR", "BIH"])
    res = score.score_qualifiers(pred, QUALIFIED)
    assert res["hits"] == 6
    assert res["with_position_bonus"] == 6
    assert res["third_place_hits"] == 2
    assert res["missed"] == []
    assert res["false_positives"] == []


def test_score_qualifiers_partial_and_false_positives():
    # Predicts QAT (did not qualify) and misses BIH; swaps a position.
    pred = _prediction(["MEX", "SUI"], ["KOR", "CAN"], ["RSA", "QAT"])
    res = score.score_qualifiers(pred, QUALIFIED)
    # predicted set: MEX, SUI, KOR, CAN, RSA, QAT
    assert res["hits"] == 5  # all but QAT qualified
    assert res["false_positives"] == ["QAT"]
    assert res["missed"] == ["BIH"]
    # MEX(1st ok), SUI(1st ok), CAN(2nd ok) -> RSA predicted 3rd but real 2nd,
    # KOR predicted 2nd but real 3rd -> position bonus = 3
    assert res["with_position_bonus"] == 3
    # KOR is a real best third and was predicted (as 2nd) -> counts as a hit;
    # third_place_hits counts real thirds the model had qualifying in any slot.
    assert res["third_place_hits"] == 1
    assert round(res["score"], 6) == round(5 / 32, 6)


def test_score_qualifiers_not_ready():
    pred = _prediction(["MEX"], ["RSA"], [])
    empty = {"teams": set(), "positions": {}, "best_thirds": set(), "ready": False}
    res = score.score_qualifiers(pred, empty)
    assert res["hits"] == 0
    assert res["score"] == 0.0
    assert res["ready"] is False



# ---------------------------------------------------------------------------
# FIFA third-place slot constraint matching
# ---------------------------------------------------------------------------

import update_qualified as uq  # noqa: E402

LETTERS = [chr(ord("A") + i) for i in range(12)]

# Official 2026 Round-of-32 slots that receive a best-third team, with the
# group combinations allowed by the FIFA bracket table.
THIRD_SLOT_CONSTRAINTS = {
    "74": ["A", "B", "C", "D", "F"],
    "77": ["C", "D", "F", "G", "H"],
    "79": ["C", "E", "F", "H", "I"],
    "80": ["E", "H", "I", "J", "K"],
    "81": ["B", "E", "F", "I", "J"],
    "82": ["A", "E", "H", "I", "J"],
    "85": ["E", "F", "G", "I", "J"],
    "87": ["D", "E", "I", "J", "L"],
}


def _det_group(letter, third_strength):
    """Deterministic complete group: t1=9pts, t2=6, t3=3 (third), t4=0.

    ``third_strength`` controls the third-placed team's goals-for / goal
    difference so thirds can be ranked deterministically across groups.
    """
    t = [f"{letter}1", f"{letter}2", f"{letter}3", f"{letter}4"]
    out = []
    n = 0

    def add(home, away, hs, as_):
        nonlocal n
        n += 1
        out.append(_match(f"{letter}{n}", f"GROUP_{letter}", home, away, hs, as_))

    add(t[0], t[1], 1, 0)
    add(t[0], t[2], 1, 0)
    add(t[0], t[3], 1, 0)
    add(t[1], t[2], 1, 0)
    add(t[1], t[3], 1, 0)
    add(t[2], t[3], third_strength, 0)  # third team's only win; controls GD
    return out


def _twelve_complete_groups():
    """Build 12 complete groups; thirds rank A (best) .. L (worst)."""
    tourn = {"groups": [{"group": g, "teams": [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]}
                        for g in LETTERS]}
    results = []
    for i, g in enumerate(LETTERS):
        results += _det_group(g, 12 - i)  # A=12 (best third) ... L=1 (worst)
    return tourn, results


def _bracket_with_third_slots():
    return [
        {"match_id": int(mid), "home_slot": "1X",
         "away_slot": f"3rd({'/'.join(groups)})"}
        for mid, groups in THIRD_SLOT_CONSTRAINTS.items()
    ]


def test_exactly_eight_best_thirds_selected():
    tourn, results = _twelve_complete_groups()
    out = q.compute_qualified(results, tourn)
    assert out["all_groups_complete"] is True
    assert len(out["best_thirds"]) == 8
    # A..H have the strongest thirds; I..L are eliminated.
    assert set(out["best_thirds"]) == {f"{g}3" for g in "ABCDEFGH"}


def test_third_slot_assignment_respects_fifa_constraints():
    tourn, results = _twelve_complete_groups()
    out = q.compute_qualified(results, tourn)

    third_groups = sorted(
        g for g, e in out["by_group"].items() if e.get("3rd") in out["best_thirds"]
    )
    assert third_groups == list("ABCDEFGH")

    bracket = _bracket_with_third_slots()
    assignment = uq.assign_third_slots(bracket, third_groups)

    # 1) Exactly the 8 third-slots are filled.
    assert len(assignment) == 8
    assert set(assignment.keys()) == set(THIRD_SLOT_CONSTRAINTS.keys())

    # 2) Each slot received a group allowed by its FIFA constraint set.
    for slot_id, group in assignment.items():
        assert group in THIRD_SLOT_CONSTRAINTS[slot_id], (
            f"slot {slot_id} got group {group} not in {THIRD_SLOT_CONSTRAINTS[slot_id]}"
        )

    # 3) Bijection: every qualifying third-group is used exactly once,
    #    no duplicates and no group left unassigned.
    used = sorted(assignment.values())
    assert used == third_groups
    assert len(set(used)) == len(used)


def test_third_slot_assignment_arbitrary_qualifying_set():
    """Any valid 8-group set must yield a complete constraint-respecting map."""
    # Pick a different qualifying set: drop A & B, keep C..J.
    third_groups = list("CDEFGHIJ")
    bracket = _bracket_with_third_slots()
    assignment = uq.assign_third_slots(bracket, third_groups)

    assert len(assignment) == 8
    for slot_id, group in assignment.items():
        assert group in THIRD_SLOT_CONSTRAINTS[slot_id]
    assert sorted(assignment.values()) == third_groups
