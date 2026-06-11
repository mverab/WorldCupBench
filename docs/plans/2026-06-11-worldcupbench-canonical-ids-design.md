# WorldCupBench — Corrección crítica: TLAs canónicos, probabilidades 1X2 y join por fd_id

## Fecha

2026-06-11

## Contexto

El benchmark usa actualmente `data/tournament.json` como fuente de verdad local. Los modelos reciben un prompt con los datos del torneo y deben devolver predicciones JSON. El scoring compara esas predicciones contra resultados reales.

Existen tres problemas críticos:

1. **Grupos inventados por los modelos:** el prompt no inyecta los datos oficiales completos, por lo que algunos modelos alucinan grupos o nombres en español.
2. **Formato de predicción inadecuado:** el schema actual mezcla `predicted_winner` + `confidence` con probabilidades 1X2, y obliga a scores exactos que no siempre son necesarios.
3. **Join frágil resultados ↔ predicciones:** `fetch_results.py` empareja por equipo + fecha porque no hay un ID estable de la API.

La API de football-data.org (`competition 2000`, `season 2398`) ya publica los 104 partidos con `tla`, `group` y `id` estables. Usaremos ese `id` como `fd_id` para unir resultados y predicciones.

## Decisiones de diseño

### 1. `data/tournament.json` se enriquece, no se regenera

El archivo actual contiene información valiosa que no está en football-data.org: `venues`, `cities`, `knockout_bracket` con `feeds_into`, etc. Por eso `build_tournament.py` **cargará el archivo existente**, consultará la API y añadirá únicamente el campo `fd_id` a cada partido, cruzando por `(home_team, away_team, date)`.

No se eliminan ni renombran campos existentes. El `match_id` numérico actual se conserva.

### 2. Nuevo schema de predicciones

Estructura mínima y orientada a probabilidades:

```json
{
  "model": "string",
  "modality": "pre_tournament | daily",
  "generated_at": "ISO8601 UTC",
  "seed_or_temp": {"temperature": 0.0, "seed": 42},
  "group_matches": [
    {"match_id": "GRP_A_M01_MEX_RSA", "probs": {"home": 0.55, "draw": 0.27, "away": 0.18}}
  ],
  "group_tables": {"A": ["MEX", "RSA", "..."]},
  "best_thirds": ["TLA", "TLA", "..."],
  "bracket": {
    "R32": [{"match": "...", "winner": "TLA"}],
    "R16": [],
    "QF": [],
    "SF": [],
    "third_place": "TLA",
    "final": {"winner": "TLA", "runner_up": "TLA"}
  },
  "champion": "TLA",
  "runner_up": "TLA",
  "third": "TLA"
}
```

Reglas duras:

- `probs.home + probs.draw + probs.away` debe sumar `1.0 ± 0.01`.
- Todos los equipos son TLAs FIFA de 3 letras mayúsculas.
- `match_id` de cada partido de grupo debe existir en `data/tournament.json`.
- 12 grupos × 4 equipos = 48 equipos en `group_tables`.
- 8 mejores terceros en `best_thirds`.

### 3. Prompt inyecta `data/tournament.json`

El prompt reemplaza `{{TOURNAMENT_JSON}}` por el contenido real de `data/tournament.json` (enriquecido). El modelo no debe inventar grupos ni equipos; debe usar únicamente los `match_id` y TLAs proporcionados.

### 4. `fetch_results.py` se mueve a `scripts/` y cruza por `fd_id`

- Consulta `competition 2000`, `season 2398`.
- Solo procesa partidos con `status = FINISHED`.
- Extrae `score.fullTime.home/away`, deriva outcome 1X2.
- Guarda en `data/results/YYYY-MM-DD.json` usando `fd_id` como clave de join y conservando `match_id` legible.
- Ignora partidos `IN_PLAY` o `TIMED`.

### 5. Validación standalone

`scripts/validate_predictions.py` carga una predicción y `data/tournament.json`, verifica:

- Cumplimiento del schema JSON.
- Suma de probabilidades.
- TLAs válidos.
- Existencia de `match_id` de grupo.
- Consistencia del bracket (ganadores avanzan correctamente).

### 6. Scoring actualizado

`src/score.py` lee predicciones en el nuevo formato, las cruza con resultados por `fd_id` y calcula:

- Brier score acumulado sobre `probs`.
- Bracket points por ronda.
- Outcomes correctos.
- Scores exactos cuando aplique.

### 7. Limpieza de archivos obsoletos

- Mover predicciones `pre-tournament` actuales a `predictions/invalidated/freeze-v3/` porque usan el schema antiguo.
- Eliminar `data/world_cup_2026_info.md` (markdown reemplazado por `data/tournament.json`).
- No tocar dashboard, workflows ni assets.

## Archivos a modificar/crear

| Ruta | Acción |
|------|--------|
| `scripts/build_tournament.py` | Crear |
| `scripts/validate_predictions.py` | Crear |
| `scripts/fetch_results.py` | Crear (mover lógica desde `src/fetch_results.py`) |
| `schema/predictions_schema.json` | Reescribir |
| `prompts/prediction_prompt.txt` | Reescribir |
| `src/run_predictions.py` | Actualizar al nuevo prompt/schema |
| `src/score.py` | Actualizar al nuevo formato |
| `tests/test_score.py` | Actualizar fixtures |
| `src/fetch_results.py` | Eliminar (se mueve a `scripts/`) |
| `data/world_cup_2026_info.md` | Eliminar |
| `predictions/pre-tournament/*` | Mover a `predictions/invalidated/freeze-v3/` |

## Testing

- `tests/test_score.py` smoke tests con resultados manuales y reales en nuevo formato.
- Test para `validate_predictions.py` con una predicción válida y una inválida.
- Verificar que `build_tournament.py` no altera la estructura de `data/tournament.json` más allá de añadir `fd_id`.

## Notas y riesgos

- `data/tournament.json` quedará temporalmente sin `fd_id` hasta que el usuario ejecute `build_tournament.py` con `FOOTBALL_DATA_API_KEY`. El resto del código debe tolerar esa ausencia o el usuario debe regenerar antes de usar `fetch_results.py`.
- El cambio de schema invalida todas las predicciones previas; se moverán a `invalidated/`.
- El dashboard y los workflows de GitHub Actions quedan fuera de scope en esta tarea.
