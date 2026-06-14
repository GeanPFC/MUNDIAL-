from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.elo_model import EloModel
from src.poisson_model import PoissonGoalModel
from src.preprocessing import load_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict one international match with validated base models.")
    parser.add_argument("team_a", help="Equipo A/local nominal.")
    parser.add_argument("team_b", help="Equipo B/visitante nominal.")
    parser.add_argument("--as-of", default="2026-06-13", help="Fecha de corte YYYY-MM-DD.")
    parser.add_argument("--neutral", action="store_true", help="Usar sede neutral.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    cutoff = pd.Timestamp(args.as_of)
    results = load_results(root / "data/raw/results.csv")
    train = results[results["date"] <= cutoff].copy()
    if train.empty:
        raise SystemExit("No hay datos antes de la fecha de corte.")

    elo = EloModel().fit(train)
    poisson = PoissonGoalModel(fit_dixon_coles=False).fit(train, as_of=cutoff)
    elo_pred = elo.predict_match(args.team_a, args.team_b, neutral=args.neutral)
    goal_pred = poisson.predict_match(args.team_a, args.team_b, neutral=args.neutral)

    print(f"Fecha de corte: {args.as_of}")
    print(f"Partido: {args.team_a} vs {args.team_b}")
    print("\nProbabilidades 1X2 principales, basadas en Elo:")
    print(f"Victoria {args.team_a}: {elo_pred.p_home_win:.3f}")
    print(f"Empate: {elo_pred.p_draw:.3f}")
    print(f"Victoria {args.team_b}: {elo_pred.p_away_win:.3f}")
    print("\nGoles esperados y marcador modal, basados en Poisson:")
    print(f"xG {args.team_a}: {goal_pred.expected_goals_home:.2f}")
    print(f"xG {args.team_b}: {goal_pred.expected_goals_away:.2f}")
    print(f"Marcador mas probable: {goal_pred.most_likely_score[0]}-{goal_pred.most_likely_score[1]}")
    print(f"Intervalo goles {args.team_a}: {goal_pred.home_goal_interval}")
    print(f"Intervalo goles {args.team_b}: {goal_pred.away_goal_interval}")
    print(f"Incertidumbre: {goal_pred.uncertainty}")
    print("\nVariables principales:")
    print(f"Elo {args.team_a}: {elo_pred.rating_home:.1f}")
    print(f"Elo {args.team_b}: {elo_pred.rating_away:.1f}")
    print(f"Diferencia Elo ajustada: {elo_pred.rating_diff:.1f}")
    for key, value in goal_pred.influential_variables.items():
        print(f"{key}: {value:.3f}")


if __name__ == "__main__":
    main()
