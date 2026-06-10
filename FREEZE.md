# 🔒 WorldCupBench Prediction Freeze

This document serves as the **audit trail** for the prediction freeze.
All predictions below were generated and committed **before the opening match**
of the 2026 FIFA World Cup (June 11, 2026).

---

## Freeze Details

| Field | Value |
|-------|-------|
| **Freeze Date** | 2026-06-10 |
| **Freeze Time (UTC)** | <!-- FREEZE_TIMESTAMP --> |
| **Git Commit** | <!-- FREEZE_COMMIT --> |
| **Commit Hash** | <!-- FREEZE_HASH --> |
| **Number of Models** | 10 |

---

## Models Frozen

| # | Model | Provider | OpenRouter ID | File |
|---|-------|----------|---------------|------|
| 1 | GPT-5.5 | OpenAI | `openai/gpt-5.5` | `predictions/GPT-5.5_predictions.json` |
| 2 | Claude Opus 4.8 | Anthropic | `anthropic/claude-opus-4.8` | `predictions/Claude-Opus-4.8_predictions.json` |
| 3 | Gemini 3.1 Ultra | Google | `google/gemini-3.1-ultra` | `predictions/Gemini-3.1-Ultra_predictions.json` |
| 4 | Grok 3 | xAI | `x-ai/grok-3` | `predictions/Grok-3_predictions.json` |
| 5 | DeepSeek V4-Pro | DeepSeek | `deepseek/deepseek-v4-pro` | `predictions/DeepSeek-V4-Pro_predictions.json` |
| 6 | Qwen 3.7 Max | Alibaba | `qwen/qwen-3.7-max` | `predictions/Qwen-3.7-Max_predictions.json` |
| 7 | Kimi K2.6 | Moonshot AI | `moonshotai/kimi-k2.6` | `predictions/Kimi-K2.6_predictions.json` |
| 8 | GLM-5 | Zhipu AI | `zhipuai/glm-5` | `predictions/GLM-5_predictions.json` |
| 9 | MiniMax M3 | MiniMax | `minimax/minimax-m3` | `predictions/MiniMax-M3_predictions.json` |
| 10 | MiMo V2.5-Pro | Xiaomi | `xiaomi/mimo-v2.5-pro` | `predictions/MiMo-V2.5-Pro_predictions.json` |

---

## File Checksums (SHA-256)

<!-- CHECKSUMS:START -->
_Generated automatically during freeze._
<!-- CHECKSUMS:END -->

---

## Verification

To verify the freeze yourself:

```bash
# Check the commit timestamp
git log -1 --format="%H %ai"

# Verify checksums
sha256sum predictions/*_predictions.json

# Validate all predictions against schema
python -c "
import json, os, sys
sys.path.insert(0, 'src')
import utils
schema = utils.load_schema()
for f in os.listdir('predictions'):
    if f.endswith('_predictions.json'):
        with open(f'predictions/{f}') as fp:
            data = json.load(fp)
        ok, msg = utils.validate_predictions(data, schema)
        print(f'{f}: {msg}')
"
```

---

## No-Edit Policy

> **No prediction file in this repository shall be modified after the freeze.**
> Any correction, re-run, or update must be stored in a separate file with a
> new timestamp and documented in this file.
