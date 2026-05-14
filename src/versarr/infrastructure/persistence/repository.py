from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, and_, case, func, insert, select, update
from sqlalchemy.engine import RowMapping

from versarr.application.contracts import StateRepository
from versarr.domain import (
    ControlRequest,
    ControlRequestStatus,
    ControlRequestType,
    DirectoryGapSummary,
    EnrichmentJob,
    JobPriority,
    JobState,
    ProvenanceRecord,
    SnapshotStateRecord,
    TrackSnapshot,
    TriggerKind,
)

from .schema import control_requests, cooldowns, jobs, provenance, scan_state, track_snapshots


class SqliteStateRepository(StateRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

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
        await asyncio.to_thread(
            self._enqueue_path_sync,
            library_root,
            media_path,
            trigger,
            priority,
            event_kind,
            force,
            overwrite_existing,
            allow_manual_overwrite,
        )

    def _enqueue_path_sync(
        self,
        library_root: Path,
        media_path: Path,
        trigger: str,
        priority: str,
        event_kind: str,
        force: bool,
        overwrite_existing: bool,
        allow_manual_overwrite: bool,
    ) -> None:
        now = datetime.now(UTC)
        job_key = str(media_path)
        with self._engine.begin() as connection:
            existing = connection.execute(select(jobs).where(jobs.c.job_key == job_key)).mappings().first()
            if existing is None:
                connection.execute(
                    insert(jobs).values(
                        job_key=job_key,
                        library_root=str(library_root),
                        media_path=str(media_path),
                        trigger=trigger,
                        priority=priority,
                        state=JobState.PENDING,
                        attempt_count=0,
                        next_attempt_at=now,
                        dirty=False,
                        force=force,
                        overwrite_existing=overwrite_existing,
                        allow_manual_overwrite=allow_manual_overwrite,
                        last_event_kind=event_kind,
                        last_event_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return

            dirty = existing["state"] == JobState.PROCESSING
            connection.execute(
                update(jobs)
                .where(jobs.c.job_key == job_key)
                .values(
                    trigger=trigger,
                    priority=priority,
                    dirty=dirty if existing["state"] == JobState.PROCESSING else False,
                    force=force or bool(existing["force"]),
                    overwrite_existing=(overwrite_existing or bool(existing["overwrite_existing"])),
                    allow_manual_overwrite=(allow_manual_overwrite or bool(existing["allow_manual_overwrite"])),
                    last_event_kind=event_kind,
                    last_event_at=now,
                    next_attempt_at=(now if existing["state"] != JobState.PROCESSING else existing["next_attempt_at"]),
                    attempt_count=existing["attempt_count"] if existing["state"] == JobState.PROCESSING else 0,
                    state=JobState.PENDING if existing["state"] != JobState.PROCESSING else existing["state"],
                    updated_at=now,
                )
            )

    async def lease_next_ready_job(self, worker_id: str, now: datetime) -> EnrichmentJob | None:
        return await asyncio.to_thread(self._lease_next_ready_job_sync, worker_id, now)

    def _lease_next_ready_job_sync(self, worker_id: str, now: datetime) -> EnrichmentJob | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(jobs)
                    .where(
                        and_(
                            jobs.c.state == JobState.PENDING,
                            jobs.c.next_attempt_at <= now,
                        )
                    )
                    .order_by(
                        case(
                            (jobs.c.priority == JobPriority.FORCE_MANUAL, 0),
                            (jobs.c.priority == JobPriority.MANUAL, 1),
                            (jobs.c.priority == JobPriority.WATCHER, 2),
                            else_=3,
                        ),
                        jobs.c.next_attempt_at.asc(),
                        jobs.c.created_at.asc(),
                    )
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            lease_until = now + timedelta(seconds=120)
            connection.execute(
                update(jobs)
                .where(jobs.c.job_key == row["job_key"])
                .values(
                    state=JobState.PROCESSING,
                    lease_owner=worker_id,
                    lease_until=lease_until,
                    attempt_count=row["attempt_count"] + 1,
                    updated_at=now,
                )
            )
            leased = dict(row)
            leased["state"] = JobState.PROCESSING
            leased["lease_until"] = lease_until
            leased["attempt_count"] = row["attempt_count"] + 1
            return _row_to_job(leased)

    async def heartbeat_job(self, job_key: str, lease_until: datetime) -> None:
        await asyncio.to_thread(self._heartbeat_job_sync, job_key, lease_until)

    def _heartbeat_job_sync(self, job_key: str, lease_until: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(update(jobs).where(jobs.c.job_key == job_key).values(lease_until=lease_until, updated_at=datetime.now(UTC)))

    async def complete_job(self, job_key: str, reason_code: str) -> None:
        await asyncio.to_thread(self._complete_job_sync, job_key, reason_code)

    def _complete_job_sync(self, job_key: str, reason_code: str) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            existing = connection.execute(select(jobs.c.dirty, jobs.c.attempt_count).where(jobs.c.job_key == job_key)).first()
            dirty = bool(existing[0]) if existing is not None else False
            attempt_count = int(existing[1]) if existing is not None else 0
            connection.execute(
                update(jobs)
                .where(jobs.c.job_key == job_key)
                .values(
                    state=JobState.PENDING if dirty else JobState.COMPLETED,
                    dirty=False,
                    next_attempt_at=now if dirty else None,
                    lease_owner=None,
                    lease_until=None,
                    last_reason_code=reason_code,
                    attempt_count=0 if dirty else attempt_count,
                    updated_at=now,
                )
            )

    async def retry_job(self, job_key: str, reason_code: str, error_class: str, next_attempt_at: datetime) -> None:
        await asyncio.to_thread(
            self._retry_job_sync,
            job_key,
            reason_code,
            error_class,
            next_attempt_at,
        )

    def _retry_job_sync(self, job_key: str, reason_code: str, error_class: str, next_attempt_at: datetime) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(jobs)
                .where(jobs.c.job_key == job_key)
                .values(
                    state=JobState.PENDING,
                    lease_owner=None,
                    lease_until=None,
                    next_attempt_at=next_attempt_at,
                    last_reason_code=reason_code,
                    last_error_class=error_class,
                    updated_at=now,
                )
            )

    async def fail_job(self, job_key: str, reason_code: str, error_class: str) -> None:
        await asyncio.to_thread(self._fail_job_sync, job_key, reason_code, error_class)

    def _fail_job_sync(self, job_key: str, reason_code: str, error_class: str) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(jobs)
                .where(jobs.c.job_key == job_key)
                .values(
                    state=JobState.FAILED,
                    lease_owner=None,
                    lease_until=None,
                    next_attempt_at=None,
                    last_reason_code=reason_code,
                    last_error_class=error_class,
                    updated_at=now,
                )
            )

    async def get_snapshot(self, media_path: Path) -> SnapshotStateRecord | None:
        return await asyncio.to_thread(self._get_snapshot_sync, media_path)

    def _get_snapshot_sync(self, media_path: Path) -> SnapshotStateRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(select(track_snapshots).where(track_snapshots.c.media_path == str(media_path))).mappings().first()
        return _row_to_snapshot(row) if row is not None else None

    async def record_snapshot(self, snapshot: TrackSnapshot) -> None:
        await asyncio.to_thread(self._record_snapshot_sync, snapshot)

    def _record_snapshot_sync(self, snapshot: TrackSnapshot) -> None:
        now = datetime.now(UTC)
        values = {
            "media_path": str(snapshot.media_path),
            "library_root": str(snapshot.library_root),
            "extension": snapshot.extension,
            "file_size": snapshot.file_size,
            "file_mtime_ns": snapshot.file_mtime_ns,
            "meaningful_state_hash": snapshot.meaningful_state_hash,
            "normalized_lookup_key": snapshot.identity.normalized_lookup_key,
            "duration_seconds": snapshot.identity.duration_seconds,
            "embedded_exists": snapshot.lyrics_presence.embedded_exists,
            "sidecar_exists": snapshot.lyrics_presence.sidecar_exists,
            "last_seen_at": now,
            "deleted_at": None,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(track_snapshots.c.media_path).where(track_snapshots.c.media_path == str(snapshot.media_path))
            ).first()
            if existing is None:
                connection.execute(insert(track_snapshots).values(**values))
            else:
                connection.execute(update(track_snapshots).where(track_snapshots.c.media_path == str(snapshot.media_path)).values(**values))

    async def get_provenance(self, media_path: Path) -> ProvenanceRecord | None:
        return await asyncio.to_thread(self._get_provenance_sync, media_path)

    def _get_provenance_sync(self, media_path: Path) -> ProvenanceRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(select(provenance).where(provenance.c.media_path == str(media_path))).mappings().first()
        return _row_to_provenance(row) if row is not None else None

    async def record_provenance(self, record: ProvenanceRecord) -> None:
        await asyncio.to_thread(self._record_provenance_sync, record)

    def _record_provenance_sync(self, record: ProvenanceRecord) -> None:
        now = datetime.now(UTC)
        values = {
            "media_path": str(record.media_path),
            "sidecar_path": str(record.sidecar_path),
            "artifact_type": record.artifact_type,
            "normalized_lyrics_hash": record.normalized_lyrics_hash,
            "provider_name": record.provider_name,
            "provider_track_id": record.provider_track_id,
            "synced": record.synced,
            "last_written_at": record.last_written_at,
            "manual_diverged": record.manual_diverged,
            "sidecar_deleted": record.sidecar_deleted,
            "conflict_marker": record.conflict_marker,
            "updated_at": now,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(select(provenance.c.media_path).where(provenance.c.media_path == str(record.media_path))).first()
            if existing is None:
                connection.execute(insert(provenance).values(**values))
            else:
                connection.execute(update(provenance).where(provenance.c.media_path == str(record.media_path)).values(**values))

    async def mark_manual_diverged(self, media_path: Path) -> None:
        await asyncio.to_thread(self._mark_manual_diverged_sync, media_path)

    def _mark_manual_diverged_sync(self, media_path: Path) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(provenance).where(provenance.c.media_path == str(media_path)).values(manual_diverged=True, updated_at=datetime.now(UTC))
            )

    async def mark_sidecar_deleted(self, media_path: Path) -> None:
        await asyncio.to_thread(self._mark_sidecar_deleted_sync, media_path)

    def _mark_sidecar_deleted_sync(self, media_path: Path) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(provenance).where(provenance.c.media_path == str(media_path)).values(sidecar_deleted=True, updated_at=datetime.now(UTC))
            )

    async def get_cooldown(self, lookup_key: str, provider_name: str) -> datetime | None:
        return await asyncio.to_thread(self._get_cooldown_sync, lookup_key, provider_name)

    def _get_cooldown_sync(self, lookup_key: str, provider_name: str) -> datetime | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(cooldowns.c.until_at).where(
                    and_(
                        cooldowns.c.lookup_key == lookup_key,
                        cooldowns.c.provider_name == provider_name,
                    )
                )
            ).first()
        return None if row is None else row[0]

    async def record_cooldown(self, lookup_key: str, provider_name: str, outcome: str, until_at: datetime) -> None:
        await asyncio.to_thread(
            self._record_cooldown_sync,
            lookup_key,
            provider_name,
            outcome,
            until_at,
        )

    def _record_cooldown_sync(self, lookup_key: str, provider_name: str, outcome: str, until_at: datetime) -> None:
        now = datetime.now(UTC)
        values = {
            "lookup_key": lookup_key,
            "provider_name": provider_name,
            "outcome": outcome,
            "until_at": until_at,
            "attempt_count": 1,
            "updated_at": now,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(select(cooldowns.c.lookup_key).where(cooldowns.c.lookup_key == lookup_key)).first()
            if existing is None:
                connection.execute(insert(cooldowns).values(**values))
            else:
                connection.execute(update(cooldowns).where(cooldowns.c.lookup_key == lookup_key).values(**values))

    async def recover_stale_jobs(self, now: datetime, stale_before_seconds: int) -> int:
        return await asyncio.to_thread(self._recover_stale_jobs_sync, now, stale_before_seconds)

    def _recover_stale_jobs_sync(self, now: datetime, stale_before_seconds: int) -> int:
        del stale_before_seconds
        with self._engine.begin() as connection:
            result = connection.execute(
                update(jobs)
                .where(
                    and_(
                        jobs.c.state == JobState.PROCESSING,
                        jobs.c.lease_until < now,
                    )
                )
                .values(
                    state=JobState.PENDING,
                    lease_owner=None,
                    lease_until=None,
                    next_attempt_at=now,
                    last_reason_code="orphan_recovered",
                    updated_at=now,
                )
            )
        return int(result.rowcount or 0)

    async def enqueue_control_request(self, request: ControlRequest) -> None:
        await asyncio.to_thread(self._enqueue_control_request_sync, request)

    def _enqueue_control_request_sync(self, request: ControlRequest) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(control_requests).values(
                    request_type=request.request_type,
                    target_root=str(request.target_root) if request.target_root else None,
                    target_path=str(request.target_path) if request.target_path else None,
                    force=request.force,
                    overwrite_existing=request.overwrite_existing,
                    allow_manual_overwrite=request.allow_manual_overwrite,
                    status=request.status,
                    requested_at=request.requested_at,
                )
            )

    async def poll_control_requests(self, limit: int = 10) -> list[tuple[int, ControlRequest]]:
        return await asyncio.to_thread(self._poll_control_requests_sync, limit)

    def _poll_control_requests_sync(self, limit: int) -> list[tuple[int, ControlRequest]]:
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    select(control_requests)
                    .where(control_requests.c.status == ControlRequestStatus.PENDING)
                    .order_by(control_requests.c.requested_at.asc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return [(int(row["id"]), _row_to_control_request(row)) for row in rows]

    async def claim_control_request(self, request_id: int, claimed_at: datetime) -> bool:
        return await asyncio.to_thread(self._claim_control_request_sync, request_id, claimed_at)

    def _claim_control_request_sync(self, request_id: int, claimed_at: datetime) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                update(control_requests)
                .where(
                    and_(
                        control_requests.c.id == request_id,
                        control_requests.c.status == ControlRequestStatus.PENDING,
                    )
                )
                .values(status=ControlRequestStatus.CLAIMED, claimed_at=claimed_at)
            )
        return bool(result.rowcount)

    async def complete_control_request(self, request_id: int) -> None:
        await asyncio.to_thread(self._complete_control_request_sync, request_id)

    def _complete_control_request_sync(self, request_id: int) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(control_requests)
                .where(control_requests.c.id == request_id)
                .values(
                    status=ControlRequestStatus.COMPLETED,
                    completed_at=datetime.now(UTC),
                    error_code=None,
                )
            )

    async def fail_control_request(self, request_id: int, error_code: str) -> None:
        await asyncio.to_thread(self._fail_control_request_sync, request_id, error_code)

    def _fail_control_request_sync(self, request_id: int, error_code: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(control_requests)
                .where(control_requests.c.id == request_id)
                .values(
                    status=ControlRequestStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error_code=error_code,
                )
            )

    async def record_scan_start(
        self,
        library_root: Path,
        scan_kind: str,
        started_at: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._record_scan_state_sync,
            library_root,
            scan_kind,
            started_at,
            None,
            None,
            None,
        )

    async def record_scan_finish(
        self,
        library_root: Path,
        scan_kind: str,
        completed_at: datetime,
        status: str,
        error_code: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_scan_state_sync,
            library_root,
            scan_kind,
            None,
            completed_at,
            status,
            error_code,
        )

    async def get_queue_depths(self) -> list[tuple[str, str, int]]:
        return await asyncio.to_thread(self._get_queue_depths_sync)

    def _get_queue_depths_sync(self) -> list[tuple[str, str, int]]:
        with self._engine.begin() as connection:
            rows = connection.execute(select(jobs.c.state, jobs.c.priority)).all()
        counts: dict[tuple[str, str], int] = {}
        for state, priority in rows:
            key = (str(state), str(priority))
            counts[key] = counts.get(key, 0) + 1
        return [(state, priority, count) for (state, priority), count in counts.items()]

    async def count_pending_control_requests(self) -> int:
        return await asyncio.to_thread(self._count_pending_control_requests_sync)

    def _count_pending_control_requests_sync(self) -> int:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(func.count()).select_from(control_requests).where(control_requests.c.status == ControlRequestStatus.PENDING)
            ).scalar_one()
        return int(row)

    async def count_active_cooldowns(self, now: datetime) -> int:
        return await asyncio.to_thread(self._count_active_cooldowns_sync, now)

    def _count_active_cooldowns_sync(self, now: datetime) -> int:
        with self._engine.begin() as connection:
            row = connection.execute(select(func.count()).select_from(cooldowns).where(cooldowns.c.until_at > now)).scalar_one()
        return int(row)

    async def list_directory_gap_summaries(
        self,
        library_root: Path | None = None,
    ) -> list[DirectoryGapSummary]:
        return await asyncio.to_thread(self._list_directory_gap_summaries_sync, library_root)

    def _list_directory_gap_summaries_sync(
        self,
        library_root: Path | None,
    ) -> list[DirectoryGapSummary]:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            snapshot_query = select(track_snapshots).where(track_snapshots.c.deleted_at.is_(None))
            if library_root is not None:
                snapshot_query = snapshot_query.where(track_snapshots.c.library_root == str(library_root))
            snapshot_rows = connection.execute(snapshot_query).mappings().all()
            if not snapshot_rows:
                return []

            media_paths = [str(row["media_path"]) for row in snapshot_rows]
            lookup_keys = sorted({str(row["normalized_lookup_key"]) for row in snapshot_rows})

            job_rows = (
                connection.execute(
                    select(
                        jobs.c.media_path,
                        jobs.c.state,
                    ).where(jobs.c.media_path.in_(media_paths))
                )
                .mappings()
                .all()
            )
            provenance_rows = (
                connection.execute(
                    select(
                        provenance.c.media_path,
                        provenance.c.manual_diverged,
                    ).where(provenance.c.media_path.in_(media_paths))
                )
                .mappings()
                .all()
            )
            cooldown_rows = (
                connection.execute(
                    select(cooldowns.c.lookup_key).where(
                        cooldowns.c.lookup_key.in_(lookup_keys),
                        cooldowns.c.until_at > now,
                    )
                )
                .mappings()
                .all()
            )

        jobs_by_media = {str(row["media_path"]): str(row["state"]) for row in job_rows}
        manual_diverged_by_media = {str(row["media_path"]): bool(row["manual_diverged"]) for row in provenance_rows}
        active_cooldowns = {str(row["lookup_key"]) for row in cooldown_rows}

        summaries: dict[tuple[str, str], dict[str, Any]] = {}
        for row in snapshot_rows:
            row_library_root = Path(str(row["library_root"]))
            media_path = Path(str(row["media_path"]))
            directory_path = media_path.parent
            key = (str(row_library_root), str(directory_path))
            summary = summaries.setdefault(
                key,
                {
                    "library_root": row_library_root,
                    "directory_path": directory_path,
                    "total_tracks": 0,
                    "tracks_with_lyrics": 0,
                    "tracks_missing_lyrics": 0,
                    "pending_jobs": 0,
                    "processing_jobs": 0,
                    "failed_jobs": 0,
                    "active_cooldowns": 0,
                    "manual_diverged": 0,
                },
            )
            summary["total_tracks"] += 1

            has_lyrics = bool(row["sidecar_exists"]) or bool(row["embedded_exists"])
            if has_lyrics:
                summary["tracks_with_lyrics"] += 1
            else:
                summary["tracks_missing_lyrics"] += 1
                job_state = jobs_by_media.get(str(media_path))
                if job_state == JobState.PENDING:
                    summary["pending_jobs"] += 1
                elif job_state == JobState.PROCESSING:
                    summary["processing_jobs"] += 1
                elif job_state == JobState.FAILED:
                    summary["failed_jobs"] += 1
                if str(row["normalized_lookup_key"]) in active_cooldowns:
                    summary["active_cooldowns"] += 1

            if manual_diverged_by_media.get(str(media_path), False):
                summary["manual_diverged"] += 1

        return [
            DirectoryGapSummary(
                library_root=summary["library_root"],
                directory_path=summary["directory_path"],
                total_tracks=summary["total_tracks"],
                tracks_with_lyrics=summary["tracks_with_lyrics"],
                tracks_missing_lyrics=summary["tracks_missing_lyrics"],
                pending_jobs=summary["pending_jobs"],
                processing_jobs=summary["processing_jobs"],
                failed_jobs=summary["failed_jobs"],
                active_cooldowns=summary["active_cooldowns"],
                manual_diverged=summary["manual_diverged"],
            )
            for summary in sorted(
                summaries.values(),
                key=lambda item: (
                    str(item["library_root"]),
                    str(item["directory_path"]),
                ),
            )
        ]

    def _record_scan_state_sync(
        self,
        library_root: Path,
        scan_kind: str,
        started_at: datetime | None,
        completed_at: datetime | None,
        status: str | None,
        error_code: str | None,
    ) -> None:
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(scan_state).where(
                    and_(
                        scan_state.c.library_root == str(library_root),
                        scan_state.c.scan_kind == scan_kind,
                    )
                )
            ).first()
            values: dict[str, Any] = {
                "library_root": str(library_root),
                "scan_kind": scan_kind,
                "last_started_at": started_at,
                "last_completed_at": completed_at,
                "last_status": status,
                "last_error_code": error_code,
            }
            if existing is None:
                connection.execute(insert(scan_state).values(**values))
            else:
                connection.execute(
                    update(scan_state)
                    .where(
                        and_(
                            scan_state.c.library_root == str(library_root),
                            scan_state.c.scan_kind == scan_kind,
                        )
                    )
                    .values(**{key: value for key, value in values.items() if value is not None or key in {"last_status", "last_error_code"}})
                )


