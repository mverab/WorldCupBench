"""Enrich data/tournament.json with fd_id from football-data.org API."""

import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
COMPETITION_ID = 2000
SEASON_ID = 2398
API_BASE = "https://api.football-data.org/v4"


def add_fd_ids(tournament: dict, api_matches: list) -> dict:
    """Add fd_id to each tournament match by matching home/away/date."""
    api_index = {}
    for m in api_matches:
        home = m.get("homeTeam", {}).get("tla")
        away = m.get("awayTeam", {}).get("tla")
        date = m.get("utcDate", "")[:10]
        if home and away and date:
            api_index[(home, away, date)] = m["id"]

    for match in tournament.get("matches", []):
        home = match.get("home_team")
        away = match.get("away_team")
        date = match.get("date", "")
        fd_id = api_index.get((home, away, date))
        if fd_id is not None:
            match["fd_id"] = fd_id

    return tournament


def fetch_api_matches(api_key: str) -> list:
    url = f"{API_BASE}/competitions/{COMPETITION_ID}/matches"
    headers = {"X-Auth-Token": api_key}
    params = {"season": SEASON_ID}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def main():
    api_key = os.environ["FOOTBALL_DATA_API_KEY"]
    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    api_matches = fetch_api_matches(api_key)
    enriched = add_fd_ids(tournament, api_matches)

    missing = [m.get("match_id") for m in enriched.get("matches", []) if "fd_id" not in m]
    if missing:
        print(f"WARNING: {len(missing)} matches without fd_id: {missing[:5]}")

    with open(TOURNAMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"OK: enriched {len(enriched.get('matches', []))} matches")


if __name__ == "__main__":
    main()
