# 0003: Single instance guarded by a file lock

Status: accepted

## Context
Two daemons on one state directory would race on jobs, migrations and sidecars.

## Decision
A non-blocking OS file lock (`versarr.lock` in the state directory) is taken before migrations or opening the database. A second instance logs `instance_lock_held` with the holder's pid, host and start time and exits non-zero. The lock is released by the OS if the holder dies. `versarr scan` takes the same lock, so it cannot run next to a daemon.

## Consequences
CLI commands that only read or queue requests (`lyrics-gaps`, `request-*`) do not need the lock and work while the daemon runs.
