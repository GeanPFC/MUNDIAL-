from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .elo_model import EloConfig, add_elo_features


FEATURE_COLUMNS = [
    "neutral",
    "elo_home",
    "elo_away",
    "elo_diff",
    "elo_p_home_win",
    "elo_p_draw",
    "elo_p_away_win",
    "home_form_points_per_match",
    "away_form_points_per_match",
    "home_form_goal_diff",
    "away_form_goal_diff",
    "home_form_goals_for",
    "away_form_goals_for",
    "home_form_goals_against",
    "away_form_goals_against",
    "form_points_diff",
    "form_goal_diff_delta",
    "home_rest_days",
    "away_rest_days",
    "rest_days_delta",
]


@dataclass
class TeamRollingState:
    window: int = 10
    matches: deque[dict[str, float]] = field(default_factory=deque)
    last_date: pd.Timestamp | None = None

    def snapshot(self, current_date: pd.Timestamp) -> dict[str, float]:
        if not self.matches:
            rest_days = np.nan if self.last_date is None else (current_date - self.last_date).days
            return {
                "points_per_match": 1.0,
                "goal_diff": 0.0,
                "goals_for": 1.2,
                "goals_against": 1.2,
                "rest_days": rest_days,
                "sample_size": 0.0,
            }
        points = np.array([m["points"] for m in self.matches], dtype=float)
        gf = np.array([m["gf"] for m in self.matches], dtype=float)
        ga = np.array([m["ga"] for m in self.matches], dtype=float)
        rest_days = np.nan if self.last_date is None else (current_date - self.last_date).days
        return {
            "points_per_match": float(points.mean()),
            "goal_diff": float((gf - ga).mean()),
            "goals_for": float(gf.mean()),
            "goals_against": float(ga.mean()),
            "rest_days": float(rest_days) if not pd.isna(rest_days) else np.nan,
            "sample_size": float(len(self.matches)),
        }

    def update(self, date: pd.Timestamp, goals_for: int, goals_against: int) -> None:
        if goals_for > goals_against:
            points = 3.0
        elif goals_for == goals_against:
            points = 1.0
        else:
            points = 0.0
        self.matches.append({"gf": float(goals_for), "ga": float(goals_against), "points": points})
        while len(self.matches) > self.window:
            self.matches.popleft()
        self.last_date = date


def add_rolling_form_features(matches: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    states: defaultdict[str, TeamRollingState] = defaultdict(lambda: TeamRollingState(window=window))
    rows: list[dict[str, Any]] = []
    ordered = matches.sort_values("date")
    for idx, row in ordered.iterrows():
        date = pd.Timestamp(row["date"])
        home_state = states[row["home_team"]].snapshot(date)
        away_state = states[row["away_team"]].snapshot(date)
        rows.append(
            {
                "index": idx,
                "home_form_points_per_match": home_state["points_per_match"],
                "away_form_points_per_match": away_state["points_per_match"],
                "home_form_goal_diff": home_state["goal_diff"],
                "away_form_goal_diff": away_state["goal_diff"],
                "home_form_goals_for": home_state["goals_for"],
                "away_form_goals_for": away_state["goals_for"],
                "home_form_goals_against": home_state["goals_against"],
                "away_form_goals_against": away_state["goals_against"],
                "home_rest_days": home_state["rest_days"],
                "away_rest_days": away_state["rest_days"],
                "home_form_sample": home_state["sample_size"],
                "away_form_sample": away_state["sample_size"],
            }
        )
        states[row["home_team"]].update(date, int(row["home_score"]), int(row["away_score"]))
        states[row["away_team"]].update(date, int(row["away_score"]), int(row["home_score"]))

    feature_frame = pd.DataFrame(rows).set_index("index")
    out = matches.join(feature_frame, how="left")
    out["form_points_diff"] = out["home_form_points_per_match"] - out["away_form_points_per_match"]
    out["form_goal_diff_delta"] = out["home_form_goal_diff"] - out["away_form_goal_diff"]
    out["rest_days_delta"] = out["home_rest_days"].fillna(7) - out["away_rest_days"].fillna(7)
    out["home_rest_days"] = out["home_rest_days"].fillna(7)
    out["away_rest_days"] = out["away_rest_days"].fillna(7)
    return out


def make_supervised_matches(
    results: pd.DataFrame,
    rolling_window: int = 10,
    elo_config: EloConfig | None = None,
) -> pd.DataFrame:
    out = results.sort_values("date").reset_index(drop=True).copy()
    out = add_elo_features(out, config=elo_config)
    out = add_rolling_form_features(out, window=rolling_window)
    out["neutral"] = out["neutral"].astype(int)
    for col in FEATURE_COLUMNS:
        if col not in out:
            out[col] = 0.0
    out[FEATURE_COLUMNS] = out[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def merge_external_team_features(
    matches: pd.DataFrame,
    team_features: pd.DataFrame,
    date_col: str = "snapshot_date",
) -> pd.DataFrame:
    required = {"team", date_col}
    missing = required - set(team_features.columns)
    if missing:
        raise ValueError(f"External team features missing columns: {sorted(missing)}")

    external = team_features.copy()
    external[date_col] = pd.to_datetime(external[date_col])
    external = external.sort_values(date_col)
    out = matches.sort_values("date").copy()

    for side in ("home", "away"):
        merged = pd.merge_asof(
            out[["date", f"{side}_team"]].sort_values("date"),
            external.rename(columns={"team": f"{side}_team"}).sort_values(date_col),
            left_on="date",
            right_on=date_col,
            by=f"{side}_team",
            direction="backward",
            allow_exact_matches=True,
        )
        feature_cols = [
            col
            for col in merged.columns
            if col not in {"date", f"{side}_team", date_col}
        ]
        for col in feature_cols:
            out[f"{side}_{col}"] = merged[col].to_numpy()
            out[f"{side}_{col}_missing"] = out[f"{side}_{col}"].isna().astype(int)
    return out
