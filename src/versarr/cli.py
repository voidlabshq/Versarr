from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import uvicorn

from versarr.bootstrap import create_runtime
from versarr.config import load_settings
from versarr.interfaces.http import build_http_app

app = typer.Typer(no_args_is_help=True)


@app.command()
def serve(config: Path | None = typer.Option(default=None, "--config")) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    http_app = build_http_app(runtime)
    uvicorn.run(http_app, host=settings.http_bind_host, port=settings.http_bind_port)


@app.command()
def scan(config: Path | None = typer.Option(default=None, "--config")) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    asyncio.run(runtime.run_scan_once())


@app.command("request-rescan")
def request_rescan(
    path: Path = typer.Argument(...),
    root: Path = typer.Option(..., "--root"),
    force: bool = typer.Option(False),
    overwrite_existing: bool = typer.Option(False),
    allow_manual_overwrite: bool = typer.Option(False),
    config: Path | None = typer.Option(default=None, "--config"),
) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    asyncio.run(
        runtime.enqueue_control_request(
            "rescan_path",
            target_root=root,
            target_path=path,
            force=force,
            overwrite_existing=overwrite_existing,
            allow_manual_overwrite=allow_manual_overwrite,
        )
    )


@app.command("request-full-scan")
def request_full_scan(
    root: Path = typer.Option(..., "--root"),
    force: bool = typer.Option(False),
    overwrite_existing: bool = typer.Option(False),
    allow_manual_overwrite: bool = typer.Option(False),
    config: Path | None = typer.Option(default=None, "--config"),
) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    asyncio.run(
        runtime.enqueue_control_request(
            "full_scan",
            target_root=root,
            force=force,
            overwrite_existing=overwrite_existing,
            allow_manual_overwrite=allow_manual_overwrite,
        )
    )


@app.command("config-check")
def config_check(config: Path | None = typer.Option(default=None, "--config")) -> None:
    settings = load_settings(config)
    typer.echo(f"Configuration valid for {len(settings.library_roots)} library root(s).")


@app.command("db-upgrade")
def db_upgrade(config: Path | None = typer.Option(default=None, "--config")) -> None:
    settings = load_settings(config)
    settings.ensure_directories()
    from versarr.infrastructure.persistence import run_migrations

    run_migrations(settings.sqlite_path)
    typer.echo("Database upgraded.")
