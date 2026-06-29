"""Knockout orchestration loop — the central fetch<->resolve<->reconcile engine.

BUG 1/2 fix. The knockout stage has a chicken-and-egg dependency:

  * the fetcher can only file a knockout result under its canonical ``match_id``
    once the bracket fixture holds *real* team names, but
  * the bracket only resolves a slot (e.g. ``1C`` -> ``BRA``) after the feeding
    matches have been fetched and scored.

This module breaks the cycle by iterating to a fixpoint:

    repeat:
        update_qualified   # resolve group seeds + propagate W##/L## winners
        reconcile_results  # back-fill match_id/fd_id for results saved as null
        fetch_results      # (if an API key is set) pull new results, now
                           # empalmados against the freshly-resolved bracket
    until the tournament + results stop changing.

Each pass propagates one more knockout round (R32 -> R16 -> QF -> SF -> Final),
so a handful of iterations always converges. It runs fine fully offline (no API
key): the update<->reconcile pair alone re-empalma already-saved results such as
the BRA-JPN octavo that was first stored with ``match_id: null``.
"""

import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import update_qualified  # noqa: E402
import reconcile_results  # noqa: E402
import fetch_results  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")

MAX_ITERS = 10


def _state_hash(results_dir: str, tournament_path: str) -> str:
    """Stable hash of the bracket resolution + every saved result.

    Used to detect the fixpoint: when a full iteration leaves both the resolved
    bracket and the stored results unchanged we are done.
    """
    h = hashlib.sha256()

    try:
        with open(tournament_path, "r", encoding="utf-8") as f:
            tournament = json.load(f)
        bracket = [
            (m.get("match_id"), m.get("home_team"), m.get("away_team"))
            for m in tournament.get("knockout_bracket", [])
        ]
        h.update(json.dumps(bracket, sort_keys=True).encode("utf-8"))
    except (json.JSONDecodeError, OSError):
        pass

    for filepath in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        matches = data if isinstance(data, list) else data.get("matches", [])
        summary = [
            (
                m.get("match_id"), m.get("fd_id"), m.get("home_team"),
                m.get("away_team"), m.get("stage"), m.get("outcome"),
                (m.get("score") or {}).get("home"), (m.get("score") or {}).get("away"),
            )
            for m in matches
        ]
        h.update(json.dumps(summary, sort_keys=True).encode("utf-8"))

    return h.hexdigest()


def _fetch_and_save(api_key: str, results_dir: str):
    """Fetch all finished matches from the API and merge them into results."""
    try:
        matches = fetch_results.fetch_from_api(api_key, date=None, fetch_all=True)
    except Exception as exc:  # network/credential issues must not abort the loop
        print(f"orchestrate: API fetch failed ({exc}); continuing offline")
        return
    if matches:
        fetch_results.save_results(matches, results_dir)


def orchestrate(results_dir: str = RESULTS_DIR,
                tournament_path: str = TOURNAMENT_PATH,
                max_iters: int = MAX_ITERS,
                use_api: bool = True) -> int:
    """Run the resolve/reconcile/fetch loop to a fixpoint.

    Returns the number of iterations performed.
    """
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "") if use_api else ""
    if not api_key:
        print("orchestrate: no FOOTBALL_DATA_API_KEY — running offline "
              "(resolve + reconcile only)")

    prev_state = None
    iterations = 0
    for i in range(1, max_iters + 1):
        iterations = i
        # 1) Resolve the bracket from everything we currently know.
        update_qualified.update_tournament(results_dir, tournament_path)
        # 2) Back-fill results that were saved before the bracket resolved.
        reconcile_results.reconcile_results(results_dir, tournament_path)
        # 3) Pull fresh results; they now empalman against the resolved bracket.
        if api_key:
            _fetch_and_save(api_key, results_dir)

        state = _state_hash(results_dir, tournament_path)
        if state == prev_state:
            print(f"orchestrate: fixpoint reached after {i} iteration(s)")
            break
        prev_state = state
    else:
        print(f"orchestrate: stopped at max {max_iters} iterations (no fixpoint)")

    # Final resolve so the bracket reflects the very last reconcile/fetch.
    update_qualified.update_tournament(results_dir, tournament_path)
    return iterations


def main():
    parser = argparse.ArgumentParser(
        description="Knockout fetch<->resolve<->reconcile orchestration loop"
    )
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument("--tournament", default=TOURNAMENT_PATH)
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    parser.add_argument(
        "--no-api", action="store_true",
        help="Skip the API fetch step (resolve + reconcile only).",
    )
    args = parser.parse_args()
    orchestrate(
        args.results_dir, args.tournament, args.max_iters, use_api=not args.no_api
    )


if __name__ == "__main__":
    main()
