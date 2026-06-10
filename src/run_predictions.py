"""
WorldCupBench - Main prediction execution script.

Reads the standard prompt and sends it to each SOTA model through the
OpenRouter API, parses and validates the JSON response, and saves each model's
predictions to predictions/{model_name}_predictions.json.

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
import sys
import time

import requests

# Allow running the script from the repo root or from src/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models_config import MODELS, get_model_by_name  # noqa: E402
import utils  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Execution parameters.
TEMPERATURE = 0.3
TOURNAMENT_PLACEHOLDER = "{{TOURNAMENT_DATA}}"

# Retry parameters.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
REQUEST_TIMEOUT = 180


def build_messages(prompt: str, model_name: str) -> list:
    """Builds the messages array for the chat API."""
    system_msg = (
        "You are an expert sports prediction system. You always respond "
        "with valid JSON and nothing else."
    )
    user_msg = prompt.replace("<model_name>", model_name)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    """
    Calls the OpenRouter API with retries. Returns the response text.
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
        # Request JSON output when the model supports it.
        "response_format": {"type": "json_object"},
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                body = resp.json()
                return body["choices"][0]["message"]["content"]

            # Recoverable errors: 429 (rate limit) and 5xx.
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"    Attempt {attempt} failed ({last_error}). "
                      f"Retrying in {wait}s...")
                time.sleep(wait)
                continue

            # Non-recoverable errors (e.g. 400, 401, 404).
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        except requests.RequestException as exc:
            last_error = str(exc)
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"    Attempt {attempt} - network error: {exc}. "
                  f"Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}")


def run_model(api_key: str, model: dict, prompt: str, schema: dict, dry_run: bool) -> bool:
    """Runs the prediction for a model. Returns True if successful."""
    name = model["name"]
    model_id = model["model_id"]
    print(f"\n=== Model: {name} ({model_id}) ===")

    if dry_run:
        print("    [dry-run] No API call is made.")
        return True

    messages = build_messages(prompt, name)
    try:
        raw = call_openrouter(api_key, model_id, messages)
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR calling model: {exc}")
        return False

    # Parse the JSON from the response.
    try:
        data = utils.extract_json(raw)
    except ValueError as exc:
        print(f"    ERROR parsing JSON: {exc}")
        # Save the raw response for debugging.
        debug_path = os.path.join(utils.PREDICTIONS_DIR, f"{name}_raw_error.txt")
        os.makedirs(utils.PREDICTIONS_DIR, exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"    Raw response saved to: {debug_path}")
        return False

    # Ensure model metadata.
    data.setdefault("model_name", name)
    data["model_id"] = model_id
    data.setdefault("timestamp", utils.now_iso())
    data["temperature"] = TEMPERATURE
    data.setdefault("prompt_version", "2.0")

    # Validate against the schema.
    is_valid, msg = utils.validate_predictions(data, schema)
    if not is_valid:
        print(f"    VALIDATION warning: {msg}")
    else:
        print(f"    Validation: {msg}")

    out_path = utils.save_predictions(name, data)
    print(f"    Predictions saved to: {out_path}")
    return True


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
    schema = utils.load_schema()

    # Load tournament data and inject it into the prompt.
    tournament_data = utils.load_tournament_data()
    tournament_str = json.dumps(tournament_data, indent=2, ensure_ascii=False)
    prompt = prompt.replace(TOURNAMENT_PLACEHOLDER, tournament_str)

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

    print(f"Running predictions for {len(models)} model(s)...")
    results = {}
    for model in models:
        ok = run_model(api_key, model, prompt, schema, args.dry_run)
        results[model["name"]] = ok

    # Final summary.
    print("\n========== SUMMARY ==========")
    successful = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")
    print(f"Total: {successful}/{len(results)} models successful.")


if __name__ == "__main__":
    main()
