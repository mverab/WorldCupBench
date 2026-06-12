"""Diagnostica por qué los partidos de grupo no empatan con la API."""
import json, os, requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")

key = os.environ["FOOTBALL_DATA_API_KEY"]
url = "https://api.football-data.org/v4/competitions/2000/matches"
api = requests.get(url, headers={"X-Auth-Token": key}, timeout=30).json()["matches"]

# Imprime los primeros 6 partidos de grupo crudos de la API
print("=== PRIMEROS PARTIDOS DE GRUPO SEGÚN LA API ===")
n = 0
for m in api:
    if m.get("stage") == "GROUP_STAGE":
        h = (m.get("homeTeam") or {}).get("tla")
        a = (m.get("awayTeam") or {}).get("tla")
        d = (m.get("utcDate") or "")[:10]
        g = m.get("group")
        print(f"  id={m['id']} {g} {h} vs {a}  {d}  status={m.get('status')}")
        n += 1
        if n >= 8:
            break

# Compara contra TU archivo
with open(TOURNAMENT_PATH, encoding="utf-8") as f:
    t = json.load(f)
print("\n=== PRIMEROS PARTIDOS DE GRUPO EN TU JSON ===")
for m in t["matches"][:8]:
    print(f"  match_id={m['match_id']} {m['group']} {m['home_team']} vs {m['away_team']}  {m['date']}")
