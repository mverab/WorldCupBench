#!/usr/bin/env python3
"""Generate predictions_summary.json from all pre-tournament prediction files."""

import glob
import json


def main():
    preds = []
    for f in sorted(glob.glob("predictions/pre-tournament/*_prediction.json")):
        with open(f) as fp:
            d = json.load(fp)
        preds.append(
            {
                "model_name": d.get("model") or d.get("model_name"),
                "model_id": d.get("model_id"),
                "champion": d.get("champion") or d.get("final_standings", {}).get("champion"),
                "runner_up": d.get("runner_up") or d.get("final_standings", {}).get("runner_up"),
                "third_place": d.get("third") or d.get("third_place") or d.get("final_standings", {}).get("third_place"),
                "fourth_place": d.get("fourth_place") or d.get("final_standings", {}).get("fourth_place"),
            }
        )

    with open("docs/data/predictions_summary.json", "w") as fp:
        json.dump(preds, fp, indent=2)

    print(f"Wrote {len(preds)} prediction summaries")


if __name__ == "__main__":
    main()
