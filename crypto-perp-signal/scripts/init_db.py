"""Initialize the local SQLite database."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from infrastructure.sqlite_repo import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


def load_db_path(config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    sqlite_path = config.get("storage", {}).get("sqlite_path", "data/signals.db")
    return PROJECT_ROOT / sqlite_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize SQLite schema")
    parser.add_argument("--db-path", type=Path, default=None, help="Override SQLite database path")
    args = parser.parse_args()

    db_path = args.db_path or load_db_path()
    init_db(db_path)
    print(f"Initialized SQLite database at {db_path}")


if __name__ == "__main__":
    main()
