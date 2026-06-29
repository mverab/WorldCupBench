<p align="center">
  <img src="assets/banner.png" alt="WorldCupBench — 10 Frontier LLMs predicted the entire 2026 FIFA World Cup" width="100%">
</p>

<h1 align="center">WorldCupBench ⚽🤖</h1>

<p align="center">
  <strong>The World Cup is the ultimate LLM eval.</strong><br>
  10 frontier AI models predicted every match of the 2026 FIFA World Cup — frozen pre-tournament, scored live.
</p>

<p align="center">
  <a href="https://github.com/mverab/WorldCupBench/stargazers"><img src="https://img.shields.io/github/stars/mverab/WorldCupBench?style=social" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/🔒%20Predictions%20Frozen-June%2010%2C%202026-red" alt="Frozen">
  <img src="https://img.shields.io/github/last-commit/mverab/WorldCupBench" alt="Last Commit">
</p>

<p align="center">
  <a href="README.es.md">🇪🇸 Versión en Español</a>
</p>

---

## 🏆 Live Leaderboard

<!-- LEADERBOARD:START -->

_No predictions available yet._

<!-- LEADERBOARD:END -->

---

## ⚡ How It Works (in 4 lines)

1. **Same prompt** → 10 SOTA LLMs via OpenRouter.
2. **JSON predictions** → every match, every round, every score, with 1X2 probabilities.
3. **Frozen before kickoff** → no post-hoc editing. Credibility is everything.
4. **Scored live** → as real results come in, we compute accuracy, Brier score, and ROI vs Polymarket.

---

## 🔮 Featured Predictions

> What do 10 frontier models agree on? What do they disagree on?

<!-- FEATURED:START -->

*Featured predictions will appear here once all models have submitted. Check back soon!*

<!-- FEATURED:END -->

---

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/mverab/WorldCupBench.git
cd WorldCupBench
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Set your OpenRouter API key
cp .env.example .env
# Edit .env and add your key

# Run predictions for all models
python src/run_predictions.py

# Or run specific models only
python src/run_predictions.py --models GPT-5.5 Grok-3

# Validate setup without calling APIs
python src/run_predictions.py --dry-run

# Generate leaderboard from collected predictions
python src/generate_leaderboard.py --inject-readme

# Run the API server (for the dashboard disagreement view)
uvicorn src.api.main:app --reload --port 8000
```

The disagreement endpoint is available at `http://localhost:8000/api/disagreement`.

---

## 🤖 Compared Models (SOTA, June 2026)

| Model | Provider | OpenRouter ID |
|-------|----------|---------------|
| GPT-5.5 | OpenAI | `openai/gpt-5.5` |
| Claude Fable 5 | Anthropic | `anthropic/claude-fable-5` |
| Gemini 3.5 Flash | Google | `google/gemini-3.5-flash` |
| Grok 4.3 | xAI | `x-ai/grok-4.3` |
| DeepSeek V4-Pro | DeepSeek | `deepseek/deepseek-v4-pro` |
| Qwen 3.7 Max | Alibaba | `qwen/qwen-3.7-max` |
| Kimi K2.6 | Moonshot AI | `moonshotai/kimi-k2.6` |
| GLM-5.1 | Zhipu AI | `z-ai/glm-5.1` |
| MiniMax M3 | MiniMax | `minimax/minimax-m3` |
| MiMo V2.5-Pro | Xiaomi | `xiaomi/mimo-v2.5-pro` |
| Nex-N2-Pro | Nex AGI | `nex-agi/nex-n2-pro:free` |

All models receive the **exact same prompt** with tournament data and must return structured JSON covering all 104 matches. See [`prompts/prediction_prompt.txt`](prompts/prediction_prompt.txt).

---

## 📐 Methodology

### Prediction Schema

Each model outputs a JSON object validated against [`schema/predictions_schema.json`](schema/predictions_schema.json) (Draft-07):

- **72 group stage matches** with exact score and 1X2 probabilities (sum = 1.0 ± 0.02)
- **Group qualifiers**: 12× 1st place, 12× 2nd place, 8× best 3rd place
- **Knockout stage**: Round of 32 → Round of 16 → Quarter Finals → Semi Finals → Third Place + Final
- **Final standings**: Champion, Runner-up, Third, Fourth

### Key Rules

- **FIFA codes only**: 3-letter codes (e.g., `ARG`, `FRA`, `BRA`)
- **Knockout = no draws**: `probs.draw` must be `0.0`; if the model predicts a draw in 90 min, it must indicate the winner of extra time/penalties
- **Frozen timestamp**: All predictions were generated and committed before the opening match (June 11, 2026)

