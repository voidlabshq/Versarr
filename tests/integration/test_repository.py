from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.domain import (
    ControlRequest,
    ControlRequestType,
    LyricsPresence,
    TrackIdentity,
    TrackSnapshot,
    TriggerKind,
    hash_meaningful_snapshot,
)
from versarr.infrastructure.persistence import SqliteStateRepository


@pytest.mark.asyncio
async def test_repository_enqueues_and_leases_job(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    media_path = Path("/music/track.flac")

    await repository.enqueue_path(
        library_root=Path("/music"),
        media_path=media_path,
        trigger=TriggerKind.WATCHER,
        priority="watcher",
        event_kind="created",
    )

    leased = await repository.lease_next_ready_job("worker-1", datetime.now(UTC))

    assert leased is not None
    assert leased.media_path == media_path


@pytest.mark.asyncio
async def test_repository_records_snapshot_and_control_request(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    identity = TrackIdentity(
        title="Track",
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
        media_path=Path("/music/track.flac"),
        extension=".flac",
        file_size=1024,
        file_mtime_ns=1,
        identity=identity,
        lyrics_presence=LyricsPresence(False, None, False),
        meaningful_state_hash="",
    )
    snapshot = TrackSnapshot(
        library_root=snapshot.library_root,
        media_path=snapshot.media_path,
        extension=snapshot.extension,
        file_size=snapshot.file_size,
        file_mtime_ns=snapshot.file_mtime_ns,
        identity=snapshot.identity,
        lyrics_presence=snapshot.lyrics_presence,
        meaningful_state_hash=hash_meaningful_snapshot(snapshot),
    )

    await repository.record_snapshot(snapshot)
    stored = await repository.get_snapshot(snapshot.media_path)
    await repository.enqueue_control_request(
        ControlRequest(
            request_type=ControlRequestType.RESCAN_PATH,
            target_root=Path("/music"),
            target_path=snapshot.media_path,
            force=False,
            overwrite_existing=False,
            allow_manual_overwrite=False,
        )
    )
    requests = await repository.poll_control_requests()

    assert stored is not None
    assert stored.meaningful_state_hash == snapshot.meaningful_state_hash
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_repository_requeues_dirty_job_on_completion(sqlite_engine: Engine) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    media_path = Path("/music/track.flac")

    await repository.enqueue_path(
        library_root=Path("/music"),
        media_path=media_path,
        trigger=TriggerKind.WATCHER,
        priority="watcher",
        event_kind="created",
    )
    leased = await repository.lease_next_ready_job("worker-1", datetime.now(UTC))
    assert leased is not None

    await repository.enqueue_path(
        library_root=Path("/music"),
        media_path=media_path,
        trigger=TriggerKind.WATCHER,
        priority="watcher",
        event_kind="modified",
    )
    await repository.complete_job(leased.job_key, "done")

    follow_up = await repository.lease_next_ready_job("worker-2", datetime.now(UTC))
    assert follow_up is not None
    assert follow_up.attempt_count == 1
