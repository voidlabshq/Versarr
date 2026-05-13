# Architecture

Versarr is a single-process, sidecar-first lyrics enrichment daemon.

- operational model: long-running daemon with watcher plus reconciliation
- persistence: same-directory `.lrc` sidecars are authoritative
- state: SQLite stores jobs, provenance, cooldowns, and scan checkpoints only
- provider: LRCLIB only in MVP
- interfaces: CLI plus `/health`, `/ready`, and `/metrics`

