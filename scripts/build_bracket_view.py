#!/usr/bin/env python3
"""Build docs/data/bracket.json — the knockout-tree view for the dashboard.

Combines three sources into a single file the bracket UI can render directly:

  1. the *real* knockout bracket from ``data/tournament.json`` (resolved team
     names, dates, venues, feeds_into links),
  2. the *real* results (score / winner) for every played knockout match, and
  3. the *models' predictions*, expressed as advancement picks: for each real
     match, how many models predicted the home / away team to reach the next
     round (i.e. to win that match), plus a per-model advancement summary.

Because each model predicted its own bracket (different teams in each slot),
the only well-defined per-matchup comparison is set-membership advancement —
"did the model expect team X to reach this round?" — which is exactly the
``advancement_accuracy`` metric. The bracket UI therefore shows, on the real
tree, how strongly the field backed each surviving team.
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import advancement  # noqa: E402
import score as score_mod  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions", "pre-tournament")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "data", "leaderboard.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "data", "bracket.json")

ROUNDS_ORDER = ["R32", "R16", "QF", "SF", "FINAL", "THIRD_PLACE"]

# For a match in stage S, the team that wins it reaches TARGET_ROUND[S]; that is
# the advancement set we compare the model picks against.
TARGET_ROUND = {
    "R32": "R16",
    "R16": "QF",
    "QF": "SF",
    "SF": "FINAL",
    "FINAL": "CHAMPION",
}


def _load_predictions() -> list:
    preds = []
    for f in sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "*_prediction.json"))):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                preds.append(json.load(fp))
        except (json.JSONDecodeError, OSError):
            continue
    return preds


def _load_leaderboard_advancement() -> dict:
    """Return {model_name: advancement_accuracy} from the leaderboard, if any."""
    out = {}
    try:
        with open(LEADERBOARD_PATH, "r", encoding="utf-8") as fp:
            lb = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return out
    for m in lb.get("models", []):
        adv = m.get("advancement_accuracy")
        if adv is not None:
            out[m.get("model")] = adv
    return out


def _result_for(results: dict, match_id) -> dict:
    res = results.get(str(match_id))
    if res is not None:
        return res
    canonical = score_mod.utils.stage_from_match_id(match_id)
    if canonical == "FINAL":
        return results.get("FINAL")
    if canonical == "THIRD_PLACE":
        return results.get("THIRD")
    return None


def build_bracket(results_dir: str = RESULTS_DIR,
                  tournament_path: str = TOURNAMENT_PATH) -> dict:
    with open(tournament_path, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    results = score_mod.load_results(results_dir)
    predictions = _load_predictions()
    lb_adv = _load_leaderboard_advancement()

    # Pre-compute each model's predicted advancement sets and third-place pick.
    model_predicted = []
    for pred in predictions:
        name = pred.get("model") or pred.get("model_name") or "Unknown"
        model_predicted.append(
            {
                "model": name,
                "advancement": advancement.predicted_advancement(pred),
                "third": pred.get("third") or pred.get("third_place")
                or (pred.get("final_standings") or {}).get("third_place"),
                "champion": pred.get("champion")
                or (pred.get("final_standings") or {}).get("champion"),
            }
        )

    matches = []
    for fixture in tournament.get("knockout_bracket", []):
        match_id = fixture.get("match_id")
        stage = score_mod.utils.normalize_stage(fixture.get("round"), match_id)
        home = fixture.get("home_team")
        away = fixture.get("away_team")

        result = _result_for(results, match_id)
        played = bool(result and result.get("outcome") in ("home", "away", "draw"))
        winner = None
        if played:
            if result.get("outcome") == "home":
                winner = result.get("home_team")
            elif result.get("outcome") == "away":
                winner = result.get("away_team")

        # How many models backed each surviving team to advance from this match.
        target = TARGET_ROUND.get(stage)
        home_models, away_models = [], []
        if stage == "THIRD_PLACE":
            for mp in model_predicted:
                if mp["third"] and mp["third"] == home:
                    home_models.append(mp["model"])
                if mp["third"] and mp["third"] == away:
                    away_models.append(mp["model"])
        elif target:
            for mp in model_predicted:
                reached = mp["advancement"].get(target, set())
                if home and home in reached:
                    home_models.append(mp["model"])
                if away and away in reached:
                    away_models.append(mp["model"])

        matches.append(
            {
                "match_id": match_id,
                "stage": stage,
                "round": fixture.get("round"),
                "home_team": home,
                "away_team": away,
                "home_slot": fixture.get("home_slot"),
                "away_slot": fixture.get("away_slot"),
                "date": fixture.get("date"),
                "venue": fixture.get("venue"),
                "feeds_into": fixture.get("feeds_into"),
                "played": played,
                "score": result.get("score") if played else None,
                "outcome": result.get("outcome") if played else None,
                "winner": winner,
                "target_round": target if stage != "THIRD_PLACE" else "THIRD_PLACE",
                "model_picks": {
                    "home": {"count": len(home_models), "models": home_models},
                    "away": {"count": len(away_models), "models": away_models},
                },
            }
        )

    # Per-model advancement summary (re-uses leaderboard detail when available).
    model_advancement = []
    for mp in model_predicted:
        model_advancement.append(
            {
                "model": mp["model"],
                "advancement_accuracy": lb_adv.get(mp["model"]),
            }
        )

    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "rounds_order": ROUNDS_ORDER,
        "n_models": len(model_predicted),
        "matches": matches,
        "model_advancement": model_advancement,
    }


def main():
    bracket = build_bracket()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bracket, f, ensure_ascii=False, indent=2)
    print(f"Wrote bracket view ({len(bracket['matches'])} matches) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
