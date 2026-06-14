"""Test de paridad Python <-> JS (auditoria M4).

Verifica que la implementacion Elo/Poisson de Python (src/) y la de JavaScript
(api/_model.js, espejo desplegado en Vercel) produzcan probabilidades 1X2 y goles
esperados muy parecidos para los mismos inputs.

Tolerancia: ambas leen la misma fuente (martj42) pero pueden diferir en la fecha
exacta del snapshot remoto vs el local; por eso se compara con tolerancia, no por
igualdad exacta. Una divergencia mayor que la tolerancia indica un bug de paridad.

Ejecutar:  python scripts/parity_check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.elo_model import EloModel  # noqa: E402
from src.poisson_model import PoissonGoalModel  # noqa: E402
from src.preprocessing import load_results  # noqa: E402

CASES = [
    ("Argentina", "France"),
    ("Spain", "Brazil"),
    ("Mexico", "South Africa"),
]
AS_OF = "2026-06-13"
PROB_TOL = 0.03   # diferencia maxima aceptable en probabilidad 1X2
XG_TOL = 0.20     # diferencia maxima aceptable en goles esperados


def python_prediction(results: pd.DataFrame, a: str, b: str) -> dict:
    cutoff = pd.Timestamp(AS_OF)
    train = results[results["date"] <= cutoff].copy()
    elo = EloModel().fit(train)
    poisson = PoissonGoalModel(fit_dixon_coles=False).fit(train, as_of=cutoff)
    ep = elo.predict_match(a, b, neutral=True)
    gp = poisson.predict_match(a, b, neutral=True)
    return {
        "probs": [ep.p_home_win, ep.p_draw, ep.p_away_win],
        "xg": [gp.expected_goals_home, gp.expected_goals_away],
    }


def js_prediction(a: str, b: str) -> dict:
    script = (
        "import predict from './api/predict.js';"
        "const res={headers:{},statusCode:200,setHeader(k,v){this.headers[k]=v;},"
        "status(c){this.statusCode=c;return this;},send(b){this.body=b;}};"
        f"await predict({{query:{{team_a:'{a}',team_b:'{b}',as_of:'{AS_OF}',neutral:'true'}},headers:{{}}}},res);"
        "const d=JSON.parse(res.body);"
        "console.log(JSON.stringify({probs:[d.probabilities.team_a_win,d.probabilities.draw,d.probabilities.team_b_win],"
        "xg:[d.expected_goals.team_a,d.expected_goals.team_b]}));"
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"Node fallo: {out.stderr[-500:]}")
    line = [ln for ln in out.stdout.strip().splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def main() -> int:
    results = load_results(ROOT / "data/raw/results.csv")
    failures = 0
    print(f"Paridad Python<->JS (as_of {AS_OF}, sede neutral). Tol probs={PROB_TOL}, xg={XG_TOL}\n")
    for a, b in CASES:
        py = python_prediction(results, a, b)
        js = js_prediction(a, b)
        dprob = max(abs(p - q) for p, q in zip(py["probs"], js["probs"]))
        dxg = max(abs(p - q) for p, q in zip(py["xg"], js["xg"]))
        ok = dprob <= PROB_TOL and dxg <= XG_TOL
        failures += 0 if ok else 1
        print(f"{'OK ' if ok else 'FAIL'} {a} vs {b}")
        print(f"     Py probs {[round(x,3) for x in py['probs']]}  JS probs {[round(x,3) for x in js['probs']]}  dmax={dprob:.4f}")
        print(f"     Py xg    {[round(x,2) for x in py['xg']]}  JS xg    {[round(x,2) for x in js['xg']]}  dmax={dxg:.4f}")
    if failures:
        print(f"\n{failures} casos exceden la tolerancia de paridad.")
        return 1
    print("\nParidad Python<->JS dentro de tolerancia en todos los casos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
