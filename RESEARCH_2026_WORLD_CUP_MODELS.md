# RESEARCH_2026_WORLD_CUP_MODELS.md — Investigación aplicada

Fecha de consulta: **2026-06-13**.
Propósito: reunir información oficial y académica actualizada para rediseñar el predictor del Mundial 2026 con criterio serio, explicable y reproducible.
Restricción cumplida: **no se usaron casas de apuestas ni mercados de predicción**. Fuentes: oficiales (FIFA), enciclopédicas (Wikipedia), prensa deportiva (ESPN/Olympics/NBC) y literatura académica (arXiv, repositorios universitarios, revistas).

> Las cifras vivas (ranking, resultados ya jugados) deben **congelarse como snapshot fechado** antes de entrenar predicciones finales. Esta investigación documenta el estado al 2026-06-13.

---

## 1. Formato oficial del Mundial 2026

**Anfitriones y fechas.** Lo organizan **Canadá, México y EE. UU.**, del **11 jun 2026 al 19 jul 2026**, en **16 sedes / 16 ciudades** (11 EE. UU., 3 México, 2 Canadá). Partido inaugural: 11 jun 2026, **México vs Sudáfrica** (Ciudad de México). Final: **19 jul 2026** en East Rutherford, Nueva Jersey.

**Estructura.** **48 selecciones**, **12 grupos de 4** (A–L), todos contra todos a una vuelta (3 partidos por equipo) → **72 partidos de fase de grupos**. Clasifican a una **Ronda de 32**: los **2 primeros de cada grupo** (24) + los **8 mejores terceros** de los 12. Luego eliminación directa: **R32 → octavos (R16) → cuartos → semifinales → final** (+ partido por el 3.er puesto el 18 jul). Total: **104 partidos**.

**Calendario de eliminatorias (2026):**
| Ronda | Fechas |
|---|---|
| Fase de grupos | 11 – 27 jun |
| Ronda de 32 | 28 jun – 3 jul |
| Octavos (R16) | 4 – 7 jul |
| Cuartos | 9 – 11 jul |
| Semifinales | 14 – 15 jul |
| 3.er puesto | 18 jul |
| Final | 19 jul |

**Desempates de grupo (orden oficial FIFA):** 1) puntos; 2) diferencia de goles general; 3) goles a favor general; 4) **enfrentamiento directo** entre empatados (puntos → dif. goles → goles a favor en esos partidos); 5) **fair-play** (menos tarjetas); 6) **sorteo**. *El sistema actual del repo solo aplica los criterios 1–3 → corregir en Fase 4 (hallazgo A3 de la auditoría).*

**Sorteo final (5 dic 2025) — los 12 grupos** (posiciones de anfitriones predeterminadas: México A1, Canadá B1, EE. UU. D1):

| Grupo | Equipos (orden por bombo) |
|---|---|
| A | México, Corea del Sur, Sudáfrica, Chequia (Czech Republic) |
| B | Canadá, Suiza, Catar, Bosnia y Herzegovina |
| C | Brasil, Marruecos, Escocia, Haití |
| D | Estados Unidos, Australia, Paraguay, Turquía |
| E | Alemania, Ecuador, Costa de Marfil (Ivory Coast), Curazao |
| F | Países Bajos, Japón, Túnez, Suecia |
| G | Bélgica, Egipto, Irán, Nueva Zelanda |
| H | España, Uruguay, Arabia Saudita, Cabo Verde |
| I | Francia, Senegal, Noruega, Irak |
| J | Argentina, Argelia, Austria, Jordania |
| K | Portugal, Colombia, Uzbekistán, RD Congo (DR Congo) |
| L | Inglaterra, Croacia, Panamá, Ghana |

✅ **Verificación cruzada con `data/raw/results.csv`:** los fixtures del 11–12 jun (México–Sudáfrica, Corea–Chequia, Canadá–Bosnia, EE.UU.–Paraguay) **coinciden** con el sorteo oficial. El dataset es consistente con los grupos reales. *Nota de nombres a mapear en el snapshot: Chequia↔"Czech Republic", Costa de Marfil↔"Ivory Coast", RD Congo↔"DR Congo", Turquía↔"Turkey".*

**Estructura fija de la Ronda de 32** (de la malla oficial; los terceros entran en slots con **conjunto de grupos permitidos**, asignados por la tabla oficial de terceros según qué 8 clasifiquen). Resumen de los 16 cruces:

