# 🔒 WorldCupBench Prediction Freeze

This document serves as the **audit trail** for the prediction freeze.
All predictions below were generated and committed **before the opening match**
of the 2026 FIFA World Cup (June 11, 2026).

---

## Freeze Details

| Field | Value |
|-------|-------|
| **Freeze Date** | 2026-06-10 |
| **Freeze Time (UTC)** | 2026-06-10T18:39:14+00:00 |
| **Git Commit** | 1bdceff |
| **Commit Hash** | `1bdceff39b6e4b1024d161f519636d2d1ac94f8e` |
| **Number of Models** | 11 |
| **Prompt Version** | 2.1 |

---

## Models Frozen

| # | Model | Provider | OpenRouter ID | Knowledge Cutoff | File |
|---|-------|----------|---------------|------------------|------|
| 1 | GPT-5.5 | OpenAI | `openai/gpt-5.5` | 2026-06 | `predictions/pre-tournament/GPT-5.5_prediction.json` |
| 2 | Claude Opus 4.8 | Anthropic | `anthropic/claude-opus-4.8` | 2026-06 | `predictions/pre-tournament/Claude-Opus-4.8_prediction.json` |
| 3 | Gemini 3.1 Ultra | Google | `google/gemini-3.1-ultra` | 2026-06 | `predictions/pre-tournament/Gemini-3.1-Ultra_prediction.json` |
| 4 | Grok 3 | xAI | `x-ai/grok-3` | 2026-06 | `predictions/pre-tournament/Grok-3_prediction.json` |
| 5 | DeepSeek V4-Pro | DeepSeek | `deepseek/deepseek-v4-pro` | 2026-04 | `predictions/pre-tournament/DeepSeek-V4-Pro_prediction.json` |
| 6 | Qwen 3.7 Max | Alibaba | `qwen/qwen-3.7-max` | 2026-06 | `predictions/pre-tournament/Qwen-3.7-Max_prediction.json` |
| 7 | Kimi K2.6 | Moonshot AI | `moonshotai/kimi-k2.6` | 2026-06 | `predictions/pre-tournament/Kimi-K2.6_prediction.json` |
| 8 | GLM-5 | Zhipu AI | `zhipuai/glm-5` | 2026-06 | `predictions/pre-tournament/GLM-5_prediction.json` |
| 9 | MiniMax M3 | MiniMax | `minimax/minimax-m3` | 2026-06 | `predictions/pre-tournament/MiniMax-M3_prediction.json` |
| 10 | MiMo V2.5-Pro | Xiaomi | `xiaomi/mimo-v2.5-pro` | 2026-06 | `predictions/pre-tournament/MiMo-V2.5-Pro_prediction.json` |
| 11 | Nex-N2-Pro | Nex AGI | `nex-agi/nex-n2-pro:free` | 2026-06 | `predictions/pre-tournament/Nex-N2-Pro_prediction.json` |

**Status:** Only DeepSeek-V4-Pro has been regenerated with prompt v2.1 so far. Remaining 10 models pending.

---

## File Checksums (SHA-256)

| Model | File | SHA-256 |
|-------|------|---------|
| DeepSeek-V4-Pro | `predictions/pre-tournament/DeepSeek-V4-Pro_prediction.json` | `ec00d719dd54552fe8fb665d0f77b538f7bdc582929ba57e8fafc8759224b084` |

---

## Verification

To verify the freeze yourself:

```bash
# Check the commit timestamp
git log -1 --format="%H %ai"

# Verify checksums
sha256sum predictions/pre-tournament/*_prediction.json

# Validate all predictions against schema
python -c "
import json, os, sys
sys.path.insert(0, 'src')
import utils
schema = utils.load_schema()
tournament_data = utils.load_tournament_data()
pre_tournament_dir = 'predictions/pre-tournament'
for f in sorted(os.listdir(pre_tournament_dir)):
    if f.endswith('_prediction.json'):
        path = os.path.join(pre_tournament_dir, f)
        with open(path) as fp:
            data = json.load(fp)
        ok, msg = utils.validate_predictions(data, schema, tournament_data)
        print(f'{f}: {msg}')
"
```

---

## Invalidated Freezes

The following predictions were generated on 2026-06-10 but are **invalidated** because they were produced with incorrect tournament data (5 wrong playoff teams) and prompt v2.0. They have been moved to `predictions/invalidated/freeze-v1/` for archival purposes.

| File | SHA-256 | Original Timestamp | Reason |
|------|---------|-------------------|--------|
| `GPT-5.5_predictions.json` | `c2299e827b15c8d65ae9214a773ff4e7d7ff7494668ac646d38652e1250a446c` | 2026-06-10T07:32:35+00:00 | Generated with incorrect tournament data, prompt v2.0 |
| `Claude-Opus-4.8_predictions.json` | `2ef8e2624c095bde63967a9156cec4724bd0807bd8dd2d325bb1b0d1898b3783` | 2026-06-10T07:34:11+00:00 | Generated with incorrect tournament data, prompt v2.0 |
| `DeepSeek-V4-Pro_predictions.json` | `aab8b156ff378a106c6323ed48d422fa169ff6abe01afd54b1cbbdf839526312` | 2026-01-20T12:00:00Z | Generated with incorrect tournament data, prompt v2.0. **Note:** timestamp `2026-01-20` is a placeholder value present in the file, predating this repository. |

---

## No-Edit Policy

> **No prediction file in this repository shall be modified after the freeze.**
> Any correction, re-run, or update must be stored in a separate file with a
> new timestamp and documented in this file.
>
> **Exception:** Predictions may be invalidated (moved to `predictions/invalidated/`) and
> regenerated when the underlying tournament data or prompt is materially corrected.
> Each invalidation must be fully documented above with SHA-256, timestamp, and reason.
