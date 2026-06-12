<p align="center">
  <img src="assets/banner.png" alt="WorldCupBench — 10 LLMs de última generación predijeron todo el Mundial 2026" width="100%">
</p>

<h1 align="center">WorldCupBench ⚽🤖</h1>

<p align="center">
  <strong>La Copa del Mundo es la evaluación definitiva de LLMs.</strong><br>
  10 modelos de IA de última generación predijeron cada partido del Mundial FIFA 2026 — congeladas pre-torneo, puntuadas en vivo.
</p>

<p align="center">
  <a href="https://github.com/mverab/WorldCupBench/stargazers"><img src="https://img.shields.io/github/stars/mverab/WorldCupBench?style=social" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="Licencia"></a>
  <img src="https://img.shields.io/badge/🔒%20Predicciones%20Congeladas-10%20de%20junio%20de%202026-red" alt="Congeladas">
  <img src="https://img.shields.io/github/last-commit/mverab/WorldCupBench" alt="Último Commit">
</p>

<p align="center">
  <a href="README.md">🇺🇸 English Version</a>
</p>

---

## 🏆 Tabla de Posiciones en Vivo

<!-- LEADERBOARD:START -->

*La tabla se generará automáticamente cuando se recolecten todas las predicciones. Ejecuta `python src/generate_leaderboard.py --inject-readme` para actualizar.*

<!-- LEADERBOARD:END -->

---

## ⚡ Cómo Funciona (en 4 líneas)

1. **Mismo prompt** → 10 LLMs SOTA vía OpenRouter.
2. **Predicciones JSON** → cada partido, cada ronda, cada marcador, con probabilidades 1X2.
3. **Congeladas antes del pitido inicial** → sin edición posterior. La credibilidad es todo.
4. **Puntuadas en vivo** → a medida que lleguen los resultados reales, calculamos precisión, Brier score y ROI vs Polymarket.

---

## 🔮 Predicciones Destacadas

> ¿En qué coinciden los 10 modelos? ¿En qué discrepan?

<!-- FEATURED:START -->

*Las predicciones destacadas aparecerán aquí cuando todos los modelos hayan enviado sus predicciones. ¡Vuelve pronto!*

<!-- FEATURED:END -->

---

## 🚀 Inicio Rápido

```bash
# Clonar y configurar
git clone https://github.com/mverab/WorldCupBench.git
cd WorldCupBench
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configurar tu API key de OpenRouter
cp .env.example .env
# Edita .env y añade tu key

# Ejecutar predicciones para todos los modelos
python src/run_predictions.py

# O ejecutar solo modelos específicos
python src/run_predictions.py --models GPT-5.5 Grok-3

# Validar configuración sin llamar a APIs
python src/run_predictions.py --dry-run

# Generar tabla de posiciones desde las predicciones recolectadas
python src/generate_leaderboard.py --inject-readme
```

---

## 🤖 Modelos Comparados (SOTA, Junio 2026)

| Modelo | Proveedor | ID de OpenRouter |
|--------|-----------|------------------|
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

Todos los modelos reciben el **mismo prompt exacto** con datos del torneo y deben devolver JSON estructurado cubriendo los 104 partidos. Ver [`prompts/prediction_prompt.txt`](prompts/prediction_prompt.txt).

---

## 📐 Metodología

### Esquema de Predicciones

Cada modelo genera un objeto JSON validado contra [`schema/predictions_schema.json`](schema/predictions_schema.json) (Draft-07):

- **72 partidos de fase de grupos** con marcador exacto y probabilidades 1X2 (suma = 1.0 ± 0.02)
- **Clasificados por grupo**: 12× 1ros, 12× 2dos, 8× mejores 3ros
- **Fase eliminatoria**: 32avos → 16avos → Cuartos → Semifinales → 3er puesto + Final
- **Posiciones finales**: Campeón, Subcampeón, Tercero, Cuarto

### Reglas Clave

- **Solo códigos FIFA**: códigos de 3 letras (ej. `ARG`, `FRA`, `BRA`)
- **Eliminatoria = sin empates**: `probs.draw` debe ser `0.0`; si el modelo predice empate en 90 min, debe indicar el ganador de tiempo extra/penales
- **Timestamp congelado**: Todas las predicciones se generaron y commitearon antes del partido inaugural (11 de junio de 2026)

---

## 📊 Cómo se calcula el ranking

WorldCupBench puntúa cada modelo en **tres métricas independientes**. El orden
del leaderboard viene de las métricas **probabilísticas**, no del pick puntual.

