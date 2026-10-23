from __future__ import annotations

import os
from pathlib import Path

import pytest

from versarr.infrastructure.filesystem import DebounceStabilityDetector


def _detector() -> DebounceStabilityDetector:
    return DebounceStabilityDetector(quiet_period_seconds=0, probe_gap_seconds=0)


@pytest.mark.asyncio
async def test_file_is_ready_after_two_identical_probes(tmp_path: Path) -> None:
    path = tmp_path / "song.flac"
    path.write_bytes(b"audio")
    detector = _detector()
    await detector.observe(path, "created")

    assert await detector.poll_ready_paths() == []
    assert await detector.poll_ready_paths() == [path]
    assert await detector.poll_ready_paths() == []


@pytest.mark.asyncio
async def test_growing_file_is_not_ready_until_it_stops_changing(tmp_path: Path) -> None:
    path = tmp_path / "song.flac"
    path.write_bytes(b"a")
    detector = _detector()
    await detector.observe(path, "created")
    await detector.poll_ready_paths()

    path.write_bytes(b"aaaa")

    assert await detector.poll_ready_paths() == []
    assert await detector.poll_ready_paths() == [path]


@pytest.mark.asyncio
async def test_mtime_change_resets_stability(tmp_path: Path) -> None:
    path = tmp_path / "song.flac"
    path.write_bytes(b"abc")
    detector = _detector()
    await detector.observe(path, "created")
    await detector.poll_ready_paths()

    os.utime(path, ns=(1, path.stat().st_mtime_ns + 10_000_000_000))

    assert await detector.poll_ready_paths() == []


@pytest.mark.asyncio
async def test_new_event_for_pending_path_restarts_the_wait(tmp_path: Path) -> None:
    path = tmp_path / "song.flac"
    path.write_bytes(b"abc")
    detector = DebounceStabilityDetector(quiet_period_seconds=3600, probe_gap_seconds=0)
    await detector.observe(path, "created")
    await detector.observe(path, "modified")

    assert await detector.poll_ready_paths() == []


@pytest.mark.asyncio
async def test_vanished_file_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "song.flac"
    path.write_bytes(b"abc")
    detector = _detector()
    await detector.observe(path, "created")
    path.unlink()

    assert await detector.poll_ready_paths() == []
    assert await detector.poll_ready_paths() == []
