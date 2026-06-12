"""Smoke tests for the scoring engine."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import score


def _make_prediction(match_id="1", probs=None):
    if probs is None:
        probs = {"home": 1.0, "draw": 0.0, "away": 0.0}
    return {
        "model": "test",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [{"match_id": match_id, "probs": probs}],
        "group_tables": {"A": ["USA", "MEX", "CAN", "CRC"]},
        "best_thirds": ["AAA"] * 8,
        "bracket": {"R32": [], "R16": [], "QF": [], "SF": [], "third_place": "USA", "final": {"winner": "USA", "runner_up": "MEX"}},
        "champion": "USA", "runner_up": "MEX", "third": "CAN",
    }


def test_score_with_manual_template_skips_unfinished_matches():
    """Manual result templates contain None scores; scoring must not crash."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        template_path = os.path.join(results_dir, "2026-06-11.json")
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": "2026-06-11",
                    "matches": [
                        {
                            "fd_id": 1,
                            "match_id": "1",
                            "home_team": "USA",
                            "away_team": "MEX",
                            "score": {"home": None, "away": None},
                            "outcome": None,
                            "date": "2026-06-11",
                            "stage": "group_stage",
                            "group": "A",
                        }
                    ],
                },
                f,
            )

        output_path = os.path.join(out_dir, "leaderboard.json")
        predictions = [_make_prediction("1")]

        leaderboard = score.generate_leaderboard(results_dir, output_path, predictions)

        assert leaderboard["total_results"] == 0
        assert leaderboard["total_models"] == 1
        assert leaderboard["models"][0]["total_evaluated"] == 0


def test_score_with_real_result_computes_metrics():
    """A finished match in results should produce non-zero scores where expected."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        result_path = os.path.join(results_dir, "2026-06-11.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-11",
                "matches": [{
                    "fd_id": 1,
                    "match_id": "1",
                    "home_team": "USA",
                    "away_team": "MEX",
                    "score": {"home": 2, "away": 1},
                    "outcome": "home",
                    "date": "2026-06-11",
                    "stage": "GROUP_STAGE",
                    "group": "A",
                }]
            }, f)

        predictions = [_make_prediction("1", {"home": 0.6, "draw": 0.2, "away": 0.2})]
        output_path = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output_path, predictions)

        assert leaderboard["total_results"] == 1
        assert leaderboard["total_models"] == 1
        assert leaderboard["models"][0]["total_evaluated"] == 1
