# Dashboard Accuracy Field Fix

## Problem

The dashboard displays `undefined%` for model accuracy in both the podium cards and the full ranking table. The root cause is a mismatch between the dashboard and the leaderboard JSON: the dashboard expects an explicit `accuracy` field on each model, while `src/score.py` only writes `correct_outcomes` and `exact_scores`.

## Goal

Add `accuracy`, `correct`, and `exact` fields to each model object in `leaderboard.json`, update the dashboard to read `model.accuracy` with safe null handling, and regenerate the published leaderboard.

## Design

### Backend changes (`src/score.py`)

In `score_model`, derive and include:

- `accuracy`: `correct_outcomes / total_evaluated * 100` as a float (e.g., `100.0` for 1/1). If `total_evaluated == 0`, set to `null`.
- `correct`: alias for `correct_outcomes`.
- `exact`: alias for `exact_scores`.

In `generate_leaderboard`, ensure these three fields are written into the `models` array of the output JSON, alongside the existing fields.

### Frontend changes (`docs/app.js`)

Change the `accuracy(m)` helper to read `m.accuracy` from the loaded leaderboard. If the value is `null` or `undefined`, return a sentinel (e.g., `null`) so callers can render `—`. Update all rendering sites that show accuracy:

- Podium cards (`renderPodiumCard`)
- Full ranking table (`renderLeaderboard`)
- Average accuracy stat (`renderStats`)

### Data regeneration

Run the scorer against the current results to produce an updated `docs/data/leaderboard.json` containing the new fields.

### Validation

- Run existing tests (`tests/test_score.py`) to confirm no regressions.
- Optionally add a new test asserting that `accuracy`, `correct`, and `exact` are present and computed correctly.

## Trade-offs

- **Approach A (chosen): source of truth in JSON.** Keeps dashboard logic simple, makes the API contract explicit, and avoids duplicating the accuracy formula. The downside is a slightly larger JSON file.
- **Approach B (rejected): compute in frontend only.** Smaller JSON but leaves the contract implicit and does not fix the backend/frontend mismatch described in the bug report.
- **Approach C (rejected): both.** Adds redundancy without a clear benefit.

## Success criteria

1. `docs/data/leaderboard.json` contains `accuracy`, `correct`, and `exact` for every model.
2. The dashboard renders accuracy as a percentage (or `—` when null) with no `undefined%` values.
3. Existing tests pass.
