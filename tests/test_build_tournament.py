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
