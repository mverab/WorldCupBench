"""
Common utilities for WorldCupBench: prompt loading, JSON response parsing,
schema validation, and prediction saving.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

# Base project paths (relative to the repo root).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "prediction_prompt.txt")
RATIONALE_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "rationale_prompt.txt")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema", "predictions_schema.json")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions")
RATIONALE_DIR = os.path.join(BASE_DIR, "predictions", "pre-tournament")

# football-data.org uses a few TLAs that differ from canonical FIFA codes.
API_TO_FIFA_TLA = {
    "URY": "URU",  # Uruguay: ISO code → FIFA code
}
FIFA_TO_API_TLA = {v: k for k, v in API_TO_FIFA_TLA.items()}


def load_prompt(path: str = PROMPT_PATH) -> str:
    """Reads and returns the standard prompt content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_rationale_prompt(path: str = RATIONALE_PROMPT_PATH) -> str:
    """Reads and returns the rationale prompt content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_schema(path: str = SCHEMA_PATH) -> dict:
    """Loads the JSON predictions schema."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tournament_data(path: str = TOURNAMENT_PATH) -> dict:
    """Loads the official tournament data from tournament.json."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_fifa_codes(tournament_data: dict) -> set:
    """Extracts all valid 3-letter FIFA team codes from tournament data."""
    codes = set()
    for group in tournament_data.get("groups", []):
        for team in group.get("teams", []):
            codes.add(team)
    return codes


def now_iso() -> str:
    """Returns the current date-time in ISO 8601 format (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str) -> str:
    """Computes the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_json(text: str):
    """
    Extracts a JSON object from a model's response.

    Handles common cases where the model wraps the JSON in markdown code
    blocks (```json ... ```) or adds text before/after.
    Returns the parsed dict or raises ValueError if parsing fails.
    """
    if not text or not text.strip():
        raise ValueError("Empty response from model.")

    # 1) Try direct parsing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Strip markdown fences ```json ... ``` or ``` ... ```.
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Take from the first '{' to the last '}'.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("Could not extract valid JSON from the model's response.")


def _get_match_winner(match: dict) -> str:
    """Returns the FIFA code of the winner (home_team or away_team) based on predicted_result."""
    result = match.get("predicted_result")
    if result == "home":
        return match.get("home_team")
    elif result == "away":
        return match.get("away_team")
    return None


def validate_predictions(data: dict, schema: dict, tournament_data: dict = None) -> tuple:
    """
    Validates predictions against the JSON schema and additional semantic rules.

    Returns (is_valid: bool, message: str). If the `jsonschema` library is not
    installed, performs a minimal validation of top-level keys.
    """
    required_top = [
        "model_name",
        "timestamp",
        "prompt_version",
        "temperature",
        "group_stage_matches",
        "group_qualifiers",
        "knockout_stage",
        "final_standings",
    ]

    # Minimal top-level key validation (always).
    missing = [k for k in required_top if k not in data]
    if missing:
        return False, f"Missing required keys: {missing}"

    # JSON schema validation.
    try:
        import jsonschema
        from jsonschema import Draft7Validator

        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errors:
            msgs = "; ".join(
                f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors[:5]
            )
            return False, f"Schema errors: {msgs}"
    except ImportError:
        pass  # Continue with semantic validations

    # Additional semantic validations.
    semantic_errors = []

    # Load FIFA codes if tournament data is provided.
    valid_codes = None
    if tournament_data is not None:
        valid_codes = get_fifa_codes(tournament_data)

    def _check_fifa_code(code: str, context: str):
        if valid_codes and code not in valid_codes:
            semantic_errors.append(f"{context}: invalid FIFA code '{code}'")

    def _check_probs(match: dict, allow_draw: bool = True):
        probs = match.get("probs", {})
        total = probs.get("home", 0) + probs.get("draw", 0) + probs.get("away", 0)
        if not (0.98 <= total <= 1.02):
            mid = match.get("match_id", "?")
            semantic_errors.append(
                f"{mid}: probs sum {total:.4f} (expected 1.0±0.02)"
            )
        if not allow_draw and probs.get("draw", 0) != 0:
            mid = match.get("match_id", "?")
            semantic_errors.append(f"{mid}: knockout draw prob must be 0.0")

    # --- Group stage validations ---
    group_matches = data.get("group_stage_matches") or []
    if isinstance(group_matches, list):
        if len(group_matches) != 72:
            semantic_errors.append(
                f"group_stage_matches has {len(group_matches)} matches (expected 72)"
            )
        for i, match in enumerate(group_matches):
            mid = match.get("match_id", f"GS-?({i})")
            expected_id = f"GS-{i + 1:02d}"
            if mid != expected_id:
                semantic_errors.append(f"group match {i}: expected {expected_id}, got {mid}")
            _check_probs(match, allow_draw=True)
            _check_fifa_code(match.get("home_team", ""), mid)
            _check_fifa_code(match.get("away_team", ""), mid)

    # --- Group qualifiers validations ---
    qualifiers = data.get("group_qualifiers") or {}
    if isinstance(qualifiers, dict):
        first = qualifiers.get("first_place") or []
        second = qualifiers.get("second_place") or []
        third = qualifiers.get("best_third_place") or []
        if len(first) != 12:
            semantic_errors.append(f"first_place has {len(first)} teams (expected 12)")
        if len(second) != 12:
            semantic_errors.append(f"second_place has {len(second)} teams (expected 12)")
        if len(third) != 8:
            semantic_errors.append(f"best_third_place has {len(third)} teams (expected 8)")
        for team in first + second + third:
            _check_fifa_code(team.get("team_code", ""), f"qualifier {team}")

    # --- Knockout stage validations ---
    knockout = data.get("knockout_stage") or {}
    if isinstance(knockout, dict):
        stage_configs = [
            ("round_of_32", 16, "R32", 73),
            ("round_of_16", 8, "R16", 89),
            ("quarter_finals", 4, "QF", 97),
            ("semi_finals", 2, "SF", 101),
        ]

        for stage_name, expected_count, prefix, start_num in stage_configs:
            stage_matches = knockout.get(stage_name) or []
            if isinstance(stage_matches, list):
                if len(stage_matches) != expected_count:
                    semantic_errors.append(
                        f"{stage_name} has {len(stage_matches)} matches (expected {expected_count})"
                    )
                for i, match in enumerate(stage_matches):
                    mid = match.get("match_id", f"{prefix}-?({i})")
                    expected_id = f"{prefix}-{start_num + i:02d}"
                    if mid != expected_id:
                        semantic_errors.append(
                            f"{stage_name} match {i}: expected {expected_id}, got {mid}"
                        )
                    _check_probs(match, allow_draw=False)
                    _check_fifa_code(match.get("home_team", ""), mid)
                    _check_fifa_code(match.get("away_team", ""), mid)

        # Third place match.
        third_match = knockout.get("third_place_match")
        if third_match:
            if third_match.get("match_id") != "THIRD":
                semantic_errors.append(
                    f"third_place_match: expected match_id 'THIRD', got '{third_match.get('match_id')}'"
                )
            _check_probs(third_match, allow_draw=False)
            _check_fifa_code(third_match.get("home_team", ""), "THIRD")
            _check_fifa_code(third_match.get("away_team", ""), "THIRD")
        else:
            semantic_errors.append("Missing third_place_match")

        # Final.
        final_match = knockout.get("final")
        if final_match:
            if final_match.get("match_id") != "FINAL":
                semantic_errors.append(
                    f"final: expected match_id 'FINAL', got '{final_match.get('match_id')}'"
                )
            _check_probs(final_match, allow_draw=False)
            _check_fifa_code(final_match.get("home_team", ""), "FINAL")
            _check_fifa_code(final_match.get("away_team", ""), "FINAL")
        else:
            semantic_errors.append("Missing final")

    # --- Final standings coherence ---
    standings = data.get("final_standings") or {}
    if isinstance(standings, dict) and final_match and third_match:
        champion = _get_match_winner(final_match)
        runner = final_match.get("away_team") if champion == final_match.get("home_team") else final_match.get("home_team")
        third = _get_match_winner(third_match)
        fourth = third_match.get("away_team") if third == third_match.get("home_team") else third_match.get("home_team")

        if standings.get("champion") != champion:
            semantic_errors.append(
                f"final_standings.champion '{standings.get('champion')}' != winner of final '{champion}'"
            )
        if standings.get("runner_up") != runner:
            semantic_errors.append(
                f"final_standings.runner_up '{standings.get('runner_up')}' != loser of final '{runner}'"
            )
        if standings.get("third_place") != third:
            semantic_errors.append(
                f"final_standings.third_place '{standings.get('third_place')}' != winner of third_place_match '{third}'"
            )
        if standings.get("fourth_place") != fourth:
            semantic_errors.append(
                f"final_standings.fourth_place '{standings.get('fourth_place')}' != loser of third_place_match '{fourth}'"
            )

        for key in ["champion", "runner_up", "third_place", "fourth_place"]:
            _check_fifa_code(standings.get(key, ""), f"final_standings.{key}")

    if semantic_errors:
        msgs = "; ".join(semantic_errors[:10])
        return False, f"Semantic errors: {msgs}"

    return True, "OK"


def save_predictions(model_name: str, data: dict, predictions_dir: str = PREDICTIONS_DIR) -> str:
    """
    Saves a model's predictions to predictions/{model_name}_predictions.json.

    Returns the path of the saved file.
    """
    os.makedirs(predictions_dir, exist_ok=True)
    safe_name = model_name.replace("/", "_").replace(" ", "_")
    out_path = os.path.join(predictions_dir, f"{safe_name}_prediction.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def save_rationale(model_name: str, text: str, rationale_dir: str = RATIONALE_DIR) -> str:
    """
    Saves a model's rationale analysis to predictions/pre-tournament/{model_name}_rationale.md.

    Returns the path of the saved file.
    """
    os.makedirs(rationale_dir, exist_ok=True)
    safe_name = model_name.replace("/", "_").replace(" ", "_")
    out_path = os.path.join(rationale_dir, f"{safe_name}_rationale.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path
