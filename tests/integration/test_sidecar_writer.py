from __future__ import annotations

from pathlib import Path

import pytest

from versarr.infrastructure.filesystem import AtomicLrcWriter


@pytest.mark.asyncio()
async def test_sidecar_writer_creates_and_replaces_normalized_lrc(tmp_path: Path) -> None:
    writer = AtomicLrcWriter()
    sidecar_path = tmp_path / "track.lrc"

    created = await writer.write(sidecar_path, "Hello\r\n\r\nWorld")
    replaced = await writer.write(sidecar_path, "Hello\n\nWorld")

    assert created.created is True
    assert replaced.replaced is True
    assert sidecar_path.read_text(encoding="utf-8") == "Hello\n\nWorld"
    assert await writer.read_normalized_hash(sidecar_path) == replaced.normalized_hash

