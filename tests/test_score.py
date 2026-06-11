"""Smoke tests for the scoring engine."""

import json
import os
import tempfile

import score


def test_score_with_manual_template_skips_unfinished_matches():
    """Manual result templates contain None scores; scoring must not crash."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        # Simulate the template fetch_results.py creates when no API key is set.
        template_path = os.path.join(results_dir, "2026-06-11.json")
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": "2026-06-11",
                    "matches": [
                        {
                            "match_id": "GS-01",
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

        # This must not raise even though the template has unfinished scores.
        leaderboard = score.generate_leaderboard(results_dir, output_path)

        # Unfinished matches are ignored, so no results are evaluated yet.
        assert leaderboard["total_results"] == 0
        assert leaderboard["total_models"] == 11
        for model in leaderboard["models"]:
            assert model["total_evaluated"] == 0
            assert model["bracket_points"] == 0


def test_score_with_real_result_computes_metrics():
    """A finished match in results should produce non-zero scores where expected."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        result_path = os.path.join(results_dir, "2026-06-11.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": "2026-06-11",
                    "matches": [
                        {
                            "match_id": "GS-01",
                            "home_team": "USA",
                            "away_team": "MEX",
                            "score": {"home": 2, "away": 1},
                            "outcome": "home",
                            "date": "2026-06-11",
                            "stage": "group_stage",
                            "group": "A",
                        }
                    ],
                },
                f,
            )

        output_path = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output_path)

        assert leaderboard["total_results"] == 1
        assert leaderboard["total_models"] == 11
        for model in leaderboard["models"]:
            assert model["total_evaluated"] == 1
