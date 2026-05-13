from __future__ import annotations

from hashlib import sha256

from .entities import TrackSnapshot
from .normalization import normalize_lyrics_text


def hash_normalized_lyrics(value: str) -> str:
    normalized = normalize_lyrics_text(value)
    return sha256(normalized.encode("utf-8")).hexdigest()


def hash_meaningful_snapshot(snapshot: TrackSnapshot) -> str:
    payload = "|".join(
        [
            str(snapshot.library_root),
            str(snapshot.media_path),
            snapshot.extension,
            snapshot.identity.normalized_lookup_key,
            str(snapshot.identity.duration_seconds or ""),
            "1" if snapshot.lyrics_presence.sidecar_exists else "0",
            "1" if snapshot.lyrics_presence.embedded_exists else "0",
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()

