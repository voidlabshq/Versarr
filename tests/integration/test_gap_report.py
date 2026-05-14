from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.domain import LyricsPresence, TrackIdentity, TrackSnapshot, hash_meaningful_snapshot
from versarr.infrastructure.persistence import SqliteStateRepository


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
