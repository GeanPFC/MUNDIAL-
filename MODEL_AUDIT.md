# MODEL_AUDIT.md — Auditoría del sistema de predicción Mundial 2026

Fecha de auditoría: 2026-06-13
Auditor: equipo Data Science / ML / MLOps (revisión de punta a punta, solo lectura).
Alcance: `worldcup-2026-predictor/` completo (Python `src/`, scripts, API serverless `api/` + `vercel-app/`, frontend, datos y reportes).
Objetivo declarado del proyecto: análisis deportivo serio, explicable y reproducible. **No** orientado a apuestas.

> Esta auditoría **no modifica código**. Es el diagnóstico previo exigido en la Fase 1. Las correcciones se proponen en el plan de implementación, no se aplican aquí.

---

## 0. Resumen ejecutivo

El proyecto está **mejor construido de lo habitual** para un predictor amateur: tiene separación en módulos, Elo recalculado internamente, Poisson con shrinkage y pesos por recencia, Dixon-Coles, un modelo bayesiano Gamma-Poisson, un ML (HistGradientBoosting / XGBoost), métricas probabilísticas correctas (log loss, Brier, ECE) y **backtesting temporal real** contra los Mundiales 2014/2018/2022 con cortes sin fuga. La filosofía documentada ("no aceptar complejidad que no mejore log loss/Brier fuera de muestra") es exactamente la correcta.

Sin embargo, hay **tres problemas de alto impacto** que contradicen el objetivo del usuario o dejan deliverables clave sin funcionar:

| # | Severidad | Problema | Impacto |
|---|---|---|---|
| C1 | **CRÍTICO (mandato)** | El modelo en producción (`api/_model.js`) genera **guía de apuestas** (`buildBettingGuidance`: "apuesta más segura", "cuota justa", doble oportunidad, niveles de riesgo) y el frontend la muestra. | Contradice frontalmente el requisito "El objetivo NO es apostar". Debe eliminarse. |
| C2 | **CRÍTICO (funcional)** | La **simulación de torneo** (`src/simulation.py`, Monte Carlo) **no se ejecuta desde ningún script**, **no existe dataset de calendario/grupos/llave 2026**, y la lógica de conteo de rondas está **incompleta y mal etiquetada** (no cuenta octavos ni cuartos). | Los deliverables centrales —probabilidad de campeón, llegar a SF/final, posición de grupo, clasificar— **hoy no se producen**. |
| C3 | **ALTO** | No existe capa de **calibración entrenada**. La "calibración v2" son **constantes hard-codeadas a mano** en JS (`temperature: 0.91`, `drawMultiplier: 0.96`); el lado Python **no calibra nada**. | La mejora reportada (log loss 0.9989 vs 0.9999) es marginal (~0.1%) y no reproducible vía un paso `fit` sobre validación. |

Además: **cero pruebas unitarias**, **sin archivo de configuración** (constantes dispersas en Python y JS), **árbol de la app duplicado** (`/api`, `/public`, `/static` **y** `/vercel-app/...`), y **sin versionado/pinning del dataset** (la fuente `martj42` es un blanco móvil).

**Veredicto:** la base estadística 1×2 por partido es sólida y defendible. Lo que falta para cumplir el encargo es: (a) quitar lo de apuestas, (b) **construir y conectar de verdad** la simulación del torneo con datos oficiales 2026, (c) convertir la calibración en un paso entrenado y validado, y (d) reproducibilidad (config, tests, versionado). Recomendación: **conservar el núcleo Elo+Poisson** (cumple el principio "no romper lo que ya valida") y construir el resto alrededor.

---

## 1. Inventario del proyecto

**Lenguaje / stack**
- **Python 3.13** (núcleo de modelado, `src/`): pandas, numpy, scipy, scikit-learn, opcional xgboost/shap. Sin venv creado todavía (`requirements.txt` presente).
- **Node.js 24 / JavaScript ESM** (modelo "espejo" para producción serverless en Vercel): reimplementa Elo + Poisson + calibración **en JS** dentro de `api/_model.js`.
- Frontend estático HTML/CSS/JS (`public/`, `static/`).

