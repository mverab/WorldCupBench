# WorldCupBench canonical IDs / 1X2 probabilities implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich `data/tournament.json` with `fd_id` from football-data.org, replace the prediction schema with 1X2 probabilities, update the prompt/runner/scoring to the new format, and join results by `fd_id`.

**Architecture:** Keep the existing `data/tournament.json` structure intact and only add `fd_id`. Introduce a new, smaller prediction schema (`group_matches` with `probs`, `group_tables`, `best_thirds`, `bracket`). Update `run_predictions.py` to inject the tournament JSON into the prompt and validate against the new schema. Update `score.py` to read the new prediction format and join results via `fd_id`.

**Tech Stack:** Python 3, `requests`, `jsonschema`, `pytest`.

---

### Task 1: Create `scripts/build_tournament.py` — enrich existing tournament.json with `fd_id`

**Files:**
- Create: `scripts/build_tournament.py`
- Modify: `data/tournament.json` (only after running the script with API key)
- Test: `tests/test_build_tournament.py`

**Step 1: Write the failing test**

Create `tests/test_build_tournament.py`:

```python
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_tournament


def test_add_fd_ids_enriches_without_changing_structure(tmp_path):
    existing = {
        "edition": "2026",
        "groups": [{"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]}],
        "matches": [
            {
                "match_id": 1,
                "stage": "GROUP_STAGE",
                "group": "A",
                "date": "2026-06-11",
                "home_team": "MEX",
                "away_team": "RSA",
                "venue": "Azteca",
            }
        ],
    }
    api_matches = [
        {
            "id": 123456,
            "stage": "GROUP_STAGE",
            "group": "GROUP_A",
            "utcDate": "2026-06-11T19:00:00Z",
            "homeTeam": {"tla": "MEX"},
            "awayTeam": {"tla": "RSA"},
            "status": "TIMED",
        }
    ]

    result = build_tournament.add_fd_ids(existing, api_matches)

    assert result["matches"][0]["fd_id"] == 123456
    assert result["matches"][0]["venue"] == "Azteca"
    assert "groups" in result
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_build_tournament.py::test_add_fd_ids_enriches_without_changing_structure -v
```

Expected: `FAIL` with `ModuleNotFoundError: No module named 'build_tournament'`.

**Step 3: Write minimal implementation**

Create `scripts/build_tournament.py`:

```python
"""Enrich data/tournament.json with fd_id from football-data.org API."""

import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
COMPETITION_ID = 2000
SEASON_ID = 2398
API_BASE = "https://api.football-data.org/v4"


def add_fd_ids(tournament: dict, api_matches: list) -> dict:
    """Add fd_id to each tournament match by matching home/away/date."""
    api_index = {}
    for m in api_matches:
        home = m.get("homeTeam", {}).get("tla")
        away = m.get("awayTeam", {}).get("tla")
        date = m.get("utcDate", "")[:10]
        if home and away and date:
            api_index[(home, away, date)] = m["id"]

    for match in tournament.get("matches", []):
        home = match.get("home_team")
        away = match.get("away_team")
        date = match.get("date", "")
        fd_id = api_index.get((home, away, date))
        if fd_id is not None:
            match["fd_id"] = fd_id

    return tournament


def fetch_api_matches(api_key: str) -> list:
    url = f"{API_BASE}/competitions/{COMPETITION_ID}/matches"
    headers = {"X-Auth-Token": api_key}
    params = {"season": SEASON_ID}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def main():
    api_key = os.environ["FOOTBALL_DATA_API_KEY"]
    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    api_matches = fetch_api_matches(api_key)
    enriched = add_fd_ids(tournament, api_matches)

    missing = [m.get("match_id") for m in enriched.get("matches", []) if "fd_id" not in m]
    if missing:
        print(f"WARNING: {len(missing)} matches without fd_id: {missing[:5]}")

    with open(TOURNAMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"OK: enriched {len(enriched.get('matches', []))} matches")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_build_tournament.py::test_add_fd_ids_enriches_without_changing_structure -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add scripts/build_tournament.py tests/test_build_tournament.py
git commit -m "feat: build_tournament.py enriches existing tournament.json with fd_id"
```

---

### Task 2: Rewrite `schema/predictions_schema.json`

**Files:**
- Modify: `schema/predictions_schema.json`
- Test: `tests/test_schema.py`

