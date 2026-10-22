from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlalchemy import create_engine as sa_create_engine

BUSY_TIMEOUT_MS = 30_000


def create_engine(sqlite_path: Path) -> Engine:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    engine = sa_create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _configure_connection)
    return engine


def _configure_connection(dbapi_connection: Any, _: object) -> None:
    # WAL lets the CLI read while the daemon writes; the timeout makes writers wait instead of failing.
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def run_migrations(sqlite_path: Path) -> None:
    alembic_ini = _find_alembic_ini()
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    # Keep the application's logging configuration; alembic.ini's would reset the root logger.
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def _find_alembic_ini() -> Path:
    env_override = os.getenv("VERSARR_ALEMBIC_INI")
    if env_override:
        candidate = Path(env_override).resolve()
        if candidate.exists():
            return candidate

    cwd_candidate = Path("/app/alembic.ini")
    if cwd_candidate.exists():
        return cwd_candidate

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "alembic.ini"
        if candidate.exists():
            return candidate

    msg = "unable to locate alembic.ini"
    raise FileNotFoundError(msg)
