from __future__ import annotations

import asyncio

import pytest

from versarr.application.supervision import LoopSupervisor


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[str] = []

    def error(self, event: str, **_: object) -> None:
        self.events.append(event)


async def _wait_for(condition: object, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():  # type: ignore[operator]
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail("condition not met in time")
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_failing_step_is_retried_and_loop_keeps_running() -> None:
    calls = 0
    logger = _RecordingLogger()
    supervisor = LoopSupervisor(stop_event=asyncio.Event(), logger=logger, backoff_seconds=0.001)

    async def step() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(0.001)

    supervisor.spawn("flaky", step)
    await _wait_for(lambda: calls >= 3)

    assert logger.events == ["runtime_loop_step_failed"]
    assert supervisor.healthy
    await supervisor.stop()


@pytest.mark.asyncio
async def test_repeated_failures_make_supervisor_unhealthy_until_recovery() -> None:
    failing = True
    supervisor = LoopSupervisor(stop_event=asyncio.Event(), logger=_RecordingLogger(), failure_threshold=2, backoff_seconds=0.001)

    async def step() -> None:
        await asyncio.sleep(0.001)
        if failing:
            raise RuntimeError("down")

    supervisor.spawn("down", step)
    await _wait_for(lambda: not supervisor.healthy)

    failing = False
    await _wait_for(lambda: supervisor.healthy)
    await supervisor.stop()


@pytest.mark.asyncio
async def test_unexpectedly_finished_loop_is_unhealthy() -> None:
    supervisor = LoopSupervisor(stop_event=asyncio.Event(), logger=_RecordingLogger())

    async def step() -> None:
        raise asyncio.CancelledError

    supervisor.spawn("cancelled", step)
    await _wait_for(lambda: not supervisor.healthy)
    await supervisor.stop()


@pytest.mark.asyncio
async def test_stop_cancels_loops_and_is_healthy_after_stop_requested() -> None:
    stop_event = asyncio.Event()
    supervisor = LoopSupervisor(stop_event=stop_event, logger=_RecordingLogger())

    async def step() -> None:
        await asyncio.sleep(10)

    supervisor.spawn("idle", step)
    stop_event.set()
    await supervisor.stop()

    assert supervisor.healthy
