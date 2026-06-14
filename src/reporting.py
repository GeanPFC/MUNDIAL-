"""Generacion de salidas explicables: por partido, por grupo y por torneo.

Sin lenguaje de apuestas. Toda salida incluye un aviso de incertidumbre.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson as poisson_dist

UNCERTAINTY_DISCLAIMER = (
    "Probabilidades calibradas, no certezas. El futbol internacional tiene alta varianza; "
    "usar como apoyo analitico, no como prediccion garantizada."
)


# --------------------------------------------------------------------------- #
# Reporte por partido
# --------------------------------------------------------------------------- #

def match_report(predictor, home: str, away: str, neutral: bool = True, top_n: int = 5) -> dict:
    """Combina Elo (1X2) + Poisson (goles) en un reporte completo de un partido."""
    probs = predictor.match_1x2(home, away, neutral)
    lam_h, lam_a = predictor.poisson.expected_goals(home, away, neutral=neutral)
    matrix = predictor.poisson.score_matrix(lam_h, lam_a)
    n = matrix.shape[0]

    # Top-N marcadores mas probables.
    flat = matrix.flatten()
    order = np.argsort(flat)[::-1][:top_n]
    top_scores = [
        {"home_goals": int(idx // n), "away_goals": int(idx % n), "probability": float(flat[idx])}
        for idx in order
    ]
    modal = top_scores[0]

    elo_pred = predictor.elo.predict_match(home, away, neutral=neutral)
    strength_h = predictor.poisson.team_strength(home)
    strength_a = predictor.poisson.team_strength(away)
    min_exposure = min(strength_h.matches, strength_a.matches)
    uncertainty = "alta" if min_exposure < 8 else "media" if min_exposure < 25 else "baja"
    max_p = float(np.max(probs))
    confidence = "alta" if max_p >= 0.7 else "media" if max_p >= 0.55 else "baja"

    return {
        "home_team": home,
        "away_team": away,
        "neutral": neutral,
        "probabilities": {
            "home_win": float(probs[0]),
            "draw": float(probs[1]),
            "away_win": float(probs[2]),
        },
        "expected_goals": {"home": float(lam_h), "away": float(lam_a)},
        "most_likely_score": modal,
        "top_scores": top_scores,
        "goal_intervals": {
            "home": [int(poisson_dist.ppf(0.05, lam_h)), int(poisson_dist.ppf(0.95, lam_h))],
            "away": [int(poisson_dist.ppf(0.05, lam_a)), int(poisson_dist.ppf(0.95, lam_a))],
        },
        "confidence": confidence,
        "uncertainty": uncertainty,
        "upset_probability": float(1.0 - max_p),
        "influential_variables": {
            "elo_home": float(elo_pred.rating_home),
            "elo_away": float(elo_pred.rating_away),
            "elo_diff_adjusted": float(elo_pred.rating_diff),
            "home_attack": float(strength_h.attack),
            "away_attack": float(strength_a.attack),
            "home_defense_allowed_rate": float(strength_h.defense),
            "away_defense_allowed_rate": float(strength_a.defense),
            "neutral_venue": float(neutral),
        },
        "disclaimer": UNCERTAINTY_DISCLAIMER,
    }


def format_match_report(report: dict) -> str:
    p = report["probabilities"]
    xg = report["expected_goals"]
    lines = [
        f"{report['home_team']} vs {report['away_team']} ({'sede neutral' if report['neutral'] else 'con localia'})",
        f"  Victoria {report['home_team']}: {p['home_win']:.1%}",
        f"  Empate:                {p['draw']:.1%}",
        f"  Victoria {report['away_team']}: {p['away_win']:.1%}",
        f"  Goles esperados: {report['home_team']} {xg['home']:.2f} - {xg['away']:.2f} {report['away_team']}",
        f"  Marcador modal: {report['most_likely_score']['home_goals']}-{report['most_likely_score']['away_goals']} "
        f"({report['most_likely_score']['probability']:.1%})",
        "  Top marcadores: " + ", ".join(
            f"{s['home_goals']}-{s['away_goals']} ({s['probability']:.1%})" for s in report["top_scores"]
        ),
        f"  Confianza: {report['confidence']} | Incertidumbre de datos: {report['uncertainty']} "
        f"| Prob. de sorpresa: {report['upset_probability']:.1%}",
        f"  Nota: {report['disclaimer']}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reporte por grupo
# --------------------------------------------------------------------------- #

def group_report(summary: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    """Por equipo: P(1.o/2.o/3.o/4.o) y P(clasificar), agrupado por grupo."""
    merged = groups.merge(summary, on="team", how="left")
    cols = ["group", "team", "first", "second", "third", "fourth", "qualified"]
    out = merged[cols].copy()
    out = out.sort_values(["group", "qualified"], ascending=[True, False]).reset_index(drop=True)
    out = out.rename(columns={
        "first": "p_1st", "second": "p_2nd", "third": "p_3rd",
        "fourth": "p_4th", "qualified": "p_qualify",
    })
    return out


# --------------------------------------------------------------------------- #
# Reporte por torneo
# --------------------------------------------------------------------------- #

def tournament_report(summary: pd.DataFrame) -> pd.DataFrame:
    cols = ["team", "advance_r32", "advance_r16", "advance_qf", "advance_sf", "advance_final", "champion"]
    out = summary[cols].copy().rename(columns={
        "advance_r32": "p_round_of_32",
        "advance_r16": "p_round_of_16",
        "advance_qf": "p_quarterfinal",
        "advance_sf": "p_semifinal",
        "advance_final": "p_final",
        "champion": "p_champion",
    })
    return out.sort_values("p_champion", ascending=False).reset_index(drop=True)


def save_reports(
    summary: pd.DataFrame,
    groups: pd.DataFrame,
    output_dir: str | Path,
    cutoff: str,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    g = group_report(summary, groups)
    t = tournament_report(summary)
    paths = {
        "group_csv": output_dir / "wc2026_group_probabilities.csv",
        "tournament_csv": output_dir / "wc2026_tournament_probabilities.csv",
        "markdown": output_dir / "wc2026_predictions.md",
    }
    g.to_csv(paths["group_csv"], index=False)
    t.to_csv(paths["tournament_csv"], index=False)

    lines = [
        "# Predicciones Mundial 2026 (simulacion Monte Carlo)",
        "",
        f"Fecha de corte: {cutoff}. Simulaciones: {summary.attrs.get('n_simulations', 'NA')}.",
        f"Condicional a los resultados ya jugados al {cutoff}.",
        "",
        f"> {UNCERTAINTY_DISCLAIMER}",
        "",
        "## Probabilidad de campeon (top 12)",
        "",
        "| Equipo | Campeon | Final | Semis | Cuartos | Octavos | R32 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in t.head(12).iterrows():
        lines.append(
            f"| {r['team']} | {r['p_champion']:.1%} | {r['p_final']:.1%} | {r['p_semifinal']:.1%} "
            f"| {r['p_quarterfinal']:.1%} | {r['p_round_of_16']:.1%} | {r['p_round_of_32']:.1%} |"
        )
    lines += ["", "## Probabilidad de clasificar por grupo", ""]
    for group in sorted(g["group"].unique()):
        block = g[g["group"] == group]
        lines.append(f"### Grupo {group}")
        lines.append("")
        lines.append("| Equipo | 1.o | 2.o | 3.o | 4.o | Clasifica |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for _, r in block.iterrows():
            lines.append(
                f"| {r['team']} | {r['p_1st']:.1%} | {r['p_2nd']:.1%} | {r['p_3rd']:.1%} "
                f"| {r['p_4th']:.1%} | {r['p_qualify']:.1%} |"
            )
        lines.append("")
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return paths
