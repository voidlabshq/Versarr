from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from versarr.application.contracts import SidecarWriter, SidecarWriteResult
from versarr.domain import hash_normalized_lyrics, normalize_lyrics_text
from versarr.observability import get_logger


class AtomicLrcWriter(SidecarWriter):
    def __init__(self) -> None:
        self._logger = get_logger("sidecar_writer")

    async def write(self, sidecar_path: Path, normalized_text: str) -> SidecarWriteResult:
        return await asyncio.to_thread(self._write_sync, sidecar_path, normalized_text)

    async def read_normalized_hash(self, sidecar_path: Path) -> str:
        return await asyncio.to_thread(self._read_normalized_hash_sync, sidecar_path)

    def _write_sync(self, sidecar_path: Path, normalized_text: str) -> SidecarWriteResult:
        if sidecar_path.suffix.lower() != ".lrc":
            msg = "sidecar path must use .lrc suffix"
            raise ValueError(msg)
        parent = sidecar_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if sidecar_path.exists() and sidecar_path.is_symlink():
            msg = "symlink sidecars are not allowed"
            raise ValueError(msg)
        temp_path = parent / f".{sidecar_path.name}.tmp.{os.getpid()}.{uuid4().hex}"
        payload = normalize_lyrics_text(normalized_text).encode("utf-8")
        with temp_path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        verify_bytes = temp_path.read_bytes()
        if verify_bytes != payload:
            temp_path.unlink(missing_ok=True)
            msg = "temp sidecar verification failed"
            raise OSError(msg)
        existed = sidecar_path.exists()
        os.replace(temp_path, sidecar_path)
        final_bytes = sidecar_path.read_bytes()
        if final_bytes != payload:
            msg = "final sidecar verification failed"
            raise OSError(msg)
        digest = hash_normalized_lyrics(payload.decode("utf-8"))
        self._logger.info(
            "sidecar_write_completed",
            sidecar_path=str(sidecar_path),
            bytes_written=len(payload),
            created=not existed,
            replaced=existed,
        )
        return SidecarWriteResult(
            sidecar_path=sidecar_path,
            normalized_hash=digest,
            created=not existed,
            replaced=existed,
        )

    def _read_normalized_hash_sync(self, sidecar_path: Path) -> str:
        return hash_normalized_lyrics(sidecar_path.read_text(encoding="utf-8"))
