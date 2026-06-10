"""
Common utilities for WorldCupBench: prompt loading, JSON response parsing,
schema validation, and prediction saving.
"""

import json
import os
import re
from datetime import datetime, timezone

# Base project paths (relative to the repo root).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "prediction_prompt.txt")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema", "predictions_schema.json")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions")


def load_prompt(path: str = PROMPT_PATH) -> str:
    """Reads and returns the standard prompt content."""
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


def now_iso() -> str:
    """Returns the current date-time in ISO 8601 format (UTC)."""
    return datetime.now(timezone.utc).isoformat()


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


def validate_predictions(data: dict, schema: dict) -> tuple:
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

    # Group stage: draw allowed.
    group_matches = data.get("group_stage_matches") or []
    if isinstance(group_matches, list):
        for match in group_matches:
            _check_probs(match, allow_draw=True)

    # Knockout stage: draw not allowed.
    knockout = data.get("knockout_stage") or {}
    if isinstance(knockout, dict):
        for stage in ["round_of_32", "round_of_16", "quarter_finals", "semi_finals"]:
            stage_matches = knockout.get(stage) or []
            if isinstance(stage_matches, list):
                for match in stage_matches:
                    _check_probs(match, allow_draw=False)
        for key in ["third_place_match", "final"]:
            match = knockout.get(key)
            if match:
                _check_probs(match, allow_draw=False)

    if semantic_errors:
        msgs = "; ".join(semantic_errors[:5])
        return False, f"Semantic errors: {msgs}"

    return True, "OK"


def save_predictions(model_name: str, data: dict, predictions_dir: str = PREDICTIONS_DIR) -> str:
    """
    Saves a model's predictions to predictions/{model_name}_predictions.json.

    Returns the path of the saved file.
    """
    os.makedirs(predictions_dir, exist_ok=True)
    safe_name = model_name.replace("/", "_").replace(" ", "_")
    out_path = os.path.join(predictions_dir, f"{safe_name}_predictions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path
