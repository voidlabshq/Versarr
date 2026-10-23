from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from versarr.infrastructure.filesystem import MutagenMetadataReader


@pytest.mark.asyncio
async def test_reads_vorbis_comments_from_flac(tmp_path: Path, make_flac: Callable[..., Path]) -> None:
    media = make_flac(tmp_path / "song.flac", title="Halo", artist="Beyonce", album="I Am", tracknumber="3/12", discnumber="1", date="2008-11-14")

    snapshot = await MutagenMetadataReader().read_snapshot(media, tmp_path)

    identity = snapshot.identity
    assert (identity.title, identity.artist, identity.album) == ("Halo", "Beyonce", "I Am")
    assert (identity.track_number, identity.disc_number, identity.release_year) == (3, 1, 2008)
    assert identity.duration_seconds == 10
    assert snapshot.extension == ".flac"
    assert not snapshot.lyrics_presence.embedded_exists
    assert not snapshot.lyrics_presence.sidecar_exists


@pytest.mark.asyncio
async def test_reads_id3_frames_from_mp3(tmp_path: Path, make_mp3: Callable[..., Path]) -> None:
    media = make_mp3(tmp_path / "song.mp3", title="Halo", artist="Beyonce", album="I Am", track="2/9")

    snapshot = await MutagenMetadataReader().read_snapshot(media, tmp_path)

    assert (snapshot.identity.title, snapshot.identity.artist, snapshot.identity.album) == ("Halo", "Beyonce", "I Am")
    assert snapshot.identity.track_number == 2


@pytest.mark.asyncio
async def test_missing_tags_fall_back_to_placeholders(tmp_path: Path, make_flac: Callable[..., Path]) -> None:
    media = make_flac(tmp_path / "untagged.flac")

    snapshot = await MutagenMetadataReader().read_snapshot(media, tmp_path)

    assert snapshot.identity.title == "Unknown Title"
    assert snapshot.identity.artist == "Unknown Artist"


@pytest.mark.asyncio
async def test_detects_embedded_lyrics_in_flac_and_mp3(tmp_path: Path, make_flac: Callable[..., Path], make_mp3: Callable[..., Path]) -> None:
    flac = make_flac(tmp_path / "a.flac", title="A", artist="B", lyrics="la la")
    mp3 = make_mp3(tmp_path / "b.mp3", title="A", artist="B", lyrics="la la")
    reader = MutagenMetadataReader()

    assert (await reader.read_snapshot(flac, tmp_path)).lyrics_presence.embedded_exists
    assert (await reader.read_snapshot(mp3, tmp_path)).lyrics_presence.embedded_exists


@pytest.mark.asyncio
async def test_detects_sidecar(tmp_path: Path, make_flac: Callable[..., Path]) -> None:
    media = make_flac(tmp_path / "song.flac", title="A", artist="B")
    media.with_suffix(".lrc").write_text("[00:01.00]hi", encoding="utf-8")

    snapshot = await MutagenMetadataReader().read_snapshot(media, tmp_path)

    assert snapshot.lyrics_presence.sidecar_exists
    assert snapshot.lyrics_presence.sidecar_path == media.with_suffix(".lrc")


@pytest.mark.asyncio
async def test_meaningful_hash_ignores_mtime_but_tracks_sidecar_presence(tmp_path: Path, make_flac: Callable[..., Path]) -> None:
    media = make_flac(tmp_path / "song.flac", title="A", artist="B")
    reader = MutagenMetadataReader()
    before = await reader.read_snapshot(media, tmp_path)

    media.touch()
    unchanged = await reader.read_snapshot(media, tmp_path)
    media.with_suffix(".lrc").write_text("x", encoding="utf-8")
    with_sidecar = await reader.read_snapshot(media, tmp_path)

    assert before.meaningful_state_hash == unchanged.meaningful_state_hash
    assert before.meaningful_state_hash != with_sidecar.meaningful_state_hash


@pytest.mark.asyncio
async def test_unsupported_and_corrupt_files_raise_value_error(tmp_path: Path) -> None:
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("x", encoding="utf-8")
    corrupt = tmp_path / "broken.flac"
    corrupt.write_bytes(b"not audio at all")
    reader = MutagenMetadataReader()

    with pytest.raises(ValueError, match="unsupported"):
        await reader.read_snapshot(unsupported, tmp_path)
    with pytest.raises(ValueError, match="unable to parse"):
        await reader.read_snapshot(corrupt, tmp_path)


@pytest.mark.parametrize(
    ("date", "year"),
    [("2008", 2008), ("2008-11-14", 2008), ("2008-11", 2008), ("2008/11/14", 2008), ("2008-11-14T00:00:00", 2008), ("unknown", None)],
)
@pytest.mark.asyncio
async def test_release_year_is_the_year_of_any_date_format(tmp_path: Path, make_flac: Callable[..., Path], date: str, year: int | None) -> None:
    media = make_flac(tmp_path / "song.flac", title="A", artist="B", date=date)

    snapshot = await MutagenMetadataReader().read_snapshot(media, tmp_path)

    assert snapshot.identity.release_year == year
