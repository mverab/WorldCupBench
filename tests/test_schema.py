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
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [
            {"match_id": "1", "probs": {"home": 0.55, "draw": 0.27, "away": 0.18}}
        ],
        "group_tables": {"A": ["MEX", "RSA", "KOR", "CZE"]},
        "best_thirds": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
        "bracket": {
            "R32": [{"match": "R32-1", "winner": "MEX"}],
            "R16": [],
            "QF": [],
            "SF": [],
            "third_place": "MEX",
            "final": {"winner": "MEX", "runner_up": "RSA"},
        },
        "champion": "MEX",
        "runner_up": "RSA",
        "third": "KOR",
    }
    jsonschema.validate(prediction, schema)
