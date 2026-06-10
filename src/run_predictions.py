"""
WorldCupBench - Script principal de ejecución de predicciones.

Lee el prompt estándar y lo envía a cada modelo SOTA a través de la API de
OpenRouter, parsea y valida la respuesta JSON, y guarda las predicciones de cada
modelo en predictions/{model_name}_predictions.json.

Uso:
    export OPENROUTER_API_KEY="tu_clave"
    python src/run_predictions.py                  # ejecuta todos los modelos
    python src/run_predictions.py --models GPT-5.5 Grok-3   # solo algunos
    python src/run_predictions.py --dry-run        # no llama a la API (prueba)

Requisitos: ver requirements.txt
"""

import argparse
import json
import os
import sys
import time

import requests

# Permitir ejecutar el script desde la raíz del repo o desde src/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models_config import MODELS, get_model_by_name  # noqa: E402
import utils  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Parámetros de la ejecución.
TEMPERATURE = 0.3
TOURNAMENT_PLACEHOLDER = "{{TOURNAMENT_DATA}}"

# Parámetros de reintentos.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
REQUEST_TIMEOUT = 180


def build_messages(prompt: str, model_name: str) -> list:
    """Construye el arreglo de mensajes para la API de chat."""
    system_msg = (
        "Eres un sistema experto de predicción deportiva. Respondes siempre "
        "con JSON válido y nada más."
    )
    user_msg = prompt.replace("<nombre del modelo>", model_name)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    """
    Llama a la API de OpenRouter con reintentos. Devuelve el texto de la respuesta.
    Lanza una excepción si todos los intentos fallan.
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
        # Solicitar salida en formato JSON cuando el modelo lo soporte.
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

            # Errores recuperables: 429 (rate limit) y 5xx.
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"    Intento {attempt} falló ({last_error}). "
                      f"Reintentando en {wait}s...")
                time.sleep(wait)
                continue

            # Errores no recuperables (p. ej. 400, 401, 404).
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        except requests.RequestException as exc:
            last_error = str(exc)
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"    Intento {attempt} - error de red: {exc}. "
                  f"Reintentando en {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Falló tras {MAX_RETRIES} intentos. Último error: {last_error}")


def run_model(api_key: str, model: dict, prompt: str, schema: dict, dry_run: bool) -> bool:
    """Ejecuta la predicción para un modelo. Devuelve True si tuvo éxito."""
    name = model["name"]
    model_id = model["model_id"]
    print(f"\n=== Modelo: {name} ({model_id}) ===")

    if dry_run:
        print("    [dry-run] No se realiza llamada a la API.")
        return True

    messages = build_messages(prompt, name)
    try:
        raw = call_openrouter(api_key, model_id, messages)
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR al llamar al modelo: {exc}")
        return False

    # Parsear el JSON de la respuesta.
    try:
        data = utils.extract_json(raw)
    except ValueError as exc:
        print(f"    ERROR al parsear JSON: {exc}")
        # Guardar la respuesta cruda para depuración.
        debug_path = os.path.join(utils.PREDICTIONS_DIR, f"{name}_raw_error.txt")
        os.makedirs(utils.PREDICTIONS_DIR, exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"    Respuesta cruda guardada en: {debug_path}")
        return False

    # Asegurar metadatos del modelo.
    data.setdefault("model_name", name)
    data["model_id"] = model_id
    data.setdefault("timestamp", utils.now_iso())
    data["temperature"] = TEMPERATURE
    data.setdefault("prompt_version", "2.0")

    # Validar contra el esquema.
    is_valid, msg = utils.validate_predictions(data, schema)
    if not is_valid:
        print(f"    ADVERTENCIA de validación: {msg}")
    else:
        print(f"    Validación: {msg}")

    out_path = utils.save_predictions(name, data)
    print(f"    Predicciones guardadas en: {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Ejecuta predicciones de WorldCupBench.")
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Nombres de modelos a ejecutar (por defecto: todos).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No llama a la API; útil para validar la configuración.",
    )
    args = parser.parse_args()

    # Cargar variables desde .env si python-dotenv está disponible.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(utils.BASE_DIR, ".env"))
    except ImportError:
        pass

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: La variable de entorno OPENROUTER_API_KEY no está definida.")
        print("Configúrala con: export OPENROUTER_API_KEY='tu_clave'")
        sys.exit(1)

    prompt = utils.load_prompt()
    schema = utils.load_schema()

    # Cargar datos del torneo e inyectarlos en el prompt.
    tournament_data = utils.load_tournament_data()
    tournament_str = json.dumps(tournament_data, indent=2, ensure_ascii=False)
    prompt = prompt.replace(TOURNAMENT_PLACEHOLDER, tournament_str)

    # Seleccionar modelos.
    if args.models:
        selected = []
        for n in args.models:
            m = get_model_by_name(n)
            if m:
                selected.append(m)
            else:
                print(f"ADVERTENCIA: modelo desconocido '{n}', se ignora.")
        models = selected
    else:
        models = MODELS

    if not models:
        print("No hay modelos para ejecutar.")
        sys.exit(1)

    print(f"Ejecutando predicciones para {len(models)} modelo(s)...")
    results = {}
    for model in models:
        ok = run_model(api_key, model, prompt, schema, args.dry_run)
        results[model["name"]] = ok

    # Resumen final.
    print("\n========== RESUMEN ==========")
    exitosos = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        estado = "OK" if ok else "FALLÓ"
        print(f"  {name}: {estado}")
    print(f"Total: {exitosos}/{len(results)} modelos exitosos.")


if __name__ == "__main__":
    main()
