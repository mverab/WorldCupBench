# WorldCupBench — Code Audit PRD

**Fecha:** 2026-06-16  
**Propósito:** Guía práctica para auditar el código existente de WorldCupBench.  
**Autor:** Claude Opus 4.8  
**Estado:** Borrador / Listo para usar.

---

## 1. Visión

Auditar el código de WorldCupBench para encontrar problemas reales, verificar que el sistema hace lo que dice hacer, y dejar una lista priorizada de arreglos. Sin reescribir el proyecto, sin metodologías pesadas.

---

## 2. Objetivo

Entregar un informe de auditoría con:

1. Lista de problemas encontrados clasificados por severidad (crítico / alto / medio / bajo).
2. Verificación de que los flujos principales funcionan: predicciones, validación, scoring, dashboard, API.
3. Recomendaciones concretas y aplicables, ordenadas por impacto.
4. Tests o reproducciones mínimas para cada problema crítico.

---

## 3. Alcance

### Dentro del alcance

- `src/` — modelos, utilidades, ejecución de predicciones, API.
- `scripts/` — scoring, validación, fetching de resultados, helpers.
- `tests/` — cobertura actual, utilidad de los tests, tests que fallan.
- `schema/predictions_schema.json` — coherencia con el prompt y con `utils.validate_predictions`.
- `data/` y `predictions/` — integridad de datos, formatos, ids.
- `docs/` — dashboard (`index.html`, `app.js`) y README.
- `requirements.txt` — dependencias y versiones.

### Fuera del alcance

- Reescritura de funcionalidades.
- Auditoría de seguridad ofensiva (pentest) o análisis de infraestructura.
- Diseño de nuevas features.
- Optimización de rendimiento exhaustiva (solo señalar cuellos de botella evidentes).

---

## 4. Requisitos de auditoría

### 4.1 Correctitud funcional

| ID | Requisito | Prioridad |
|---|---|---|
| A-1 | Verificar que `src/run_predictions.py` genera predicciones válidas para cada modelo configurado. | Alta |
| A-2 | Verificar que `src/utils.py:extract_json` maneja correctamente JSON con/sin fences de markdown. | Alta |
| A-3 | Verificar que `scripts/score.py` calcula accuracy, Brier y ROI de forma correcta y reproducible. | Alta |
| A-4 | Verificar que `scripts/fetch_results.py` mapea resultados reales a `match_id` sin duplicados ni pérdidas. | Alta |
| A-5 | Verificar que `scripts/build_tournament.py` genera 104 partidos con ids únicos y fases correctas. | Alta |
| A-6 | Verificar que el endpoint `/api/disagreement` (si está presente) devuelve resultados coherentes. | Media |

### 4.2 Robustez y manejo de errores

| ID | Requisito | Prioridad |
|---|---|---|
| B-1 | Revisar qué pasa cuando OpenRouter devuelve 429, 5xx, timeout o JSON inválido. | Alta |
| B-2 | Revisar manejo de archivos de predicciones incompletos, corruptos o con keys faltantes. | Alta |
| B-3 | Revisar manejo de `data/tournament.json` o `data/results/*.json` ausentes. | Media |
| B-4 | Revisar que el dashboard no rompa si el API no responde o devuelve estructuras inesperadas. | Media |
| B-5 | Revisar que `run_predictions.py` no pierda el progreso si un modelo falla a la mitad. | Baja |

### 4.3 Consistencia de datos y schema

| ID | Requisito | Prioridad |
|---|---|---|
| C-1 | Comparar `schema/predictions_schema.json` con el ejemplo del prompt y con las validaciones de `utils.py`. | Alta |
| C-2 | Verificar que los `match_id` sean consistentes entre `tournament.json`, resultados y predicciones. | Alta |
| C-3 | Verificar que los nombres de modelo en `src/models_config.py` coincidan con los archivos en `predictions/`. | Media |
| C-4 | Verificar que no haya campos requeridos en el schema que los modelos no estén generando. | Alta |

