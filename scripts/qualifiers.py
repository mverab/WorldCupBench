"""Compute the real set of 32 qualified teams for the 2026 World Cup.

Reads the finished group-stage results from ``data/results/*.json`` and the
group composition from ``data/tournament.json`` and derives, applying the FIFA
tie-breaking rules:

  * the standings of each group (3 pts win / 1 draw / 0 loss),
  * the 1st and 2nd placed team of every completed group (24 teams),
  * the 8 best third-placed teams (ranked across all completed groups),

for a total of 32 qualified teams.

FIFA tie-breaking order (2026 regulations, art. on group ranking):
  1. points in all group matches
  2. goal difference in all group matches
  3. goals scored in all group matches
  -- if still tied, only among the tied teams --
  4. points in head-to-head matches between the tied teams
  5. goal difference in those head-to-head matches
  6. goals scored in those head-to-head matches
  7. fair-play points
  8. drawing of lots

Fair-play data is not tracked in this benchmark, so criteria 7-8 fall back to a
deterministic alphabetical ordering of the team code (acting as the
"drawing of lots" stand-in) so the output is stable and reproducible.
"""

import os
from collections import defaultdict

GROUP_LETTERS = [chr(ord("A") + i) for i in range(12)]
BEST_THIRDS_COUNT = 8


def _norm_group(value) -> str:
    """Normalise a group label ('GROUP_A', 'A', 'a') to a single letter."""
    if value is None:
        return ""
    g = str(value).upper().replace("GROUP_", "").replace("GROUP", "").strip()
    return g[-1] if g else ""


def team_to_group(tournament: dict) -> dict:
    """Map every team code to its group letter."""
    mapping = {}
    for grp in tournament.get("groups", []):
        letter = _norm_group(grp.get("group"))
        for team in grp.get("teams", []):
            mapping[team] = letter
    return mapping


def _is_group_match(match: dict) -> bool:
    """True if the match is a group-stage match with a final score."""
    stage = str(match.get("stage", "")).upper()
    mid = match.get("match_id")
    in_group_range = False
    try:
        in_group_range = 1 <= int(mid) <= 72
    except (TypeError, ValueError):
        in_group_range = False
    if stage and stage != "GROUP_STAGE" and not in_group_range:
        return False
    score = match.get("score", {})
    return isinstance(score.get("home"), int) and isinstance(score.get("away"), int)


def collect_group_matches(results: list, team_group: dict) -> list:
    """Return finished group-stage matches annotated with a group letter."""
    matches = []
    for m in results:
        if not _is_group_match(m):
            continue
        group = _norm_group(m.get("group")) or team_group.get(m.get("home_team"), "")
        if not group:
            continue
        matches.append(
            {
                "group": group,
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "home_score": m["score"]["home"],
                "away_score": m["score"]["away"],
            }
        )
    return matches


def _blank_row(team: str, group: str) -> dict:
    return {
        "team": team,
        "group": group,
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "gf": 0,
        "ga": 0,
        "gd": 0,
        "points": 0,
    }


def _apply_match(table: dict, home, away, hs, as_):
    h, a = table[home], table[away]
    h["played"] += 1
    a["played"] += 1
    h["gf"] += hs
    h["ga"] += as_
    a["gf"] += as_
    a["ga"] += hs
    if hs > as_:
        h["won"] += 1
        a["lost"] += 1
        h["points"] += 3
    elif hs < as_:
        a["won"] += 1
        h["lost"] += 1
        a["points"] += 3
    else:
        h["drawn"] += 1
        a["drawn"] += 1
        h["points"] += 1
        a["points"] += 1
    h["gd"] = h["gf"] - h["ga"]
    a["gd"] = a["gf"] - a["ga"]


def build_group_tables(matches: list, tournament: dict) -> dict:
    """Build per-group standings tables from finished matches.

    Returns ``{group_letter: {"table": [rows...], "complete": bool}}`` where
    ``table`` is sorted best-first applying the FIFA tie-breakers.
    """
    team_group = team_to_group(tournament)
    matches_by_group = defaultdict(list)
    for m in matches:
        matches_by_group[m["group"]].append(m)

    # Initialise standings rows for every team in every group.
    group_teams = {}
    for grp in tournament.get("groups", []):
        letter = _norm_group(grp.get("group"))
        group_teams[letter] = list(grp.get("teams", []))

    out = {}
    for letter, teams in group_teams.items():
        table = {t: _blank_row(t, letter) for t in teams}
        gmatches = matches_by_group.get(letter, [])
        for m in gmatches:
            if m["home_team"] in table and m["away_team"] in table:
                _apply_match(
                    table, m["home_team"], m["away_team"], m["home_score"], m["away_score"]
                )
        ranked = _rank_group(list(table.values()), gmatches)
        # A standard 4-team group is complete after all 6 matches are played.
        complete = len(gmatches) >= (len(teams) * (len(teams) - 1)) // 2
        out[letter] = {"table": ranked, "complete": complete}
    return out


