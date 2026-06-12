"""Convierte predicciones freeze-v3 (schema viejo) al schema nuevo.
Reformateo PURO: no toca probabilidades ni picks. Mapea por (home, away),
pero indexa también el orden invertido y corrige las probs cuando es necesario."""
import json, os, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOURNAMENT = os.path.join(BASE, "data", "tournament.json")
SRC_DIR = os.path.join(BASE, "predictions", "invalidated", "freeze-v3")
OUT_DIR = os.path.join(BASE, "predictions", "pre-tournament")

def build_team_index(tournament):
    """(home, away) -> (match_id, inverted?). Indexa ambos órdenes."""
    idx = {}
    for m in tournament.get("matches", []):
        mid = str(m["match_id"])
        h, a = m["home_team"], m["away_team"]
        idx[(h, a)] = (mid, False)   # orden oficial
        idx[(a, h)] = (mid, True)    # orden invertido
    return idx

def convert(old, team_index):
    new = {
        "model": old.get("model_name") or old.get("model"),
        "modality": "pre_tournament",
        "generated_at": old.get("timestamp") or old.get("generated_at"),
        "seed_or_temp": {"temperature": old.get("temperature")},
        "source_schema": old.get("prompt_version"),
        "group_matches": [],
    }
    unmatched = []
    for gm in old.get("group_stage_matches", []):
        key = (gm["home_team"], gm["away_team"])
        entry = team_index.get(key)
        if entry is None:
            unmatched.append(key)
            continue
        mid, inverted = entry
        p = gm["probs"]
        total = p["home"] + p["draw"] + p["away"]
        if abs(total - 1.0) > 0.01:
            raise ValueError(f'{old.get("model_name")} {gm["match_id"]}: probs suman {total}')
        if inverted:
            probs = {"home": p["away"], "draw": p["draw"], "away": p["home"]}
        else:
            probs = {"home": p["home"], "draw": p["draw"], "away": p["away"]}
        match_entry = {
            "match_id": mid,
            "probs": {
                "home": round(probs["home"], 4),
                "draw": round(probs["draw"], 4),
                "away": round(probs["away"], 4),
            },
            "orientation_flipped": inverted,
        }
        if "predicted_result" in gm:
            match_entry["predicted_result"] = gm["predicted_result"]
        if "predicted_score" in gm:
            match_entry["predicted_score"] = gm["predicted_score"]
        new["group_matches"].append(match_entry)
    if unmatched:
        raise ValueError(f'{old.get("model_name")}: sin mapear {unmatched}')
    # Conserva bracket/champion si existían en el viejo
    for k in ("group_tables", "best_thirds", "bracket", "champion", "runner_up", "third"):
        if k in old:
            new[k] = old[k]
    return new, unmatched

def main():
    with open(TOURNAMENT, encoding="utf-8") as f:
        team_index = build_team_index(json.load(f))
    os.makedirs(OUT_DIR, exist_ok=True)
    files = glob.glob(os.path.join(SRC_DIR, "*.json"))
    print(f"Convirtiendo {len(files)} predicciones...")
    for path in files:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        new, unmatched = convert(old, team_index)
        name = (new["model"] or "model").lower().replace("/", "_").replace(" ", "-")
        out = os.path.join(OUT_DIR, f"{name}_prediction.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(new, f, indent=2, ensure_ascii=False)
        n = len(new["group_matches"])
        print(f"  ✓ {os.path.basename(path)} -> {os.path.basename(out)} ({n}/72 partidos)")

if __name__ == "__main__":
    main()