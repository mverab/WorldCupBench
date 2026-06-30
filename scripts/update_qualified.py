"""Populate data/tournament.json with the real qualified teams.

Reads finished results, computes the 32 qualified teams (via qualifiers.py) and:

  * writes a top-level ``qualified`` block:
        {
          "teams": ["BRA", "ARG", ...],
          "by_group": {"A": {"1st": ..., "2nd": ..., "3rd": ...}, ...},
          "best_thirds": [...],
          "third_slot_assignment": {"74": "B", ...},
          "all_groups_complete": true,
          "last_updated": "..."
        }
  * resolves the knockout bracket slots 73-102 (Round of 32 group seeds and,
    where results allow, knockout winners) into real team codes.

Original slot placeholders ("2A", "3rd(A/B/C/D/F)", "W73", ...) are preserved in
``home_slot`` / ``away_slot`` so the resolution is fully idempotent: re-running
always resolves from the preserved template, never from a previously resolved
value.

Third-placed teams are assigned to their Round-of-32 slots **strictly from the
official FIFA "Annex C" combination table** (all 495 possible combinations of
which eight groups produce a qualifying third-placed team). The table is stored
in ``data/annex_c_third_place.json`` keyed by the sorted set of qualifying
groups (e.g. ``"BDEFIJKL"``) and mapping each group-winner slot
(``1A/1B/1D/1E/1G/1I/1K/1L``) to the group whose third-placed team plays there.

This matters because several different assignments may all satisfy the per-slot
allowed-group constraints (``"3rd(A/B/C/D/F)"`` …), so a plain constraint search
can pick a *valid but wrong* bracket. FIFA fixes one specific assignment per
combination, and getting it wrong breaks the result<->fixture join: e.g. for the
real set {B,D,E,F,I,J,K,L} the correct slot 1E (Germany) opponent is 3D
(Paraguay); a naive search instead put 3B there, leaving the played GER-PAR
octavo unmatched (``match_id: null``).

A deterministic constraint-satisfaction backtracking remains as a safety net for
combinations not present in the table (e.g. synthetic/partial sets in tests).
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qualifiers as q  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")
TOURNAMENT_PATH = os.path.join(BASE_DIR, "data", "tournament.json")
ANNEX_C_PATH = os.path.join(BASE_DIR, "data", "annex_c_third_place.json")

THIRD_RE = re.compile(r"3rd\(([^)]+)\)")
SEED_RE = re.compile(r"^([12])([A-L])$")
WINNER_RE = re.compile(r"^([WL])(\d+)$")
WINNER_SLOT_RE = re.compile(r"^1([A-L])$")


def load_annex_c(path: str = ANNEX_C_PATH) -> dict:
    """Load the FIFA Annex C third-place combination table.

    Returns ``{qual_key: {winner_slot_label: group_letter}}`` where ``qual_key``
    is the eight qualifying group letters sorted and concatenated
    (e.g. ``"BDEFIJKL"``). Returns ``{}`` if the file is missing/unreadable so
    the caller transparently falls back to constraint-satisfaction matching.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("combinations", {})
    except (json.JSONDecodeError, OSError):
        return {}


_ANNEX_C = load_annex_c()


def load_all_results(results_dir: str = RESULTS_DIR) -> list:
    matches = []
    for f in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue
        matches.extend(data if isinstance(data, list) else data.get("matches", []))
    return matches


def _allowed_groups(slot: str) -> list:
    m = THIRD_RE.search(slot or "")
    if not m:
        return []
    return [g.strip() for g in m.group(1).split("/")]


