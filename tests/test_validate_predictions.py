import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate_predictions


def test_valid_prediction_passes():
    tournament = {
        "groups": [{"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]}],
        "matches": [
            {"match_id": "1", "stage": "GROUP_STAGE", "group": "A", "home_team": "MEX", "away_team": "RSA"}
        ],
    }
    prediction = {
        "model": "test",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [
            {"match_id": "1", "probs": {"home": 0.55, "draw": 0.27, "away": 0.18}}
        ],
        "group_tables": {"A": ["MEX", "RSA", "KOR", "CZE"]},
        "best_thirds": ["MEX", "RSA", "KOR", "CZE", "MEX", "RSA", "KOR", "CZE"],
        "bracket": {
            "R32": [], "R16": [], "QF": [], "SF": [],
            "third_place": "MEX",
            "final": {"winner": "MEX", "runner_up": "RSA"},
        },
        "champion": "MEX", "runner_up": "RSA", "third": "KOR",
    }
    valid, msg = validate_predictions.validate(prediction, tournament)
    assert valid, msg


def test_invalid_probs_fail():
    tournament = {
        "groups": [{"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]}],
        "matches": [{"match_id": "1", "stage": "GROUP_STAGE", "group": "A", "home_team": "MEX", "away_team": "RSA"}],
    }
    prediction = {
        "model": "test",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [
            {"match_id": "1", "probs": {"home": 0.5, "draw": 0.5, "away": 0.5}}
        ],
        "group_tables": {"A": ["MEX", "RSA", "KOR", "CZE"]},
        "best_thirds": ["MEX"] * 8,
        "bracket": {
            "R32": [], "R16": [], "QF": [], "SF": [],
            "third_place": "MEX",
            "final": {"winner": "MEX", "runner_up": "RSA"},
        },
        "champion": "MEX", "runner_up": "RSA", "third": "KOR",
    }
    valid, msg = validate_predictions.validate(prediction, tournament)
    assert not valid
    assert "probs" in msg.lower()
