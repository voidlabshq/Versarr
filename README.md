# Versarr

Versarr is a sidecar-first lyrics enrichment daemon for self-hosted music libraries.

It watches one or more library roots, detects stable media files that are missing lyrics, queries LRCLIB, and writes same-directory `.lrc` sidecars. It does not proxy lyrics at playback time, does not modify embedded tags in the MVP, and uses SQLite only for operational state.

## MVP status

This repository is scaffolded for the approved MVP:

- long-running daemon with watcher plus reconciliation scan
- CLI administration
- operational HTTP endpoints only: `/health`, `/ready`, `/metrics`
- `.lrc` sidecar-first persistence
- LRCLIB-only provider integration
- SQLite process-state storage only

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
versarr config-check
```

