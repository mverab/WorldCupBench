import json
import re
from pathlib import Path
from statistics import pvariance
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "predictions" / "pre-tournament"
TOURNAMENT_PATH = BASE_DIR / "data" / "tournament.json"

PHASE_GROUP = "group"
PHASE_KNOCKOUT = "knockout"

KNOCKOUT_ROUNDS = ["R32", "R16", "QF", "SF", "third_place", "final"]


def load_predictions(directory: Path | None = None) -> list[dict[str, Any]]:
    if directory is None:
        directory = PREDICTIONS_DIR
    predictions = []
    if not directory.exists():
        return predictions
    for path in sorted(directory.glob("*_prediction.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            predictions.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return predictions


def load_tournament(path: Path = TOURNAMENT_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Tournament file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compute_disagreement(
    predictions: list[dict[str, Any]],
    phase: str,
) -> float:
    if len(predictions) < 2:
        return 0.0

    if phase == PHASE_KNOCKOUT:
        home_raw = [p["home"] for p in predictions]
        away_raw = [p["away"] for p in predictions]
        home = []
        away = []
        for h, a in zip(home_raw, away_raw):
            total = h + a
            if total == 0:
                home.append(0.5)
                away.append(0.5)
            else:
                home.append(h / total)
                away.append(a / total)
        values = [home, away]
    else:
        home = [p["home"] for p in predictions]
        draw = [p["draw"] for p in predictions]
        away = [p["away"] for p in predictions]
        values = [home, draw, away]

    return sum(pvariance(v) for v in values) / len(values)


def _normalise_model_name(name: str) -> str:
    return re.sub(r"[\s_-]+", "-", name).strip().lower()


def _find_knockout_match(bracket: dict[str, Any], match_id: int) -> dict[str, Any] | None:
    for round_key in KNOCKOUT_ROUNDS:
        item_or_list = bracket.get(round_key, [])
        items = item_or_list if isinstance(item_or_list, list) else [item_or_list]
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("match_id")) == str(match_id):
                return item
    return None


def _collect_model_predictions(
    match_id: int,
    phase: str,
    predictions: list[dict[str, Any]],
) -> list[dict[str, float]]:
    collected = []
    for pred in predictions:
        model_name = pred.get("model", "Unknown")
        if phase == PHASE_KNOCKOUT:
            match = _find_knockout_match(pred.get("bracket", {}), match_id)
        else:
            match = next(
                (m for m in pred.get("group_matches", []) if str(m.get("match_id")) == str(match_id)),
                None,
            )
        if match:
            collected.append({
                "model": model_name,
                **match.get("probs", {"home": 0.0, "draw": 0.0, "away": 0.0}),
            })
    return collected


def build_disagreement_response(
    tournament: dict[str, Any],
    predictions: list[dict[str, Any]],
    phase: str | None,
    model_names: list[str] | None,
) -> dict[str, Any]:
    if model_names:
        allowed = {_normalise_model_name(n) for n in model_names}
        predictions = [
            p for p in predictions
            if _normalise_model_name(p.get("model", "")) in allowed
        ]

    all_matches = []
    for m in tournament.get("matches", []):
        all_matches.append({"data": m, "phase": PHASE_GROUP})
    for m in tournament.get("knockout_bracket", []):
        all_matches.append({"data": m, "phase": PHASE_KNOCKOUT})

    if phase:
        all_matches = [m for m in all_matches if m["phase"] == phase]

    results = []
    for item in all_matches:
        data = item["data"]
        match_id = data["match_id"]
        model_predictions = _collect_model_predictions(match_id, item["phase"], predictions)
        if len(model_predictions) < 2:
            continue
        score = compute_disagreement(model_predictions, item["phase"])
        results.append({
            "match_id": match_id,
            "phase": item["phase"],
            "group": data.get("group") if item["phase"] == PHASE_GROUP else None,
            "round": data.get("round") if item["phase"] == PHASE_KNOCKOUT else None,
            "home_team": data.get("home_team"),
            "away_team": data.get("away_team"),
            "date": data.get("date"),
            "disagreement_score": round(score, 6),
            "model_predictions": model_predictions,
        })

    results.sort(key=lambda x: x["disagreement_score"], reverse=True)

    return {
        "matches": results,
        "meta": {
            "total_matches": len(results),
            "models_used": [p.get("model", "Unknown") for p in predictions],
            "phase_filter": phase,
            "models_filter": model_names,
        },
    }
