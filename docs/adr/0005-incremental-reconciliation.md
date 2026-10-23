# 0005: Incremental reconciliation with tombstones

Status: accepted

## Context
Re-queueing every file on every pass re-read the whole library, reset finished jobs and revived exhausted ones against the provider.

## Decision
Startup and periodic passes queue only tracks that need evaluation: new or tombstoned, changed (size or mtime), sidecar appeared or disappeared, or lyric-less with a last job older than `scan.revisit_after_seconds`. Jobs already queued are left alone. Manual full scans (`request-full-scan`, `versarr scan`) evaluate everything. After a successful scan, snapshots whose files are gone are tombstoned (skipped when the root is not a directory, so an unmounted library does not erase state).

## Consequences
Passes cost one stat per file plus one query. Files with lyrics and no change are never re-read.