**Step 1: Write the failing test**

Create `tests/test_schema.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_schema.py::test_schema_accepts_valid_prediction -v
```

Expected: `FAIL` because schema still expects old keys like `model_name` and `group_stage_matches`.

**Step 3: Write minimal implementation**

Replace `schema/predictions_schema.json` with:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://github.com/mverab/WorldCupBench/schema/predictions_schema.json",
  "title": "WorldCupBench Predictions Schema v3",
  "description": "Prediction format using explicit 1X2 probabilities and canonical FIFA TLAs.",
  "type": "object",
  "required": [
    "model",
    "modality",
    "generated_at",
    "seed_or_temp",
    "group_matches",
    "group_tables",
    "best_thirds",
    "bracket",
    "champion",
    "runner_up",
    "third"
  ],
  "properties": {
    "model": {"type": "string"},
    "modality": {"enum": ["pre_tournament", "daily"]},
    "generated_at": {"type": "string", "format": "date-time"},
    "seed_or_temp": {
      "type": "object",
      "properties": {
        "temperature": {"type": "number"},
        "seed": {"type": "integer"}
      }
    },
    "group_matches": {
      "type": "array",
      "items": {"$ref": "#/definitions/group_match"}
    },
    "group_tables": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "minItems": 4,
        "maxItems": 4,
        "items": {"$ref": "#/definitions/tla"}
      }
    },
    "best_thirds": {
      "type": "array",
      "minItems": 8,
      "maxItems": 8,
      "items": {"$ref": "#/definitions/tla"}
    },
    "bracket": {"$ref": "#/definitions/bracket"},
    "champion": {"$ref": "#/definitions/tla"},
    "runner_up": {"$ref": "#/definitions/tla"},
    "third": {"$ref": "#/definitions/tla"}
  },
  "definitions": {
    "tla": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "group_match": {
      "type": "object",
      "required": ["match_id", "probs"],
      "properties": {
        "match_id": {"type": "string"},
        "probs": {"$ref": "#/definitions/probs"}
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
        "third_place": {"$ref": "#/definitions/tla"},
        "final": {
          "type": "object",
          "required": ["winner", "runner_up"],
          "properties": {
            "winner": {"$ref": "#/definitions/tla"},
            "runner_up": {"$ref": "#/definitions/tla"}
          }
        }
      }
    },
    "knockout_round": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["match", "winner"],
        "properties": {
          "match": {"type": "string"},
          "winner": {"$ref": "#/definitions/tla"}
        }
      }
    }
  }
}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_schema.py::test_schema_accepts_valid_prediction -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add schema/predictions_schema.json tests/test_schema.py
git commit -m "feat: new prediction schema with 1X2 probabilities and TLAs"
```

---

### Task 3: Rewrite `prompts/prediction_prompt.txt`

**Files:**
- Modify: `prompts/prediction_prompt.txt`
- Test: `tests/test_prompt.py`

**Step 1: Write the failing test**

Create `tests/test_prompt.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils


def test_prompt_contains_tournament_placeholder():
    prompt = utils.load_prompt()
    assert "{{TOURNAMENT_JSON}}" in prompt
    assert "home" in prompt
    assert "draw" in prompt
    assert "away" in prompt
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_prompt.py::test_prompt_contains_tournament_placeholder -v
```

Expected: `FAIL` because prompt currently uses `{{TOURNAMENT_DATA}}`.

**Step 3: Write minimal implementation**

Replace `prompts/prediction_prompt.txt`:

```
Eres un analista experto de fútbol. Vas a predecir el Mundial 2026 COMPLETO.

DATOS OFICIALES DEL TORNEO (fuente de verdad, no inventes nada):
{{TOURNAMENT_JSON}}

TAREA:
1. Para CADA partido de grupo (usa el match_id exacto), da probabilidades 1X2:
   {"home": x, "draw": y, "away": z} donde x+y+z = 1.0
2. Predice la tabla final de cada grupo (orden de los 4 equipos por TLA).
3. Predice los 8 mejores terceros (best_thirds) por TLA.
4. Predice el bracket completo (R32 -> R16 -> QF -> SF -> final + tercer lugar) por TLA.
5. Da campeón, subcampeón y tercer lugar.