| R32 | Local | Visitante |
|---|---|---|
| 1 | 2.º A | 2.º B |
| 2 | 1.º C | 2.º F |
| 3 | 1.º E | 3.º de {A,B,C,D,F} |
| 4 | 1.º F | 2.º C |
| 5 | 2.º E | 2.º I |
| 6 | 1.º I | 3.º de {C,D,F,G,H} |
| 7 | 1.º A | 3.º de {C,E,F,H,I} |
| 8 | 1.º L | 3.º de {E,H,I,J,K} |
| 9 | 1.º G | 3.º de {A,E,H,I,J} |
| 10 | 1.º D | 3.º de {B,E,F,I,J} |
| 11 | 1.º H | 2.º J |
| 12 | 2.º K | 2.º L |
| 13 | 1.º B | 3.º de {E,F,G,I,J} |
| 14 | 2.º D | 2.º G |
| 15 | 1.º J | 2.º H |
| 16 | 1.º K | 3.º de {D,E,I,J,L} |

> **Asignación de terceros:** FIFA usa una tabla predeterminada (estilo "Annex C", análoga a la usada en Eurocopas con 4 mejores terceros, aquí extendida a 8/12 grupos) que mapea **cada combinación de los 8 grupos cuyos terceros avanzan** a un slot concreto, garantizando que (a) ningún equipo enfrenta a otro de su grupo y (b) los terceros siempre enfrentan a primeros de grupo. Para la simulación implementaremos esa asignación como un **emparejamiento factible** que respeta los conjuntos de grupos permitidos de la tabla anterior (Fase 4). Las **rondas posteriores** (R16→final) siguen una malla fija de ganadores de R32.

---

## 2. Rankings y fuerza de selecciones

**Ranking FIFA/Coca-Cola masculino** — última actualización **11 jun 2026**, próxima **20 jul 2026** (fuente oficial). Cabeza de la tabla al 11 jun 2026: **Argentina 1.º** (recuperó el liderato), seguida de **España, Francia, Inglaterra, Portugal** (top 5) y **Brasil 6.º**. Anfitriones: **México 14.º**, **EE. UU. 17.º**, **Canadá 30.º**. *Los puntos exactos deben tomarse del snapshot oficial fechado; aquí se documenta el orden, no se inventan decimales.*

**World Football Elo Ratings (eloratings.net).** Referencia externa no oficial; útil como contraste. El repo **ya recalcula Elo internamente** desde resultados históricos (lo correcto para reproducibilidad). Conclusión práctica: mantener el Elo interno como núcleo y usar el ranking FIFA y/o Elo externo solo como **feature adicional** si mejora log loss/Brier/RPS fuera de muestra.

**Hallazgos de la literatura sobre fuerza/ranking:**
- Lasek, Szlávik & Bhulai (2013): los sistemas de rating tipo Elo tienen **fuerte poder predictivo** en fútbol internacional, a menudo iguales o mejores que el ranking FIFA.
- La **ventaja de campo/anfitrión** es real pero menor en sedes neutrales; en 2026 los anfitriones juegan de local solo en sus sedes. El repo ya distingue `neutral` y aplica ventaja local solo si no es neutral (correcto).
- **Partidos oficiales vs amistosos:** deben ponderarse distinto. El repo ya pondera por importancia de torneo (amistoso 0.7, Mundial 4.0) y por recencia (half-life ~3 años). Es una práctica alineada con FIFA (que también pondera por importancia) y con la literatura.

---

## 3. Modelos predictivos de fútbol (estado del arte aplicable)

**3.1 Modelos de goles (base estadística).**
- **Poisson independiente** (Maher 1982): goles de cada equipo ~ Poisson(λ) con λ = f(ataque, defensa, localía). Simple y sorprendentemente competitivo.
- **Dixon-Coles (1997):** corrige la independencia en marcadores bajos (0-0, 1-0, 0-1, 1-1) con el factor τ(·,ρ) y añade ponderación temporal. **Ya implementado** en `poisson_model.py` (τ + grid de ρ). Mejora marcador exacto y empates.
- **Poisson bivariado** (Karlis & Ntzoufras 2003): modela correlación entre goles de ambos equipos con un término común. Alternativa más principista que Dixon-Coles para la dependencia.
- **Binomial negativa / Poisson inflado en cero** (p. ej. *Nested Zero-Inflated Generalized Poisson*, FIFA 2022, arXiv:2205.04173): maneja sobredispersión y exceso de 0-0. Útil solo si el backtest muestra sobredispersión real; no adoptar por defecto.

