r"""Pruebas unitarias del sistema de prediccion Mundial 2026.

Ejecutar:  .\.venv\Scripts\python.exe -m pytest tests/ -q

Cubren (encargo Fase 5.4):
  - probabilidades validas que suman 1;
  - calculo/coherencia de features y modelo de goles;
  - conversion/empate de nombres de selecciones;
  - simulacion de grupos y reglas de clasificacion (2 primeros + 8 terceros);
  - asignacion de terceros a la llave;
  - propiedad ordinal del RPS.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent

from src.calibration import TemperatureScaling, apply_temperature
from src.config import load_config
from src.data_sources_2026 import (
    build_group_schedule,
    load_bracket,
    load_groups,
    load_third_place_table,
    validate_groups_against_results,
)
from src.evaluation import evaluate_probabilities, ranked_probability_score
from src.preprocessing import load_results
from src.tournament import (
    assign_thirds_to_slots,
    build_predictor,
    precompute_group_fixtures,
    run_tournament,
    simulate_group_stage,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "config.yaml")


@pytest.fixture(scope="module")
def results(cfg):
    return load_results(cfg.path("data", "results_csv"))


@pytest.fixture(scope="module")
def predictor(results, cfg):
    return build_predictor(results, str(cfg.get("model", "cutoff_date")), fit_dixon_coles=False)


@pytest.fixture(scope="module")
def wc_data(cfg):
    groups = load_groups(cfg.path("data", "wc2026_groups"))
    schedule = pd.read_csv(cfg.path("data", "wc2026_schedule"))
    bracket = load_bracket(cfg.path("data", "wc2026_bracket"))
    third = load_third_place_table(cfg.path("data", "third_place_table"))
    return groups, schedule, bracket, third


# --------------------------- datos / nombres ------------------------------- #

def test_groups_have_48_teams_in_12_groups(wc_data):
    groups = wc_data[0]
    assert len(groups) == 48
    assert groups["group"].nunique() == 12
    assert (groups.groupby("group").size() == 4).all()


def test_all_group_team_names_match_results(cfg):
    groups = load_groups(cfg.path("data", "wc2026_groups"))
    missing = validate_groups_against_results(groups, cfg.path("data", "results_csv"))
    assert missing == [], f"Nombres sin empatar en results.csv: {missing}"


def test_schedule_has_72_group_matches(cfg):
    groups = load_groups(cfg.path("data", "wc2026_groups"))
    sched = build_group_schedule(cfg.path("data", "results_csv"), groups)
    assert len(sched) == 72
    assert (sched.groupby("group").size() == 6).all()


# --------------------------- probabilidades -------------------------------- #

def test_match_1x2_sums_to_one(predictor):
    probs = predictor.match_1x2("Argentina", "France", neutral=True)
    assert probs.shape == (3,)
    assert abs(float(probs.sum()) - 1.0) < 1e-9
    assert (probs >= 0).all()


def test_score_matrix_sums_to_one(predictor):
    lam_h, lam_a = predictor.poisson.expected_goals("Spain", "Brazil", neutral=True)
    matrix = predictor.poisson.score_matrix(lam_h, lam_a)
    assert abs(float(matrix.sum()) - 1.0) < 1e-9


def test_temperature_keeps_simplex():
    probs = np.array([[0.6, 0.25, 0.15], [0.2, 0.2, 0.6]])
    out = apply_temperature(probs, 0.8)
    assert np.allclose(out.sum(axis=1), 1.0)
    cal = TemperatureScaling().fit(probs, ["H", "A"])
    assert cal.temperature > 0


# ------------------------------- RPS --------------------------------------- #

def test_rps_perfect_is_zero():
    probs = np.array([[1.0, 0.0, 0.0]])
    assert ranked_probability_score(["H"], probs) < 1e-9


def test_rps_is_distance_sensitive():
    # Verdad = victoria visitante (A). Predecir empate (cercano) debe penalizar menos
    # que predecir victoria local (lejano).
    near = np.array([[0.0, 1.0, 0.0]])   # todo al empate
    far = np.array([[1.0, 0.0, 0.0]])    # todo a la victoria local
    assert ranked_probability_score(["A"], near) < ranked_probability_score(["A"], far)


def test_evaluate_probabilities_has_rps():
    probs = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    metrics = evaluate_probabilities(["H", "A"], probs)
    assert "rps" in metrics and 0.0 <= metrics["rps"] <= 1.0


# ------------------- simulacion de grupos y reglas ------------------------- #

def test_third_place_assignment_respects_allowed_groups(wc_data):
    third_table = wc_data[3]
    # 8 grupos cualquiera entre los permitidos; debe existir asignacion factible.
    qualifying = ["A", "B", "C", "D", "E", "F", "G", "H"]
    assignment = assign_thirds_to_slots(qualifying, third_table)
    assert assignment is not None
    allowed = {row["third_slot"]: set(row["allowed_groups"]) for _, row in third_table.iterrows()}
    assert len(set(assignment.values())) == 8  # sin repetir grupo
    for slot, group in assignment.items():
        assert group in allowed[slot]


def test_group_stage_picks_exactly_8_thirds(predictor, wc_data):
    _, schedule, _, _ = wc_data
    fixtures = precompute_group_fixtures(schedule, predictor)
    rng = np.random.default_rng(0)
    positions, best_thirds = simulate_group_stage(fixtures, rng)
    assert len(positions) == 12
    assert all(len(v) == 4 for v in positions.values())
    assert len(best_thirds) == 8


def test_full_tournament_probabilities_consistent(predictor, wc_data):
    _, schedule, bracket, third = wc_data
    summary = run_tournament(predictor, schedule, bracket, third, n_simulations=300, random_seed=1)
    # Exactamente un campeon por simulacion.
    assert abs(summary["champion"].sum() - 1.0) < 1e-9
    # Exactamente 32 clasificados por simulacion.
    assert abs(summary["qualified"].sum() - 32.0) < 1e-6
    # Monotonia de avance por ronda.
    for col_a, col_b in [
        ("advance_r32", "advance_r16"), ("advance_r16", "advance_qf"),
        ("advance_qf", "advance_sf"), ("advance_sf", "advance_final"),
        ("advance_final", "champion"),
    ]:
        assert (summary[col_a] + 1e-9 >= summary[col_b]).all(), f"{col_a} < {col_b}"
    # Probabilidades en [0,1].
    prob_cols = [c for c in summary.columns if c != "team"]
    assert (summary[prob_cols] >= -1e-9).all().all()
    assert (summary[prob_cols] <= 1 + 1e-9).all().all()
