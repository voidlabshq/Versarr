from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from versarr.application.contracts import LyricsProvider
from versarr.domain import ProviderResult, ProviderStatus, TrackIdentity

_PROBE_RETRY_SECONDS = 5.0


class RequestPacer:
    """Spaces outgoing requests at least ``min_interval_seconds`` apart; callers wait their turn."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval = min_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = self._monotonic()
            wait = self._next_slot - now
            if wait > 0:
                await self._sleep(wait)
                now = self._monotonic()
            self._next_slot = max(now, self._next_slot) + self._min_interval


class ResilientProvider(LyricsProvider):
    """Wraps a provider with a circuit breaker shared by all workers.

    - After ``failure_threshold`` consecutive transient failures the circuit opens. While open,
      ``fetch`` returns ``THROTTLED`` immediately (with the remaining wait) so jobs defer without
      spending retry attempts. The open window honors the provider's ``Retry-After`` and otherwise
      doubles on each consecutive trip up to ``max_open_seconds``.
    - When the window ends a single probe request is let through; success closes the circuit,
      failure reopens it.
    """

    def __init__(
        self,
        inner: LyricsProvider,
        *,
        failure_threshold: int,
        open_seconds: float,
        max_open_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
        metrics: Any = None,
        logger: Any = None,
    ) -> None:
        self._inner = inner
        self._failure_threshold = failure_threshold
        self._open_seconds = open_seconds
        self._max_open_seconds = max_open_seconds
        self._monotonic = monotonic
        self._metrics = metrics
        self._logger = logger
        self._consecutive_failures = 0
        self._trips = 0
        self._open_until: float | None = None
        self._probe_in_flight = False

    async def fetch(self, identity: TrackIdentity) -> ProviderResult:
        wait = self._blocked_for()
        if wait is not None:
            if self._metrics is not None:
                self._metrics.provider_requests_total.labels(provider="lrclib", status="throttled").inc()
            return ProviderResult(
                status=ProviderStatus.THROTTLED,
                provider_name="lrclib",
                lyrics_text=None,
                synced=False,
                provider_track_id=None,
                confidence=0.0,
                retry_after_seconds=wait,
            )
        try:
            result = await self._inner.fetch(identity)
        except BaseException:
            self._probe_in_flight = False
            raise
        self._record(result)
        return result

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()

    def _blocked_for(self) -> float | None:
        """Seconds the caller must wait, or ``None`` if a request may go out now."""
        if self._open_until is None:
            return None
        now = self._monotonic()
        if now < self._open_until:
            return self._open_until - now
        if self._probe_in_flight:
            return _PROBE_RETRY_SECONDS
        self._probe_in_flight = True
        return None

    def _record(self, result: ProviderResult) -> None:
        self._probe_in_flight = False
        if result.status != ProviderStatus.TRANSIENT_FAILURE:
            self._consecutive_failures = 0
            self._trips = 0
            self._open_until = None
            return
        self._consecutive_failures += 1
        if self._open_until is None and self._consecutive_failures < self._failure_threshold:
            return
        window = min(self._open_seconds * 2**self._trips, self._max_open_seconds)
        window = min(max(window, result.retry_after_seconds or 0.0), self._max_open_seconds)
        self._trips += 1
        self._open_until = self._monotonic() + window
        if self._logger is not None:
            self._logger.warning("provider_circuit_opened", open_seconds=window, consecutive_failures=self._consecutive_failures)
