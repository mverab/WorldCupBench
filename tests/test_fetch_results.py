import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_results


def test_map_api_to_tournament_uses_fd_id():
    tournament = {
        "matches": [
            {"match_id": 1, "home_team": "MEX", "away_team": "RSA", "date": "2026-06-11", "fd_id": 123}
        ]
    }
    api_match = {
        "id": 123,
        "utcDate": "2026-06-11T19:00:00Z",
        "homeTeam": {"tla": "MEX"},
        "awayTeam": {"tla": "RSA"},
        "status": "FINISHED",
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
    result = fetch_results.map_api_match(api_match, tournament)
    assert result["fd_id"] == 123
    # match_id is preserved as-is from tournament.json (canonically an integer).
    assert result["match_id"] == 1
    assert result["outcome"] == "home"
