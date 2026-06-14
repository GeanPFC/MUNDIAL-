# worldcup-2026-predictor

Sistema reproducible para estimar probabilidades de partidos y simular el Mundial FIFA 2026 con modelos probabilisticos calibrados. El objetivo es analitico y deportivo; no esta orientado a apuestas.

## Web automatica para Vercel

La carpeta `public/` contiene el frontend y `api/` contiene funciones serverless para Vercel.
La version limpia usada para despliegue esta en `vercel-app/`.

Produccion desplegada:

- https://vercel-app-henna-psi.vercel.app

Version actual del modelo desplegado:

- `elo_live_v3`
- Elo "live" (recalculado con todos los resultados hasta la fecha de corte, incluidos los del Mundial ya jugados) para 1X2; Poisson para goles esperados, marcador modal e intervalos.
- Validacion pre-torneo 2014/2018/2022: log loss `0.99346`, Brier `0.589783`, RPS `0.210983`.
- Decision basada en evidencia: la calibracion por temperatura se evaluo y **se descarto** porque no generaliza fuera de muestra (ver `reports/calibration_experiment.csv` y `CHANGELOG_MODEL_IMPROVEMENTS.md`).
- **No** produce recomendaciones de apuestas. La salida incluye una "lectura analitica del partido" (favorito, equilibrio, goles) sin lenguaje de mercado.

- `/api/teams` descarga el dataset vivo `martj42/international_results` desde GitHub y devuelve equipos disponibles.
- `/api/predict` recalcula Elo/Poisson con la fecha de corte solicitada y devuelve probabilidades, xG, marcador modal, incertidumbre y lectura analitica.

> Nota de despliegue (dedup M3): existen **dos proyectos Vercel distintos** vinculados en el repo: la raiz (`worldcup-2026-predictor`) y `vercel-app/` (`vercel-app`). El README designa `vercel-app/` como produccion. Ambas copias del codigo se mantienen identicas; consolidar a un solo proyecto es una decision de dashboard de Vercel, no de archivos.
- `/api/refresh` se ejecuta con Vercel Cron una vez al dia segun `vercel.json`, compatible con Vercel Hobby.
- Las respuestas usan cache CDN (`s-maxage`) para evitar recalcular el modelo en cada visita.
- La entrada de equipos acepta nombres en espanol y en ingles. Ejemplo: `Catar`/`Suiza` se convierten internamente a `Qatar`/`Switzerland`.

Comandos:

```powershell
npm run test:api
npx vercel dev
npx vercel --prod
```

Para desplegar desde CLI necesitas estar autenticado en Vercel o pasar `--token`.

## Principio operativo

No se publican predicciones finales sin backtesting. El pipeline primero compara cada candidato contra modelos base:

- tasas historicas por resultado y fase;
- Elo puro;
- Poisson simple de goles;
- Poisson con correccion Dixon-Coles;
- modelos bayesianos con incertidumbre explicita;
- ML supervisado solo si supera a los modelos simples en validacion temporal.

Si el ensemble no mejora log loss y Brier score frente a los baselines, se descarta o se repondera. La complejidad no se acepta por defecto.

## Fuentes verificadas y fuentes a cargar

Datos disponibles y recomendados:

- Resultados internacionales masculinos historicos: [`martj42/international_results`](https://github.com/martj42/international_results). El README del dataset indica partidos internacionales masculinos desde 1872, columnas de marcador, torneo, ciudad, pais y neutralidad.
- Ranking FIFA oficial: [`FIFA/Coca-Cola Men's World Ranking`](https://inside.fifa.com/fifa-world-ranking/men). Consultado el 13 de junio de 2026: la pagina oficial muestra ultima actualizacion el 11 de junio de 2026 y proxima actualizacion el 20 de julio de 2026.
- Calendario, sedes y grupos: [`FIFA World Cup 26 match schedule`](https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/match-schedule). Debe cargarse como snapshot local antes de simular porque es dato vivo y cambia con resultados.
- Elo internacional: [`World Football Elo Ratings`](https://www.eloratings.net/) como referencia externa no oficial. El codigo tambien puede recalcular Elo internamente desde resultados historicos.
- Literatura: Dixon y Coles (1997) para dependencia en marcadores bajos; Lasek, Szlavik y Bhulai (2013) sobre poder predictivo de rankings; Gilch y Muller (2018) y Gilch (2022) para Poisson/Elo y simulacion Monte Carlo en mundiales.

Datos faltantes que no deben inventarse:

- lesiones y ausencias confirmadas;
- minutos de futbolistas en clubes;
- valor de mercado y edad promedio de plantel;
- xG/xGA, presion, tiros y posesion por seleccion;
- clima real por sede y hora;
- fatiga individual y viajes exactos.

Estos datos se integran solo si existen snapshots trazables con fecha de corte anterior al partido.

## Estructura

```text
worldcup-2026-predictor/
  data/
    raw/
    processed/
  notebooks/
  reports/
    methodology.md
  src/
    data_collection.py
    preprocessing.py
    features.py
    elo_model.py
    poisson_model.py
    bayesian_model.py
    ml_model.py
    ensemble.py
    simulation.py
    evaluation.py
  requirements.txt
  README.md
```

## Flujo recomendado

Desde PowerShell:

```powershell
cd "D:\LO DEL DISCO C\Descargas\MODELO DE PREDICCIONES MUNDIAL 2026\worldcup-2026-predictor"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

1. Descargar snapshots crudos en `data/raw/`:

```powershell
.\.venv\Scripts\python.exe -m src.data_collection --raw-dir data/raw
```

Si el Python local falla por certificados TLS al descargar desde GitHub, usar solamente para esta fuente conocida:

```powershell
.\.venv\Scripts\python.exe -m src.data_collection --raw-dir data/raw --allow-insecure-ssl
```

2. Repetir la validacion contra Mundiales anteriores:

```powershell
.\.venv\Scripts\python.exe run_backtest.py
```

3. Probar una prediccion de partido con fecha de corte:

```powershell
.\.venv\Scripts\python.exe predict_match.py "Argentina" "France" --neutral --as-of 2026-06-13
```

Simular el torneo completo (Monte Carlo, reglas FIFA 2026) y generar reportes por grupo y por equipo:

```powershell
.\.venv\Scripts\python.exe run_tournament.py            # 50.000 simulaciones (config.yaml)
.\.venv\Scripts\python.exe run_tournament.py --n 100000 # mas simulaciones
```

Salidas: `reports/wc2026_predictions.md`, `reports/wc2026_group_probabilities.csv`, `reports/wc2026_tournament_probabilities.csv`.

Publicar las probabilidades del torneo en la web (snapshot estatico para Vercel):

```powershell
.\.venv\Scripts\python.exe build_tournament_snapshot.py   # escribe public/tournament_snapshot.json
npx vercel --prod --cwd vercel-app                         # redespliega
```

La pagina `/tournament.html` (campeon, rondas y grupos) lee ese JSON. Como la simulacion
Monte Carlo es Python pesado (~minutos), no corre en serverless: se regenera localmente y se
redespliega tras cada jornada. El predictor por partido (`/api/predict`) si recalcula en vivo.

Pruebas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
node scripts/test-team-names.mjs
.\.venv\Scripts\python.exe scripts/parity_check.py
```

4. Abrir el frontend local:

La forma mas simple es abrir este archivo en el navegador:

```powershell
.\.venv\Scripts\python.exe build_static_snapshot.py
start .\static\index.html
```

Tambien puedes usar servidor local:

```powershell
.\.venv\Scripts\python.exe web_app.py --port 8765
```

Luego entra a `http://127.0.0.1:8765`.

Tambien puedes dejarlo corriendo en segundo plano:

```powershell
.\start_frontend.ps1
```

Para detenerlo:

```powershell
.\stop_frontend.ps1
```

Alternativa equivalente:

```powershell
.\.venv\Scripts\python.exe start_frontend.py
.\.venv\Scripts\python.exe stop_frontend.py
```

5. Construir dataset supervisado sin leakage desde Python:

```python
from src.preprocessing import load_results
from src.features import make_supervised_matches

results = load_results("data/raw/results.csv")
matches = make_supervised_matches(results)
```

3. Ejecutar backtesting temporal:

```python
from src.evaluation import temporal_backtest, BaselineRateModel
from src.ml_model import MLOutcomeModel

splits = [
    ("2014-01-01", "2018-06-14", "2018-07-15"),
    ("2018-01-01", "2022-11-20", "2022-12-18"),
]

scores = temporal_backtest(
    matches,
    model_builders={
        "baseline_rates": lambda: BaselineRateModel(),
        "ml_gradient_boosting": lambda: MLOutcomeModel(),
    },
    splits=splits,
)
```

4. Entrenar solo los modelos que superan baselines y simular:

```python
from src.simulation import run_monte_carlo

summary = run_monte_carlo(
    schedule=worldcup_schedule,
    predictor=validated_predictor,
    n_simulations=20000,
    random_state=2026,
)
```

## Backtesting inicial ejecutado

Se descargo `data/raw/results.csv` y se valido contra los Mundiales 2014, 2018 y 2022. Resultados promedio:

| Modelo | Log loss | Brier | Accuracy | ECE |
|---|---:|---:|---:|---:|
| Elo features | 0.9935 | 0.5902 | 0.5625 | 0.1192 |
| ML Hist Gradient Boosting | 0.9994 | 0.5951 | 0.5469 | 0.0953 |
| Bayesian Gamma-Poisson | 1.0437 | 0.6286 | 0.5052 | 0.1100 |
| Poisson simple | 1.0445 | 0.6291 | 0.5104 | 0.1081 |
| Baseline tasas historicas | 1.0735 | 0.6514 | 0.4271 | 0.0522 |

Un ensemble conservador no supero a Elo en log loss promedio (`0.9958` vs `0.9935`), aunque mejoro ECE. Por tanto, la recomendacion actual es usar Elo como nucleo para 1X2, y Poisson/Bayes para goles esperados, marcador modal e incertidumbre hasta que una calibracion adicional demuestre mejora fuera de muestra.

Los CSV completos estan en `reports/backtest_worldcups_2014_2018_2022.csv` y `reports/backtest_fixed_ensemble_2014_2018_2022.csv`.

Advertencia de leakage: el snapshot abierto descargado contiene filas posteriores al 13 de junio de 2026. Para predicciones reales se debe filtrar siempre por fecha de corte y verificar resultados oficiales.

## Salida por partido

Cada predictor debe entregar:

- probabilidad victoria local/equipo A;
- probabilidad empate;
- probabilidad victoria visitante/equipo B;
- goles esperados de ambos equipos;
- marcador mas probable;
- intervalo de goles por equipo;
- nivel de incertidumbre;
- variables que mas influyeron.

## Actualizacion despues de cada partido

1. Registrar resultado oficial con fecha, sede, neutralidad y marcador de tiempo reglamentario/extra sin penales para el modelo de goles.
2. Actualizar Elo cronologicamente.
3. Actualizar posteriors bayesianos de ataque/defensa.
4. Recalcular features de descanso, viaje y fatiga para partidos futuros.
5. Reentrenar o actualizar solo con datos disponibles antes de cada proximo partido.
6. Volver a medir calibracion en ventanas recientes; si el modelo se descalibra, aumentar shrinkage hacia tasas base.
7. Versionar cada snapshot de datos y predicciones para auditoria.

## Limitaciones

El futbol internacional tiene muestras pequenas, planteles que cambian, rivales desbalanceados y alta varianza en marcadores bajos. El sistema produce probabilidades, no certezas. Variables ruidosas o caras de obtener se descartan si no mejoran backtesting temporal.
