"""Seguimiento de calibracion en vivo de la probabilidad de victoria.

Mide si las probabilidades de victoria del modelo se cumplen en la realidad.
Re-ejecutar despues de cada jornada del Mundial para ver como se acumula.

Uso:
    python run_live_calibration.py
    python run_live_calibration.py --as-of 2026-06-20 --reference-months 24

Salidas:
    reports/live_calibration_wc2026.csv      (log por partido del Mundial)
    reports/live_calibration_report.md       (resumen + curvas)
    reports/calibration_curve_reference.png  (curva de fiabilidad, muestra grande)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.live_calibration import (
    calibration_summary,
    save_reliability_png,
    walkforward_predictions,
    win_event_reliability,
)
from src.preprocessing import load_results

WORLD_CUP = "FIFA World Cup"


def _fmt_metrics(s: dict) -> str:
    if s.get("n_matches", 0) == 0:
        return "Sin partidos evaluados todavia."
    return (
        f"n={s['n_matches']} · acierto={s['accuracy']:.1%} · log loss={s['log_loss']:.4f} · "
        f"Brier={s['brier']:.4f} · RPS={s['rps']:.4f} · ECE(victoria)={s['win_event_ece']:.4f}"
    )


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Calibracion en vivo de la probabilidad de victoria.")
    parser.add_argument("--as-of", default=str(cfg.get("model", "cutoff_date", default="2026-06-13")))
    parser.add_argument("--reference-months", type=int, default=24)
    args = parser.parse_args()

    cutoff = pd.Timestamp(args.as_of)
    results = load_results(cfg.path("data", "results_csv"))
    results = results[results["date"] <= cutoff]
    out_dir = Path(cfg.path("reporting", "output_dir"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Vista 1: Mundial 2026 en vivo (partidos del torneo ya jugados).
    wc = walkforward_predictions(results, "2026-06-01", cutoff, tournament=WORLD_CUP)
    wc_summary = calibration_summary(wc)
    wc_rel = win_event_reliability(wc, n_bins=10)

    # Vista 2: referencia (ventana de partidos recientes -> muestra grande).
    ref_start = cutoff - pd.DateOffset(months=args.reference_months)
    ref = walkforward_predictions(results, ref_start, cutoff, tournament=None)
    ref_summary = calibration_summary(ref)
    ref_rel = win_event_reliability(ref, n_bins=10)

    # Guardar artefactos.
    if not wc.empty:
        wc.to_csv(out_dir / "live_calibration_wc2026.csv", index=False)
    png = save_reliability_png(
        ref_rel,
        f"Calibracion de la probabilidad de victoria (ultimos {args.reference_months} meses)",
        out_dir / "calibration_curve_reference.png",
    )

    lines = [
        "# Calibracion en vivo de la probabilidad de victoria",
        "",
        f"Fecha de corte: {args.as_of}.",
        "",
        "Pregunta: cuando el modelo dice que un equipo tiene X% de ganar, ¿gana cerca del X% de las veces?",
        "Metodo walk-forward sin leakage (cada prediccion usa solo partidos anteriores).",
        "",
        "## Mundial 2026 (en vivo, se acumula con cada jornada)",
        "",
        _fmt_metrics(wc_summary),
    ]
    if wc_summary.get("n_matches", 0) < 20:
        lines += [
            "",
            f"> Aviso: solo {wc_summary.get('n_matches', 0)} partidos jugados. La calibracion necesita "
            "~30+ partidos para ser informativa; estos numeros aun son ruido. Re-ejecuta tras cada jornada.",
        ]
    if not wc.empty:
        lines += ["", "### Log por partido (probabilidad asignada al resultado real)", "",
                  "| Fecha | Partido | P(L) | P(E) | P(V) | Real | P(real) | Acierto |",
                  "|---|---|---:|---:|---:|:--:|---:|:--:|"]
        for _, r in wc.iterrows():
            lines.append(
                f"| {r['date'].date()} | {r['home_team']} vs {r['away_team']} | {r['p_home_win']:.0%} | "
                f"{r['p_draw']:.0%} | {r['p_away_win']:.0%} | {r['outcome']} | {r['p_assigned_to_actual']:.0%} | "
                f"{'si' if r['correct'] else 'no'} |"
            )

    lines += [
        "",
        f"## Referencia: ultimos {args.reference_months} meses (muestra grande)",
        "",
        _fmt_metrics(ref_summary),
        "",
        "### Curva de fiabilidad del evento victoria",
        "",
        "| Prob. predicha (bin) | Prob. media predicha | Frecuencia real | nº |",
        "|---|---:|---:|---:|",
    ]
    for _, r in ref_rel.iterrows():
        lines.append(
            f"| {r['bin_lower']:.1f}-{r['bin_upper']:.1f} | {r['predicted_win_prob']:.1%} | "
            f"{r['observed_win_freq']:.1%} | {int(r['count'])} |"
        )
    if png:
        lines += ["", f"Curva: `{png.name}` (la diagonal es calibracion perfecta).", ]
    lines += [
        "",
        "## Como leerlo",
        "",
        "- Si la frecuencia real sigue de cerca a la probabilidad predicha (columna a columna, o puntos sobre la diagonal), el modelo esta **bien calibrado**.",
        "- Si la frecuencia real es menor que la predicha en los bins altos, el modelo es **sobreconfiado**; si es mayor, es **conservador**.",
        "- ECE(victoria) bajo = mejor calibracion. log loss/Brier/RPS bajos = predicciones mas informativas.",
        "",
        "> No son certezas: el modelo da probabilidades. Esta vista mide su honestidad, no garantiza resultados.",
    ]
    report_path = out_dir / "live_calibration_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("=== Calibracion en vivo de la probabilidad de victoria ===\n")
    print("Mundial 2026 (en vivo):", _fmt_metrics(wc_summary))
    print(f"Referencia ({args.reference_months} meses):", _fmt_metrics(ref_summary))
    print(f"\nReportes: {report_path}")
    if png:
        print(f"Curva:    {png}")


if __name__ == "__main__":
    main()
