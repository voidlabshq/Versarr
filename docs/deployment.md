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
VERSARR_HTTP_BIND_PORT=9280

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
      - "9280:9280"

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
curl http://localhost:9280/health
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

## Container user and file ownership

The image runs as user `versarr` with uid and gid **1000:1000**. This matches the first user on most Linux systems, so bind mounts owned by that user work without changes.

Versarr must be able to write to `/state` and to your music library (it writes `.lrc` files next to the tracks). If your mounted directories belong to a different user, either:

- run the container as that user in compose: `user: "<uid>:<gid>"` (find yours with `id -u` and `id -g`), or
- change the owner of the directories to 1000:1000.

Named volumes created by versions up to 2.1.0 belong to uid 10001. After upgrading, fix them once:

```bash
docker run --rm -u 0 -v versarr-state:/state ghcr.io/voidlabshq/versarr:latest chown -R 1000:1000 /state
```

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
curl http://localhost:9280/health
```

Validate:

- container running state
- port mapping
- local firewall rules
- bind configuration

---

### SQLite startup failures

A `PermissionError` on `/state/versarr.lock` means the container user (1000:1000 by default) cannot write the mounted directory. See [Container user and file ownership](#container-user-and-file-ownership).

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
