#!/usr/bin/env python3
"""Generate predictions_summary.json from all pre-tournament prediction files.

Also merges the qualifier_accuracy detail (hits, score, missed teams,
false positives, ...) from data/leaderboard.json so the dashboard can show the
"Clasificados acertados (n/32)" column with hover details.
"""

import glob
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEADERBOARD_PATH = os.path.join(BASE_DIR, "data", "leaderboard.json")


def _load_qualifier_details() -> dict:
    """Return {model_name: qualifier_accuracy} from the leaderboard, if present."""
    details = {}
    try:
        with open(LEADERBOARD_PATH, "r", encoding="utf-8") as fp:
            lb = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return details
    for m in lb.get("models", []):
        qa = m.get("qualifier_accuracy")
        if qa is not None:
            details[m.get("model")] = qa
    return details


def main():
    qual_details = _load_qualifier_details()
    preds = []
    for f in sorted(glob.glob(os.path.join(BASE_DIR, "predictions/pre-tournament/*_prediction.json"))):
        with open(f) as fp:
            d = json.load(fp)
        model_name = d.get("model") or d.get("model_name")
        preds.append(
            {
                "model_name": model_name,
                "model_id": d.get("model_id"),
                "champion": d.get("champion") or d.get("final_standings", {}).get("champion"),
                "runner_up": d.get("runner_up") or d.get("final_standings", {}).get("runner_up"),
                "third_place": d.get("third") or d.get("third_place") or d.get("final_standings", {}).get("third_place"),
                "fourth_place": d.get("fourth_place") or d.get("final_standings", {}).get("fourth_place"),
                "qualifier_accuracy": qual_details.get(model_name),
            }
        )

    out_path = os.path.join(BASE_DIR, "docs/data/predictions_summary.json")
    with open(out_path, "w") as fp:
        json.dump(preds, fp, indent=2)

    print(f"Wrote {len(preds)} prediction summaries")


if __name__ == "__main__":
    main()
