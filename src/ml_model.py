from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS


OUTCOME_ORDER = ("H", "D", "A")


@dataclass
class MLOutcomeModel:
    feature_columns: list[str] = field(default_factory=lambda: FEATURE_COLUMNS.copy())
    random_state: int = 2026
    use_xgboost_if_available: bool = True
    n_estimators: int = 120
    learning_rate: float = 0.04
    model: object | None = None

    def _build_model(self) -> object:
        if self.use_xgboost_if_available:
            try:
                from xgboost import XGBClassifier

                return XGBClassifier(
                    objective="multi:softprob",
                    num_class=3,
                    n_estimators=250,
                    learning_rate=0.035,
                    max_depth=3,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    reg_lambda=4.0,
                    eval_metric="mlogloss",
                    random_state=self.random_state,
                )
            except Exception:
                pass
        return Pipeline(
            steps=[
                ("scale", StandardScaler()),
                (
                    "hgb",
                    HistGradientBoostingClassifier(
                        max_iter=self.n_estimators,
                        learning_rate=self.learning_rate,
                        max_leaf_nodes=15,
                        l2_regularization=0.5,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )

    def _xy(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
        missing = set(self.feature_columns) - set(frame.columns)
        if missing:
            raise ValueError(f"Missing feature columns: {sorted(missing)}")
        x = frame[self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        y = frame["outcome"].map({label: idx for idx, label in enumerate(OUTCOME_ORDER)}).to_numpy()
        return x, y

    def fit(self, frame: pd.DataFrame) -> "MLOutcomeModel":
        x, y = self._xy(frame)
        self.model = self._build_model()
        self.model.fit(x, y)
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model is not fitted.")
        x = frame[self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        probabilities = self.model.predict_proba(x)
        ordered = np.zeros((len(frame), len(OUTCOME_ORDER)))
        classes = getattr(self.model, "classes_", None)
        if classes is None and hasattr(self.model, "named_steps"):
            classes = self.model.named_steps["hgb"].classes_
        for source_idx, cls in enumerate(classes):
            ordered[:, int(cls)] = probabilities[:, source_idx]
        ordered = np.clip(ordered, 1e-9, 1.0)
        return ordered / ordered.sum(axis=1, keepdims=True)

    def feature_importance(self, frame: pd.DataFrame, n_repeats: int = 8) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model is not fitted.")
        x, y = self._xy(frame)
        result = permutation_importance(
            self.model,
            x,
            y,
            n_repeats=n_repeats,
            random_state=self.random_state,
            scoring="neg_log_loss",
        )
        return (
            pd.DataFrame(
                {
                    "feature": self.feature_columns,
                    "importance_mean": result.importances_mean,
                    "importance_std": result.importances_std,
                }
            )
            .sort_values("importance_mean", ascending=False)
            .reset_index(drop=True)
        )
