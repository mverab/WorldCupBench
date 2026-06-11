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