def assign_third_slots(bracket: list, qualifying_third_groups: list) -> dict:
    """Match qualifying third-placed groups to their Round-of-32 slots.

    Returns ``{match_id(str): group_letter}``.

    Primary path — **FIFA Annex C**: when the exact set of eight qualifying
    third-place groups is found in the official combination table (always true
    for a real tournament, since the table covers all 495 combinations), the
    assignment is taken verbatim from FIFA. This guarantees the *one* correct
    bracket among the several that merely satisfy the per-slot constraints.

    Fallback — **constraint-satisfaction backtracking**: used only when the
    combination is absent from the table or the bracket does not expose real
    group-winner slot labels (e.g. synthetic/partial fixtures in unit tests).
    """
    groups = sorted(set(qualifying_third_groups))
    annex_assignment = _assign_from_annex_c(bracket, groups)
    if annex_assignment is not None:
        return annex_assignment
    return _assign_third_slots_backtrack(bracket, qualifying_third_groups)


def _assign_from_annex_c(bracket: list, groups: list):
    """Resolve third-place slots from the FIFA Annex C table.

    ``groups`` must be the sorted list of qualifying third-place group letters.
    Returns ``{match_id(str): group_letter}``, or ``None`` when the combination
    is not in the table or the bracket lacks real winner-slot labels (so the
    caller falls back to constraint-satisfaction matching).
    """
    if len(groups) != 8:
        return None
    row = _ANNEX_C.get("".join(groups))
    if not row:
        return None

    assignment = {}
    for m in bracket:
        # The third-place team always occupies the slot carrying the
        # ``3rd(...)`` constraint; the *other* slot carries the group-winner
        # label (``1E``) that indexes the Annex C row.
        if _allowed_groups(m.get("away_slot")):
            winner_slot = m.get("home_slot")
        elif _allowed_groups(m.get("home_slot")):
            winner_slot = m.get("away_slot")
        else:
            continue  # not a third-place match
        if not WINNER_SLOT_RE.match(winner_slot or ""):
            return None  # no real winner label -> fall back
        grp = row.get(winner_slot)
        if grp is None:
            return None
        assignment[str(m["match_id"])] = grp

    return assignment or None


def _assign_third_slots_backtrack(bracket: list, qualifying_third_groups: list) -> dict:
    """Deterministic constraint-satisfaction fallback (legacy behaviour).

    Honours each slot's allowed-group constraint, preferring the most
    constrained slots first so a valid complete assignment is found. Note this
    returns *a* valid assignment, not necessarily FIFA's specific one — hence it
    is only a safety net behind :func:`_assign_from_annex_c`.
    """
    # Collect third slots: match_id -> sorted list of allowed qualifying groups.
    slots = {}
    for m in bracket:
        for side in ("home_slot", "away_slot"):
            slot = m.get(side)
            allowed = _allowed_groups(slot)
            if allowed:
                qualifying = sorted(set(allowed) & set(qualifying_third_groups))
                slots[str(m["match_id"])] = qualifying

    groups_to_place = sorted(set(qualifying_third_groups))
    slot_ids = sorted(slots.keys(), key=lambda s: (len(slots[s]), int(s)))

    assignment = {}

    def backtrack(idx: int, remaining: set) -> bool:
        if idx == len(slot_ids):
            return len(remaining) == 0
        sid = slot_ids[idx]
        for grp in slots[sid]:
            if grp in remaining:
                assignment[sid] = grp
                remaining.discard(grp)
                if backtrack(idx + 1, remaining):
                    return True
                remaining.add(grp)
                del assignment[sid]
        return False

    if len(groups_to_place) == len(slot_ids):
        backtrack(0, set(groups_to_place))
    return assignment


def _ensure_slots_preserved(bracket: list):
    """Copy the original placeholder into home_slot/away_slot once (idempotent)."""
    for m in bracket:
        if "home_slot" not in m:
            m["home_slot"] = m.get("home_team")
        if "away_slot" not in m:
            m["away_slot"] = m.get("away_team")


def _result_index(results: list) -> dict:
    """Map match_id (str) -> finished result match."""
    idx = {}
    for m in results:
        mid = m.get("match_id")
        if mid is None:
            continue
        score = m.get("score", {})
        if isinstance(score.get("home"), int) and isinstance(score.get("away"), int):
            idx[str(mid)] = m
    return idx


