# Calibracion en vivo de la probabilidad de victoria

Fecha de corte: 2026-06-13.

Pregunta: cuando el modelo dice que un equipo tiene X% de ganar, ¿gana cerca del X% de las veces?
Metodo walk-forward sin leakage (cada prediccion usa solo partidos anteriores).

## Mundial 2026 (en vivo, se acumula con cada jornada)

n=4 · acierto=75.0% · log loss=0.9015 · Brier=0.5471 · RPS=0.1689 · ECE(victoria)=0.2948

> Aviso: solo 4 partidos jugados. La calibracion necesita ~30+ partidos para ser informativa; estos numeros aun son ruido. Re-ejecuta tras cada jornada.

### Log por partido (probabilidad asignada al resultado real)

| Fecha | Partido | P(L) | P(E) | P(V) | Real | P(real) | Acierto |
|---|---|---:|---:|---:|:--:|---:|:--:|
| 2026-06-11 | Mexico vs South Africa | 78% | 15% | 7% | H | 78% | si |
| 2026-06-11 | South Korea vs Czech Republic | 49% | 23% | 28% | H | 49% | si |
| 2026-06-12 | Canada vs Bosnia and Herzegovina | 73% | 16% | 11% | D | 16% | no |
| 2026-06-12 | United States vs Paraguay | 44% | 25% | 31% | H | 44% | si |

## Referencia: ultimos 24 meses (muestra grande)

n=2038 · acierto=60.3% · log loss=0.8785 · Brier=0.5124 · RPS=0.1689 · ECE(victoria)=0.0264

### Curva de fiabilidad del evento victoria

| Prob. predicha (bin) | Prob. media predicha | Frecuencia real | nº |
|---|---:|---:|---:|
| 0.0-0.1 | 4.8% | 5.1% | 529 |
| 0.1-0.2 | 15.2% | 11.0% | 545 |
| 0.2-0.3 | 25.2% | 20.8% | 566 |
| 0.3-0.4 | 34.7% | 33.2% | 551 |
| 0.4-0.5 | 45.0% | 43.0% | 430 |
| 0.5-0.6 | 55.0% | 54.1% | 386 |
| 0.6-0.7 | 64.9% | 60.6% | 401 |
| 0.7-0.8 | 75.1% | 72.8% | 346 |
| 0.8-0.9 | 84.2% | 88.8% | 258 |
| 0.9-1.0 | 91.4% | 95.3% | 64 |

Curva: `calibration_curve_reference.png` (la diagonal es calibracion perfecta).

## Como leerlo

- Si la frecuencia real sigue de cerca a la probabilidad predicha (columna a columna, o puntos sobre la diagonal), el modelo esta **bien calibrado**.
- Si la frecuencia real es menor que la predicha en los bins altos, el modelo es **sobreconfiado**; si es mayor, es **conservador**.
- ECE(victoria) bajo = mejor calibracion. log loss/Brier/RPS bajos = predicciones mas informativas.

> No son certezas: el modelo da probabilidades. Esta vista mide su honestidad, no garantiza resultados.