"""Diagnóstico completo de discrepancias entre tournament.json y football-data.org."""
import json
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
COMPETITION_ID = 2000
API_BASE = "https://api.football-data.org/v4"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from utils import API_TO_FIFA_TLA  # noqa: E402


def to_fifa_tla(api_tla: str) -> str:
    return API_TO_FIFA_TLA.get(api_tla, api_tla)


def main():
    key = os.environ["FOOTBALL_DATA_API_KEY"]
    resp = requests.get(
        f"{API_BASE}/competitions/{COMPETITION_ID}/matches",
        headers={"X-Auth-Token": key},
        timeout=30,
    )
    resp.raise_for_status()
    api_matches = resp.json().get("matches", [])

    with open(TOURNAMENT_PATH, encoding="utf-8") as f:
        tournament = json.load(f)

    api_group = []
    for m in api_matches:
        if m.get("stage") == "GROUP_STAGE":
            home = to_fifa_tla((m.get("homeTeam") or {}).get("tla"))
            away = to_fifa_tla((m.get("awayTeam") or {}).get("tla"))
            date = (m.get("utcDate") or "")[:10]
            api_group.append({
                "id": m["id"],
                "group": m.get("group", ""),
                "home": home,
                "away": away,
                "date": date,
            })

    local_group = []
    for m in tournament.get("matches", []):
        if m.get("group"):
            local_group.append({
                "match_id": m.get("match_id"),
                "group": m.get("group", ""),
                "home": m.get("home_team"),
                "away": m.get("away_team"),
                "date": m.get("date"),
                "fd_id": m.get("fd_id"),
            })

    # Índices
    api_by_teams = {(m["home"], m["away"]): m for m in api_group}
    local_by_teams = {(m["home"], m["away"]): m for m in local_group}

    # Comparaciones
    exact_matches = []
    date_mismatches = []
    only_in_api = []
    only_in_local = []

    for m in api_group:
        key = (m["home"], m["away"])
        local = local_by_teams.get(key)
        if local:
            if local["date"] == m["date"]:
                exact_matches.append((m, local))
            else:
                date_mismatches.append((m, local))
        else:
            only_in_api.append(m)

    for m in local_group:
        key = (m["home"], m["away"])
        if key not in api_by_teams:
            only_in_local.append(m)

    print(f"Total partidos de grupo API: {len(api_group)}")
    print(f"Total partidos de grupo local: {len(local_group)}")
    print(f"Emparejamientos exactos (mismo home/away/date): {len(exact_matches)}")
    print(f"Mismo enfrentamiento, fecha distinta: {len(date_mismatches)}")
    print(f"Solo en API: {len(only_in_api)}")
    print(f"Solo en local: {len(only_in_local)}")

    if date_mismatches:
        print("\n=== FECHAS DISTINTAS PARA EL MISMO ENFRENTAMIENTO ===")
        for api_m, local_m in sorted(date_mismatches, key=lambda x: x[0]["id"]):
            print(
                f"  {api_m['group']} {api_m['home']} vs {api_m['away']}: "
                f"API {api_m['date']} (id={api_m['id']}) vs local {local_m['date']} (match_id={local_m['match_id']})"
            )

    if only_in_api:
        print("\n=== SOLO EN API ===")
        for m in sorted(only_in_api, key=lambda x: x["id"]):
            print(f"  {m['group']} {m['home']} vs {m['away']} {m['date']} (id={m['id']})")

    if only_in_local:
        print("\n=== SOLO EN LOCAL ===")
        for m in sorted(only_in_local, key=lambda x: x["match_id"]):
            print(f"  {m['group']} {m['home']} vs {m['away']} {m['date']} (match_id={m['match_id']})")


if __name__ == "__main__":
    main()
