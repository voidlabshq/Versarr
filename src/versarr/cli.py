from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from versarr.bootstrap import create_runtime
from versarr.config import load_settings
from versarr.domain import DirectoryGapSummary
from versarr.interfaces.http import build_http_app
from versarr.observability import configure_logging

app = typer.Typer(no_args_is_help=True)

ConfigOption = Annotated[
    Path | None,
    typer.Option("--config"),
]

RescanPathArgument = Annotated[
    Path,
    typer.Argument(),
]

RootOption = Annotated[
    Path | None,
    typer.Option("--root"),
]

ForceOption = Annotated[
    bool,
    typer.Option("--force"),
]

OverwriteOption = Annotated[
    bool,
    typer.Option("--overwrite-existing"),
]

ManualOverwriteOption = Annotated[
    bool,
    typer.Option("--allow-manual-overwrite"),
]

AllOption = Annotated[
    bool,
    typer.Option("--all", help="Show directories without gaps too."),
]


@app.command()
def serve(config: ConfigOption = None) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    http_app = build_http_app(runtime)
    uvicorn.run(http_app, host=settings.http_bind_host, port=settings.http_bind_port)


@app.command()
def scan(config: ConfigOption = None) -> None:
    settings = load_settings(config)
    runtime = create_runtime(settings)
    asyncio.run(runtime.run_scan_once())


@app.command("request-rescan")
def request_rescan(
    path: RescanPathArgument,
    root: RootOption,
    force: ForceOption = False,
    overwrite_existing: OverwriteOption = False,
    allow_manual_overwrite: ManualOverwriteOption = False,
    config: ConfigOption = None,
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
    root: RootOption,
    force: ForceOption = False,
    overwrite_existing: OverwriteOption = False,
    allow_manual_overwrite: ManualOverwriteOption = False,
    config: ConfigOption = None,
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
def config_check(config: ConfigOption = None) -> None:
    settings = load_settings(config)
    typer.echo(f"Configuration valid for {len(settings.library_roots)} library root(s).")


@app.command("db-upgrade")
def db_upgrade(config: ConfigOption = None) -> None:
    settings = load_settings(config)
    settings.ensure_directories()
    from versarr.infrastructure.persistence import run_migrations

    run_migrations(settings.sqlite_path)
    typer.echo("Database upgraded.")


@app.command("lyrics-gaps")
def lyrics_gaps(
    root: RootOption = None,
    show_all: AllOption = False,
    config: ConfigOption = None,
) -> None:
    settings = load_settings(config)
    configure_logging(settings.log_level)
    settings.ensure_directories()

    from versarr.infrastructure.persistence import (
        SqliteStateRepository,
        create_engine,
        run_migrations,
    )

    run_migrations(settings.sqlite_path)
    engine = create_engine(settings.sqlite_path)
    repository = SqliteStateRepository(engine)
    try:
        summaries = asyncio.run(repository.list_directory_gap_summaries(root))
    finally:
        engine.dispose()

    if not show_all:
        summaries = [summary for summary in summaries if summary.tracks_missing_lyrics > 0]

    if not summaries:
        typer.echo("No lyric gaps found in persisted scan state.")
        return

    total_tracks = sum(summary.total_tracks for summary in summaries)
    tracks_with_lyrics = sum(summary.tracks_with_lyrics for summary in summaries)
    tracks_missing_lyrics = sum(summary.tracks_missing_lyrics for summary in summaries)
    typer.echo(f"Directories: {len(summaries)} | Tracks with lyrics: {tracks_with_lyrics}/{total_tracks} | Missing: {tracks_missing_lyrics}")
    for summary in summaries:
        typer.echo(_format_gap_summary(summary))


def _format_gap_summary(summary: DirectoryGapSummary) -> str:
    status_parts: list[str] = []
    if summary.pending_jobs:
        status_parts.append(f"pending={summary.pending_jobs}")
    if summary.processing_jobs:
        status_parts.append(f"processing={summary.processing_jobs}")
    if summary.failed_jobs:
        status_parts.append(f"failed={summary.failed_jobs}")
    if summary.active_cooldowns:
        status_parts.append(f"cooldown={summary.active_cooldowns}")
    if summary.manual_diverged:
        status_parts.append(f"manual_diverged={summary.manual_diverged}")
    status_suffix = f" [{' '.join(status_parts)}]" if status_parts else ""
    return f"{summary.directory_path} ({summary.tracks_with_lyrics}/{summary.total_tracks}){status_suffix}"
