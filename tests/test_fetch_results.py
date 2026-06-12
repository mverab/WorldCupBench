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


def test_map_api_match_resilient_to_utc_date_shift():
    """A match that kicks off in the evening local time is reported on the next
    calendar day in UTC by football-data.org. The mapper must still resolve the
    canonical fixture (via fd_id / team pair) and file it under the local date.
    """
    tournament = {
        "matches": [
            {
                "match_id": 2,
                "group": "A",
                "home_team": "KOR",
                "away_team": "CZE",
                "date": "2026-06-11",
                "fd_id": 537328,
            }
        ]
    }
    api_match = {
        "id": 537328,
        "utcDate": "2026-06-12T02:00:00Z",  # next-day UTC
        "homeTeam": {"tla": "KOR"},
        "awayTeam": {"tla": "CZE"},
        "status": "FINISHED",
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
    result = fetch_results.map_api_match(api_match, tournament)
    assert result["fd_id"] == 537328
    assert result["match_id"] == 2
    assert isinstance(result["match_id"], int)
    # Canonical (local) date is used, not the API's UTC date.
    assert result["date"] == "2026-06-11"
    assert result["stage"] == "GROUP_STAGE"
    assert result["group"] == "GROUP_A"
    assert result["outcome"] == "home"


def test_map_api_match_falls_back_to_team_pair_without_id():
    """When the API id is missing, the ordered team pair still resolves the
    fixture even if the reported date differs."""
    tournament = {
        "matches": [
            {
                "match_id": 2,
                "group": "A",
                "home_team": "KOR",
                "away_team": "CZE",
                "date": "2026-06-11",
                "fd_id": 537328,
            }
        ]
    }
    api_match = {
        "utcDate": "2026-06-12T02:00:00Z",
        "homeTeam": {"tla": "KOR"},
        "awayTeam": {"tla": "CZE"},
        "status": "FINISHED",
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
    result = fetch_results.map_api_match(api_match, tournament)
    assert result["match_id"] == 2
    assert result["fd_id"] == 537328
    assert result["date"] == "2026-06-11"
