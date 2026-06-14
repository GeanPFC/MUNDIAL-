from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


WORLD_CUP_NAME = "FIFA World Cup"

TOURNAMENT_IMPORTANCE = {
    "FIFA World Cup": 4.0,
    "FIFA World Cup qualification": 2.2,
    "UEFA Euro": 2.8,
    "Copa America": 2.6,
    "African Cup of Nations": 2.4,
    "AFC Asian Cup": 2.2,
    "CONCACAF Championship": 2.0,
    "CONCACAF Gold Cup": 2.0,
    "Oceania Nations Cup": 1.8,
    "UEFA Nations League": 1.6,
    "Friendly": 0.7,
}


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_results(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
        "city",
        "country",
        "neutral",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in results data: {sorted(missing)}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["home_score"] = pd.to_numeric(out["home_score"], errors="coerce")
    out["away_score"] = pd.to_numeric(out["away_score"], errors="coerce")
    out["neutral"] = out["neutral"].map(_parse_bool)
    out = out.dropna(subset=["date", "home_team", "away_team", "home_score", "away_score"])
    out["home_score"] = out["home_score"].astype(int)
    out["away_score"] = out["away_score"].astype(int)
    out["goal_diff"] = out["home_score"] - out["away_score"]
    out["total_goals"] = out["home_score"] + out["away_score"]
    out["outcome"] = np.select(
        [out["goal_diff"] > 0, out["goal_diff"] < 0],
        ["H", "A"],
        default="D",
    )
    out = out.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)
    return out


def tournament_importance(tournament: str) -> float:
    if tournament in TOURNAMENT_IMPORTANCE:
        return TOURNAMENT_IMPORTANCE[tournament]
    lowered = str(tournament).lower()
    if "qualification" in lowered or "qualifier" in lowered:
        return 1.8
    if "cup" in lowered or "championship" in lowered:
        return 1.6
    return 1.0


def add_time_weights(
    matches: pd.DataFrame,
    as_of: str | pd.Timestamp | None = None,
    half_life_days: float = 1095.0,
) -> pd.DataFrame:
    if matches.empty:
        return matches.assign(weight=pd.Series(dtype=float))
    out = matches.copy()
    cutoff = pd.Timestamp(as_of) if as_of is not None else out["date"].max()
    age_days = (cutoff - out["date"]).dt.days.clip(lower=0)
    recency = np.power(0.5, age_days / half_life_days)
    importance = out["tournament"].map(tournament_importance).astype(float)
    out["weight"] = recency * importance
    return out


def temporal_filter(
    matches: pd.DataFrame,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    mask = pd.Series(True, index=matches.index)
    if start is not None:
        mask &= matches["date"] >= pd.Timestamp(start)
    if end is not None:
        mask &= matches["date"] <= pd.Timestamp(end)
    return matches.loc[mask].copy()


def temporal_train_test_split(
    matches: pd.DataFrame,
    train_start: str | pd.Timestamp | None,
    train_end: str | pd.Timestamp,
    test_start: str | pd.Timestamp,
    test_end: str | pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = temporal_filter(matches, train_start, train_end)
    test = temporal_filter(matches, test_start, test_end)
    if train["date"].max() >= test["date"].min():
        raise ValueError("Temporal split overlaps; this would create leakage.")
    return train, test


def filter_world_cup_editions(matches: pd.DataFrame, years: Iterable[int]) -> pd.DataFrame:
    year_set = set(int(year) for year in years)
    mask = (matches["tournament"] == WORLD_CUP_NAME) & matches["date"].dt.year.isin(year_set)
    return matches.loc[mask].copy()


def result_points(outcome: str, perspective: str) -> int:
    if outcome == "D":
        return 1
    if (outcome == "H" and perspective == "home") or (outcome == "A" and perspective == "away"):
        return 3
    return 0
