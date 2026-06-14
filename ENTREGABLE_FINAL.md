# ENTREGABLE_FINAL.md — Mundial 2026: rediseño del sistema de predicción

Fecha: 2026-06-13 · Modelo activo: `elo_live_v3` · Objetivo: análisis deportivo serio, explicable y reproducible. **No orientado a apuestas.**

Documentos de respaldo: [MODEL_AUDIT.md](MODEL_AUDIT.md) · [RESEARCH_2026_WORLD_CUP_MODELS.md](RESEARCH_2026_WORLD_CUP_MODELS.md) · [ARCHITECTURE_V3.md](ARCHITECTURE_V3.md) · [CHANGELOG_MODEL_IMPROVEMENTS.md](CHANGELOG_MODEL_IMPROVEMENTS.md)

---

## 1. Resumen ejecutivo: qué estaba mal o débil en el modelo original

El proyecto partía de una **base estadística sólida** (Elo interno, Poisson con shrinkage, Dixon-Coles, bayesiano, backtesting temporal honesto y métricas probabilísticas). Pero tenía tres problemas de alto impacto que contradecían el objetivo o dejaban deliverables sin funcionar:

| Sev. | Problema | Estado tras el rediseño |
|---|---|---|
| 🔴 C1 | El modelo **en producción generaba guía de apuestas** ("apuesta más segura", "cuota justa", doble oportunidad, riesgo) pese a declarar que no era para apuestas. | **Eliminado.** Reemplazado por lectura analítica. |
| 🔴 C2 | La **simulación del torneo no funcionaba**: código muerto, sin datos de grupos/llave 2026, conteo de rondas incompleto. No producía probabilidad de campeón, semis, grupos. | **Reescrita y funcional** (`src/tournament.py`). |
| 🟠 C3 | La "calibración" eran **constantes a mano** (`temperature 0.91`) sin ajuste ni validación; el lado Python no calibraba. | **Calibración entrenada** implementada, **evaluada y descartada** por no generalizar. |

Problemas secundarios resueltos o documentados: el modelo desplegado **no era el mejor de su propio backtest** (A1), **falta de RPS** (métrica ordinal pedida), **dataset sin versionar** (A2), desempates de grupo incompletos (A3), acoplamiento marcador↔resultado en la simulación (A4), penales 50/50 sin fuerza (A5), **cero tests** (M1), **sin config central** (M2), **árbol duplicado** (M3), riesgo de divergencia Python/JS (M4).

---

## 2. Qué se investigó y qué se aprendió (fuentes oficiales/académicas, sin casas de apuestas)

- **Formato oficial 2026** (FIFA, Wikipedia, ESPN): 48 equipos, 12 grupos, 2 primeros + 8 mejores terceros, R32→octavos→cuartos→semis→final, 104 partidos, 11 jun–19 jul. Obtuve los **12 grupos completos**, la **malla fija del R32** (con grupos permitidos por slot de tercero) y los **desempates oficiales** (incluyen enfrentamiento directo y fair-play). Los grupos **coinciden** con los fixtures ya cargados en `results.csv`.
- **Rankings/fuerza** (FIFA ranking jun-2026; World Football Elo; Lasek et al. 2013): los sistemas tipo Elo igualan o superan al ranking FIFA como predictores → confirma usar Elo interno como núcleo.
- **Modelos** (Groll et al.; Gilch & Müller 2018; Dixon-Coles 1997; Karlis & Ntzoufras 2003): el patrón de referencia para mundiales es **Poisson/Elo por partido → Monte Carlo del torneo**, justo lo que faltaba aquí. El ML rara vez supera a un Elo bien calibrado con datos públicos.
- **Evaluación** (Constantinou & Fenton; debate Wheatcroft): el **RPS** es la regla ordinal adecuada para fútbol (sensible a la distancia L>E>V); se reporta junto a log loss y Brier.

Detalle y enlaces con fecha de consulta en [RESEARCH_2026_WORLD_CUP_MODELS.md](RESEARCH_2026_WORLD_CUP_MODELS.md).

---

## 3. Qué mejoras se implementaron

**Datos y reproducibilidad**
- `config.yaml` + `src/config.py`: configuración central (fuentes, corte, nº sims, modelo activo, semilla, params).
- Snapshots oficiales 2026 (`wc2026_groups/schedule/bracket/third_place`) con **hash SHA-256** en el manifest; 48 nombres validados contra `results.csv`.

**Modelo y métricas**
- **Elo live** como modelo activo (mejor en backtest).
- `src/calibration.py`: temperature/isotónica **entrenadas** (evaluadas honestamente).
- **RPS** + curvas de fiabilidad en `src/evaluation.py`.

**Simulación del torneo** (`src/tournament.py`, nuevo)
- Monte Carlo 50k–100k condicional a resultados jugados; marcador coherente desde la matriz de goles; desempates FIFA con enfrentamiento directo; 8 mejores terceros + asignación a la llave; prórroga/penales ponderados por Elo; conteo completo por ronda.

