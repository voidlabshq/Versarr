from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from versarr.application.contracts import MetadataReader
from versarr.domain import LyricsPresence, TrackIdentity, TrackSnapshot, hash_meaningful_snapshot

from .scanner import SUPPORTED_MEDIA_EXTENSIONS


class MutagenMetadataReader(MetadataReader):
    async def read_snapshot(self, media_path: Path, library_root: Path) -> TrackSnapshot:
        return await asyncio.to_thread(self._read_snapshot_sync, media_path, library_root)

    def _read_snapshot_sync(self, media_path: Path, library_root: Path) -> TrackSnapshot:
        if media_path.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS:
            msg = f"unsupported media format: {media_path.suffix}"
            raise ValueError(msg)
        stat = media_path.stat()
        audio = mutagen.File(media_path)
        if audio is None:
            msg = f"unable to parse metadata for {media_path}"
            raise ValueError(msg)
        identity = _build_identity(audio)
        sidecar_path = media_path.with_suffix(".lrc")
        sidecar_exists = sidecar_path.is_file()
        embedded_exists = _detect_embedded_lyrics(audio)
        lyrics_presence = LyricsPresence(
            sidecar_exists=sidecar_exists,
            sidecar_path=sidecar_path if sidecar_exists else None,
            embedded_exists=embedded_exists,
        )
        snapshot = TrackSnapshot(
            library_root=library_root,
            media_path=media_path,
            extension=media_path.suffix.lower(),
            file_size=stat.st_size,
            file_mtime_ns=stat.st_mtime_ns,
            identity=identity,
            lyrics_presence=lyrics_presence,
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


def _build_identity(audio: Any) -> TrackIdentity:
    tags = getattr(audio, "tags", {}) or {}
    title = _first_tag(tags, ["title", "TIT2", "\xa9nam"]) or "Unknown Title"
    artist = _first_tag(tags, ["artist", "TPE1", "\xa9ART"]) or "Unknown Artist"
    album = _first_tag(tags, ["album", "TALB", "\xa9alb"])
    album_artist = _first_tag(tags, ["albumartist", "TPE2", "aART"])
    track_number = _parse_int(_first_tag(tags, ["tracknumber", "TRCK"]))
    disc_number = _parse_int(_first_tag(tags, ["discnumber", "TPOS"]))
    release_year = _parse_int(_first_tag(tags, ["date", "TDRC", "\xa9day"]))
    isrc = _first_tag(tags, ["isrc", "TSRC"])
    duration = int(getattr(getattr(audio, "info", None), "length", 0) or 0) or None
    return TrackIdentity(
        title=title,
        artist=artist,
        album=album,
        album_artist=album_artist,
        track_number=track_number,
        disc_number=disc_number,
        duration_seconds=duration,
        release_year=release_year,
        musicbrainz_ids=tuple(
            filter(
                None,
                [
                    _first_tag(tags, ["musicbrainz_trackid"]),
                    _first_tag(tags, ["musicbrainz_recordingid"]),
                ],
            )
        ),
        isrc=isrc,
    )


def _first_tag(tags: Any, keys: list[str]) -> str | None:
    for key in keys:
        if hasattr(tags, "get"):
            value = tags.get(key)
            if value:
                return _coerce_tag_value(value)
        if hasattr(tags, "getall") and key in {"TIT2", "TPE1", "TALB", "TPE2", "TRCK", "TPOS", "TDRC", "TSRC"}:
            frames = tags.getall(key)
            if frames:
                return _coerce_tag_value(frames[0])
    return None


def _coerce_tag_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return _coerce_tag_value(value[0]) if value else None
    if isinstance(value, tuple):
        return _coerce_tag_value(value[0]) if value else None
    if hasattr(value, "text"):
        text = getattr(value, "text")
        return _coerce_tag_value(text)
    if hasattr(value, "value"):
        return _coerce_tag_value(getattr(value, "value"))
    return str(value).strip() or None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.split("/", maxsplit=1)[0]
    digits = "".join(character for character in raw if character.isdigit())
    return int(digits) if digits else None


def _detect_embedded_lyrics(audio: Any) -> bool:
    if isinstance(audio, MP4):
        return bool(getattr(audio, "tags", {}).get("\xa9lyr"))
    if isinstance(audio, FLAC | OggVorbis | OggOpus):
        tags = getattr(audio, "tags", {}) or {}
        return bool(tags.get("LYRICS") or tags.get("lyrics") or tags.get("UNSYNCEDLYRICS"))
    if hasattr(audio, "tags") and isinstance(audio.tags, ID3):
        return bool(audio.tags.getall("USLT"))
    return False

