"""Enrich data/tournament.json with fd_id from football-data.org API."""

import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
COMPETITION_ID = 2000
API_BASE = "https://api.football-data.org/v4"


def build_api_index(api_matches: list) -> dict:
    """Index API matches by (home_tla, away_tla, date)."""
    api_index = {}
    for m in api_matches:
        home = (m.get("homeTeam") or {}).get("tla")
        away = (m.get("awayTeam") or {}).get("tla")
        date = (m.get("utcDate") or "")[:10]
        if home and away and date:
            api_index[(home, away, date)] = m["id"]
    return api_index


def enrich(matches: list, api_index: dict) -> int:
    """Add fd_id in place. Returns how many were matched."""
    matched = 0
    for match in matches:
        home = match.get("home_team")
        away = match.get("away_team")
        date = (match.get("date") or "")[:10]
        fd_id = api_index.get((home, away, date))
        if fd_id is not None:
            match["fd_id"] = fd_id
            matched += 1
    return matched


def fetch_api_matches(api_key: str) -> list:
    url = f"{API_BASE}/competitions/{COMPETITION_ID}/matches"
    headers = {"X-Auth-Token": api_key}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def main():
    api_key = os.environ["FOOTBALL_DATA_API_KEY"]
    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    api_matches = fetch_api_matches(api_key)
    api_index = build_api_index(api_matches)
    print(f"API devolvió {len(api_matches)} partidos, {len(api_index)} indexables.")

    group_matches = tournament.get("matches", [])
    knockout = tournament.get("knockout_bracket", [])

    m1 = enrich(group_matches, api_index)
    m2 = enrich(knockout, api_index)

    # Solo los de grupo deberían empatar ahora (los knockouts aún no tienen equipos definidos)
    no_fd = [m.get("match_id") for m in group_matches if "fd_id" not in m]
    if no_fd:
        print(f"WARNING: {len(no_fd)} partidos de grupo sin fd_id: {no_fd[:10]}")

    with open(TOURNAMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(tournament, f, indent=2, ensure_ascii=False)

    print(f"OK: {m1} de grupo + {m2} de eliminatoria enriquecidos -> data/tournament.json")


if __name__ == "__main__":
    main()