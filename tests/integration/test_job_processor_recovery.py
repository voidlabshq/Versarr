from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.application.services import JobProcessor
from versarr.config import Settings
from versarr.domain import (
    JobPriority,
    LyricsPresence,
    ProviderResult,
    ProviderStatus,
    TrackIdentity,
    TrackSnapshot,
    TriggerKind,
    hash_meaningful_snapshot,
)
from versarr.infrastructure.filesystem import AtomicLrcWriter
from versarr.infrastructure.persistence import SqliteStateRepository


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: int) -> None:
        self._now += timedelta(seconds=seconds)


class _NullMetricChild:
    def inc(self, amount: int | float = 1) -> None:
        del amount

    def set(self, value: int | float) -> None:
        del value

    def observe(self, value: int | float) -> None:
        del value


class _NullMetric:
    def labels(self, **kwargs: object) -> _NullMetricChild:
        del kwargs
        return _NullMetricChild()

    def inc(self, amount: int | float = 1) -> None:
        del amount

    def dec(self, amount: int | float = 1) -> None:
        del amount

    def set(self, value: int | float) -> None:
        del value

    def observe(self, value: int | float) -> None:
        del value


class NullMetrics:
    def __init__(self) -> None:
        self.jobs_enqueued_total = _NullMetric()
        self.jobs_completed_total = _NullMetric()
        self.jobs_retried_total = _NullMetric()
        self.provider_requests_total = _NullMetric()
        self.sidecar_writes_total = _NullMetric()
        self.sidecar_conflicts_total = _NullMetric()
        self.manual_divergence_total = _NullMetric()
        self.embedded_preserved_total = _NullMetric()
        self.watcher_events_total = _NullMetric()
        self.stability_drops_total = _NullMetric()
        self.startup_recoveries_total = _NullMetric()
        self.queue_depth = _NullMetric()
        self.active_jobs = _NullMetric()
        self.watcher_roots_active = _NullMetric()
        self.readiness_state = _NullMetric()
        self.cooldowns_active = _NullMetric()
        self.control_requests_pending = _NullMetric()
        self.job_duration_seconds = _NullMetric()
        self.provider_latency_seconds = _NullMetric()
        self.sidecar_write_seconds = _NullMetric()
        self.metadata_read_seconds = _NullMetric()
        self.scan_duration_seconds = _NullMetric()
        self.stability_wait_seconds = _NullMetric()


class FakeMetadataReader:
    def __init__(self, library_root: Path, media_path: Path) -> None:
        self._library_root = library_root
        self._media_path = media_path
        self._identity = TrackIdentity(
            title="Track",
            artist="Artist",
            album="Album",
            album_artist=None,
            track_number=1,
            disc_number=1,
            duration_seconds=180,
            release_year=2024,
        )

    async def read_snapshot(self, media_path: Path, library_root: Path) -> TrackSnapshot:
        assert media_path == self._media_path
        assert library_root == self._library_root
        sidecar_path = media_path.with_suffix(".lrc")
        snapshot = TrackSnapshot(
            library_root=library_root,
            media_path=media_path,
            extension=media_path.suffix.lower(),
            file_size=media_path.stat().st_size,
            file_mtime_ns=media_path.stat().st_mtime_ns,
            identity=self._identity,
            lyrics_presence=LyricsPresence(
                sidecar_exists=sidecar_path.exists(),
                sidecar_path=sidecar_path if sidecar_path.exists() else None,
                embedded_exists=False,
            ),
            meaningful_state_hash="",
        )
        return TrackSnapshot(
            library_root=snapshot.library_root,
            media_path=snapshot.media_path,
            extension=snapshot.extension,
            file_size=snapshot.file_size,
            file_mtime_ns=snapshot.file_mtime_ns,
            identity=snapshot.identity,
            lyrics_presence=snapshot.lyrics_presence,
            meaningful_state_hash=hash_meaningful_snapshot(snapshot),
        )


@dataclass
class FakeProvider:
    lyrics_text: str
    fetch_count: int = 0
    delay_seconds: int = 0

    async def fetch(self, identity: TrackIdentity) -> ProviderResult:
        self.fetch_count += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return ProviderResult(
            status=ProviderStatus.MATCHED,
            provider_name="lrclib",
            lyrics_text=self.lyrics_text,
            synced=False,
            provider_track_id="track-1",
            confidence=1.0,
            matched_identity=identity,
        )


