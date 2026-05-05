from __future__ import annotations

from app.scheduler import LoopScheduler
from scripts.run_cycle import main, parse_args


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return {"ok": True}


def test_scheduler_runs_limited_loop_and_can_stop() -> None:
    orchestrator = FakeOrchestrator()
    sleeps: list[int] = []
    scheduler = LoopScheduler(orchestrator=orchestrator, loop_minutes=38, sleep_func=lambda seconds: sleeps.append(seconds))

    completed = scheduler.run_loop(max_cycles=2)

    assert completed == 2
    assert orchestrator.calls == 2
    assert sleeps == [38 * 60]


def test_scheduler_stop_prevents_background_runaway() -> None:
    orchestrator = FakeOrchestrator()
    scheduler = LoopScheduler(orchestrator=orchestrator)
    scheduler.stop()

    assert scheduler.run_loop() == 0
    assert orchestrator.calls == 0


def test_run_cycle_once_does_not_enter_loop() -> None:
    orchestrator = FakeOrchestrator()

    exit_code = main(["--once"], orchestrator=orchestrator)

    assert exit_code == 0
    assert orchestrator.calls == 1


def test_run_cycle_parse_config_and_default_loop_minutes() -> None:
    args = parse_args(["--once", "--config", "custom.yaml"])

    assert args.once is True
    assert args.config == "custom.yaml"
    assert args.loop_minutes == 38
