# WorldCupBench Scoring & Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reemplazar `src/score.py` por `scripts/score.py`, actualizar el schema y la validación al formato freeze-v3 (`group_qualifiers`), y migrar los tests correspondientes.

**Architecture:** Un único script de scoring (`scripts/score.py`) con funciones puras y testables. Validación estructural (`jsonschema`) + semántica (`scripts/validate_predictions.py`) contra `data/tournament.json`. ROI Polymarket opcional y desacoplado. Schema actualizado para reflejar el formato real de las predicciones.

**Tech Stack:** Python 3, `jsonschema`, `pytest`, `pathlib`.

---

## Task 1: Update schema to freeze-v3

**Files:**
- Modify: `schema/predictions_schema.json`
- Test: `tests/test_schema.py` (si existe) o validación manual con las 11 predicciones

**Step 1: Backup the current schema**

```bash
cp schema/predictions_schema.json schema/predictions_schema.json.bak
```

**Step 2: Rewrite schema with group_qualifiers**

Replace the current schema with the freeze-v3 structure:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://github.com/mverab/WorldCupBench/schema/predictions_schema.json",
  "title": "WorldCupBench Predictions Schema v3",
  "description": "Prediction format using explicit 1X2 probabilities, canonical FIFA TLAs, and group_qualifiers.",
  "type": "object",
  "required": [
    "model",
    "model_id",
    "modality",
    "generated_at",
    "seed_or_temp",
    "group_matches",
    "group_qualifiers",
    "bracket",
    "champion",
    "runner_up",
    "third",
    "fourth_place"
  ],
  "properties": {
    "model": {"type": "string"},
    "model_id": {"type": "string"},
    "modality": {"enum": ["pre_tournament", "daily"]},
    "generated_at": {"type": "string", "format": "date-time"},
    "source_schema": {"type": "string"},
    "seed_or_temp": {
      "type": "object",
      "properties": {
        "temperature": {"type": "number"},
        "seed": {"type": "integer"}
      }
    },
    "group_matches": {
      "type": "array",
      "minItems": 72,
      "maxItems": 72,
      "items": {"$ref": "#/definitions/group_match"}
    },
    "group_qualifiers": {
      "type": "object",
      "required": ["first_place", "second_place", "best_third_place"],
      "properties": {
        "first_place": {
          "type": "array",
          "minItems": 12,
          "maxItems": 12,
          "items": {"$ref": "#/definitions/qualifier"}
        },
        "second_place": {
          "type": "array",
          "minItems": 12,
          "maxItems": 12,
          "items": {"$ref": "#/definitions/qualifier"}
        },
        "best_third_place": {
          "type": "array",
          "minItems": 8,
          "maxItems": 8,
          "items": {"$ref": "#/definitions/qualifier"}
        }
      }
    },
    "bracket": {"$ref": "#/definitions/bracket"},
    "champion": {"$ref": "#/definitions/tla"},
    "runner_up": {"$ref": "#/definitions/tla"},
    "third": {"$ref": "#/definitions/tla"},
    "fourth_place": {"$ref": "#/definitions/tla"}
  },
  "definitions": {
    "tla": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "qualifier": {
      "type": "object",
      "required": ["team_code", "group"],
      "properties": {
        "team_code": {"$ref": "#/definitions/tla"},
        "group": {"type": "string", "pattern": "^[A-L]$"}
      }
    },
    "group_match": {
      "type": "object",
      "required": ["match_id", "probs", "predicted_result", "predicted_score"],
      "properties": {
        "match_id": {"type": "string"},
        "probs": {"$ref": "#/definitions/probs"},
        "predicted_result": {"enum": ["home", "draw", "away"]},
        "predicted_score": {
          "type": "object",
          "required": ["home", "away"],
          "properties": {
            "home": {"type": "integer"},
            "away": {"type": "integer"}
          }
        },
        "orientation_flipped": {"type": "boolean"}
      }
    },
    "probs": {
      "type": "object",
      "required": ["home", "draw", "away"],
      "properties": {
        "home": {"type": "number", "minimum": 0, "maximum": 1},
        "draw": {"type": "number", "minimum": 0, "maximum": 1},
        "away": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "bracket": {
      "type": "object",
      "required": ["R32", "R16", "QF", "SF", "third_place", "final"],
      "properties": {
        "R32": {"$ref": "#/definitions/knockout_round"},
        "R16": {"$ref": "#/definitions/knockout_round"},
        "QF": {"$ref": "#/definitions/knockout_round"},
        "SF": {"$ref": "#/definitions/knockout_round"},
        "third_place": {"$ref": "#/definitions/knockout_match"},
        "final": {"$ref": "#/definitions/knockout_match"}
      }
    },
    "knockout_round": {
      "type": "array",
      "items": {"$ref": "#/definitions/knockout_match"}
    },
    "knockout_match": {
      "type": "object",
      "required": ["match_id", "home_team", "away_team", "probs", "predicted_result", "predicted_score", "winner"],
      "properties": {
        "match_id": {"type": "string"},
        "home_team": {"$ref": "#/definitions/tla"},
        "away_team": {"$ref": "#/definitions/tla"},
        "probs": {"$ref": "#/definitions/probs"},
        "predicted_result": {"enum": ["home", "away"]},
        "predicted_score": {
          "type": "object",
          "required": ["home", "away"],
          "properties": {
            "home": {"type": "integer"},
            "away": {"type": "integer"}
          }
        },
        "winner": {"$ref": "#/definitions/tla"},
        "orientation_flipped": {"type": "boolean"}
      }
    }
  }
}
```

**Step 3: Validate schema against all prediction files**

```bash
python -c "
import json, glob
from jsonschema import Draft7Validator
schema = json.load(open('schema/predictions_schema.json'))
validator = Draft7Validator(schema)
for path in sorted(glob.glob('predictions/pre-tournament/*_prediction.json')):
    data = json.load(open(path))
    errors = list(validator.iter_errors(data))
    print(path, 'OK' if not errors else f'ERRORS: {len(errors)}')
    for e in errors[:3]:
        print('  ', '/'.join(map(str, e.path)), e.message)
"
```

Expected: 11 files OK.

**Step 4: Commit**

```bash
git add schema/predictions_schema.json
git commit -m "feat(schema): update to freeze-v3 group_qualifiers format"
```

---

## Task 2: Rewrite validate_predictions.py

**Files:**
- Modify: `scripts/validate_predictions.py`
- Test: `tests/test_validate_predictions.py`

**Step 1: Write the new tests first**

Replace `tests/test_validate_predictions.py` with tests for the new structure:

```python
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate_predictions


@pytest.fixture
def tournament():
    return {
        "groups": [
            {"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]},
            {"group": "B", "teams": ["CAN", "BIH", "QAT", "SUI"]},
        ],
        "matches": [
            {"match_id": "1", "stage": "GROUP_STAGE", "group": "A", "home_team": "MEX", "away_team": "RSA"},
            {"match_id": "73", "stage": "ROUND_OF_32", "home_team": "MEX", "away_team": "CAN"},
        ],
    }


def _base_prediction():
    return {
        "model": "test",
        "model_id": "test/test",
        "modality": "pre_tournament",
        "generated_at": "2026-06-11T00:00:00Z",
        "seed_or_temp": {"temperature": 0.3},
        "group_matches": [
            {"match_id": "1", "probs": {"home": 0.55, "draw": 0.27, "away": 0.18},
             "predicted_result": "home", "predicted_score": {"home": 1, "away": 0}}
        ],
        "group_qualifiers": {
            "first_place": [{"team_code": "MEX", "group": "A"}, {"team_code": "CAN", "group": "B"}],
            "second_place": [{"team_code": "RSA", "group": "A"}, {"team_code": "SUI", "group": "B"}],
            "best_third_place": [{"team_code": "KOR", "group": "A"}, {"team_code": "QAT", "group": "B"}],
        },
        "bracket": {
            "R32": [{"match_id": "73", "home_team": "MEX", "away_team": "CAN",
                     "probs": {"home": 0.6, "draw": 0.0, "away": 0.4},
                     "predicted_result": "home", "predicted_score": {"home": 1, "away": 0},
                     "winner": "MEX"}],
            "R16": [], "QF": [], "SF": [],
            "third_place": {"match_id": "THIRD", "home_team": "MEX", "away_team": "CAN",
                            "probs": {"home": 0.55, "draw": 0.0, "away": 0.45},
                            "predicted_result": "home", "predicted_score": {"home": 1, "away": 0},
                            "winner": "MEX"},
            "final": {"match_id": "FINAL", "home_team": "MEX", "away_team": "CAN",
                      "probs": {"home": 0.52, "draw": 0.0, "away": 0.48},
                      "predicted_result": "home", "predicted_score": {"home": 1, "away": 0},
                      "winner": "MEX"},
        },
        "champion": "MEX", "runner_up": "CAN", "third": "RSA", "fourth_place": "SUI",
    }


def test_valid_prediction_passes(tournament):
    valid, msg = validate_predictions.validate(_base_prediction(), tournament)
    assert valid, msg


def test_invalid_probs_fail(tournament):
    pred = _base_prediction()
    pred["group_matches"][0]["probs"] = {"home": 0.5, "draw": 0.5, "away": 0.5}
    valid, msg = validate_predictions.validate(pred, tournament)
    assert not valid
    assert "probs" in msg.lower()


def test_knockout_draw_prob_must_be_zero(tournament):
    pred = _base_prediction()
    pred["bracket"]["R32"][0]["probs"]["draw"] = 0.1
    valid, msg = validate_predictions.validate(pred, tournament)
    assert not valid
    assert "draw" in msg.lower()


def test_group_qualifiers_group_mismatch_fails(tournament):
    pred = _base_prediction()
    pred["group_qualifiers"]["first_place"][0]["group"] = "B"
    valid, msg = validate_predictions.validate(pred, tournament)
    assert not valid
    assert "group" in msg.lower()


def test_invalid_tla_in_qualifiers_fails(tournament):
    pred = _base_prediction()
    pred["group_qualifiers"]["first_place"][0]["team_code"] = "XXX"
    valid, msg = validate_predictions.validate(pred, tournament)
    assert not valid
    assert "invalid" in msg.lower()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_validate_predictions.py -v
```

Expected: FAIL (old script does not match new structure).

**Step 3: Implement scripts/validate_predictions.py**

```python
"""Validate a prediction file against the schema and tournament data."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils

SCHEMA_PATH = utils.SCHEMA_PATH
TOURNAMENT_PATH = utils.TOURNAMENT_PATH


def load_prediction(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate(prediction: dict, tournament: dict) -> tuple:
    schema = utils.load_schema()

    try:
        import jsonschema
        jsonschema.validate(prediction, schema)
    except ImportError:
        pass
    except jsonschema.ValidationError as e:
        return False, f"Schema error: {e.message}"

    valid_codes = utils.get_fifa_codes(tournament)
    group_of_code = {}
    for g in tournament.get("groups", []):
        for team in g.get("teams", []):
            group_of_code[team] = g["group"]

    valid_match_ids = {}
    for m in tournament.get("matches", []):
        mid = str(m.get("match_id"))
        valid_match_ids[mid] = m

    errors = []

    def _check_fifa(code: str, context: str):
        if code not in valid_codes:
            errors.append(f"{context}: invalid TLA {code}")

    def _check_probs(match: dict, allow_draw: bool):
        probs = match.get("probs", {})
        total = probs.get("home", 0) + probs.get("draw", 0) + probs.get("away", 0)
        mid = str(match.get("match_id", "?"))
        if not (0.98 <= total <= 1.02):
            errors.append(f"{mid}: probs sum {total:.4f}")
        if not allow_draw and probs.get("draw", 0) != 0:
            errors.append(f"{mid}: knockout draw prob must be 0.0")

    # Group matches
    for gm in prediction.get("group_matches", []):
        mid = str(gm.get("match_id", "?"))
        if mid not in valid_match_ids:
            errors.append(f"{mid}: unknown group match_id")
            continue
        _check_probs(gm, allow_draw=True)

    # Group qualifiers
    gq = prediction.get("group_qualifiers") or {}
    first = gq.get("first_place") or []
    second = gq.get("second_place") or []
    third = gq.get("best_third_place") or []

    if len(first) != 12:
        errors.append(f"first_place has {len(first)} teams (expected 12)")
    if len(second) != 12:
        errors.append(f"second_place has {len(second)} teams (expected 12)")
    if len(third) != 8:
        errors.append(f"best_third_place has {len(third)} teams (expected 8)")

    for team_info in first + second + third:
        code = team_info.get("team_code", "")
        group = team_info.get("group", "")
        _check_fifa(code, f"qualifier {team_info}")
        if code in group_of_code and group_of_code[code] != group:
            errors.append(f"qualifier {code} group {group} != tournament group {group_of_code[code]}")

    # Knockout bracket
    bracket = prediction.get("bracket") or {}
    for round_key in ["R32", "R16", "QF", "SF"]:
        for m in bracket.get(round_key, []):
            _check_probs(m, allow_draw=False)
            _check_fifa(m.get("home_team", ""), str(m.get("match_id")))
            _check_fifa(m.get("away_team", ""), str(m.get("match_id")))
            if m.get("winner") not in (m.get("home_team"), m.get("away_team")):
                errors.append(f"{m.get('match_id')}: winner {m.get('winner')} not in match")

    for key in ["third_place", "final"]:
        m = bracket.get(key)
        if m:
            _check_probs(m, allow_draw=False)
            _check_fifa(m.get("home_team", ""), str(m.get("match_id")))
            _check_fifa(m.get("away_team", ""), str(m.get("match_id")))
            if m.get("winner") not in (m.get("home_team"), m.get("away_team")):
                errors.append(f"{m.get('match_id')}: winner {m.get('winner')} not in match")

    # Top-level standings
    for key in ["champion", "runner_up", "third", "fourth_place"]:
        val = prediction.get(key)
        if val:
            _check_fifa(val, key)

    if errors:
        return False, "; ".join(errors[:10])
    return True, "OK"


def main():
    parser = argparse.ArgumentParser(description="Validate a prediction file")
    parser.add_argument("prediction", help="Path to prediction JSON")
    parser.add_argument("--tournament", default=TOURNAMENT_PATH, help="Path to tournament.json")
    args = parser.parse_args()

    prediction = load_prediction(args.prediction)
    with open(args.tournament, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    valid, msg = validate(prediction, tournament)
    print(msg)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
pytest tests/test_validate_predictions.py -v
```

Expected: PASS.

**Step 5: Validate all 11 prediction files**

```bash
for f in predictions/pre-tournament/*_prediction.json; do
  python scripts/validate_predictions.py "$f";
done
```

Expected: all print `OK`.

**Step 6: Commit**

```bash
git add scripts/validate_predictions.py tests/test_validate_predictions.py
git commit -m "feat(validate): sync validation with freeze-v3 group_qualifiers"
```

---

## Task 3: Create scripts/score.py

**Files:**
- Create: `scripts/score.py`
- Test: `tests/test_score.py`

**Step 1: Write tests first**

Replace `tests/test_score.py` with:

```python
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


def _make_knockout_match(match_id="73", probs=None, winner="MEX", home_team="MEX", away_team="CAN", predicted_result="home"):
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
            "R32": [], "R16": [], "QF": [], "SF": [],
            "third_place": _make_knockout_match("THIRD"),
            "final": _make_knockout_match("FINAL"),
        },
        "champion": "MEX", "runner_up": "CAN", "third": "RSA", "fourth_place": "SUI",
    }


def test_skips_unfinished_matches():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-11",
                "matches": [{
                    "fd_id": 1, "match_id": "1", "home_team": "MEX", "away_team": "RSA",
                    "score": {"home": None, "away": None}, "outcome": None,
                    "date": "2026-06-11", "stage": "GROUP_STAGE", "group": "A",
                }]
            }, f)
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[_make_prediction()])
        assert leaderboard["models"][0]["n_matches_scored"] == 0
        assert leaderboard["models"][0]["brier_group"] == 0.0
        assert leaderboard["models"][0]["brier_knockout"] is None


def test_group_brier_three_classes():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-11",
                "matches": [{
                    "fd_id": 1, "match_id": "1", "home_team": "MEX", "away_team": "RSA",
                    "score": {"home": 2, "away": 0}, "outcome": "home",
                    "date": "2026-06-11", "stage": "GROUP_STAGE", "group": "A",
                }]
            }, f)
        pred = _make_prediction()
        pred["group_matches"][0]["probs"] = {"home": 0.6, "draw": 0.2, "away": 0.2}
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # (0.6-1)^2 + (0.2-0)^2 + (0.2-0)^2 = 0.16 + 0.04 + 0.04 = 0.24
        assert leaderboard["models"][0]["brier_group"] == 0.24
        assert leaderboard["models"][0]["brier_knockout"] is None
        assert leaderboard["models"][0]["brier_total"] == 0.12  # 0.24 / 2


def test_knockout_brier_bernoulli_with_winner_orientation():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-11",
                "matches": [{
                    "fd_id": 73, "match_id": "73", "home_team": "MEX", "away_team": "CAN",
                    "score": {"home": 0, "away": 1}, "outcome": "away",
                    "date": "2026-06-11", "stage": "ROUND_OF_32",
                }]
            }, f)
        pred = _make_prediction()
        pred["group_matches"] = []
        pred["bracket"]["R32"] = [_make_knockout_match("73", {"home": 0.6, "draw": 0.0, "away": 0.4}, winner="MEX")]
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # model predicted MEX with p=0.6, real winner CAN -> y=0 -> brier=0.36
        assert leaderboard["models"][0]["brier_knockout"] == 0.36
        assert leaderboard["models"][0]["brier_group"] == 0.0
        assert leaderboard["models"][0]["brier_total"] == 0.36


def test_quiniela_points_table():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        matches = [
            {"fd_id": 1, "match_id": "1", "home_team": "MEX", "away_team": "RSA",
             "score": {"home": 1, "away": 0}, "outcome": "home", "stage": "GROUP_STAGE", "group": "A"},
            {"fd_id": 73, "match_id": "73", "home_team": "MEX", "away_team": "CAN",
             "score": {"home": 1, "away": 0}, "outcome": "home", "stage": "ROUND_OF_32"},
            {"fd_id": 103, "match_id": "THIRD", "home_team": "RSA", "away_team": "SUI",
             "score": {"home": 2, "away": 1}, "outcome": "home", "stage": "THIRD_PLACE"},
            {"fd_id": 104, "match_id": "FINAL", "home_team": "MEX", "away_team": "CAN",
             "score": {"home": 1, "away": 0}, "outcome": "home", "stage": "FINAL"},
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": "2026-06-11", "matches": matches}, f)
        pred = _make_prediction()
        pred["group_matches"] = [_make_group_match("1")]
        pred["bracket"]["R32"] = [_make_knockout_match("73")]
        pred["bracket"]["third_place"] = _make_knockout_match("THIRD", winner="RSA", home_team="RSA", away_team="SUI")
        pred["bracket"]["final"] = _make_knockout_match("FINAL", winner="MEX")
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[pred])
        # group=1, R32=2, THIRD=8, FINAL=32 -> 43
        assert leaderboard["models"][0]["quiniela_points"] == 43


def test_roi_null_without_market_map():
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        path = os.path.join(results_dir, "2026-06-11.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": "2026-06-11", "matches": []}, f)
        output = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output, predictions=[_make_prediction()])
        assert leaderboard["models"][0]["roi"] is None
        assert leaderboard["models"][0]["roi_status"] == "no_market_data"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_score.py -v
```

Expected: FAIL (script does not exist yet).

**Step 3: Implement scripts/score.py**

Create `scripts/score.py`:

```python
"""WorldCupBench scoring engine (freeze-v3).

Reads prediction JSONs and actual results, computes per-model metrics, and
writes data/leaderboard.json.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils

BASE_DIR = utils.BASE_DIR
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
PREDICTIONS_DIR = os.path.join(utils.PREDICTIONS_DIR, "pre-tournament")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "data", "leaderboard.json")
POLYMARKET_DIR = os.path.join(BASE_DIR, "data", "polymarket")

QUINIELA_POINTS = {
    "GROUP_STAGE": 1,
    "R32": 2,
    "R16": 4,
    "QF": 8,
    "SF": 16,
    "FINAL": 32,
    "THIRD_PLACE": 8,
}


def load_results(results_dir: str = RESULTS_DIR) -> dict:
    """Load actual match results from data/results/*.json."""
    results = {}
    if not os.path.isdir(results_dir):
        return results
    for filename in sorted(os.listdir(results_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(results_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        matches = data if isinstance(data, list) else data.get("matches", [])
        for m in matches:
            if not _has_result(m):
                continue
            for key in ("fd_id", "match_id"):
                val = m.get(key)
                if val is not None:
                    results[str(val)] = m
    return results


def _has_result(match: dict) -> bool:
    outcome = match.get("outcome")
    if outcome in ("home", "draw", "away"):
        return True
    score = match.get("score", {})
    return isinstance(score.get("home"), int) and isinstance(score.get("away"), int)


def load_predictions(predictions_dir: str = PREDICTIONS_DIR) -> list:
    predictions = []
    if not os.path.isdir(predictions_dir):
        return predictions
    for filename in sorted(os.listdir(predictions_dir)):
        if not filename.endswith("_prediction.json"):
            continue
        filepath = os.path.join(predictions_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                predictions.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return predictions


def _match_stage(match_id: str) -> str:
    if match_id in ("FINAL", "THIRD"):
        return "FINAL" if match_id == "FINAL" else "THIRD_PLACE"
    try:
        mid = int(match_id)
    except (ValueError, TypeError):
        return "UNKNOWN"
    if 1 <= mid <= 72:
        return "GROUP_STAGE"
    if 73 <= mid <= 88:
        return "R32"
    if 89 <= mid <= 96:
        return "R16"
    if 97 <= mid <= 100:
        return "QF"
    if 101 <= mid <= 102:
        return "SF"
    return "UNKNOWN"


def _brier_group(probs: dict, actual: str) -> float:
    return sum((probs.get(o, 0.0) - (1.0 if o == actual else 0.0)) ** 2 for o in ("home", "draw", "away"))


def _brier_knockout(probs: dict, winner: str, home_team: str, away_team: str, actual_winner: str) -> float:
    """Bernoulli Brier for the predicted advancing team."""
    if winner == home_team:
        p = probs.get("home", 0.0)
    elif winner == away_team:
        p = probs.get("away", 0.0)
    else:
        return None
    y = 1.0 if winner == actual_winner else 0.0
    return (p - y) ** 2


def _actual_winner(result: dict) -> str:
    outcome = result.get("outcome")
    if outcome == "home":
        return result.get("home_team")
    if outcome == "away":
        return result.get("away_team")
    return None


def _score_match(pred_match: dict, result: dict, stage: str) -> dict:
    actual_outcome = result.get("outcome")
    probs = pred_match.get("probs", {})
    entry = {
        "match_id": pred_match.get("match_id"),
        "stage": stage,
        "predicted": None,
        "actual": actual_outcome,
    }

    if stage == "GROUP_STAGE":
        brier = _brier_group(probs, actual_outcome)
        predicted = pred_match.get("predicted_result")
        hit = predicted == actual_outcome
        entry.update({"brier": brier, "predicted": predicted, "hit": hit})
        return entry

    # Knockout
    winner = pred_match.get("winner")
    actual_winner = _actual_winner(result)
    if actual_winner is None:
        return None
    brier = _brier_knockout(probs, winner, pred_match.get("home_team"), pred_match.get("away_team"), actual_winner)
    hit = winner == actual_winner
    entry.update({"brier": brier, "predicted": winner, "actual": actual_winner, "hit": hit})
    return entry


def _iterate_knockout_matches(bracket: dict):
    for round_key in ("R32", "R16", "QF", "SF"):
        for m in bracket.get(round_key, []):
            yield m
    for key in ("third_place", "final"):
        m = bracket.get(key)
        if m:
            yield m


def score_model(prediction: dict, results: dict) -> dict:
    group_briers = []
    knockout_briers = []
    quiniela = 0
    n_group = 0
    n_ko = 0

    for gm in prediction.get("group_matches", []):
        mid = str(gm.get("match_id"))
        result = results.get(mid)
        if not result:
            continue
        stage = _match_stage(mid)
        scored = _score_match(gm, result, stage)
        if scored is None:
            continue
        group_briers.append(scored["brier"])
        n_group += 1
        if scored["hit"]:
            quiniela += QUINIELA_POINTS.get(stage, 0)

    for km in _iterate_knockout_matches(prediction.get("bracket", {})):
        mid = str(km.get("match_id"))
        result = results.get(mid)
        if not result:
            continue
        stage = _match_stage(mid)
        scored = _score_match(km, result, stage)
        if scored is None or scored["brier"] is None:
            continue
        knockout_briers.append(scored["brier"])
        n_ko += 1
        if scored["hit"]:
            quiniela += QUINIELA_POINTS.get(stage, 0)

    brier_group = sum(group_briers) if group_briers else 0.0
    brier_knockout = sum(knockout_briers) if knockout_briers else None

    if n_group == 0 and n_ko == 0:
        brier_total = None
    elif n_ko == 0:
        brier_total = brier_group / 2.0
    elif n_group == 0:
        brier_total = brier_knockout
    else:
        brier_total = (n_group * (brier_group / 2.0) + n_ko * brier_knockout) / (n_group + n_ko)

    return {
        "model": prediction.get("model", "Unknown"),
        "model_id": prediction.get("model_id", ""),
        "brier_group": round(brier_group, 6),
        "brier_knockout": round(brier_knockout, 6) if brier_knockout is not None else None,
        "brier_total": round(brier_total, 6) if brier_total is not None else None,
        "quiniela_points": quiniela,
        "roi": None,
        "roi_status": "no_market_data",
        "n_matches_scored": n_group + n_ko,
    }


def _load_polymarket_map() -> dict:
    map_path = os.path.join(POLYMARKET_DIR, "market_map.json")
    if not os.path.exists(map_path):
        return {}
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _compute_roi(prediction: dict, results: dict, market_map: dict, odds: dict) -> tuple:
    """Placeholder for real Polymarket ROI. Returns (roi, roi_status)."""
    if not market_map or not odds:
        return None, "no_market_data"
    # TODO: implement real Gamma price settlement once markets are mapped.
    return None, "no_market_data"


def generate_leaderboard(
    results_dir: str = RESULTS_DIR,
    output_path: str = LEADERBOARD_PATH,
    predictions: list = None,
) -> dict:
    results = load_results(results_dir)
    predictions = load_predictions() if predictions is None else predictions

    if not predictions:
        print("No prediction files found")
        return {}

    market_map = _load_polymarket_map()
    odds = {}
    odds_path = os.path.join(POLYMARKET_DIR, "odds.json")
    if os.path.exists(odds_path):
        try:
            with open(odds_path, "r", encoding="utf-8") as f:
                odds = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    models = []
    for pred in predictions:
        scored = score_model(pred, results)
        roi, roi_status = _compute_roi(pred, results, market_map, odds)
        scored["roi"] = roi
        scored["roi_status"] = roi_status
        models.append(scored)

    models.sort(key=lambda m: (
        m["brier_total"] if m["brier_total"] is not None else float("inf"),
        -m["quiniela_points"],
        m["model"],
    ))

    leaderboard = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_models": len(models),
        "models": models,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

    print(f"Leaderboard written to {output_path}")
    return leaderboard


def main():
    parser = argparse.ArgumentParser(description="WorldCupBench scoring engine")
    parser.add_argument("--results-dir", default=RESULTS_DIR, help="Directory with actual results")
    parser.add_argument("--output", default=LEADERBOARD_PATH, help="Output leaderboard JSON path")
    args = parser.parse_args()
    generate_leaderboard(args.results_dir, args.output)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
pytest tests/test_score.py -v
```

Expected: PASS.

**Step 5: Run scoring against real data**

```bash
python scripts/score.py
```

Expected: `data/leaderboard.json` generated, `roi: null`, `roi_status: "no_market_data"`.

**Step 6: Commit**

```bash
git add scripts/score.py tests/test_score.py data/leaderboard.json
git commit -m "feat(scoring): add freeze-v3 scoring engine with Brier, quiniela and fail-safe ROI"
```

---

## Task 4: Run full test suite and fix regressions

**Files:**
- All tests under `tests/`

**Step 1: Run pytest**

```bash
pytest -v
```

Expected: all tests pass. If `test_schema.py` or `test_run_predictions.py` fail because usan estructuras viejas, arreglarlos para freeze-v3.

**Step 2: Commit fixes**

```bash
git add tests/
git commit -m "test: update tests to freeze-v3 format"
```

---

## Task 5: Delete src/score.py

**Files:**
- Delete: `src/score.py`

**Step 1: Verify no other imports**

```bash
grep -r "from src import score\|import score\|from score import\|src.score" --include="*.py" .
```

Expected: no references (except possibly tests now updated).

**Step 2: Delete the file**

```bash
rm src/score.py
git rm src/score.py
```

**Step 3: Run tests again**

```bash
pytest -v
```

Expected: all tests pass.

**Step 4: Commit**

```bash
git commit -m "chore: remove legacy src/score.py; scripts/score.py is the single source"
```

---

## Verification summary

```bash
# 1. Schema validation passes for all pre-tournament predictions
for f in predictions/pre-tournament/*_prediction.json; do python scripts/validate_predictions.py "$f"; done

# 2. Scoring runs
python scripts/score.py

# 3. Tests pass
pytest -v

# 4. No legacy references
grep -r "src.score\|from src import score\|import score" --include="*.py" . || echo "No legacy imports"
```

All green? Listo para PR.
