# Diseño: motor de scoring y validación post-PR#16

**Fecha:** 2026-06-11  
**Ámbito:** WorldCupBench — scoring engine, validación y schema de predicciones.

## 1. Contexto

Tras el PR#16 las predicciones usan el formato freeze-v3:

- `group_matches` con `match_id`, `probs{home,draw,away}`, `predicted_result`, `predicted_score`.
- `group_qualifiers.{first_place,second_place,best_third_place}`: listas de `{team_code, group}`.
- `bracket` con `R32`, `R16`, `QF`, `SF`, `final`, `third_place`.
- Top-level: `champion`, `runner_up`, `third`, `fourth_place`.

El scoring antiguo (`src/score.py`) aún usa `group_tables`, `best_thirds` y un bracket sin `match_id`. Este diseño define la nueva única fuente de scoring: `scripts/score.py`.

## 2. Decisiones clave

### 2.1. Arquitectura

**Opción B — script modular autónomo.**

`scripts/score.py` contendrá funciones pequeñas y testables, sin crear librerías adicionales. Es el mínimo necesario y evita dispersión.

### 2.2. Métricas por modelo

| Métrica | Definición | Escala |
|---------|------------|--------|
| `brier_group` | Suma sobre los 3 resultados 1X2 de cada partido de grupo: `Σ(p_i − y_i)²` | `[0, 2]` por partido |
| `brier_knockout` | Bernoulli binario: `p` = probabilidad asignada al equipo que el modelo predice que avanza (`winner`); `y = 1` si avanzó, `0` si no. `(p − y)²` | `[0, 1]` por partido |
| `brier_total` | Ponderado por partidos jugados, normalizando grupos a `[0,1]`: si `n_ko == 0` → `brier_group / 2`; si `n_group == 0` → `brier_knockout`; en otro caso → `(n_group * (brier_group / 2) + n_ko * brier_knockout) / (n_group + n_ko)`. | `[0, 1]` |
| `quiniela_points` | Puntos por acertar resultado/ganador según ronda. | ver tabla |
| `roi` | Retorno de inversión simulado en Polymarket. | porcentaje o `null` |
| `roi_status` | `"ok"`, `"no_market_data"`, etc. | string |
| `n_matches_scored` | Total de partidos con resultado real disponible puntuados. | integer |

**Puntos de quiniela:**

| Ronda | Puntos |
|-------|--------|
| Grupo | 1 |
| R32 | 2 |
| R16 | 4 |
| QF | 8 |
| THIRD | 8 |
| SF | 16 |
| FINAL | 32 |

**Reglas de acierto:**

- **Grupos:** se compara `predicted_result` del modelo con `outcome` real (`home`/`draw`/`away`).
- **Eliminatorias:** se compara el equipo `winner` predicho con el ganador real del partido.
- No hay empates en eliminatorias, por tanto no se usa `predicted_result` en R32-R16-QF-SF-FINAL-THIRD.

**Brier knockout — orientación:**

`p` debe ser la probabilidad asignada al equipo que figura en `winner`, independientemente de si es `home_team` o `away_team`:

```python
if match["winner"] == match["home_team"]:
    p = probs["home"]
elif match["winner"] == match["away_team"]:
    p = probs["away"]
else:
    # winner no coincide con ninguno de los dos equipos → dato inválido,
    # se ignora este partido para Brier y quiniela.
```

Si `winner` no coincide con `home_team` ni `away_team`, el partido no se puntuará para ese modelo (se contabiliza como no disponible para ese modelo, pero sigue contando como partido con resultado real para `n_matches_scored` global si el resultado existe).

### 2.3. ROI Polymarket

- Lectura de `data/polymarket/odds.json` y, opcionalmente, `data/polymarket/market_map.json`.
- Formato de `market_map.json`: `{ "match_id": { "conditionId": "...", "outcome_home": "Yes/...", "outcome_away": "..." } }`.
- Si el mapeo no existe o un partido no tiene mercado: `roi = null`, `roi_status = "no_market_data"`.
- Si existe mercado: para cada partido mapeado se apuestan $10 al outcome favorito del modelo (el equipo predicho como ganador). El retorno se calcula con el precio Gamma resuelto.
- No se inventan mercados. Con los datos actuales el resultado será `null` para todos los modelos.

### 2.4. Schema JSON

Se actualiza `schema/predictions_schema.json` para reflejar freeze-v3:

- Eliminar `group_tables` y `best_thirds`.
- Añadir `group_qualifiers` con `first_place`, `second_place`, `best_third_place`; cada elemento es `{ "team_code": "TLA", "group": "A" }`.
- Confirmar que `group_matches` exige `match_id`, `probs`, `predicted_result`, `predicted_score`.
- Confirmar `bracket` con `R32/R16/QF/SF/final/third_place`, `match_id` único, `probs` con `draw=0.0`, `winner`.
- Top-level: `champion`, `runner_up`, `third`, `fourth_place`.
- Metadata: `model`, `model_id`, `modality`, `generated_at`, `seed_or_temp`, `source_schema`.

### 2.5. Validación (`scripts/validate_predictions.py`)

1. Validación estructural con `jsonschema` usando el schema actualizado.
2. Validaciones semánticas:
   - `match_id` válidos contra `tournament.json`.
   - Probabilidades suman `1.0 ± 0.02`; `draw = 0.0` en eliminatorias.
   - Todos los `team_code` de `group_qualifiers` y `bracket` son TLAs FIFA presentes en `tournament.json`.
   - `group_qualifiers` tiene 12 + 12 + 8 entradas.
   - El `group` de cada entrada en `group_qualifiers` coincide con el grupo real del `team_code` en `tournament.json`.

### 2.6. Tests y limpieza

- Reescribir `tests/test_score.py` para importar `scripts.score`.
- Cubrir: Brier grupos 3 clases, Brier knockouts Bernoulli, `brier_total` normalizado, quiniela con THIRD=8, ROI `null` sin mercado.
- Actualizar `tests/test_validate_predictions.py` al formato `group_qualifiers`.
- Verificar con `grep` que nadie importa `src.score`.
- Eliminar `src/score.py` una vez los tests nuevos pasen.

## 3. Criterios de éxito

- `python scripts/score.py` genera `data/leaderboard.json` ordenado por `brier_total` ascendente.
- Todos los modelos de `predictions/pre-tournament/` son puntuados.
- Los 11 archivos de predicciones pasan `scripts/validate_predictions.py`.
- `pytest tests/test_score.py tests/test_validate_predictions.py tests/test_schema.py` pasa.
- `src/score.py` ya no existe y nadie lo referencia.

## 4. Notas de implementación

- Solo se puntúan partidos con resultado real disponible; el torneo está en curso.
- `brier_knockout` debe ser `null` (no `0`) cuando aún no hay eliminatorias disputadas.
- `brier_total` nunca debe dividir entre cero; manejar los tres casos de `n_group`/`n_ko`.
