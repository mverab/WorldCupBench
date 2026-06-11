"""
WorldCupBench - Main prediction execution script.

Reads the standard prompt and sends it to each SOTA model through the
OpenRouter API, parses and validates the JSON response, and saves each model's
predictions to predictions/pre-tournament/{model_name}_prediction.json.

Usage:
    export OPENROUTER_API_KEY="your_key"
    python src/run_predictions.py                  # run all models
    python src/run_predictions.py --models GPT-5.5 Grok-3   # only some
    python src/run_predictions.py --dry-run        # no API call (test)

Requirements: see requirements.txt
"""

import argparse
import json
import os
import re
import sys
import time

import requests

# Allow running the script from the repo root or from src/.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import validate_predictions  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models_config import MODELS, get_model_by_name  # noqa: E402
import utils  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Execution parameters.
TEMPERATURE = 0.3
TOURNAMENT_PLACEHOLDER = "{{TOURNAMENT_JSON}}"

# Retry parameters.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
REQUEST_TIMEOUT = 180


def _log(msg: str, indent: int = 0) -> None:
    """Print a timestamped log message with optional indentation."""
    ts = time.strftime("%H:%M:%S", time.localtime())
    prefix = "  " * indent
    print(f"[{ts}] {prefix}{msg}")


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds into a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m {secs}s"


def _is_non_retryable(exc: Exception) -> bool:
    """Returns True for permanent failures (HTTP 4xx except 429) that should not be retried."""
    msg = str(exc)
    match = re.search(r"HTTP (\d{3})", msg)
    if match:
        code = int(match.group(1))
        return 400 <= code < 500 and code != 429
    return False


def fetch_model_pricing(api_key: str) -> dict:
    """
    Fetches model pricing from OpenRouter.

    Returns a dict mapping model_id -> {"prompt": price_per_1M, "completion": price_per_1M}.
    Prices are in USD per 1,000,000 tokens.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/mverab/WorldCupBench",
        "X-Title": "WorldCupBench",
    }
    _log("Fetching model pricing from OpenRouter...")
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        pricing = {}
        for model in resp.json().get("data", []):
            model_id = model.get("id", "")
            p = model.get("pricing", {})
            pricing[model_id] = {
                "prompt": float(p.get("prompt", 0) or 0),
                "completion": float(p.get("completion", 0) or 0),
            }
        _log(f"Pricing loaded for {len(pricing)} models")
        return pricing
    except Exception as exc:
        _log(f"WARNING: Could not fetch pricing: {exc}")
        return {}


def calc_cost(usage: dict, pricing: dict, model_id: str, fallback_model_id: str = None) -> float:
    """
    Calculate approximate cost in USD from token usage and model pricing.

    Args:
        usage: dict with "prompt_tokens" and "completion_tokens"
        pricing: dict from fetch_model_pricing
        model_id: the exact model ID used for the request
        fallback_model_id: optional fallback ID (e.g. config model_id) if exact ID not found

    Returns:
        Approximate cost in USD.
    """
    model_pricing = pricing.get(model_id, {})
    if not model_pricing and fallback_model_id:
        model_pricing = pricing.get(fallback_model_id, {})
    prompt_price = model_pricing.get("prompt", 0)
    completion_price = model_pricing.get("completion", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    return (prompt_tokens * prompt_price + completion_tokens * completion_price) / 1_000_000


def build_messages(model_name: str, prompt: str, tournament_data: dict, rationale: str = None) -> list:
    """Builds the messages array for the chat API."""
    tournament_json = json.dumps(tournament_data, indent=2, ensure_ascii=False)
    user_msg = prompt.replace("<model name>", model_name).replace(TOURNAMENT_PLACEHOLDER, tournament_json)

    if not rationale:
        return [{"role": "user", "content": user_msg}]

    system_msg = (
        "You are an expert sports prediction system. You have already "
        "provided a strategic analysis of this tournament. Now you must "
        "respond with valid JSON predictions and nothing else."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "assistant", "content": f"Here is my strategic analysis:\n\n{rationale}"},
        {"role": "user", "content": user_msg},
    ]


def call_openrouter(api_key: str, model_id: str, messages: list, json_mode: bool = True) -> tuple:
    """
    Calls the OpenRouter API with retries.

    Args:
        json_mode: If True, request JSON output via response_format.
                   Phase 1 (rationale) should use False; Phase 2 (prediction) True.

    Returns (response_text, actual_model_id, usage_dict).
    Raises an exception if all attempts fail.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/mverab/WorldCupBench",
        "X-Title": "WorldCupBench",
    }
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    _log(f"→ POST {model_id} (timeout={REQUEST_TIMEOUT}s)", indent=1)
    phase_start = time.time()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            elapsed = time.time() - phase_start
            if resp.status_code == 200:
                body = resp.json()
                text = body["choices"][0]["message"]["content"]
                actual_model = body.get("model", model_id)
                usage = body.get("usage", {})
                usage_dict = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                _log(
                    f"← HTTP 200 in {elapsed:.1f}s "
                    f"({usage_dict['prompt_tokens']}+{usage_dict['completion_tokens']} tokens, "
                    f"{len(text) if text else 0} chars)",
                    indent=1,
                )
                if text is None:
                    raise RuntimeError(
                        f"API returned content=None ("
                        f"{usage_dict['prompt_tokens']}+{usage_dict['completion_tokens']} tokens). "
                        f"Possible function call or empty response."
                    )
                return text, actual_model, usage_dict

            # Recoverable errors: 429 (rate limit) and 5xx.
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                wait = RETRY_BACKOFF_SECONDS * attempt
                _log(f"Attempt {attempt} failed ({last_error}). Retrying in {wait}s...", indent=1)
                time.sleep(wait)
                continue

            # Non-recoverable errors (e.g. 400, 401, 404).
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        except requests.RequestException as exc:
            last_error = str(exc)
            wait = RETRY_BACKOFF_SECONDS * attempt
            _log(f"Attempt {attempt} - network error: {exc}. Retrying in {wait}s...", indent=1)
            time.sleep(wait)

    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}")


