# 0002: SQLite stores process state only

Status: accepted

## Context
The authoritative data (sidecars, audio files) lives on disk. A database that also owned user data would need backup and migration care.

## Decision
SQLite holds only process state: jobs, snapshots, provenance, cooldowns, scan checkpoints and control requests. It runs in WAL mode with a busy timeout so the CLI can read and queue requests while the daemon writes. Datetimes are stored as UTC and returned timezone-aware. The database can be deleted: the next scan rebuilds it from disk (losing cooldowns and provenance, so existing sidecars are then treated as user-made).

## Consequences
Schema changes go through Alembic migrations. Nothing here is a source of truth for lyrics.
