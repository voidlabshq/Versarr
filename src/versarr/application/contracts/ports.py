from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from versarr.domain import (
    ControlRequest,
    EnrichmentJob,
    ProvenanceRecord,
    ProviderResult,
    SnapshotStateRecord,
    TrackIdentity,
    TrackSnapshot,
)


class LyricsProvider(Protocol):
    async def fetch(self, identity: TrackIdentity) -> ProviderResult:
        ...


class MetadataReader(Protocol):
    async def read_snapshot(self, media_path: Path, library_root: Path) -> TrackSnapshot:
        ...


@dataclass(frozen=True, slots=True)
class SidecarWriteResult:
    sidecar_path: Path
    normalized_hash: str
    created: bool
    replaced: bool


class SidecarWriter(Protocol):
    async def write(self, sidecar_path: Path, normalized_text: str) -> SidecarWriteResult:
        ...

    async def read_normalized_hash(self, sidecar_path: Path) -> str:
        ...


class StateRepository(Protocol):
    async def enqueue_path(
        self,
        *,
        library_root: Path,
        media_path: Path,
        trigger: str,
        priority: str,
        event_kind: str,
        force: bool = False,
        overwrite_existing: bool = False,
        allow_manual_overwrite: bool = False,
    ) -> None:
        ...

    async def lease_next_ready_job(self, worker_id: str, now: datetime) -> EnrichmentJob | None:
        ...

    async def heartbeat_job(self, job_key: str, lease_until: datetime) -> None:
        ...

    async def complete_job(self, job_key: str, reason_code: str) -> None:
        ...

    async def retry_job(
        self, job_key: str, reason_code: str, error_class: str, next_attempt_at: datetime
    ) -> None:
        ...

    async def fail_job(self, job_key: str, reason_code: str, error_class: str) -> None:
        ...

    async def get_snapshot(self, media_path: Path) -> SnapshotStateRecord | None:
        ...

    async def record_snapshot(self, snapshot: TrackSnapshot) -> None:
        ...

    async def get_provenance(self, media_path: Path) -> ProvenanceRecord | None:
        ...

    async def record_provenance(self, record: ProvenanceRecord) -> None:
        ...

    async def mark_manual_diverged(self, media_path: Path) -> None:
        ...

    async def mark_sidecar_deleted(self, media_path: Path) -> None:
        ...

    async def get_cooldown(self, lookup_key: str, provider_name: str) -> datetime | None:
        ...

    async def record_cooldown(
        self, lookup_key: str, provider_name: str, outcome: str, until_at: datetime
    ) -> None:
        ...

    async def recover_stale_jobs(self, now: datetime, stale_before_seconds: int) -> int:
        ...

    async def enqueue_control_request(self, request: ControlRequest) -> None:
        ...

    async def poll_control_requests(self, limit: int = 10) -> list[tuple[int, ControlRequest]]:
        ...

    async def claim_control_request(self, request_id: int, claimed_at: datetime) -> bool:
        ...

    async def complete_control_request(self, request_id: int) -> None:
        ...

    async def fail_control_request(self, request_id: int, error_code: str) -> None:
        ...

    async def record_scan_start(self, library_root: Path, scan_kind: str, started_at: datetime) -> None:
        ...

    async def record_scan_finish(
        self,
        library_root: Path,
        scan_kind: str,
        completed_at: datetime,
        status: str,
        error_code: str | None = None,
    ) -> None:
        ...

    async def get_queue_depths(self) -> list[tuple[str, str, int]]:
        ...

    async def count_pending_control_requests(self) -> int:
        ...

    async def count_active_cooldowns(self, now: datetime) -> int:
        ...


class FileWatcher(Protocol):
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...


class LibraryScanner(Protocol):
    async def scan(self, root: Path) -> list[Path]:
        ...


class StabilityDetector(Protocol):
    async def observe(self, candidate_path: Path, event_kind: str) -> None:
        ...

    async def poll_ready_paths(self) -> list[Path]:
        ...


@dataclass(frozen=True, slots=True)
class LockHandle:
    path: Path
    holder_metadata: str


class LockManager(Protocol):
    async def acquire(self) -> LockHandle:
        ...

    async def release(self) -> None:
        ...


class Clock(Protocol):
    def now(self) -> datetime:
        ...
