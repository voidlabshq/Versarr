from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from versarr.infrastructure.persistence import create_engine, metadata


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(tmp_path / "state.db")
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
