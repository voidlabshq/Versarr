from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine as sa_create_engine


def create_engine(sqlite_path: Path) -> Engine:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return sa_create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def run_migrations(sqlite_path: Path) -> None:
    alembic_ini = _find_alembic_ini()
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    command.upgrade(config, "head")


def _find_alembic_ini() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "alembic.ini"
        if candidate.exists():
            return candidate
    msg = "unable to locate alembic.ini"
    raise FileNotFoundError(msg)