**Datos (`data/raw/`)** — snapshots de [`martj42/international_results`](https://github.com/martj42/international_results):
- `results.csv` — 49.477 partidos internacionales masculinos, 1872-11-30 → 2026-06-27. **Incluye los 72 partidos de fase de grupos del Mundial 2026** (con resultados reales ya cargados para 11–12 jun 2026 y `NA` para los aún no jugados).
- `shootouts.csv` — ganadores por penales (hasta jun 2026).
- `goalscorers.csv` — goleadores (no usado por el modelo base).
- `source_manifest.json` — registra fuentes + recordatorio de snapshots manuales (ranking FIFA, calendario 2026) que **nunca se cargaron**.

**Módulos de modelado (`src/`)**
- `preprocessing.py` — carga/limpieza, importancia por torneo, pesos por recencia (half-life 1095 d), splits temporales con guardia anti-overlap.
- `features.py` — features supervisadas walk-forward: Elo pre-partido, forma rodante (ventana 10), descanso, deltas. Merge `merge_asof` para features externas.
- `elo_model.py` — Elo con ventaja local, ajuste por margen e importancia; draw heurístico por decaimiento.
- `poisson_model.py` — Poisson con shrinkage, Dixon-Coles (τ + grid search de ρ), matriz de marcadores, xG, intervalos.
- `bayesian_model.py` — Gamma-Poisson conjugado ataque/defensa + incertidumbre posterior.
- `ml_model.py` — XGBoost (si está) o HistGradientBoosting + permutation importance.
- `ensemble.py` — promedio ponderado de probabilidades; pesos por softmax sobre log loss de backtest; guardia "candidato debe vencer baseline".
- `evaluation.py` — log loss, Brier multiclase, ECE, accuracy; backtest temporal y por edición de Mundial; baselines (tasas, Elo).
- `simulation.py` — Monte Carlo de grupos + eliminatorias (**ver C2: no conectado, datos ausentes, conteo incompleto**).
- `data_collection.py` — descarga snapshots + manifest.

**Scripts de entrada**
- `predict_match.py` — predicción 1×2 + goles de un partido con fecha de corte (usa **solo Elo + Poisson**, no el ensemble ni bayes).
- `run_backtest.py` — backtest por edición 2014/2018/2022, escribe CSV en `reports/`.
- `web_app.py`, `build_static_snapshot.py`, `start/stop_frontend.*` — servidor/snapshot del frontend.

**Producción (Vercel)** — `api/` (`predict.js`, `teams.js`, `backtest.js`, `refresh.js`, `_model.js`, `_teams_es.js`) + `public/`. **Duplicado** íntegro en `vercel-app/`.

**Salidas actuales (`reports/`)**: `methodology.md`, `backtesting_summary.md`, `model_v2_improvement_summary.md`, 2 CSV de backtest. No hay artefactos de modelo serializados (todo se reentrena en caliente).

---

## 2. ¿Qué predice exactamente el modelo hoy?

**Sí produce (por partido, vía Python `predict_match.py` y JS `/api/predict`):**
- Probabilidad 1×2 (victoria A / empate / victoria B) — **núcleo = Elo** (en JS, Elo calibrado + 3% Poisson).
- Goles esperados (λ) de A y B — **Poisson** con shrinkage.
- Marcador modal y, en JS, **top-5 marcadores** + intervalos de goles + probabilidades over/under.
- Nivel de incertidumbre/confianza y variables influyentes (ratings Elo, ataque/defensa).

**NO produce hoy (aunque el encargo y el README los piden):**
- ❌ **Probabilidad de ganar el grupo / quedar 1.º-4.º / clasificar.**
- ❌ **Probabilidad de llegar a R32 / octavos / cuartos / semi / final / campeón.**
- ❌ Simulación Monte Carlo del torneo ejecutable (código existe pero **muerto**, sin datos).
- ❌ Marcador exacto como salida del modelo Python (sí en JS top-5).
- Parcial: el "ensemble" y el bayesiano existen pero **no** alimentan la predicción final desplegada (el deploy usa Elo calibrado + 3% Poisson, no el ensemble).

**Conclusión:** el sistema es hoy un **predictor de partido individual**, no un **simulador de torneo**. La mitad "torneo" del encargo está sin implementar de forma utilizable.

---

## 3. Hallazgos detallados (por severidad)

### 🔴 Críticos

**C1 — Lógica de apuestas en producción, contraria al objetivo.**
`api/_model.js:332-434` (`buildBettingGuidance`) y su consumo en `api/_model.js:579-588`, más render en `public/app.js`, `public/index.html` (y copias en `vercel-app/`). Genera "apuesta más segura", "doble oportunidad", "cuota justa = 1/prob", niveles de riesgo y mercados de goles. El README afirma "no está orientado a apuestas", pero el producto desplegado **sí** lo está. → **Eliminar** todo el bloque y su UI; sustituir por lectura analítica de incertidumbre (favorito, margen, sorpresa) sin lenguaje de mercado.

**C2 — Simulación de torneo no funcional.** Tres defectos acumulados:
1. **Nunca se invoca:** `run_monte_carlo` solo aparece en `simulation.py` y el README; ningún script lo llama (grep confirmado). Es código muerto.
2. **Faltan datos:** `simulation.py` espera un `schedule` con columnas `stage`, `group`, `home_slot`, `away_slot`, `match_id`, `order` y un `third_place_slot_map` oficial. **No existe ese dataset** en el repo. Los 72 partidos de grupos están en `results.csv` pero **sin etiqueta de grupo ni estructura de llave**, y los 32 partidos de eliminatorias no están.
3. **Conteo de rondas incompleto y mal etiquetado:** `simulation.py:206-211` solo cuenta `{quarterfinal, semifinal, final}` y mapea "ganar cuartos → semifinal", etc. **No cuenta octavos (R16) ni R32 de eliminatoria**, justo rondas que el deliverable exige. `advance_r32` mide clasificar de grupos, no avanzar en la llave.
4. **Reglas 2026 no implementadas correctamente:** `default_qualifiers` toma "8 mejores terceros" globalmente, pero **el formato 2026 fija qué 8 grupos de terceros van a qué slot de R32** mediante una tabla oficial; sin `third_place_slot_map` real, los cruces son arbitrarios. Tampoco hay desempates FIFA oficiales (ver A3).

**C3 — Calibración no entrenada / no reproducible.** `api/_model.js:13-26` define `temperature: 0.91`, `drawMultiplier: 0.96`, `poissonBlend: 0.03` como **constantes fijas a mano**. No hay módulo que las **ajuste** por validación temporal (isotónica / Platt / temperature scaling), y el lado **Python carece por completo de calibración**. La mejora reportada (log loss 0.998866 vs 0.999864) es ~0.1% y, por su origen manual, **no es reproducible** con un `fit`. Riesgo de overfitting a 3 Mundiales.

### 🟠 Altos

**A1 — El modelo desplegado no es el mejor de su propio backtest.** Por `reports/backtesting_summary.md`, `elo_features_live` (Elo actualizado dentro del torneo) logra log loss **0.9935**, claramente mejor que el desplegado `calibrated_elo_poisson_v2` (**0.9989**). El deploy usa el **estático pre-torneo**. Durante el Mundial (que ya empezó), debería operarse el Elo **actualizado tras cada partido**, que es justo el modo que el README llama "válido para operar durante el Mundial" pero que **no está cableado** en `/api/predict`.

**A2 — Dataset sin versionar / fuente móvil.** `/api/_model.js:108-128` y `data_collection.py` descargan `results.csv` en vivo desde `master` de GitHub, sin pin de commit ni hash. La composición del dataset puede cambiar entre ejecuciones → resultados **no reproducibles**. El README advierte del leakage de filas futuras y el código filtra por fecha (bien), pero no congela la **versión** del dato.

**A3 — Desempates de grupo no oficiales.** `simulation.py:114` ordena por `points, gd, gf, wins`. El reglamento FIFA 2026 usa: puntos → diferencia de goles → goles a favor → **enfrentamiento directo (pts/dg/gf entre empatados)** → fair-play → ranking FIFA. Faltan los criterios de enfrentamiento directo y fair-play; afecta qué terceros clasifican.

**A4 — Acoplamiento marcador↔resultado en la simulación de grupos.** `simulation.py:73-90`: primero muestrea el resultado 1×2, luego muestrea goles Poisson y **los fuerza** a concordar (`if outcome=="H" and home<=away: home=away+1`). Esto sesga la **diferencia de goles** (clave para desempates) hacia márgenes mínimos y mete doble fuente de aleatoriedad inconsistente. Lo correcto: muestrear el marcador de la **matriz Poisson/Dixon-Coles** y derivar el resultado de ahí (una sola fuente coherente).

**A5 — Penales/prórroga sin fuerza de equipo.** `simulation.py:179` llama `simulate_match(..., knockout=True)` **sin** pasar `penalty_strength`, así que todo empate en eliminatoria se resuelve **50/50** (default 1.0/1.0). La prórroga ni se modela. El encargo pide "prórroga o penales como mecanismo probabilístico separado".

### 🟡 Medios

**M1 — Sin pruebas unitarias.** No hay `tests/` ni pytest. `scripts/test-api.mjs` es solo un smoke test HTTP. El encargo exige tests de: cálculo de features, conversión de nombres, simulación de grupos, reglas de clasificación y "probabilidades que sumen 1".

**M2 — Sin archivo de configuración.** Constantes (K de Elo, ventaja local, half-life, blend, semilla, nº simulaciones, modelo activo, pesos de ensemble) están **dispersas y duplicadas** en Python y JS. El encargo pide YAML/JSON central.

**M3 — Duplicación del árbol de la app.** `api/`, `public/`, `static/` existen **dos veces** (raíz + `vercel-app/`). Cualquier corrección (p. ej. quitar apuestas) hay que hacerla en dos sitios → fuente de bugs y deriva.

**M4 — Dos implementaciones del modelo (Python vs JS) que pueden divergir.** El Elo/Poisson de `_model.js` reimplementa a mano la lógica de `src/`. No hay test de paridad que garantice que dan la misma probabilidad para el mismo input. Riesgo de que la web y el análisis "oficial" Python discrepen.

**M5 — Modelo de empate crudo.** El empate en Elo (`elo_model.py:62-63`) es una heurística de decaimiento con clip [0.08, 0.34], no un modelo ordenado (p. ej. Davidson o logit ordinal) ni calibrado contra tasa real de empates por diferencia de Elo. Es la pieza 1×2 más débil.

**M6 — `predict_match.py` no usa lo mejor disponible.** Usa Elo+Poisson crudos, sin la calibración v2 ni el bayesiano para incertidumbre. La CLI y la web dan números distintos para el mismo partido.

### 🟢 Bajos

- **B1 — Acentos faltantes en nombres** (`api/_teams_es.js`): "Haiti"→Haití, "Oman"→Omán, "Pakistan"→Pakistán, "Sudan"→Sudán, "Turkmenistan", "Uzbekistan", "Tayikistan". Cosmético.
- **B2 — `DR Congo`** está en el dataset y en `EXTRA_ALIASES` como destino, pero no en `TEAM_ES`, así que su display queda en inglés. Cosmético.
- **B3 — Importancia de torneo incompleta** (`preprocessing.py:12-24`): faltan CONMEBOL/UEFA Nations variantes, repechajes, etc.; caen al fallback genérico. Bajo impacto.
- **B4 — `goalscorers.csv`** se descarga (3,2 MB) pero no se usa. Limpieza.
- **B5 — `most_likely_score`** se reporta como "marcador más probable" pero es el **modo de la matriz independiente**, que casi siempre tira a marcadores bajos; conviene rotularlo como tal.

---

## 4. Chequeo explícito contra la lista de riesgos del encargo (Fase 1.4)

| Riesgo solicitado | Estado | Nota |
|---|---|---|
| Fuga de datos (leakage) | ✅ Mayormente controlado | Splits temporales con guardia (`preprocessing.py:120`); features walk-forward; filtro por fecha de corte. Único pendiente real: **versionar** el snapshot (A2). |
| Datos desactualizados | ⚠️ Parcial | Dataset vivo y actualizado, pero **sin pin de versión** ni ranking FIFA oficial cargado. |
| Mal manejo de nombres de selecciones | ✅ Bueno (ES/EN) con detalles | Mapeo ES/EN + alias robusto; solo acentos menores (B1/B2). |
| Features débiles | ⚠️ | Forma/Elo/descanso OK; faltan ranking FIFA, fuerza de plantel (cuando haya snapshot legal). Empate débil (M5). |
| Validación incorrecta | ✅ Correcta | Backtest temporal + por edición, sin overlap. Falta ampliar a Euro/Copa América (más muestra). |
| Sobreajuste | ⚠️ | ML regularizado y descartado si no vence baseline (bien). Riesgo real: **calibración manual** ajustada a 3 Mundiales (C3). |
| Falta de calibración | 🔴 | No hay calibración **entrenada**; solo constantes a mano en JS (C3). |
| Accuracy en vez de log loss/Brier/RPS | ✅ log loss/Brier/ECE; ❌ **RPS** | Métricas probabilísticas presentes salvo **Ranked Probability Score**, que el encargo pide explícitamente y es el más adecuado para 1×2 ordinal. |
| Simulación incompleta del torneo | 🔴 | No conectada, sin datos, conteo incompleto (C2). |
| Reglas Mundial 2026 mal implementadas | 🔴 | Sin grupos/llave oficiales, terceros sin mapa de slots, desempates incompletos (C2/A3). |

---

## 5. Lo que está bien (conservar)

- Núcleo **Elo recalculado internamente** con importancia y margen — robusto y barato.
- **Poisson con shrinkage + pesos por recencia + Dixon-Coles** — base correcta para goles y marcadores.
- **Backtesting temporal honesto** y principio "no aceptar complejidad sin mejora fuera de muestra".
- Métricas probabilísticas (log loss, Brier, ECE) bien implementadas.
- Manejo ES/EN de nombres y resolución difusa con sugerencias.
- Documentación de metodología y limitaciones ya presente.

Estos componentes **no deben reescribirse**; deben envolverse con config, tests, calibración entrenada y un simulador de torneo real.

---

## 6. Prioridad de remediación (entra al plan de implementación)

1. **(C1)** Eliminar toda la guía de apuestas (API + UI, ambas copias) y reemplazar por lectura de incertidumbre analítica.
2. **(C2)** Crear dataset oficial de **grupos + calendario + llave 2026** (snapshot fechado) e implementar/conectar un **Monte Carlo real** con reglas FIFA y conteo por ronda completo (R32→octavos→cuartos→SF→final→campeón).
3. **(C3 + RPS)** Añadir módulo `calibration.py` **entrenado** (isotónica/Platt/temperature) validado temporalmente, y añadir **RPS** a `evaluation.py`.
4. **(A1)** Cablear el modo Elo **actualizado durante el torneo** como modelo activo mientras el Mundial está en curso.
5. **(A2/M2/M3)** Versionar dataset (pin + hash), añadir **config YAML** central, y **deduplicar** el árbol de la app.
6. **(M1)** Añadir **pytest**: features, nombres, simulación de grupos, reglas de clasificación, suma de probabilidades = 1.
7. **(A3/A4/A5)** Corregir desempates de grupo, acoplamiento marcador↔resultado y prórroga/penales por fuerza.
8. **(M4/M5/M6 + B*)** Test de paridad Python↔JS, mejorar modelo de empate, unificar salida CLI/web, limpieza menor.

> **Regla de aceptación (del propio proyecto y del encargo):** ninguna mejora reemplaza al modelo actual salvo que **mejore log loss / Brier / RPS / calibración** en validación temporal. Si no mejora, se documenta y se conserva el modelo previo.

---

## 7. Reproducibilidad de esta auditoría

- Sin venv presente; Python 3.13.5 y Node 24.16 disponibles en la máquina.
- Cifras de backtest citadas provienen de `reports/*.md` y `api/_model.js` (no re-ejecutadas aún). **Acción pendiente en Fase 4:** reconstruir el venv y **re-correr `run_backtest.py`** para confirmar que las métricas publicadas son reproducibles con el snapshot versionado.
