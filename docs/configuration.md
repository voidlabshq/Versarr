# Configuration

Configuration sources are applied in this order:

1. CLI flags
2. environment variables
3. optional TOML config file
4. defaults

Key settings:

- `library_roots`
- `state_dir`
- `sqlite_path`
- `http_bind_host`
- `http_bind_port`
- `worker_concurrency`
- `provider_timeout_seconds`
- `scan.reconciliation_interval_seconds`
- `policy.overwrite_existing`

