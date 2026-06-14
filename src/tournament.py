"""Simulacion Monte Carlo del Mundial 2026 con reglas FIFA correctas.

Reemplaza a src/simulation.py (que estaba sin conectar, sin datos y con conteo
incompleto). Aqui:

  - se respetan los resultados YA jugados (simulacion condicional al estado real);
  - cada partido de grupos muestrea un marcador coherente desde el modelo de goles,
    condicionado al resultado 1X2 del modelo Elo calibrado (una sola fuente, sin el
    hack de "forzar goles a concordar");
  - desempates de grupo oficiales: puntos -> dif. goles -> goles a favor ->
    enfrentamiento directo -> sorteo reproducible (fair-play omitido por falta de
    datos de tarjetas, documentado);
  - clasifican 2 primeros + 8 mejores terceros;
  - los terceros se asignan a la llave por emparejamiento factible respetando los
    grupos permitidos de cada slot (malla oficial);
  - eliminatorias R32 -> octavos -> cuartos -> semis -> final, con prorroga/penales
    como mecanismo separado ponderado por Elo (no 50/50);
  - conteo completo por ronda y posicion de grupo.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .elo_model import EloModel, EloConfig
from .poisson_model import PoissonGoalModel
from .calibration import apply_temperature

OUTCOME_ORDER = ("H", "D", "A")
GROUP_POS_LABELS = ("first", "second", "third", "fourth")


@dataclass
class TournamentPredictor:
    """Empaqueta Elo (1X2) + Poisson (goles) entrenados hasta la fecha de corte."""

    elo: EloModel
    poisson: PoissonGoalModel
    temperature: float = 1.0
    max_goals: int = 7

    def elo_expected(self, home: str, away: str, neutral: bool) -> float:
        return self.elo.expected_score(home, away, neutral=neutral)

    def match_1x2(self, home: str, away: str, neutral: bool) -> np.ndarray:
        pred = self.elo.predict_match(home, away, neutral=neutral)
        probs = np.array([pred.p_home_win, pred.p_draw, pred.p_away_win], dtype=float)
        if abs(self.temperature - 1.0) > 1e-9:
            probs = apply_temperature(probs[None, :], self.temperature)[0]
        return probs

    def conditional_score_cdfs(self, home: str, away: str, neutral: bool):
        """Para un fixture, devuelve por cada resultado (H/D/A) la distribucion de
        marcadores condicionada, como (indices_planos, cdf)."""
        lam_h, lam_a = self.poisson.expected_goals(home, away, neutral=neutral)
        matrix = self.poisson.score_matrix(lam_h, lam_a)
        n = min(self.max_goals + 1, matrix.shape[0])
        matrix = matrix[:n, :n]
        matrix = matrix / matrix.sum()
        a_idx, b_idx = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        diff = a_idx - b_idx
        cdfs = {}
        for outcome, mask in (
            ("H", diff > 0),
            ("D", diff == 0),
            ("A", diff < 0),
        ):
            cells = matrix[mask]
            total = cells.sum()
            flat_a = a_idx[mask]
            flat_b = b_idx[mask]
            if total <= 0:
                # Resultado imposible bajo el modelo: marcador minimo coherente.
                fallback = {"H": (1, 0), "D": (0, 0), "A": (0, 1)}[outcome]
                cdfs[outcome] = (np.array([fallback[0]]), np.array([fallback[1]]), np.array([1.0]))
            else:
                cdfs[outcome] = (flat_a, flat_b, np.cumsum(cells / total))
        return lam_h, lam_a, cdfs


def build_predictor(
    history: pd.DataFrame,
    cutoff: str | pd.Timestamp,
    elo_config: EloConfig | None = None,
    fit_dixon_coles: bool = True,
    half_life_days: float = 1095.0,
    temperature: float = 1.0,
) -> TournamentPredictor:
    """Entrena Elo + Poisson con todos los partidos hasta `cutoff` (inclusive).

    Como incluye los partidos ya jugados del Mundial, esto es el modo 'elo_live'.
    """
    cutoff = pd.Timestamp(cutoff)
    train = history[history["date"] <= cutoff].copy()
    elo = EloModel(elo_config or EloConfig()).fit(train)
    poisson = PoissonGoalModel(fit_dixon_coles=fit_dixon_coles)
    poisson.fit(train, as_of=cutoff)
    return TournamentPredictor(elo=elo, poisson=poisson, temperature=temperature)


# --------------------------------------------------------------------------- #
# Precomputo de fixtures de grupo
# --------------------------------------------------------------------------- #

@dataclass
class GroupFixture:
    group: str
    home: str
    away: str
    neutral: bool
    played: bool
    fixed_home_goals: int = 0
    fixed_away_goals: int = 0
    probs_1x2: np.ndarray = field(default_factory=lambda: np.array([1 / 3, 1 / 3, 1 / 3]))
    cond: dict = field(default_factory=dict)


def precompute_group_fixtures(schedule: pd.DataFrame, predictor: TournamentPredictor) -> list[GroupFixture]:
    fixtures: list[GroupFixture] = []
    for _, row in schedule.iterrows():
        home, away = str(row["home_team"]), str(row["away_team"])
        neutral = bool(row["neutral"]) if not pd.isna(row.get("neutral")) else True
        played = str(row.get("status", "scheduled")) == "played"
        if played:
            fixtures.append(
                GroupFixture(
                    group=str(row["group"]), home=home, away=away, neutral=neutral, played=True,
                    fixed_home_goals=int(row["home_score"]), fixed_away_goals=int(row["away_score"]),
                )
            )
        else:
            probs = predictor.match_1x2(home, away, neutral)
            _, _, cond = predictor.conditional_score_cdfs(home, away, neutral)
            fixtures.append(
                GroupFixture(
                    group=str(row["group"]), home=home, away=away, neutral=neutral, played=False,
                    probs_1x2=probs, cond=cond,
                )
            )
    return fixtures


# --------------------------------------------------------------------------- #
# Standings con desempates oficiales
# --------------------------------------------------------------------------- #

def _rank_group(team_stats: dict, played_matches: list[tuple], rng: np.random.Generator) -> list[str]:
    """Ordena un grupo con criterios FIFA: pts, dg, gf, enfrentamiento directo, sorteo."""
    teams = list(team_stats.keys())

    def overall_key(team):
        s = team_stats[team]
        return (s["points"], s["gd"], s["gf"])

    # Orden inicial por criterios generales.
    teams.sort(key=overall_key, reverse=True)

    # Resolver clusters empatados en (pts, dg, gf) con enfrentamiento directo + sorteo.
    result: list[str] = []
    i = 0
    while i < len(teams):
        j = i + 1
        while j < len(teams) and overall_key(teams[j]) == overall_key(teams[i]):
            j += 1
        cluster = teams[i:j]
        if len(cluster) == 1:
            result.append(cluster[0])
        else:
            result.extend(_break_tie(cluster, played_matches, rng))
        i = j
    return result


def _break_tie(cluster: list[str], played_matches: list[tuple], rng: np.random.Generator) -> list[str]:
    """Mini-tabla de enfrentamientos directos entre los empatados; resto por sorteo."""
    h2h = {t: {"points": 0, "gf": 0, "ga": 0} for t in cluster}
    cset = set(cluster)
    for home, away, hs, as_ in played_matches:
        if home in cset and away in cset:
            h2h[home]["gf"] += hs
            h2h[home]["ga"] += as_
            h2h[away]["gf"] += as_
            h2h[away]["ga"] += hs
            if hs > as_:
                h2h[home]["points"] += 3
            elif hs < as_:
                h2h[away]["points"] += 3
            else:
                h2h[home]["points"] += 1
                h2h[away]["points"] += 1

    def h2h_key(team):
        s = h2h[team]
        return (s["points"], s["gf"] - s["ga"], s["gf"], rng.random())

    return sorted(cluster, key=h2h_key, reverse=True)


def simulate_group_stage(fixtures: list[GroupFixture], rng: np.random.Generator):
    """Simula todos los grupos. Devuelve (posiciones, terceros_ordenados_globales)."""
    groups: dict[str, dict] = {}
    group_matches: dict[str, list[tuple]] = {}
    for fx in fixtures:
        groups.setdefault(fx.group, {})
        group_matches.setdefault(fx.group, [])
        for team in (fx.home, fx.away):
            groups[fx.group].setdefault(team, {"points": 0, "gf": 0, "ga": 0, "gd": 0})

    for fx in fixtures:
        if fx.played:
            hg, ag = fx.fixed_home_goals, fx.fixed_away_goals
        else:
            outcome = OUTCOME_ORDER[_sample_index(fx.probs_1x2, rng)]
            flat_a, flat_b, cdf = fx.cond[outcome]
            k = int(np.searchsorted(cdf, rng.random()))
            k = min(k, len(flat_a) - 1)
            hg, ag = int(flat_a[k]), int(flat_b[k])
        g = groups[fx.group]
        g[fx.home]["gf"] += hg
        g[fx.home]["ga"] += ag
        g[fx.away]["gf"] += ag
        g[fx.away]["ga"] += hg
        if hg > ag:
            g[fx.home]["points"] += 3
        elif hg < ag:
            g[fx.away]["points"] += 3
        else:
            g[fx.home]["points"] += 1
            g[fx.away]["points"] += 1
        group_matches[fx.group].append((fx.home, fx.away, hg, ag))

    positions: dict[str, list[str]] = {}
    thirds_pool: list[tuple] = []
    for group, stats in groups.items():
        for team, s in stats.items():
            s["gd"] = s["gf"] - s["ga"]
        ordered = _rank_group(stats, group_matches[group], rng)
        positions[group] = ordered
        third = ordered[2]
        s = stats[third]
        thirds_pool.append((group, third, s["points"], s["gd"], s["gf"], rng.random()))

    # 8 mejores terceros: pts -> dg -> gf -> sorteo.
    thirds_pool.sort(key=lambda x: (x[2], x[3], x[4], x[5]), reverse=True)
    best_thirds = thirds_pool[:8]
    return positions, best_thirds


def _sample_index(probs: np.ndarray, rng: np.random.Generator) -> int:
    return int(np.searchsorted(np.cumsum(probs), rng.random()))


# --------------------------------------------------------------------------- #
# Asignacion de terceros a la llave (emparejamiento factible)
# --------------------------------------------------------------------------- #

def assign_thirds_to_slots(
    qualified_third_groups: list[str],
    third_place_table: pd.DataFrame,
) -> dict[str, str] | None:
    """Asigna cada grupo-tercero clasificado a un slot del R32 respetando los grupos
    permitidos. Devuelve {third_slot: group} o None si no hay emparejamiento."""
    slots = list(third_place_table["third_slot"])
    allowed = {row["third_slot"]: set(row["allowed_groups"]) for _, row in third_place_table.iterrows()}
    groups = list(qualified_third_groups)

    # Backtracking sobre slots ordenados por menor numero de opciones (heuristica MRV).
    assignment: dict[str, str] = {}
    used: set[str] = set()

    def options(slot):
        return [g for g in groups if g in allowed[slot] and g not in used]

    def backtrack(remaining: list[str]) -> bool:
        if not remaining:
            return True
        remaining.sort(key=lambda s: len(options(s)))
        slot = remaining[0]
        for g in options(slot):
            assignment[slot] = g
            used.add(g)
            if backtrack(remaining[1:]):
                return True
            used.discard(g)
            del assignment[slot]
        return False

    return assignment if backtrack(list(slots)) else None


# --------------------------------------------------------------------------- #
# Eliminatorias
# --------------------------------------------------------------------------- #

def _knockout_winner(predictor, home, away, rng, penalty_scale):
    """Resuelve un partido de eliminatoria. Empate -> prorroga/penales por Elo."""
    probs = predictor.match_1x2(home, away, neutral=True)
    idx = _sample_index(probs, rng)
    if idx == 0:
        return home, away
    if idx == 2:
        return away, home
    # Empate en tiempo reglamentario: prorroga/penales ponderados por Elo.
    e = predictor.elo_expected(home, away, neutral=True)
    p_home = 0.5 + penalty_scale * (e - 0.5)
    if rng.random() < p_home:
        return home, away
    return away, home


def simulate_knockout(
    predictor,
    bracket: pd.DataFrame,
    slot_values: dict[str, str],
    rng: np.random.Generator,
    penalty_scale: float,
):
    """Resuelve toda la llave. Devuelve dict de ganadores/perdedores por match_id."""
    winners: dict[str, str] = {}
    losers: dict[str, str] = {}
    for _, row in bracket.iterrows():
        mid = str(int(row["match_id"]))
        home = _resolve_slot(str(row["home_slot"]), slot_values, winners, losers)
        away = _resolve_slot(str(row["away_slot"]), slot_values, winners, losers)
        w, l = _knockout_winner(predictor, home, away, rng, penalty_scale)
        winners[mid] = w
        losers[mid] = l
    return winners, losers


def _resolve_slot(slot, slot_values, winners, losers):
    if slot in slot_values:
        return slot_values[slot]
    if slot.startswith("W"):
        return winners[slot[1:]]
    if slot.startswith("L"):
        return losers[slot[1:]]
    raise KeyError(f"No se pudo resolver el slot {slot!r}")


# --------------------------------------------------------------------------- #
# Orquestacion Monte Carlo
# --------------------------------------------------------------------------- #

STAGE_TO_REACH = {
    "round_of_32": "advance_r16",     # ganar R32 = llegar a octavos
    "round_of_16": "advance_qf",      # ganar octavos = llegar a cuartos
    "quarterfinal": "advance_sf",     # ganar cuartos = llegar a semis
    "semifinal": "advance_final",     # ganar semis = llegar a la final
    "final": "champion",
}
COUNTER_KEYS = (
    "first", "second", "third", "fourth", "qualified",
    "advance_r32", "advance_r16", "advance_qf", "advance_sf", "advance_final", "champion",
)


def run_tournament(
    predictor: TournamentPredictor,
    schedule: pd.DataFrame,
    bracket: pd.DataFrame,
    third_place_table: pd.DataFrame,
    n_simulations: int = 50000,
    random_seed: int = 2026,
    penalty_scale: float = 0.65,
    progress_every: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_seed)
    fixtures = precompute_group_fixtures(schedule, predictor)
    all_teams = sorted(set(schedule["home_team"]).union(schedule["away_team"]))
    counts = {team: {k: 0 for k in COUNTER_KEYS} for team in all_teams}
    failed_assignments = 0

    for sim in range(n_simulations):
        positions, best_thirds = simulate_group_stage(fixtures, rng)

        slot_values: dict[str, str] = {}
        for group, ordered in positions.items():
            slot_values[f"1{group}"] = ordered[0]
            slot_values[f"2{group}"] = ordered[1]
            counts[ordered[0]]["first"] += 1
            counts[ordered[1]]["second"] += 1
            counts[ordered[2]]["third"] += 1
            counts[ordered[3]]["fourth"] += 1

        qualified_third_groups = [t[0] for t in best_thirds]
        assignment = assign_thirds_to_slots(qualified_third_groups, third_place_table)
        if assignment is None:
            failed_assignments += 1
            continue
        group_to_team = {t[0]: t[1] for t in best_thirds}
        for slot, group in assignment.items():
            slot_values[slot] = group_to_team[group]

        # Marcar clasificados (llegan a R32).
        qualifiers = set()
        for group, ordered in positions.items():
            qualifiers.add(ordered[0])
            qualifiers.add(ordered[1])
        qualifiers.update(group_to_team.values())
        for team in qualifiers:
            counts[team]["qualified"] += 1
            counts[team]["advance_r32"] += 1

        winners, _losers = simulate_knockout(predictor, bracket, slot_values, rng, penalty_scale)
        for _, row in bracket.iterrows():
            stage = str(row["stage"])
            reach = STAGE_TO_REACH.get(stage)
            if reach is None:
                continue
            mid = str(int(row["match_id"]))
            counts[winners[mid]][reach] += 1

        if progress_every and (sim + 1) % progress_every == 0:
            print(f"  ... {sim + 1}/{n_simulations} simulaciones")

    rows = []
    for team, c in counts.items():
        row = {"team": team}
        for k in COUNTER_KEYS:
            row[k] = c[k] / n_simulations
        rows.append(row)
    summary = pd.DataFrame(rows).sort_values("champion", ascending=False).reset_index(drop=True)
    summary.attrs["failed_assignments"] = failed_assignments
    summary.attrs["n_simulations"] = n_simulations
    return summary
