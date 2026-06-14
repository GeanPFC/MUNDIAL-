"""DEPRECADO: usar src/tournament.py.

Este era el simulador original. La auditoria (MODEL_AUDIT.md, hallazgo C2) detecto que
nunca se conectaba a ningun script, no tenia datos de calendario/grupos 2026 y su conteo
por ronda estaba incompleto (no contaba octavos ni cuartos). Quedo reemplazado por
src/tournament.py, que implementa el Monte Carlo real con reglas FIFA 2026, resultados ya
jugados, desempates oficiales y conteo completo R32->octavos->cuartos->semis->final->campeon.

Se conserva solo por compatibilidad historica; no usar en codigo nuevo.
"""
from __future__ import annotations

import warnings

from dataclasses import dataclass, field
from typing import Callable

warnings.warn(
    "src.simulation esta deprecado; usa src.tournament y run_tournament.py.",
    DeprecationWarning,
    stacklevel=2,
)

import numpy as np
import pandas as pd

from .evaluation import OUTCOME_ORDER


@dataclass
class SimulatedMatch:
    home_team: str
    away_team: str
    outcome: str
    winner: str | None
    home_goals: int | None = None
    away_goals: int | None = None


def _predict_single(predictor: object, match: pd.Series) -> np.ndarray:
    frame = pd.DataFrame([match.to_dict()])
    if hasattr(predictor, "predict_proba"):
        probs = predictor.predict_proba(frame)[0]
    elif hasattr(predictor, "predict_match"):
        pred = predictor.predict_match(
            match["home_team"],
            match["away_team"],
            neutral=bool(match.get("neutral", False)),
        )
        probs = np.array([pred.p_home_win, pred.p_draw, pred.p_away_win], dtype=float)
    else:
        raise TypeError("Predictor must implement predict_proba(frame) or predict_match(...).")
    probs = np.clip(probs, 1e-12, 1.0)
    return probs / probs.sum()


def simulate_match(
    predictor: object,
    match: pd.Series,
    rng: np.random.Generator,
    knockout: bool = False,
    penalty_strength: dict[str, float] | None = None,
) -> SimulatedMatch:
    probs = _predict_single(predictor, match)
    outcome = str(rng.choice(OUTCOME_ORDER, p=probs))
    home_team = str(match["home_team"])
    away_team = str(match["away_team"])
    winner: str | None
    if outcome == "H":
        winner = home_team
    elif outcome == "A":
        winner = away_team
    elif knockout:
        strengths = penalty_strength or {}
        home_strength = max(float(strengths.get(home_team, 1.0)), 0.01)
        away_strength = max(float(strengths.get(away_team, 1.0)), 0.01)
        p_home_pen = home_strength / (home_strength + away_strength)
        winner = home_team if rng.random() < p_home_pen else away_team
    else:
        winner = None
    return SimulatedMatch(home_team=home_team, away_team=away_team, outcome=outcome, winner=winner)


def group_standings(group_matches: pd.DataFrame, predictor: object, rng: np.random.Generator) -> pd.DataFrame:
    teams = sorted(set(group_matches["home_team"]).union(group_matches["away_team"]))
    table = {
        team: {"team": team, "points": 0, "gf": 0, "ga": 0, "gd": 0, "wins": 0, "draws": 0, "losses": 0}
        for team in teams
    }
    for _, match in group_matches.iterrows():
        simulated = simulate_match(predictor, match, rng, knockout=False)
        # Draw sampled scores from expected-goal models when available; otherwise use conservative placeholders.
        if hasattr(predictor, "predict_match"):
            pred = predictor.predict_match(simulated.home_team, simulated.away_team, neutral=bool(match.get("neutral", False)))
            home_goals = int(rng.poisson(pred.expected_goals_home))
            away_goals = int(rng.poisson(pred.expected_goals_away))
            if simulated.outcome == "H" and home_goals <= away_goals:
                home_goals = away_goals + 1
            elif simulated.outcome == "A" and away_goals <= home_goals:
                away_goals = home_goals + 1
            elif simulated.outcome == "D":
                away_goals = home_goals
        else:
            home_goals, away_goals = {
                "H": (1, 0),
                "D": (1, 1),
                "A": (0, 1),
            }[simulated.outcome]

        h = table[simulated.home_team]
        a = table[simulated.away_team]
        h["gf"] += home_goals
        h["ga"] += away_goals
        a["gf"] += away_goals
        a["ga"] += home_goals
        if home_goals > away_goals:
            h["points"] += 3
            h["wins"] += 1
            a["losses"] += 1
        elif home_goals < away_goals:
            a["points"] += 3
            a["wins"] += 1
            h["losses"] += 1
        else:
            h["points"] += 1
            a["points"] += 1
            h["draws"] += 1
            a["draws"] += 1

    standings = pd.DataFrame(table.values())
    standings["gd"] = standings["gf"] - standings["ga"]
    return standings.sort_values(["points", "gd", "gf", "wins"], ascending=False).reset_index(drop=True)


