"""Re-empalmar (reconcile) saved results with the resolved knockout bracket.

BUG 1/2 fix. Knockout results can be fetched *before* the bracket is resolved:
when football-data.org reports "BRA 2-1 JPN" the tournament fixture for match 76
still reads ``home_team: "1C"`` / ``away_team: "2F"`` (placeholders), so the
fetcher cannot find the fixture and saves the result with
``match_id: null, fd_id: null, stage: "LAST_32"``.

Once :mod:`update_qualified` resolves the bracket (slot ``1C`` -> ``BRA`` …),
this module walks every saved result and, for any entry that still has a null
``match_id``, joins it to the resolved bracket **by the unordered team pair**
``{home_team, away_team}`` and back-fills the canonical ``match_id`` / ``fd_id``
/ ``stage`` / ``round``. It also normalises *every* result's ``stage`` through
the single taxonomy point in :mod:`utils` (e.g. ``LAST_32`` -> ``R32``).

The operation is idempotent: a result that already carries a ``match_id`` and a
canonical stage is left untouched, so re-running reconcile reports 0 changes.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")


def _pair_key(home: str, away: str):
    """Unordered team-pair key (orientation-independent join key)."""
    if not home or not away:
        return None
    return frozenset((home, away))


def build_resolved_index(tournament: dict) -> dict:
    """Map ``frozenset({home, away})`` -> resolved bracket fixture.

    Only bracket entries whose *both* slots have resolved into real FIFA team
    codes (present in the group rosters) are indexed; entries still holding
    placeholders ("2A", "W73", "3rd(A/B/C)", …) are skipped.
    """
    fifa_codes = utils.get_fifa_codes(tournament)
    index = {}
    for m in tournament.get("knockout_bracket", []):
        home = m.get("home_team")
        away = m.get("away_team")
        if home not in fifa_codes or away not in fifa_codes:
            continue
        key = _pair_key(home, away)
        if key is not None:
            index[key] = m
    return index


def _reconcile_match(match: dict, resolved_index: dict) -> bool:
    """Reconcile a single result entry in place. Returns True if it changed."""
    changed = False

    # 1) Always normalise the stage through the single taxonomy point.
    canonical_stage = utils.normalize_stage(match.get("stage"), match.get("match_id"))
    if canonical_stage and match.get("stage") != canonical_stage:
        match["stage"] = canonical_stage
        changed = True

    # 2) Back-fill an unresolved knockout result by its team pair.
    if match.get("match_id") is None:
        key = _pair_key(match.get("home_team"), match.get("away_team"))
        fixture = resolved_index.get(key) if key is not None else None
        if fixture is not None:
            match["match_id"] = fixture.get("match_id")
            # Prefer a fd_id we already have; otherwise take the bracket's
            # (which may legitimately still be null if the API never gave one).
            if match.get("fd_id") is None and fixture.get("fd_id") is not None:
                match["fd_id"] = fixture.get("fd_id")
            new_stage = utils.normalize_stage(
                fixture.get("round"), fixture.get("match_id")
            )
            if new_stage and match.get("stage") != new_stage:
                match["stage"] = new_stage
            # Carry the bracket round label for convenience.
            if fixture.get("round") and match.get("round") != fixture.get("round"):
                match["round"] = fixture.get("round")
            changed = True

    return changed


def reconcile_results(results_dir: str = RESULTS_DIR,
                      tournament_path: str = TOURNAMENT_PATH) -> int:
    """Reconcile every saved result file against the resolved bracket.

    Returns the number of result entries that were modified.
    """
    try:
        with open(tournament_path, "r", encoding="utf-8") as f:
            tournament = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0

    resolved_index = build_resolved_index(tournament)
    total_changed = 0

    for filepath in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        is_list = isinstance(data, list)
        matches = data if is_list else data.get("matches", [])
        file_changed = 0
        for m in matches:
            if _reconcile_match(m, resolved_index):
                file_changed += 1

        if file_changed:
            total_changed += file_changed
            if not is_list:
                data["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"reconciled {file_changed} match(es) in {os.path.basename(filepath)}")

    if total_changed == 0:
        print("reconcile: nothing to do (already consistent)")
    return total_changed


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile saved results with the resolved knockout bracket"
    )
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument("--tournament", default=TOURNAMENT_PATH)
    args = parser.parse_args()
    n = reconcile_results(args.results_dir, args.tournament)
    print(f"reconcile complete: {n} match(es) updated")


if __name__ == "__main__":
    main()
