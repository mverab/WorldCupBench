# Model Disagreement View — Product Requirements Document

**Fecha:** 2026-06-16  
**Feature:** Model Disagreement View  
**Autor:** Claude Opus 4.8  
**Estado:** Borrador / Listo para implementación

---

## 1. Visión

Permitir a los usuarios del dashboard de WorldCupBench descubrir, de un vistazo, en qué partidos los modelos de IA discrepan más sobre el resultado 1X2. Esto añade una dimensión analítica al benchmark: no solo qué predice cada modelo, sino dónde los mejores modelos del mundo no se ponen de acuerdo.

---

## 2. Objetivo

Entregar:

1. Un endpoint backend `GET /api/disagreement` que devuelva los 104 partidos ordenados por grado de desacuerdo entre modelos.
2. Una nueva pestaña "Disagreement" en el dashboard existente (`docs/index.html`) que muestre esos partidos con filtros por fase y visualización por modelo.

---

## 3. Alcance

### Dentro del alcance
- Endpoint FastAPI con filtros opcionales: `phase` (`group` | `knockout`) y `models` (lista separada por comas).
- Cálculo de desacuerdo basado en varianza de probabilidades 1X2.
- Fase de grupos: usa `home`, `draw`, `away`.
- Fase eliminatoria: ignora el empate y renormaliza `home` y `away`.
- Integración con el dashboard actual en vanilla JS + Tailwind.
- Tests con pytest.

### Fuera del alcance
- Persistencia de datos: se leen archivos JSON existentes en cada petición.
- Autenticación o rate limiting.
- Cálculos en tiempo real durante el torneo (vista pre-tournament sobre predicciones congeladas).

---

## 4. Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| FR-1 | El endpoint debe leer todas las predicciones disponibles en `predictions/pre-tournament/`. | Alta |
| FR-2 | El endpoint debe leer los metadatos del torneo desde `data/tournament.json`. | Alta |
| FR-3 | Debe calcular un `disagreement_score` por partido usando la varianza media de las probabilidades 1X2. | Alta |
| FR-4 | Los resultados deben ordenarse por `disagreement_score` descendente. | Alta |
| FR-5 | Debe soportar filtro por fase (`group`, `knockout`) y devolver 400 si la fase es inválida. | Media |
| FR-6 | Debe soportar filtro por uno o varios modelos (`?models=GPT-5.5,Grok-3`). | Media |
| FR-7 | El dashboard debe mostrar una pestaña "Disagreement" con filtros All / Group Stage / Knockout. | Alta |
| FR-8 | Los 10 partidos con mayor desacuerdo deben resaltarse visualmente con una insignia "Top Disagreement". | Media |
| FR-9 | Cada tarjeta de partido debe mostrar las probabilidades de cada modelo en barras coloreadas. | Alta |
| FR-10 | Si el servidor API no está disponible, el dashboard debe mostrar un mensaje de error amigable. | Media |

---

## 5. Requisitos no funcionales

- **Rendimiento:** El endpoint debe responder en < 500 ms para 104 partidos y ~10 modelos.
- **Mantenibilidad:** La lógica de cálculo debe estar desacoplada de FastAPI para ser testable puramente con pytest.
- **Compatibilidad:** El dashboard funciona localmente apuntando a `localhost:8000` y en producción bajo mismo origen.
- **Robustez:** IDs de partido comparados como strings (los modelos los devuelven como strings; `tournament.json` usa enteros).
- **Estilo:** Código y UI deben seguir los patrones existentes del proyecto.

---

## 6. API

### `GET /api/disagreement`

**Query params:**
- `phase` (opcional): `"group"` | `"knockout"`
- `models` (opcional): nombres separados por comas, ej. `GPT-5.5,Grok-3`

**Respuesta 200:**

```json
{
  "matches": [
    {
      "match_id": 1,
      "phase": "group",
      "group": "A",
      "round": null,
      "home_team": "MEX",
      "away_team": "RSA",
      "date": "2026-06-11",
      "disagreement_score": 0.123456,
      "model_predictions": [
        { "model": "GPT-5.5", "home": 0.7, "draw": 0.2, "away": 0.1 },
        { "model": "Grok-3", "home": 0.3, "draw": 0.4, "away": 0.3 }
      ]
    }
  ],
  "meta": {
    "total_matches": 104,
    "models_used": ["GPT-5.5", "Grok-3"],
    "phase_filter": null,
    "models_filter": null
  }
}
```

**Errores:**
- `400`: fase inválida.
- `500`: no se encuentra `tournament.json` o no hay predicciones disponibles.

---

## 7. Interfaz de usuario

### Pestaña "Disagreement"
- Filtros: All / Group Stage / Knockout.
- Lista vertical de tarjetas, ordenadas por desacuerdo descendente.
- Cada tarjeta incluye:
  - Equipos y banderas.
  - Etiqueta de fase/grupo o ronda.
  - Score de desacuerdo con 6 decimales.
  - Barras de probabilidad por modelo y resultado.
- Los 10 primeros resaltados como "Top Disagreement".

---

## 8. Criterios de aceptación

- [ ] `GET /api/disagreement` devuelve 104 partidos sin filtros.
- [ ] `GET /api/disagreement?phase=group` devuelve 72 partidos de grupo.
- [ ] `GET /api/disagreement?phase=knockout` devuelve 32 partidos eliminatorios.
- [ ] `GET /api/disagreement?phase=invalid` devuelve 400.
- [ ] `GET /api/disagreement?models=GPT-5.5` solo usa ese modelo.
- [ ] Los partidos están ordenados por `disagreement_score` descendente.
- [ ] El cálculo de grupo usa 3 probabilidades; el de eliminatoria ignora el empate.
- [ ] El dashboard muestra la pestaña y los datos correctamente.
- [ ] Todos los tests nuevos pasan.

---

## 9. Dependencias

- `fastapi>=0.110.0`
- `uvicorn[standard]>=0.29.0`
- Archivos de datos:
  - `data/tournament.json`
  - `predictions/pre-tournament/*_prediction.json`
- Dashboard existente (`docs/index.html`, `docs/app.js`) con Tailwind y `MODEL_COLORS`.

---

## 10. Notas de implementación

- Mantener `src/api/disagreement.py` libre de imports de FastAPI para facilitar tests unitarios.
- El cálculo en fase eliminatoria debe renormalizar `home` y `away` si su suma es distinta de cero; si ambos son cero, usar 0.5 cada uno.
- Los nombres de modelo en el filtro `models` deben compararse de forma normalizada (case-insensitive, guiones/espacios/underscores equivalentes).
- En producción, servir API y dashboard bajo el mismo origen para evitar problemas de CORS.

---

## 11. Métricas de éxito

- Tiempo de respuesta del endpoint < 500 ms.
- Cobertura de tests sobre el nuevo módulo `src/api/`.
- Dashboard usable sin errores de carga con el servidor API activo.