def _row_to_job(row: RowMapping | dict[str, Any]) -> EnrichmentJob:
    return EnrichmentJob(
        job_key=str(row["job_key"]),
        library_root=Path(str(row["library_root"])),
        media_path=Path(str(row["media_path"])),
        trigger=TriggerKind(str(row["trigger"])),
        priority=JobPriority(str(row["priority"])),
        state=JobState(str(row["state"])),
        attempt_count=int(row["attempt_count"]),
        next_attempt_at=row["next_attempt_at"],
        lease_until=row["lease_until"],
        dirty=bool(row["dirty"]),
        force=bool(row["force"]),
        overwrite_existing=bool(row["overwrite_existing"]),
        allow_manual_overwrite=bool(row["allow_manual_overwrite"]),
        last_reason_code=row["last_reason_code"],
    )


def _row_to_snapshot(row: RowMapping) -> SnapshotStateRecord:
    return SnapshotStateRecord(
        media_path=Path(str(row["media_path"])),
        library_root=Path(str(row["library_root"])),
        extension=str(row["extension"]),
        file_size=int(row["file_size"]),
        file_mtime_ns=int(row["file_mtime_ns"]),
        meaningful_state_hash=str(row["meaningful_state_hash"]),
        normalized_lookup_key=str(row["normalized_lookup_key"]),
        duration_seconds=row["duration_seconds"],
        embedded_exists=bool(row["embedded_exists"]),
        sidecar_exists=bool(row["sidecar_exists"]),
        last_seen_at=row["last_seen_at"],
        deleted_at=row["deleted_at"],
    )


