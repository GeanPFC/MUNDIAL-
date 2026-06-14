# ARCHITECTURE_V3.md — Rediseño del sistema (Fase 3)

Fecha: 2026-06-13
Estado: **diseño aprobado pendiente** → no se ha modificado código de modelo todavía.
Base: hallazgos de [MODEL_AUDIT.md](MODEL_AUDIT.md) + conclusiones de [RESEARCH_2026_WORLD_CUP_MODELS.md](RESEARCH_2026_WORLD_CUP_MODELS.md).

Principio rector (heredado del proyecto y del encargo): **se conserva el núcleo Elo + Poisson/Dixon-Coles** porque ya valida; todo lo nuevo se acepta **solo si mejora log loss / Brier / RPS / calibración** en validación temporal. Nada se reescribe "porque parece sofisticado".

---

## 0. Visión general

```
                 ┌─────────────────────────────────────────────────────────┐
                 │                     config.yaml                          │
                 │  fuentes · fecha_corte · n_sims · modelo_activo ·        │
                 │  pesos_ensemble · semilla · half_life · params Elo       │
                 └─────────────────────────────────────────────────────────┘
                                          │
   data_ingestion ──► feature_engineering ──► model_training ──► calibration
        │                                          │                  │
   snapshots fechados                         Elo / Poisson /         temperature /
   + hash SHA-256                             Bayes / ML / ensemble   Platt / isotónica
        │                                          │                  │
        ▼                                          ▼                  ▼
   wc2026_groups.csv                         predict_match()    probs calibradas
   wc2026_schedule.csv  ───────────────────►  ┌───────────────────────────────┐
   wc2026_bracket.csv                         │   tournament_simulation        │
   third_place_table.csv                      │   Monte Carlo 50k–100k         │
        │                                      │   (condicional a resultados)   │
        ▼                                      └───────────────────────────────┘
   evaluation (log loss, Brier, RPS, ECE,                 │
   reliability curves, baselines)                          ▼
        │                                            reporting
        └───────────────────────────────────────►  por partido / grupo / torneo
```

**Cambio conceptual central:** pasar de "predictor de partido" a "**predictor de partido + simulador de torneo condicional**". El simulador respeta los resultados ya jugados (el Mundial está en curso) y solo simula lo pendiente → probabilidades **condicionadas al estado real** del torneo.

---

## 1. Mapeo a los módulos pedidos (Fase 5) sin romper la interfaz

El encargo pide módulos `data_ingestion, feature_engineering, model_training, calibration, tournament_simulation, evaluation, reporting`. Para **no romper imports existentes** (`src.elo_model`, `src.poisson_model`, etc.), se conservan los nombres actuales y se **añaden** los nuevos. Mapeo lógico:

| Rol pedido | Módulo(s) en el repo | Acción |
|---|---|---|
| data_ingestion | `src/data_collection.py` + **nuevo** `src/data_sources_2026.py` | Añadir carga/validación de grupos, calendario, bracket, tabla de terceros + hash de snapshot |
| feature_engineering | `src/features.py`, `src/preprocessing.py` | Conservar; añadir feature opcional de ranking FIFA y confederación |
| model_training | `src/elo_model.py`, `src/poisson_model.py`, `src/bayesian_model.py`, `src/ml_model.py`, `src/ensemble.py` | Conservar; pequeños ajustes (Elo live, etiqueta de marcador modal) |
| **calibration** | **nuevo** `src/calibration.py` | Temperature / Platt / isotónica **entrenadas** + multiclase |
| tournament_simulation | **reescribir** `src/simulation.py` (o nuevo `src/tournament.py`) | Monte Carlo real con reglas FIFA 2026 |
| evaluation | `src/evaluation.py` | Añadir **RPS** + curvas de fiabilidad + baseline ranking FIFA |
| reporting | **nuevo** `src/reporting.py` + `run_tournament.py` | Salidas por partido/grupo/torneo + explicabilidad |
| config | **nuevo** `config.yaml` + `src/config.py` | Carga central de parámetros |

Scripts de entrada (interfaz pública, se mantienen): `predict_match.py`, `run_backtest.py`, **nuevo** `run_tournament.py`. API JS: se limpia (quitar apuestas) y se documenta como espejo del modelo Python.

---

## 2. Capa de datos (`data_ingestion`)

### 2.1 Histórico (existente, a versionar)
- Fuente: `martj42/international_results` → `results.csv`, `shootouts.csv`.
- **Reproducibilidad:** al descargar, escribir en `source_manifest.json` el **SHA-256** de cada archivo, la **fecha de corte** y, si la API de GitHub lo da, el **commit/ETag** de origen. Guardar copia inmutable en `data/snapshots/results_YYYYMMDD.csv`.

