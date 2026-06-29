"""Tests for the knockout scoring + reconciliation pipeline.

Covers the three bugs and the new metric introduced in this change set:

* BUG 3 — a *single* canonical stage taxonomy (``utils.normalize_stage`` /
  ``utils.stage_from_match_id``): ``LAST_32`` -> ``R32``, match_id 104 ->
  ``FINAL`` …
* BUG 1/2 — ``reconcile_results`` back-fills knockout results that were saved
  with ``match_id: null`` (because the bracket was not resolved yet) by joining
  on the unordered team pair, and is idempotent.
* The set-membership ``advancement`` metric (per-round "which teams reach this
  round", independent of seeding).
* Byte-coherence between ``data/results/*.json`` and the consolidated
  ``docs/data/results.json`` produced by ``build_dashboard_results``.
* Result orientation consistency on the **real** committed results.

These tests are intentionally self-contained (temp dirs / hand-built fixtures)
*and* assert a couple of invariants on the real, reconciled data so they double
as regression guards for the actual deliverable.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import advancement  # noqa: E402
import build_dashboard_results  # noqa: E402
import reconcile_results  # noqa: E402
import utils  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_RESULTS_DIR = os.path.join(BASE_DIR, "data", "results")


# --------------------------------------------------------------------------- #
# BUG 3 — single canonical stage taxonomy
# --------------------------------------------------------------------------- #
def test_stage_from_match_id_ranges():
    assert utils.stage_from_match_id(1) == "GROUP_STAGE"
    assert utils.stage_from_match_id(72) == "GROUP_STAGE"
    assert utils.stage_from_match_id(73) == "R32"
    assert utils.stage_from_match_id(88) == "R32"
    assert utils.stage_from_match_id(89) == "R16"
    assert utils.stage_from_match_id(96) == "R16"
    assert utils.stage_from_match_id(97) == "QF"
    assert utils.stage_from_match_id(100) == "QF"
    assert utils.stage_from_match_id(101) == "SF"
    assert utils.stage_from_match_id(102) == "SF"
    assert utils.stage_from_match_id(103) == "THIRD_PLACE"
    assert utils.stage_from_match_id(104) == "FINAL"
    # Sentinels used by the frozen prediction brackets.
    assert utils.stage_from_match_id("FINAL") == "FINAL"
    assert utils.stage_from_match_id("THIRD") == "THIRD_PLACE"
    # Unknown / unparsable ids resolve to "".
    assert utils.stage_from_match_id(999) == ""
    assert utils.stage_from_match_id(None) == ""


def test_normalize_stage_aliases():
    # The whole point of BUG 3: every alias collapses to ONE label.
    assert utils.normalize_stage("LAST_32") == "R32"
    assert utils.normalize_stage("ROUND_OF_32") == "R32"
    assert utils.normalize_stage("round_of_16") == "R16"
    assert utils.normalize_stage("Quarter-Finals") == "QF"
    assert utils.normalize_stage("SEMI FINALS") == "SF"
    assert utils.normalize_stage("THIRD") == "THIRD_PLACE"
    assert utils.normalize_stage("FINAL") == "FINAL"
    assert utils.normalize_stage("GROUP_STAGE") == "GROUP_STAGE"


def test_normalize_stage_match_id_takes_priority_over_label():
    # When a (wrong) label disagrees with the match_id range, the id wins.
    assert utils.normalize_stage("LAST_32", 104) == "FINAL"
    assert utils.normalize_stage("GROUP_STAGE", 90) == "R16"
    # Label is used only when the id is unknown / missing.
    assert utils.normalize_stage("LAST_32", None) == "R32"
    assert utils.normalize_stage("LAST_32", 999) == "R32"


# --------------------------------------------------------------------------- #
# BUG 1/2 — reconcile knockout results saved with match_id: null
# --------------------------------------------------------------------------- #
def _mini_tournament():
    """A tiny tournament with a resolved knockout bracket (73 RSA/CAN, 76 BRA/JPN)."""
    return {
        "groups": [
            {"group": "A", "teams": ["RSA", "CAN", "MEX", "KOR"]},
            {"group": "B", "teams": ["BRA", "JPN", "GER", "BIH"]},
        ],
        "knockout_bracket": [
            {
                "match_id": 73, "round": "round_of_32",
                "home_team": "RSA", "away_team": "CAN",
                "home_slot": "2A", "away_slot": "2B",
                "fd_id": None, "feeds_into": 90, "date": "2026-06-28",
                "venue": {"stadium": "SoFi Stadium", "city": "Inglewood"},
            },
            {
                "match_id": 76, "round": "round_of_32",
                "home_team": "BRA", "away_team": "JPN",
                "home_slot": "1C", "away_slot": "2F",
                "fd_id": None, "feeds_into": 91, "date": "2026-06-29",
                "venue": {"stadium": "NRG Stadium", "city": "Houston"},
            },
        ],
    }


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _setup_repo(tmp_path):
    """Create a results dir + tournament file under a tmp dir; return their paths."""
    rdir = os.path.join(tmp_path, "results")
    os.makedirs(rdir)
    tpath = os.path.join(tmp_path, "tournament.json")
    _write_json(tpath, _mini_tournament())
    return rdir, tpath


def test_reconcile_backfills_null_match_id(tmp_path):
    rdir, tpath = _setup_repo(str(tmp_path))
    # A knockout result fetched BEFORE the bracket resolved: null ids, API stage.
    _write_json(os.path.join(rdir, "2026-06-29.json"), {
        "date": "2026-06-29",
        "matches": [{
            "match_id": None, "fd_id": None, "stage": "LAST_32",
            "home_team": "BRA", "away_team": "JPN",
            "score": {"home": 2, "away": 1}, "outcome": "home",
        }],
    })

    changed = reconcile_results.reconcile_results(rdir, tpath)
    assert changed == 1

    data = json.load(open(os.path.join(rdir, "2026-06-29.json")))
    m = data["matches"][0]
    # BUG 1: the real BRA-JPN knockout result now carries a real match_id.
    assert m["match_id"] == 76
    assert m["match_id"] is not None
    # BUG 3: stage normalised to the single canonical label.
    assert m["stage"] == "R32"
    assert m["round"] == "round_of_32"


def test_reconcile_is_idempotent(tmp_path):
    rdir, tpath = _setup_repo(str(tmp_path))
    _write_json(os.path.join(rdir, "2026-06-28.json"), {
        "date": "2026-06-28",
        "matches": [{
            "match_id": None, "fd_id": None, "stage": "LAST_32",
            "home_team": "RSA", "away_team": "CAN",
            "score": {"home": 0, "away": 1}, "outcome": "away",
        }],
    })

    first = reconcile_results.reconcile_results(rdir, tpath)
    second = reconcile_results.reconcile_results(rdir, tpath)
    assert first == 1
    # Idempotent: a second pass finds nothing to do.
    assert second == 0

    m = json.load(open(os.path.join(rdir, "2026-06-28.json")))["matches"][0]
    assert m["match_id"] == 73
    assert m["stage"] == "R32"


def test_reconcile_normalizes_stage_even_with_match_id(tmp_path):
    rdir, tpath = _setup_repo(str(tmp_path))
    # match_id already present but the stage label is a stale API alias.
    _write_json(os.path.join(rdir, "x.json"), {
        "date": "2026-06-29",
        "matches": [{
            "match_id": 76, "fd_id": None, "stage": "LAST_32",
            "home_team": "BRA", "away_team": "JPN",
            "score": {"home": 2, "away": 1}, "outcome": "home",
        }],
    })
    changed = reconcile_results.reconcile_results(rdir, tpath)
    assert changed == 1
    m = json.load(open(os.path.join(rdir, "x.json")))["matches"][0]
    assert m["stage"] == "R32"


def test_build_resolved_index_skips_placeholders():
    t = _mini_tournament()
    # Add an unresolved bracket entry (still on slot placeholders).
    t["knockout_bracket"].append({
        "match_id": 90, "round": "round_of_16",
        "home_team": "W73", "away_team": "W74",
    })
    idx = reconcile_results.build_resolved_index(t)
    assert frozenset({"RSA", "CAN"}) in idx
    assert frozenset({"BRA", "JPN"}) in idx
    # The placeholder entry must NOT be indexed (its codes aren't real teams).
    assert frozenset({"W73", "W74"}) not in idx
    assert len(idx) == 2


# --------------------------------------------------------------------------- #
# Set-membership ADVANCEMENT metric
# --------------------------------------------------------------------------- #
def test_compute_real_advancement_partial_round():
    # Only two Round-of-32 matches decided so far.
    results = {
        "73": {"match_id": 73, "home_team": "RSA", "away_team": "CAN",
               "outcome": "away", "score": {"home": 0, "away": 1}},
        "76": {"match_id": 76, "home_team": "BRA", "away_team": "JPN",
               "outcome": "home", "score": {"home": 2, "away": 1}},
    }
    ra = advancement.compute_real_advancement(results)
    assert ra["R16"]["teams"] == {"CAN", "BRA"}
    # Not ready: only 2 of the 16 feeder matches are decided.
    assert ra["R16"]["ready"] is False
    assert ra["QF"]["teams"] == set()


def test_compute_real_advancement_orientation_by_score():
    # No explicit "outcome" — winner must be derived from the score.
    results = {
        "73": {"match_id": 73, "home_team": "RSA", "away_team": "CAN",
               "score": {"home": 3, "away": 1}},
    }
    ra = advancement.compute_real_advancement(results)
    assert ra["R16"]["teams"] == {"RSA"}


def test_compute_real_advancement_ready_when_all_feeders_decided():
    # The two semi-finals (101, 102) fully decide who REACHES the final.
    results = {
        "101": {"match_id": 101, "home_team": "ARG", "away_team": "ESP",
                "outcome": "home", "score": {"home": 1, "away": 0}},
        "102": {"match_id": 102, "home_team": "FRA", "away_team": "ENG",
                "outcome": "home", "score": {"home": 2, "away": 1}},
        "104": {"match_id": 104, "home_team": "ARG", "away_team": "FRA",
                "outcome": "away", "score": {"home": 0, "away": 1}},
    }
    ra = advancement.compute_real_advancement(results)
    assert ra["FINAL"]["ready"] is True
    assert ra["FINAL"]["teams"] == {"ARG", "FRA"}
    assert ra["CHAMPION"]["ready"] is True
    assert ra["CHAMPION"]["teams"] == {"FRA"}


def test_predicted_advancement_reads_bracket_winners():
    prediction = {"bracket": {
        "R32": [{"winner": "CAN"}, {"winner": "BRA"}],
        "R16": [{"winner": "BRA"}],
        "QF": [],
        "SF": [{"winner": "ARG"}, {"winner": "BRA"}],
        "final": {"winner": "ARG"},
    }}
    pa = advancement.predicted_advancement(prediction)
    assert pa["R16"] == {"CAN", "BRA"}
    assert pa["QF"] == {"BRA"}
    assert pa["FINAL"] == {"ARG", "BRA"}
    assert pa["CHAMPION"] == {"ARG"}


def test_score_advancement_hits_missed_and_false_positives():
    real = {
        "R16": {"teams": {"CAN", "BRA"}, "ready": False},
        "QF": {"teams": set(), "ready": False},
        "SF": {"teams": set(), "ready": False},
        "FINAL": {"teams": {"ARG", "FRA"}, "ready": True},
        "CHAMPION": {"teams": {"FRA"}, "ready": True},
    }
    prediction = {"bracket": {
        "R32": [{"winner": "CAN"}, {"winner": "GER"}],   # predicts R16 = {CAN, GER}
        "R16": [],
        "QF": [],
        "SF": [{"winner": "ARG"}, {"winner": "BRA"}],    # predicts FINAL = {ARG, BRA}
        "final": {"winner": "FRA"},                      # predicts CHAMPION = {FRA}
    }}
    sc = advancement.score_advancement(prediction, real)

    r16 = sc["rounds"]["R16"]
    assert r16["hits"] == 1                       # CAN
    assert r16["missed"] == ["BRA"]
    assert r16["false_positives"] == ["GER"]
    assert r16["total"] == 16
    assert r16["ready"] is False

    assert sc["rounds"]["FINAL"]["hits"] == 1     # ARG
    assert sc["rounds"]["CHAMPION"]["hits"] == 1  # FRA

    # Overall aggregates ONLY ready rounds: FINAL(total 2) + CHAMPION(total 1).
    assert sc["total"] == 3
    assert sc["hits"] == 2
    assert sc["ready"] is True
    # score is rounded to 6 decimals by score_advancement.
    assert abs(sc["score"] - (2 / 3)) < 1e-6


# --------------------------------------------------------------------------- #
# Byte-coherence: docs/data/results.json mirrors data/results/*.json
# --------------------------------------------------------------------------- #
def test_dashboard_results_coherent_with_source(tmp_path):
    rdir = os.path.join(str(tmp_path), "results")
    os.makedirs(rdir)
    out_path = os.path.join(str(tmp_path), "docs", "results.json")

    _write_json(os.path.join(rdir, "2026-06-28.json"), {
        "date": "2026-06-28",
        "matches": [
            {"match_id": 73, "stage": "R32", "home_team": "RSA",
             "away_team": "CAN", "score": {"home": 0, "away": 1}, "outcome": "away"},
            {"match_id": None, "stage": "R32", "home_team": "X", "away_team": "Y"},
        ],
    })
    _write_json(os.path.join(rdir, "2026-06-29.json"), {
        "date": "2026-06-29",
        "matches": [
            {"match_id": 76, "stage": "R32", "home_team": "BRA",
             "away_team": "JPN", "score": {"home": 2, "away": 1}, "outcome": "home"},
        ],
    })

    old_rdir = build_dashboard_results.RESULTS_DIR
    old_out = build_dashboard_results.OUTPUT_PATH
    build_dashboard_results.RESULTS_DIR = rdir
    build_dashboard_results.OUTPUT_PATH = out_path
    try:
        build_dashboard_results.main()
    finally:
        build_dashboard_results.RESULTS_DIR = old_rdir
        build_dashboard_results.OUTPUT_PATH = old_out

    out = json.load(open(out_path))
    by_id = {str(m["match_id"]): m for m in out["matches"]}

    # Knockout matches with a real match_id are present and byte-identical.
    assert "73" in by_id and "76" in by_id
    assert by_id["73"]["score"] == {"home": 0, "away": 1}
    assert by_id["76"]["outcome"] == "home"
    # match_id: null entries are dropped (they cannot be keyed/scored).
    assert all(m.get("match_id") is not None for m in out["matches"])


# --------------------------------------------------------------------------- #
# Regression guards on the REAL, committed (reconciled) results
# --------------------------------------------------------------------------- #
def _load_real_results():
    matches = []
    for fp in sorted(glob.glob(os.path.join(REAL_RESULTS_DIR, "*.json"))):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        matches.extend(data.get("matches", []) if isinstance(data, dict) else data)
    return matches


def test_real_knockout_results_have_match_id():
    """BUG 1 regression: the played knockout games are no longer match_id: null."""
    matches = _load_real_results()

    def find_pair(a, b):
        for m in matches:
            teams = {m.get("home_team"), m.get("away_team")}
            if teams == {a, b} and m.get("outcome") is not None:
                return m
        return None

    rsa_can = find_pair("RSA", "CAN")
    bra_jpn = find_pair("BRA", "JPN")
    assert rsa_can is not None, "RSA-CAN knockout result missing from real data"
    assert bra_jpn is not None, "BRA-JPN knockout result missing from real data"
    assert rsa_can["match_id"] == 73
    assert bra_jpn["match_id"] == 76
    # And their stage is the single canonical label.
    assert utils.normalize_stage(rsa_can.get("stage"), rsa_can.get("match_id")) == "R32"
    assert utils.normalize_stage(bra_jpn.get("stage"), bra_jpn.get("match_id")) == "R32"


def test_real_results_orientation_is_consistent():
    """Every played result's outcome must agree with its score orientation."""
    for m in _load_real_results():
        outcome = m.get("outcome")
        if outcome is None:
            continue
        score = m.get("score") or {}
        hs, as_ = score.get("home"), score.get("away")
        if not isinstance(hs, int) or not isinstance(as_, int):
            continue
        if outcome == "home":
            assert hs > as_, f"match {m.get('match_id')}: outcome home but {hs}-{as_}"
        elif outcome == "away":
            assert as_ > hs, f"match {m.get('match_id')}: outcome away but {hs}-{as_}"
        elif outcome == "draw":
            assert hs == as_, f"match {m.get('match_id')}: outcome draw but {hs}-{as_}"
