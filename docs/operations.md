# Operations

## Overview

Versarr is a long-running operational daemon for self-hosted music libraries.

Its runtime model combines:

- filesystem event monitoring
- periodic reconciliation scanning
- asynchronous job processing
- persistent operational state
- HTTP observability endpoints

Versarr is intended to run continuously rather than as a one-shot enrichment utility.

---

## Runtime Behavior

Primary operational responsibilities:

- detect library filesystem changes
- identify tracks missing lyrics
- schedule enrichment work
- retrieve lyrics from configured providers
- write `.lrc` sidecar files
- maintain operational process state
- expose runtime observability

Filesystem state remains authoritative.

SQLite stores operational state only.

---

## CLI Commands

### `versarr serve`

Primary daemon runtime.

Starts:

- configuration validation
- state initialization
- database migrations
- HTTP endpoints
- filesystem watcher
- reconciliation scheduling
- worker processing

Example:

```bash
versarr serve
```

This is the primary production runtime mode.

---

### `versarr scan`

Runs an explicit scan operation.

Useful for:

- operational verification
- troubleshooting
- manual execution

Example:

```bash
versarr scan
```

---

### `versarr request-rescan`

Requests targeted reevaluation.

Example:

```bash
versarr request-rescan --root /music /music/Artist/Album/Track.flac
```

Useful for:

- troubleshooting specific files
- forcing reevaluation of known paths

---

### `versarr request-full-scan`

Requests full library reevaluation.

Example:

```bash
versarr request-full-scan --root /music
```

Useful for:

- major library changes
- operational troubleshooting
- state reconciliation

---

### `versarr config-check`

Validates configuration.

Example:

```bash
versarr config-check
```

Recommended after:

- deployment changes
- environment changes
- configuration updates

---

### `versarr db-upgrade`

Runs database migrations.

Example:

```bash
versarr db-upgrade
```

Normally handled automatically during startup.

---

## Scan Model

Versarr uses complementary scan mechanisms.

---

### Filesystem Watcher

Primary real-time detection mechanism.

Used to detect:

- file creation
- modification activity
- eligible media changes

Watcher behavior is optimized for continuous daemon operation.

---

### Stability Protection

Versarr intentionally delays processing of recently changing files.

This reduces risk of acting on:

- incomplete downloads
- actively written files
- transient temporary artifacts

---

### Reconciliation Scanning

Periodic reconciliation reevaluates library state independently of watcher activity.

Purpose:

- recover missed events
- reduce operational drift
- maintain consistency over time

Reconciliation runs periodically and may also occur during startup.

---

## Startup Recovery

Versarr includes restart safety protections for interrupted operational work.

This improves resilience after:

- container restarts
- host reboots
- process crashes
- interrupted deployments

---

## HTTP Endpoints

Versarr exposes operational observability endpoints.

These are infrastructure-facing endpoints, not public application APIs.

Default bind:

```text
0.0.0.0:8080
```

---

### `/health`

Basic liveness indicator.

Typical uses:

- container health checks
- service monitoring
- liveness verification

Example:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"ok"}
```

---

### `/ready`

Operational readiness indicator.

Typical uses:

- readiness probes
- deployment orchestration
- operational dependency checks

---

### `/metrics`

Prometheus metrics endpoint.

Used for:

- monitoring
- dashboards
- operational troubleshooting

Metrics expose operational state such as:

- queue activity
- worker activity
- provider interactions
- retry behavior
- sidecar write behavior
- readiness state

---

## Endpoint Exposure Guidance

Operational assumptions:

- self-hosted deployment
- trusted operator environment
- controlled network access

Recommendations:

- prefer local or private network exposure
- avoid direct public internet exposure
- do not assume built-in authentication
- restrict access appropriately if broader exposure is required

---

## Shutdown Expectations

Versarr is intended for supervised long-running operation.

Expected scenarios:

- service restart
- container stop
- host shutdown
- deployment replacement

Operational recovery protections exist for interrupted work.

Deployment-sensitive shutdown behavior should be validated in your environment.

---

## Troubleshooting

### No lyrics are being written

Check:

- library root configuration
- filesystem permissions
- provider connectivity
- container/process logs

---

### Health endpoint unavailable

Check:

- process/container running state
- bind configuration
- port mapping
- firewall rules

---

### Repeated rescanning

Expected causes:

- filesystem activity
- startup reconciliation
- scheduled reconciliation

Unexpected excessive churn may indicate:

- noisy filesystems
- unstable downloads
- mount churn
- incorrect library scoping

---

### Persistent stale operational state

Potential causes:

- delayed reconciliation
- operational drift
- pending retries or cooldown behavior

Manual remediation:

```bash
versarr request-full-scan --root /music
```

---

## Related Documentation

Deployment guidance:

`docs/deployment.md`

Configuration reference:

`docs/configuration.md`

Architecture constraints:

`docs/architecture.md`