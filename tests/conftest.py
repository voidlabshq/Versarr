from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.infrastructure.persistence import create_engine, metadata


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(tmp_path / "state.db")
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def make_flac() -> Callable[..., Path]:
    """Build a minimal valid FLAC (STREAMINFO only) with Vorbis comments."""
    from mutagen.flac import FLAC

    def build(path: Path, **tags: str) -> Path:
        packed = (44100 << 44) | (1 << 41) | (15 << 36) | 441000
        streaminfo = struct.pack(">HH", 4096, 4096) + b"\0" * 6 + packed.to_bytes(8, "big") + b"\0" * 16
        path.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo)
        audio = FLAC(path)
        audio.add_tags()
        for key, value in tags.items():
            audio[key] = value
        audio.save()
        return path

    return build


@pytest.fixture
def make_mp3() -> Callable[..., Path]:
    """Build a tiny valid MP3 with ID3 frames."""
    from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK, USLT
    from mutagen.mp3 import MP3

    def build(
        path: Path,
        *,
        title: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        track: str | None = None,
        lyrics: str | None = None,
    ) -> Path:
        path.write_bytes((b"\xff\xfb\x90\x00" + b"\0" * 413) * 40)
        audio = MP3(path)
        audio.add_tags()
        tags: ID3 = audio.tags  # type: ignore[assignment]
        if title:
            tags.add(TIT2(encoding=3, text=title))
        if artist:
            tags.add(TPE1(encoding=3, text=artist))
        if album:
            tags.add(TALB(encoding=3, text=album))
        if track:
            tags.add(TRCK(encoding=3, text=track))
        if lyrics:
            tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
        audio.save()
        return path

    return build