---

## 📊 How the ranking is computed

WorldCupBench scores every model on **three independent metrics**. The
leaderboard ordering is driven by the **probabilistic** metrics, not by the
single-outcome pick.

| Metric | What it measures | Input field used |
|---|---|---|
| **Brier score** ↓ | Calibration quality of the 1X2 probabilities | `probs.{home,draw,away}` |
| **Outcome accuracy** ↑ | Did the most likely outcome happen? (`argmax(probs)`) | `probs.{home,draw,away}` |
| **Exact-score points** ↑ | Did the predicted scoreline match exactly? | `predicted_result` + `predicted_score` |

> [!IMPORTANT]
> The leaderboard (Brier + outcome accuracy) is computed **strictly from the
> 1X2 probabilities** (`probs`). The fields `predicted_result` and
> `predicted_score` feed **only** the exact-score metric.
>
> This is why you may see a match where `probs.away` is the highest value but
> `predicted_result` is `"draw"`: in tight matches (e.g. `0.30 / 0.30 / 0.40`)
> a model can rationally pick a draw as its single best guess while still
> assigning the marginally higher probability to one side. **This is a
> legitimate model decision, not a data error.** All 792 frozen predictions
> (11 models × 72 group matches) were audited: **0 inconsistencies** between
> `predicted_result` and `predicted_score`.

### ⚠️ Knockout Brier vs. Qualifier Accuracy

The **knockout Brier** (`brier_knockout`) is scored against the **bracket the
model itself predicted**, slot by slot — *not* against the real bracket. Each
model laid out its own Round-of-32 → Final tree before kickoff, so a model is
graded on whether the team it placed in a given slot actually won that tie. If
the real bracket diverges from a model's predicted bracket (e.g. a different
team reaches that slot), the comparison is made on the **predicted matchup**,
which can reward or penalize a model for a tie that never happened as it
imagined it. Treat `brier_knockout` as a **soft, intra-bracket calibration
signal**, not as a ground-truth measure of knockout performance.

The robust, ground-truth metric for the knockout phase is **`qualifier_accuracy`**
(`scripts/qualifiers.py` + `score.score_qualifiers`). It compares the model's
predicted set of qualified teams against the **real 32 teams** that advanced to
the Round of 32, derived from actual group results using FIFA tie-breaking
rules (points → goal difference → goals for → head-to-head → fair-play / draw
of lots). It reports, per model:

| Field | Meaning |
|---|---|
| `hits` / `score` | Correctly predicted qualifiers (`hits/32`) |
| `with_position_bonus` | Hits where the predicted slot (1st/2nd/3rd) also matched |
| `third_place_hits` | How many of the 8 real best-third teams were predicted |
| `missed` / `false_positives` | Qualified teams not predicted / predicted teams that did not qualify |

Because it is computed against the **actual** qualified set (not a
model-specific bracket), `qualifier_accuracy` is the recommended metric for
comparing knockout-stage foresight across models.

🇪🇸 **Resumen (ES):** el Brier de knockout se calcula sobre el cruce **que
predijo cada modelo** (slot a slot), no sobre el cruce real, así que es solo
una señal blanda de calibración dentro del propio bracket. La métrica robusta
de clasificación es `qualifier_accuracy`: compara los clasificados predichos
contra los **32 equipos reales** que avanzaron (derivados con las reglas de
desempate FIFA), y reporta aciertos sobre 32, bonus de posición, terceros
acertados y falsos positivos.

### 📈 Advancement Accuracy (per-round set membership)

`advancement_accuracy` (`scripts/advancement.py`) extends the same robust,
ground-truth philosophy as `qualifier_accuracy` into the knockout phase. For
every round it answers a single question — **"which teams *reach* this
round?"** — as pure set membership, **independent of the bracket slot** a team
occupies. The set of teams reaching a round is exactly the set of winners of
the previous round:

| Round | Teams that reach it | Total scored |
|---|---|---|
| `R16` | winners of the 16 Round-of-32 ties (match_id 73–88) | /16 |
| `QF` | winners of the 8 Round-of-16 ties (89–96) | /8 |
| `SF` | winners of the 4 quarter-finals (97–100) | /4 |
| `FINAL` | winners of the 2 semi-finals (101–102) | /2 |
| `CHAMPION` | winner of the final (104) | /1 |