**3.2 Modelos de rating / resultado 1×2.**
- **Elo** (con K, ventaja local, ajuste por margen e importancia): **ya implementado**; fue el **mejor modelo 1×2** en el backtest del propio repo.
- **Regresión Poisson con Elo como covariable + simulación Monte Carlo** (Groll et al.; Gilch & Müller 2018; Gilch 2022): el enfoque académico de referencia para mundiales. Estima λ de cada partido con la diferencia de Elo y luego **simula el torneo** para obtener probabilidades de avanzar por ronda y de campeón. **Es exactamente el patrón objetivo de este proyecto.**
- **Modelos bayesianos:** fuerza de ataque/defensa con priores e incertidumbre explícita y actualización tras cada partido. **Ya implementado** (Gamma-Poisson). Buen ajuste con "actualizar durante el Mundial".

**3.3 Machine Learning.**
- **Gradient boosting (XGBoost/LightGBM/CatBoost), random forest, regresión logística, redes neuronales.** Evidencia mixta: **rara vez superan a un Elo/Poisson bien calibrado en 1×2** con los datos públicos disponibles (pocos features fuertes, alta varianza). El repo ya lo trata con el criterio correcto: el ML **solo entra si vence al baseline** en validación temporal (en su backtest, el ML **no** superó a Elo). Mantener ese criterio.
- Híbridos "random forest + ranking Poisson" (Groll et al. 2019) son competitivos, pero requieren features de plantel/mercado que aquí **no** están disponibles con snapshots legales y fechados.

**3.4 Ensembles.** Promediado/stacking de probabilidades. El repo ya tiene `ensemble.py` con pesos por desempeño y guardia "debe vencer baseline". Conclusión: **conservar, pero solo desplegar el ensemble si mejora log loss/Brier/RPS** fuera de muestra (en el backtest actual no lo hizo → seguir con Elo como núcleo).

