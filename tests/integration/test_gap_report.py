from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.application.services import IngestionService, ReconciliationService, SystemClock
from versarr.domain import (
    LyricsPresence,
    ScanKind,
    TrackIdentity,
    TrackSnapshot,
    TriggerKind,
    hash_meaningful_snapshot,
)
from versarr.infrastructure.filesystem.scanner import FilesystemScanner
from versarr.infrastructure.persistence import SqliteStateRepository
from versarr.observability import MetricsFacade


def _build_snapshot(
    media_path: Path,
    *,
    sidecar_exists: bool,
    embedded_exists: bool = False,
) -> TrackSnapshot:
    identity = TrackIdentity(
        title=media_path.stem,
        artist="Artist",
        album="Album",
        album_artist=None,
        track_number=1,
        disc_number=1,
        duration_seconds=180,
        release_year=2024,
    )
    snapshot = TrackSnapshot(
        library_root=Path("/music"),
        media_path=media_path,
        extension=".flac",
        file_size=1024,
        file_mtime_ns=1,
        identity=identity,
        lyrics_presence=LyricsPresence(
            sidecar_exists=sidecar_exists,
            sidecar_path=media_path.with_suffix(".lrc") if sidecar_exists else None,
            embedded_exists=embedded_exists,
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


@pytest.mark.asyncio
async def test_repository_lists_directory_gap_summaries(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    complete_track = _build_snapshot(Path("/music/Album A/01 - Ready.flac"), sidecar_exists=True)
    missing_track = _build_snapshot(Path("/music/Album A/02 - Missing.flac"), sidecar_exists=False)
    failed_track = _build_snapshot(Path("/music/Album B/01 - Failed.flac"), sidecar_exists=False)

    await repository.record_snapshot(complete_track)
    await repository.record_snapshot(missing_track)
    await repository.record_snapshot(failed_track)

    await repository.record_cooldown(
        missing_track.identity.normalized_lookup_key,
        "lrclib",
        "not_found",
        datetime.now(UTC) + timedelta(hours=1),
    )
    await repository.enqueue_path(
        library_root=Path("/music"),
        media_path=failed_track.media_path,
        trigger="manual_rescan",
        priority="manual",
        event_kind="manual",
    )
    leased = await repository.lease_next_ready_job("worker-1", datetime.now(UTC))
    assert leased is not None
    await repository.fail_job(leased.job_key, "lyrics_not_found", "terminal")

    summaries = await repository.list_directory_gap_summaries()

    assert len(summaries) == 2
    first, second = summaries
    assert first.directory_path == Path("/music/Album A")
    assert first.tracks_with_lyrics == 1
    assert first.tracks_missing_lyrics == 1
    assert first.active_cooldowns == 1
    assert second.directory_path == Path("/music/Album B")
    assert second.tracks_missing_lyrics == 1
    assert second.failed_jobs == 1


@pytest.mark.asyncio
async def test_missing_snapshots_are_excluded_from_gap_report_until_seen_again(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    kept = _build_snapshot(Path("/music/Kept/01 - Kept.flac"), sidecar_exists=True)
    removed = _build_snapshot(Path("/music/Removed/01 - Gone.flac"), sidecar_exists=False)
    await repository.record_snapshot(kept)
    await repository.record_snapshot(removed)

    count = await repository.mark_missing_snapshots_deleted(Path("/music"), [kept.media_path], datetime.now(UTC))

    assert count == 1
    summaries = await repository.list_directory_gap_summaries()
    assert [summary.directory_path for summary in summaries] == [Path("/music/Kept")]
    stored = await repository.get_snapshot(removed.media_path)
    assert stored is not None
    assert stored.deleted_at is not None

    assert await repository.mark_missing_snapshots_deleted(Path("/music"), [kept.media_path], datetime.now(UTC)) == 0

    await repository.record_snapshot(removed)
    summaries = await repository.list_directory_gap_summaries()
    assert [summary.directory_path for summary in summaries] == [Path("/music/Kept"), Path("/music/Removed")]


@pytest.mark.asyncio
async def test_mark_missing_snapshots_deleted_is_scoped_to_library_root(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    track = _build_snapshot(Path("/music/Album/01 - Track.flac"), sidecar_exists=True)
    await repository.record_snapshot(track)

    count = await repository.mark_missing_snapshots_deleted(Path("/other"), [], datetime.now(UTC))

    assert count == 0
    assert len(await repository.list_directory_gap_summaries()) == 1


@pytest.fixture(scope="module")
def metrics() -> MetricsFacade:
    return MetricsFacade()


def _reconciliation(repository: SqliteStateRepository, metrics: MetricsFacade) -> ReconciliationService:
    return ReconciliationService(
        repository=repository,
        scanner=FilesystemScanner(),
        ingestion=IngestionService(repository=repository, metrics=metrics),
        clock=SystemClock(),
        metrics=metrics,
    )


@pytest.mark.asyncio
async def test_scan_root_removes_deleted_directories_from_gap_report(sqlite_engine: Engine, tmp_path: Path, metrics: MetricsFacade) -> None:
    root = tmp_path / "music"
    (root / "New").mkdir(parents=True)
    new_track = root / "New" / "01 - New.flac"
    new_track.write_bytes(b"x")
    repository = SqliteStateRepository(sqlite_engine)
    old_track = _build_snapshot(root / "Old" / "01 - Old.flac", sidecar_exists=False)
    await repository.record_snapshot(replace(old_track, library_root=root))
    await repository.record_snapshot(replace(_build_snapshot(new_track, sidecar_exists=False), library_root=root))

    await _reconciliation(repository, metrics).scan_root(root, ScanKind.RECONCILIATION, TriggerKind.MANUAL_RESCAN)

    summaries = await repository.list_directory_gap_summaries()
    assert [summary.directory_path for summary in summaries] == [root / "New"]


@pytest.mark.asyncio
async def test_scan_root_keeps_state_when_root_is_missing(sqlite_engine: Engine, tmp_path: Path, metrics: MetricsFacade) -> None:
    root = tmp_path / "unmounted"
    repository = SqliteStateRepository(sqlite_engine)
    track = _build_snapshot(root / "Album" / "01 - Track.flac", sidecar_exists=True)
    await repository.record_snapshot(replace(track, library_root=root))

    await _reconciliation(repository, metrics).scan_root(root, ScanKind.RECONCILIATION, TriggerKind.MANUAL_RESCAN)

    assert len(await repository.list_directory_gap_summaries()) == 1
