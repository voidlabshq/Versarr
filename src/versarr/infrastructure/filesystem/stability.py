from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from versarr.application.contracts import StabilityDetector
from versarr.domain import FileStabilityState


class DebounceStabilityDetector(StabilityDetector):
    def __init__(
        self,
        *,
        quiet_period_seconds: int,
        probe_gap_seconds: int,
    ) -> None:
        self._quiet_period = timedelta(seconds=quiet_period_seconds)
        self._probe_gap = timedelta(seconds=probe_gap_seconds)
        self._states: dict[Path, FileStabilityState] = {}
        self._last_probe_at: dict[Path, datetime] = {}

    async def observe(self, candidate_path: Path, event_kind: str) -> None:
        del event_kind
        now = datetime.now(UTC)
        state = self._states.get(candidate_path)
        if state is None:
            self._states[candidate_path] = FileStabilityState(candidate_path=candidate_path, first_seen_at=now, last_seen_at=now)
            return
        state.last_seen_at = now
        state.successful_probes = 0

    async def poll_ready_paths(self) -> list[Path]:
        now = datetime.now(UTC)
        ready: list[Path] = []
        for path, state in list(self._states.items()):
            if now - state.last_seen_at < self._quiet_period:
                continue
            last_probe = self._last_probe_at.get(path)
            if last_probe and now - last_probe < self._probe_gap:
                continue
            self._last_probe_at[path] = now
            try:
                stat = await asyncio.to_thread(path.stat)
            except OSError:
                self._states.pop(path, None)
                self._last_probe_at.pop(path, None)
                continue
            if state.last_size == stat.st_size and state.last_mtime_ns == stat.st_mtime_ns:
                state.successful_probes += 1
            else:
                state.successful_probes = 1
                state.last_size = stat.st_size
                state.last_mtime_ns = stat.st_mtime_ns
                continue
            if state.successful_probes >= 2:
                ready.append(path)
                self._states.pop(path, None)
                self._last_probe_at.pop(path, None)
        return ready
