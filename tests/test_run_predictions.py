import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import run_predictions


def test_build_messages_injects_tournament_json():
    prompt = "{{TOURNAMENT_JSON}}"
    tournament = {"groups": []}
    messages = run_predictions.build_messages("GPT", prompt, tournament)
    content = messages[0]["content"]
    assert "{{TOURNAMENT_JSON}}" not in content
    assert json.loads(content) == tournament
