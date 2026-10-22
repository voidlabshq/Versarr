from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

MAX_BACKOFF_SECONDS = 60.0


class LoopSupervisor:
    """Runs background loop steps, surviving step failures and reporting health.

    A step is one iteration of work (including any idle sleep). A step that raises is logged and
    retried after an exponentially growing delay instead of ending its loop. The supervisor is
    unhealthy while any loop has failed ``failure_threshold`` times in a row, or if a loop task
    ended without a stop having been requested.
    """

    def __init__(
        self,
        *,
        stop_event: asyncio.Event,
        logger: Any,
        failure_threshold: int = 3,
        backoff_seconds: float = 5.0,
    ) -> None:
        self._stop_event = stop_event
        self._logger = logger
        self._failure_threshold = failure_threshold
        self._backoff_seconds = backoff_seconds
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._failures: dict[str, int] = {}

    def spawn(self, name: str, step: Callable[[], Awaitable[None]]) -> None:
        self._failures[name] = 0
        self._tasks[name] = asyncio.create_task(self._run(name, step), name=name)

    @property
    def healthy(self) -> bool:
        if any(count >= self._failure_threshold for count in self._failures.values()):
            return False
        if self._stop_event.is_set():
            return True
        return not any(task.done() for task in self._tasks.values())

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._failures.clear()

    async def _run(self, name: str, step: Callable[[], Awaitable[None]]) -> None:
        while not self._stop_event.is_set():
            try:
                await step()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._failures[name] += 1
                self._logger.error(
                    "runtime_loop_step_failed",
                    loop=name,
                    consecutive_failures=self._failures[name],
                    error_class=type(error).__name__,
                    error_message=str(error),
                )
                delay = min(self._backoff_seconds * 2 ** (self._failures[name] - 1), MAX_BACKOFF_SECONDS)
                await asyncio.sleep(delay)
            else:
                self._failures[name] = 0
