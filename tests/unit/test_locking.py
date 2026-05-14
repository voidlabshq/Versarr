from __future__ import annotations

from pathlib import Path

from versarr.infrastructure.filesystem.locking import FileLockManager


def test_file_lock_manager_can_be_acquired_multiple_times(tmp_path: Path) -> None:
    lock_path = tmp_path / "versarr.lock"

    first = FileLockManager(lock_path)
    first._acquire_sync()
    first._release_sync()

    second = FileLockManager(lock_path)
    second._acquire_sync()
    second._release_sync()
