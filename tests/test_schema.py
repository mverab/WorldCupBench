import json
import os

import jsonschema
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema", "predictions_schema.json")


def test_schema_accepts_valid_prediction():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    prediction = {
        "model": "gpt-5.5",
        "model_id": "openai/gpt-5.5",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [
            {
                "match_id": "A1",
                "probs": {"home": 0.55, "draw": 0.27, "away": 0.18},
                "predicted_result": "home",
                "predicted_score": {"home": 2, "away": 1},
            }
        ]
        * 72,
        "group_qualifiers": {
            "first_place": [
                {"team_code": "MEX", "group": "A"},
                {"team_code": "ARG", "group": "B"},
                {"team_code": "FRA", "group": "C"},
                {"team_code": "ESP", "group": "D"},
                {"team_code": "BRA", "group": "E"},
                {"team_code": "GER", "group": "F"},
                {"team_code": "ENG", "group": "G"},
                {"team_code": "POR", "group": "H"},
                {"team_code": "NED", "group": "I"},
                {"team_code": "ITA", "group": "J"},
                {"team_code": "USA", "group": "K"},
                {"team_code": "BEL", "group": "L"},
            ],
            "second_place": [
                {"team_code": "RSA", "group": "A"},
                {"team_code": "URU", "group": "B"},
                {"team_code": "CAN", "group": "C"},
                {"team_code": "CRO", "group": "D"},
                {"team_code": "COL", "group": "E"},
                {"team_code": "MAR", "group": "F"},
                {"team_code": "SEN", "group": "G"},
                {"team_code": "KOR", "group": "H"},
                {"team_code": "JPN", "group": "I"},
                {"team_code": "SUI", "group": "J"},
                {"team_code": "AUS", "group": "K"},
                {"team_code": "DEN", "group": "L"},
            ],
            "best_third_place": [
                {"team_code": "CHI", "group": "A"},
                {"team_code": "ECU", "group": "B"},
                {"team_code": "GHA", "group": "C"},
                {"team_code": "SRB", "group": "D"},
                {"team_code": "CMR", "group": "E"},
                {"team_code": "POL", "group": "F"},
                {"team_code": "IRN", "group": "G"},
                {"team_code": "TUN", "group": "H"},
            ],
        },
        "bracket": {
            "R32": [
                {
                    "match_id": "R32-1",
                    "home_team": "MEX",
                    "away_team": "RSA",
                    "probs": {"home": 0.6, "draw": 0.2, "away": 0.2},
                    "predicted_result": "home",
                    "predicted_score": {"home": 2, "away": 1},
                    "winner": "MEX",
                }
            ],
            "R16": [],
            "QF": [],
            "SF": [],
            "third_place": {
                "match_id": "3P",
                "home_team": "FRA",
                "away_team": "GER",
                "probs": {"home": 0.5, "draw": 0.25, "away": 0.25},
                "predicted_result": "home",
                "predicted_score": {"home": 2, "away": 1},
                "winner": "FRA",
            },
            "final": {
                "match_id": "F",
                "home_team": "ARG",
                "away_team": "BRA",
                "probs": {"home": 0.5, "draw": 0.25, "away": 0.25},
                "predicted_result": "home",
                "predicted_score": {"home": 2, "away": 1},
                "winner": "ARG",
            },
        },
        "champion": "ARG",
        "runner_up": "BRA",
        "third": "FRA",
        "fourth_place": "GER",
    }
    jsonschema.validate(prediction, schema)