### 2.2 Datos oficiales del Mundial 2026 (nuevos, fechados)
Construidos desde las fuentes de la investigación (§1 de RESEARCH), verificados contra `results.csv`.

**`data/raw/wc2026_groups.csv`** — 48 filas
```
group,team,team_dataset,pot,confederation,is_host
A,Mexico,Mexico,1,CONCACAF,1
A,South Korea,South Korea,2,AFC,0
A,South Africa,South Africa,3,CAF,0
A,Czechia,Czech Republic,4,UEFA,0
...
```
`team_dataset` = nombre tal cual aparece en `results.csv` (para empatar nombres sin ambigüedad).

**`data/raw/wc2026_schedule.csv`** — 72 partidos de grupos (+ se rellenan resultados a medida que se juegan)
```
match_id,stage,group,date,venue,home_team,away_team,neutral,home_score,away_score,status
G01,group,A,2026-06-11,Mexico City,Mexico,South Africa,0,2,0,played
...
G72,group,L,2026-06-27,...,...,...,1,,,scheduled
```
`status ∈ {played, scheduled}`. `neutral`: 0 solo para el anfitrión local en su país; 1 en el resto.

**`data/raw/wc2026_bracket.csv`** — 32 partidos de eliminatoria (slots simbólicos)
```
match_id,stage,order,home_slot,away_slot
R32_M73,round_of_32,1,2A,2B
R32_M74,round_of_32,2,1C,2F
R32_M75,round_of_32,3,1E,3_ABCDF
...
R16_M89,round_of_16,17,W73,W74
...
QF_M101,quarterfinal,...,W..,W..
SF_M103,semifinal,...,W..,W..
F_M104,final,...,W..,W..
```
Slots: `1X`/`2X` = 1.º/2.º del grupo X; `3_ABCDF` = tercero proveniente de uno de esos grupos; `Wnn` = ganador del match nn.

**`data/raw/wc2026_third_place_allocation.csv`** — asignación de terceros
- Cada uno de los **8 slots de tercero** del R32 tiene un **conjunto de grupos permitidos** (de la malla oficial, §1 RESEARCH):
  - `3_ABCDF`, `3_CDFGH`, `3_CEFHI`, `3_EHIJK`, `3_AEHIJ`, `3_BEFIJ`, `3_EFGIJ`, `3_DEIJL`.
- Resolución en simulación: dado el conjunto de 8 grupos cuyos terceros clasifican, se asigna cada tercero a un slot respetando los conjuntos permitidos mediante **emparejamiento bipartito factible** (sin reutilizar grupo).
  - **Nota de fidelidad:** FIFA publica una tabla determinista (≈495 combinaciones, estilo "Annex"). El emparejamiento factible respeta las **mismas restricciones estructurales** (ningún equipo enfrenta a su grupo; terceros vs primeros) y es una aproximación documentada. Si se consigue la tabla oficial completa, se cargará aquí sin cambiar el resto del código. *(Riesgo: en casos límite el cruce exacto puede diferir; impacto pequeño en probabilidades agregadas de avance.)*

### 2.3 Opcionales (solo si hay snapshot legal y fechado)
- `data/raw/fifa_ranking_YYYYMMDD.csv` (orden + puntos oficiales) → feature/baseline.
- No se integran lesiones/alineaciones/valor de plantel salvo fuente trazable (se mantiene la regla del repo).

---

## 3. Feature engineering (existente + extensiones menores)

Se conserva `make_supervised_matches` (Elo walk-forward + forma rodante + descanso, todo sin leakage). Extensiones **candidatas** (entran solo si mejoran backtest):
- `fifa_rank_home/away`, `fifa_rank_diff` (desde snapshot fechado).
- `same_confederation` (de `wc2026_groups`/tabla de confederaciones).
- `match_importance`, `stage` ya disponibles vía torneo.
- `is_host` y `host_country_match` (localía real en 2026).

Regla intacta: variable externa entra solo con snapshot fechado, cobertura suficiente y mejora de log loss/Brier/RPS.

---

## 4. Modelo de partido (1×2) — `model_training` + `calibration`

**Núcleo:** Elo (validado como mejor 1×2). Dos modos:
- `elo_pre_tournament`: ratings congelados antes del torneo (baseline reproducible).
- `elo_live`: ratings **actualizados cronológicamente tras cada resultado real** → **modelo activo durante el Mundial** (mejor en backtest, A1). El simulador y `/api/predict` usarán este modo cuando el corte está dentro del torneo.

