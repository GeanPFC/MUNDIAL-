from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .poisson_model import MatchPrediction, PoissonGoalModel
from .preprocessing import add_time_weights


@dataclass
class GammaPosterior:
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        return self.alpha / self.beta

    @property
    def variance(self) -> float:
        return self.alpha / (self.beta**2)

    @property
    def coefficient_of_variation(self) -> float:
        return float(np.sqrt(self.variance) / max(self.mean, 1e-9))


@dataclass
class BayesianTeamStrengthModel:
    prior_matches: float = 10.0
    max_goals: int = 10
    global_goal_rate: float = 1.2
    attack_posteriors: dict[str, GammaPosterior] = field(default_factory=dict)
    defense_posteriors: dict[str, GammaPosterior] = field(default_factory=dict)
    poisson_proxy: PoissonGoalModel = field(default_factory=PoissonGoalModel)

    def fit(self, matches: pd.DataFrame, as_of: str | pd.Timestamp | None = None) -> "BayesianTeamStrengthModel":
        weighted = add_time_weights(matches, as_of=as_of)
        total_weight = max(float(weighted["weight"].sum()), 1e-9)
        total_goals = float(((weighted["home_score"] + weighted["away_score"]) * weighted["weight"]).sum())
        self.global_goal_rate = max(total_goals / (2.0 * total_weight), 0.2)
        alpha_prior = self.global_goal_rate * self.prior_matches
        beta_prior = self.prior_matches

        teams = sorted(set(weighted["home_team"]).union(weighted["away_team"]))
        for team in teams:
            home = weighted[weighted["home_team"] == team]
            away = weighted[weighted["away_team"] == team]
            exposure = float(home["weight"].sum() + away["weight"].sum())
            goals_for = float((home["home_score"] * home["weight"]).sum() + (away["away_score"] * away["weight"]).sum())
            goals_against = float((home["away_score"] * home["weight"]).sum() + (away["home_score"] * away["weight"]).sum())
            self.attack_posteriors[team] = GammaPosterior(alpha_prior + goals_for, beta_prior + exposure)
            self.defense_posteriors[team] = GammaPosterior(alpha_prior + goals_against, beta_prior + exposure)

        self.poisson_proxy = PoissonGoalModel(prior_matches=self.prior_matches, max_goals=self.max_goals)
        self.poisson_proxy.fit(matches, as_of=as_of)
        return self

    def posterior(self, team: str, kind: str) -> GammaPosterior:
        mapping = self.attack_posteriors if kind == "attack" else self.defense_posteriors
        return mapping.get(
            team,
            GammaPosterior(
                alpha=max(self.global_goal_rate * self.prior_matches, 1e-6),
                beta=self.prior_matches,
            ),
        )

    def update_after_match(
        self,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        weight: float = 1.0,
    ) -> None:
        for team, gf, ga in (
            (home_team, home_score, away_score),
            (away_team, away_score, home_score),
        ):
            attack = self.posterior(team, "attack")
            defense = self.posterior(team, "defense")
            self.attack_posteriors[team] = GammaPosterior(attack.alpha + weight * gf, attack.beta + weight)
            self.defense_posteriors[team] = GammaPosterior(defense.alpha + weight * ga, defense.beta + weight)

    def predict_match(self, home_team: str, away_team: str, neutral: bool = False) -> MatchPrediction:
        attack_home = self.posterior(home_team, "attack")
        attack_away = self.posterior(away_team, "attack")
        defense_home = self.posterior(home_team, "defense")
        defense_away = self.posterior(away_team, "defense")

        pred = self.poisson_proxy.predict_match(home_team, away_team, neutral=neutral)
        uncertainty_score = np.mean(
            [
                attack_home.coefficient_of_variation,
                attack_away.coefficient_of_variation,
                defense_home.coefficient_of_variation,
                defense_away.coefficient_of_variation,
            ]
        )
        pred.influential_variables.update(
            {
                "posterior_attack_home_cv": attack_home.coefficient_of_variation,
                "posterior_attack_away_cv": attack_away.coefficient_of_variation,
                "posterior_defense_home_cv": defense_home.coefficient_of_variation,
                "posterior_defense_away_cv": defense_away.coefficient_of_variation,
            }
        )
        pred.uncertainty = "alta" if uncertainty_score > 0.35 else "media" if uncertainty_score > 0.20 else "baja"
        return pred

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
