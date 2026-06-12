#!/usr/bin/env python3
"""Recover knockout bracket and final standings from the pre-migration commit.

PR #14 (commit a99af4f) migrated prediction files to the freeze-v3 schema but
only preserved group_stage_matches, discarding the knockout bracket and final
standings. The original data still exists intact in commit 64f3703.

This script merges, for each current prediction file in
predictions/pre-tournament/:

  - group_qualifiers
  - knockout_stage   (renamed/normalized to the `bracket` shape score.py expects)
  - final_standings  (promoted to top-level champion/runner_up/third/fourth_place)

The current group_matches and model metadata are left untouched.
"""

import argparse
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTIONS_DIR = os.path.join(BASE_DIR, "predictions", "pre-tournament")
OLD_COMMIT = "64f3703046febbce8db2caa22edb2ee14945573d"


def list_old_prediction_files() -> list:
    """Return basenames of all prediction JSONs in the old commit."""
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "-r", f"{OLD_COMMIT}:predictions/pre-tournament"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith("_prediction.json")]


# Mapping from the old knockout_stage keys to the bracket keys used by score.py.
ROUND_KEY_MAP = {
    "round_of_32": "R32",
    "round_of_16": "R16",
    "quarter_finals": "QF",
    "semi_finals": "SF",
    "final": "final",
    "third_place_match": "third_place",
}


def git_show_old(basename: str) -> dict:
    """Read a prediction file as it existed in OLD_COMMIT."""
    full_ref = f"{OLD_COMMIT}:predictions/pre-tournament/{basename}"
    result = subprocess.run(
        ["git", "show", full_ref],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def find_old_basename(current_basename: str, old_files: list) -> str:
    """Find the old filename that corresponds to the current (lowercased) file."""
    current_lower = current_basename.lower()
    candidates = [f for f in old_files if f.lower() == current_lower]
    if len(candidates) == 1:
        return candidates[0]
    # Fallback: match by stripping common suffixes and comparing lowercased stems.
    current_stem = current_basename.replace("_prediction.json", "").lower()
    for old in old_files:
        old_stem = old.replace("_prediction.json", "").lower()
        if old_stem == current_stem:
            return old
    raise FileNotFoundError(f"No old prediction file matches {current_basename}")


def canonical_match_id(old_match_id: str) -> str:
    """Extract the numeric match id the tournament uses (e.g. 'R32-73' -> '73')."""
    if old_match_id is None:
        return None
    # Old ids are like 'R32-73', 'R16-89', 'QF-97', 'FINAL', 'THIRD'.
    # We need the number after the dash, not the round digits.
    m = re.search(r"-(\d+)$", str(old_match_id))
    if m:
        return m.group(1)
    return str(old_match_id)


def compute_winner(match: dict) -> str:
    """Return the FIFA code of the predicted winner for a knockout match."""
    predicted = match.get("predicted_result")
    if predicted == "home":
        return match.get("home_team")
    if predicted == "away":
        return match.get("away_team")
    # Fallback to max probability if predicted_result is missing or a draw.
    probs = match.get("probs", {})
    if probs:
        best = max(probs, key=probs.get)
        if best == "home":
            return match.get("home_team")
        if best == "away":
            return match.get("away_team")
    return None


def convert_knockout_match(match: dict) -> dict:
    """Normalize an old knockout match dict for score.py."""
    converted = {
        "match_id": canonical_match_id(match.get("match_id")),
        "match": canonical_match_id(match.get("match_id")),
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "predicted_result": match.get("predicted_result"),
        "predicted_score": match.get("predicted_score"),
        "probs": match.get("probs"),
        "winner": compute_winner(match),
    }
    return converted


def convert_knockout_stage(knockout_stage: dict) -> dict:
    """Convert old knockout_stage to the bracket shape score.py consumes."""
    bracket = {}
    for old_key, new_key in ROUND_KEY_MAP.items():
        value = knockout_stage.get(old_key)
        if value is None:
            continue
        if isinstance(value, list):
            bracket[new_key] = [convert_knockout_match(m) for m in value]
        elif isinstance(value, dict):
            bracket[new_key] = convert_knockout_match(value)
    return bracket


def merge_prediction(current_path: str, old_files: list, dry_run: bool = False) -> dict:
    """Merge old bracket data into a current prediction file."""
    basename = os.path.basename(current_path)
    old_basename = find_old_basename(basename, old_files)

    with open(current_path, "r", encoding="utf-8") as f:
        current = json.load(f)

    old = git_show_old(old_basename)

    # Keep current group_matches and model metadata intact.
    merged = dict(current)

    # Copy group qualifiers.
    if "group_qualifiers" in old:
        merged["group_qualifiers"] = old["group_qualifiers"]

    # Normalize knockout stage to bracket shape.
    if "knockout_stage" in old:
        merged["bracket"] = convert_knockout_stage(old["knockout_stage"])

    # Promote final_standings to top-level keys used by score.py.
    final_standings = old.get("final_standings", {})
    if final_standings.get("champion"):
        merged["champion"] = final_standings["champion"]
    if final_standings.get("runner_up"):
        merged["runner_up"] = final_standings["runner_up"]
    if final_standings.get("third_place"):
        merged["third"] = final_standings["third_place"]
    if final_standings.get("fourth_place"):
        merged["fourth_place"] = final_standings["fourth_place"]

    # Avoid double source of truth: remove the nested final_standings copy.
    merged.pop("final_standings", None)

    if not dry_run:
        with open(current_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return merged


def count_knockout_matches(bracket: dict) -> int:
    """Return the total number of knockout matches in a bracket."""
    total = 0
    for key in ("R32", "R16", "QF", "SF"):
        total += len(bracket.get(key, []))
    if bracket.get("third_place"):
        total += 1
    if bracket.get("final"):
        total += 1
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Recover knockout brackets from commit 64f3703 into current prediction files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    args = parser.parse_args()

    files = sorted(
        f
        for f in os.listdir(PREDICTIONS_DIR)
        if f.endswith("_prediction.json")
    )

    if not files:
        print("No prediction files found", file=sys.stderr)
        sys.exit(1)

    print(f"{'DRY RUN' if args.dry_run else 'Merging'} {len(files)} predictions...")
    old_files = list_old_prediction_files()
    for filename in files:
        path = os.path.join(PREDICTIONS_DIR, filename)
        merged = merge_prediction(path, old_files, dry_run=args.dry_run)
        model = merged.get("model") or merged.get("model_name") or filename
        bracket = merged.get("bracket", {})
        n_ko = count_knockout_matches(bracket)
        print(
            f"  {model:22s} | champion: {merged.get('champion') or '—':4s} | "
            f"knockout matches: {n_ko:2d}"
        )


if __name__ == "__main__":
    main()
