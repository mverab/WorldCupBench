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
