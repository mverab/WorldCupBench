#!/usr/bin/env python3
"""Consolidate data/results/*.json into docs/data/results.json for the dashboard."""

import glob
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "data", "results.json")


def main():
    matches = []
    pattern = os.path.join(RESULTS_DIR, "*.json")
    for filepath in sorted(glob.glob(pattern)):
        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue
        matches.extend(data.get("matches", []) if isinstance(data, dict) else data)

    by_id = {str(m["match_id"]): m for m in matches if m.get("match_id") is not None}
    out = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "matches": list(by_id.values()),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    print(f"Wrote {len(out['matches'])} results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
