from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from versarr.application.resilient_provider import ResilientProvider
from versarr.domain import ProviderResult, ProviderStatus, TrackIdentity

_IDENTITY = TrackIdentity(
    title="Song",
    artist="Artist",
    album=None,
    album_artist=None,
    track_number=None,
    disc_number=None,
    duration_seconds=180,
    release_year=None,
)


def _result(status: ProviderStatus, retry_after: float | None = None) -> ProviderResult:
    return ProviderResult(
        status=status,
        provider_name="lrclib",
        lyrics_text="x" if status == ProviderStatus.MATCHED else None,
        synced=False,
        provider_track_id=None,
        confidence=1.0 if status == ProviderStatus.MATCHED else 0.0,
        retry_after_seconds=retry_after,
    )


class _ScriptedProvider:
    def __init__(self, script: Callable[[], ProviderResult]) -> None:
        self.script = script
        self.calls = 0

    async def fetch(self, identity: TrackIdentity) -> ProviderResult:
        del identity
        self.calls += 1
        return self.script()


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _gate(inner: _ScriptedProvider, clock: _Clock, **overrides: float) -> ResilientProvider:
    settings = {"min_interval_seconds": 0.0, "failure_threshold": 2, "open_seconds": 60, "max_open_seconds": 300, **overrides}
    return ResilientProvider(inner, monotonic=clock.monotonic, sleep=clock.sleep, **settings)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_requests_are_spaced_by_min_interval() -> None:
    clock = _Clock()
    inner = _ScriptedProvider(lambda: _result(ProviderStatus.NOT_FOUND))
    gate = _gate(inner, clock, min_interval_seconds=2.0)

    for _ in range(3):
        await gate.fetch(_IDENTITY)

    assert clock.slept == [2.0, 2.0]


@pytest.mark.asyncio
async def test_concurrent_callers_share_the_pace() -> None:
    clock = _Clock()
    inner = _ScriptedProvider(lambda: _result(ProviderStatus.NOT_FOUND))
    gate = _gate(inner, clock, min_interval_seconds=1.0)

    await asyncio.gather(*(gate.fetch(_IDENTITY) for _ in range(4)))

    assert clock.now - 1000.0 == pytest.approx(3.0)
    assert inner.calls == 4


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_and_throttles_without_calling_provider() -> None:
    clock = _Clock()
    inner = _ScriptedProvider(lambda: _result(ProviderStatus.TRANSIENT_FAILURE))
    gate = _gate(inner, clock)

    first = await gate.fetch(_IDENTITY)
    second = await gate.fetch(_IDENTITY)
    throttled = await gate.fetch(_IDENTITY)

    assert first.status == second.status == ProviderStatus.TRANSIENT_FAILURE
    assert throttled.status == ProviderStatus.THROTTLED
    assert throttled.retry_after_seconds == pytest.approx(60.0)
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_retry_after_extends_open_window_up_to_cap() -> None:
    clock = _Clock()
    inner = _ScriptedProvider(lambda: _result(ProviderStatus.TRANSIENT_FAILURE, retry_after=120))
    gate = _gate(inner, clock)

    await gate.fetch(_IDENTITY)
    await gate.fetch(_IDENTITY)
    throttled = await gate.fetch(_IDENTITY)

    assert throttled.retry_after_seconds == pytest.approx(120.0)

    long_inner = _ScriptedProvider(lambda: _result(ProviderStatus.TRANSIENT_FAILURE, retry_after=10_000))
    capped = _gate(long_inner, _Clock())
    await capped.fetch(_IDENTITY)
    await capped.fetch(_IDENTITY)
    assert (await capped.fetch(_IDENTITY)).retry_after_seconds == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_probe_after_window_closes_circuit_on_success() -> None:
    clock = _Clock()
    outcomes = [ProviderStatus.TRANSIENT_FAILURE, ProviderStatus.TRANSIENT_FAILURE, ProviderStatus.MATCHED, ProviderStatus.MATCHED]
    inner = _ScriptedProvider(lambda: _result(outcomes.pop(0)))
    gate = _gate(inner, clock)
    await gate.fetch(_IDENTITY)
    await gate.fetch(_IDENTITY)
    clock.now += 61

    probe = await gate.fetch(_IDENTITY)
    after = await gate.fetch(_IDENTITY)

    assert probe.status == after.status == ProviderStatus.MATCHED
    assert inner.calls == 4


@pytest.mark.asyncio
async def test_failed_probe_reopens_with_longer_window_and_blocks_other_callers_during_probe() -> None:
    clock = _Clock()
    inner = _ScriptedProvider(lambda: _result(ProviderStatus.TRANSIENT_FAILURE))
    gate = _gate(inner, clock)
    await gate.fetch(_IDENTITY)
    await gate.fetch(_IDENTITY)
    clock.now += 61

    probe = await gate.fetch(_IDENTITY)
    reopened = await gate.fetch(_IDENTITY)

    assert probe.status == ProviderStatus.TRANSIENT_FAILURE
    assert reopened.status == ProviderStatus.THROTTLED
    assert reopened.retry_after_seconds == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_non_transient_results_reset_failure_count() -> None:
    clock = _Clock()
    outcomes = iter([ProviderStatus.TRANSIENT_FAILURE, ProviderStatus.NOT_FOUND, ProviderStatus.TRANSIENT_FAILURE, ProviderStatus.TRANSIENT_FAILURE])
    inner = _ScriptedProvider(lambda: _result(next(outcomes)))
    gate = _gate(inner, clock)

    results = [await gate.fetch(_IDENTITY) for _ in range(4)]

    assert [r.status for r in results] == [
        ProviderStatus.TRANSIENT_FAILURE,
        ProviderStatus.NOT_FOUND,
        ProviderStatus.TRANSIENT_FAILURE,
        ProviderStatus.TRANSIENT_FAILURE,
    ]
    assert (await gate.fetch(_IDENTITY)).status == ProviderStatus.THROTTLED
