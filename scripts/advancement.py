"""Per-round set-membership ADVANCEMENT metric for WorldCupBench.

This is the knockout-stage analogue of ``score.score_qualifiers`` (the group
``qualifier_accuracy`` metric). Instead of asking *"which 32 teams reach the
Round of 32?"* it asks, for every knockout round:

    *"which teams REACH this round?"*  — independent of the bracket seeding /
    slot a team occupies.

Concretely the set of teams that *reach* a round equals the set of teams that
won the previous round's matches:

    reach R16      = winners of the 16 Round-of-32 matches  (match_id 73-88)
    reach QF       = winners of the  8 Round-of-16 matches  (match_id 89-96)
    reach SF       = winners of the  4 quarter-finals       (match_id 97-100)
    reach FINAL    = winners of the  2 semi-finals          (match_id 101-102)
    CHAMPION       = winner  of the    final                (match_id 104)

A model's *predicted* advancement is read from the frozen prediction bracket:
the ``winner`` of every R32 match is a team it expects to reach the R16, and so
on. The metric is pure set membership (Jaccard-style hits), so it rewards a
model that picked the right teams to go deep even if it placed them in the
wrong half of the bracket.

The scoring mirrors ``qualifier_accuracy`` exactly (hits / total / missed /
false_positives / ready) so the dashboard can render both with one code path.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils  # noqa: E402

# Number of teams that reach each round (the "total" each round is scored over).
ROUND_SIZES = {"R16": 16, "QF": 8, "SF": 4, "FINAL": 2, "CHAMPION": 1}

# Rounds in bracket-depth order.
ROUND_ORDER = ["R16", "QF", "SF", "FINAL", "CHAMPION"]

# Integer match_id range whose WINNERS advance into the keyed round.
_FEEDER_RANGE = {
    "R16": range(73, 89),     # winners of the Round of 32
    "QF": range(89, 97),      # winners of the Round of 16
    "SF": range(97, 101),     # winners of the quarter-finals
    "FINAL": range(101, 103),  # winners of the semi-finals
    "CHAMPION": range(104, 105),  # winner of the final
}

# Prediction-bracket key whose per-match ``winner`` fields populate each round.
# (the winner a model picks in R32 is a team it predicts will reach R16, etc.)
_PRED_SOURCE = {
    "R16": ("round", "R32"),
    "QF": ("round", "R16"),
    "SF": ("round", "QF"),
    "FINAL": ("round", "SF"),
    "CHAMPION": ("single", "final"),
}


def _winner_of(result: dict) -> str:
    """Return the FIFA code of the team that won a finished match, else None."""
    if not result:
        return None
    outcome = result.get("outcome")
    if outcome == "home":
        return result.get("home_team")
    if outcome == "away":
        return result.get("away_team")
    if outcome == "draw":
        return None
    # No explicit outcome: derive from the score when available.
    score = result.get("score", {}) or {}
    hs, as_ = score.get("home"), score.get("away")
    if isinstance(hs, int) and isinstance(as_, int):
        if hs > as_:
            return result.get("home_team")
        if as_ > hs:
            return result.get("away_team")
    return None


def _lookup(results: dict, match_id: int) -> dict:
    """Find a result by canonical match_id, honouring the FINAL/THIRD bridge."""
    res = results.get(str(match_id))
    if res is not None:
        return res
    canonical = utils.stage_from_match_id(match_id)
    if canonical == "FINAL":
        return results.get("FINAL")
    if canonical == "THIRD_PLACE":
        return results.get("THIRD")
    return None


def compute_real_advancement(results: dict) -> dict:
    """Build the real set of teams reaching each knockout round.

    ``results`` is the lookup produced by :func:`score.load_results` (keyed by
    ``str(match_id)`` / ``str(fd_id)`` plus the ``"FINAL"`` / ``"THIRD"``
    sentinels).

    Returns ``{round: {"teams": set, "ready": bool}}`` for every round in
    :data:`ROUND_ORDER`. ``ready`` is True only when *every* feeder match of
    that round has a decisive winner, so partially played rounds never
    penalise a model for matches that have not happened yet.
    """
    out = {}
    for rnd, rng in _FEEDER_RANGE.items():
        teams = set()
        decided = 0
        for mid in rng:
            winner = _winner_of(_lookup(results, mid))
            if winner:
                teams.add(winner)
                decided += 1
        out[rnd] = {"teams": teams, "ready": decided == len(rng)}
    return out


def predicted_advancement(prediction: dict) -> dict:
    """Extract the set of teams a model predicts will reach each round."""
    bracket = prediction.get("bracket", {}) or {}
    out = {}
    for rnd, (kind, key) in _PRED_SOURCE.items():
        teams = set()
        if kind == "round":
            for m in bracket.get(key, []) or []:
                w = m.get("winner")
                if w:
                    teams.add(w)
        else:  # single match (the final)
            m = bracket.get(key)
            if m and m.get("winner"):
                teams.add(m["winner"])
        out[rnd] = teams
    return out


def score_advancement(prediction: dict, real: dict) -> dict:
    """Score a model's predicted advancement against the real one.

    Mirrors ``score.score_qualifiers``: per-round hits / total / missed /
    false_positives / ready, plus an overall ``hits``/``total``/``score`` that
    aggregates only the rounds that are *ready* (fully decided).

    Returns a JSON-serialisable dict (sets are converted to sorted lists).
    """
    predicted = predicted_advancement(prediction)

    rounds = {}
    overall_hits = 0
    overall_total = 0
    any_ready = False

    for rnd in ROUND_ORDER:
        pred_set = predicted.get(rnd, set())
        real_info = real.get(rnd, {"teams": set(), "ready": False})
        real_set = set(real_info.get("teams", set()))
        ready = bool(real_info.get("ready", False))
        total = ROUND_SIZES[rnd]

        hit_teams = pred_set & real_set
        hits = len(hit_teams)
        missed = sorted(real_set - pred_set)
        false_positives = sorted(pred_set - real_set)

        rounds[rnd] = {
            "hits": hits,
            "total": total,
            "predicted_count": len(pred_set),
            "reached_count": len(real_set),
            "missed": missed,
            "false_positives": false_positives,
            "ready": ready,
        }

        if ready:
            any_ready = True
            overall_hits += hits
            overall_total += total

    score = round(overall_hits / overall_total, 6) if overall_total else 0.0
    return {
        "rounds": rounds,
        "hits": overall_hits,
        "total": overall_total,
        "score": score,
        "ready": any_ready,
    }
