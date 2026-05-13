from __future__ import annotations

import asyncio
from pathlib import Path

from versarr.application.contracts import LibraryScanner

SUPPORTED_MEDIA_EXTENSIONS = {".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".opus"}


def resolve_candidate_media_path(candidate_path: Path) -> Path | None:
    if candidate_path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS:
        return candidate_path
    if candidate_path.suffix.lower() != ".lrc":
        return None
    for extension in SUPPORTED_MEDIA_EXTENSIONS:
        sibling = candidate_path.with_suffix(extension)
        if sibling.exists():
            return sibling
    return None


class FilesystemScanner(LibraryScanner):
    async def scan(self, root: Path) -> list[Path]:
        return await asyncio.to_thread(self._scan_sync, root)

    def _scan_sync(self, root: Path) -> list[Path]:
        candidates: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS:
                candidates.append(path)
        return candidates

