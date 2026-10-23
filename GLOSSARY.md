# Glossary

Domain language for Versarr. Use these terms in code, issues and docs.

**Library root**: a configured directory tree of music. Roots are validated to exist and not overlap.

**Track**: one supported audio file under a library root (`.flac`, `.mp3`, `.m4a`, `.mp4`, `.ogg`, `.opus`).

**Sidecar**: the `.lrc` file next to a track holding its lyrics. Sidecars are the authoritative output; Versarr never writes lyrics into embedded tags.

**Embedded lyrics**: lyrics already stored inside the audio file's tags. If present and no sidecar exists, the track is left alone.

**Lyrics gap**: a track with neither a sidecar nor embedded lyrics. `versarr lyrics-gaps` reports gaps per directory.

**Snapshot**: what Versarr last observed about a track: identity (title, artist, ...), size, mtime, and whether a sidecar / embedded lyrics exist. Used for the gap report and for incremental reconciliation.

**Meaningful state hash**: a hash of the parts of a snapshot that matter for lyrics decisions (identity, duration, sidecar and embedded presence). File mtime noise is ignored.

**Tombstone**: a snapshot marked deleted (`deleted_at`) because its file disappeared. Tombstoned snapshots are excluded from the gap report and revived if the file returns.

**Job**: the unit of work for one track. States: `pending`, `processing`, `completed`, `failed`. Priorities, highest first: `force_manual`, `manual`, `watcher`, `reconciliation`.

**Lease**: a worker's time-limited claim on a job (`lease_ttl_seconds`). A **heartbeat** extends it while work is running; expired leases are recovered to `pending` at startup.

**Dirty job**: a job re-enqueued while it was processing; it goes back to `pending` when the current attempt completes.

**Decision**: the policy result for a track: *preserve* (leave it alone), *noop* (skip for now) or *fetch* (look the lyrics up). See `application/job_policy.py`.

**Outcome**: how an attempt ended: `written`, `preserved`, `noop`, `retry`, `deferred`, `terminal`.

**Provenance**: the record of a sidecar Versarr wrote (provider, hash of the lyrics, time). It lets Versarr tell its own sidecars from user-made ones.

**Manual divergence**: a sidecar whose content no longer matches its provenance hash, i.e. the user edited it. Preserved unless a forced rescan allows overwriting.

**Cooldown**: a time window during which a track's lookup key is not queried again after `not_found`, `ambiguous` or `invalid_content` results.

**Provider**: the lyrics source. Currently only LRCLIB.

**Circuit breaker**: shared protection in front of the provider. After repeated transient failures it opens and jobs are *deferred* (no attempt spent) until a probe succeeds.

**Pacer**: the shared limiter that spaces provider HTTP requests.

**Reconciliation**: comparing disk with stored state. Periodic and startup passes are *incremental* (only new, changed or stale tracks are queued); manual full scans evaluate everything.

**Control request**: a command (`rescan_path`, `full_scan`) written to SQLite by the CLI and executed by the running daemon.

**Stability detection**: waiting until a file stops changing (two identical probes after a quiet period) before treating a watcher event as ready.

**Instance lock**: the single-instance file lock in the state directory; a second instance fails fast.
