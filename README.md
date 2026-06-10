# WorldCupBench ⚽🏆

**WorldCupBench** is a benchmark for comparing predictions from different state-of-the-art (SOTA) AI models for the **FIFA World Cup 2026™** (Canada, Mexico, and USA).

Each model receives the **same standard prompt** with tournament information and must predict, in JSON format:

- All matches in the **group stage** (72 matches, 12 groups A–L).
- The **qualifiers** from each group (1st, 2nd, and the 8 best third-place teams).
- The winners of each round of the **knockout stage** (Round of 32 → Round of 16 → Quarter Finals → Semi-Finals → Third Place + Final).
- The **final positions**: Champion (1st), Runner-up (2nd), Third Place (3rd), and Fourth Place (4th).

The goal is, once the tournament is over, to measure which model predicted the results best.

> The 2026 World Cup begins on **June 11, 2026** (opening match: Mexico vs. South Africa) and the final will be played on **July 19, 2026**.

---

## 📁 Project Structure

```
.
├── README.md                  # This file
├── .env.example               # Template for OPENROUTER_API_KEY
├── .gitignore
├── requirements.txt
├── schema/
│   └── predictions_schema.json   # JSON schema for predictions
├── prompts/
│   └── prediction_prompt.txt     # Standard prompt for ALL models
├── src/
│   ├── run_predictions.py        # Main script (OpenRouter)
│   ├── models_config.py          # List of models and their OpenRouter IDs
│   └── utils.py                  # Utilities (loading, parsing, validation, saving)
├── predictions/                  # Model prediction JSONs are saved here
├── data/
│   └── world_cup_2026_info.md    # Tournament info (prompt source)
└── dashboard/                    # Placeholder for visualization (future)
```

---

## 🤖 Compared Models (SOTA, June 2026)

| Model | Provider |
| --- | --- |
| GPT-5.5 | OpenAI |
| Claude Opus 4.8 | Anthropic |
| Gemini 3.1 Ultra | Google |
| Grok 3 | xAI |
| DeepSeek V4-Pro | DeepSeek |
| Qwen 3.7 Max | Alibaba |
| Kimi K2.6 | Moonshot AI |
| GLM-5 | Zhipu AI |
| MiniMax M3 | MiniMax |
| MiMo V2.5-Pro | Xiaomi |

Exact OpenRouter identifiers are defined in [`src/models_config.py`](src/models_config.py). Verify/adjust the `model_id` values at [openrouter.ai/models](https://openrouter.ai/models) according to availability.

---

## ⚙️ Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mverab/WorldCupBench.git
   cd WorldCupBench
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure your OpenRouter key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your key, or export the variable:
   export OPENROUTER_API_KEY="your_key"
   ```
   Get your key at [openrouter.ai/keys](https://openrouter.ai/keys).

---

## ▶️ Usage

Run predictions for **all** models:
```bash
python src/run_predictions.py
```

Run only **some** models:
```bash
python src/run_predictions.py --models GPT-5.5 Grok-3
```

**Dry-run** mode without calling the API (validates configuration and prompt):
```bash
python src/run_predictions.py --dry-run
```

Each model's predictions are saved to:
```
predictions/{model_name}_predictions.json
```

---

## 🧩 Prediction Schema

The [`schema/predictions_schema.json`](schema/predictions_schema.json) file defines the expected structure (JSON Schema draft-07). Each match prediction includes: `match_id`, `team_a`, `team_b`, `predicted_winner`, `predicted_score`, `confidence`, plus model metadata (`model_name`, `timestamp`). The script automatically validates responses against this schema.

---

## 🛣️ Roadmap

- [x] Initial project structure (MVP).
- [x] Standard prompt and prediction schema.
- [x] Execution script via OpenRouter with retries.
- [ ] Collection of actual tournament results.
- [ ] Accuracy metric calculation (accuracy, Brier score).
- [ ] Model comparison dashboard.

---

## 📄 License

Project for educational and research purposes. Tournament data comes from official FIFA sources (see `data/world_cup_2026_info.md`).
