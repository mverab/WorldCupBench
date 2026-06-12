# Recover Bracket from Git History

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline; no subagents needed.

**Goal:** Restore the complete knockout bracket and final standings for all 11 models by merging data from commit `64f3703` into the current freeze-v3 prediction files, without regenerating predictions.

**Architecture:** A small merge script reads the old prediction JSONs from `git show 64f3703:...`, copies `group_qualifiers`, converts `knockout_stage` into the `bracket` shape expected by `src/score.py`, and promotes `final_standings` to top-level `champion`/`runner_up`/`third`. Current `group_matches` and model metadata are left untouched. After merging, regenerate `docs/data/predictions_summary.json`, rerun `src/score.py`, and fix the dashboard JS to compute accuracy locally.

**Tech Stack:** Python 3, Git CLI, vanilla JS.

---

### Task 1: Inspect key mappings

**Files:**
- Read: `src/score.py:174-185` (bracket scoring keys)
- Read: `scripts/generate_predictions_summary.py` (summary keys)
- Read: one old prediction: `git show 64f3703:predictions/pre-tournament/Grok-4.3_prediction.json`

- [ ] **Step 1.1: Confirm score.py expects `bracket` with keys `R32`, `R16`, `QF`, `SF`, `final`, and top-level `champion`, `runner_up`, `third`.**
- [ ] **Step 1.2: Confirm old prediction keys are `knockout_stage` (`round_of_32`, `round_of_16`, `quarter_finals`, `semi_finals`, `third_place_match`, `final`) and `final_standings`.**

Run: `python -c "import json; d=json.load(open('predictions/pre-tournament/Grok-4.3_prediction.json')); print(d.keys())"`
Expected: current file has `group_matches`, no `bracket`, `champion` null.

---

### Task 2: Write `scripts/recover_bracket.py`

**Files:**
- Create: `scripts/recover_bracket.py`

- [ ] **Step 2.1: Create the merge script**

Logic:
- List current files in `predictions/pre-tournament/*_prediction.json`.
- For each file, read the corresponding old JSON from `git show 64f3703:predictions/pre-tournament/<basename>`.
- Keep current `group_matches` exactly as-is.
- Add `group_qualifiers` from old.
- Convert `knockout_stage` → `bracket`:
  - `round_of_32` → `R32`
  - `round_of_16` → `R16`
  - `quarter_finals` → `QF`
  - `semi_finals` → `SF`
  - `final` → `final` (dict)
  - `third_place_match` → `third_place` (dict)
- For each knockout match, derive `winner` from `predicted_result`/`probs`, and set `match` to the canonical numeric match id parsed from the old `match_id` (e.g. `"R32-73"` → `"73"`).
- Promote `final_standings` to top-level `champion`, `runner_up`, `third` (and keep `fourth_place`).
- Write the merged JSON back with `indent=2, ensure_ascii=False`.

Run: `python scripts/recover_bracket.py --dry-run`
Expected: prints 11 models and key counts, no file written.

- [ ] **Step 2.2: Run the script for real**

Run: `python scripts/recover_bracket.py`
Expected: writes 11 merged files.

- [ ] **Step 2.3: Verify merged files**

Run: `python -c "
import json, glob
for f in sorted(glob.glob('predictions/pre-tournament/*_prediction.json')):
    d=json.load(open(f))
    b=d.get('bracket',{})
    ko=len(b.get('R32',[]))+len(b.get('R16',[]))+len(b.get('QF',[]))+len(b.get('SF',[]))
    tp=1 if b.get('third_place') else 0
    fin=1 if b.get('final') else 0
    print(d.get('model'), d.get('champion'), ko+tp+fin)
"`
Expected: 11 lines, all `champion` non-null, total knockout matches = 32.

- [ ] **Step 2.4: Commit the merge script**

```bash
git add scripts/recover_bracket.py
git commit -m "feat(scripts): add recover_bracket.py to restore knockout data from 64f3703"
```

---

### Task 3: Fix `scripts/generate_predictions_summary.py`

**Files:**
- Modify: `scripts/generate_predictions_summary.py`

Current summary has `model_name: null` because current prediction files use `model`, not `model_name`, and it reads `final_standings` which no longer exists after normalization.

- [ ] **Step 3.1: Update key reads**
  - `model_name`: `d.get("model") or d.get("model_name")`
  - `champion`, `runner_up`, `third_place`, `fourth_place`: read from top-level keys.

- [ ] **Step 3.2: Run the generator**

Run: `python scripts/generate_predictions_summary.py`
Expected: `Wrote 11 prediction summaries` and `docs/data/predictions_summary.json` now has real `model_name` and champion values.

- [ ] **Step 3.3: Commit**

```bash
git add scripts/generate_predictions_summary.py docs/data/predictions_summary.json
git commit -m "fix(scripts): update summary generator for freeze-v3 top-level keys"
```

---

### Task 4: Regenerate leaderboard

**Files:**
- Modify: `data/leaderboard.json` (generated)

- [ ] **Step 4.1: Run scorer**

Run: `python src/score.py`
Expected: prints 11 models with non-null `champion`, `runner_up`, `third_place`.

- [ ] **Step 4.2: Verify leaderboard**

Run: `python -c "import json; lb=json.load(open('data/leaderboard.json')); print(lb['total_models']); print([(m['model_name'], m['champion'], m['runner_up'], m['third_place']) for m in lb['models']])"`
Expected: 11 models, no `null` champion/runner_up/third_place.

- [ ] **Step 4.3: Commit**

```bash
git add data/leaderboard.json predictions/pre-tournament/*_prediction.json
git commit -m "data: recover knockout brackets and final standings from 64f3703"
```

---

### Task 5: Fix dashboard accuracy

**Files:**
- Modify: `docs/app.js:99-101`, `:158`, `:182`

`leaderboard.json` has no `accuracy` field. Compute it as `correct_outcomes / total_evaluated * 100` and guard against division by zero.

- [ ] **Step 5.1: Add a helper `accuracy(model)`**

```js
function accuracy(m) {
  return m.total_evaluated > 0 ? (m.correct_outcomes / m.total_evaluated * 100).toFixed(1) : '0.0';
}
```

- [ ] **Step 5.2: Replace all `m.accuracy` references with `accuracy(m)`**
  - `renderStats` avg accuracy: use `accuracy(m)`.
  - `renderLeaderboard` table cell.
  - `renderPodiumCard` big number.

- [ ] **Step 5.3: Verify no undefined accuracy**

Run: `grep -n "accuracy" docs/app.js` and confirm every usage is either the helper definition or a call.

- [ ] **Step 5.4: Commit**

```bash
git add docs/app.js
git commit -m "fix(docs): compute accuracy in JS from correct_outcomes/total_evaluated"
```

---

### Task 6: Final validation and push

- [ ] **Step 6.1: Run smoke checks**

```bash
python scripts/validate_predictions.py predictions/pre-tournament
python src/score.py
python -m http.server 8080 --directory docs &  # optional manual browser check
```

- [ ] **Step 6.2: Confirm git diff summary**

Run: `git diff --stat origin/main`
Expected: modified predictions (size increase), new `scripts/recover_bracket.py`, updated `scripts/generate_predictions_summary.py`, `docs/app.js`, generated JSONs.

- [ ] **Step 6.3: Push to main**

```bash
git push origin mverab/la-paz-v1:main
```

Expected: remote main updated; dashboard tabs Leaderboard/Consensus/Bracket show real data.
