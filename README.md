# Versarr

Versarr is a self-hosted, sidecar-first lyrics enrichment daemon for music libraries.

It continuously monitors one or more library roots, detects tracks missing lyrics, retrieves lyrics from supported providers, and writes same-directory `.lrc` sidecar files.

Versarr is designed for predictable long-running operation in self-hosted environments.

Current MVP scope intentionally excludes embedded tag mutation and playback-time proxy behavior.

---

## Why Versarr?

Self-hosted music ecosystems often handle lyrics inconsistently.

Common approaches typically involve tradeoffs such as:

- playback-time proxy injection with client compatibility constraints
- invasive embedded metadata mutation
- one-off scripts with weak operational resilience
- manual sidecar management
- limited observability for long-running automation

Versarr treats lyrics enrichment as an operational background service.

Core design priorities:

- deterministic behavior
- restart safety
- sidecar-first persistence
- minimal deployment friction
- infrastructure-friendly observability

---

## Features

Current MVP capabilities:

- long-running daemon runtime
- filesystem event monitoring
- periodic reconciliation scanning
- asynchronous multi-worker processing
- SQLite-backed operational state
- same-directory `.lrc` sidecar writing
- LRCLIB provider integration
- Docker-first deployment
- operational HTTP endpoints
  - `/health`
  - `/ready`
  - `/metrics`
- Prometheus metrics exposure
- CLI administration commands
- startup recovery protections

---

## Architecture Overview

Versarr follows a focused single-service architecture.

Runtime components:

- filesystem watcher
- reconciliation scanner
- async worker queue
- provider integration
- SQLite operational state
- HTTP observability surface
- sidecar writer

Architectural constraints:

- `.lrc` sidecars are the authoritative persistence target
- SQLite stores operational state only
- filesystem state remains authoritative
- embedded lyrics writing is out of MVP scope

See:

- [Architecture constraints](docs/architecture.md)
- [Operations guide](docs/operations.md)

---

## Requirements

Recommended deployment:

- Docker
- Docker Compose

Runtime expectations:

- writable music library access
- writable persistent state storage
- outbound HTTPS access to the configured provider

Source development:

- Python 3.12+

---

## Quick Start

Minimal Docker Compose example:

```yaml
services:
  versarr:
    image: ghcr.io/voidlabshq/versarr:latest
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8080:8080"
    volumes:
      - ./state:/state
      - /srv/music:/music
```

Example `.env`:

```env
VERSARR_LIBRARY_ROOTS=["/music"]
VERSARR_HTTP_BIND_PORT=8080
```

Start:

```bash
docker compose up -d
```

Health check:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"ok"}
```

Full deployment guidance:

[Deployment guide](docs/deployment.md)

---

## Configuration

Configuration precedence:

1. CLI arguments
2. environment variables
3. TOML configuration
4. defaults

Recommended deployment uses environment variables.

Configuration reference:

[Configuration reference](docs/configuration.md)

---

## Operations and Observability

Operational endpoints:

- `/health`
- `/ready`
- `/metrics`

Versarr exposes infrastructure-facing observability endpoints, not public application APIs.

Operational guidance:

[Operations guide](docs/operations.md)

---

## Current Limitations

Current MVP intentionally excludes:

- embedded lyrics writing
- playback-time proxy behavior
- multi-provider orchestration
- generalized media management

Current provider support:

- LRCLIB only

---

## Roadmap

Planned work is tracked through GitHub Issues and project planning.

Current roadmap areas include:

- documentation hardening
- CI/CD security improvements
- container security scanning
- operational validation improvements

---

## Contributing

Contributions are welcome.

Expected contribution principles:

- keep changes narrowly scoped
- avoid speculative refactors
- preserve architectural constraints
- validate changes proportionally to risk

Engineering governance:

- `AGENTS.md`
- [Engineering playbook](docs/engineering-playbook.md)

---

## Security

Versarr is self-hosted operational software.

Operational guidance:

- prefer least-privilege filesystem access
- avoid unnecessary public exposure of operational endpoints
- monitor dependency and container security posture

For security issues, prefer responsible private disclosure.

---

## License

Licensed under the Apache License 2.0.

See:

[LICENSE](LICENSE)
