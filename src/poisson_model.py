from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import poisson

from .preprocessing import add_time_weights


OUTCOME_ORDER = ("H", "D", "A")


@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    p_home_win: float
    p_draw: float
    p_away_win: float
    expected_goals_home: float
    expected_goals_away: float
    most_likely_score: tuple[int, int]
    home_goal_interval: tuple[int, int]
    away_goal_interval: tuple[int, int]
    uncertainty: str
    influential_variables: dict[str, float]

    @property
    def probabilities(self) -> dict[str, float]:
        return {"H": self.p_home_win, "D": self.p_draw, "A": self.p_away_win}


@dataclass
class TeamStrength:
    attack: float
    defense: float
    matches: float


@dataclass
class PoissonGoalModel:
    prior_matches: float = 8.0
    max_goals: int = 10
    dixon_coles_rho: float = 0.0
    fit_dixon_coles: bool = False
    global_home_rate: float = 1.35
    global_away_rate: float = 1.05
    strengths: dict[str, TeamStrength] = field(default_factory=dict)

    def fit(self, matches: pd.DataFrame, as_of: str | pd.Timestamp | None = None) -> "PoissonGoalModel":
        weighted = add_time_weights(matches, as_of=as_of)
        total_weight = float(weighted["weight"].sum()) if "weight" in weighted else float(len(weighted))
        if total_weight <= 0:
            raise ValueError("Cannot fit Poisson model with zero total weight.")

        self.global_home_rate = float((weighted["home_score"] * weighted["weight"]).sum() / total_weight)
        self.global_away_rate = float((weighted["away_score"] * weighted["weight"]).sum() / total_weight)
        global_goal_rate = (self.global_home_rate + self.global_away_rate) / 2.0
        global_goal_rate = max(global_goal_rate, 0.2)

        teams = sorted(set(weighted["home_team"]).union(weighted["away_team"]))
        strengths: dict[str, TeamStrength] = {}
        for team in teams:
            home = weighted[weighted["home_team"] == team]
            away = weighted[weighted["away_team"] == team]
            exposure = float(home["weight"].sum() + away["weight"].sum())
            goals_for = float((home["home_score"] * home["weight"]).sum() + (away["away_score"] * away["weight"]).sum())
            goals_against = float((home["away_score"] * home["weight"]).sum() + (away["home_score"] * away["weight"]).sum())
            gf_rate = (goals_for + self.prior_matches * global_goal_rate) / (exposure + self.prior_matches)
            ga_rate = (goals_against + self.prior_matches * global_goal_rate) / (exposure + self.prior_matches)
            attack = float(np.clip(gf_rate / global_goal_rate, 0.35, 2.75))
            defense = float(np.clip(ga_rate / global_goal_rate, 0.35, 2.75))
            strengths[team] = TeamStrength(attack=attack, defense=defense, matches=exposure)
        self.strengths = strengths

        if self.fit_dixon_coles:
            self.dixon_coles_rho = self._fit_rho(weighted)
        return self

    def team_strength(self, team: str) -> TeamStrength:
        return self.strengths.get(team, TeamStrength(attack=1.0, defense=1.0, matches=0.0))

    def expected_goals(self, home_team: str, away_team: str, neutral: bool = False) -> tuple[float, float]:
        home = self.team_strength(home_team)
        away = self.team_strength(away_team)
        if neutral:
            base_home = (self.global_home_rate + self.global_away_rate) / 2.0
            base_away = base_home
        else:
            base_home = self.global_home_rate
            base_away = self.global_away_rate
        lambda_home = base_home * home.attack * away.defense
        lambda_away = base_away * away.attack * home.defense
        return float(np.clip(lambda_home, 0.05, 5.5)), float(np.clip(lambda_away, 0.05, 5.5))

    def score_matrix(self, lambda_home: float, lambda_away: float) -> np.ndarray:
        goals = np.arange(self.max_goals + 1)
        matrix = np.outer(poisson.pmf(goals, lambda_home), poisson.pmf(goals, lambda_away))
        if abs(self.dixon_coles_rho) > 1e-12:
            matrix = self._apply_dixon_coles(matrix, lambda_home, lambda_away, self.dixon_coles_rho)
        matrix = np.clip(matrix, 0.0, None)
        return matrix / matrix.sum()

    @staticmethod
    def _tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
        if x == 0 and y == 0:
            return 1.0 - lambda_home * lambda_away * rho
        if x == 0 and y == 1:
            return 1.0 + lambda_home * rho
        if x == 1 and y == 0:
            return 1.0 + lambda_away * rho
        if x == 1 and y == 1:
            return 1.0 - rho
        return 1.0

    def _apply_dixon_coles(
        self,
        matrix: np.ndarray,
        lambda_home: float,
        lambda_away: float,
        rho: float,
    ) -> np.ndarray:
        adjusted = matrix.copy()
        for x in (0, 1):
            for y in (0, 1):
                adjusted[x, y] *= max(self._tau(x, y, lambda_home, lambda_away, rho), 0.01)
        return adjusted

    def _fit_rho(self, matches: pd.DataFrame) -> float:
        candidate_rhos = np.linspace(-0.20, 0.20, 41)
        best_rho = 0.0
        best_loss = math.inf
        for rho in candidate_rhos:
            old_rho = self.dixon_coles_rho
            self.dixon_coles_rho = float(rho)
            losses = []
            weights = []
            for row in matches.itertuples(index=False):
                if row.home_score > self.max_goals or row.away_score > self.max_goals:
                    continue
                lh, la = self.expected_goals(row.home_team, row.away_team, neutral=bool(row.neutral))
                p = self.score_matrix(lh, la)[int(row.home_score), int(row.away_score)]
                losses.append(-math.log(max(float(p), 1e-12)))
                weights.append(float(getattr(row, "weight", 1.0)))
            self.dixon_coles_rho = old_rho
            if losses:
                loss = float(np.average(losses, weights=weights))
                if loss < best_loss:
                    best_loss = loss
                    best_rho = float(rho)
        return best_rho

    def predict_match(self, home_team: str, away_team: str, neutral: bool = False) -> MatchPrediction:
        lambda_home, lambda_away = self.expected_goals(home_team, away_team, neutral=neutral)
        matrix = self.score_matrix(lambda_home, lambda_away)
        p_home = float(np.tril(matrix, -1).sum())
        p_draw = float(np.trace(matrix))
        p_away = float(np.triu(matrix, 1).sum())
        modal_index = np.unravel_index(np.argmax(matrix), matrix.shape)
        home_strength = self.team_strength(home_team)
        away_strength = self.team_strength(away_team)
        min_exposure = min(home_strength.matches, away_strength.matches)
        uncertainty = "alta" if min_exposure < 8 else "media" if min_exposure < 25 else "baja"
        influential = {
            "home_attack": home_strength.attack,
            "away_attack": away_strength.attack,
            "home_defense_allowed_rate": home_strength.defense,
            "away_defense_allowed_rate": away_strength.defense,
            "dixon_coles_rho": self.dixon_coles_rho,
            "neutral_venue": float(neutral),
        }
        return MatchPrediction(
            home_team=home_team,
            away_team=away_team,
            p_home_win=p_home,
            p_draw=p_draw,
            p_away_win=p_away,
            expected_goals_home=lambda_home,
            expected_goals_away=lambda_away,
            most_likely_score=(int(modal_index[0]), int(modal_index[1])),
            home_goal_interval=(
                int(poisson.ppf(0.05, lambda_home)),
                int(poisson.ppf(0.95, lambda_home)),
            ),
            away_goal_interval=(
                int(poisson.ppf(0.05, lambda_away)),
                int(poisson.ppf(0.95, lambda_away)),
            ),
            uncertainty=uncertainty,
            influential_variables=influential,
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
