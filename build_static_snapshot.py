from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.elo_model import EloModel
from src.poisson_model import PoissonGoalModel
from src.preprocessing import load_results


ROOT = Path(__file__).resolve().parent
DEFAULT_CUTOFF = "2026-06-13"


def main() -> None:
    results = load_results(ROOT / "data/raw/results.csv")
    cutoff = pd.Timestamp(DEFAULT_CUTOFF)
    train = results[results["date"] <= cutoff].copy()
    elo = EloModel().fit(train)
    poisson = PoissonGoalModel(fit_dixon_coles=False).fit(train, as_of=cutoff)

    teams = sorted(set(train["home_team"]).union(train["away_team"]))
    team_rows = []
    for team in teams:
        strength = poisson.team_strength(team)
        team_rows.append(
            {
                "team": team,
                "elo": elo.rating(team),
                "attack": strength.attack,
                "defense": strength.defense,
                "matches": strength.matches,
            }
        )

    backtest_path = ROOT / "reports/backtest_worldcups_2014_2018_2022.csv"
    backtest_rows = []
    if backtest_path.exists():
        scores = pd.read_csv(backtest_path)
        summary = (
            scores.groupby("model")[["log_loss", "brier", "accuracy", "ece"]]
            .mean()
            .sort_values("log_loss")
            .reset_index()
        )
        backtest_rows = summary.to_dict(orient="records")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of": DEFAULT_CUTOFF,
        "n_train_matches": int(len(train)),
        "max_train_date": train["date"].max().strftime("%Y-%m-%d"),
        "snapshot_max_date": results["date"].max().strftime("%Y-%m-%d"),
        "global_home_rate": poisson.global_home_rate,
        "global_away_rate": poisson.global_away_rate,
        "elo_home_advantage": elo.config.home_advantage,
        "elo_draw_base_rate": elo.config.draw_base_rate,
        "elo_draw_decay": elo.config.draw_decay,
        "teams": team_rows,
        "backtest": backtest_rows,
        "model_decision": (
            "Backtesting 2014-2018-2022 favorecio Elo para 1X2; "
            "Poisson se usa para goles esperados e intervalos."
        ),
    }

    out = ROOT / "static/model_snapshot.js"
    out.write_text(
        "window.MODEL_SNAPSHOT = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Snapshot escrito en: {out}")
    print(f"Equipos: {len(team_rows)}")
    print(f"Partidos entrenamiento: {len(train)}")


if __name__ == "__main__":
    main()
