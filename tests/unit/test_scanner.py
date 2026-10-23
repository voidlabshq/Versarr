from __future__ import annotations

from pathlib import Path

import pytest

from versarr.infrastructure.filesystem import FilesystemScanner, resolve_candidate_media_path


@pytest.mark.asyncio
async def test_scanner_finds_supported_media_recursively_and_ignores_the_rest(tmp_path: Path) -> None:
    (tmp_path / "Artist" / "Album").mkdir(parents=True)
    wanted = [
        tmp_path / "a.flac",
        tmp_path / "Artist" / "b.MP3",
        tmp_path / "Artist" / "Album" / "c.opus",
    ]
    for path in wanted:
        path.write_bytes(b"x")
    for name in ("cover.jpg", "notes.txt", "a.lrc", "d.flac.part"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "folder.flac").mkdir()

    found = await FilesystemScanner().scan(tmp_path)

    assert sorted(found) == sorted(wanted)


def test_resolve_candidate_maps_media_and_sidecar_events_to_the_media_file(tmp_path: Path) -> None:
    media = tmp_path / "song.flac"
    media.write_bytes(b"x")

    assert resolve_candidate_media_path(media) == media
    assert resolve_candidate_media_path(tmp_path / "song.lrc") == media
    assert resolve_candidate_media_path(tmp_path / "other.lrc") is None
    assert resolve_candidate_media_path(tmp_path / "cover.jpg") is None
