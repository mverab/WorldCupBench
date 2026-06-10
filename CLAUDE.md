# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WorldCupBench** is a Python benchmark that compares predictions from multiple SOTA AI models for the FIFA World Cup 2026. Each model receives the same prompt and must return structured JSON predictions covering all 104 tournament matches, group qualifiers, knockout brackets, and final standings. Results are validated against a JSON Schema and saved per model for later comparison.

## Common Commands

**Setup:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OpenRouter API key
```

**Run predictions:**
```bash
# All configured models
python src/run_predictions.py

# Specific models only (names are case-insensitive)
python src/run_predictions.py --models GPT-5.5 Grok-3

# Validate setup without calling APIs
python src/run_predictions.py --dry-run
```

**Environment:**
- `OPENROUTER_API_KEY` is required (read from `.env` via `python-dotenv` or from the environment).
- There is no test suite, build step, or linting configuration.

## Architecture

### Three-Module Structure

| File | Responsibility |
|------|---------------|
| `src/models_config.py` | Defines the list of SOTA models (`MODELS`) with their human-readable `name`, OpenRouter `model_id`, and `provider`. `get_model_by_name()` performs case-insensitive lookups. |
| `src/utils.py` | I/O and validation utilities: `load_prompt()`, `load_schema()`, `extract_json()`, `validate_predictions()`, `save_predictions()`. Also defines `BASE_DIR` and output paths relative to the repo root. |
| `src/run_predictions.py` | Entry point. Parses CLI args, iterates over selected models, calls OpenRouter via `requests` with retry logic, parses the JSON response, validates against the schema, and writes `predictions/{model_name}_predictions.json`. |

### Data Flow

1. **Prompt** (`prompts/prediction_prompt.txt`) is loaded once. It contains the full tournament context and a `<model_name>` placeholder that `build_messages()` substitutes per model.
2. **API call** (`call_openrouter`) sends the prompt to OpenRouter with `response_format: {"type": "json_object"}`, `temperature: 0.3`, and a 3-retry backoff for HTTP 429/5xx or network errors.
3. **JSON extraction** (`utils.extract_json`) handles raw responses that may be wrapped in markdown code fences or have surrounding text — it tries direct parse, then regex for fences, then brute-force substring from first `{` to last `}`.
4. **Validation** (`utils.validate_predictions`) uses `jsonschema.Draft7Validator` if available; falls back to a minimal top-level key check otherwise.
5. **Output** is saved to `predictions/{safe_name}_predictions.json` with `ensure_ascii=False` and `indent=2`. Failed parses are saved as `predictions/{name}_raw_error.txt` for debugging.

### Key Design Decisions

- **OpenRouter as unified gateway:** All models are accessed through a single OpenRouter API call. Model IDs follow the OpenRouter convention (`provider/model-name`). Verify available IDs at https://openrouter.ai/models before adding new models.
- **Schema as contract:** `schema/predictions_schema.json` (draft-07) is the source of truth. Any change to the prediction structure must update the schema, the prompt example output, and `utils.validate_predictions` (which hardcodes the same top-level required keys as a fallback).
- **Resilient parsing:** Models sometimes wrap JSON in markdown or add commentary. `extract_json` is intentionally permissive to maximize success rate across diverse model behaviors.
- **No persistent state:** The script is stateless across runs. Each execution overwrites existing prediction files for the selected models.
