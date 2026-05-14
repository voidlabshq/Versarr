from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import Counter, Gauge, Histogram


@dataclass(slots=True)
class RuntimeReadiness:
    config_loaded: bool = False
    migrations_complete: bool = False
    database_ready: bool = False
    lock_held: bool = False
    worker_active: bool = False
    discovery_active: bool = False

    @property
    def ready(self) -> bool:
        return all(
            [
                self.config_loaded,
                self.migrations_complete,
                self.database_ready,
                self.lock_held,
                self.worker_active,
                self.discovery_active,
            ]
        )


class MetricsFacade:
    def __init__(self) -> None:
        self.jobs_enqueued_total = Counter(
            "versarr_jobs_enqueued_total",
            "Jobs enqueued.",
            labelnames=("trigger",),
        )
        self.jobs_completed_total = Counter(
            "versarr_jobs_completed_total",
            "Jobs completed.",
            labelnames=("outcome", "reason"),
        )
        self.jobs_retried_total = Counter(
            "versarr_jobs_retried_total",
            "Jobs retried.",
            labelnames=("classification",),
        )
        self.provider_requests_total = Counter(
            "versarr_provider_requests_total",
            "Provider requests.",
            labelnames=("provider", "status"),
        )
        self.sidecar_writes_total = Counter(
            "versarr_sidecar_writes_total",
            "Sidecar writes.",
            labelnames=("mode",),
        )
        self.sidecar_conflicts_total = Counter(
            "versarr_sidecar_conflicts_total",
            "Existing sidecar conflicts.",
        )
        self.manual_divergence_total = Counter(
            "versarr_manual_divergence_total",
            "Manual divergence detections.",
        )
        self.embedded_preserved_total = Counter(
            "versarr_embedded_preserved_total",
            "Embedded-only lyrics preserved.",
        )
        self.watcher_events_total = Counter(
            "versarr_watcher_events_total",
            "Watcher events received.",
            labelnames=("kind",),
        )
        self.stability_drops_total = Counter(
            "versarr_stability_drops_total",
            "Dropped unstable candidates.",
            labelnames=("reason",),
        )
        self.startup_recoveries_total = Counter(
            "versarr_startup_recoveries_total",
            "Recovered stale jobs on startup.",
        )
        self.queue_depth = Gauge(
            "versarr_queue_depth",
            "Approximate queue depth.",
            labelnames=("state", "priority"),
        )
        self.active_jobs = Gauge("versarr_active_jobs", "Active jobs.")
        self.watcher_roots_active = Gauge("versarr_watcher_roots_active", "Active watcher roots.")
        self.readiness_state = Gauge("versarr_readiness_state", "Readiness state.")
        self.cooldowns_active = Gauge("versarr_cooldowns_active", "Active cooldown records.")
        self.control_requests_pending = Gauge("versarr_control_requests_pending", "Pending control requests.")
        self.job_duration_seconds = Histogram(
            "versarr_job_duration_seconds",
            "Job duration seconds.",
        )
        self.provider_latency_seconds = Histogram(
            "versarr_provider_latency_seconds",
            "Provider latency seconds.",
            labelnames=("provider",),
        )
        self.sidecar_write_seconds = Histogram(
            "versarr_sidecar_write_seconds",
            "Sidecar write latency seconds.",
        )
        self.metadata_read_seconds = Histogram(
            "versarr_metadata_read_seconds",
            "Metadata read latency seconds.",
        )
        self.scan_duration_seconds = Histogram(
            "versarr_scan_duration_seconds",
            "Scan duration seconds.",
            labelnames=("kind",),
        )
        self.stability_wait_seconds = Histogram(
            "versarr_stability_wait_seconds",
            "Time spent waiting for file stability.",
        )

    def set_readiness(self, ready: bool) -> None:
        self.readiness_state.set(1 if ready else 0)
