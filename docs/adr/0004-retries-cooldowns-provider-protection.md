# 0004: Retries, cooldowns and provider protection

Status: accepted

## Context
LRCLIB is a shared public service. Failures come in bursts (rate limits, outages) and per-job retry alone multiplies the load.

## Decision
- Provider requests are spaced by a shared pacer (`provider_min_interval_seconds`).
- A shared circuit breaker opens after N consecutive transient failures (429, 5xx, network, malformed body), honoring `Retry-After`; the open window doubles per consecutive trip up to a cap, and a single probe decides recovery. While open, jobs are **deferred**: they return to `pending` and the attempt consumed by the lease is refunded.
- Per-job transient failures retry with exponential backoff (jittered for provider failures) up to `max_attempts`, then fail with `*_retry_exhausted`. This applies to provider failures and to unexpected/filesystem errors alike.
- Client errors (4xx other than 404/429) fail the attempt without a content cooldown.
- `not_found`, `ambiguous` and `invalid_content` results set cooldowns (7d, 3d, 3d by default).

## Consequences
An outage longer than a job's retry window does not burn through attempts. Failed and lyric-less tracks are looked at again by reconciliation after `scan.revisit_after_seconds`.
