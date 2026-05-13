from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent
from watchdog.observers import Observer

from versarr.application.contracts import FileWatcher


class _EventHandler(FileSystemEventHandler):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        callback: Callable[[Path, str], Awaitable[None]],
    ) -> None:
        self._loop = loop
        self._callback = callback

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.src_path), "modified")

    def on_moved(self, event: FileSystemMovedEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.dest_path), "moved")

    def _schedule(self, path: Path, kind: str) -> None:
        asyncio.run_coroutine_threadsafe(self._callback(path, kind), self._loop)


class WatchdogFileWatcher(FileWatcher):
    def __init__(
        self,
        *,
        roots: tuple[Path, ...],
        callback: Callable[[Path, str], Awaitable[None]],
    ) -> None:
        self._roots = roots
        self._callback = callback
        self._observer: Observer | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        handler = _EventHandler(loop, self._callback)
        observer = Observer()
        for root in self._roots:
            observer.schedule(handler, str(root), recursive=True)
        observer.start()
        self._observer = observer

    async def stop(self) -> None:
        if self._observer is None:
            return
        observer = self._observer
        self._observer = None
        await asyncio.to_thread(observer.stop)
        await asyncio.to_thread(observer.join)
