import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_tournament


def test_add_fd_ids_enriches_without_changing_structure(tmp_path):
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

    result = build_tournament.add_fd_ids(existing, api_matches)

    assert result["matches"][0]["fd_id"] == 123456
    assert result["matches"][0]["venue"] == "Azteca"
    assert "groups" in result
