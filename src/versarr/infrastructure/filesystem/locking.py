from __future__ import annotations

import asyncio
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from versarr.application.contracts import LockHandle, LockManager


class FileLockManager(LockManager):
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._file_handle: IO[str] | None = None
        self._holder_metadata = json.dumps(
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "started_at": datetime.now(UTC).isoformat(),
            }
        )

    async def acquire(self) -> LockHandle:
        return await asyncio.to_thread(self._acquire_sync)

    async def release(self) -> None:
        await asyncio.to_thread(self._release_sync)

    def _acquire_sync(self) -> LockHandle:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+", encoding="utf-8")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = __import__("fcntl")

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            holder = self._read_holder_metadata()
            handle.close()
            msg = f"lock already held: {holder}"
            raise RuntimeError(msg) from error
        handle.seek(0)
        handle.truncate()
        handle.write(self._holder_metadata)
        handle.flush()
        self._file_handle = handle
        return LockHandle(path=self._lock_path, holder_metadata=self._holder_metadata)

    def _release_sync(self) -> None:
        if self._file_handle is None:
            return
        handle = self._file_handle
        self._file_handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = __import__("fcntl")

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def _read_holder_metadata(self) -> str:
        try:
            return self._lock_path.read_text(encoding="utf-8")
        except OSError:
            return "unknown"
