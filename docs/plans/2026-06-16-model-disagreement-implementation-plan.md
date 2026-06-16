# Model Disagreement View Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a FastAPI endpoint `GET /api/disagreement` that returns matches sorted by 1X2 prediction disagreement across models, plus a new dashboard tab that renders those matches.

**Architecture:** A small FastAPI app in `src/api/` reads frozen pre-tournament predictions and tournament metadata, computes a per-match variance-based disagreement score, and exposes it via a single endpoint. The existing static dashboard gains a vanilla-JS tab that consumes this endpoint.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, pytest; vanilla JS + Tailwind in `docs/`.

---

### Task 1: Add FastAPI dependencies to requirements.txt

**Files:**
- Modify: `requirements.txt`

**Step 1: Add dependencies**

Append at the end of `requirements.txt`:

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
```

**Step 2: Install locally**

Run:
```bash
pip install -r requirements.txt
```

Expected: installs `fastapi` and `uvicorn` without errors.

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fastapi and uvicorn dependencies

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create prediction and tournament loading utilities

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/disagreement.py`
- Test: `tests/test_disagreement.py`

**Step 1: Write failing test for utility functions**

Create `tests/test_disagreement.py`:

```python
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
        pred_dir.parent,
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
```

**Step 2: Run test, expect failure**

```bash
python -m pytest tests/test_disagreement.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `src.api.disagreement`.

**Step 3: Implement utilities**

Create `src/api/__init__.py` (empty) and `src/api/disagreement.py`:

```python
import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "predictions" / "pre-tournament"
TOURNAMENT_PATH = BASE_DIR / "data" / "tournament.json"


