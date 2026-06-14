from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

from .features import FEATURE_COLUMNS
from .preprocessing import WORLD_CUP_NAME, temporal_train_test_split


OUTCOME_ORDER = ("H", "D", "A")
OUTCOME_TO_INDEX = {label: idx for idx, label in enumerate(OUTCOME_ORDER)}


def probabilities_to_frame(probabilities: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(probabilities, columns=list(OUTCOME_ORDER))


def multiclass_brier(y_true: pd.Series | np.ndarray, probabilities: np.ndarray) -> float:
    y = np.array([OUTCOME_TO_INDEX[str(label)] for label in y_true])
    one_hot = np.eye(len(OUTCOME_ORDER))[y]
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def ranked_probability_score(y_true: pd.Series | np.ndarray, probabilities: np.ndarray) -> float:
    """RPS multiclase ordinal (Constantinou & Fenton, 2012).

    Sensible a la distancia: penaliza menos un error "cercano" (local->empate) que uno
    "lejano" (local->visitante). Usa el orden ordinal H < D < A. Rango [0, 1]; menor mejor.
    """
    y = _to_index_safe(y_true)
    probs = np.clip(np.asarray(probabilities, dtype=float), 0.0, None)
    probs = probs / probs.sum(axis=1, keepdims=True)
    one_hot = np.eye(len(OUTCOME_ORDER))[y]
    cdf_pred = np.cumsum(probs, axis=1)
    cdf_true = np.cumsum(one_hot, axis=1)
    # Se suman (r-1) terminos; dividir por (r-1) deja el RPS en [0, 1].
    per_sample = np.sum((cdf_pred[:, :-1] - cdf_true[:, :-1]) ** 2, axis=1) / (len(OUTCOME_ORDER) - 1)
    return float(np.mean(per_sample))


def _to_index_safe(y_true: pd.Series | np.ndarray) -> np.ndarray:
    return np.array([OUTCOME_TO_INDEX[str(label)] for label in y_true], dtype=int)


def reliability_table(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    n_bins: int = 10,
) -> pd.DataFrame:
    """Tabla de fiabilidad (confianza media vs acierto real) por bin de confianza."""
    y = _to_index_safe(y_true)
    confidence = probabilities.max(axis=1)
    prediction = probabilities.argmax(axis=1)
    correct = (prediction == y).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for lower, upper in zip(bins[:-1], bins[1:]):
        mask = (confidence > lower) & (confidence <= upper)
        if not np.any(mask):
            continue
        rows.append(
            {
                "bin_lower": float(lower),
                "bin_upper": float(upper),
                "mean_confidence": float(confidence[mask].mean()),
                "empirical_accuracy": float(correct[mask].mean()),
                "count": int(mask.sum()),
            }
        )
    return pd.DataFrame(rows)


def expected_calibration_error(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    n_bins: int = 10,
) -> float:
    y = np.array([OUTCOME_TO_INDEX[str(label)] for label in y_true])
    confidence = probabilities.max(axis=1)
    prediction = probabilities.argmax(axis=1)
    correct = (prediction == y).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lower, upper in zip(bins[:-1], bins[1:]):
        mask = (confidence > lower) & (confidence <= upper)
        if not np.any(mask):
            continue
        ece += float(mask.mean()) * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return ece


def evaluate_probabilities(y_true: pd.Series | np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    clipped = np.clip(probabilities, 1e-12, 1.0)
    clipped = clipped / clipped.sum(axis=1, keepdims=True)
    y_labels = np.asarray(y_true).astype(str)
    y_index = np.array([OUTCOME_TO_INDEX[label] for label in y_labels], dtype=int)
    row_index = np.arange(len(y_index))
    return {
        "log_loss": float(-np.mean(np.log(clipped[row_index, y_index]))),
        "brier": multiclass_brier(y_labels, clipped),
        "rps": ranked_probability_score(y_labels, clipped),
        "accuracy": float(accuracy_score(y_labels, [OUTCOME_ORDER[i] for i in clipped.argmax(axis=1)])),
        "ece": expected_calibration_error(y_labels, clipped),
    }


@dataclass
class BaselineRateModel:
    probabilities_: np.ndarray | None = None

    def fit(self, frame: pd.DataFrame) -> "BaselineRateModel":
        rates = frame["outcome"].value_counts(normalize=True).reindex(OUTCOME_ORDER, fill_value=0.0)
        probs = rates.to_numpy(dtype=float)
        probs = np.clip(probs, 1e-6, 1.0)
        self.probabilities_ = probs / probs.sum()
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if self.probabilities_ is None:
            raise RuntimeError("Model is not fitted.")
        return np.tile(self.probabilities_, (len(frame), 1))


@dataclass
class EloFeatureModel:
    """Baseline that uses precomputed Elo probabilities from src.features."""

    def fit(self, frame: pd.DataFrame) -> "EloFeatureModel":
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        probs = frame[["elo_p_home_win", "elo_p_draw", "elo_p_away_win"]].to_numpy(dtype=float)
        probs = np.clip(probs, 1e-9, 1.0)
        return probs / probs.sum(axis=1, keepdims=True)


def temporal_backtest(
    matches: pd.DataFrame,
    model_builders: dict[str, Callable[[], object]],
    splits: list[tuple[str, str, str]],
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    features = feature_columns or FEATURE_COLUMNS
    for split_id, (train_start, test_start, test_end) in enumerate(splits, start=1):
        train_end = (pd.Timestamp(test_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        train, test = temporal_train_test_split(matches, train_start, train_end, test_start, test_end)
        if train.empty or test.empty:
            continue

        for model_name, builder in model_builders.items():
            model = builder()
            fit_frame = train.copy()
            test_frame = test.copy()
            if hasattr(model, "feature_columns"):
                model.feature_columns = features
            model.fit(fit_frame)
            probabilities = model.predict_proba(test_frame)
            metrics = evaluate_probabilities(test_frame["outcome"], probabilities)
            rows.append(
                {
                    "split_id": split_id,
                    "model": model_name,
                    "train_start": train["date"].min(),
                    "train_end": train["date"].max(),
                    "test_start": test["date"].min(),
                    "test_end": test["date"].max(),
                    "n_train": len(train),
                    "n_test": len(test),
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def tournament_edition_backtest(
    matches: pd.DataFrame,
    model_builders: dict[str, Callable[[], object]],
    editions: list[int],
    tournament: str = WORLD_CUP_NAME,
    train_start: str | None = None,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    features = feature_columns or FEATURE_COLUMNS
    ordered = matches.sort_values("date").copy()
    for edition in editions:
        test = ordered[(ordered["tournament"].eq(tournament)) & (ordered["date"].dt.year.eq(int(edition)))]
        if test.empty:
            continue
        train = ordered[ordered["date"] < test["date"].min()]
        if train_start is not None:
            train = train[train["date"] >= pd.Timestamp(train_start)]
        if train.empty:
            continue
        for model_name, builder in model_builders.items():
            model = builder()
            if hasattr(model, "feature_columns"):
                model.feature_columns = features
            model.fit(train)
            probabilities = model.predict_proba(test)
            metrics = evaluate_probabilities(test["outcome"], probabilities)
            rows.append(
                {
                    "edition": edition,
                    "model": model_name,
                    "train_start": train["date"].min(),
                    "train_end": train["date"].max(),
                    "test_start": test["date"].min(),
                    "test_end": test["date"].max(),
                    "n_train": len(train),
                    "n_test": len(test),
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def compare_against_baselines(
    scores: pd.DataFrame,
    candidate_model: str,
    baseline_models: tuple[str, ...] = ("baseline_rates", "elo_features"),
    metric: str = "log_loss",
) -> dict[str, object]:
    summary = scores.groupby("model")[metric].mean().sort_values()
    if candidate_model not in summary:
        raise ValueError(f"Candidate model {candidate_model!r} not found in scores.")
    candidate = float(summary.loc[candidate_model])
    baseline = float(summary.loc[list(baseline_models)].min())
    return {
        "candidate_model": candidate_model,
        "metric": metric,
        "candidate_score": candidate,
        "best_baseline_score": baseline,
        "beats_baseline": candidate < baseline,
        "ranking": summary,
    }
