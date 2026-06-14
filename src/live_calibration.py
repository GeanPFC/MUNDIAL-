"""Seguimiento de calibracion en vivo de la probabilidad de victoria.

La pregunta que responde: cuando el modelo dice "este equipo tiene X% de ganar",
¿gana cerca del X% de las veces? Eso es lo que valida (o no) un modelo de
probabilidad, mas alla de acertar partidos sueltos.

Metodo honesto (sin leakage): para cada partido se usa SOLO la informacion previa.
Se recorre todo el historico en orden cronologico con Elo incremental: antes de
actualizar con un resultado, se registra la prediccion pre-partido. Asi cada
probabilidad refleja unicamente partidos anteriores.

Dos vistas:
  - Mundial 2026 en vivo: solo los partidos del torneo ya jugados (se acumula).
  - Referencia: ventana de partidos internacionales recientes (muestra grande ya).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .elo_model import EloModel, EloConfig
from .evaluation import evaluate_probabilities

OUTCOME_ORDER = ("H", "D", "A")


def walkforward_predictions(
    results: pd.DataFrame,
    eval_start: str | pd.Timestamp,
    eval_end: str | pd.Timestamp,
    tournament: str | None = None,
    elo_config: EloConfig | None = None,
) -> pd.DataFrame:
    """Predicciones pre-partido (Elo walk-forward) para los partidos de la ventana.

    Recorre TODO el historico actualizando Elo en orden; registra la prediccion solo
    para los partidos dentro de [eval_start, eval_end] (y del torneo dado si se filtra).
    """
    eval_start = pd.Timestamp(eval_start)
    eval_end = pd.Timestamp(eval_end)
    elo = EloModel(elo_config or EloConfig())
    ordered = results.sort_values("date")
    rows: list[dict] = []
    for r in ordered.itertuples(index=False):
        in_window = eval_start <= r.date <= eval_end
        if tournament is not None:
            in_window = in_window and getattr(r, "tournament", "") == tournament
        if in_window:
            pred = elo.predict_match(r.home_team, r.away_team, neutral=bool(r.neutral))
            actual = "H" if r.home_score > r.away_score else "A" if r.home_score < r.away_score else "D"
            probs = {"H": pred.p_home_win, "D": pred.p_draw, "A": pred.p_away_win}
            rows.append(
                {
                    "date": r.date,
                    "home_team": r.home_team,
                    "away_team": r.away_team,
                    "tournament": getattr(r, "tournament", ""),
                    "p_home_win": pred.p_home_win,
                    "p_draw": pred.p_draw,
                    "p_away_win": pred.p_away_win,
                    "home_score": int(r.home_score),
                    "away_score": int(r.away_score),
                    "outcome": actual,
                    "p_assigned_to_actual": probs[actual],
                    "predicted": OUTCOME_ORDER[int(np.argmax([pred.p_home_win, pred.p_draw, pred.p_away_win]))],
                    "correct": int(OUTCOME_ORDER[int(np.argmax([pred.p_home_win, pred.p_draw, pred.p_away_win]))] == actual),
                }
            )
        elo.update_match(
            r.home_team, r.away_team, int(r.home_score), int(r.away_score),
            tournament=getattr(r, "tournament", ""), neutral=bool(r.neutral),
        )
    return pd.DataFrame(rows)


def win_event_reliability(pred_df: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Curva de fiabilidad del evento 'ganar'.

    Cada partido aporta dos puntos: (P(local gana), gano local) y (P(visita gana),
    gano visita). Se agrupa por bin de probabilidad y se compara probabilidad media
    predicha vs frecuencia real de victoria. Calibrado perfecto -> diagonal.
    """
    if pred_df.empty:
        return pd.DataFrame()
    pred_win = np.concatenate([pred_df["p_home_win"].to_numpy(), pred_df["p_away_win"].to_numpy()])
    did_win = np.concatenate([
        (pred_df["outcome"] == "H").to_numpy().astype(float),
        (pred_df["outcome"] == "A").to_numpy().astype(float),
    ])
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (pred_win > lo) & (pred_win <= hi)
        if not np.any(mask):
            continue
        rows.append(
            {
                "bin_lower": round(float(lo), 2),
                "bin_upper": round(float(hi), 2),
                "predicted_win_prob": float(pred_win[mask].mean()),
                "observed_win_freq": float(did_win[mask].mean()),
                "count": int(mask.sum()),
            }
        )
    return pd.DataFrame(rows)


def calibration_summary(pred_df: pd.DataFrame) -> dict:
    """Metricas de calibracion/acierto sobre los partidos evaluados."""
    if pred_df.empty:
        return {"n_matches": 0}
    probs = pred_df[["p_home_win", "p_draw", "p_away_win"]].to_numpy()
    metrics = evaluate_probabilities(pred_df["outcome"], probs)
    rel = win_event_reliability(pred_df)
    # Error de calibracion del evento victoria (media ponderada |pred - obs|).
    win_ece = 0.0
    if not rel.empty:
        w = rel["count"] / rel["count"].sum()
        win_ece = float((w * (rel["predicted_win_prob"] - rel["observed_win_freq"]).abs()).sum())
    return {
        "n_matches": int(len(pred_df)),
        "accuracy": metrics["accuracy"],
        "log_loss": metrics["log_loss"],
        "brier": metrics["brier"],
        "rps": metrics["rps"],
        "ece_outcome": metrics["ece"],
        "win_event_ece": win_ece,
    }


def save_reliability_png(rel: pd.DataFrame, title: str, out_path: str | Path) -> Path | None:
    """Guarda la curva de fiabilidad como PNG (diagonal = calibracion perfecta)."""
    out_path = Path(out_path)
    if rel.empty:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot([0, 1], [0, 1], "--", color="#888", label="Calibracion perfecta")
    sizes = 20 + 4 * rel["count"].to_numpy()
    ax.scatter(rel["predicted_win_prob"], rel["observed_win_freq"], s=sizes, color="#197a52", zorder=3, label="Bins (tamano = nº)")
    ax.plot(rel["predicted_win_prob"], rel["observed_win_freq"], color="#197a52", alpha=0.5, zorder=2)
    ax.set_xlabel("Probabilidad de victoria predicha")
    ax.set_ylabel("Frecuencia real de victoria")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
