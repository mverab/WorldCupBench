"""
WorldCupBench Scoring Engine.

Reads prediction JSONs from predictions/pre-tournament/ and actual results
from data/results/, computes per-model metrics, and outputs data/leaderboard.json.

Metrics:
  - Brier score (accumulated over 1X2 probabilities)
  - Bracket points (1 group-stage / 2 R32 / 4 R16 / 8 QF / 16 SF / 32 Final)
  - Correct match outcomes
  - Exact score predictions

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
    "group_stage": 1,
    "round_of_32": 2,
    "round_of_16": 4,
    "quarter_finals": 8,
    "semi_finals": 16,
    "third_place_match": 16,
    "final": 32,
}

RESULTS_DIR = os.path.join(utils.BASE_DIR, "data", "results")
LEADERBOARD_PATH = os.path.join(utils.BASE_DIR, "data", "leaderboard.json")
PRE_TOURNAMENT_DIR = os.path.join(utils.PREDICTIONS_DIR, "pre-tournament")


def load_results(results_dir: str = RESULTS_DIR) -> dict:
    """Load all actual match results from data/results/*.json.

    Returns a dict mapping match_id -> result dict.
    Result dict has: home_team, away_team, score {home, away}, outcome (home/draw/away).
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
            mid = m.get("match_id")
            if mid:
                results[mid] = m

    return results


def load_predictions() -> list:
    """Load all frozen prediction files."""
    predictions = []
    if not os.path.isdir(PRE_TOURNAMENT_DIR):
        return predictions

    for filename in sorted(os.listdir(PRE_TOURNAMENT_DIR)):
        if not filename.endswith("_prediction.json"):
            continue
        filepath = os.path.join(PRE_TOURNAMENT_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            predictions.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return predictions


def _outcome_from_score(score: dict) -> str:
    """Determine outcome from a score dict {home, away}."""
    h, a = score.get("home", 0), score.get("away", 0)
    if h is None or a is None:
        return None
    if h > a:
        return "home"
    elif a > h:
        return "away"
    return "draw"


def _result_is_finished(match: dict) -> bool:
    """Return True if the match has a usable result (outcome or numeric score)."""
    outcome = match.get("outcome")
    if outcome in ("home", "draw", "away"):
        return True
    score = match.get("score", {})
    return isinstance(score.get("home"), int) and isinstance(score.get("away"), int)


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


def _get_stage(match_id: str) -> str:
    """Infer stage from match_id prefix."""
    if match_id.startswith("GS"):
        return "group_stage"
    elif match_id.startswith("R32"):
        return "round_of_32"
    elif match_id.startswith("R16"):
        return "round_of_16"
    elif match_id.startswith("QF"):
        return "quarter_finals"
    elif match_id.startswith("SF"):
        return "semi_finals"
    elif match_id == "THIRD":
        return "third_place_match"
    elif match_id == "FINAL":
        return "final"
    return "group_stage"


def score_model(prediction: dict, results: dict) -> dict:
    """Score a single model's predictions against actual results.

    Returns a dict with all metrics.
    """
    model_name = prediction.get("model_name", "Unknown")

    # Collect all predicted matches (group + knockout).
    all_predicted = []
    for m in prediction.get("group_stage_matches", []):
        all_predicted.append(m)

    knockout = prediction.get("knockout_stage", {})
    for stage_name in ["round_of_32", "round_of_16", "quarter_finals", "semi_finals"]:
        for m in knockout.get(stage_name, []):
            all_predicted.append(m)
    if knockout.get("third_place_match"):
        all_predicted.append(knockout["third_place_match"])
    if knockout.get("final"):
        all_predicted.append(knockout["final"])

    # Score against actual results.
    total_evaluated = 0
    correct_outcomes = 0
    exact_scores = 0
    total_brier = 0.0
    bracket_points = 0
    matches_scored = []

    for pred_match in all_predicted:
        mid = pred_match.get("match_id")
        if mid not in results:
            continue

        actual = results[mid]
        total_evaluated += 1

        # Actual outcome.
        actual_score = actual.get("score", {})
        actual_outcome = actual.get("outcome") or _outcome_from_score(actual_score)

        # Predicted outcome.
        predicted_outcome = pred_match.get("predicted_result")
        predicted_score = pred_match.get("predicted_score", {})

        # Brier score.
        probs = pred_match.get("probs", {})
        if probs:
            brier = _brier_score(probs, actual_outcome)
            total_brier += brier

        # Correct outcome?
        outcome_correct = predicted_outcome == actual_outcome
        if outcome_correct:
            correct_outcomes += 1

        # Exact score?
        score_exact = (
            predicted_score.get("home") == actual_score.get("home")
            and predicted_score.get("away") == actual_score.get("away")
        )
        if score_exact:
            exact_scores += 1

        # Bracket points.
        stage = _get_stage(mid)
        points = BRACKET_POINTS.get(stage, 1)
        earned = points if outcome_correct else 0
        bracket_points += earned

        matches_scored.append(
            {
                "match_id": mid,
                "stage": stage,
                "predicted": predicted_outcome,
                "actual": actual_outcome,
                "predicted_score": predicted_score,
                "actual_score": actual_score,
                "correct": outcome_correct,
                "exact": score_exact,
                "brier": _brier_score(probs, actual_outcome) if probs else None,
                "points": earned,
            }
        )

    avg_brier = total_brier / total_evaluated if total_evaluated > 0 else None

    return {
        "model_name": model_name,
        "model_id": prediction.get("model_id", ""),
        "total_evaluated": total_evaluated,
        "correct_outcomes": correct_outcomes,
        "exact_scores": exact_scores,
        "accuracy": round(correct_outcomes / total_evaluated * 100, 2) if total_evaluated > 0 else 0,
        "brier_total": round(total_brier, 4),
        "brier_avg": round(avg_brier, 4) if avg_brier is not None else None,
        "bracket_points": bracket_points,
        "champion": prediction.get("final_standings", {}).get("champion"),
        "runner_up": prediction.get("final_standings", {}).get("runner_up"),
        "third_place": prediction.get("final_standings", {}).get("third_place"),
        "fourth_place": prediction.get("final_standings", {}).get("fourth_place"),
        "matches": matches_scored,
    }


def generate_leaderboard(results_dir: str = RESULTS_DIR, output_path: str = LEADERBOARD_PATH):
    """Generate the full leaderboard JSON."""
    results = load_results(results_dir)
    predictions = load_predictions()

    if not predictions:
        print("No prediction files found in", PRE_TOURNAMENT_DIR)
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
            f"Accuracy: {scored['accuracy']:5.1f}% | "
            f"Brier avg: {scored['brier_avg'] or 'N/A':>6} | "
            f"Bracket pts: {scored['bracket_points']:4d}"
        )

    # Sort by: bracket_points desc, accuracy desc, brier_avg asc.
    models_scored.sort(
        key=lambda m: (
            -m["bracket_points"],
            -m["accuracy"],
            m["brier_avg"] if m["brier_avg"] is not None else 999,
        )
    )

    # Add rank.
    for i, m in enumerate(models_scored):
        m["rank"] = i + 1

    leaderboard = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_results": len(results),
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
                "brier_avg": m["brier_avg"],
                "brier_total": m["brier_total"],
                "bracket_points": m["bracket_points"],
                "champion": m["champion"],
                "runner_up": m["runner_up"],
                "third_place": m["third_place"],
                "fourth_place": m["fourth_place"],
            }
            for m in models_scored
        ],
        # Daily history for sparklines (append-only).
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
                "accuracy": m["accuracy"],
                "brier_avg": m["brier_avg"],
                "bracket_points": m["bracket_points"],
                "correct_outcomes": m["correct_outcomes"],
            }
            for m in models_scored
        ],
    }

    # Replace if today already exists, otherwise append.
    history = leaderboard["history"]
    replaced = False
    for i, h in enumerate(history):
        if h["date"] == today:
            history[i] = today_snapshot
            replaced = True
            break
    if not replaced:
        history.append(today_snapshot)

    # Write output.
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
