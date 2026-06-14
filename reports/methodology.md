# Metodologia del modelo Mundial 2026

## 1. Tesis de modelado

El modelo debe empezar con tasas base historicas y fuerza relativa de equipos. En futbol, una arquitectura simple bien calibrada suele ser dificil de superar porque los marcadores tienen baja informacion y alta varianza. Por eso el orden de decision es:

1. tasa base historica;
2. Elo recalculado internamente;
3. Poisson de goles con shrinkage;
4. Dixon-Coles para dependencia de marcadores 0-0, 1-0, 0-1 y 1-1;
5. Bayesiano para incertidumbre y actualizacion despues de cada partido;
6. ML supervisado solo si agrega poder predictivo fuera de muestra;
7. ensemble ponderado por rendimiento historico y calibracion.

## 2. Variables candidatas

Variables incluidas por defecto:

- diferencia Elo prepartido;
- probabilidades Elo 1X2;
- goles esperados por Poisson;
- ataque y defensa con shrinkage;
- forma reciente sin leakage: goles a favor, goles contra, diferencia de gol, puntos por partido;
- neutralidad/localia;
- descanso desde ultimo partido;
- tipo de torneo y fase si esta disponible;
- rendimiento historico en Mundial y eliminatorias si esta codificado en el dataset.

Variables externas opcionales:

- ranking FIFA oficial e historico;
- valor de mercado;
- edad promedio;
- minutos recientes en clubes;
- lesiones y ausencias;
- xG/xGA, tiros, presion y recuperaciones;
- clima, altitud, distancia de viaje y huso horario.

Regla: una variable externa entra al modelo solo si tiene fecha de snapshot, cobertura suficiente y mejora log loss/Brier sin leakage.

## 3. Formulas principales

### Elo

Probabilidad esperada:

```text
E_A = 1 / (1 + 10^(-(R_A - R_B + H) / 400))
```

Actualizacion:

```text
R_A' = R_A + K * I * M * (S_A - E_A)
R_B' = R_B - K * I * M * (S_A - E_A)
```

Donde `H` es ventaja local, `I` peso por importancia del torneo, `M` ajuste por diferencia de goles y `S_A` es 1, 0.5 o 0.

### Poisson

```text
lambda_A = base_home * attack_A * defense_B * home_factor
lambda_B = base_away * attack_B * defense_A
P(X=x, Y=y) = Pois(x; lambda_A) * Pois(y; lambda_B)
```

### Dixon-Coles

Se corrigen los cuatro marcadores bajos mediante `tau(x, y, lambda_A, lambda_B, rho)` y luego se normaliza la matriz de probabilidad. `rho` se ajusta por grid search en training con log loss de marcador exacto.

### Bayesiano

Se usa Gamma-Poisson conjugado para tasas de gol:

```text
goals_for_team ~ Poisson(rate_team * exposure)
rate_team ~ Gamma(alpha, beta)
posterior_mean = (alpha + goals) / (beta + exposure)
```

El nivel de incertidumbre se deriva de la dispersion posterior y de la distancia entre equipos.

## 4. Backtesting

Validacion temporal recomendada:

- entrenar hasta antes del Mundial 2014 y validar Mundial 2014;
- entrenar hasta antes del Mundial 2018 y validar Mundial 2018;
- entrenar hasta antes del Mundial 2022 y validar Mundial 2022;
- opcional: validar por Copa America, Eurocopa, Copa Africa, Copa Asia y eliminatorias, manteniendo cortes temporales.

Metricas:

- log loss multicategoria;
- Brier score multicategoria;
- accuracy solo como metrica secundaria;
- Expected Calibration Error;
- curvas de calibracion por clase;
- MAE de goles esperados;
- comparacion contra ranking FIFA, Elo puro, tasa base y Poisson simple.

## 5. Criterio de aceptacion

Un modelo candidato entra al ensemble si:

- tiene menor log loss que tasa base y Elo puro en promedio temporal;
- no degrada Brier score de forma material;
- no muestra sobreconfianza extrema en curvas de calibracion;
- conserva cobertura razonable de intervalos de goles.

Si no cumple, se reduce complejidad, se aumenta shrinkage o se descarta.

## 6. Investigacion usada

- FIFA mantiene el ranking masculino oficial; la pagina consultada el 13 de junio de 2026 muestra ultima actualizacion el 11 de junio de 2026 y proxima actualizacion el 20 de julio de 2026.
- El dataset `martj42/international_results` documenta resultados internacionales masculinos desde 1872 y columnas necesarias para modelar marcador, sede y neutralidad.
- Dixon-Coles (1997) es referencia para corregir independencia Poisson en marcadores bajos.
- Lasek, Szlavik y Bhulai (2013) reportan fuerte capacidad predictiva de sistemas de ranking en futbol internacional.
- Gilch y Muller (2018) y Gilch (2022) usan Elo, modelos Poisson y simulacion Monte Carlo para mundiales, incluyendo validacion contra torneos anteriores.

## 7. Limitaciones

El modelo no conoce automaticamente informacion de vestuario, cambios tacticos no medidos, lesiones tardias, clima real de ultimo momento ni alineaciones confirmadas si no se cargan como datos. Cada prediccion debe publicarse con fecha de corte y version de datos.
