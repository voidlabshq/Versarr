from __future__ import annotations

from pathlib import Path

from versarr.domain import LyricsPresence, TrackIdentity, TrackSnapshot, hash_meaningful_snapshot


def test_meaningful_snapshot_hash_ignores_raw_file_mtime_noise() -> None:
    identity = TrackIdentity(
        title="Song",
        artist="Artist",
        album="Album",
        album_artist=None,
        track_number=1,
        disc_number=1,
        duration_seconds=180,
        release_year=2020,
    )
    snapshot_a = TrackSnapshot(
        library_root=Path("/music"),
        media_path=Path("/music/song.flac"),
        extension=".flac",
        file_size=123,
        file_mtime_ns=1,
        identity=identity,
        lyrics_presence=LyricsPresence(False, None, False),
        meaningful_state_hash="",
    )
    snapshot_b = TrackSnapshot(
        library_root=Path("/music"),
        media_path=Path("/music/song.flac"),
        extension=".flac",
        file_size=123,
        file_mtime_ns=999,
        identity=identity,
        lyrics_presence=LyricsPresence(False, None, False),
        meaningful_state_hash="",
    )
    assert hash_meaningful_snapshot(snapshot_a) == hash_meaningful_snapshot(snapshot_b)

