# Deployment

## Overview

Versarr is designed for long-running self-hosted deployment.

The recommended deployment model is:

- Docker
- Docker Compose
- environment-variable configuration via `.env`
- persistent operational state storage
- direct access to music library files

Containerized deployment is the canonical operational model for MVP.

---

## Runtime Storage Layout

Versarr expects persistent access to:

### `/state`

Operational process state.

Used for:

- SQLite database
- migration state
- runtime metadata

Requirements:

- writable
- persistent across restarts

---

### `/music`

Target music library roots.

Used for:

- media file discovery
- sidecar `.lrc` creation

Requirements:

- readable
- writable
- persistent

Versarr writes lyrics as same-directory sidecar files.

---

## Recommended Deployment

### `.env`

Example:

```env
VERSARR_LIBRARY_ROOTS=["/music"]

VERSARR_STATE_DIR="/state"
VERSARR_SQLITE_PATH="/state/versarr.db"

VERSARR_HTTP_BIND_HOST="0.0.0.0"
VERSARR_HTTP_BIND_PORT=8080

VERSARR_WORKER_CONCURRENCY=2

VERSARR_SCAN__RECONCILIATION_INTERVAL_SECONDS=900
VERSARR_SCAN__STARTUP_RECONCILIATION=true
```

Notes:

- environment values use JSON-compatible parsing where applicable
- booleans should use `true` / `false`
- arrays should use JSON syntax
- nested settings use double underscores

Example:

```env
VERSARR_SCAN__RECONCILIATION_INTERVAL_SECONDS=900
```

---

### `compose.yaml`

Example:

```yaml
services:
  versarr:
    image: ghcr.io/voidlabshq/versarr:latest
    container_name: versarr
    restart: unless-stopped

    env_file:
      - .env

    ports:
      - "8080:8080"

    volumes:
      - ./state:/state
      - /srv/music:/music
```

Start:

```bash
docker compose up -d
```

Stop:

```bash
docker compose down
```

---

## Startup Behavior

Normal startup includes:

- configuration loading
- configuration validation
- state initialization
- database migrations
- HTTP endpoint startup
- filesystem watcher startup
- reconciliation scheduling

Operational endpoints:

- `/health`
- `/ready`
- `/metrics`

Health check:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"ok"}
```

---

## Upgrades

Recommended upgrade flow:

```bash
docker compose pull
docker compose up -d
```

Persistent operational state depends on preserving:

```text
/state
```

Do not remove persistent state unintentionally.

---

## Backups

Minimum recommended backup target:

```text
/state
```

The SQLite database contains operational process state.

Lyrics persistence remains filesystem-based through `.lrc` sidecar files.

Music library backup strategy should follow your existing media backup practices.

---

## Network Exposure

Versarr exposes infrastructure-facing operational endpoints.

These endpoints are intended for:

- health checks
- readiness probes
- observability integration

They are not public application APIs.

Recommendations:

- prefer local or trusted network exposure
- avoid direct public internet exposure
- do not assume built-in authentication
- restrict access appropriately if broader exposure is required

---

## Troubleshooting

### Container starts but no lyrics are written

Check:

- music mount path correctness
- library root configuration
- filesystem write permissions
- provider connectivity
- container logs

Common causes:

- invalid `VERSARR_LIBRARY_ROOTS`
- read-only music storage
- incorrect volume mapping

---

### Health endpoint unavailable

Check:

```bash
docker compose ps
curl http://localhost:8080/health
```

Validate:

- container running state
- port mapping
- local firewall rules
- bind configuration

---

### SQLite startup failures

Check:

- `/state` permissions
- persistent storage configuration
- filesystem ownership

Versarr requires writable persistent operational state.

---

### Provider connectivity failures

Current MVP provider:

```text
https://lrclib.net
```

Potential causes:

- firewall restrictions
- DNS failures
- proxy misconfiguration
- upstream provider outage

---

## Related Documentation

Configuration reference:

[Configuration reference](configuration.md)

Operational guidance:

[Operations guide](operations.md)

Architecture constraints:

[Architecture constraints](architecture.md)