### 4.4 Calidad de código y mantenibilidad

| ID | Requisito | Prioridad |
|---|---|---|
| D-1 | Detectar código duplicado entre `src/` y `scripts/`. | Media |
| D-2 | Detectar funciones largas o con múltiples responsabilidades. | Media |
| D-3 | Revisar nombres de variables, funciones y archivos. | Baja |
| D-4 | Revisar que no haya imports, variables o funciones muertas introducidas por cambios recientes. | Media |
| D-5 | Revisar que los paths se construyan con `BASE_DIR` o `Path`, no con strings hardcodeadas. | Media |

### 4.5 Testing

| ID | Requisito | Prioridad |
|---|---|---|
| E-1 | Ejecutar la suite de tests y documentar fallos. | Alta |
| E-2 | Revisar qué partes del código carecen de tests. | Media |
| E-3 | Revisar si los tests usan mocks en lugar de llamadas reales a API. | Alta |
| E-4 | Revisar si los tests de schema validan todos los casos de borde. | Media |

### 4.6 Seguridad básica

| ID | Requisito | Prioridad |
|---|---|---|
| F-1 | Verificar que `OPENROUTER_API_KEY` se lea de `.env` y no esté hardcodeada. | Alta |
| F-2 | Verificar que archivos de predicciones no expongan la API key. | Alta |
| F-3 | Revisar que el dashboard no haga peticiones a dominios no confiables sin CORS controlado. | Baja |

---

## 5. Metodología

1. **Lectura rápida:** revisar README, CLAUDE.md, y los archivos principales en `src/` y `scripts/`.
2. **Ejecución:** correr tests, correr `run_predictions.py --dry-run`, correr `scripts/score.py` y `scripts/validate_predictions.py`.
3. **Revisión por áreas:** usar la checklist de la sección 4.
4. **Reproducción:** para cada problema crítico, escribir el comando o test mínimo que lo reproduce.
5. **Informe:** llenar la plantilla de la sección 9.

---

## 6. Criterios de aceptación

- [ ] Todos los tests existentes pasan, o cada fallo está documentado con severidad.
- [ ] Se identifican todos los problemas críticos y altos con reproducción clara.
- [ ] Se entrega un ranking de arreglos por impacto/esfuerzo.
- [ ] No se proponen refactorizaciones que no estén justificadas por un problema real.

---

## 7. Entregables

1. `docs/audit/YYYY-MM-DD-code-audit-report.md` — informe con hallazgos, severidad y recomendaciones.
2. Issues o tareas en el tracker del proyecto para cada problema crítico/alto.
3. Opcional: PRs pequeños para arreglos triviales (typos, imports muertos) si no interfieren con trabajo en curso.

---

## 8. Riesgos

- **Datos en movimiento:** durante el torneo, `data/results/` cambia. La auditoría debe usar una snapshot congelada o verificar la rama actual.
- **Dependencia de API key:** algunos flujos (`run_predictions.py`) requieren `OPENROUTER_API_KEY`. Usar `--dry-run` o mocks.
- **Scope creep:** mantenerse en encontrar problemas, no rediseñar features.

---

## 9. Plantilla de hallazgo

Cada problema debe documentarse con esta estructura mínima:

```markdown
### AUD-NN: Título corto

- **Severidad:** crítico / alto / medio / bajo
- **Área:** src / scripts / tests / schema / dashboard / datos
- **Archivo(s):** `ruta/al/archivo.py:linea`
- **Descripción:** qué está mal y por qué importa.
- **Reproducción:** comando o test mínimo.
- **Recomendación:** arreglo concreto.
- **Esfuerzo estimado:** XS / S / M / L
```

---

## 10. Notas

- Priorizar lo que afecta el resultado del benchmark (scoring, validación, datos) sobre lo cosmético.
- Si algo funciona, no tocarlo.
- Si un problema ya está documentado en un issue o PR, enlazarlo en lugar de duplicarlo.
