"""
WorldCupBench Scoring Engine.

Reads prediction JSONs and actual results from data/results/, computes
per-model metrics, and outputs data/leaderboard.json.

Metrics:
  - Brier score (accumulated over 1X2 probabilities)
  - Bracket points (2 R32 / 4 R16 / 8 QF / 16 SF / 32 Final)
  - Correct match outcomes
  - Exact score predictions (when prediction includes predicted_score)

Usage:
    python src/score.py
    python src/score.py --results-dir data/results
    python src/score.py --output data/leaderboard.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils  # noqa: E402

# Points awarded per correct knockout winner prediction by round.
BRACKET_POINTS = {
    "R32": 2,
    "R16": 4,
    "QF": 8,
    "SF": 16,
    "final": 32,
}

RESULTS_DIR = os.path.join(utils.BASE_DIR, "data", "results")
LEADERBOARD_PATH = os.path.join(utils.BASE_DIR, "data", "leaderboard.json")
PREDICTIONS_DIR = utils.PREDICTIONS_DIR


def _result_is_finished(match: dict) -> bool:
    """Return True if the match has a usable result."""
    outcome = match.get("outcome")
    if outcome in ("home", "draw", "away"):
        return True
    score = match.get("score", {})
    return isinstance(score.get("home"), int) and isinstance(score.get("away"), int)


def _winner_team(result: dict) -> str:
    """Return the FIFA code of the winning team, or None."""
    outcome = result.get("outcome")
    if outcome == "home":
        return result.get("home_team")
    if outcome == "away":
        return result.get("away_team")
    return None


def load_results(results_dir: str = RESULTS_DIR) -> dict:
    """Load all actual match results from data/results/*.json.

    Returns a dict mapping fd_id and match_id -> result dict.
    """
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
            if not _result_is_finished(m):
                continue
            fd_id = m.get("fd_id")
            mid = m.get("match_id")
            if fd_id is not None:
                results[fd_id] = m
            if mid is not None:
                results[mid] = m

    return results


def load_predictions(predictions_dir: str = PREDICTIONS_DIR, override: list = None) -> list:
    """Load prediction files. If override is provided, use that list instead."""
    if override is not None:
        return override

    predictions = []
    pre_tournament_dir = os.path.join(predictions_dir, "pre-tournament")
    if not os.path.isdir(pre_tournament_dir):
        return predictions

    for filename in sorted(os.listdir(pre_tournament_dir)):
        if not filename.endswith("_prediction.json"):
            continue
        filepath = os.path.join(pre_tournament_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            predictions.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return predictions


def _brier_score(probs: dict, actual_outcome: str) -> float:
    """Compute Brier score for a single 1X2 prediction.

    Brier = sum( (p_i - o_i)^2 ) for i in {home, draw, away}
    where o_i = 1 if actual, 0 otherwise.
    Lower is better.
    """
    outcomes = ["home", "draw", "away"]
    brier = 0.0
    for o in outcomes:
        p = probs.get(o, 0.0)
        actual = 1.0 if o == actual_outcome else 0.0
        brier += (p - actual) ** 2
    return brier


def evaluate_prediction(prediction: dict, results: dict) -> dict:
    """Score a single prediction dict against actual results."""
    brier_total = 0.0
    evaluated = 0
    exact_scores = 0
    correct_outcomes = 0
    bracket_points = 0
    matches_scored = []

    for gm in prediction.get("group_matches", []):
        key = gm.get("fd_id") if gm.get("fd_id") is not None else gm.get("match_id")
        result = results.get(key)
        if not result:
            continue
        evaluated += 1
        actual_outcome = result.get("outcome")
        probs = gm.get("probs", {})
        brier_total += _brier_score(probs, actual_outcome)

        predicted_outcome = max(probs, key=probs.get) if probs else None
        if predicted_outcome == actual_outcome:
            correct_outcomes += 1

        predicted_score = gm.get("predicted_score")
        if predicted_score is not None:
            actual_score = result.get("score", {})
            if (
                predicted_score.get("home") == actual_score.get("home")
                and predicted_score.get("away") == actual_score.get("away")
            ):
                exact_scores += 1

        matches_scored.append({
            "match_id": gm.get("match_id"),
            "fd_id": gm.get("fd_id"),
            "predicted_outcome": predicted_outcome,
            "actual_outcome": actual_outcome,
            "brier": _brier_score(probs, actual_outcome),
        })

    bracket = prediction.get("bracket", {})
    for round_key, pts in [("R32", 2), ("R16", 4), ("QF", 8), ("SF", 16)]:
        for m in bracket.get(round_key, []):
            key = m.get("fd_id") if m.get("fd_id") is not None else m.get("match")
            result = results.get(key)
            if result and _winner_team(result) and m.get("winner") == _winner_team(result):
                bracket_points += pts

    final = bracket.get("final", {})
    final_result = results.get(final.get("fd_id")) or results.get("final")
    if final_result and _winner_team(final_result) and final.get("winner") == _winner_team(final_result):
        bracket_points += BRACKET_POINTS["final"]

    avg_brier = brier_total / evaluated if evaluated > 0 else None

    return {
        "total_evaluated": evaluated,
        "correct_outcomes": correct_outcomes,
        "exact_scores": exact_scores,
        "brier_total": round(brier_total, 4),
        "brier_avg": round(avg_brier, 4) if avg_brier is not None else None,
        "bracket_points": bracket_points,
        "matches": matches_scored,
    }


def score_model(prediction: dict, results: dict) -> dict:
    """Score a single model's predictions against actual results."""
    model_name = prediction.get("model", "Unknown")
    metrics = evaluate_prediction(prediction, results)

    total_evaluated = metrics["total_evaluated"]
    correct_outcomes = metrics["correct_outcomes"]
    exact_scores = metrics["exact_scores"]
    accuracy = (correct_outcomes / total_evaluated * 100) if total_evaluated > 0 else None

    return {
        "model_name": model_name,
        "model_id": prediction.get("model_id", ""),
        **metrics,
        "accuracy": round(accuracy, 2) if accuracy is not None else None,
        "correct": correct_outcomes,
        "exact": exact_scores,
        "champion": prediction.get("champion"),
        "runner_up": prediction.get("runner_up"),
        "third_place": prediction.get("third"),
    }


def generate_leaderboard(
    results_dir: str = RESULTS_DIR,
    output_path: str = LEADERBOARD_PATH,
    predictions: list = None,
):
    """Generate the full leaderboard JSON."""
    results = load_results(results_dir)
    predictions = load_predictions(override=predictions)

    if not predictions:
        print("No prediction files found")
        return

    print(f"Loaded {len(predictions)} predictions, {len(results)} actual results")

    models_scored = []
    for pred in predictions:
        scored = score_model(pred, results)
        models_scored.append(scored)
        print(
            f"  {scored['model_name']:20s} | "
            f"Evaluated: {scored['total_evaluated']:3d} | "
            f"Correct: {scored['correct_outcomes']:3d} | "
            f"Exact: {scored['exact_scores']:2d} | "
            f"Brier avg: {scored['brier_avg'] or 'N/A':>6} | "
            f"Bracket pts: {scored['bracket_points']:4d}"
        )

    # Sort by: bracket_points desc, correct_outcomes desc, brier_avg asc.
    models_scored.sort(
        key=lambda m: (
            -m["bracket_points"],
            -m["correct_outcomes"],
            m["brier_avg"] if m["brier_avg"] is not None else 999,
        )
    )

    # Add rank.
    for i, m in enumerate(models_scored):
        m["rank"] = i + 1

    leaderboard = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_results": len(results) // 2 if results else 0,  # keys are duplicated (fd_id + match_id)
        "total_models": len(models_scored),
        "models": [
            {
                "rank": m["rank"],
                "model_name": m["model_name"],
                "model_id": m["model_id"],
                "total_evaluated": m["total_evaluated"],
                "correct_outcomes": m["correct_outcomes"],
                "exact_scores": m["exact_scores"],
                "accuracy": m["accuracy"],
                "correct": m["correct"],
                "exact": m["exact"],
                "brier_avg": m["brier_avg"],
                "brier_total": m["brier_total"],
                "bracket_points": m["bracket_points"],
                "champion": m["champion"],
                "runner_up": m["runner_up"],
                "third_place": m["third_place"],
            }
            for m in models_scored
        ],
        "history": [],
    }

    # Load existing leaderboard to preserve history.
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            leaderboard["history"] = existing.get("history", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Append today's snapshot to history.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_snapshot = {
        "date": today,
        "models": [
            {
                "model_name": m["model_name"],
                "correct_outcomes": m["correct_outcomes"],
                "brier_avg": m["brier_avg"],
                "bracket_points": m["bracket_points"],
            }
            for m in models_scored
        ],
    }

    history = leaderboard["history"]
    replaced = False
    for i, h in enumerate(history):
        if h["date"] == today:
            history[i] = today_snapshot
            replaced = True
            break
    if not replaced:
        history.append(today_snapshot)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

    print(f"\nLeaderboard written to {output_path}")
    return leaderboard


def main():
    parser = argparse.ArgumentParser(description="WorldCupBench Scoring Engine")
    parser.add_argument(
        "--results-dir",
        default=RESULTS_DIR,
        help=f"Directory with actual results (default: {RESULTS_DIR})",
    )
    parser.add_argument(
        "--output",
        default=LEADERBOARD_PATH,
        help=f"Output leaderboard JSON path (default: {LEADERBOARD_PATH})",
    )
    args = parser.parse_args()

    generate_leaderboard(args.results_dir, args.output)


if __name__ == "__main__":
    main()
