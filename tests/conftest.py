from __future__ import annotations

from pathlib import Path

import pytest

from versarr.infrastructure.persistence import create_engine, metadata


@pytest.fixture()
def sqlite_engine(tmp_path: Path):
    engine = create_engine(tmp_path / "state.db")
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()

