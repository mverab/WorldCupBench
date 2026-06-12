"""WorldCupBench — Fetch Real Match Results.

Ingests actual World Cup 2026 match results into data/results/YYYY-MM-DD.json.
Supports two modes:
  1. Manual: reads from a hand-edited JSON file.
  2. API: fetches from football-data.org (free tier, key via env FOOTBALL_DATA_API_KEY).

Usage:
    # Manual mode (create/edit data/results/2026-06-11.json by hand, then run score.py)
    python scripts/fetch_results.py --manual

    # API mode
    export FOOTBALL_DATA_API_KEY="your_key"
    python scripts/fetch_results.py

    # Fetch specific date
    python scripts/fetch_results.py --date 2026-06-11

    # Fetch all played matches
    python scripts/fetch_results.py --all
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    requests = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils  # noqa: E402

RESULTS_DIR = os.path.join(utils.BASE_DIR, "data", "results")
TOURNAMENT_PATH = utils.TOURNAMENT_PATH

# football-data.org — FIFA World Cup 2026 competition ID.
COMPETITION_ID = 2000
SEASON_ID = 2398
API_BASE = "https://api.football-data.org/v4"


def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_tournament_schedule() -> dict:
    """Load tournament.json and build a mapping of match_id -> match info."""
    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    schedule = {}
    for match in data.get("matches", []):
        mid = match.get("match_id")
        if mid:
            schedule[mid] = match

    for match in data.get("knockout_bracket", []):
        mid = match.get("match_id")
        if mid:
            schedule[mid] = match

    return schedule


def _stage_label(match_id) -> str:
    """Derive the canonical stage label from an integer match_id (1..104)."""
    try:
        mid = int(match_id)
    except (TypeError, ValueError):
        return ""
    if 1 <= mid <= 72:
        return "GROUP_STAGE"
    if 73 <= mid <= 88:
        return "R32"
    if 89 <= mid <= 96:
        return "R16"
    if 97 <= mid <= 100:
        return "QF"
    if 101 <= mid <= 102:
        return "SF"
    if mid == 103:
        return "THIRD_PLACE"
    if mid == 104:
        return "FINAL"
    return ""


def _outcome_from_score(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    elif away_goals > home_goals:
        return "away"
    return "draw"


def _match_tournament_fixture(api_match: dict, home: str, away: str, api_date: str, tournament: dict) -> dict:
    """Find the tournament fixture that corresponds to an API match.

    Matching is resilient to the football-data.org UTC date shift (a match that
    kicks off in the evening local time is reported on the *next* calendar day in
    UTC). We therefore prefer identity-based keys over the date:

      1. football-data match id  ==  tournament fd_id   (most reliable)
      2. ordered (home_team, away_team) pair            (unique per group stage)
      3. (home_team, away_team) pair + exact date       (last-resort tiebreaker)

    Returns the matching tournament match dict, or ``None``.
    """
    matches = tournament.get("matches", []) + tournament.get("knockout_bracket", [])

    api_id = api_match.get("id")
    if api_id is not None:
        for m in matches:
            if m.get("fd_id") == api_id:
                return m

    pair_hits = [
        m for m in matches
        if m.get("home_team") == home and m.get("away_team") == away
    ]
    if len(pair_hits) == 1:
        return pair_hits[0]
    if len(pair_hits) > 1:
        for m in pair_hits:
            if m.get("date") == api_date:
                return m
        return pair_hits[0]

    return None


def map_api_match(api_match: dict, tournament: dict) -> dict:
    """Map a single football-data.org match to our result format.

    The ``match_id``/``fd_id``/``date``/``stage``/``group`` fields are taken from
    the canonical tournament fixture when a match is found, so results are always
    filed under the correct (local) tournament date and carry the integer
    ``match_id`` the scorer and dashboard expect.
    """
    home = utils.API_TO_FIFA_TLA.get(
        api_match.get("homeTeam", {}).get("tla", ""),
        api_match.get("homeTeam", {}).get("tla", ""),
    )
    away = utils.API_TO_FIFA_TLA.get(
        api_match.get("awayTeam", {}).get("tla", ""),
        api_match.get("awayTeam", {}).get("tla", ""),
    )
    api_date = api_match.get("utcDate", "")[:10]
    score = api_match.get("score", {}).get("fullTime", {})

    fixture = _match_tournament_fixture(api_match, home, away, api_date, tournament)

    if fixture is not None:
        fd_id = fixture.get("fd_id")
        # match_id is canonically an integer in tournament.json; keep the type.
        match_id = fixture.get("match_id")
        # Prefer the tournament's canonical (local) date over the API's UTC date
        # so the result lands in the right data/results/YYYY-MM-DD.json file.
        date = fixture.get("date") or api_date
        stage = _stage_label(match_id) or api_match.get("stage", "")
        grp = fixture.get("group")
        group = f"GROUP_{grp}" if grp else api_match.get("group", "")
    else:
        fd_id = None
        match_id = None
        date = api_date
        stage = api_match.get("stage", "")
        group = api_match.get("group", "")

    home_goals = score.get("home")
    away_goals = score.get("away")
    outcome = None
    if home_goals is not None and away_goals is not None:
        outcome = _outcome_from_score(home_goals, away_goals)

    return {
        "fd_id": fd_id,
        "match_id": match_id,
        "home_team": home,
        "away_team": away,
        "score": {"home": home_goals, "away": away_goals},
        "outcome": outcome,
        "date": date,
        "stage": stage,
        "group": group,
    }


def fetch_from_api(api_key: str, date: str = None, fetch_all: bool = False) -> list:
    """Fetch results from football-data.org API."""
    if requests is None:
        _log("ERROR: 'requests' package not installed. Run: pip install requests")
        return []

    headers = {"X-Auth-Token": api_key}

    url = f"{API_BASE}/competitions/{COMPETITION_ID}/matches"
    params = {"status": "FINISHED"}
    if date and not fetch_all:
        params["dateFrom"] = date
        params["dateTo"] = date

    _log(f"Fetching from {url} with params={params}")
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    tournament = utils.load_tournament_data()
    matches = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None:
            continue
        matches.append(map_api_match(m, tournament))

    _log(f"Fetched {len(matches)} finished matches")
    return matches


def save_results(matches: list, results_dir: str = RESULTS_DIR):
    """Save results grouped by date."""
    os.makedirs(results_dir, exist_ok=True)

    by_date = {}
    for m in matches:
        date = m.get("date", "unknown")
        by_date.setdefault(date, []).append(m)

    for date, day_matches in by_date.items():
        filepath = os.path.join(results_dir, f"{date}.json")

        # Merge with existing file if present.
        existing = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                existing = data if isinstance(data, list) else data.get("matches", [])
            except (json.JSONDecodeError, OSError):
                pass

        # Merge keyed by fd_id when available, otherwise match_id.
        def _key(x):
            return x.get("fd_id") if x.get("fd_id") is not None else x.get("match_id")

        existing_by_key = {_key(e): e for e in existing}
        for m in day_matches:
            existing_by_key[_key(m)] = m
        merged = list(existing_by_key.values())

        output = {
            "date": date,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "matches": merged,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        _log(f"Saved {len(merged)} results to {filepath}")


def create_manual_template(date: str, results_dir: str = RESULTS_DIR):
    """Create a template JSON for manual result entry."""
    os.makedirs(results_dir, exist_ok=True)
    filepath = os.path.join(results_dir, f"{date}.json")

    if os.path.exists(filepath):
        _log(f"File already exists: {filepath}")
        return

    # Find matches scheduled for this date.
    try:
        schedule = load_tournament_schedule()
        day_matches = []
        for mid, match in schedule.items():
            if match.get("date") == date:
                grp = match.get("group")
                day_matches.append(
                    {
                        "fd_id": match.get("fd_id"),
                        "match_id": mid,
                        "home_team": match.get("home_team", ""),
                        "away_team": match.get("away_team", ""),
                        "score": {"home": None, "away": None},
                        "outcome": None,
                        "date": date,
                        "stage": _stage_label(mid),
                        "group": f"GROUP_{grp}" if grp else "",
                    }
                )
    except Exception:
        day_matches = []

    output = {
        "date": date,
        "last_updated": None,
        "matches": day_matches,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Template created: {filepath} ({len(day_matches)} matches)")
    _log("Edit the file to fill in scores and outcomes, then run score.py")


def main():
    parser = argparse.ArgumentParser(description="Fetch World Cup 2026 match results")
    parser.add_argument(
        "--date",
        default=None,
        help="Specific date to fetch (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch all finished matches.",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Create a manual template for the given date.",
    )
    parser.add_argument(
        "--results-dir",
        default=RESULTS_DIR,
        help=f"Results directory (default: {RESULTS_DIR})",
    )
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.manual:
        create_manual_template(date, args.results_dir)
        return

    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        _log("No FOOTBALL_DATA_API_KEY found. Creating manual template instead.")
        create_manual_template(date, args.results_dir)
        _log("Tip: Set FOOTBALL_DATA_API_KEY env var for automatic fetching.")
        return

    matches = fetch_from_api(api_key, date, args.all)
    if matches:
        save_results(matches, args.results_dir)
    else:
        _log("No finished matches found.")


if __name__ == "__main__":
    main()
