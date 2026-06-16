# Model Disagreement View — Design

Date: 2026-06-16  
Status: Approved

## Goal

Add a backend endpoint and a dashboard view that, for every tournament match, compares the 1X2 probability distributions predicted by each available model and surfaces the matches where models disagree the most.

## Decisions made

- **Stack choice**: Hybrid approach. Add a FastAPI backend with `GET /api/disagreement`, and add a new vanilla-JS tab to the existing static dashboard (`docs/app.js`). This satisfies the endpoint requirement with minimal disruption to the current frontend.
- **Disagreement metric**: Mean per-outcome variance.
  - Group stage: variance over `home`, `draw`, `away`.
  - Knockout stage: drop `draw`, renormalize `home`/`away` to sum to 1, then variance over those two outcomes.
- **Data source**: `predictions/pre-tournament/*.json` for model predictions, `data/tournament.json` for match metadata.
- **Filters**: optional `phase` (`group` | `knockout`) and optional `models` comma-separated list.

## Files added / changed

### New files

- `src/api/__init__.py`
- `src/api/main.py` — FastAPI application and `/api/disagreement` endpoint.
- `src/api/disagreement.py` — pure logic for loading predictions, pairing them with matches, computing disagreement scores, and filtering.
- `tests/test_disagreement.py` — unit tests for calculation logic and endpoint behavior.

### Changed files

- `requirements.txt` — add `fastapi>=0.110.0` and `uvicorn[standard]>=0.29.0`.
- `docs/index.html` — add a "Disagreement" tab button and container.
- `docs/app.js` — implement the new tab: fetch data, render sorted matches, highlight top disagreements, show per-model probability bars.

## Backend API

### `GET /api/disagreement`

Optional query parameters:

- `phase=group|knockout`
- `models=GPT-5.5,Grok-4.3` (case-insensitive)

Success response (`200`):

```json
{
  "matches": [
    {
      "match_id": 2,
      "phase": "group",
      "group": "A",
      "round": null,
      "home_team": "KOR",
      "away_team": "CZE",
      "date": "2026-06-11",
      "disagreement_score": 0.0084,
      "model_predictions": [
        { "model": "GPT-5.5", "home": 0.35, "draw": 0.31, "away": 0.34 },
        { "model": "Grok-4.3", "home": 0.28, "draw": 0.30, "away": 0.42 }
      ]
    }
  ],
  "meta": {
    "total_matches": 104,
    "models_used": ["GPT-5.5", "Grok-4.3"],
    "phase_filter": null,
    "models_filter": null
  }
}
```

Error responses:

- `400` — invalid `phase` or unknown model name.
- `500` — missing `data/tournament.json` or no prediction files found.

## Calculation details

For a given match with `n` models:

### Group stage

```
p_home  = [m.probs.home  for m in models]
p_draw  = [m.probs.draw  for m in models]
p_away  = [m.probs.away  for m in models]
score = mean(variance(p_home), variance(p_draw), variance(p_away))
```

### Knockout stage

```
p_home_raw = [m.probs.home for m in models]
p_away_raw = [m.probs.away for m in models]
# renormalize to ignore draw
p_home = [p / (p + a) for p, a in zip(p_home_raw, p_away_raw)]
p_away = [1 - p for p in p_home]
score = mean(variance(p_home), variance(p_away))
```

Matches are returned sorted by `disagreement_score` descending.

## Frontend behavior

A new "Disagreement" tab sits alongside Leaderboard, Consensus, Matches, and Bracket.

On load it fetches `/api/disagreement` and renders:

1. A phase filter (All / Group / Knockout) that changes the query param and re-fetches.
2. A list/table sorted by `disagreement_score` descending.
3. The top 10 matches highlighted with a warm/alert color.
4. Per-model probability bars for each match, using `MODEL_COLORS` already defined in `app.js`.

## Testing

- Variance calculation with synthetic probabilities.
- Knockout renormalization (e.g. a draw probability is ignored).
- Phase filter behavior.
- Model filter behavior.
- Error handling when prediction files or tournament data are missing.

## Open questions / future work

- The static dashboard currently loads JSON files directly; the FastAPI endpoint requires a running server. A future iteration could pre-generate a static `docs/data/disagreement.json` during the daily scoring workflow so the view works without a backend.
- If the project later migrates to React/TypeScript, the same endpoint and calculation module can be reused; only the frontend component changes.