def rank_group_stage(schedule: pd.DataFrame, predictor: object, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    groups: dict[str, pd.DataFrame] = {}
    group_matches = schedule[schedule["stage"].eq("group")]
    for group, frame in group_matches.groupby("group"):
        groups[str(group)] = group_standings(frame, predictor, rng)
    return groups


def default_qualifiers(group_tables: dict[str, pd.DataFrame]) -> dict[str, str]:
    qualifiers: dict[str, str] = {}
    third_rows = []
    for group, table in group_tables.items():
        qualifiers[f"1{group}"] = str(table.iloc[0]["team"])
        qualifiers[f"2{group}"] = str(table.iloc[1]["team"])
        third = table.iloc[2].copy()
        third["group"] = group
        third_rows.append(third)
    thirds = pd.DataFrame(third_rows).sort_values(["points", "gd", "gf", "wins"], ascending=False).head(8)
    for _, row in thirds.iterrows():
        qualifiers[f"3{row['group']}"] = str(row["team"])
    return qualifiers


def resolve_slot(
    slot: str,
    qualifiers: dict[str, str],
    used_thirds: set[str],
    third_place_slot_map: dict[str, str] | None = None,
) -> str:
    if slot in qualifiers:
        return qualifiers[slot]
    if slot.startswith("3"):
        if third_place_slot_map and slot in third_place_slot_map:
            mapped = third_place_slot_map[slot]
            used_thirds.add(mapped)
            return qualifiers[mapped]
        allowed = [f"3{group}" for group in slot[1:]]
        for key in allowed:
            if key in qualifiers and key not in used_thirds:
                used_thirds.add(key)
                return qualifiers[key]
    raise KeyError(f"Cannot resolve bracket slot {slot!r}. Provide official third_place_slot_map.")


def simulate_knockout(
    knockout_schedule: pd.DataFrame,
    predictor_factory: Callable[[str, str], object] | object,
    qualifiers: dict[str, str],
    rng: np.random.Generator,
    third_place_slot_map: dict[str, str] | None = None,
) -> dict[str, str]:
    winners: dict[str, str] = {}
    used_thirds: set[str] = set()
    for _, row in knockout_schedule.sort_values("order").iterrows():
        home_slot = str(row["home_slot"])
        away_slot = str(row["away_slot"])
        home_team = winners.get(home_slot) or resolve_slot(home_slot, qualifiers, used_thirds, third_place_slot_map)
        away_team = winners.get(away_slot) or resolve_slot(away_slot, qualifiers, used_thirds, third_place_slot_map)
        match = row.copy()
        match["home_team"] = home_team
        match["away_team"] = away_team
        predictor = predictor_factory(home_team, away_team) if callable(predictor_factory) else predictor_factory
        simulated = simulate_match(predictor, match, rng, knockout=True)
        winners[str(row["match_id"])] = str(simulated.winner)
    return winners


def run_monte_carlo(
    schedule: pd.DataFrame,
    predictor: object,
    n_simulations: int = 10000,
    random_state: int = 2026,
    third_place_slot_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    teams = sorted(set(schedule["home_team"].dropna()).union(schedule["away_team"].dropna()))
    counts = {
        team: {"team": team, "advance_r32": 0, "semifinal": 0, "final": 0, "champion": 0}
        for team in teams
    }
    knockout = schedule[~schedule["stage"].eq("group")].copy()
    for _ in range(n_simulations):
        tables = rank_group_stage(schedule, predictor, rng)
        qualifiers = default_qualifiers(tables)
        for team in qualifiers.values():
            counts.setdefault(team, {"team": team, "advance_r32": 0, "semifinal": 0, "final": 0, "champion": 0})
            counts[team]["advance_r32"] += 1
        if not knockout.empty:
            winners = simulate_knockout(knockout, predictor, qualifiers, rng, third_place_slot_map)
            for match_id, winner in winners.items():
                stage = str(knockout.loc[knockout["match_id"].eq(match_id), "stage"].iloc[0])
                if stage in {"quarterfinal", "semifinal", "final"}:
                    counts[winner]["semifinal"] += int(stage == "quarterfinal")
                    counts[winner]["final"] += int(stage == "semifinal")
                    counts[winner]["champion"] += int(stage == "final")

    summary = pd.DataFrame(counts.values())
    probability_cols = ["advance_r32", "semifinal", "final", "champion"]
    summary[probability_cols] = summary[probability_cols] / float(n_simulations)
    return summary.sort_values("champion", ascending=False).reset_index(drop=True)
