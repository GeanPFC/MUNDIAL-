# CHANGELOG_MODEL_IMPROVEMENTS.md

Registro de cambios del rediseño. Cada entrada indica QUÉ cambió, POR QUÉ y cómo se VALIDÓ.
Principio: una mejora se conserva solo si supera al modelo previo en validación temporal
(log loss / Brier / RPS / ECE). Si no, se documenta y se descarta.

---

## [Fase 4] 2026-06-13 — Infraestructura, calibración, RPS y simulador de torneo

### Añadido
- **`config.yaml` + `src/config.py`** — configuración central reproducible (fuentes,
  fecha de corte, nº de simulaciones, modelo activo, pesos de ensemble, semilla, params
  Elo/Poisson). Resuelve el hallazgo **M2** (constantes dispersas).
- **Datos oficiales 2026 versionados** (`src/data_sources_2026.py`):
  - `data/raw/wc2026_groups.csv` — 12 grupos × 4 (sorteo FIFA 05-dic-2025).
  - `data/raw/wc2026_schedule.csv` — 72 partidos de grupos derivados de `results.csv`
    con etiqueta de grupo y estado jugado/pendiente.
  - `data/raw/wc2026_bracket.csv` — malla completa de eliminatorias (R32→final, matches 73–104).
  - `data/raw/wc2026_third_place_allocation.csv` — slots de terceros con grupos permitidos.
  - Hash **SHA-256** de cada archivo en `source_manifest.json`. Resuelve **A2** (versionado).
  - **Verificación:** los 48 nombres de equipo empatan con `results.csv` (0 faltantes); los
    grupos coinciden con los fixtures ya jugados. Cubre la falta de datos de **C2**.
- **`src/calibration.py`** — calibración **entrenada** (TemperatureScaling, IsotonicPerClass),
  reemplazando las constantes a mano (`temperature: 0.91`) del modelo desplegado. Resuelve **C3**.
- **RPS y curvas de fiabilidad en `src/evaluation.py`** — `ranked_probability_score`,
  `reliability_table`; RPS añadido a `evaluate_probabilities`. Cubre la métrica ordinal
  que faltaba (lista de riesgos del encargo).
- **`src/tournament.py`** — simulador Monte Carlo nuevo y funcional (reemplaza a
  `simulation.py`, que estaba sin conectar y con conteo incompleto). Resuelve **C2, A3, A4, A5**:
  - condicional a resultados ya jugados;
  - marcador coherente muestreado de la matriz de goles, condicionado al 1X2 de Elo (una sola
    fuente; elimina el hack de "forzar goles a concordar" — **A4**);
  - desempates oficiales FIFA con enfrentamiento directo + sorteo reproducible (**A3**);
  - 2 primeros + 8 mejores terceros; asignación a la llave por emparejamiento factible;
  - prórroga/penales ponderados por Elo, no 50/50 (**A5**);
  - conteo completo por ronda: R32→octavos→cuartos→semis→final→campeón.
- **`src/reporting.py` + `run_tournament.py`** — salidas por partido, grupo y torneo, con
  explicabilidad y aviso de incertidumbre, sin lenguaje de apuestas. Cubre la Fase 6 del encargo.

### Cambiado
- **`run_backtest.py`** — ahora reporta **RPS** y ejecuta un experimento de **calibración
  honesta** (aprende T en 2014/2018, evalúa en 2022). Usa `config.yaml`.

### Decisiones basadas en evidencia (gate de aceptación)
- **Calibración por temperatura: NO se adopta.** T=0.83 aprendida en 2014/2018 **empeora**
  2022 en todas las métricas (log loss 1.0368→1.0504, Brier 0.6103→0.6138, RPS 0.2173→0.2188,
  ECE 0.0701→0.0841). El Elo live ya está razonablemente calibrado (ECE 2022 ≈ 0.07). Confirma
  empíricamente que la calibración a mano del deploy no estaba justificada. → `calibration.method: none`.
  Evidencia: `reports/calibration_experiment.csv`.
- **Dixon-Coles: NO se adopta por defecto.** El backtest del repo ya mostró que DC fijo no
  mejora el 1X2 (1.0514 vs 1.0445) y su ajuste de ρ recorre todo el histórico (lento). → Poisson
  simple para el torneo. Reactivable en config para experimentar.
- **Modelo activo: `elo_live`** (Elo actualizado con todos los resultados hasta el corte,
  incluidos los del Mundial). Es el mejor en backtest (log loss 0.9935 vs 1.0008 del estático).
  Resuelve **A1**.

### Métricas de validación (Mundiales 2014/2018/2022, promedio)
| Modelo | Log loss | Brier | RPS | Accuracy | ECE |
|---|---:|---:|---:|---:|---:|
| **elo_features_live** | **0.9935** | **0.5898** | **0.2110** | 0.547 | 0.093 |
| elo_static_pre_tournament | 1.0008 | 0.5957 | 0.2137 | 0.552 | 0.111 |
| ml_hist_gradient_boosting | 1.0044 | 0.5984 | 0.2141 | 0.547 | 0.105 |
| bayesian_gamma_poisson | 1.0554 | 0.6369 | 0.2324 | 0.490 | 0.112 |
| poisson_simple | 1.0563 | 0.6375 | 0.2326 | 0.490 | 0.112 |
| baseline_rates | 1.0736 | 0.6516 | 0.2416 | 0.427 | 0.054 |

