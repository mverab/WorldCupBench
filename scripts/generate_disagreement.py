#!/usr/bin/env python3
"""Generate docs/data/disagreement.json for the dashboard.

For every match that already has a real result (any file in data/results/*.json),
this script measures how much the frozen pre-tournament model predictions disagree
on the 1X2 probabilities (home / draw / away).

For each such match it computes:
  * the consensus (mean) probability for each outcome,
  * the population standard deviation of each outcome across models,
  * a single ``disagreement_score`` (the sum of the per-outcome std devs),
  * the per-model distance from the consensus (Euclidean), used to flag the
    models that are furthest from the pack.

The output is shaped exactly the way docs/app.js expects it so the
"Disagreement" tab can render directly from the static JSON file.
"""

import argparse
import glob
import json
import os
import statistics
import sys
from datetime import datetime, timezone

# Make the bundled helpers importable regardless of the current working dir.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils  # noqa: E402

BASE_DIR = utils.BASE_DIR
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions", "pre-tournament")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "data", "disagreement.json")

OUTCOMES = ("home", "draw", "away")


def load_tournament(path: str = TOURNAMENT_PATH) -> dict:
    """Return a {match_id(str): match_meta} map from tournament.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    matches = {}
    for m in data.get("matches", []):
        mid = m.get("match_id")
        if mid is not None:
            matches[str(mid)] = m
    return matches


def _has_result(match: dict) -> bool:
    if match.get("outcome") in OUTCOMES:
        return True
    score = match.get("score", {})
    return isinstance(score.get("home"), int) and isinstance(score.get("away"), int)


def load_results(results_dir: str = RESULTS_DIR) -> dict:
    """Return {match_id(str): result_match} for every finished match."""
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
            mid = m.get("match_id")
            if mid is not None:
                results[str(mid)] = m
    return results


def load_predictions(predictions_dir: str = PREDICTIONS_DIR) -> list:
    """Load every pre-tournament prediction file."""
    preds = []
    for filepath in sorted(glob.glob(os.path.join(predictions_dir, "*_prediction.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                preds.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return preds


def _index_group_matches(prediction: dict) -> dict:
    """Return {match_id(str): probs_dict} for a single model's group matches."""
    indexed = {}
    for gm in prediction.get("group_matches", []):
        mid = gm.get("match_id")
        probs = gm.get("probs")
        if mid is None or not isinstance(probs, dict):
            continue
        indexed[str(mid)] = probs
    return indexed


def _normalize_probs(probs: dict) -> dict:
    """Coerce probs to floats for home/draw/away and renormalize if needed."""
    vals = {o: float(probs.get(o, 0.0) or 0.0) for o in OUTCOMES}
    total = sum(vals.values())
    if total > 0:
        vals = {o: v / total for o, v in vals.items()}
    return vals


def _phase_for_match(match_id: str) -> str:
    try:
        mid = int(match_id)
    except (ValueError, TypeError):
        return "knockout"
    return "group" if 1 <= mid <= 72 else "knockout"


def build_disagreement(tournament: dict, results: dict, predictions: list) -> list:
    """Compute the disagreement record for every match that has a result."""
    # Pre-index each model's group predictions once.
    model_indexes = []
    for pred in predictions:
        model_name = pred.get("model") or pred.get("model_name") or pred.get("model_id")
        model_indexes.append((model_name, _index_group_matches(pred)))

    records = []
    for match_id, result in results.items():
        meta = tournament.get(match_id, {})

        # Collect every model's 1X2 probabilities for this match.
        model_predictions = []
        for model_name, index in model_indexes:
            probs = index.get(match_id)
            if not probs:
                continue
            model_predictions.append((model_name, _normalize_probs(probs)))

        # Need at least two models to talk about disagreement.
        if len(model_predictions) < 2:
            continue

        # Consensus (mean) per outcome and population std per outcome.
        consensus = {}
        std = {}
        for outcome in OUTCOMES:
            series = [mp[1][outcome] for mp in model_predictions]
            consensus[outcome] = sum(series) / len(series)
            std[outcome] = statistics.pstdev(series) if len(series) > 1 else 0.0

        disagreement_score = sum(std.values())
        variance = sum(v * v for v in std.values())

        # Per-model Euclidean distance from the consensus vector.
        enriched_predictions = []
        for model_name, probs in model_predictions:
            distance = (
                sum((probs[o] - consensus[o]) ** 2 for o in OUTCOMES)
            ) ** 0.5
            enriched_predictions.append(
                {
                    "model": model_name,
                    "home": round(probs["home"], 4),
                    "draw": round(probs["draw"], 4),
                    "away": round(probs["away"], 4),
                    "distance": round(distance, 4),
                }
            )

        # Order models by how far they sit from the consensus (outliers first).
        enriched_predictions.sort(key=lambda mp: mp["distance"], reverse=True)
        outliers = [
            {"model": mp["model"], "distance": mp["distance"]}
            for mp in enriched_predictions[:3]
        ]

        group = meta.get("group")
        if not group:
            # results files store it as "GROUP_A" -> normalize to "A"
            raw_group = (result.get("group") or "").replace("GROUP_", "")
            group = raw_group or None

        records.append(
            {
                "match_id": int(match_id) if match_id.isdigit() else match_id,
                "date": meta.get("date") or result.get("date"),
                "phase": _phase_for_match(match_id),
                "group": group,
                "round": result.get("stage") or meta.get("stage") or "GROUP_STAGE",
                "home_team": meta.get("home_team") or result.get("home_team"),
                "away_team": meta.get("away_team") or result.get("away_team"),
                "outcome": result.get("outcome"),
                "disagreement_score": round(disagreement_score, 6),
                "variance": round(variance, 6),
                "consensus": {o: round(consensus[o], 4) for o in OUTCOMES},
                "std": {o: round(std[o], 4) for o in OUTCOMES},
                "outliers": outliers,
                "model_predictions": enriched_predictions,
            }
        )

    # Highest disagreement first so the dashboard can flag the "hottest" matches.
    records.sort(key=lambda r: r["disagreement_score"], reverse=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default=OUTPUT_PATH, help="Path to write disagreement.json"
    )
    args = parser.parse_args()

    tournament = load_tournament()
    results = load_results()
    predictions = load_predictions()

    matches = build_disagreement(tournament, results, predictions)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_count": len(predictions),
        "match_count": len(matches),
        "matches": matches,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(
        f"Wrote {len(matches)} disagreement records "
        f"(from {len(predictions)} models, {len(results)} finished matches) "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
