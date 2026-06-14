"""Ingesta y validacion de los datos oficiales del Mundial 2026.

Construye un snapshot reproducible:
  - grupos oficiales (wc2026_groups.csv, fuente: sorteo FIFA 05-dic-2025);
  - calendario de fase de grupos derivado de results.csv (con resultados ya jugados);
  - malla de eliminatorias (wc2026_bracket.csv);
  - tabla de asignacion de terceros (wc2026_third_place_allocation.csv).

Tambien calcula hashes SHA-256 para versionado y verificacion (auditoria A2).

Todos los nombres de seleccion usan la convencion del dataset martj42/international_results
para empatar sin ambiguedad con results.csv.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

WORLD_CUP_NAME = "FIFA World Cup"
WC2026_YEAR = 2026


def sha256_file(path: str | Path) -> str:
    """Hash SHA-256 de un archivo, para fijar la version del snapshot."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_groups(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"group", "team", "pot", "confederation", "is_host"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"wc2026_groups.csv missing columns: {sorted(missing)}")
    if len(df) != 48:
        raise ValueError(f"Expected 48 teams in groups, got {len(df)}.")
    if df["group"].nunique() != 12:
        raise ValueError(f"Expected 12 groups, got {df['group'].nunique()}.")
    counts = df.groupby("group").size()
    bad = counts[counts != 4]
    if not bad.empty:
        raise ValueError(f"Groups without exactly 4 teams: {bad.to_dict()}")
    return df


def load_bracket(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"match_id", "stage", "order", "home_slot", "away_slot"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"wc2026_bracket.csv missing columns: {sorted(missing)}")
    return df.sort_values("order").reset_index(drop=True)


def load_third_place_table(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"r32_match", "third_slot", "allowed_groups"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"third place table missing columns: {sorted(missing)}")
    return df


def validate_groups_against_results(groups: pd.DataFrame, results_csv: str | Path) -> list[str]:
    """Devuelve la lista de equipos de grupo que NO aparecen en results.csv.

    Una lista vacia significa que todos los nombres empatan (sin errores de mapeo).
    """
    raw = pd.read_csv(results_csv, usecols=["home_team", "away_team"])
    known = set(raw["home_team"]).union(raw["away_team"])
    return sorted(team for team in groups["team"] if team not in known)


def build_group_schedule(
    results_csv: str | Path,
    groups: pd.DataFrame,
    year: int = WC2026_YEAR,
) -> pd.DataFrame:
    """Extrae los 72 partidos de fase de grupos desde results.csv y les asigna grupo.

    Marca status=played si el marcador esta confirmado; scheduled si viene como NA.
    """
    team_to_group = dict(zip(groups["team"], groups["group"]))
    raw = pd.read_csv(results_csv)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    mask = (raw["tournament"] == WORLD_CUP_NAME) & (raw["date"].dt.year == year)
    wc = raw.loc[mask].copy()

    rows: list[dict] = []
    match_counter = 1
    for _, row in wc.sort_values("date").iterrows():
        home, away = row["home_team"], row["away_team"]
        g_home = team_to_group.get(home)
        g_away = team_to_group.get(away)
        # Un partido de grupo tiene ambos equipos en el mismo grupo.
        if g_home is None or g_away is None or g_home != g_away:
            continue
        home_score = pd.to_numeric(row["home_score"], errors="coerce")
        away_score = pd.to_numeric(row["away_score"], errors="coerce")
        played = pd.notna(home_score) and pd.notna(away_score)
        rows.append(
            {
                "match_id": f"G{match_counter:02d}",
                "stage": "group",
                "group": g_home,
                "date": row["date"].date().isoformat(),
                "venue": row.get("city", ""),
                "country": row.get("country", ""),
                "home_team": home,
                "away_team": away,
                "neutral": bool(str(row.get("neutral", "False")).strip().lower() in {"true", "1", "yes", "y"}),
                "home_score": int(home_score) if played else "",
                "away_score": int(away_score) if played else "",
                "status": "played" if played else "scheduled",
            }
        )
        match_counter += 1
    return pd.DataFrame(rows)


def write_group_schedule(schedule: pd.DataFrame, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    schedule.to_csv(out, index=False)
    return out


def update_manifest(
    manifest_path: str | Path,
    tracked_files: dict[str, str | Path],
    cutoff_date: str,
) -> Path:
    """Escribe/actualiza el manifest con hashes SHA-256 y fecha de corte."""
    manifest_path = Path(manifest_path)
    existing: dict = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    snapshot = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff_date": str(cutoff_date),
        "files": {},
    }
    for name, path in tracked_files.items():
        path = Path(path)
        if path.exists():
            snapshot["files"][name] = {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
    existing["wc2026_snapshot"] = snapshot
    manifest_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return manifest_path


def load_full_schedule(
    schedule_csv: str | Path,
    bracket_csv: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga calendario de grupos + malla de eliminatorias listos para simular."""
    schedule = pd.read_csv(schedule_csv)
    bracket = load_bracket(bracket_csv)
    return schedule, bracket
