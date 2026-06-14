"""Simulacion completa del Mundial 2026 y generacion de reportes.

Uso:
    python run_tournament.py                 # usa config.yaml
    python run_tournament.py --n 100000      # sobreescribe nº de simulaciones
    python run_tournament.py --as-of 2026-06-20

Produce:
    reports/wc2026_group_probabilities.csv
    reports/wc2026_tournament_probabilities.csv
    reports/wc2026_predictions.md
"""
from __future__ import annotations

import argparse
import time

import pandas as pd

from src.config import load_config
from src.data_sources_2026 import load_bracket, load_groups, load_third_place_table
from src.preprocessing import load_results
from src.reporting import save_reports
from src.tournament import build_predictor, run_tournament


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Simula el Mundial 2026 con Monte Carlo.")
    parser.add_argument("--n", type=int, default=int(cfg.get("simulation", "n_simulations", default=50000)))
    parser.add_argument("--as-of", default=str(cfg.get("model", "cutoff_date", default="2026-06-13")))
    parser.add_argument("--seed", type=int, default=int(cfg.get("simulation", "random_seed", default=2026)))
    args = parser.parse_args()

    results = load_results(cfg.path("data", "results_csv"))
    schedule = pd.read_csv(cfg.path("data", "wc2026_schedule"))
    bracket = load_bracket(cfg.path("data", "wc2026_bracket"))
    third_place = load_third_place_table(cfg.path("data", "third_place_table"))
    groups = load_groups(cfg.path("data", "wc2026_groups"))

    fit_dc = bool(cfg.get("model", "poisson", "fit_dixon_coles", default=True))
    temperature = float(cfg.get("calibration", "applied_temperature", default=1.0))
    penalty_scale = float(cfg.get("simulation", "penalty_elo_scale", default=0.65))

    print(f"Entrenando predictor (elo_live) hasta {args.as_of} ...")
    predictor = build_predictor(results, args.as_of, fit_dixon_coles=fit_dc, temperature=temperature)

    n_played = int((schedule["status"] == "played").sum())
    print(f"Partidos de grupos ya jugados (fijos): {n_played}/72")
    print(f"Corriendo {args.n} simulaciones (semilla {args.seed}) ...")
    t0 = time.time()
    summary = run_tournament(
        predictor, schedule, bracket, third_place,
        n_simulations=args.n, random_seed=args.seed, penalty_scale=penalty_scale,
        progress_every=max(args.n // 10, 1),
    )
    dt = time.time() - t0
    print(f"Listo en {dt:.1f}s. Emparejamientos de terceros fallidos: {summary.attrs['failed_assignments']}")

    paths = save_reports(summary, groups, cfg.path("reporting", "output_dir"), cutoff=args.as_of)
    print("\nReportes guardados:")
    for name, path in paths.items():
        print(f"  {name}: {path}")

    from src.reporting import tournament_report
    print("\n=== Probabilidad de campeon (top 10) ===")
    t = tournament_report(summary)
    show = t.head(10).copy()
    for col in [c for c in show.columns if c.startswith("p_")]:
        show[col] = (show[col] * 100).round(1)
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
