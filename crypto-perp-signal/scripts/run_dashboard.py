"""CLI entrypoint for the local Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dashboard import run_dashboard


def main() -> int:
    run_dashboard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