**Capa de calibración (`src/calibration.py`, nueva):**
- `TemperatureScaling`: un parámetro T; `p_cal ∝ p^(1/T)`; se **ajusta** minimizando log loss en validación.
- `PlattMulticlass` / `IsotonicPerClass`: opciones alternativas.
- **Entrenamiento honesto:** se ajusta en ediciones **anteriores** al test (p. ej. T aprendido en 2014/2018, evaluado en 2022) — nunca en la misma edición evaluada.
- Sustituye las constantes `temperature: 0.91`/`drawMultiplier: 0.96` del JS por valores **derivados** y versionados en `config.yaml`.
- **Modelo de empate (M5):** opción de reemplazar la heurística de decaimiento por una calibración del empate vs |ΔElo| ajustada en datos (manteniendo el clip como salvaguarda). Se adopta solo si baja log loss/Brier.

**Ensemble:** se mantiene `ensemble.py` con guardia "debe vencer baseline". El ensemble Elo+Poisson+Bayes(+ML) se **despliega solo si** mejora fuera de muestra (hoy no lo hace → núcleo Elo).

---

## 5. Modelo de goles — `poisson_model.py` (existente, afinado)

Produce por partido: `λA, λB`, **matriz de marcadores** Poisson/Dixon-Coles, P(victoria/empate/derrota), **top-5 marcadores**, intervalos de goles, over/under. Ajustes:
- Activar **Dixon-Coles con ρ ajustado por grid** (hoy desactivado en la corrida rápida) si mejora el log loss de marcador exacto.
- Rebautizar la salida `most_likely_score` como "marcador modal de la matriz" (es modo de la conjunta independiente; tiende a marcadores bajos — B5).
- El modelo de goles es la **fuente única** de marcador en la simulación (resuelve A4: no muestrear 1×2 y goles por separado).

---

## 6. Modelo de torneo — `tournament_simulation` (reescritura, núcleo de la Fase 4)

**Entradas:** `wc2026_groups`, `wc2026_schedule` (con resultados jugados), `wc2026_bracket`, tabla de terceros, predictor de partido (Elo live + goles), `n_sims`, `seed`, `as_of`.

**Algoritmo por simulación:**
1. **Fase de grupos.** Para cada partido:
   - si `status == played` → usar marcador real (fijo, no se simula);
   - si no → muestrear marcador de la **matriz de goles** (una sola fuente) → derivar puntos/dg/gf.
2. **Tablas con desempates oficiales FIFA** (§1 RESEARCH): puntos → dg → gf → **enfrentamiento directo** → fair-play (placeholder neutral si no hay datos de tarjetas) → sorteo (aleatorio reproducible). Registrar posición 1.º/2.º/3.º/4.º de cada equipo.
3. **Clasificados:** 2 primeros por grupo + **8 mejores terceros** (mismo orden de criterios entre los 12 terceros).
4. **Asignación de terceros** a los 8 slots del R32 por emparejamiento factible (tabla de §2.2).
5. **Eliminatorias:** resolver R32→R16→cuartos→semis→final con el predictor.
   - Empate en eliminatoria → **prórroga/penales como mecanismo separado** ponderado por **fuerza** (Elo) en vez de 50/50 (resuelve A5). Probabilidad de ganar en penales modelada como función suave de ΔElo (no determinista).
6. **Conteo por equipo y por ronda:** posición de grupo (1/2/3/4), **clasifica (sí/no)**, **llega a** R32 / R16 (octavos) / cuartos / semis / final / **campeón**. (Resuelve C2: conteo completo y bien etiquetado.)

**Salidas agregadas (sobre `n_sims`):** para cada equipo, probabilidad de cada hito; para cada grupo, distribución de posiciones y prob. de clasificar.

**Rendimiento:** vectorizar el muestreo de marcadores; objetivo 50k sims en minutos en una laptop, 100k si el tiempo lo permite. Semilla fija → reproducible.

**Condicionalidad:** como hay partidos ya jugados, las salidas son **probabilidades condicionadas al estado actual** del torneo (se recalculan tras cada jornada → cumple "actualización después de cada resultado real").

---

## 7. Evaluación — `evaluation.py` (extensión)

Se añade:
- **RPS (Ranked Probability Score)** multiclase ordinal (L>E>V), reportado **junto** a log loss y Brier (no en su lugar; hay debate académico).
- **Curvas de fiabilidad / diagramas de calibración** por clase (además del ECE ya existente).
- **Baseline explícito de ranking FIFA** (prob. derivada de diferencia de ranking) sumado a los baselines actuales (tasas, Elo, Poisson).
- Backtest ampliable a Eurocopa/Copa América/eliminatorias (más muestra) — opcional.

**Criterio de aceptación (gate):** el modelo nuevo/calibrado reemplaza al actual **solo si** mejora log loss **o** Brier **o** RPS **o** calibración (ECE) en validación temporal, sin degradar materialmente las demás. Si no, se conserva el anterior y se documenta en `CHANGELOG_MODEL_IMPROVEMENTS.md` por qué.

---

