from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .preprocessing import tournament_importance


OUTCOME_ORDER = ("H", "D", "A")


@dataclass
class EloConfig:
    initial_rating: float = 1500.0
    k_factor: float = 20.0
    home_advantage: float = 60.0
    draw_base_rate: float = 0.27
    draw_decay: float = 500.0
    max_margin_multiplier: float = 2.5
    importance_scale: float = 0.25


@dataclass
class EloPrediction:
    home_team: str
    away_team: str
    p_home_win: float
    p_draw: float
    p_away_win: float
    rating_home: float
    rating_away: float
    rating_diff: float

    @property
    def probabilities(self) -> dict[str, float]:
        return {"H": self.p_home_win, "D": self.p_draw, "A": self.p_away_win}


@dataclass
class EloModel:
    config: EloConfig = field(default_factory=EloConfig)
    ratings: dict[str, float] = field(default_factory=dict)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self.config.initial_rating)

    def expected_score(self, home_team: str, away_team: str, neutral: bool = False) -> float:
        diff = self.rating(home_team) - self.rating(away_team)
        if not neutral:
            diff += self.config.home_advantage
        return 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

    def predict_match(self, home_team: str, away_team: str, neutral: bool = False) -> EloPrediction:
        rating_home = self.rating(home_team)
        rating_away = self.rating(away_team)
        diff = rating_home - rating_away + (0.0 if neutral else self.config.home_advantage)
        expected = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))
        draw = self.config.draw_base_rate * math.exp(-abs(diff) / self.config.draw_decay)
        draw = float(np.clip(draw, 0.08, 0.34))
        home_win = expected - 0.5 * draw
        away_win = 1.0 - expected - 0.5 * draw
        probs = np.array([home_win, draw, away_win], dtype=float)
        probs = np.clip(probs, 1e-6, 1.0)
        probs = probs / probs.sum()
        return EloPrediction(
            home_team=home_team,
            away_team=away_team,
            p_home_win=float(probs[0]),
            p_draw=float(probs[1]),
            p_away_win=float(probs[2]),
            rating_home=rating_home,
            rating_away=rating_away,
            rating_diff=diff,
        )

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        rows = []
        for row in frame.itertuples(index=False):
            pred = self.predict_match(
                row.home_team,
                row.away_team,
                neutral=bool(getattr(row, "neutral", False)),
            )
            rows.append([pred.p_home_win, pred.p_draw, pred.p_away_win])
        probabilities = np.asarray(rows, dtype=float)
        probabilities = np.clip(probabilities, 1e-12, 1.0)
        return probabilities / probabilities.sum(axis=1, keepdims=True)

    def update_match(
        self,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        tournament: str = "",
        neutral: bool = False,
    ) -> None:
        expected = self.expected_score(home_team, away_team, neutral=neutral)
        actual = 1.0 if home_score > away_score else 0.0 if home_score < away_score else 0.5
        goal_diff = abs(home_score - away_score)
        margin = 1.0 if goal_diff <= 1 else math.log(goal_diff + 1.0)
        margin = min(margin, self.config.max_margin_multiplier)
        importance = 1.0 + self.config.importance_scale * max(tournament_importance(tournament) - 1.0, 0.0)
        change = self.config.k_factor * importance * margin * (actual - expected)
        self.ratings[home_team] = self.rating(home_team) + change
        self.ratings[away_team] = self.rating(away_team) - change

    def fit(self, matches: pd.DataFrame) -> "EloModel":
        for row in matches.sort_values("date").itertuples(index=False):
            self.update_match(
                row.home_team,
                row.away_team,
                int(row.home_score),
                int(row.away_score),
                tournament=getattr(row, "tournament", ""),
                neutral=bool(getattr(row, "neutral", False)),
            )
        return self

    def to_frame(self) -> pd.DataFrame:
        return (
            pd.DataFrame(
                [{"team": team, "elo_rating": rating} for team, rating in self.ratings.items()]
            )
            .sort_values("elo_rating", ascending=False)
            .reset_index(drop=True)
        )


def add_elo_features(matches: pd.DataFrame, config: EloConfig | None = None) -> pd.DataFrame:
    model = EloModel(config or EloConfig())
    rows: list[dict[str, Any]] = []
    for idx, row in matches.sort_values("date").iterrows():
        pred = model.predict_match(row["home_team"], row["away_team"], neutral=bool(row["neutral"]))
        rows.append(
            {
                "index": idx,
                "elo_home": pred.rating_home,
                "elo_away": pred.rating_away,
                "elo_diff": pred.rating_diff,
                "elo_p_home_win": pred.p_home_win,
                "elo_p_draw": pred.p_draw,
                "elo_p_away_win": pred.p_away_win,
            }
        )
        model.update_match(
            row["home_team"],
            row["away_team"],
            int(row["home_score"]),
            int(row["away_score"]),
            tournament=str(row.get("tournament", "")),
            neutral=bool(row["neutral"]),
        )
    feature_frame = pd.DataFrame(rows).set_index("index")
    return matches.join(feature_frame, how="left")
