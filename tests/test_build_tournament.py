import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_tournament


def test_build_api_index_and_enrich(tmp_path):
    existing = {
        "edition": "2026",
        "groups": [{"group": "A", "teams": ["MEX", "RSA", "KOR", "CZE"]}],
        "matches": [
            {
                "match_id": 1,
                "stage": "GROUP_STAGE",
                "group": "A",
                "date": "2026-06-11",
                "home_team": "MEX",
                "away_team": "RSA",
                "venue": "Azteca",
            }
        ],
    }
    api_matches = [
        {
            "id": 123456,
            "stage": "GROUP_STAGE",
            "group": "GROUP_A",
            "utcDate": "2026-06-11T19:00:00Z",
            "homeTeam": {"tla": "MEX"},
            "awayTeam": {"tla": "RSA"},
            "status": "TIMED",
        }
    ]

    api_index = build_tournament.build_api_index(api_matches)
    matched = build_tournament.enrich(existing["matches"], api_index)

    assert matched == 1
    assert existing["matches"][0]["fd_id"] == 123456
    assert existing["matches"][0]["venue"] == "Azteca"
    assert "groups" in existing


def test_knockout_placeholders_are_not_matched_or_warned(capsys):
    """Knockout placeholders like '2A' or 'W74' never match the API and must not warn."""
    tournament = {
        "matches": [
            {
                "match_id": 1,
                "stage": "GROUP_STAGE",
                "group": "A",
                "date": "2026-06-11",
                "home_team": "MEX",
                "away_team": "RSA",
            }
        ],
        "knockout_bracket": [
            {
                "match_id": 97,
                "stage": "ROUND_OF_32",
                "date": "2026-06-27",
                "home_team": "2A",
                "away_team": "2B",
            }
        ],
    }
    api_matches = [
        {
            "id": 123456,
            "utcDate": "2026-06-11T19:00:00Z",
            "homeTeam": {"tla": "MEX"},
            "awayTeam": {"tla": "RSA"},
        }
    ]

    api_index = build_tournament.build_api_index(api_matches)
    group_matched = build_tournament.enrich(tournament["matches"], api_index)
    knockout_matched = build_tournament.enrich(tournament["knockout_bracket"], api_index)

    assert group_matched == 1
    assert tournament["matches"][0]["fd_id"] == 123456
    assert knockout_matched == 0
    assert "fd_id" not in tournament["knockout_bracket"][0]

    # Simulate the warning logic from main(), scoped to group matches only.
    no_fd = [m.get("match_id") for m in tournament["matches"] if "fd_id" not in m]
    assert no_fd == []
    captured = capsys.readouterr()
    assert "WARNING" not in captured.out


def test_group_match_missing_fd_id_warns(capsys):
    """A group match not present in the API should be reported as a warning."""
    tournament = {
        "matches": [
            {
                "match_id": 2,
                "stage": "GROUP_STAGE",
                "group": "B",
                "date": "2026-06-12",
                "home_team": "USA",
                "away_team": "GER",
            }
        ],
    }
    api_index = build_tournament.build_api_index([])
    build_tournament.enrich(tournament["matches"], api_index)

    no_fd = [m.get("match_id") for m in tournament["matches"] if "fd_id" not in m]
    print(f"WARNING: {len(no_fd)} partidos de grupo sin fd_id: {no_fd[:10]}")

    captured = capsys.readouterr()
    assert "WARNING: 1 partidos de grupo sin fd_id" in captured.out
