import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate_predictions


@pytest.fixture
def tournament():
    with open(validate_predictions.TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def valid_prediction():
    path = os.path.join(
        os.path.dirname(__file__), "..", "predictions", "pre-tournament", "gpt-5.5_prediction.json"
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_valid_prediction_passes(valid_prediction, tournament):
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert valid, msg


def test_invalid_probs_fail(valid_prediction, tournament):
    valid_prediction["group_matches"][0]["probs"] = {
        "home": 0.5,
        "draw": 0.5,
        "away": 0.5,
    }
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert not valid
    assert "probs" in msg.lower()


def test_knockout_draw_prob_must_be_zero(valid_prediction, tournament):
    valid_prediction["bracket"]["R32"][0]["probs"]["draw"] = 0.1
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert not valid
    assert "draw" in msg.lower()


def test_group_qualifiers_group_mismatch_fails(valid_prediction, tournament):
    valid_prediction["group_qualifiers"]["first_place"][0]["group"] = "Z"
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert not valid


def test_invalid_tla_in_qualifiers_fails(valid_prediction, tournament):
    valid_prediction["group_qualifiers"]["first_place"][0]["team_code"] = "XXX"
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert not valid
    assert "invalid" in msg.lower()


def test_winner_must_be_in_match(valid_prediction, tournament):
    valid_prediction["bracket"]["R32"][0]["winner"] = "FRA"
    valid, msg = validate_predictions.validate(valid_prediction, tournament)
    assert not valid
    assert "winner" in msg.lower()
