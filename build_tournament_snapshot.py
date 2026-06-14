"""Genera el snapshot estatico de probabilidades del torneo para la web.

Corre la simulacion Monte Carlo y escribe un JSON que la web de Vercel sirve como
archivo estatico (la simulacion en si no cabe en una funcion serverless: es Python
pesado de ~minutos). Se regenera localmente y se redespliega tras cada jornada.

Uso:
    python build_tournament_snapshot.py            # n desde config.yaml
    python build_tournament_snapshot.py --n 30000  # mas rapido
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.data_sources_2026 import load_bracket, load_groups, load_third_place_table
from src.preprocessing import load_results
from src.reporting import group_report, tournament_report, UNCERTAINTY_DISCLAIMER
from src.tournament import build_predictor, run_tournament

ROOT = Path(__file__).resolve().parent
# La web Vercel (vercel-app) y la copia raiz sirven public/ en la raiz del dominio.
TARGETS = [ROOT / "vercel-app" / "public" / "tournament_snapshot.json",
           ROOT / "public" / "tournament_snapshot.json"]


def main() -> None:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Construye el snapshot del torneo para la web.")
    parser.add_argument("--n", type=int, default=int(cfg.get("simulation", "n_simulations", default=50000)))
    parser.add_argument("--as-of", default=str(cfg.get("model", "cutoff_date", default="2026-06-13")))
    parser.add_argument("--seed", type=int, default=int(cfg.get("simulation", "random_seed", default=2026)))
    args = parser.parse_args()

    results = load_results(cfg.path("data", "results_csv"))
    schedule = pd.read_csv(cfg.path("data", "wc2026_schedule"))
    bracket = load_bracket(cfg.path("data", "wc2026_bracket"))
    third = load_third_place_table(cfg.path("data", "third_place_table"))
    groups = load_groups(cfg.path("data", "wc2026_groups"))

    fit_dc = bool(cfg.get("model", "poisson", "fit_dixon_coles", default=False))
    print(f"Entrenando predictor (elo_live) hasta {args.as_of} ...")
    predictor = build_predictor(results, args.as_of, fit_dixon_coles=fit_dc)
    n_played = int((schedule["status"] == "played").sum())
    print(f"Simulando {args.n} veces (jugados fijos: {n_played}/72) ...")
    summary = run_tournament(predictor, schedule, bracket, third,
                             n_simulations=args.n, random_seed=args.seed,
                             penalty_scale=float(cfg.get("simulation", "penalty_elo_scale", default=0.65)),
                             progress_every=max(args.n // 5, 1))

    t = tournament_report(summary)
    g = group_report(summary, groups)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of": args.as_of,
        "n_simulations": args.n,
        "model": "elo_live_v3",
        "matches_played": n_played,
        "disclaimer": UNCERTAINTY_DISCLAIMER,
        "tournament": [
            {
                "team": r["team"],
                "p_champion": round(float(r["p_champion"]), 4),
                "p_final": round(float(r["p_final"]), 4),
                "p_semifinal": round(float(r["p_semifinal"]), 4),
                "p_quarterfinal": round(float(r["p_quarterfinal"]), 4),
                "p_round_of_16": round(float(r["p_round_of_16"]), 4),
                "p_round_of_32": round(float(r["p_round_of_32"]), 4),
            }
            for _, r in t.iterrows()
        ],
        "groups": {
            str(group): [
                {
                    "team": r["team"],
                    "p_1st": round(float(r["p_1st"]), 4),
                    "p_2nd": round(float(r["p_2nd"]), 4),
                    "p_3rd": round(float(r["p_3rd"]), 4),
                    "p_4th": round(float(r["p_4th"]), 4),
                    "p_qualify": round(float(r["p_qualify"]), 4),
                }
                for _, r in g[g["group"] == group].iterrows()
            ]
            for group in sorted(g["group"].unique())
        },
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"Escrito: {target}")
    print(f"Campeon top: {payload['tournament'][0]['team']} {payload['tournament'][0]['p_champion']:.1%}")


if __name__ == "__main__":
    main()
