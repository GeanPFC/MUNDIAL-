from __future__ import annotations

import argparse
import json
import mimetypes
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.elo_model import EloModel
from src.poisson_model import PoissonGoalModel
from src.preprocessing import load_results


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
RESULTS_PATH = ROOT / "data/raw/results.csv"
BACKTEST_PATH = ROOT / "reports/backtest_worldcups_2014_2018_2022.csv"
DEFAULT_CUTOFF = "2026-06-13"


@lru_cache(maxsize=1)
def load_all_results() -> pd.DataFrame:
    return load_results(RESULTS_PATH)


@lru_cache(maxsize=12)
def build_models(as_of: str) -> tuple[EloModel, PoissonGoalModel, int, str]:
    cutoff = pd.Timestamp(as_of)
    results = load_all_results()
    train = results[results["date"] <= cutoff].copy()
    if train.empty:
        raise ValueError(f"No hay partidos antes de la fecha de corte {as_of}.")
    elo = EloModel().fit(train)
    poisson = PoissonGoalModel(fit_dixon_coles=False).fit(train, as_of=cutoff)
    max_date = train["date"].max().strftime("%Y-%m-%d")
    return elo, poisson, len(train), max_date


def json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "y", "on"}


def get_first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key, [])
    return values[0].strip() if values else default


def api_teams(handler: SimpleHTTPRequestHandler) -> None:
    results = load_all_results()
    cutoff = pd.Timestamp(DEFAULT_CUTOFF)
    usable = results[results["date"] <= cutoff]
    teams = sorted(set(usable["home_team"]).union(usable["away_team"]))
    json_response(
        handler,
        {
            "teams": teams,
            "default_cutoff": DEFAULT_CUTOFF,
            "n_matches": int(len(usable)),
            "snapshot_max_date": results["date"].max().strftime("%Y-%m-%d"),
        },
    )


def api_predict(handler: SimpleHTTPRequestHandler, params: dict[str, list[str]]) -> None:
    team_a = get_first(params, "team_a")
    team_b = get_first(params, "team_b")
    as_of = get_first(params, "as_of", DEFAULT_CUTOFF)
    neutral = parse_bool(get_first(params, "neutral", "true"))

    if not team_a or not team_b:
        json_response(handler, {"error": "Selecciona ambos equipos."}, status=HTTPStatus.BAD_REQUEST)
        return
    if team_a == team_b:
        json_response(handler, {"error": "Los equipos deben ser distintos."}, status=HTTPStatus.BAD_REQUEST)
        return

    try:
        cutoff = pd.Timestamp(as_of)
    except Exception:
        json_response(handler, {"error": "Fecha de corte invalida. Usa YYYY-MM-DD."}, status=HTTPStatus.BAD_REQUEST)
        return

    try:
        elo, poisson, n_train, max_train_date = build_models(cutoff.strftime("%Y-%m-%d"))
        elo_pred = elo.predict_match(team_a, team_b, neutral=neutral)
        goal_pred = poisson.predict_match(team_a, team_b, neutral=neutral)
    except Exception as exc:
        json_response(handler, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        return

    results = load_all_results()
    leakage_warning = None
    if results["date"].max() > cutoff:
        leakage_warning = (
            "El snapshot contiene filas posteriores a la fecha de corte; "
            "la API filtro el entrenamiento para evitar leakage."
        )

    json_response(
        handler,
        {
            "teams": {"team_a": team_a, "team_b": team_b},
            "as_of": cutoff.strftime("%Y-%m-%d"),
            "neutral": neutral,
            "n_train_matches": n_train,
            "max_train_date": max_train_date,
            "probabilities": {
                "team_a_win": elo_pred.p_home_win,
                "draw": elo_pred.p_draw,
                "team_b_win": elo_pred.p_away_win,
            },
            "expected_goals": {
                "team_a": goal_pred.expected_goals_home,
                "team_b": goal_pred.expected_goals_away,
            },
            "most_likely_score": {
                "team_a": goal_pred.most_likely_score[0],
                "team_b": goal_pred.most_likely_score[1],
            },
            "goal_intervals": {
                "team_a": goal_pred.home_goal_interval,
                "team_b": goal_pred.away_goal_interval,
            },
            "uncertainty": goal_pred.uncertainty,
            "influential_variables": {
                "elo_team_a": elo_pred.rating_home,
                "elo_team_b": elo_pred.rating_away,
                "elo_diff_adjusted": elo_pred.rating_diff,
                **goal_pred.influential_variables,
            },
            "model_decision": (
                "Backtesting 2014-2018-2022 favorecio Elo para 1X2; "
                "Poisson se usa para goles esperados e intervalos."
            ),
            "warning": leakage_warning,
        },
    )


def api_backtest(handler: SimpleHTTPRequestHandler) -> None:
    if not BACKTEST_PATH.exists():
        json_response(handler, {"error": "No existe el reporte de backtesting. Ejecuta run_backtest.py."}, status=404)
        return
    scores = pd.read_csv(BACKTEST_PATH)
    summary = (
        scores.groupby("model")[["log_loss", "brier", "accuracy", "ece"]]
        .mean()
        .sort_values("log_loss")
        .reset_index()
    )
    json_response(
        handler,
        {
            "rows": summary.to_dict(orient="records"),
            "source": str(BACKTEST_PATH),
        },
    )


class PredictorHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/teams":
            api_teams(self)
            return
        if parsed.path == "/api/predict":
            api_predict(self, parse_qs(parsed.query))
            return
        if parsed.path == "/api/backtest":
            api_backtest(self)
            return
        self.serve_static(parsed.path)

    def serve_static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (STATIC_DIR / requested).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or target.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web UI for the World Cup predictor.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not RESULTS_PATH.exists():
        raise SystemExit("Falta data/raw/results.csv. Ejecuta src.data_collection primero.")
    server = ThreadingHTTPServer((args.host, args.port), PredictorHandler)
    print(f"Servidor listo: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