def _head_to_head(tied_rows: list, matches: list) -> list:
    """Re-rank a set of tied teams using only matches among themselves."""
    names = {r["team"] for r in tied_rows}
    mini = {r["team"]: _blank_row(r["team"], r["group"]) for r in tied_rows}
    for m in matches:
        if m["home_team"] in names and m["away_team"] in names:
            _apply_match(mini, m["home_team"], m["away_team"], m["home_score"], m["away_score"])
    return sorted(
        tied_rows,
        key=lambda r: (
            -mini[r["team"]]["points"],
            -mini[r["team"]]["gd"],
            -mini[r["team"]]["gf"],
            r["team"],  # deterministic fair-play / drawing-of-lots stand-in
        ),
    )


def _rank_group(rows: list, matches: list) -> list:
    """Sort rows best-first using overall criteria, then head-to-head."""
    # Overall criteria: points, goal difference, goals for.
    rows = sorted(rows, key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))

    # Resolve groups of teams equal on (points, gd, gf) via head-to-head.
    result = []
    i = 0
    while i < len(rows):
        j = i + 1
        while (
            j < len(rows)
            and rows[j]["points"] == rows[i]["points"]
            and rows[j]["gd"] == rows[i]["gd"]
            and rows[j]["gf"] == rows[i]["gf"]
        ):
            j += 1
        block = rows[i:j]
        if len(block) > 1:
            block = _head_to_head(block, matches)
        result.extend(block)
        i = j
    return result


def rank_best_thirds(group_tables: dict) -> list:
    """Rank the third-placed teams of completed groups, best first.

    Criteria: points, goal difference, goals scored, then team code
    (deterministic fair-play / lots stand-in).
    """
    thirds = []
    for letter in GROUP_LETTERS:
        info = group_tables.get(letter)
        if not info or not info["complete"]:
            continue
        table = info["table"]
        if len(table) >= 3:
            thirds.append(table[2])
    thirds.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    return thirds


def compute_qualified(results: list, tournament: dict) -> dict:
    """Compute the full qualification picture from finished results.

    Returns a dict with:
      * ``teams``         – sorted list of all qualified team codes
      * ``by_group``      – {group: {"1st", "2nd", "3rd"}} for completed groups
      * ``best_thirds``   – list of the up-to-8 best third-placed team codes
      * ``positions``     – {team: "1st"|"2nd"|"3rd"} for qualified teams
      * ``standings``     – {group: [rows...]} full standings (debug/inspection)
      * ``groups_complete`` / ``all_groups_complete`` – completeness flags
    """
    team_group = team_to_group(tournament)
    matches = collect_group_matches(results, team_group)
    group_tables = build_group_tables(matches, tournament)

    by_group = {}
    positions = {}
    firsts_seconds = []
    complete_groups = []

    for letter in GROUP_LETTERS:
        info = group_tables.get(letter)
        if not info or not info["complete"]:
            continue
        complete_groups.append(letter)
        table = info["table"]
        entry = {}
        if len(table) >= 1:
            entry["1st"] = table[0]["team"]
            positions[table[0]["team"]] = "1st"
            firsts_seconds.append(table[0]["team"])
        if len(table) >= 2:
            entry["2nd"] = table[1]["team"]
            positions[table[1]["team"]] = "2nd"
            firsts_seconds.append(table[1]["team"])
        if len(table) >= 3:
            entry["3rd"] = table[2]["team"]
        by_group[letter] = entry

    # Best thirds are only meaningful once every group has finished, because
    # they are ranked across all 12 groups. Until then we keep the provisional
    # ranking but only mark them qualified when all groups are complete.
    all_complete = len(complete_groups) == len(GROUP_LETTERS)
    thirds_ranked = rank_best_thirds(group_tables)
    best_thirds = []
    if all_complete:
        best_thirds = [r["team"] for r in thirds_ranked[:BEST_THIRDS_COUNT]]
        for t in best_thirds:
            positions[t] = "3rd"

    qualified_teams = sorted(set(firsts_seconds) | set(best_thirds))

    standings = {g: info["table"] for g, info in group_tables.items()}

    return {
        "teams": qualified_teams,
        "by_group": by_group,
        "best_thirds": best_thirds,
        "positions": positions,
        "standings": standings,
        "groups_complete": complete_groups,
        "all_groups_complete": all_complete,
    }
