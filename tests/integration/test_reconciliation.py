from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import Engine

from versarr.application.services import IngestionService, ReconciliationService
from versarr.domain import LyricsPresence, ScanKind, TrackIdentity, TrackSnapshot, TriggerKind
from versarr.infrastructure.filesystem.scanner import FilesystemScanner
from versarr.infrastructure.persistence import SqliteStateRepository

_REVISIT_SECONDS = 3600


class _Clock:
    def __init__(self) -> None:
        self.current = datetime.now(UTC)

    def now(self) -> datetime:
        return self.current


def _service(repository: SqliteStateRepository, clock: _Clock) -> ReconciliationService:
    metrics = MagicMock()
    return ReconciliationService(
        repository=repository,
        scanner=FilesystemScanner(),
        ingestion=IngestionService(repository=repository, metrics=metrics),
        clock=clock,
        metrics=metrics,
        revisit_after_seconds=_REVISIT_SECONDS,
    )


async def _scan(service: ReconciliationService, root: Path, *, evaluate_all: bool = False) -> int:
    return await service.scan_root(root, ScanKind.RECONCILIATION, TriggerKind.RECONCILIATION, evaluate_all=evaluate_all)


async def _evaluate(repository: SqliteStateRepository, root: Path, media_path: Path, *, with_lyrics: bool = False) -> None:
    """Stand-in for the job processor: record the snapshot and finish the job."""
    if with_lyrics:
        media_path.with_suffix(".lrc").write_text("[00:01.00]hi", encoding="utf-8")
    stat = media_path.stat()
    sidecar_exists = media_path.with_suffix(".lrc").is_file()
    await repository.record_snapshot(
        TrackSnapshot(
            library_root=root,
            media_path=media_path,
            extension=media_path.suffix,
            file_size=stat.st_size,
            file_mtime_ns=stat.st_mtime_ns,
            identity=TrackIdentity(
                title=media_path.stem,
                artist="Artist",
                album=None,
                album_artist=None,
                track_number=None,
                disc_number=None,
                duration_seconds=100,
                release_year=None,
            ),
            lyrics_presence=LyricsPresence(
                sidecar_exists=sidecar_exists,
                sidecar_path=media_path.with_suffix(".lrc") if sidecar_exists else None,
                embedded_exists=False,
            ),
            meaningful_state_hash="h",
        )
    )
    leased = await repository.lease_next_ready_job("worker", datetime.now(UTC) + timedelta(seconds=5))
    assert leased is not None
    await repository.complete_job(leased.job_key, "done")


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    (root / "Album").mkdir(parents=True)
    for name in ("a.flac", "b.flac"):
        (root / "Album" / name).write_bytes(b"audio")
    return root


@pytest_asyncio.fixture
async def evaluated_library(sqlite_engine: Engine, library: Path) -> tuple[SqliteStateRepository, ReconciliationService, _Clock, Path]:
    repository = SqliteStateRepository(sqlite_engine)
    clock = _Clock()
    service = _service(repository, clock)
    assert await _scan(service, library) == 2
    for name in ("a.flac", "b.flac"):
        await _evaluate(repository, library, library / "Album" / name, with_lyrics=name == "a.flac")
    return repository, service, clock, library


@pytest.mark.asyncio
async def test_unchanged_library_enqueues_nothing(evaluated_library: tuple[SqliteStateRepository, ReconciliationService, _Clock, Path]) -> None:
    _, service, _, library = evaluated_library

    assert await _scan(service, library) == 0


@pytest.mark.asyncio
async def test_changed_file_is_enqueued(evaluated_library: tuple[SqliteStateRepository, ReconciliationService, _Clock, Path]) -> None:
    _, service, _, library = evaluated_library
    changed = library / "Album" / "a.flac"
    os.utime(changed, ns=(1, changed.stat().st_mtime_ns + 5_000_000_000))

    assert await _scan(service, library) == 1


@pytest.mark.asyncio
async def test_sidecar_appearing_or_disappearing_is_enqueued(
    evaluated_library: tuple[SqliteStateRepository, ReconciliationService, _Clock, Path],
) -> None:
    _, service, _, library = evaluated_library
    (library / "Album" / "b.lrc").write_text("[00:01.00]new", encoding="utf-8")
    (library / "Album" / "a.lrc").unlink()

    assert await _scan(service, library) == 2


@pytest.mark.asyncio
async def test_lyricless_file_is_revisited_only_after_the_interval(
    evaluated_library: tuple[SqliteStateRepository, ReconciliationService, _Clock, Path],
) -> None:
    _, service, clock, library = evaluated_library
    clock.current += timedelta(seconds=_REVISIT_SECONDS // 2)
    assert await _scan(service, library) == 0

    clock.current += timedelta(seconds=_REVISIT_SECONDS)

    assert await _scan(service, library) == 1


@pytest.mark.asyncio
async def test_evaluate_all_ignores_what_is_already_known(
    evaluated_library: tuple[SqliteStateRepository, ReconciliationService, _Clock, Path],
) -> None:
    _, service, _, library = evaluated_library

    assert await _scan(service, library, evaluate_all=True) == 2


@pytest.mark.asyncio
async def test_already_queued_job_is_not_reset(sqlite_engine: Engine, library: Path) -> None:
    repository = SqliteStateRepository(sqlite_engine)
    service = _service(repository, _Clock())
    assert await _scan(service, library) == 2
    await _evaluate(repository, library, library / "Album" / "a.flac")
    await _evaluate(repository, library, library / "Album" / "b.flac")
    await repository.enqueue_path(
        library_root=library,
        media_path=library / "Album" / "a.flac",
        trigger="manual_rescan",
        priority="manual",
        event_kind="manual",
    )

    assert await _scan(service, library) == 0
