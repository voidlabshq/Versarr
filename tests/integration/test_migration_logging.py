from __future__ import annotations

import logging
from pathlib import Path

from versarr.infrastructure.persistence import run_migrations


def test_run_migrations_preserves_logging_configuration(tmp_path: Path) -> None:
    uvicorn_logger = logging.getLogger("uvicorn.error")
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    root.setLevel(logging.INFO)

    try:
        run_migrations(tmp_path / "state.db")

        assert root.level == logging.INFO
        assert root.handlers == original_handlers
        assert not uvicorn_logger.disabled
    finally:
        root.setLevel(original_level)