REGLAS:
- Usa SOLO los TLA de 3 letras presentes en los datos oficiales.
- Las probabilidades de cada partido deben sumar exactamente 1.0.
- Responde ÚNICAMENTE con JSON válido según el schema. Sin texto adicional, sin markdown.

OUTPUT JSON:
{
  "model": "<model name>",
  "modality": "pre_tournament",
  "generated_at": "<ISO8601 UTC>",
  "seed_or_temp": {"temperature": 0.3},
  "group_matches": [
    {"match_id": "<match_id>", "probs": {"home": 0.55, "draw": 0.27, "away": 0.18}}
  ],
  "group_tables": {"A": ["TLA1", "TLA2", "TLA3", "TLA4"]},
  "best_thirds": ["TLA", "..."],
  "bracket": {
    "R32": [{"match": "<match_id>", "winner": "TLA"}],
    "R16": [],
    "QF": [],
    "SF": [],
    "third_place": "TLA",
    "final": {"winner": "TLA", "runner_up": "TLA"}
  },
  "champion": "TLA",
  "runner_up": "TLA",
  "third": "TLA"
}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_prompt.py::test_prompt_contains_tournament_placeholder -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add prompts/prediction_prompt.txt tests/test_prompt.py
git commit -m "feat: new prompt injects tournament.json and demands 1X2 probs"
```

---

### Task 4: Create `scripts/validate_predictions.py`

**Files:**
- Create: `scripts/validate_predictions.py`
- Test: `tests/test_validate_predictions.py`

**Step 1: Write the failing test**

Create `tests/test_validate_predictions.py`:

```python
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
        "best_thirds": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
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
        "best_thirds": ["AAA"] * 8,
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_validate_predictions.py -v
```

Expected: `FAIL` with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**

Create `scripts/validate_predictions.py`:

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
    valid_group_match_ids = {
        str(m["match_id"])
        for m in tournament.get("matches", [])
        if m.get("stage") == "GROUP_STAGE"
    }

    errors = []

    for gm in prediction.get("group_matches", []):
        mid = str(gm.get("match_id", "?"))
        probs = gm.get("probs", {})
        total = probs.get("home", 0) + probs.get("draw", 0) + probs.get("away", 0)
        if not (0.99 <= total <= 1.01):
            errors.append(f"{mid}: probs sum {total:.4f}")
        if mid not in valid_group_match_ids:
            errors.append(f"{mid}: unknown group match_id")

    for group, teams in prediction.get("group_tables", {}).items():
        for t in teams:
            if t not in valid_codes:
                errors.append(f"group {group}: invalid TLA {t}")

    for t in prediction.get("best_thirds", []):
        if t not in valid_codes:
            errors.append(f"best_thirds: invalid TLA {t}")

    for key in ["champion", "runner_up", "third"]:
        val = prediction.get(key)
        if val and val not in valid_codes:
            errors.append(f"{key}: invalid TLA {val}")

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

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_validate_predictions.py -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add scripts/validate_predictions.py tests/test_validate_predictions.py
git commit -m "feat: standalone prediction validator with probs, TLA and match_id checks"
```

---

### Task 5: Move and update `scripts/fetch_results.py`

**Files:**
- Create: `scripts/fetch_results.py`
- Delete: `src/fetch_results.py`
- Test: `tests/test_fetch_results.py`

**Step 1: Write the failing test**

Create `tests/test_fetch_results.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_results


def test_map_api_to_tournament_uses_fd_id():
    tournament = {
        "matches": [
            {"match_id": "1", "home_team": "MEX", "away_team": "RSA", "date": "2026-06-11", "fd_id": 123}
        ]
    }
    api_match = {
        "id": 123,
        "utcDate": "2026-06-11T19:00:00Z",
        "homeTeam": {"tla": "MEX"},
        "awayTeam": {"tla": "RSA"},
        "status": "FINISHED",
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
    result = fetch_results.map_api_match(api_match, tournament)
    assert result["fd_id"] == 123
    assert result["match_id"] == "1"
    assert result["outcome"] == "home"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetch_results.py::test_map_api_to_tournament_uses_fd_id -v
```

Expected: `FAIL` with `ModuleNotFoundError` for scripts.fetch_results.

**Step 3: Write minimal implementation**

Move `src/fetch_results.py` to `scripts/fetch_results.py` and adapt the mapping function:

```python
def map_api_match(api_match: dict, tournament: dict) -> dict:
    home = api_match.get("homeTeam", {}).get("tla", "")
    away = api_match.get("awayTeam", {}).get("tla", "")
    date = api_match.get("utcDate", "")[:10]
    score = api_match.get("score", {}).get("fullTime", {})

    fd_id = None
    match_id = None
    for m in tournament.get("matches", []):
        if (m.get("home_team") == home and m.get("away_team") == away and m.get("date") == date):
            fd_id = m.get("fd_id")
            match_id = str(m.get("match_id"))
            break

    home_goals = score.get("home")
    away_goals = score.get("away")
    outcome = None
    if home_goals is not None and away_goals is not None:
        if home_goals > away_goals:
            outcome = "home"
        elif away_goals > home_goals:
            outcome = "away"
        else:
            outcome = "draw"

    return {
        "fd_id": fd_id,
        "match_id": match_id,
        "home_team": home,
        "away_team": away,
        "score": {"home": home_goals, "away": away_goals},
        "outcome": outcome,
        "date": date,
        "stage": api_match.get("stage", ""),
        "group": api_match.get("group", ""),
    }
```

Update `fetch_from_api` to skip non-FINISHED matches and use `map_api_match`. Update imports to use `utils` from `src/`.

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_fetch_results.py::test_map_api_to_tournament_uses_fd_id -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
rm src/fetch_results.py
git add scripts/fetch_results.py tests/test_fetch_results.py
git commit -m "feat: move fetch_results to scripts/ and join by fd_id"
```

---

### Task 6: Update `src/run_predictions.py`

**Files:**
- Modify: `src/run_predictions.py`
- Test: `tests/test_run_predictions.py`

**Step 1: Write the failing test**

Create `tests/test_run_predictions.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import run_predictions


def test_build_messages_injects_tournament_json():
    prompt = "{{TOURNAMENT_JSON}}"
    tournament = {"groups": []}
    messages = run_predictions.build_messages("GPT", prompt, tournament)
    content = messages[0]["content"]
    assert "{{TOURNAMENT_JSON}}" not in content
    assert json.loads(content) == tournament
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_run_predictions.py::test_build_messages_injects_tournament_json -v
```

Expected: `FAIL` because `build_messages` does not exist or uses `{{TOURNAMENT_DATA}}`.

**Step 3: Write minimal implementation**

Update `src/run_predictions.py`:

- Change `TOURNAMENT_PLACEHOLDER` from `{{TOURNAMENT_DATA}}` to `{{TOURNAMENT_JSON}}`.
- Load tournament data with `utils.load_tournament_data()`.
- Add `build_messages(model_name, prompt, tournament_data)` that dumps tournament to JSON and replaces placeholder.
- Update validation call to pass `tournament_data`.
- Save output file name as `{safe_name}_prediction.json` (already does).

Key snippet:

```python
TOURNAMENT_PLACEHOLDER = "{{TOURNAMENT_JSON}}"


def build_messages(model_name: str, prompt: str, tournament_data: dict) -> list:
    tournament_json = json.dumps(tournament_data, ensure_ascii=False, indent=2)
    content = prompt.replace(TOURNAMENT_PLACEHOLDER, tournament_json)
    return [{"role": "user", "content": content}]
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_run_predictions.py::test_build_messages_injects_tournament_json -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add src/run_predictions.py tests/test_run_predictions.py
git commit -m "feat: run_predictions injects tournament.json and validates new schema"
```

---

### Task 7: Update `src/score.py`

**Files:**
- Modify: `src/score.py`
- Test: `tests/test_score.py`

**Step 1: Write the failing test**

Update `tests/test_score.py` to use new format:

```python
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


def test_score_with_real_result_computes_metrics():
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_score.py -v
```

Expected: `FAIL` because `score.py` expects old prediction format.

**Step 3: Write minimal implementation**

Rewrite `src/score.py` to read new format:

- `load_predictions()` returns list of prediction dicts (can accept optional list for testing).
- Build results index keyed by `fd_id`.
- For each prediction, iterate `group_matches`, look up result by `fd_id`.
- Brier: `(1 - prob_actual_outcome)^2` where actual outcome is home/draw/away.
- Bracket points: iterate `bracket.R32/R16/QF/SF`, award points per correct winner.
- Keep exact-score count for group matches.

Key functions:

```python
def brier_score(probs: dict, outcome: str) -> float:
    return (1.0 - probs.get(outcome, 0.0)) ** 2


