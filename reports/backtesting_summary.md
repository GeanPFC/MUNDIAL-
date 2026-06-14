# Backtesting inicial contra Mundiales anteriores

Fecha de ejecucion local: 2026-06-13.

Dataset usado:

- `data/raw/results.csv`
- 49,477 partidos internacionales masculinos.
- Rango del snapshot: 1872-11-30 a 2026-06-27.
- Advertencia: el snapshot contiene filas posteriores al 2026-06-13. Para cualquier prediccion "as of today" se debe filtrar `date <= 2026-06-13` y excluir resultados futuros o fixtures con marcador no confirmado.

Validacion:

- Entrenamiento temporal desde 2010-01-01 hasta el dia previo a cada Mundial.
- Tests: Mundial FIFA 2014, 2018 y 2022, 64 partidos por edicion.
- Sin datos de ranking FIFA historico, lesiones, planteles, valor de mercado, xG ni clima en esta primera corrida.
- ML: `HistGradientBoostingClassifier` con 60 iteraciones para prueba rapida.
- Dixon-Coles: version fija `rho=-0.08`; el ajuste por grid queda en codigo, pero no se uso en esta corrida rapida.

## Resultado promedio

| Modelo | Log loss | Brier | Accuracy | ECE |
|---|---:|---:|---:|---:|
| Elo features | 0.9935 | 0.5902 | 0.5625 | 0.1192 |
| ML Hist Gradient Boosting | 0.9994 | 0.5951 | 0.5469 | 0.0953 |
| Bayesian Gamma-Poisson | 1.0437 | 0.6286 | 0.5052 | 0.1100 |
| Poisson simple | 1.0445 | 0.6291 | 0.5104 | 0.1081 |
| Poisson Dixon-Coles fijo | 1.0514 | 0.6333 | 0.5104 | 0.1166 |
| Baseline tasas historicas | 1.0735 | 0.6514 | 0.4271 | 0.0522 |

## Ensemble conservador

Pesos probados sin optimizacion sobre el test:

- 55% Elo
- 25% ML
- 10% Poisson simple
- 10% Bayes

| Modelo | Log loss | Brier | Accuracy | ECE |
|---|---:|---:|---:|---:|
| Elo features | 0.9935 | 0.5902 | 0.5625 | 0.1192 |
| Ensemble conservador | 0.9958 | 0.5935 | 0.5469 | 0.0947 |
| Baseline tasas historicas | 1.0735 | 0.6514 | 0.4271 | 0.0522 |

## Decision metodologica

El ensemble conservador no supera a Elo en log loss ni Brier promedio. Por el principio definido, no se acepta como modelo superior todavia.

Correccion recomendada antes de publicar predicciones finales:

1. Mantener Elo como nucleo probabilistico inicial.
2. Usar Poisson/Bayes para goles esperados, marcador modal e intervalos, no para dominar 1X2.
3. Calibrar probabilidades con validacion temporal adicional: isotonic regression o temperature scaling por edicion/torneo.
4. Agregar ranking FIFA historico y snapshots de plantel solo si mejoran log loss/Brier.
5. Repetir backtesting con Eurocopa, Copa America, Copa Africa y eliminatorias para aumentar muestra.
6. Probar un ensemble apilado con pesos aprendidos solo en ediciones anteriores al test, nunca en el mismo Mundial evaluado.

Conclusion: el sistema base ya supera tasas historicas simples, pero el candidato mas defendible en esta corrida es Elo calibrado + Poisson/Bayes para distribucion de goles e incertidumbre.
