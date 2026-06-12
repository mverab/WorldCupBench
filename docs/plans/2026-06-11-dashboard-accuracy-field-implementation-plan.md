# Dashboard Accuracy Field Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `accuracy`, `correct`, and `exact` fields to `leaderboard.json`, update the dashboard to read `model.accuracy` safely, and regenerate the published leaderboard.

**Architecture:** The scorer becomes the source of truth for accuracy by deriving it from `correct_outcomes / total_evaluated`. The dashboard stops computing accuracy locally and instead reads the explicit `accuracy` field, rendering `—` when it is `null`. The published `docs/data/leaderboard.json` is regenerated from the current results.

**Tech Stack:** Python 3, pytest, vanilla JavaScript (static dashboard), GitHub Pages for docs deployment.

---

## Task 1: Write failing tests for new leaderboard fields

**Files:**
- Modify: `tests/test_score.py`

**Step 1: Add test for accuracy/correct/exact on a finished match**

Append to `tests/test_score.py`:

```python
def test_score_includes_accuracy_correct_exact():
    """A finished match should expose accuracy, correct, and exact fields."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        result_path = os.path.join(results_dir, "2026-06-11.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": "2026-06-11",
                "matches": [{
                    "fd_id": 1,
                    "match_id": "1",
                    "home_team": "USA",
                    "away_team": "MEX",
                    "score": {"home": 2, "away": 1},
                    "outcome": "home",
                    "date": "2026-06-11",
                    "stage": "GROUP_STAGE",
                    "group": "A",
                }]
            }, f)

        predictions = [_make_prediction("1", {"home": 0.6, "draw": 0.2, "away": 0.2})]
        output_path = os.path.join(out_dir, "leaderboard.json")
        leaderboard = score.generate_leaderboard(results_dir, output_path, predictions)

        model = leaderboard["models"][0]
        assert "accuracy" in model
        assert "correct" in model
        assert "exact" in model
        assert model["accuracy"] == 100.0
        assert model["correct"] == 1
        assert model["exact"] == 0
```

**Step 2: Add test for null accuracy when no matches are evaluated**

Append to `tests/test_score.py`:

```python
def test_score_null_accuracy_when_no_matches_evaluated():
    """Accuracy must be null (not 0 or undefined) when no matches have results."""
    with tempfile.TemporaryDirectory() as results_dir, tempfile.TemporaryDirectory() as out_dir:
        template_path = os.path.join(results_dir, "2026-06-11.json")
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": "2026-06-11",
                    "matches": [
                        {
                            "fd_id": 1,
                            "match_id": "1",
                            "home_team": "USA",
                            "away_team": "MEX",
                            "score": {"home": None, "away": None},
                            "outcome": None,
                            "date": "2026-06-11",
                            "stage": "group_stage",
                            "group": "A",
                        }
                    ],
                },
                f,
            )

        output_path = os.path.join(out_dir, "leaderboard.json")
        predictions = [_make_prediction("1")]
        leaderboard = score.generate_leaderboard(results_dir, output_path, predictions)

        model = leaderboard["models"][0]
        assert model["accuracy"] is None
        assert model["correct"] == 0
        assert model["exact"] == 0
```

**Step 3: Run tests to verify they fail**

Run:
```bash
pytest tests/test_score.py -v
```

Expected: FAIL with `KeyError: 'accuracy'` or assertion error.

**Step 4: Commit the failing tests**

```bash
git add tests/test_score.py
git commit -m "test: assert accuracy/correct/exact fields in leaderboard"
```

---

## Task 2: Add accuracy, correct, and exact fields in scorer

**Files:**
- Modify: `src/score.py:200-212` (`score_model`)
- Modify: `src/score.py:260-274` (`generate_leaderboard` model dict)

**Step 1: Derive accuracy and aliases in `score_model`**

Replace the `score_model` function with:

```python
def score_model(prediction: dict, results: dict) -> dict:
    """Score a single model's predictions against actual results."""
    model_name = prediction.get("model", "Unknown")
    metrics = evaluate_prediction(prediction, results)

    total_evaluated = metrics["total_evaluated"]
    correct_outcomes = metrics["correct_outcomes"]
    exact_scores = metrics["exact_scores"]
    accuracy = (correct_outcomes / total_evaluated * 100) if total_evaluated > 0 else None

    return {
        "model_name": model_name,
        "model_id": prediction.get("model_id", ""),
        **metrics,
        "accuracy": round(accuracy, 2) if accuracy is not None else None,
        "correct": correct_outcomes,
        "exact": exact_scores,
        "champion": prediction.get("champion"),
        "runner_up": prediction.get("runner_up"),
        "third_place": prediction.get("third"),
    }
```

**Step 2: Include new fields in leaderboard output**

In `generate_leaderboard`, update the model dict inside the list comprehension to include the new fields:

