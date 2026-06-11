import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import utils


def test_prompt_contains_tournament_placeholder():
    prompt = utils.load_prompt()
    assert "{{TOURNAMENT_JSON}}" in prompt
    assert "home" in prompt
    assert "draw" in prompt
    assert "away" in prompt