**Salidas y limpieza**
- `src/reporting.py` + `run_tournament.py`: reportes por partido/grupo/torneo, sin lenguaje de apuestas.
- Guía de apuestas eliminada (API+UI); acentos de nombres; `simulation.py` deprecado.
- Pruebas: `tests/` (pytest), `scripts/test-team-names.mjs`, `scripts/parity_check.py`.

**Decisiones basadas en evidencia (se probaron y NO se adoptaron):**
- Calibración por temperatura → **descartada** (no generaliza a 2022).
- Dixon-Coles → **descartado** (no mejora el 1X2 y es lento).
- Ensemble agresivo → **descartado** (no supera a Elo).

> Esto es el principio del encargo en acción: implementado ≠ mantenido. Solo sobrevive lo que mejora en validación temporal.

---

## 4. Métricas antes vs después

**Backtest 1X2 (Mundiales 2014/2018/2022, validación temporal, promedio):**

| Modelo | Log loss | Brier | RPS | ECE |
|---|---:|---:|---:|---:|
| Original desplegado (`calibrated_elo_poisson_v2`) | 0.9989 | 0.5945 | n/d (no se medía) | 0.0613 |
| **Nuevo activo (`elo_live_v3`)** | **0.9935** | **0.5898** | **0.2110** | 0.0925 |
| Mejor baseline (tasas históricas) | 1.0736 | 0.6516 | 0.2416 | 0.0541 |

El nuevo activo mejora log loss, Brier y aporta **RPS** (antes inexistente). La calibración por temperatura se probó y empeoró 2022 (log loss 1.0368→1.0504), por eso **no se adoptó**.

**Capacidad de torneo: antes = 0 (no funcionaba). Después = simulación completa.**
Salida ejemplo (50.000 sims, condicional al 2026-06-13):

| Equipo | Campeón | Final | Semis | Cuartos | Octavos | R32 |
|---|---:|---:|---:|---:|---:|---:|
| España | 21.8% | 33.0% | 45.8% | 56.6% | 75.6% | 99.4% |
| Argentina | 20.3% | 31.5% | 44.2% | 58.7% | 71.7% | 98.1% |
| Francia | 10.7% | 19.2% | 34.8% | 52.0% | 75.5% | 96.0% |
| Brasil | 7.2% | 14.0% | 27.3% | 44.2% | 65.0% | 96.5% |
| Inglaterra | 5.9% | 12.0% | 23.6% | 40.8% | 65.9% | 96.6% |

Reportes completos: `reports/wc2026_predictions.md`, `reports/wc2026_group_probabilities.csv`, `reports/wc2026_tournament_probabilities.csv`.

**Pruebas:** pytest 12/12 · nombres 17/17 · paridad Python↔JS dentro de tolerancia (Δprob ≤0.005).

---

## 5. Salidas del sistema (Fase 6)

**Por partido** (`predict_match.py` / `src/reporting.py` / `/api/predict`): P(victoria A / empate / victoria B), xG A/B, marcador modal, **top-5 marcadores**, intervalos de goles, confianza, incertidumbre, prob. de sorpresa, variables influyentes, aviso. Ejemplo:
```
Argentina vs Brazil — V.Arg 49.6% | Empate 23.1% | V.Bra 27.3%
xG 1.12-0.96 · modal 1-0 (14%) · top: 1-0,1-1,0-0,0-1,2-0 · sorpresa 50.4%
```

**Por grupo**: P(1.º/2.º/3.º/4.º) y P(clasificar) por equipo (sumas verificadas: cada posición = 1.0 por grupo; 32 clasificados totales).

**Por torneo**: P(R32, octavos, cuartos, semis, final, campeón) por equipo.

**Reporte explicativo (por qué predice así):** las variables más influyentes (importancia por permutación, neg-log-loss) son, en orden: **probabilidades Elo y diferencia de Elo** (dominantes), luego **forma reciente** (diferencia de goles, goles en contra). Es decir, el modelo predice sobre todo por **fuerza relativa Elo** (que ya incorpora todos los resultados hasta el corte) ajustada por forma reciente y localía. Toda salida lleva el aviso: *probabilidades calibradas, no certezas; el fútbol tiene alta varianza*.

---

## 6. Cómo ejecutar el modelo