A model's *predicted* advancement is read from the `winner` fields of its frozen
bracket (the team it picked to win each R32 tie is a team it expects in the
R16, etc.). Per round it reports `hits` / `total` / `missed` /
`false_positives`, plus an overall `hits`/`total`/`score` that aggregates
**only rounds that are fully decided** (`ready: true`), so a half-played round
never penalizes a model for matches that have not happened yet. Because it
scores set membership rather than the exact slot, it rewards a model that
correctly picked the teams to go deep even if it placed them in the wrong half
of the bracket — complementing the slot-based `brier_knockout`.

🇪🇸 **Resumen (ES):** `advancement_accuracy` mide, ronda por ronda, **qué
equipos llegan** a cada instancia (octavos, cuartos, semis, final, campeón) como
pertenencia de conjunto, sin importar el cruce exacto. Los equipos que alcanzan
una ronda son los ganadores de la ronda anterior; se compara contra los
`winner` del bracket congelado de cada modelo. Reporta aciertos, no predichos y
falsos positivos por ronda, y solo agrega al total las rondas ya completas
(`ready`), de modo que una ronda a medias no penaliza al modelo.

### 🧊 Freeze provenance (`freeze-v3`)

All pre-tournament predictions were frozen **before kickoff** and carry an
audit trail:

- `source_schema: "freeze-v3"` — the schema version the prediction was
  generated under.
- `model_id` — the exact model checkpoint queried (e.g.
  `anthropic/claude-5-fable-20260609`).
- `generated_at` — UTC timestamp of generation.
- `orientation_flipped` — `true` when the match was stored in the opposite
  home/away orientation vs. the official fixture. On these matches `probs`,
  `predicted_result` and `predicted_score` are **all** normalized to the
  official orientation, so the data is internally consistent.

> ⚽ MEX–RSA (match 1) counts toward scoring: the freeze timestamp (2026-06-10)
> precedes the match (2026-06-11). `freeze-v3` does **not** include a bracket /
> champion prediction, so those points are scored as 0 for this modality.

🇪🇸 **Resumen (ES):** el ranking (Brier + acierto de resultado) se calcula
**solo sobre las probabilidades 1X2**. Los campos `predicted_result` y
`predicted_score` alimentan únicamente la métrica de marcador exacto. Por eso
en partidos parejos un modelo puede tener la prob más alta en un lado y aun así
elegir empate como pick puntual: es una decisión válida del modelo, no un error
de datos. Los 792 partidos congelados fueron auditados: 0 inconsistencias.

---

## 📁 Project Structure

```
.
├── README.md                       # This file
├── README.es.md                    # Spanish version
├── FREEZE.md                       # Audit log: commit hash, timestamps, checksums
├── LICENSE
├── .env.example
├── requirements.txt
├── schema/
│   └── predictions_schema.json     # JSON Schema draft-07
├── prompts/
│   └── prediction_prompt.txt       # Standard prompt for ALL models
├── src/
│   ├── run_predictions.py          # Main execution script
│   ├── models_config.py            # Model definitions
│   ├── utils.py                    # Parsing, validation, I/O
│   └── generate_leaderboard.py     # Auto-generate leaderboard
├── predictions/                    # Model prediction JSONs
├── data/
│   └── tournament.json             # Official FIFA draw data
└── assets/
    ├── banner.png                  # README banner
    └── social-preview.png          # GitHub social preview (1280×640)
```

---

## 🏷️ Repository Topics

`llm` `benchmark` `llm-evaluation` `ai` `world-cup` `fifa-world-cup-2026` `predictions` `forecasting` `leaderboard` `sports-analytics` `gpt-5` `claude` `gemini`

---

## 🤝 Contributing

### Add Your Model

Want to add a new model? It's one PR:

1. Add your model to `src/models_config.py`:
   ```python
   {
       "name": "Your-Model-Name",
       "model_id": "provider/model-name",
       "provider": "Your Lab",
   }
   ```
2. Run `python src/run_predictions.py --models Your-Model-Name`
3. Submit a PR with the generated JSON

### Add Real Results

As matches conclude, add actual results to `data/results.json` (format TBD) so we can compute live accuracy.

### Improve Scoring

The scoring system is evolving. Open an issue or PR with your proposed metric.

---

## 📜 License

MIT — see [LICENSE](LICENSE).

> Tournament data sourced from official FIFA sources. This project is for educational and research purposes.

---

<p align="center">
  <sub>Built with ⚽ and 🤖 by <a href="https://github.com/mverab">@mverab</a></sub>
</p>