```python
{
    "rank": m["rank"],
    "model_name": m["model_name"],
    "model_id": m["model_id"],
    "total_evaluated": m["total_evaluated"],
    "correct_outcomes": m["correct_outcomes"],
    "exact_scores": m["exact_scores"],
    "accuracy": m["accuracy"],
    "correct": m["correct"],
    "exact": m["exact"],
    "brier_avg": m["brier_avg"],
    "brier_total": m["brier_total"],
    "bracket_points": m["bracket_points"],
    "champion": m["champion"],
    "runner_up": m["runner_up"],
    "third_place": m["third_place"],
}
```

**Step 3: Run tests**

Run:
```bash
pytest tests/test_score.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add src/score.py
git commit -m "feat(scoring): add accuracy, correct, and exact fields"
```

---

## Task 3: Update dashboard to read model.accuracy safely

**Files:**
- Modify: `docs/app.js:64-67` (`accuracy` helper)
- Modify: `docs/app.js:99-120` (`renderStats`)
- Modify: `docs/app.js:147-173` (`renderLeaderboard`)
- Modify: `docs/app.js:176-197` (`renderPodiumCard`)

**Step 1: Update `accuracy` helper to read from JSON**

Replace:
```javascript
function accuracy(m) {
  if (!m || m.total_evaluated <= 0) return '0.0';
  return (m.correct_outcomes / m.total_evaluated * 100).toFixed(1);
}
```

With:
```javascript
function accuracy(m) {
  if (!m) return null;
  if (m.accuracy === null || m.accuracy === undefined) return null;
  return Number(m.accuracy).toFixed(1);
}
```

**Step 2: Update `renderStats` to handle null average accuracy**

Replace the `avgAcc` calculation and summary card:

```javascript
const accuracies = leaderboard?.models?.length
  ? leaderboard.models.map(m => accuracy(m)).filter(a => a !== null).map(Number)
  : [];
const avgAcc = accuracies.length
  ? (accuracies.reduce((s, v) => s + v, 0) / accuracies.length).toFixed(1)
  : null;

el.innerHTML = [
  { label: 'AI Models', value: models, icon: '🤖', color: 'blue' },
  { label: 'Results In', value: `${results}/${totalMatches}`, icon: '⚽', color: 'green' },
  { label: 'Avg Accuracy', value: results > 0 && avgAcc !== null ? `${avgAcc}%` : '—', icon: '🎯', color: 'gold' },
  { label: 'Tournament', value: results === 0 ? 'Pre-Kickoff' : 'Live', icon: '📅', color: 'purple' },
].map(s => `...`)
```

Keep the existing card HTML structure unchanged.

**Step 3: Update `renderLeaderboard` accuracy column**

Replace:
```javascript
<td class="px-4 py-3 text-center">
  <span class="font-bold" style="color:${color}">${accuracy(m)}%</span>
</td>
```

With:
```javascript
<td class="px-4 py-3 text-center">
  <span class="font-bold" style="color:${color}">${accuracy(m) !== null ? accuracy(m) + '%' : '—'}</span>
</td>
```

**Step 4: Update `renderPodiumCard` accuracy display**

Replace:
```javascript
<div class="mt-3 text-3xl font-black" style="color:${color}">${accuracy(model)}%</div>
```

With:
```javascript
<div class="mt-3 text-3xl font-black" style="color:${color}">${accuracy(model) !== null ? accuracy(model) + '%' : '—'}</div>
```

**Step 5: Verify dashboard loads without undefined%**

Open `docs/index.html` in a browser (or run a local server) and confirm the leaderboard shows `100.0%` for accuracy instead of `undefined%`.

**Step 6: Commit**

```bash
git add docs/app.js
git commit -m "fix(dashboard): read model.accuracy from JSON with null handling"
```

---

## Task 4: Regenerate leaderboard.json

**Files:**
- Modify: `docs/data/leaderboard.json`

**Step 1: Run the scorer against current results**

Run:
```bash
python src/score.py --output docs/data/leaderboard.json
```

Expected output: `Leaderboard written to docs/data/leaderboard.json` and the file should now contain `accuracy`, `correct`, and `exact` fields for every model.

**Step 2: Inspect the generated JSON**

Run:
```bash
python -c "import json; d=json.load(open('docs/data/leaderboard.json')); print(d['models'][0])"
```

Expected: the printed model dict includes `accuracy`, `correct`, and `exact` keys.

**Step 3: Commit**

```bash
git add docs/data/leaderboard.json
git commit -m "data: regenerate leaderboard with accuracy/correct/exact fields"
```

---

## Task 5: Final verification

**Files:**
- All modified files

**Step 1: Run full test suite**

Run:
```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 2: Sanity-check dashboard in browser**

Open `docs/index.html` and confirm:
- Podium cards show `100.0%` accuracy (or the correct value) instead of `undefined%`.
- Full ranking table shows the accuracy column correctly.
- "Avg Accuracy" stat is `100.0%` (or the correct average), not `0.0%`.

**Step 3: Commit any final fixes**

If no changes are needed, this step is a no-op.

---

## Deployment note

After merging, the `docs/` folder is served via GitHub Pages. Re-deploy happens automatically on push to the default branch; no separate deploy step is required unless the project uses a different hosting mechanism.