def load_predictions(directory: Path = PREDICTIONS_DIR) -> list[dict[str, Any]]:
    predictions = []
    if not directory.exists():
        return predictions
    for path in sorted(directory.glob("*_prediction.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            predictions.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return predictions


def load_tournament(path: Path = TOURNAMENT_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Tournament file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
```

**Step 4: Run test, expect pass**

```bash
python -m pytest tests/test_disagreement.py::test_load_predictions_finds_pre_tournament_files tests/test_disagreement.py::test_load_tournament_returns_matches_and_knockout -v
```

Expected: 2 passed.

**Step 5: Commit**

```bash
git add src/api/ tests/test_disagreement.py
git commit -m "feat(api): add prediction and tournament loading utilities

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Implement disagreement score calculation

**Files:**
- Modify: `src/api/disagreement.py`
- Test: `tests/test_disagreement.py`

**Step 1: Write failing tests for calculation**

Append to `tests/test_disagreement.py`:

```python
from src.api.disagreement import compute_disagreement, PHASE_GROUP, PHASE_KNOCKOUT


def test_compute_disagreement_group_basic():
    predictions = [
        {"probs": {"home": 0.5, "draw": 0.3, "away": 0.2}},
        {"probs": {"home": 0.5, "draw": 0.3, "away": 0.2}},
    ]
    score = compute_disagreement(predictions, PHASE_GROUP)
    assert score == pytest.approx(0.0, abs=1e-9)


def test_compute_disagreement_group_variance():
    predictions = [
        {"probs": {"home": 1.0, "draw": 0.0, "away": 0.0}},
        {"probs": {"home": 0.0, "draw": 1.0, "away": 0.0}},
    ]
    score = compute_disagreement(predictions, PHASE_GROUP)
    # variance of [1.0, 0.0] = 0.25 for each outcome; mean = 0.25
    assert score == pytest.approx(0.25, abs=1e-9)


def test_compute_disagreement_knockout_ignores_draw():
    predictions = [
        {"probs": {"home": 0.7, "draw": 0.2, "away": 0.1}},
        {"probs": {"home": 0.1, "draw": 0.2, "away": 0.7}},
    ]
    score = compute_disagreement(predictions, PHASE_KNOCKOUT)
    # normalized: [0.875, 0.125] and [0.125, 0.875]
    # variance home = variance away = 0.28125; mean = 0.28125
    assert score == pytest.approx(0.28125, abs=1e-9)


def test_compute_disagreement_knockout_all_draw_still_works():
    predictions = [
        {"probs": {"home": 0.4, "draw": 0.2, "away": 0.4}},
        {"probs": {"home": 0.4, "draw": 0.2, "away": 0.4}},
    ]
    score = compute_disagreement(predictions, PHASE_KNOCKOUT)
    assert score == pytest.approx(0.0, abs=1e-9)
```

**Step 2: Run tests, expect failure**

```bash
python -m pytest tests/test_disagreement.py::test_compute_disagreement_group_basic tests/test_disagreement.py::test_compute_disagreement_group_variance tests/test_disagreement.py::test_compute_disagreement_knockout_ignores_draw tests/test_disagreement.py::test_compute_disagreement_knockout_all_draw_still_works -v
```

Expected: 4 failed (function not defined).

**Step 3: Implement calculation**

Append to `src/api/disagreement.py`:

```python
from statistics import variance

PHASE_GROUP = "group"
PHASE_KNOCKOUT = "knockout"


def compute_disagreement(
    predictions: list[dict[str, Any]],
    phase: str,
) -> float:
    if len(predictions) < 2:
        return 0.0

    if phase == PHASE_KNOCKOUT:
        home_raw = [p["probs"]["home"] for p in predictions]
        away_raw = [p["probs"]["away"] for p in predictions]
        home = []
        away = []
        for h, a in zip(home_raw, away_raw):
            total = h + a
            if total == 0:
                home.append(0.5)
                away.append(0.5)
            else:
                home.append(h / total)
                away.append(a / total)
        values = [home, away]
    else:
        home = [p["probs"]["home"] for p in predictions]
        draw = [p["probs"]["draw"] for p in predictions]
        away = [p["probs"]["away"] for p in predictions]
        values = [home, draw, away]

    return sum(variance(v) for v in values) / len(values)
```

**Step 4: Run tests, expect pass**

```bash
python -m pytest tests/test_disagreement.py -k compute_disagreement -v
```

Expected: 4 passed.

**Step 5: Commit**

```bash
git add src/api/disagreement.py tests/test_disagreement.py
git commit -m "feat(api): implement variance-based disagreement score

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Build match-model pairing and response assembly

**Files:**
- Modify: `src/api/disagreement.py`
- Test: `tests/test_disagreement.py`

**Step 1: Write failing test for assembly**

Append to `tests/test_disagreement.py`:

```python
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
```

**Step 2: Run tests, expect failure**

```bash
python -m pytest tests/test_disagreement.py::test_build_disagreement_response_basic -v
```

Expected: `ImportError` for `build_disagreement_response`.

**Step 3: Implement assembly**

Append to `src/api/disagreement.py`:

```python
import re

KNOCKOUT_ROUNDS = ["R32", "R16", "QF", "SF", "third_place", "final"]


def _normalise_model_name(name: str) -> str:
    return re.sub(r"[\s_-]+", "-", name).strip().lower()


def _find_knockout_match(bracket: dict[str, Any], match_id: int) -> dict[str, Any] | None:
    for round_key in KNOCKOUT_ROUNDS:
        items = bracket.get(round_key, [])
        for item in items:
            if str(item.get("match_id")) == str(match_id):
                return item
    return None


def _collect_model_predictions(
    match_id: int,
    phase: str,
    predictions: list[dict[str, Any]],
) -> list[dict[str, float]]:
    collected = []
    for pred in predictions:
        model_name = pred.get("model", "Unknown")
        if phase == PHASE_KNOCKOUT:
            match = _find_knockout_match(pred.get("bracket", {}), match_id)
        else:
            match = next(
                (m for m in pred.get("group_matches", []) if str(m.get("match_id")) == str(match_id)),
                None,
            )
        if match:
            collected.append({
                "model": model_name,
                **match.get("probs", {"home": 0.0, "draw": 0.0, "away": 0.0}),
            })
    return collected


def build_disagreement_response(
    tournament: dict[str, Any],
    predictions: list[dict[str, Any]],
    phase: str | None,
    model_names: list[str] | None,
) -> dict[str, Any]:
    if model_names:
        allowed = {_normalise_model_name(n) for n in model_names}
        predictions = [
            p for p in predictions
            if _normalise_model_name(p.get("model", "")) in allowed
        ]

    all_matches = []
    for m in tournament.get("matches", []):
        all_matches.append({"data": m, "phase": PHASE_GROUP})
    for m in tournament.get("knockout_bracket", []):
        all_matches.append({"data": m, "phase": PHASE_KNOCKOUT})

    if phase:
        all_matches = [m for m in all_matches if m["phase"] == phase]

    results = []
    for item in all_matches:
        data = item["data"]
        match_id = data["match_id"]
        model_predictions = _collect_model_predictions(match_id, item["phase"], predictions)
        if len(model_predictions) < 2:
            continue
        score = compute_disagreement(model_predictions, item["phase"])
        results.append({
            "match_id": match_id,
            "phase": item["phase"],
            "group": data.get("group") if item["phase"] == PHASE_GROUP else None,
            "round": data.get("round") if item["phase"] == PHASE_KNOCKOUT else None,
            "home_team": data.get("home_team"),
            "away_team": data.get("away_team"),
            "date": data.get("date"),
            "disagreement_score": round(score, 6),
            "model_predictions": model_predictions,
        })

    results.sort(key=lambda x: x["disagreement_score"], reverse=True)

    return {
        "matches": results,
        "meta": {
            "total_matches": len(results),
            "models_used": [p.get("model", "Unknown") for p in predictions],
            "phase_filter": phase,
            "models_filter": model_names,
        },
    }
```

**Step 4: Run tests, expect pass**

```bash
python -m pytest tests/test_disagreement.py::test_build_disagreement_response_basic -v
```

Expected: 1 passed.

**Step 5: Commit**

```bash
git add src/api/disagreement.py tests/test_disagreement.py
git commit -m "feat(api): pair matches with predictions and assemble response

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire up FastAPI endpoint

**Files:**
- Create: `src/api/main.py`
- Test: `tests/test_disagreement.py`

**Step 1: Write failing test for endpoint**

Append to `tests/test_disagreement.py`:

```python
from fastapi.testclient import TestClient
from src.api.main import app


client = TestClient(app)


def test_get_disagreement_returns_matches():
    response = client.get("/api/disagreement")
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert "meta" in data
    assert data["meta"]["total_matches"] == 104


def test_get_disagreement_phase_filter():
    response = client.get("/api/disagreement?phase=group")
    assert response.status_code == 200
    data = response.json()
    assert all(m["phase"] == "group" for m in data["matches"])
    assert data["meta"]["total_matches"] == 72


def test_get_disagreement_invalid_phase():
    response = client.get("/api/disagreement?phase=invalid")
    assert response.status_code == 400
```

**Step 2: Run tests, expect failure**

```bash
python -m pytest tests/test_disagreement.py::test_get_disagreement_returns_matches -v
```

Expected: `ModuleNotFoundError` for `src.api.main`.

**Step 3: Implement FastAPI app**

Create `src/api/main.py`:

```python
from fastapi import FastAPI, HTTPException, Query
from typing import Annotated

from src.api.disagreement import (
    PHASE_GROUP,
    PHASE_KNOCKOUT,
    build_disagreement_response,
    load_predictions,
    load_tournament,
)

app = FastAPI(title="WorldCupBench API")

VALID_PHASES = {PHASE_GROUP, PHASE_KNOCKOUT}


@app.get("/api/disagreement")
def get_disagreement(
    phase: Annotated[str | None, Query(description="Filter by phase: group or knockout")] = None,
    models: Annotated[str | None, Query(description="Comma-separated model names")] = None,
):
    if phase and phase not in VALID_PHASES:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")

    model_names = None
    if models:
        model_names = [m.strip() for m in models.split(",") if m.strip()]

    try:
        tournament = load_tournament()
        predictions = load_predictions()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not predictions:
        raise HTTPException(status_code=500, detail="No predictions found")

    return build_disagreement_response(tournament, predictions, phase, model_names)
```

**Step 4: Run tests, expect pass**

```bash
python -m pytest tests/test_disagreement.py -k "get_disagreement" -v
```

Expected: 3 passed.

**Step 5: Commit**

```bash
git add src/api/main.py tests/test_disagreement.py
git commit -m "feat(api): add GET /api/disagreement endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Add model filter tests

**Files:**
- Modify: `tests/test_disagreement.py`

**Step 1: Write tests**

Append to `tests/test_disagreement.py`:

```python
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
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_disagreement.py::test_get_disagreement_model_filter tests/test_disagreement.py::test_get_disagreement_unknown_model -v
```

Expected: 2 passed.

**Step 3: Commit**

```bash
git add tests/test_disagreement.py
git commit -m "test(api): cover model filter in disagreement endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Add run script for API server

**Files:**
- Modify: `README.md`

**Step 1: Document how to run the API**

Append a small section to `README.md` under "Quick Start":

```markdown
### Run the API server

```bash
uvicorn src.api.main:app --reload --port 8000
```

The disagreement endpoint is available at `http://localhost:8000/api/disagreement`.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document how to run the API server

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Add "Disagreement" tab to docs/index.html

**Files:**
- Modify: `docs/index.html`

**Step 1: Locate tab container**

Find the tab navigation in `docs/index.html`. It currently contains buttons like:

```html
<button id="tab-leaderboard" ...>Leaderboard</button>
```

**Step 2: Add tab button**

Insert after the Bracket tab button:

```html
<button id="tab-disagreement" onclick="showTab('disagreement')" class="tab-inactive pb-3 text-sm font-medium whitespace-nowrap transition">Disagreement</button>
```

**Step 3: Add section container**

Find the bracket section:

```html
<section id="section-bracket" ...>
```

Insert after it closes:

```html
<section id="section-disagreement" class="hidden">
  <div class="mb-6">
    <h2 class="text-2xl font-bold text-white mb-2">Model Disagreement</h2>
    <p class="text-gray-400 text-sm">Matches where models disagree most on the 1X2 probabilities.</p>
  </div>
  <div id="disagreement-filters" class="flex flex-wrap gap-2 mb-6"></div>
  <div id="disagreement-content">
    <p class="text-gray-500 text-center py-12">Loading disagreement data...</p>
  </div>
</section>
```

**Step 4: Commit**

```bash
git add docs/index.html
git commit -m "feat(dashboard): add disagreement tab shell

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Implement disagreement rendering in docs/app.js

**Files:**
- Modify: `docs/app.js`

**Step 1: Add API base URL**

At the top of `docs/app.js`, after `MODEL_COLORS`:

```javascript
const API_BASE_URL = window.location.hostname === 'localhost'
  ? 'http://localhost:8000'
  : '';  // served behind same-origin proxy in production
```

**Step 2: Add disagreement data loader**

After `loadData()`:

```javascript
async function loadDisagreement(phase = 'all') {
  const el = document.getElementById('disagreement-content');
  el.innerHTML = '<p class="text-gray-500 text-center py-12">Loading...</p>';
  try {
    const url = new URL(`${API_BASE_URL}/api/disagreement`);
    if (phase !== 'all') url.searchParams.set('phase', phase);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderDisagreement(data.matches, phase);
  } catch (e) {
    el.innerHTML = `<p class="text-red-400 text-center py-12">Could not load disagreement data. Make sure the API server is running.</p>`;
    console.error('Disagreement load error:', e);
  }
}
```

**Step 3: Add render function**

```javascript
function renderDisagreement(matches, activePhase) {
  const filtersEl = document.getElementById('disagreement-filters');
  const contentEl = document.getElementById('disagreement-content');

  const phases = [
    { key: 'all', label: 'All' },
    { key: 'group', label: 'Group Stage' },
    { key: 'knockout', label: 'Knockout' },
  ];

  filtersEl.innerHTML = phases.map(p => `
    <button onclick="loadDisagreement('${p.key}')"
      class="px-3 py-1 rounded-full text-xs font-medium ${p.key === activePhase ? 'bg-gold text-black' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}">
      ${p.label}
    </button>
  `).join('');

  if (!matches.length) {
    contentEl.innerHTML = '<p class="text-gray-500 text-center py-12">No disagreement data available.</p>';
    return;
  }

  contentEl.innerHTML = `
    <div class="space-y-4">
      ${matches.map((m, index) => renderDisagreementCard(m, index)).join('')}
    </div>
  `;
}

function renderDisagreementCard(match, index) {
  const isHot = index < 10;
  const date = new Date(match.date + 'T00:00:00');
  const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const phaseLabel = match.phase === 'group' ? `Group ${match.group}` : match.round.replace(/_/g, ' ');
  const maxScore = Math.max(...match.model_predictions.map(mp => Math.max(mp.home, mp.draw || 0, mp.away)));

  return `
    <div class="glass rounded-xl p-4 ${isHot ? 'border-red-500/40' : ''} hover:border-gold/30 transition">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <span class="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">${phaseLabel}</span>
          ${isHot ? '<span class="text-xs px-2 py-0.5 rounded bg-red-900/50 text-red-400 font-bold">Top Disagreement</span>' : ''}
        </div>
        <span class="text-xs text-gray-500">${dateStr}</span>
      </div>
      <div class="flex items-center justify-between mb-4">
        <div class="text-center flex-1">
          <div class="text-2xl mb-1">${codeToFlag(match.home_team)}</div>
          <div class="text-xs font-medium text-white">${match.home_team}</div>
        </div>
        <div class="text-center px-4">
          <div class="text-xs text-gray-400">vs</div>
        </div>
        <div class="text-center flex-1">
          <div class="text-2xl mb-1">${codeToFlag(match.away_team)}</div>
          <div class="text-xs font-medium text-white">${match.away_team}</div>
        </div>
      </div>
      <div class="mb-3">
        <div class="text-xs text-gray-400 mb-1">Disagreement score</div>
        <div class="text-xl font-bold ${isHot ? 'text-red-400' : 'text-gold'}">${match.disagreement_score.toFixed(6)}</div>
      </div>
      <div class="space-y-2">
        ${match.model_predictions.map(mp => renderModelPrediction(mp, match.phase, maxScore)).join('')}
      </div>
    </div>
  `;
}

function renderModelPrediction(mp, phase, maxScore) {
  const color = MODEL_COLORS[mp.model] || '#9CA3AF';
  const outcomes = phase === 'knockout'
    ? [['home', mp.home], ['away', mp.away]]
    : [['home', mp.home], ['draw', mp.draw], ['away', mp.away]];

  return `
    <div class="flex items-center gap-3 text-xs">
      <div class="w-28 flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" style="background:${color}"></div>
        <span class="text-white truncate">${mp.model}</span>
      </div>
      <div class="flex-1 flex gap-1">
        ${outcomes.map(([label, value]) => `
          <div class="flex-1 bg-gray-800 rounded h-5 overflow-hidden relative">
            <div class="h-full flex items-center justify-end px-1 text-[10px] font-bold text-black" style="width:${(value / maxScore * 100).toFixed(0)}%; background:${color}80">
              ${label[0].toUpperCase()}
            </div>
          </div>
        `).join('')}
      </div>
      <div class="w-24 text-right text-gray-400">
        ${outcomes.map(([label, value]) => `${label[0].toUpperCase()}:${value.toFixed(2)}`).join(' ')}
      </div>
    </div>
  `;
}
```

**Step 4: Wire tab switching**

In `showTab(name)`:

```javascript
function showTab(name) {
  ['leaderboard', 'consensus', 'matches', 'bracket', 'disagreement'].forEach(t => {
    document.getElementById(`section-${t}`).classList.toggle('hidden', t !== name);
    document.getElementById(`tab-${t}`).className = t === name
      ? 'tab-active pb-3 text-sm font-medium whitespace-nowrap transition'
      : 'tab-inactive pb-3 text-sm font-medium whitespace-nowrap transition';
  });
  if (name === 'disagreement') {
    loadDisagreement('all');
  }
}
```

**Step 5: Commit**

```bash
git add docs/app.js
git commit -m "feat(dashboard): render disagreement view with filters and highlights

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Final verification

**Files:**
- All modified files.

**Step 1: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass (initial 21 + new disagreement tests).

**Step 2: Start API server and smoke-test**

```bash
uvicorn src.api.main:app --port 8000 &
sleep 2
curl -s "http://localhost:8000/api/disagreement?phase=group" | head -c 200
curl -s "http://localhost:8000/api/disagreement?phase=knockout" | head -c 200
kill %1
```

Expected: JSON responses with `matches` array.

**Step 3: Verify dashboard HTML**

Open `docs/index.html` in a browser with the API server running, click the Disagreement tab, and confirm:
- List is sorted by score descending.
- Top 10 items have "Top Disagreement" badge.
- Phase filters work.
- Per-model probability bars render.

**Step 4: Final commit if any remaining changes**

```bash
git add -A
git commit -m "feat: Model Disagreement View backend and dashboard tab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for implementer

- Keep `src/api/disagreement.py` free of FastAPI imports so it remains testable as pure Python.
- Match IDs in predictions are strings; in `tournament.json` they are integers. Always compare via `str()`.
- The dashboard uses `fetch` to `localhost:8000` only when served locally. In production, serve the API and static files under the same origin or adjust `API_BASE_URL`.
- The existing `MODEL_COLORS` map already covers all current models; new models will fall back to gray.
