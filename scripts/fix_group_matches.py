"""Corrige los partidos de grupo en data/tournament.json para que coincidan con football-data.org.

Actualiza:
  - home_team / away_team (algunos están invertidos)
  - date (varios días distintos)
  - group (se normaliza GROUP_A → A)
  - fd_id (se añade si falta)

Preserva:
  - match_id (identificador estable para predicciones)
  - venue (estadio y ciudad)
"""
import json
import os
from datetime import datetime, timezone

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
COMPETITION_ID = 2000
API_BASE = "https://api.football-data.org/v4"

# football-data.org usa algunos TLAs distintos a FIFA.
API_TO_FIFA_TLA = {
    "URY": "URU",  # football-data.org → FIFA
}
FIFA_TO_API_TLA = {v: k for k, v in API_TO_FIFA_TLA.items()}


def normalize_group(api_group: str) -> str:
    """Convierte GROUP_A → A."""
    if api_group and api_group.startswith("GROUP_"):
        return api_group.split("_")[-1]
    return api_group


def to_fifa_tla(api_tla: str) -> str:
    return API_TO_FIFA_TLA.get(api_tla, api_tla)


def to_api_tla(fifa_tla: str) -> str:
    return FIFA_TO_API_TLA.get(fifa_tla, fifa_tla)


def fetch_api_matches(api_key: str) -> list:
    url = f"{API_BASE}/competitions/{COMPETITION_ID}/matches"
    resp = requests.get(url, headers={"X-Auth-Token": api_key}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def build_api_index(api_matches: list) -> dict:
    """Indexa partidos de grupo API por par de equipos FIFA (sin orden)."""
    index = {}
    for m in api_matches:
        if m.get("stage") != "GROUP_STAGE":
            continue
        home_api = (m.get("homeTeam") or {}).get("tla")
        away_api = (m.get("awayTeam") or {}).get("tla")
        home = to_fifa_tla(home_api)
        away = to_fifa_tla(away_api)
        date = (m.get("utcDate") or "")[:10]
        if home and away and date:
            key = tuple(sorted([home, away]))
            index[key] = {
                "fd_id": m["id"],
                "home": home,
                "away": away,
                "date": date,
                "group": normalize_group(m.get("group", "")),
            }
    return index


def fix_group_matches(tournament: dict, api_index: dict) -> dict:
    """Actualiza los partidos de grupo del torneo local."""
    updated = 0
    unmatched = []

    for match in tournament.get("matches", []):
        if not match.get("group"):
            continue

        home = match.get("home_team")
        away = match.get("away_team")
        key = tuple(sorted([home, away]))
        api = api_index.get(key)

        if api is None:
            unmatched.append(match)
            continue

        changes = []
        if match.get("home_team") != api["home"]:
            changes.append(f"home {match.get('home_team')} -> {api['home']}")
            match["home_team"] = api["home"]
        if match.get("away_team") != api["away"]:
            changes.append(f"away {match.get('away_team')} -> {api['away']}")
            match["away_team"] = api["away"]
        if match.get("date") != api["date"]:
            changes.append(f"date {match.get('date')} -> {api['date']}")
            match["date"] = api["date"]
        if match.get("group") != api["group"]:
            changes.append(f"group {match.get('group')} -> {api['group']}")
            match["group"] = api["group"]
        if match.get("fd_id") != api["fd_id"]:
            changes.append(f"fd_id {match.get('fd_id')} -> {api['fd_id']}")
            match["fd_id"] = api["fd_id"]

        if changes:
            updated += 1
            print(f"  match_id={match['match_id']}: {', '.join(changes)}")

    return {"updated": updated, "unmatched": unmatched}


def main():
    api_key = os.environ["FOOTBALL_DATA_API_KEY"]

    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    api_matches = fetch_api_matches(api_key)
    api_index = build_api_index(api_matches)
    print(f"API devolvió {len(api_matches)} partidos, {len(api_index)} de grupo indexables.")
    print(f"Partidos de grupo locales: {sum(1 for m in tournament.get('matches', []) if m.get('group'))}")

    print("\n=== CAMBIOS APLICADOS ===")
    result = fix_group_matches(tournament, api_index)

    if result["unmatched"]:
        print(f"\nWARNING: {len(result['unmatched'])} partidos sin correspondencia en API:")
        for m in result["unmatched"]:
            print(f"  match_id={m['match_id']} {m.get('group')} {m.get('home_team')} vs {m.get('away_team')} {m.get('date')}")

    metadata = tournament.setdefault("metadata", {})
    metadata["last_updated"] = datetime.now(timezone.utc).isoformat()
    metadata["source"] = "FIFA Official Draw 2025-12-05 + football-data.org sync"

    with open(TOURNAMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(tournament, f, indent=2, ensure_ascii=False)

    print(f"\nOK: {result['updated']} partidos actualizados en {TOURNAMENT_PATH}")


if __name__ == "__main__":
    main()