## 8. Reporting — `reporting.py` + `run_tournament.py` (nuevo)

**Por partido:** A vs B → P(victoria A/empate/victoria B), xG A/B, top-5 marcadores, intervalos, incertidumbre, variables influyentes, **aviso de incertidumbre** (no certezas). Sin lenguaje de apuestas.

**Por grupo:** tabla con P(1.º), P(2.º), P(3.º), P(4.º) y **P(clasificar)** por equipo.

**Por torneo:** por equipo, P(R32), P(octavos), P(cuartos), P(semi), P(final), P(campeón), ordenado por P(campeón).

**Explicabilidad:** variables más importantes (Elo diff, forma, ataque/defensa, localía), por qué el modelo favorece a un equipo, nivel de incertidumbre, y advertencia explícita de varianza del fútbol.

**Formatos:** CSV en `reports/` + resumen Markdown. La web (`/api`) consume el mismo modelo Python o su espejo JS (con **test de paridad**, M4).

---

## 9. Configuración (`config.yaml` + `src/config.py`, nuevos)

```yaml
data:
  results_csv: data/raw/results.csv
  snapshot_dir: data/snapshots
  wc2026_groups: data/raw/wc2026_groups.csv
  wc2026_schedule: data/raw/wc2026_schedule.csv
  wc2026_bracket: data/raw/wc2026_bracket.csv
  third_place_table: data/raw/wc2026_third_place_allocation.csv
  pin_sha256: true
model:
  active: elo_live            # elo_pre_tournament | elo_live | ensemble
  cutoff_date: 2026-06-13
  elo: {k_factor: 20, home_advantage: 60, importance_scale: 0.25}
  poisson: {prior_matches: 8, fit_dixon_coles: true, half_life_days: 1095}
  ensemble_weights: {elo: 1.0, poisson: 0.0, bayes: 0.0, ml: 0.0}
calibration:
  method: temperature         # none | temperature | platt | isotonic
  fit_on: [2014, 2018]
  evaluate_on: [2022]
simulation:
  n_simulations: 50000
  random_seed: 2026
  extra_time_penalty_model: elo_weighted
evaluation:
  metrics: [log_loss, brier, rps, ece]
  baselines: [baseline_rates, elo_features, poisson_simple, fifa_ranking]
```

---

## 10. Pruebas (`tests/`, pytest, Fase 5)

- `test_features.py` — features sin leakage; valores walk-forward correctos.
- `test_team_names.py` — conversión ES↔EN y alias (Catar→Qatar, Chequia→Czech Republic, RD Congo→DR Congo…).
- `test_group_simulation.py` — una tabla de grupo con resultados conocidos produce el orden esperado.
- `test_qualification_rules.py` — 2 primeros + 8 mejores terceros + desempates oficiales.
- `test_probabilities.py` — toda predicción 1×2 suma 1 (±1e-9) y ∈ [0,1]; matriz de goles suma 1.
- `test_bracket.py` — asignación de terceros respeta conjuntos permitidos y no repite grupo.
- `test_parity_py_js.py` (opcional) — Elo/Poisson Python vs JS coinciden para inputs fijos.

---

## 11. Orden de implementación propuesto (Fases 4–5)

| Paso | Entregable | Cubre |
|---|---|---|
| 4.1 | `config.yaml` + `src/config.py` | M2 |
| 4.2 | Snapshots oficiales 2026 + `data_sources_2026.py` + hash | C2(datos), A2 |
| 4.3 | `src/calibration.py` + RPS y curvas en `evaluation.py` | C3, RPS |
| 4.4 | Reescritura `tournament_simulation` + `run_tournament.py` | C2, A3, A4, A5 |
| 4.5 | `reporting.py` (partido/grupo/torneo) | Fase 6 |
| 5.1 | `tests/` pytest | M1 |
| 5.2 | Quitar apuestas (API+UI, ambas copias) + dedupe | C1, M3 |
| 5.3 | Elo live como activo + paridad Py/JS + limpieza menor | A1, M4, M6, B* |
| — | Backtest antes/después + `CHANGELOG_MODEL_IMPROVEMENTS.md` | Fase 4/7 |

Cada paso: implementar → validar (gate de métricas) → documentar. Ninguna mejora se mantiene si no supera al modelo previo en validación temporal.

---

## 12. Lo que NO cambia (compromisos de seguridad)

- No se inventan datos; los huecos (lesiones, plantel, clima) quedan fuera salvo snapshot trazable.
- No se usan datos futuros para entrenar (filtro por fecha de corte + walk-forward).
- No se usan casas de apuestas ni se optimiza para apostar; se **elimina** la guía de apuestas existente.
- Reproducibilidad: snapshot + hash + semilla + config versionada.
- No se promete exactitud; toda salida lleva aviso de incertidumbre.
```