def _row_to_provenance(row: RowMapping) -> ProvenanceRecord:
    return ProvenanceRecord(
        media_path=Path(str(row["media_path"])),
        sidecar_path=Path(str(row["sidecar_path"])),
        artifact_type=str(row["artifact_type"]),
        normalized_lyrics_hash=str(row["normalized_lyrics_hash"]),
        provider_name=str(row["provider_name"]),
        provider_track_id=row["provider_track_id"],
        synced=bool(row["synced"]),
        last_written_at=row["last_written_at"],
        manual_diverged=bool(row["manual_diverged"]),
        sidecar_deleted=bool(row["sidecar_deleted"]),
        conflict_marker=row["conflict_marker"],
    )


def _row_to_control_request(row: RowMapping) -> ControlRequest:
    return ControlRequest(
        request_type=ControlRequestType(str(row["request_type"])),
        target_root=Path(str(row["target_root"])) if row["target_root"] else None,
        target_path=Path(str(row["target_path"])) if row["target_path"] else None,
        force=bool(row["force"]),
        overwrite_existing=bool(row["overwrite_existing"]),
        allow_manual_overwrite=bool(row["allow_manual_overwrite"]),
        requested_at=row["requested_at"],
        status=ControlRequestStatus(str(row["status"])),
    )
