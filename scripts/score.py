"""WorldCupBench scoring engine (freeze-v3).

Reads prediction JSONs and actual results, computes per-model metrics, and
writes data/leaderboard.json.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils
import advancement

BASE_DIR = utils.BASE_DIR
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
PREDICTIONS_DIR = os.path.join(utils.PREDICTIONS_DIR, "pre-tournament")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "data", "leaderboard.json")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
POLYMARKET_DIR = os.path.join(BASE_DIR, "data", "polymarket")

TOTAL_QUALIFIERS = 32

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
    """Load actual match results from data/results/*.json.

    Results are indexed by every key a prediction might use to look them up:
      * ``str(fd_id)`` and ``str(match_id)`` (the canonical integer ids), and
      * the string sentinels ``"FINAL"`` / ``"THIRD"`` used by the frozen
        prediction brackets — bridged here from the canonical stage so the
        final (match_id 104) and third-place (103) results are scored even
        though predictions key them as "FINAL"/"THIRD".
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
            if not _has_result(m):
                continue
            for key in ("fd_id", "match_id"):
                val = m.get(key)
                if val is not None:
                    results[str(val)] = m
            # Bridge canonical final/third-place results to the "FINAL"/"THIRD"
            # sentinel keys the prediction brackets use.
            canonical = utils.normalize_stage(m.get("stage"), m.get("match_id"))
            if canonical == "FINAL":
                results.setdefault("FINAL", m)
            elif canonical == "THIRD_PLACE":
                results.setdefault("THIRD", m)
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
    """Canonical stage for a match_id (delegates to the single taxonomy point).

    Returns the canonical label (GROUP_STAGE, R32, R16, QF, SF, THIRD_PLACE,
    FINAL) or ``"UNKNOWN"`` when the id cannot be resolved.
    """
    return utils.stage_from_match_id(match_id) or "UNKNOWN"


def _brier_group(probs: dict, actual: str) -> float:
    return sum(
        (probs.get(o, 0.0) - (1.0 if o == actual else 0.0)) ** 2
        for o in ("home", "draw", "away")
    )


def _brier_knockout(
    probs: dict, predicted_winner: str, home_team: str, away_team: str, actual_winner: str
) -> float:
    """Bernoulli Brier for the predicted advancing team."""
    if predicted_winner == home_team:
        p = probs.get("home", 0.0)
    elif predicted_winner == away_team:
        p = probs.get("away", 0.0)
    else:
        return None
    y = 1.0 if predicted_winner == actual_winner else 0.0
    return (p - y) ** 2


def _actual_winner(result: dict) -> str:
    outcome = result.get("outcome")
    if outcome == "home":
        return result.get("home_team")
    if outcome == "away":
        return result.get("away_team")
    return None


def _score_group_match(pred_match: dict, result: dict, stage: str) -> dict:
    actual_outcome = result.get("outcome")
    probs = pred_match.get("probs", {})
    predicted = pred_match.get("predicted_result")
    return {
        "match_id": pred_match.get("match_id"),
        "stage": stage,
        "brier": _brier_group(probs, actual_outcome),
        "predicted": predicted,
        "actual": actual_outcome,
        "hit": predicted == actual_outcome,
    }


def _score_knockout_match(pred_match: dict, result: dict, stage: str) -> dict:
    actual_winner = _actual_winner(result)
    if actual_winner is None:
        return None
    predicted_winner = pred_match.get("winner")
    brier = _brier_knockout(
        pred_match.get("probs", {}),
        predicted_winner,
        pred_match.get("home_team"),
        pred_match.get("away_team"),
        actual_winner,
    )
    if brier is None:
        return None
    return {
        "match_id": pred_match.get("match_id"),
        "stage": stage,
        "brier": brier,
        "predicted": predicted_winner,
        "actual": actual_winner,
        "hit": predicted_winner == actual_winner,
    }


def _iterate_knockout_matches(bracket: dict):
    for round_key in ("R32", "R16", "QF", "SF"):
        for m in bracket.get(round_key, []):
            yield m
    for key in ("third_place", "final"):
        m = bracket.get(key)
        if m:
            yield m


def load_qualified(tournament_path: str = TOURNAMENT_PATH) -> dict:
    """Build the real-qualifiers lookup from the tournament 'qualified' block.

    Returns a dict with:
      * ``teams``       – set of qualified team codes (real)
      * ``positions``   – {team: "1st"|"2nd"|"3rd"} for qualified teams
      * ``best_thirds`` – set of the 8 best third-placed team codes
      * ``ready``       – True once every group is complete (full 32 known)
    """
    empty = {"teams": set(), "positions": {}, "best_thirds": set(), "ready": False}
    try:
        with open(tournament_path, "r", encoding="utf-8") as f:
            tournament = json.load(f)
    except (json.JSONDecodeError, OSError):
        return empty
    qual = tournament.get("qualified")
    if not qual:
        return empty

    teams = set(qual.get("teams", []))
    best_thirds = set(qual.get("best_thirds", []))
    positions = {}
    for grp, entry in qual.get("by_group", {}).items():
        if entry.get("1st"):
            positions[entry["1st"]] = "1st"
        if entry.get("2nd"):
            positions[entry["2nd"]] = "2nd"
    for t in best_thirds:
        positions[t] = "3rd"
    return {
        "teams": teams,
        "positions": positions,
        "best_thirds": best_thirds,
        "ready": bool(qual.get("all_groups_complete", False)),
    }


def _predicted_qualifiers(prediction: dict) -> dict:
    """Extract a model's predicted qualifiers as {team: predicted_position}."""
    gq = prediction.get("group_qualifiers", {}) or {}
    predicted = {}
    for info in gq.get("first_place", []):
        code = info.get("team_code")
        if code:
            predicted[code] = "1st"
    for info in gq.get("second_place", []):
        code = info.get("team_code")
        if code:
            predicted.setdefault(code, "2nd")
    for info in gq.get("best_third_place", []):
        code = info.get("team_code")
        if code:
            predicted.setdefault(code, "3rd")
    return predicted


def score_qualifiers(prediction: dict, qualified: dict) -> dict:
    """Score a model's predicted set of 32 qualifiers against the real set.

    ``qualified`` is the lookup produced by :func:`load_qualified`.

    Returns a dict with:
      * ``hits``                – |predicted ∩ real| (teams correctly qualified)
      * ``score``               – hits / 32 (main metric, 0.0 - 1.0)
      * ``with_position_bonus`` – hits where the predicted position
                                  (1st/2nd/3rd) also matched the real position
      * ``third_place_hits``    – how many of the 8 real best thirds were
                                  predicted to qualify
      * ``missed``              – real qualified teams the model did NOT predict
      * ``false_positives``     – teams the model predicted that did NOT qualify
      * ``predicted_count`` / ``qualified_count`` – set sizes
      * ``ready``               – whether the full real set is known yet
    """
    real_teams = set(qualified.get("teams", set()))
    real_positions = qualified.get("positions", {})
    real_thirds = set(qualified.get("best_thirds", set()))

    predicted = _predicted_qualifiers(prediction)
    predicted_set = set(predicted.keys())

    hit_teams = predicted_set & real_teams
    hits = len(hit_teams)

    with_position_bonus = sum(
        1 for t in hit_teams if predicted.get(t) == real_positions.get(t)
    )
    third_place_hits = len(predicted_set & real_thirds)

    missed = sorted(real_teams - predicted_set)
    false_positives = sorted(predicted_set - real_teams)

    return {
        "hits": hits,
        "score": round(hits / TOTAL_QUALIFIERS, 6),
        "with_position_bonus": with_position_bonus,
        "third_place_hits": third_place_hits,
        "missed": missed,
        "false_positives": false_positives,
        "predicted_count": len(predicted_set),
        "qualified_count": len(real_teams),
        "ready": bool(qualified.get("ready", False)),
    }


def score_model(prediction: dict, results: dict, qualified: dict = None,
                real_advancement: dict = None) -> dict:
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
        scored = _score_group_match(gm, result, stage)
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
        scored = _score_knockout_match(km, result, stage)
        if scored is None:
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
        brier_total = (
            n_group * (brier_group / 2.0) + n_ko * brier_knockout
        ) / (n_group + n_ko)

    qual_lookup = qualified if qualified is not None else {
        "teams": set(), "positions": {}, "best_thirds": set(), "ready": False
    }
    qualifier_detail = score_qualifiers(prediction, qual_lookup)

    adv_lookup = real_advancement if real_advancement is not None else {}
    advancement_detail = advancement.score_advancement(prediction, adv_lookup)

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
        "qualifier_accuracy": qualifier_detail,
        "advancement_accuracy": advancement_detail,
    }


def _compute_roi(prediction: dict, results: dict) -> tuple:
    """Placeholder for real Polymarket ROI.

    Once data/polymarket/market_map.json maps match_id -> Polymarket market,
    implement Gamma price settlement here. Until then, report no market data.
    """
    return None, "no_market_data"


def generate_leaderboard(
    results_dir: str = RESULTS_DIR,
    output_path: str = LEADERBOARD_PATH,
    predictions: list = None,
    tournament_path: str = TOURNAMENT_PATH,
) -> dict:
    results = load_results(results_dir)
    predictions = load_predictions() if predictions is None else predictions
    qualified = load_qualified(tournament_path)
    real_advancement = advancement.compute_real_advancement(results)

    if not predictions:
        print("No prediction files found")
        return {}

    models = []
    for pred in predictions:
        scored = score_model(pred, results, qualified, real_advancement)
        roi, roi_status = _compute_roi(pred, results)
        scored["roi"] = roi
        scored["roi_status"] = roi_status
        models.append(scored)

    models.sort(
        key=lambda m: (
            m["brier_total"] if m["brier_total"] is not None else float("inf"),
            -m["quiniela_points"],
            m["model"],
        )
    )

    advancement_rounds_ready = [
        rnd for rnd in advancement.ROUND_ORDER
        if real_advancement.get(rnd, {}).get("ready")
    ]

    leaderboard = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_results": len({id(m) for m in results.values()}),
        "total_models": len(models),
        "qualifiers_known": len(qualified.get("teams", set())),
        "qualifiers_ready": bool(qualified.get("ready", False)),
        "advancement_rounds_ready": advancement_rounds_ready,
        "models": models,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

    print(f"Leaderboard written to {output_path}")
    return leaderboard


def main():
    parser = argparse.ArgumentParser(description="WorldCupBench scoring engine")
    parser.add_argument(
        "--results-dir", default=RESULTS_DIR, help="Directory with actual results"
    )
    parser.add_argument(
        "--output", default=LEADERBOARD_PATH, help="Output leaderboard JSON path"
    )
    args = parser.parse_args()
    generate_leaderboard(args.results_dir, args.output)


if __name__ == "__main__":
    main()
