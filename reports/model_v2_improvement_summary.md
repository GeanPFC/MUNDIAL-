# Modelo v2: calibracion conservadora Elo + Poisson

Fecha local: 2026-06-13.

## Cambio principal

Se reemplazo la probabilidad 1X2 de Elo puro por:

```text
P_final = 0.97 * calibrate(Elo) + 0.03 * Poisson_goals
```

La calibracion de Elo usa:

- temperature: `0.91`
- draw multiplier: `0.96`
- Poisson blend: `0.03`

Motivo: mantener Elo como nucleo, porque fue el modelo mas fuerte, pero aplicar una correccion pequena y medible contra Mundiales anteriores. El blend Poisson es deliberadamente bajo porque Poisson simple no supero a Elo como predictor 1X2, aunque si aporta informacion para goles esperados y marcadores.

## Validacion pre-torneo estricta

Entrenamiento: partidos desde 2010 hasta el dia previo a cada Mundial.
Test: todos los partidos de Mundiales FIFA 2014, 2018 y 2022.
Modo: pre-torneo, sin actualizar con partidos del mismo Mundial.

| Modelo | Log loss | Brier | Accuracy | ECE |
|---|---:|---:|---:|---:|
| calibrated_elo_poisson_v2 | 0.998866 | 0.594472 | 0.557292 | 0.061331 |
| elo_static_pre_tournament | 0.999864 | 0.595462 | 0.557292 | 0.057627 |
| poisson_simple | 1.044504 | 0.629101 | 0.510417 | 0.108115 |
| baseline_rates | 1.073520 | 0.651417 | 0.427083 | 0.052247 |

La mejora es pequena pero positiva en log loss y Brier. No se adopto un ensemble agresivo porque no se justifico estadisticamente.

## Backtesting vivo

El modo `elo_features_live` usa actualizaciones cronologicas dentro del torneo y consigue log loss promedio `0.993473`, pero no es comparable con una prediccion pre-torneo completa. Es valido para operar durante el Mundial si se actualiza despues de cada partido.

## Decision

La web desplegada usa `calibrated_elo_poisson_v2` para probabilidades 1X2, y mantiene Poisson para:

- goles esperados;
- marcador modal;
- top 5 marcadores;
- intervalos de goles.

El modelo sigue sin usar lesiones, alineaciones, xG propietario, clima real ni ranking FIFA oficial historico porque esos datos aun no estan integrados con snapshots verificables.
