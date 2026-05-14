from __future__ import annotations

from pathlib import Path

import pytest

from versarr.infrastructure.filesystem import AtomicLrcWriter


@pytest.mark.asyncio
async def test_sidecar_writer_creates_and_replaces_normalized_lrc(tmp_path: Path) -> None:
    writer = AtomicLrcWriter()
    sidecar_path = tmp_path / "track.lrc"

    created = await writer.write(sidecar_path, "Hello\r\n\r\nWorld")
    replaced = await writer.write(sidecar_path, "Hello\n\nWorld")

    assert created.created is True
    assert replaced.replaced is True
    assert sidecar_path.read_text(encoding="utf-8") == "Hello\n\nWorld"
    assert await writer.read_normalized_hash(sidecar_path) == replaced.normalized_hash


@pytest.mark.asyncio
async def test_sidecar_writer_fsyncs_parent_directory_after_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = AtomicLrcWriter()
    sidecar_path = tmp_path / "track.lrc"
    synced_directories: list[Path] = []

    def record_directory_fsync(directory_path: Path) -> None:
        synced_directories.append(directory_path)

    monkeypatch.setattr(writer, "_fsync_directory", record_directory_fsync)

    await writer.write(sidecar_path, "Hello")

    assert synced_directories == [tmp_path]


def test_sidecar_writer_directory_fsync_is_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = AtomicLrcWriter()

    def raise_open_error(path: Path, flags: int) -> int:
        del path, flags
        msg = "directory open unsupported"
        raise OSError(msg)

    monkeypatch.setattr("os.open", raise_open_error)

    writer._fsync_directory(tmp_path)