def call_rationale_phase(api_key: str, model: dict, rationale_prompt: str, tournament_data: dict) -> tuple:
    """
    Calls the rationale phase for a model.

    Returns (rationale_text, actual_model_id, usage_dict).
    """
    name = model["name"]
    model_id = model["model_id"]
    _log("Phase 1: Rationale", indent=1)

    tournament_json = json.dumps(tournament_data, indent=2, ensure_ascii=False)
    user_msg = rationale_prompt.replace("<model name>", name).replace(TOURNAMENT_PLACEHOLDER, tournament_json)

    # Build messages without rationale context for the first phase.
    system_msg = (
        "You are an expert football analyst and sports prediction system. "
        "Provide your strategic analysis in free-form markdown."
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    raw, actual_model, usage = call_openrouter(api_key, model_id, messages, json_mode=False)
    _log("✓ Rationale received — saved", indent=1)
    return raw, actual_model, usage


def call_prediction_phase(
    api_key: str, model: dict, prompt: str, rationale: str, schema: dict, tournament_data: dict
) -> tuple:
    """
    Calls the prediction phase for a model with rationale context.

    Returns (parsed_prediction_dict, actual_model_id, usage_dict).
    Raises an exception on failure.
    """
    name = model["name"]
    model_id = model["model_id"]
    _log("Phase 2: Prediction", indent=1)

    messages = build_messages(prompt, name, rationale=rationale)
    raw, actual_model, usage = call_openrouter(api_key, model_id, messages, json_mode=True)

    # Parse the JSON from the response.
    try:
        data = utils.extract_json(raw)
    except ValueError as exc:
        exc.raw_response = raw
        raise

    # Ensure model metadata (override model-generated values).
    data["model"] = name
    data["modality"] = "pre_tournament"
    data["generated_at"] = utils.now_iso()
    data["seed_or_temp"] = {"temperature": TEMPERATURE}

    # Validate against the schema and semantic rules.
    is_valid, msg = validate_predictions.validate(data, tournament_data)
    if not is_valid:
        exc = ValueError(f"Validation failed: {msg}")
        exc.raw_response = raw
        raise exc

    _log(f"✓ Validation: {msg} — saved", indent=1)
    return data, actual_model, usage


def run_model(
    api_key: str, model: dict, rationale_prompt: str, prompt: str,
    schema: dict, tournament_data: dict, dry_run: bool,
    model_index: int, total_models: int, pricing: dict,
) -> tuple:
    """
    Runs the 2-phase prediction for a model.

    Returns (success: bool, rationale_path: str|None, prediction_path: str|None).
    """
    name = model["name"]
    _log(f"[{model_index}/{total_models}] Model: {name}")

    if dry_run:
        _log("[dry-run] Skipping API calls", indent=1)
        return True, None, None

    model_start = time.time()

    # Track usage and cost across both phases.
    total_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    actual_model_id = model["model_id"]

    # --- Phase 1: Rationale ---
    rationale = None
    rationale_path = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            rationale, actual_model_id, usage = call_rationale_phase(api_key, model, rationale_prompt, tournament_data)
            total_usage["prompt_tokens"] += usage["prompt_tokens"]
            total_usage["completion_tokens"] += usage["completion_tokens"]
            total_usage["total_tokens"] += usage["total_tokens"]
            break
        except Exception as exc:
            _log(f"Phase 1 attempt {attempt} failed: {exc}", indent=1)
            if _is_non_retryable(exc):
                _log("Non-retryable error, aborting Phase 1.", indent=1)
                return False, None, None
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * attempt
                _log(f"Retrying Phase 1 in {wait}s...", indent=1)
                time.sleep(wait)
            else:
                _log(f"ERROR: Phase 1 failed after {MAX_RETRIES} attempts.", indent=1)
                return False, None, None

    # Save rationale.
    rationale_path = utils.save_rationale(name, rationale)

    # --- Phase 2: Prediction with retry ---
    prediction_path = None
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data, actual_model_id, usage = call_prediction_phase(
                api_key, model, prompt, rationale, schema, tournament_data
            )
            total_usage["prompt_tokens"] += usage["prompt_tokens"]
            total_usage["completion_tokens"] += usage["completion_tokens"]
            total_usage["total_tokens"] += usage["total_tokens"]
            break

        except Exception as exc:
            _log(f"Phase 2 attempt {attempt} failed: {exc}", indent=1)
            if _is_non_retryable(exc):
                _log("Non-retryable error, aborting Phase 2.", indent=1)
            if attempt < MAX_RETRIES and not _is_non_retryable(exc):
                wait = RETRY_BACKOFF_SECONDS * attempt
                _log(f"Retrying Phase 2 in {wait}s...", indent=1)
                time.sleep(wait)
                continue
            _log(f"ERROR: Phase 2 failed after {attempt} attempt(s).", indent=1)
            # Save raw response for debugging.
            debug_path = os.path.join(utils.RATIONALE_DIR, f"{name}_raw_error.txt")
            os.makedirs(utils.RATIONALE_DIR, exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                raw_text = getattr(exc, "raw_response", None)
                if raw_text:
                    f.write(raw_text)
                else:
                    f.write(str(exc))
            _log(f"Error details saved to: {debug_path}", indent=1)
            return False, rationale_path, None

    # Calculate cost and inject usage/cost into the prediction data.
    if data is not None:
        fallback_id = model["model_id"]
        cost_rationale = calc_cost(
            {
                "prompt_tokens": total_usage["prompt_tokens"] - usage["prompt_tokens"],
                "completion_tokens": total_usage["completion_tokens"] - usage["completion_tokens"],
            },
            pricing,
            actual_model_id,
            fallback_id,
        )
        cost_prediction = calc_cost(usage, pricing, actual_model_id, fallback_id)
        total_cost = calc_cost(total_usage, pricing, actual_model_id, fallback_id)

        data["usage"] = {
            "rationale": {
                "prompt_tokens": total_usage["prompt_tokens"] - usage["prompt_tokens"],
                "completion_tokens": total_usage["completion_tokens"] - usage["completion_tokens"],
                "total_tokens": (total_usage["prompt_tokens"] - usage["prompt_tokens"]
                                  + total_usage["completion_tokens"] - usage["completion_tokens"]),
            },
            "prediction": usage,
            "total": total_usage,
        }
        data["cost_usd"] = {
            "rationale": round(cost_rationale, 6),
            "prediction": round(cost_prediction, 6),
            "total": round(total_cost, 6),
        }

        prediction_path = utils.save_predictions(name, data, predictions_dir=utils.RATIONALE_DIR)

    model_elapsed = time.time() - model_start
    if data and "cost_usd" in data:
        _log(
            f"Model done in {_fmt_elapsed(model_elapsed)} — "
            f"{total_usage['total_tokens']} tokens, ~${data['cost_usd']['total']:.4f}",
            indent=1,
        )
    else:
        _log(f"Model done in {_fmt_elapsed(model_elapsed)}", indent=1)
    return True, rationale_path, prediction_path


def main():
    parser = argparse.ArgumentParser(description="Run WorldCupBench predictions.")
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Model names to run (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call the API; useful for validating setup.",
    )
    args = parser.parse_args()

    # Load variables from .env if python-dotenv is available.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(utils.BASE_DIR, ".env"))
    except ImportError:
        pass

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: The environment variable OPENROUTER_API_KEY is not set.")
        print("Set it with: export OPENROUTER_API_KEY='your_key'")
        sys.exit(1)

    prompt = utils.load_prompt()
    rationale_prompt = utils.load_rationale_prompt()
    schema = utils.load_schema()
    tournament_data = utils.load_tournament_data()

    # Fetch model pricing once at startup (for cost tracking).
    pricing = {}
    if api_key and not args.dry_run:
        pricing = fetch_model_pricing(api_key)

    # Select models.
    if args.models:
        selected = []
        for n in args.models:
            m = get_model_by_name(n)
            if m:
                selected.append(m)
            else:
                print(f"WARNING: unknown model '{n}', ignoring.")
        models = selected
    else:
        models = MODELS

    if not models:
        print("No models to run.")
        sys.exit(1)

    run_start = time.time()
    _log(f"Running predictions for {len(models)} model(s)")
    print()

    results = {}
    for idx, model in enumerate(models, start=1):
        ok, rationale_path, prediction_path = run_model(
            api_key, model, rationale_prompt, prompt, schema, tournament_data,
            args.dry_run, model_index=idx, total_models=len(models), pricing=pricing,
        )
        results[model["name"]] = {
            "ok": ok,
            "rationale_path": rationale_path,
            "prediction_path": prediction_path,
        }
        if idx < len(models):
            print()

    # Final summary.
    total_elapsed = time.time() - run_start
    successful = sum(1 for v in results.values() if v["ok"])

    _log("========== SUMMARY ==========")
    for name, info in results.items():
        status = "OK" if info["ok"] else "FAILED"
        r = info.get("rationale_path")
        p = info.get("prediction_path")
        r_status = "✓" if r else "✗"
        p_status = "✓" if p else "✗"
        _log(f"{name}: {status} (rationale: {r_status}, prediction: {p_status})", indent=1)
    _log(f"Total: {successful}/{len(results)} models successful", indent=1)
    _log(f"Total elapsed: {_fmt_elapsed(total_elapsed)}", indent=1)


if __name__ == "__main__":
    main()