```powershell
cd "D:\LO DEL DISCO C\Descargas\MODELO DE PREDICCIONES MUNDIAL 2026\worldcup-2026-predictor"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1) (Opcional) refrescar snapshot de datos
.\.venv\Scripts\python.exe -m src.data_collection --raw-dir data/raw --overwrite

# 2) Backtest + experimento de calibración (métricas con RPS)
.\.venv\Scripts\python.exe run_backtest.py

# 3) Predicción de un partido
.\.venv\Scripts\python.exe predict_match.py "Argentina" "France" --neutral --as-of 2026-06-13

# 4) Simular el torneo completo (50k; usar --n 100000 para más)
.\.venv\Scripts\python.exe run_tournament.py

# 5) Frontend local (Python, ya sin apuestas)
.\.venv\Scripts\python.exe build_static_snapshot.py ; start .\static\index.html

# 6) Pruebas
.\.venv\Scripts\python.exe -m pytest tests/ -q
node scripts/test-team-names.mjs
.\.venv\Scripts\python.exe scripts/parity_check.py
```

Web Vercel: `npm run test:api` · `npx vercel dev` · `npx vercel --prod` (desde el proyecto canónico; ver nota de dedup).

---

## 7. Cómo actualizar datos durante el Mundial 2026

Después de **cada jornada**:

1. **Refrescar resultados**: `python -m src.data_collection --raw-dir data/raw --overwrite` (descarga `martj42` actualizado). Esto trae los marcadores reales nuevos.
2. **Reconstruir el snapshot del calendario** (marca los partidos jugados como fijos):
   ```python
   from src.data_sources_2026 import load_groups, build_group_schedule, write_group_schedule, update_manifest
   from src.config import load_config
   cfg = load_config(); groups = load_groups(cfg.path("data","wc2026_groups"))
   sched = build_group_schedule(cfg.path("data","results_csv"), groups)
   write_group_schedule(sched, cfg.path("data","wc2026_schedule"))
   update_manifest(cfg.path("data","manifest"), {...}, cutoff_date="2026-06-XX")
   ```
3. **Avanzar la fecha de corte** en `config.yaml` (`model.cutoff_date`) al día actual.
4. **Re-simular**: `python run_tournament.py --as-of 2026-06-XX`. El Elo se recalcula con los nuevos resultados (modo *live*) y la simulación queda **condicionada al estado real** del torneo.
5. (Eliminatorias) Cuando empiece el R32, los partidos jugados de la llave se pueden fijar editando `wc2026_bracket.csv`/añadiendo resultados; la simulación de las rondas restantes sigue igual.
6. **Re-medir calibración** periódicamente; si el modelo se descalibra, reactivar `calibration.method: temperature` y re-evaluar con el gate.
7. **Versionar** cada snapshot (el hash SHA-256 queda en el manifest).

La web (`/api/predict`, `/api/teams`) ya descarga el dataset vivo y recalcula con la fecha de corte, con caché CDN; el cron `/api/refresh` corre a diario.

---

## 8. Limitaciones que siguen existiendo

- **Muestra pequeña de mundiales** (3 ediciones de backtest) → las métricas y la calibración tienen incertidumbre alta; por eso se prefiere simplicidad.
- **Sin datos de plantel**: lesiones, alineaciones confirmadas, minutos, valor de mercado, xG propietario, clima real. No se integran sin snapshots trazables y legales.
- **Asignación de terceros aproximada**: se usa emparejamiento factible que respeta los grupos permitidos, no la tabla oficial completa (~495 combinaciones). Impacto pequeño en probabilidades agregadas.
- **Prórroga/penales** modelados como función suave de Elo, no con un modelo específico de penales.
- **Modelo de empate** sigue siendo heurístico (decaimiento por |ΔElo|), no un ordinal calibrado.
- **Dos proyectos Vercel** sin consolidar (decisión de despliegue pendiente del usuario).
- **El fútbol es de alta varianza**: el sistema da probabilidades, nunca certezas.

---

## 9. Próximos pasos para nivel profesional

1. **Ampliar el backtest** a Eurocopa, Copa América, Copa África/Asia y eliminatorias (más muestra → calibración más fiable y posible adopción de temperature/isotónica).
2. **Tabla oficial de terceros** (Annex C, 495 combinaciones) para fidelidad exacta de la llave.
3. **Features de plantel** vía fuente con licencia y snapshot fechado (valor de mercado, disponibilidad), entrando solo si mejoran RPS/Brier.
4. **Modelo de empate principista** (Davidson / logit ordinal) y **bivariate Poisson** evaluados con el gate.
5. **CI/CD**: ejecutar pytest + paridad + lint en cada cambio; **versionar el repo con git** (hoy no lo está → sin historial ni undo).
6. **MLOps**: registrar cada corrida (datos+hash+semilla+métricas) y publicar predicciones fechadas para auditoría; dashboard de calibración en vivo.
7. **Consolidar el árbol Vercel** a un único proyecto.
8. **Validación de torneo**: back-simular 2018/2022 desde pre-torneo y comprobar la calibración de las probabilidades de avance por ronda.

---

*Prioridad del sistema: probabilidades calibradas y reproducibles sobre "acertar el ganador". Ninguna mejora se mantiene si no supera al modelo previo en validación temporal. El fútbol tiene mucha incertidumbre; estas son estimaciones, no certezas.*
