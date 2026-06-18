import pytest
from src.api.disagreement import load_predictions, load_tournament


def test_load_predictions_finds_pre_tournament_files(tmp_path, monkeypatch):
    # Create a fake predictions directory
    pred_dir = tmp_path / "predictions" / "pre-tournament"
    pred_dir.mkdir(parents=True)
    (pred_dir / "model_a_prediction.json").write_text('{"model": "Model-A"}')
    (pred_dir / "model_b_prediction.json").write_text('{"model": "Model-B"}')

    monkeypatch.setattr(
        "src.api.disagreement.PREDICTIONS_DIR",
        pred_dir,
    )
    preds = load_predictions()
    assert len(preds) == 2
    assert {p["model"] for p in preds} == {"Model-A", "Model-B"}


def test_load_tournament_returns_matches_and_knockout():
    tournament = load_tournament()
    assert "matches" in tournament
    assert "knockout_bracket" in tournament
    assert len(tournament["matches"]) == 72
    assert len(tournament["knockout_bracket"]) == 32


from src.api.disagreement import compute_disagreement, PHASE_GROUP, PHASE_KNOCKOUT


def test_compute_disagreement_group_basic():
    predictions = [
        {"home": 0.5, "draw": 0.3, "away": 0.2},
        {"home": 0.5, "draw": 0.3, "away": 0.2},
    ]
    score = compute_disagreement(predictions, PHASE_GROUP)
    assert score == pytest.approx(0.0, abs=1e-9)


def test_compute_disagreement_group_variance():
    predictions = [
        {"home": 1.0, "draw": 0.0, "away": 0.0},
        {"home": 0.0, "draw": 1.0, "away": 0.0},
    ]
    score = compute_disagreement(predictions, PHASE_GROUP)
    # population std dev: home=0.5, draw=0.5, away=0.0; sum=1.0
    assert score == pytest.approx(1.0, abs=1e-9)


def test_compute_disagreement_knockout_ignores_draw():
    predictions = [
        {"home": 0.7, "draw": 0.2, "away": 0.1},
        {"home": 0.1, "draw": 0.2, "away": 0.7},
    ]
    score = compute_disagreement(predictions, PHASE_KNOCKOUT)
    # normalized: [0.875, 0.125] and [0.125, 0.875]
    # population std dev home = std dev away = sqrt(0.140625) = 0.375; sum = 0.75
    assert score == pytest.approx(0.75, abs=1e-9)


def test_compute_disagreement_knockout_all_draw_still_works():
    predictions = [
        {"home": 0.4, "draw": 0.2, "away": 0.4},
        {"home": 0.4, "draw": 0.2, "away": 0.4},
    ]
    score = compute_disagreement(predictions, PHASE_KNOCKOUT)
    assert score == pytest.approx(0.0, abs=1e-9)


from src.api.disagreement import build_disagreement_response


def test_build_disagreement_response_basic():
    tournament = {
        "matches": [
            {
                "match_id": 1,
                "group": "A",
                "home_team": "MEX",
                "away_team": "RSA",
                "date": "2026-06-11",
            }
        ],
        "knockout_bracket": [],
    }
    predictions = [
        {
            "model": "Model-A",
            "group_matches": [
                {"match_id": "1", "probs": {"home": 0.7, "draw": 0.2, "away": 0.1}}
            ],
            "bracket": {"R32": [], "R16": [], "QF": [], "SF": [], "third_place": [], "final": []},
        },
        {
            "model": "Model-B",
            "group_matches": [
                {"match_id": "1", "probs": {"home": 0.3, "draw": 0.4, "away": 0.3}}
            ],
            "bracket": {"R32": [], "R16": [], "QF": [], "SF": [], "third_place": [], "final": []},
        },
    ]
    result = build_disagreement_response(tournament, predictions, phase=None, model_names=None)
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["match_id"] == 1
    assert match["phase"] == PHASE_GROUP
    assert match["disagreement_score"] > 0
    assert len(match["model_predictions"]) == 2
    assert result["meta"]["models_used"] == ["Model-A", "Model-B"]


from fastapi.testclient import TestClient
from src.api.main import app


client = TestClient(app)


def test_get_disagreement_returns_matches():
    response = client.get("/api/disagreement")
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert "meta" in data
    # Group stage always has 72 matches; knockout count depends on how many
    # models provided bracket predictions (freeze-v3 models did not).
    assert data["meta"]["total_matches"] >= 72
    for match in data["matches"]:
        assert len(match["model_predictions"]) >= 2


def test_get_disagreement_phase_filter():
    response = client.get("/api/disagreement?phase=group")
    assert response.status_code == 200
    data = response.json()
    assert all(m["phase"] == "group" for m in data["matches"])
    assert data["meta"]["total_matches"] == 72


def test_get_disagreement_invalid_phase():
    response = client.get("/api/disagreement?phase=invalid")
    assert response.status_code == 400


def test_get_disagreement_model_filter():
    response = client.get("/api/disagreement?models=GPT-5.5")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["models_used"] == ["GPT-5.5"]
    for match in data["matches"]:
        assert len(match["model_predictions"]) == 1


def test_get_disagreement_unknown_model():
    response = client.get("/api/disagreement?models=Not-A-Model")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total_matches"] == 0