| Métrica | Qué mide | Campo usado |
|---|---|---|
| **Brier score** ↓ | Calibración de las probabilidades 1X2 | `probs.{home,draw,away}` |
| **Precisión de resultado** ↑ | ¿Ocurrió el resultado más probable? (`argmax(probs)`) | `probs.{home,draw,away}` |
| **Puntos de marcador exacto** ↑ | ¿Coincidió el marcador exacto? | `predicted_result` + `predicted_score` |

> [!IMPORTANT]
> El ranking (Brier + precisión de resultado) se calcula **estrictamente desde
> las probabilidades 1X2** (`probs`). Los campos `predicted_result` y
> `predicted_score` alimentan **solo** la métrica de marcador exacto.
>
> Por eso puedes ver un partido donde `probs.away` es el valor más alto pero
> `predicted_result` es `"draw"`: en partidos parejos (p. ej.
> `0.30 / 0.30 / 0.40`) un modelo puede racionalmente elegir empate como su
> mejor pick individual mientras aún asigna la probabilidad marginalmente mayor
> a un lado. **Esta es una decisión legítima del modelo, no un error de datos.**
> Las 792 predicciones congeladas (11 modelos × 72 partidos de grupos) fueron
> auditadas: **0 inconsistencias** entre `predicted_result` y
> `predicted_score`.

### 🧊 Procedencia del freeze (`freeze-v3`)

Todas las predicciones pre-torneo fueron congeladas **antes del pitido inicial**
y llevan trazabilidad:

- `source_schema: "freeze-v3"` — la versión de schema bajo la cual se generó
  la predicción.
- `model_id` — el checkpoint exacto consultado (p. ej.
  `anthropic/claude-5-fable-20260609`).
- `generated_at` — timestamp UTC de generación.
- `orientation_flipped` — `true` cuando el partido quedó almacenado en la
  orientación local/visitante opuesta al fixture oficial. En esos partidos
  `probs`, `predicted_result` y `predicted_score` están **todos** normalizados
  a la orientación oficial, así que los datos son internamente consistentes.

> ⚽ MEX–RSA (partido 1) cuenta para puntuar: el timestamp del freeze
> (2026-06-10) precede al partido (2026-06-11). `freeze-v3` **no** incluye
> predicción de bracket/campeón, así que esos puntos se puntúan como 0 para
> esta modalidad.

---

## 📁 Estructura del Proyecto

```
.
├── README.md                       # Este archivo
├── README.es.md                    # Versión en español
├── FREEZE.md                       # Registro de auditoría: hash, timestamps, checksums
├── LICENSE
├── .env.example
├── requirements.txt
├── schema/
│   └── predictions_schema.json     # JSON Schema draft-07
├── prompts/
│   └── prediction_prompt.txt       # Prompt estándar para TODOS los modelos
├── src/
│   ├── run_predictions.py          # Script principal de ejecución
│   ├── models_config.py            # Definiciones de modelos
│   ├── utils.py                    # Parsing, validación, I/O
│   └── generate_leaderboard.py     # Generar tabla auto-actualizable
├── predictions/                    # JSONs de predicciones por modelo
├── data/
│   └── tournament.json             # Datos oficiales del sorteo FIFA
└── assets/
    ├── banner.png                  # Banner del README
    └── social-preview.png          # GitHub social preview (1280×640)
```

---

## 🏷️ Temas del Repositorio

`llm` `benchmark` `llm-evaluation` `ai` `world-cup` `fifa-world-cup-2026` `predictions` `forecasting` `leaderboard` `sports-analytics` `gpt-5` `claude` `gemini`

---

## 🤝 Contribuir

### Añade Tu Modelo

¿Quieres añadir un nuevo modelo? Es un PR:

1. Añade tu modelo a `src/models_config.py`:
   ```python
   {
       "name": "Tu-Modelo",
       "model_id": "proveedor/nombre-modelo",
       "provider": "Tu Laboratorio",
   }
   ```
2. Ejecuta `python src/run_predictions.py --models Tu-Modelo`
3. Envía un PR con el JSON generado

### Añade Resultados Reales

A medida que los partidos concluyen, añade los resultados reales a `data/results.json` (formato por definir) para calcular precisión en vivo.

### Mejora la Puntuación

El sistema de puntuación está evolucionando. Abre un issue o PR con tu métrica propuesta.

---

## 📜 Licencia

MIT — ver [LICENSE](LICENSE).

> Datos del torneo obtenidos de fuentes oficiales de la FIFA. Este proyecto es con fines educativos y de investigación.

---

<p align="center">
  <sub>Hecho con ⚽ y 🤖 por <a href="https://github.com/mverab">@mverab</a></sub>
</p>
