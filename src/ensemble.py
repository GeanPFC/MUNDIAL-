from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from .evaluation import OUTCOME_ORDER


class ProbabilityModel(Protocol):
    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        ...


def normalize_probabilities(probabilities: np.ndarray) -> np.ndarray:
    probs = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)
    return probs / probs.sum(axis=1, keepdims=True)


@dataclass
class ProbabilityEnsemble:
    models: dict[str, ProbabilityModel] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    validation_report: pd.DataFrame | None = None

    def fit(self, frame: pd.DataFrame) -> "ProbabilityEnsemble":
        for model in self.models.values():
            if hasattr(model, "fit"):
                model.fit(frame)
        if not self.weights:
            n = max(len(self.models), 1)
            self.weights = {name: 1.0 / n for name in self.models}
        self._validate_weights()
        return self

    def _validate_weights(self) -> None:
        missing = set(self.models) - set(self.weights)
        if missing:
            raise ValueError(f"Missing ensemble weights for: {sorted(missing)}")
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("Ensemble weights must sum to a positive number.")
        self.weights = {name: weight / total for name, weight in self.weights.items()}

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        self._validate_weights()
        combined = np.zeros((len(frame), len(OUTCOME_ORDER)), dtype=float)
        for name, model in self.models.items():
            combined += self.weights[name] * normalize_probabilities(model.predict_proba(frame))
        return normalize_probabilities(combined)

    @classmethod
    def from_backtest(
        cls,
        models: dict[str, ProbabilityModel],
        scores: pd.DataFrame,
        metric: str = "log_loss",
        temperature: float = 12.0,
    ) -> "ProbabilityEnsemble":
        means = scores.groupby("model")[metric].mean()
        eligible = means.loc[means.index.intersection(models.keys())].dropna()
        if eligible.empty:
            raise ValueError("No model scores available to build ensemble weights.")
        raw = np.exp(-temperature * (eligible - eligible.min()))
        weights = (raw / raw.sum()).to_dict()
        return cls(models={name: models[name] for name in eligible.index}, weights=weights, validation_report=scores)


def assert_candidate_beats_baseline(
    scores: pd.DataFrame,
    candidate_model: str,
    baseline_models: tuple[str, ...],
    metric: str = "log_loss",
    min_improvement: float = 0.0,
) -> None:
    means = scores.groupby("model")[metric].mean()
    candidate = float(means.loc[candidate_model])
    baseline = float(means.loc[list(baseline_models)].min())
    if candidate >= baseline - min_improvement:
        raise ValueError(
            f"{candidate_model} failed validation on {metric}: "
            f"{candidate:.4f} vs best baseline {baseline:.4f}."
        )
