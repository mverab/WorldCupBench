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
            errors.append(
                f"qualifier {code} group {group} != tournament group {group_of_code[code]}"
            )

    # Knockout bracket
    bracket = prediction.get("bracket") or {}
    for round_key in ["R32", "R16", "QF", "SF"]:
        for m in bracket.get(round_key, []):
            _check_probs(m, allow_draw=False)
            _check_fifa(m.get("home_team", ""), str(m.get("match_id")))
            _check_fifa(m.get("away_team", ""), str(m.get("match_id")))
            if m.get("winner") not in (m.get("home_team"), m.get("away_team")):
                errors.append(
                    f"{m.get('match_id')}: winner {m.get('winner')} not in match"
                )

    for key in ["third_place", "final"]:
        m = bracket.get(key)
        if m:
            _check_probs(m, allow_draw=False)
            _check_fifa(m.get("home_team", ""), str(m.get("match_id")))
            _check_fifa(m.get("away_team", ""), str(m.get("match_id")))
            if m.get("winner") not in (m.get("home_team"), m.get("away_team")):
                errors.append(
                    f"{m.get('match_id')}: winner {m.get('winner')} not in match"
                )

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
