# Configuration

## Overview

Versarr supports multiple configuration sources.

Values are applied in the following precedence order:

1. CLI arguments
2. environment variables
3. TOML configuration
4. defaults

Higher-precedence values override lower-precedence values.

Recommended deployment uses environment variables via Docker Compose.

---

## Environment Variable Model

Versarr uses:

- prefix: `VERSARR_`
- nested delimiter: double underscore (`__`)

Examples:

```env
VERSARR_HTTP_BIND_PORT=8080
VERSARR_WORKER_CONCURRENCY=4
VERSARR_SCAN__RECONCILIATION_INTERVAL_SECONDS=1800
VERSARR_POLICY__OVERWRITE_EXISTING=false
```

---

## Parsing Rules

Environment values are parsed using JSON-compatible semantics where applicable.

Examples:

### Boolean

```env
VERSARR_POLICY__OVERWRITE_EXISTING=true
```

---

### Integer

```env
VERSARR_WORKER_CONCURRENCY=4
```

---

### Array

```env
VERSARR_LIBRARY_ROOTS=["/music"]
```

Multiple roots:

```env
VERSARR_LIBRARY_ROOTS=["/music","/music-archive"]
```

---

### String

```env
VERSARR_HTTP_BIND_HOST="0.0.0.0"
VERSARR_PROVIDER_BASE_URL="https://lrclib.net"
```

---

## Required Configuration

### `VERSARR_LIBRARY_ROOTS`

Required.

Defines one or more library roots monitored by Versarr.

Example:

```env
VERSARR_LIBRARY_ROOTS=["/music"]
```

Validation rules:

- at least one root is required
- configured roots must exist
- duplicate roots are rejected
- overlapping parent/child roots are rejected

Invalid example:

```env
VERSARR_LIBRARY_ROOTS=["/music","/music/archive"]
```

---

## Common Runtime Settings

### HTTP

```env
VERSARR_HTTP_BIND_HOST="0.0.0.0"
VERSARR_HTTP_BIND_PORT=8080
```

Controls operational endpoint exposure.

---

### State Storage

```env
VERSARR_STATE_DIR="/state"
VERSARR_SQLITE_PATH="/state/versarr.db"
```

Controls persistent operational state.

The SQLite database must reside under the configured state directory.

---

### Worker Concurrency

```env
VERSARR_WORKER_CONCURRENCY=2
```

Controls concurrent async processing capacity.

Must be greater than zero.

---

### Provider Settings

Current MVP provider support is LRCLIB-only.

Example:

```env
VERSARR_PROVIDER_BASE_URL="https://lrclib.net"
VERSARR_PROVIDER_TIMEOUT_SECONDS=10
```

---

## Common Operational Tuning

### Reconciliation Interval

Controls periodic full library reevaluation.

Example:

```env
VERSARR_SCAN__RECONCILIATION_INTERVAL_SECONDS=900
```

---

### Startup Reconciliation

Controls whether reconciliation runs during startup.

Example:

```env
VERSARR_SCAN__STARTUP_RECONCILIATION=true
```

---

### Overwrite Policy

Controls whether existing sidecar lyrics may be replaced.

Example:

```env
VERSARR_POLICY__OVERWRITE_EXISTING=false
```

---

## Advanced Configuration

Additional nested settings exist for advanced tuning, including:

- retry behavior
- cooldown timing
- file stability detection
- overwrite policy behavior

Most operators should not need to modify these defaults.

---

## Docker Compose Example

Example `.env`:

```env
VERSARR_LIBRARY_ROOTS=["/music"]

VERSARR_STATE_DIR="/state"
VERSARR_SQLITE_PATH="/state/versarr.db"

VERSARR_HTTP_BIND_HOST="0.0.0.0"
VERSARR_HTTP_BIND_PORT=8080

VERSARR_WORKER_CONCURRENCY=2

VERSARR_PROVIDER_BASE_URL="https://lrclib.net"
VERSARR_PROVIDER_TIMEOUT_SECONDS=10

VERSARR_SCAN__RECONCILIATION_INTERVAL_SECONDS=900
VERSARR_SCAN__STARTUP_RECONCILIATION=true
```

---

## TOML Support

TOML configuration remains supported.

Example:

```toml
library_roots = ["/music"]

state_dir = "/state"
sqlite_path = "/state/versarr.db"

http_bind_host = "0.0.0.0"
http_bind_port = 8080
```

Environment-variable deployment remains the recommended operational path.

---

## Validation

Validate configuration before runtime:

```bash
versarr config-check
```

Recommended after:

- environment changes
- deployment changes
- configuration refactoring

---

## Related Documentation

Deployment guidance:

[Deployment guide](deployment.md)

Operational guidance:

[Operations guide](operations.md)

Architecture constraints:

[Architecture constraints](architecture.md)