El núcleo Elo live vence a todos los baselines en log loss, Brier y RPS → se conserva como modelo activo.

---

## [Fase 5] 2026-06-13 — Limpieza, MLOps y consistencia producción

### Eliminado (C1 — mandato del usuario: el objetivo NO es apostar)
- **Guía de apuestas removida** de `api/_model.js` (función `buildBettingGuidance` y
  `poissonTotalGoalsProbability`, solo usadas para apuestas) y de la UI (`public/app.js`,
  `public/index.html`, `public/styles.css`). Reemplazada por una **lectura analítica del
  partido** (`buildMatchReading`: favorito, equilibrio, goles) sin "cuota", "apuesta",
  "doble oportunidad" ni niveles de riesgo de mercado. Aplicado en **ambas copias** (raíz y `vercel-app/`).

### Cambiado
- **Modelo desplegado alineado con la evidencia (A1):** el JS pasa de
  `calibrated_elo_poisson_v2` (temperatura 0.91 + 3% Poisson, a mano) a **`elo_live_v3`**
  (Elo live crudo, sin calibración ad-hoc). Los factores de calibración quedan en identidad.
  `BACKTEST_SUMMARY` y `model_decision` actualizados; RPS añadido al resumen.
- **Acentos de nombres (B1/B2):** Haití, Omán, Pakistán, Sudán, Taiwán, Tahití, Tayikistán,
  Turkmenistán, Uzbekistán; añadido display "DR Congo" → "RD Congo". En ambas copias.
- **`src/simulation.py` marcado como DEPRECADO** (emite `DeprecationWarning`); reemplazado por
  `src/tournament.py`. Se conserva por compatibilidad.

### Añadido (pruebas — M1/M4)
- `tests/test_model_system.py` — **12 pruebas pytest** (suma de probabilidades = 1, 32
  clasificados, monotonía por ronda, asignación de terceros, propiedad ordinal del RPS,
  nombres que empatan). **12/12 pasan.**
- `scripts/test-team-names.mjs` — conversión ES↔EN y alias (17 casos, todos pasan).
- `scripts/parity_check.py` — **paridad Python↔JS**: las probabilidades 1X2 difieren ≤0.005 y
  xG ≤0.05 entre ambas implementaciones (dentro de tolerancia en todos los casos).

### Decisión de deduplicación (M3) — documentada, no destructiva
- Los `.vercel/project.json` revelan **dos proyectos Vercel distintos** (`worldcup-2026-predictor`
  en la raíz y `vercel-app` en `vercel-app/`), no una simple duplicación de archivos. Como el
  repo **no tiene git** (borrado irreversible) y ambos pueden estar desplegados, **no se eliminó**
  ningún árbol. Se mantuvieron ambas copias idénticas y sincronizadas. Recomendación: consolidar a
  un único proyecto desde el dashboard de Vercel y luego borrar la copia sobrante.

### Pendiente (próximos pasos, fuera de alcance inmediato)
- Consolidar definitivamente el árbol Vercel tras decidir el proyecto canónico.
- Ampliar backtest a Eurocopa/Copa América/eliminatorias (más muestra).
- Cargar la tabla oficial de asignación de terceros (≈495 combinaciones) si se obtiene.

---

## [Calibración en vivo] 2026-06-13 — Validación de la probabilidad de victoria

### Añadido
- **`src/live_calibration.py` + `run_live_calibration.py`** — seguimiento de calibración
  de la probabilidad de victoria, walk-forward sin leakage. Responde: "cuando el modelo
  dice X% de ganar, ¿gana ~X% de las veces?". Dos vistas: Mundial 2026 en vivo (se acumula
  por jornada) y referencia sobre partidos recientes (muestra grande).
- Salidas: `reports/live_calibration_report.md`, `reports/live_calibration_wc2026.csv`,
  `reports/calibration_curve_reference.png`.

### Resultado de validación
- Sobre **2.038 partidos internacionales** (últimos 24 meses), la probabilidad de victoria
  está **bien calibrada**: ECE de victoria **0.026** (~2.6 pp de error medio); la frecuencia
  real sigue de cerca a la predicha en todo el rango.
- Diagnóstico: leve sobreconfianza en probabilidades bajas (0.1–0.3) y leve conservadurismo
  en altas (>0.8). Como una sola temperatura no corrige ambos extremos, **explica por qué la
  calibración por temperatura no mejoró** en el backtest.

---

## [Torneo en la web] 2026-06-13 — Probabilidades del torneo desplegadas en Vercel

### Añadido
- **`build_tournament_snapshot.py`** — corre el Monte Carlo y exporta `public/tournament_snapshot.json`
  (campeón, rondas y grupos) a las dos copias de la web. La simulación es Python pesado (~minutos),
  no cabe en serverless → patrón de snapshot estático, regenerado y redesplegado por jornada.
- **`public/tournament.html`** — página web autocontenida que lee el JSON y muestra la tabla de
  campeón/rondas y las probabilidades de clasificar por grupo. Enlazada desde el predictor.
- Despliegue verificado en producción (https://vercel-app-henna-psi.vercel.app/tournament.html).

### Estado de "todo en la nube"
- En la nube (Vercel): predictor por partido (recalcula en vivo) + probabilidades del torneo (snapshot).
- Sigue local: la *generación* del snapshot (simulación) y la calibración en vivo (herramientas Python).
- Pendiente de seguridad: el código aún **no está en git/GitHub** (solo en el PC + snapshot de Vercel).