def _winner_loser(result: dict):
    hs, as_ = result["score"]["home"], result["score"]["away"]
    if hs > as_:
        return result.get("home_team"), result.get("away_team")
    if as_ > hs:
        return result.get("away_team"), result.get("home_team")
    return None, None  # draw: undecided (penalties unknown)


def resolve_slot(slot: str, qinfo: dict, third_groups_by_slot: dict,
                 slot_match_id: str, side: str, resolved_winners: dict) -> str:
    """Resolve a single slot string into a team code, or return it unchanged."""
    if not slot:
        return slot
    by_group = qinfo.get("by_group", {})

    sm = SEED_RE.match(slot)
    if sm:
        pos, grp = sm.group(1), sm.group(2)
        key = "1st" if pos == "1" else "2nd"
        return by_group.get(grp, {}).get(key, slot)

    if THIRD_RE.search(slot):
        grp = third_groups_by_slot.get(str(slot_match_id))
        if grp:
            return by_group.get(grp, {}).get("3rd", slot)
        return slot

    wm = WINNER_RE.match(slot)
    if wm:
        return resolved_winners.get(slot, slot)

    return slot


def update_tournament(results_dir: str = RESULTS_DIR,
                      tournament_path: str = TOURNAMENT_PATH) -> dict:
    with open(tournament_path, "r", encoding="utf-8") as f:
        tournament = json.load(f)

    results = load_all_results(results_dir)
    qinfo = q.compute_qualified(results, tournament)

    bracket = tournament.get("knockout_bracket", [])
    _ensure_slots_preserved(bracket)

    # Determine the groups whose third-placed team qualified.
    third_groups = []
    for letter, entry in qinfo["by_group"].items():
        if entry.get("3rd") in qinfo["best_thirds"]:
            third_groups.append(letter)
    third_assignment = {}
    if qinfo["all_groups_complete"]:
        third_assignment = assign_third_slots(bracket, third_groups)

    # Iteratively resolve slots: group seeds + thirds first, then winners as
    # results of feeding matches become available.
    res_idx = _result_index(results)
    resolved_winners = {}

    def resolve_pass():
        changed = False
        for m in bracket:
            for side, slot_field, team_field in (
                ("home", "home_slot", "home_team"),
                ("away", "away_slot", "away_team"),
            ):
                slot = m.get(slot_field)
                new_val = resolve_slot(
                    slot, qinfo, third_assignment, m["match_id"], side, resolved_winners
                )
                if new_val != m.get(team_field):
                    m[team_field] = new_val
                    changed = True
        # Compute winners/losers for matches whose result is known and whose
        # team slots are now resolved into real codes.
        for m in bracket:
            mid = str(m["match_id"])
            result = res_idx.get(mid)
            if not result:
                continue
            w, l = _winner_loser(result)
            if w and f"W{mid}" not in resolved_winners:
                resolved_winners[f"W{mid}"] = w
                changed = True
            if l and f"L{mid}" not in resolved_winners:
                resolved_winners[f"L{mid}"] = l
                changed = True
        return changed

    for _ in range(8):  # enough passes to propagate through all rounds
        if not resolve_pass():
            break

    tournament["qualified"] = {
        "teams": qinfo["teams"],
        "by_group": qinfo["by_group"],
        "best_thirds": qinfo["best_thirds"],
        "third_slot_assignment": third_assignment,
        "groups_complete": qinfo["groups_complete"],
        "all_groups_complete": qinfo["all_groups_complete"],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    with open(tournament_path, "w", encoding="utf-8") as f:
        json.dump(tournament, f, ensure_ascii=False, indent=2)

    print(
        f"tournament.json updated: {len(qinfo['teams'])} qualified teams, "
        f"all_groups_complete={qinfo['all_groups_complete']}"
    )
    return tournament


def main():
    parser = argparse.ArgumentParser(description="Populate qualified teams in tournament.json")
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument("--tournament", default=TOURNAMENT_PATH)
    args = parser.parse_args()
    update_tournament(args.results_dir, args.tournament)


if __name__ == "__main__":
    main()
