from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class DataSource:
    name: str
    url: str
    filename: str
    source_type: str
    notes: str


OPEN_SOURCES: tuple[DataSource, ...] = (
    DataSource(
        name="international_results",
        url="https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
        filename="results.csv",
        source_type="match_results",
        notes="Men's full international results. Snapshot before modeling.",
    ),
    DataSource(
        name="international_shootouts",
        url="https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv",
        filename="shootouts.csv",
        source_type="shootouts",
        notes="Penalty shootout winners for knockout modeling.",
    ),
    DataSource(
        name="international_goalscorers",
        url="https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv",
        filename="goalscorers.csv",
        source_type="goalscorers",
        notes="Optional player-level scorer data; not required for base model.",
    ),
)


REQUIRED_RESULTS_COLUMNS = {
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


def download_file(
    source: DataSource,
    raw_dir: Path,
    overwrite: bool = False,
    allow_insecure_ssl: bool = False,
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    destination = raw_dir / source.filename
    if destination.exists() and not overwrite:
        return destination

    context = ssl._create_unverified_context() if allow_insecure_ssl else ssl.create_default_context()
    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": "worldcup-2026-predictor/1.0"},
    )
    with urllib.request.urlopen(request, context=context, timeout=60) as response:
        destination.write_bytes(response.read())
    return destination


def write_source_manifest(
    sources: Iterable[DataSource],
    raw_dir: Path,
    filename: str = "source_manifest.json",
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / filename
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [asdict(source) for source in sources],
        "manual_sources_required": [
            {
                "name": "fifa_mens_world_ranking",
                "url": "https://inside.fifa.com/fifa-world-ranking/men",
                "notes": "Save the official ranking table as a dated CSV snapshot before training final 2026 predictions.",
            },
            {
                "name": "fifa_world_cup_2026_schedule",
                "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/match-schedule",
                "notes": "Save official fixtures, venues, kickoff times, groups, and results as a dated CSV snapshot.",
            },
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def validate_results_schema(path: Path) -> None:
    sample = pd.read_csv(path, nrows=10)
    missing = REQUIRED_RESULTS_COLUMNS - set(sample.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")


def collect_open_sources(
    raw_dir: str | Path,
    overwrite: bool = False,
    allow_insecure_ssl: bool = False,
) -> list[Path]:
    raw_path = Path(raw_dir)
    downloaded: list[Path] = []
    for source in OPEN_SOURCES:
        path = download_file(
            source,
            raw_path,
            overwrite=overwrite,
            allow_insecure_ssl=allow_insecure_ssl,
        )
        downloaded.append(path)
        if source.filename == "results.csv":
            validate_results_schema(path)
    write_source_manifest(OPEN_SOURCES, raw_path)
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Download open football data snapshots.")
    parser.add_argument("--raw-dir", default="data/raw", help="Raw data directory.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing snapshots.")
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="Allow downloads when the local CA store breaks TLS verification. Do not use for untrusted sources.",
    )
    args = parser.parse_args()
    paths = collect_open_sources(
        args.raw_dir,
        overwrite=args.overwrite,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
