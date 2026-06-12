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


def _outcome_from_score(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    elif away_goals > home_goals:
        return "away"
    return "draw"


def map_api_match(api_match: dict, tournament: dict) -> dict:
    """Map a single football-data.org match to our result format using fd_id."""
    home = utils.API_TO_FIFA_TLA.get(
        api_match.get("homeTeam", {}).get("tla", ""),
        api_match.get("homeTeam", {}).get("tla", ""),
    )
    away = utils.API_TO_FIFA_TLA.get(
        api_match.get("awayTeam", {}).get("tla", ""),
        api_match.get("awayTeam", {}).get("tla", ""),
    )
    date = api_match.get("utcDate", "")[:10]
    score = api_match.get("score", {}).get("fullTime", {})

    fd_id = None
    match_id = None
    for m in tournament.get("matches", []):
        if (m.get("home_team") == home and m.get("away_team") == away and m.get("date") == date):
            fd_id = m.get("fd_id")
            match_id = str(m.get("match_id"))
            break

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
        "stage": api_match.get("stage", ""),
        "group": api_match.get("group", ""),
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
                day_matches.append(
                    {
                        "fd_id": match.get("fd_id"),
                        "match_id": str(mid),
                        "home_team": match.get("home_team", ""),
                        "away_team": match.get("away_team", ""),
                        "score": {"home": None, "away": None},
                        "outcome": None,
                        "date": date,
                        "stage": match.get("stage", ""),
                        "group": match.get("group", ""),
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