**3.5 Calibración (clave y hoy ausente como paso entrenado).**
- **Platt scaling** (logística), **isotónica** (no paramétrica, monótona), **temperature scaling** (un parámetro, multiclase), y **calibración multinomial**. Se **ajustan sobre un conjunto de validación temporal**, no a mano.
- Recomendación: implementar `calibration.py` que **aprenda** la temperatura/mapeo en ediciones anteriores y se evalúe en la edición de test, reemplazando las constantes hard-codeadas del JS (hallazgo C3). Adoptar solo si reduce log loss/Brier/**RPS** y ECE.

**3.6 Simulación Monte Carlo del torneo.** 50.000–100.000 simulaciones; en cada una se muestrea cada partido desde el modelo de goles (matriz Poisson/Dixon-Coles → resultado coherente), se arman las tablas con desempates oficiales, se eligen los 8 mejores terceros, se asignan a la llave (tabla oficial) y se resuelven eliminatorias con **prórroga/penales como mecanismo separado** (ponderado por fuerza, no 50/50). Es el patrón de Gilch/Groll y el objetivo de Fase 4.

---

## 4. Buenas prácticas de evaluación y reproducibilidad

- **Validación temporal estricta:** entrenar hasta el día previo a cada torneo y validar dentro. **Ya implementado** y con guardia anti-overlap. Ampliar muestra con Eurocopa, Copa América, Copa África, Copa Asia y eliminatorias (todas con corte temporal) para reducir el ruido de validar con solo 3 Mundiales.
- **Backtesting contra torneos pasados** (2014/2018/2022): hecho. Mantener y extender.
- **Comparación contra baselines:** tasas base, ranking FIFA, Elo puro, Poisson simple. Hecho parcialmente; añadir un baseline **explícito de ranking FIFA**.
- **Métricas probabilísticas:**
  - **Log loss** y **Brier multiclase**: presentes.
  - **Ranked Probability Score (RPS):** **faltante y solicitado**. Constantinou & Fenton (2012) lo proponen como regla adecuada para fútbol porque es **sensible a la distancia** (un resultado local está "más cerca" del empate que de la victoria visitante), respetando la naturaleza **ordinal** L>E>V. Hay debate académico (Wheatcroft 2019/2021, *"the case against the RPS"*), por lo que se reportará **junto** a log loss y Brier, no en su lugar. → Añadir RPS a `evaluation.py` (Fase 3/4).
  - **ECE y curvas de calibración:** ECE presente; añadir curvas/diagramas de fiabilidad por clase.
  - **Accuracy y matriz de confusión:** solo como métricas secundarias.
- **Control de leakage:** features walk-forward, splits temporales, filtro por fecha de corte. Bien; el pendiente es **versionar el dato**.
- **Versionado de datasets y reproducibilidad:** la fuente `martj42/international_results` es un **blanco móvil** (rama `master`). Práctica recomendada: descargar a un **snapshot fechado**, registrar **hash SHA-256** y (si se puede) **commit/tag** de origen, y fijar **semilla aleatoria** en simulación. → Config central + manifest con hash (Fase 5).

---

## 5. Conclusiones prácticas para ESTE proyecto

1. **Conservar el núcleo Elo + Poisson/Dixon-Coles** (ya validado; cumple el principio "no complejidad sin mejora"). No reescribir.
2. **Construir el snapshot oficial 2026** (`data/raw/wc2026_groups.csv` + calendario + tabla de terceros + malla de eliminatorias) a partir de las fuentes de la §1, con fecha y hash. Los grupos ya están verificados contra `results.csv`.
3. **Implementar Monte Carlo real** (50k–100k) con reglas FIFA correctas: desempates oficiales (incl. enfrentamiento directo/fair-play), 8 mejores terceros, asignación oficial a la llave, marcador coherente desde la matriz de goles, prórroga/penales ponderados por fuerza, y conteo **completo** por ronda (R32→octavos→cuartos→SF→final→campeón). Esto cubre el hallazgo C2.
4. **Añadir calibración entrenada** (`calibration.py`: temperature/Platt/isotónica) validada temporalmente, sustituyendo las constantes manuales (C3). Adoptar solo si mejora.
5. **Añadir RPS** y diagramas de fiabilidad a `evaluation.py`; mantener log loss/Brier como principales.
6. **Operar el Elo actualizado-en-vivo** durante el Mundial (mejor en su propio backtest: 0.9935 vs 0.9989) en vez del estático pre-torneo (A1).
7. **Eliminar la guía de apuestas** (C1) y reemplazar por lectura de incertidumbre analítica.
8. **MLOps:** `config.yaml` central, semilla fija, snapshot versionado con hash, `pytest`, y deduplicar el árbol de la app.

---

## 6. Fuentes consultadas (2026-06-13)

**Oficiales / formato / grupos / calendario**
- FIFA — Final Draw results: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/final-draw-results
- FIFA — Knockout stage schedule & bracket: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/knockout-stage-match-schedule-bracket
- FIFA — Standings: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/standings
- Wikipedia — 2026 FIFA World Cup draw (grupos completos): https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_draw
- Wikipedia — 2026 FIFA World Cup (formato, sedes, fechas): https://en.wikipedia.org/wiki/2026_FIFA_World_Cup
- ESPN — Match schedule, fixtures, R32 bracket: https://www.espn.com/soccer/story/_/id/48939282/2026-fifa-world-cup-fixtures-results-match-schedule-group-stage-knockout-rounds-bracket
- Olympics.com — Schedule, results, standings: https://www.olympics.com/en/news/fifa-world-cup-2026-schedule-results-scores-standings-list
- NBC Sports — Groups confirmed: https://www.nbcsports.com/soccer/news/2026-world-cup-groups-confirmed-full-draw-groups-details

**Ranking FIFA**
- FIFA/Coca-Cola Men's World Ranking (oficial): https://inside.fifa.com/fifa-world-ranking/men
- ESPN — FIFA Men's Top 50, jun 2026: https://www.espn.com/soccer/story/_/id/46664763/fifa-mens-top-50-world-rankings
- Wikipedia — FIFA Men's World Ranking: https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking

**Modelos predictivos (academia / open source)**
- Groll et al. — Prediction of major international soccer tournaments (Poisson + Elo + Monte Carlo): https://epub.ub.uni-muenchen.de/31579/1/Groll_Prediction.pdf
- Lasek et al. — On Elo based prediction models for the FIFA World Cup 2018: https://arxiv.org/pdf/1806.01930
- Karlis & Ntzoufras (bivariate Poisson) y Dixon-Coles, vía: https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/
- Nested Zero-Inflated Generalized Poisson (WC 2022): https://arxiv.org/pdf/2205.04173
- Extending Dixon-Coles (datos de fútbol femenino): https://arxiv.org/pdf/2307.02139
- Forecasting Soccer Matches through Distributions: https://arxiv.org/html/2501.05873v1
- Ejemplo open source (Elo + Dixon-Coles + Monte Carlo) WC2026: https://github.com/Hicruben/world-cup-2026-prediction-model

**Evaluación / RPS / calibración**
- Constantinou & Fenton — Solving the problem of inadequate scoring rules (propone RPS): https://www.researchgate.net/publication/227378917
- Wheatcroft — Evaluating probabilistic forecasts of football matches: the case against the RPS: https://arxiv.org/pdf/1908.08980

> Aviso: la prensa deportiva se usó solo para datos fácticos (grupos, fechas, bracket) verificables contra fuentes oficiales. Ningún número del modelo se deriva de mercados de apuestas.
