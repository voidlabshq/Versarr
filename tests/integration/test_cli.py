from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from versarr.cli import app
from versarr.domain import LyricsPresence, TrackIdentity, TrackSnapshot
from versarr.infrastructure.persistence import SqliteStateRepository, create_engine, run_migrations

runner = CliRunner()


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    library = tmp_path / "music"
    state = tmp_path / "state"
    library.mkdir()
    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", f'["{library}"]')
    monkeypatch.setenv("VERSARR_STATE_DIR", str(state))
    monkeypatch.setenv("VERSARR_SQLITE_PATH", str(state / "versarr.db"))
    return library, state


def _snapshot(library: Path, relative: str, *, lyrics: bool) -> TrackSnapshot:
    media_path = library / relative
    sidecar_path = media_path.with_suffix(".lrc")
    return TrackSnapshot(
        library_root=library,
        media_path=media_path,
        extension=".flac",
        file_size=1,
        file_mtime_ns=1,
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
            sidecar_exists=lyrics,
            sidecar_path=sidecar_path if lyrics else None,
            embedded_exists=False,
        ),
        meaningful_state_hash="h",
    )


def test_config_check_reports_valid_configuration(deployment: tuple[Path, Path]) -> None:
    result = runner.invoke(app, ["config-check"])

    assert result.exit_code == 0
    assert "Configuration valid for 1 library root(s)." in result.output


def test_config_check_fails_for_missing_library_root(deployment: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", '["/definitely/not/here"]')

    result = runner.invoke(app, ["config-check"])

    assert result.exit_code != 0


def test_lyrics_gaps_with_empty_state(deployment: tuple[Path, Path]) -> None:
    result = runner.invoke(app, ["lyrics-gaps"])

    assert result.exit_code == 0
    assert "No lyric gaps found" in result.output


def test_lyrics_gaps_lists_only_directories_with_gaps_unless_all(deployment: tuple[Path, Path]) -> None:
    library, state = deployment
    state.mkdir(exist_ok=True)
    run_migrations(state / "versarr.db")
    engine = create_engine(state / "versarr.db")
    repository = SqliteStateRepository(engine)

    async def seed() -> None:
        await repository.record_snapshot(_snapshot(library, "Complete/01.flac", lyrics=True))
        await repository.record_snapshot(_snapshot(library, "Gappy/01.flac", lyrics=False))
        await repository.record_snapshot(replace(_snapshot(library, "Gappy/02.flac", lyrics=True)))

    asyncio.run(seed())
    engine.dispose()

    gaps = runner.invoke(app, ["lyrics-gaps"])
    everything = runner.invoke(app, ["lyrics-gaps", "--all"])

    assert gaps.exit_code == 0
    assert "Directories: 1 | Tracks with lyrics: 1/2 | Missing: 1" in gaps.output
    assert "Gappy (1/2)" in gaps.output
    assert "Complete" not in gaps.output
    assert "Directories: 2" in everything.output
    assert "Complete (1/1)" in everything.output


def test_request_rescan_records_a_control_request(deployment: tuple[Path, Path]) -> None:
    library, state = deployment
    track = library / "song.flac"
    track.write_bytes(b"x")

    result = runner.invoke(app, ["request-rescan", str(track), "--root", str(library)])

    assert result.exit_code == 0
    engine = create_engine(state / "versarr.db")
    try:
        pending = asyncio.run(SqliteStateRepository(engine).count_pending_control_requests())
    finally:
        engine.dispose()
    assert pending == 1
