from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import text

from versarr.infrastructure.persistence import create_engine


def test_engine_enables_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "state.db")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 30_000
    finally:
        engine.dispose()


def test_reader_is_not_blocked_by_open_write_transaction(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "state.db")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE t (x INTEGER)"))
            connection.execute(text("INSERT INTO t VALUES (1)"))

        writer_ready = threading.Event()
        release_writer = threading.Event()

        def hold_write_transaction() -> None:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO t VALUES (2)"))
                writer_ready.set()
                release_writer.wait(timeout=10)

        thread = threading.Thread(target=hold_write_transaction)
        thread.start()
        try:
            assert writer_ready.wait(timeout=10)
            with engine.connect() as reader:
                assert reader.execute(text("SELECT count(*) FROM t")).scalar() == 1
        finally:
            release_writer.set()
            thread.join(timeout=10)
    finally:
        engine.dispose()
