"""Backtesting temporal contra Mundiales 2014/2018/2022.

Reporta log loss, Brier, RPS, accuracy y ECE por modelo, y ejecuta un experimento
de calibracion ENTRENADA (aprende la temperatura en ediciones previas y la evalua
fuera de muestra), reemplazando las constantes hardcodeadas (auditoria C3).

El criterio de aceptacion: una mejora se conserva solo si baja log loss/Brier/RPS
o mejora calibracion (ECE) sin degradar las demas. Si no, se documenta y se descarta.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.bayesian_model import BayesianTeamStrengthModel
from src.calibration import TemperatureScaling, apply_temperature
from src.config import load_config
from src.elo_model import EloModel
from src.evaluation import (
    BaselineRateModel,
    EloFeatureModel,
    evaluate_probabilities,
    tournament_edition_backtest,
)
from src.features import make_supervised_matches
from src.ml_model import MLOutcomeModel
from src.poisson_model import PoissonGoalModel
from src.preprocessing import load_results, temporal_filter

METRIC_COLS = ["log_loss", "brier", "rps", "accuracy", "ece"]


def model_comparison(features: pd.DataFrame, editions: list[int], train_start: str) -> pd.DataFrame:
    models = {
        "baseline_rates": lambda: BaselineRateModel(),
        "elo_static_pre_tournament": lambda: EloModel(),
        "elo_features_live": lambda: EloFeatureModel(),
        "poisson_simple": lambda: PoissonGoalModel(fit_dixon_coles=False),
        "bayesian_gamma_poisson": lambda: BayesianTeamStrengthModel(),
        "ml_hist_gradient_boosting": lambda: MLOutcomeModel(use_xgboost_if_available=False, n_estimators=60),
    }
    return tournament_edition_backtest(features, models, editions=editions, train_start=train_start)


def calibration_experiment(
    features: pd.DataFrame,
    fit_on: list[int],
    evaluate_on: list[int],
) -> tuple[pd.DataFrame, float]:
    """Aprende la temperatura sobre `fit_on` y la evalua en `evaluate_on`.

    Usa las probabilidades Elo live (elo_p_*), que son el modelo operativo durante el
    torneo. Honesto: el ajuste nunca toca la edicion evaluada.
    """
    elo_cols = ["elo_p_home_win", "elo_p_draw", "elo_p_away_win"]

    def edition_probs(years: list[int]) -> tuple[np.ndarray, pd.Series]:
        frames = [features[(features["tournament"] == "FIFA World Cup") & (features["date"].dt.year == y)] for y in years]
        block = pd.concat(frames)
        probs = block[elo_cols].to_numpy(dtype=float)
        probs = np.clip(probs, 1e-9, 1.0)
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs, block["outcome"]

    fit_probs, fit_y = edition_probs(fit_on)
    test_probs, test_y = edition_probs(evaluate_on)

    calibrator = TemperatureScaling().fit(fit_probs, fit_y)
    raw_metrics = evaluate_probabilities(test_y, test_probs)
    cal_metrics = evaluate_probabilities(test_y, apply_temperature(test_probs, calibrator.temperature))

    table = pd.DataFrame(
        [
            {"model": "elo_live_raw", **raw_metrics},
            {"model": "elo_live_temperature_calibrated", **cal_metrics},
        ]
    )
    return table, calibrator.temperature


def main() -> None:
    cfg = load_config()
    root = Path(__file__).resolve().parent
    train_start = str(cfg.get("model", "train_start", default="2010-01-01"))
    editions = list(cfg.get("evaluation", "backtest_editions", default=[2014, 2018, 2022]))

    results = temporal_filter(load_results(cfg.path("data", "results_csv")), start=train_start)
    features = make_supervised_matches(results)

    print(f"=== Comparacion de modelos (Mundiales {editions}, train desde {train_start}) ===")
    scores = model_comparison(features, editions, train_start)
    out = root / "reports/backtest_worldcups_2014_2018_2022.csv"
    scores.to_csv(out, index=False)
    print(scores[["edition", "model"] + METRIC_COLS].to_string(index=False))
    print("\nPromedio por modelo (ordenado por log loss):")
    print(scores.groupby("model")[METRIC_COLS].mean().sort_values("log_loss").to_string())

    print("\n=== Experimento de calibracion entrenada ===")
    fit_on = list(cfg.get("calibration", "fit_on", default=[2014, 2018]))
    evaluate_on = list(cfg.get("calibration", "evaluate_on", default=[2022]))
    cal_table, temperature = calibration_experiment(features, fit_on, evaluate_on)
    print(f"Temperatura aprendida en {fit_on}, evaluada en {evaluate_on}: T = {temperature:.4f}")
    print(cal_table[["model"] + METRIC_COLS].to_string(index=False))
    cal_table.to_csv(root / "reports/calibration_experiment.csv", index=False)

    raw = cal_table.iloc[0]
    cal = cal_table.iloc[1]
    verdict = []
    for m in ["log_loss", "brier", "rps", "ece"]:
        better = cal[m] < raw[m]
        verdict.append(f"{m}: {'MEJORA' if better else 'no mejora'} ({raw[m]:.4f} -> {cal[m]:.4f})")
    print("\nVeredicto de calibracion (gate de aceptacion):")
    for line in verdict:
        print("  -", line)
    print(f"\nGuardado en: {out} y reports/calibration_experiment.csv")


if __name__ == "__main__":
    main()
