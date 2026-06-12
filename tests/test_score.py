"""Tests for scripts/score.py."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import score


def _make_group_match(match_id="1", probs=None, predicted_result="home"):
    if probs is None:
        probs = {"home": 1.0, "draw": 0.0, "away": 0.0}
    return {
        "match_id": match_id,
        "probs": probs,
        "predicted_result": predicted_result,
        "predicted_score": {"home": 1, "away": 0},
    }


def _make_knockout_match(
    match_id="73",
    probs=None,
    winner="MEX",
    home_team="MEX",
    away_team="CAN",
    predicted_result="home",
):
    if probs is None:
        probs = {"home": 1.0, "draw": 0.0, "away": 0.0}
    return {
        "match_id": match_id,
        "home_team": home_team,
        "away_team": away_team,
        "probs": probs,
        "predicted_result": predicted_result,
        "predicted_score": {"home": 1, "away": 0},
        "winner": winner,
    }


def _make_prediction(model="test"):
    return {
        "model": model,
        "model_id": f"test/{model}",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "source_schema": "freeze-v3",
        "group_matches": [_make_group_match()],
        "group_qualifiers": {
            "first_place": [],
            "second_place": [],
            "best_third_place": [],
        },
        "bracket": {
            "R32": [],
            "R16": [],
            "QF": [],
            "SF": [],
            "third_place": _make_knockout_match("THIRD"),
            "final": _make_knockout_match("FINAL"),
        },
        "champion": "MEX",
        "runner_up": "CAN",
        "third": "RSA",
        "fourth_place": "SUI",
    }


def _write_result(results_dir, match_id, outcome, home_team, away_team, stage):
    path = os.path.join(results_dir, "2026-06-11.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": "2026-06-11",
                "matches": [
                    {
                        "fd_id": int(match_id) if match_id.isdigit() else 0,
                        "match_id": match_id,
                        "home_team": home_team,
                        "away_team": away_team,
                        "score": {"home": 1, "away": 0},
                        "outcome": outcome,
                        "stage": stage,
                    }
                ],
            },
            f,
        )


def test_skips_unfinished_matches():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": "2026-06-11",
                    "matches": [
                        {
                            "fd_id": 1,
                            "match_id": "1",
                            "home_team": "MEX",
                            "away_team": "RSA",
                            "score": {"home": None, "away": None},
                            "outcome": None,
                            "stage": "GROUP_STAGE",
                            "group": "A",
                        }
                    ],
                },
                f,
            )
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[_make_prediction()])
        assert leaderboard["models"][0]["n_matches_scored"] == 0
        assert leaderboard["models"][0]["brier_group"] == 0.0
        assert leaderboard["models"][0]["brier_knockout"] is None


def test_group_brier_three_classes():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        _write_result(results_dir, "1", "home", "MEX", "RSA", "GROUP_STAGE")
        pred = _make_prediction()
        pred["group_matches"] = [_make_group_match("1", {"home": 0.6, "draw": 0.2, "away": 0.2})]
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # (0.6-1)^2 + (0.2-0)^2 + (0.2-0)^2 = 0.16 + 0.04 + 0.04 = 0.24
        assert leaderboard["models"][0]["brier_group"] == 0.24
        assert leaderboard["models"][0]["brier_knockout"] is None
        assert leaderboard["models"][0]["brier_total"] == 0.12  # 0.24 / 2


def test_knockout_brier_bernoulli_with_winner_orientation():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        _write_result(results_dir, "73", "away", "MEX", "CAN", "ROUND_OF_32")
        pred = _make_prediction()
        pred["group_matches"] = []
        pred["bracket"]["R32"] = [
            _make_knockout_match("73", {"home": 0.6, "draw": 0.0, "away": 0.4}, winner="MEX")
        ]
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # model predicted MEX with p=0.6, real winner CAN -> y=0 -> brier=0.36
        assert leaderboard["models"][0]["brier_knockout"] == 0.36
        assert leaderboard["models"][0]["brier_group"] == 0.0
        assert leaderboard["models"][0]["brier_total"] == 0.36


def test_quiniela_points_table():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        matches = [
            {
                "fd_id": 1,
                "match_id": "1",
                "home_team": "MEX",
                "away_team": "RSA",
                "score": {"home": 1, "away": 0},
                "outcome": "home",
                "stage": "GROUP_STAGE",
            },
            {
                "fd_id": 73,
                "match_id": "73",
                "home_team": "MEX",
                "away_team": "CAN",
                "score": {"home": 1, "away": 0},
                "outcome": "home",
                "stage": "ROUND_OF_32",
            },
            {
                "fd_id": 103,
                "match_id": "THIRD",
                "home_team": "RSA",
                "away_team": "SUI",
                "score": {"home": 2, "away": 1},
                "outcome": "home",
                "stage": "THIRD_PLACE",
            },
            {
                "fd_id": 104,
                "match_id": "FINAL",
                "home_team": "MEX",
                "away_team": "CAN",
                "score": {"home": 1, "away": 0},
                "outcome": "home",
                "stage": "FINAL",
            },
        ]
        with open(os.path.join(results_dir, "2026-06-11.json"), "w", encoding="utf-8") as f:
            json.dump({"date": "2026-06-11", "matches": matches}, f)
        pred = _make_prediction()
        pred["group_matches"] = [_make_group_match("1")]
        pred["bracket"]["R32"] = [_make_knockout_match("73")]
        pred["bracket"]["third_place"] = _make_knockout_match(
            "THIRD", winner="RSA", home_team="RSA", away_team="SUI"
        )
        pred["bracket"]["final"] = _make_knockout_match("FINAL", winner="MEX")
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # group=1, R32=2, THIRD=8, FINAL=32 -> 43
        assert leaderboard["models"][0]["quiniela_points"] == 43


def test_roi_null_without_market_map():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        with open(os.path.join(results_dir, "2026-06-11.json"), "w", encoding="utf-8") as f:
            json.dump({"date": "2026-06-11", "matches": []}, f)
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[_make_prediction()])
        assert leaderboard["models"][0]["roi"] is None
        assert leaderboard["models"][0]["roi_status"] == "no_market_data"


def test_knockout_brier_null_when_winner_not_in_match():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        _write_result(results_dir, "73", "home", "MEX", "CAN", "ROUND_OF_32")
        pred = _make_prediction()
        pred["group_matches"] = []
        pred["bracket"]["R32"] = [
            _make_knockout_match("73", {"home": 0.6, "draw": 0.0, "away": 0.4}, winner="FRA")
        ]
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        assert leaderboard["models"][0]["n_matches_scored"] == 0
        assert leaderboard["models"][0]["brier_knockout"] is None