def evaluate_prediction(prediction: dict, results: dict) -> dict:
    brier_total = 0.0
    evaluated = 0
    exact_scores = 0
    bracket_points = 0

    for gm in prediction.get("group_matches", []):
        fd_id = gm.get("fd_id") or gm.get("match_id")
        result = results.get(fd_id)
        if not result:
            continue
        evaluated += 1
        brier_total += brier_score(gm["probs"], result["outcome"])
        if result["score"] == gm.get("predicted_score"):
            exact_scores += 1

    points_by_round = {"R32": 2, "R16": 4, "QF": 8, "SF": 16, "final": 32}
    for round_key, pts in [("R32", 2), ("R16", 4), ("QF", 8), ("SF", 16)]:
        for m in prediction.get("bracket", {}).get(round_key, []):
            fd_id = m.get("fd_id") or m.get("match")
            result = results.get(fd_id)
            if result and result.get("outcome") and m.get("winner") == result.get("winner_team"):
                bracket_points += pts

    return {
        "brier_total": brier_total,
        "total_evaluated": evaluated,
        "exact_scores": exact_scores,
        "bracket_points": bracket_points,
    }
```

Also update result loader to key by `fd_id` when present, fallback to `match_id`.

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_score.py -v
```

Expected: `PASS`.

**Step 5: Commit**

```bash
git add src/score.py tests/test_score.py
git commit -m "feat: score.py reads new prediction format and joins results by fd_id"
```

---

### Task 8: Clean up obsolete files

**Files:**
- Delete: `data/world_cup_2026_info.md`
- Move: `predictions/pre-tournament/*` → `predictions/invalidated/freeze-v3/`

**Step 1: Verify files to move**

```bash
ls predictions/pre-tournament/
```

Expected: list of `_prediction.json` and `_rationale.md` files.

**Step 2: Move and delete**

```bash
mkdir -p predictions/invalidated/freeze-v3
git mv predictions/pre-tournament/* predictions/invalidated/freeze-v3/
rm data/world_cup_2026_info.md
```

**Step 3: Verify**

```bash
ls predictions/pre-tournament/ || true
ls predictions/invalidated/freeze-v3/ | head
```

Expected: `predictions/pre-tournament/` empty or nonexistent; `freeze-v3/` contains old predictions.

**Step 4: Commit**

```bash
git add predictions/invalidated/freeze-v3 data/world_cup_2026_info.md
rm -rf predictions/pre-tournament || true
git commit -m "chore: invalidate old predictions and remove obsolete tournament.md"
```

---

### Task 9: Final integration test

**Files:**
- Test: all tests

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 2: Dry-run key scripts**

```bash
python scripts/validate_predictions.py --help
python scripts/fetch_results.py --help
python src/run_predictions.py --dry-run
```

Expected: help works, dry-run completes without errors.

**Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "fix: integration fixes after full test run"
```

---

## Summary of final file changes

| Path | Action |
|------|--------|
| `scripts/build_tournament.py` | Create |
| `scripts/validate_predictions.py` | Create |
| `scripts/fetch_results.py` | Create (moved from `src/`) |
| `schema/predictions_schema.json` | Rewrite |
| `prompts/prediction_prompt.txt` | Rewrite |
| `src/run_predictions.py` | Update |
| `src/score.py` | Update |
| `tests/test_build_tournament.py` | Create |
| `tests/test_schema.py` | Create |
| `tests/test_prompt.py` | Create |
| `tests/test_validate_predictions.py` | Create |
| `tests/test_fetch_results.py` | Create |
| `tests/test_run_predictions.py` | Create |
| `tests/test_score.py` | Update |
| `src/fetch_results.py` | Delete |
| `data/world_cup_2026_info.md` | Delete |
| `predictions/pre-tournament/*` | Move to `predictions/invalidated/freeze-v3/` |

## Notes

- `data/tournament.json` remains unchanged in this plan; the user will run `build_tournament.py` with `FOOTBALL_DATA_API_KEY` to add `fd_id` values.
- Until `fd_id` is added, `fetch_results.py` and `score.py` can fall back to `match_id` for local testing.
- Dashboard and GitHub workflows are explicitly out of scope.
