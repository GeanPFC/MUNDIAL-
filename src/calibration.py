"""Calibracion entrenada de probabilidades 1X2.

Sustituye las constantes hardcodeadas del modelo desplegado (temperature/draw
multiplier puestos a mano) por calibradores que se *ajustan* sobre un conjunto de
validacion temporal y se *evaluan* fuera de muestra.

Metodos:
  - TemperatureScaling: un parametro T, p_cal proporcional a p^(1/T). Suaviza (T>1)
    o agudiza (T<1) la confianza. Multiclase, conserva el orden de probabilidades.
  - IsotonicPerClass: calibracion no parametrica monotona one-vs-rest con
    renormalizacion. Mas flexible, necesita mas datos.

Regla de uso honesto (anti-leakage): el calibrador se ajusta en ediciones ANTERIORES
a la edicion evaluada. Nunca en la misma edicion de test.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression

OUTCOME_ORDER = ("H", "D", "A")
OUTCOME_TO_INDEX = {label: idx for idx, label in enumerate(OUTCOME_ORDER)}


def _to_index(y_true) -> np.ndarray:
    return np.array([OUTCOME_TO_INDEX[str(label)] for label in y_true], dtype=int)


def _normalize(probs: np.ndarray) -> np.ndarray:
    clipped = np.clip(probs, 1e-12, 1.0)
    return clipped / clipped.sum(axis=1, keepdims=True)


def apply_temperature(probs: np.ndarray, temperature: float) -> np.ndarray:
    """p_cal proporcional a p^(1/T), renormalizado por fila."""
    t = max(float(temperature), 1e-6)
    powered = np.power(np.clip(probs, 1e-12, 1.0), 1.0 / t)
    return _normalize(powered)


def _log_loss(probs: np.ndarray, y_idx: np.ndarray) -> float:
    p = _normalize(probs)
    rows = np.arange(len(y_idx))
    return float(-np.mean(np.log(np.clip(p[rows, y_idx], 1e-12, 1.0))))


@dataclass
class TemperatureScaling:
    """Calibrador de un parametro. Aprende T minimizando log loss en validacion."""

    temperature: float = 1.0
    fitted_: bool = False

    def fit(self, probs: np.ndarray, y_true) -> "TemperatureScaling":
        y_idx = _to_index(y_true)
        probs = np.asarray(probs, dtype=float)

        def objective(log_t: float) -> float:
            t = np.exp(log_t)  # garantiza T > 0
            return _log_loss(apply_temperature(probs, t), y_idx)

        result = minimize_scalar(objective, bounds=(np.log(0.3), np.log(5.0)), method="bounded")
        self.temperature = float(np.exp(result.x))
        self.fitted_ = True
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        return apply_temperature(np.asarray(probs, dtype=float), self.temperature)

    def fit_transform(self, probs: np.ndarray, y_true) -> np.ndarray:
        return self.fit(probs, y_true).transform(probs)


@dataclass
class IsotonicPerClass:
    """Calibracion isotonica one-vs-rest por clase, con renormalizacion final."""

    models_: list[IsotonicRegression] | None = None

    def fit(self, probs: np.ndarray, y_true) -> "IsotonicPerClass":
        y_idx = _to_index(y_true)
        probs = np.asarray(probs, dtype=float)
        self.models_ = []
        for cls in range(len(OUTCOME_ORDER)):
            target = (y_idx == cls).astype(float)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(probs[:, cls], target)
            self.models_.append(iso)
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        if self.models_ is None:
            raise RuntimeError("IsotonicPerClass no esta ajustado.")
        probs = np.asarray(probs, dtype=float)
        out = np.column_stack([self.models_[c].predict(probs[:, c]) for c in range(len(OUTCOME_ORDER))])
        return _normalize(out)

    def fit_transform(self, probs: np.ndarray, y_true) -> np.ndarray:
        return self.fit(probs, y_true).transform(probs)


def build_calibrator(method: str):
    method = (method or "none").lower()
    if method == "temperature":
        return TemperatureScaling()
    if method == "isotonic":
        return IsotonicPerClass()
    if method == "none":
        return None
    raise ValueError(f"Metodo de calibracion no soportado: {method!r}")
