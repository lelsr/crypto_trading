"""CLI entrypoint for manual or looped scan cycles."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.scheduler import LoopScheduler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crypto perp signal scan cycle")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run one scan cycle")
    mode.add_argument("--loop", action="store_true", help="run scan cycles continuously")
    parser.add_argument("--config", default="config/settings.yaml", help="path to settings yaml")
    parser.add_argument("--loop-minutes", type=int, default=38, help="loop interval in minutes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, orchestrator: Any | None = None) -> int:
    args = parse_args(argv)
    if orchestrator is None:
        raise RuntimeError("orchestrator construction is not wired until real adapters are configured")

    scheduler = LoopScheduler(orchestrator=orchestrator, loop_minutes=args.loop_minutes)
    if args.once:
        scheduler.run_once()
        return 0
    scheduler.run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