class FailingProvenanceRepository(SqliteStateRepository):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self.fail_record_provenance = True
        self.heartbeat_calls = 0

    async def record_provenance(self, record: object) -> None:
        if self.fail_record_provenance:
            self.fail_record_provenance = False
            msg = "simulated provenance write failure"
            raise OSError(msg)
        await super().record_provenance(record)

    async def heartbeat_job(self, job_key: str, lease_until: datetime) -> None:
        self.heartbeat_calls += 1
        await super().heartbeat_job(job_key, lease_until)


def _build_settings(library_root: Path, state_dir: Path) -> Settings:
    return Settings(
        library_roots=(library_root,),
        state_dir=state_dir,
        sqlite_path=state_dir / "state.db",
    )


async def _enqueue_job(repository: SqliteStateRepository, media_path: Path, library_root: Path) -> None:
    await repository.enqueue_path(
        library_root=library_root,
        media_path=media_path,
        trigger=TriggerKind.WATCHER,
        priority=JobPriority.WATCHER,
        event_kind="created",
    )


def _build_processor(
    repository: SqliteStateRepository,
    library_root: Path,
    media_path: Path,
    provider: FakeProvider,
    *,
    now: datetime,
) -> tuple[JobProcessor, FixedClock]:
    clock = FixedClock(now)
    return JobProcessor(
        repository=repository,
        metadata_reader=FakeMetadataReader(library_root, media_path),
        provider=provider,
        sidecar_writer=AtomicLrcWriter(),
        metrics=NullMetrics(),
        clock=clock,
        settings=_build_settings(library_root, library_root / ".state"),
    ), clock


@pytest.mark.asyncio
async def test_job_processor_repairs_provenance_after_partial_commit(sqlite_engine: Engine, tmp_path: Path) -> None:
    library_root = tmp_path / "music"
    library_root.mkdir()
    media_path = library_root / "track.flac"
    media_path.write_bytes(b"audio")

    repository = FailingProvenanceRepository(sqlite_engine)
    provider = FakeProvider("Hello\nWorld")
    await _enqueue_job(repository, media_path, library_root)
    processor, clock = _build_processor(repository, library_root, media_path, provider, now=datetime.now(UTC) + timedelta(seconds=1))

    first_attempt = await processor.process_next("worker-1")
    assert first_attempt is True
    assert media_path.with_suffix(".lrc").read_text(encoding="utf-8") == "Hello\nWorld"
    assert await repository.get_provenance(media_path) is None

    clock.advance(6)
    second_attempt = await processor.process_next("worker-1")
    repaired = await repository.get_provenance(media_path)

    assert second_attempt is True
    assert repaired is not None
    assert repaired.normalized_lyrics_hash == await AtomicLrcWriter().read_normalized_hash(media_path.with_suffix(".lrc"))
    assert provider.fetch_count == 2


@pytest.mark.asyncio
async def test_job_processor_preserves_manual_sidecar_when_retry_sidecar_no_longer_matches_provider(sqlite_engine: Engine, tmp_path: Path) -> None:
    library_root = tmp_path / "music"
    library_root.mkdir()
    media_path = library_root / "track.flac"
    media_path.write_bytes(b"audio")

    repository = FailingProvenanceRepository(sqlite_engine)
    provider = FakeProvider("Hello\nWorld")
    await _enqueue_job(repository, media_path, library_root)
    processor, clock = _build_processor(repository, library_root, media_path, provider, now=datetime.now(UTC) + timedelta(seconds=1))

    first_attempt = await processor.process_next("worker-1")
    assert first_attempt is True

    sidecar_path = media_path.with_suffix(".lrc")
    sidecar_path.write_text("Manual replacement", encoding="utf-8")

    clock.advance(6)
    second_attempt = await processor.process_next("worker-1")
    repaired = await repository.get_provenance(media_path)

    assert second_attempt is True
    assert sidecar_path.read_text(encoding="utf-8") == "Manual replacement"
    assert repaired is None


@pytest.mark.asyncio
async def test_job_processor_renews_lease_during_long_running_work(sqlite_engine: Engine, tmp_path: Path) -> None:
    library_root = tmp_path / "music"
    library_root.mkdir()
    media_path = library_root / "track.flac"
    media_path.write_bytes(b"audio")

    repository = FailingProvenanceRepository(sqlite_engine)
    repository.fail_record_provenance = False
    provider = FakeProvider("Hello\nWorld", delay_seconds=31)

    await _enqueue_job(repository, media_path, library_root)
    processor, _ = _build_processor(repository, library_root, media_path, provider, now=datetime.now(UTC))

    processed = await processor.process_next("worker-1")

    assert processed is True
    assert repository.heartbeat_calls >= 1
