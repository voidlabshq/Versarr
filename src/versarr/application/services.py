from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from versarr.application.contracts import (
    Clock,
    LibraryScanner,
    LyricsProvider,
    MetadataReader,
    SidecarWriter,
    StateRepository,
)
from versarr.application.job_policy import JobAction, JobFacts, decide
from versarr.config import Settings
from versarr.domain import (
    ControlRequestType,
    EnrichmentJob,
    JobPriority,
    JobState,
    ProcessingCategory,
    ProcessingOutcome,
    ProvenanceRecord,
    ProviderResult,
    ProviderStatus,
    ReconciliationRecord,
    RetryClassification,
    RetryDecision,
    ScanKind,
    TriggerKind,
    hash_normalized_lyrics,
    normalize_lyrics_text,
)
from versarr.observability import MetricsFacade, get_logger


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(slots=True)
class IngestionService:
    repository: StateRepository
    metrics: MetricsFacade
    logger: Any = None

    async def ingest_candidate(
        self,
        *,
        library_root: Path,
        media_path: Path,
        trigger: TriggerKind,
        priority: JobPriority,
        event_kind: str,
        force: bool = False,
        overwrite_existing: bool = False,
        allow_manual_overwrite: bool = False,
    ) -> None:
        await self.repository.enqueue_path(
            library_root=library_root,
            media_path=media_path,
            trigger=trigger,
            priority=priority,
            event_kind=event_kind,
            force=force,
            overwrite_existing=overwrite_existing,
            allow_manual_overwrite=allow_manual_overwrite,
        )
        if self.logger is not None:
            self.logger.info(
                "job_enqueued",
                library_root=str(library_root),
                media_path=str(media_path),
                trigger=trigger,
                priority=priority,
                event_kind=event_kind,
                force=force,
                overwrite_existing=overwrite_existing,
                allow_manual_overwrite=allow_manual_overwrite,
            )
        self.metrics.jobs_enqueued_total.labels(trigger=trigger).inc()


@dataclass(slots=True)
class RecoveryService:
    repository: StateRepository
    clock: Clock
    metrics: MetricsFacade
    stale_before_seconds: int

    async def recover_stale_jobs(self) -> int:
        recovered = await self.repository.recover_stale_jobs(
            self.clock.now(),
            self.stale_before_seconds,
        )
        if recovered:
            self.metrics.startup_recoveries_total.inc(recovered)
        return recovered


@dataclass(slots=True)
class ReconciliationService:
    repository: StateRepository
    scanner: LibraryScanner
    ingestion: IngestionService
    clock: Clock
    metrics: MetricsFacade
    revisit_after_seconds: int = 6 * 60 * 60

    async def scan_root(
        self,
        root: Path,
        scan_kind: ScanKind,
        trigger: TriggerKind,
        *,
        evaluate_all: bool = False,
    ) -> int:
        """Reconcile ``root`` with disk and return how many files were queued for evaluation.

        Unless ``evaluate_all`` is set, only files that need it are queued: new or changed files,
        files whose sidecar appeared or disappeared, and lyric-less files not looked at recently.
        """
        started = perf_counter()
        logger = get_logger(
            "reconciliation",
            root=str(root),
            scan_kind=scan_kind,
            trigger=trigger,
        )
        logger.info("scan_root_started")
        await self.repository.record_scan_start(root, scan_kind, self.clock.now())
        try:
            candidates = await self.scanner.scan(root)
            to_evaluate = candidates
            if not evaluate_all:
                records = await self.repository.list_reconciliation_records(root)
                facts = await asyncio.to_thread(_read_file_facts, candidates)
                now = self.clock.now()
                to_evaluate = [path for path, fact in facts if _needs_evaluation(records.get(path), fact, now, self.revisit_after_seconds)]
            for candidate in to_evaluate:
                await self.ingestion.ingest_candidate(
                    library_root=root,
                    media_path=candidate,
                    trigger=trigger,
                    priority=JobPriority.RECONCILIATION,
                    event_kind=scan_kind,
                )
            removed = 0
            if root.is_dir():
                removed = await self.repository.mark_missing_snapshots_deleted(root, candidates, self.clock.now())
            await self.repository.record_scan_finish(root, scan_kind, self.clock.now(), "ok")
            logger.info("scan_root_completed", candidates=len(candidates), enqueued=len(to_evaluate), removed=removed)
            return len(to_evaluate)
        except Exception as error:
            await self.repository.record_scan_finish(
                root,
                scan_kind,
                self.clock.now(),
                "failed",
                type(error).__name__,
            )
            logger.exception("scan_root_failed", error_class=type(error).__name__)
            raise
        finally:
            self.metrics.scan_duration_seconds.labels(kind=scan_kind).observe(perf_counter() - started)


@dataclass(frozen=True, slots=True)
class _FileFacts:
    size: int
    mtime_ns: int
    sidecar_exists: bool


def _read_file_facts(paths: list[Path]) -> list[tuple[Path, _FileFacts]]:
    facts: list[tuple[Path, _FileFacts]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        facts.append((path, _FileFacts(stat.st_size, stat.st_mtime_ns, path.with_suffix(".lrc").is_file())))
    return facts


def _needs_evaluation(
    record: ReconciliationRecord | None,
    facts: _FileFacts,
    now: datetime,
    revisit_after_seconds: int,
) -> bool:
    if record is None or record.deleted or record.job_state is None:
        return True
    if record.file_size != facts.size or record.file_mtime_ns != facts.mtime_ns:
        return True
    if record.sidecar_exists != facts.sidecar_exists:
        return True
    if record.job_state in {JobState.PENDING, JobState.PROCESSING}:
        return False
    if record.has_lyrics:
        return False
    # Lyric-less files are looked at again once the last evaluation is old enough (cooldowns, failures).
    if record.job_updated_at is None:
        return True
    return now - record.job_updated_at >= timedelta(seconds=revisit_after_seconds)


@dataclass(slots=True)
class ControlRequestService:
    repository: StateRepository
    ingestion: IngestionService
    reconciliation: ReconciliationService
    clock: Clock

    async def drain_once(self) -> int:
        drained = 0
        for request_id, request in await self.repository.poll_control_requests():
            claimed = await self.repository.claim_control_request(request_id, self.clock.now())
            if not claimed:
                continue
            drained += 1
            try:
                if request.request_type == ControlRequestType.FULL_SCAN:
                    if request.target_root is None:
                        raise ValueError("full scan request requires target_root")
                    await self.reconciliation.scan_root(
                        request.target_root,
                        ScanKind.RECONCILIATION,
                        TriggerKind.FORCE_RESCAN if request.force else TriggerKind.MANUAL_RESCAN,
                        evaluate_all=True,
                    )
                else:
                    if request.target_root is None or request.target_path is None:
                        raise ValueError("rescan request requires target_root and target_path")
                    trigger = TriggerKind.FORCE_RESCAN if request.force else TriggerKind.MANUAL_RESCAN
                    priority = JobPriority.FORCE_MANUAL if request.force else JobPriority.MANUAL
                    await self.ingestion.ingest_candidate(
                        library_root=request.target_root,
                        media_path=request.target_path,
                        trigger=trigger,
                        priority=priority,
                        event_kind=request.request_type,
                        force=request.force,
                        overwrite_existing=request.overwrite_existing,
                        allow_manual_overwrite=request.allow_manual_overwrite,
                    )
                await self.repository.complete_control_request(request_id)
            except Exception as error:
                await self.repository.fail_control_request(request_id, type(error).__name__)
        return drained


@dataclass(slots=True)
class JobProcessor:
    repository: StateRepository
    metadata_reader: MetadataReader
    provider: LyricsProvider
    sidecar_writer: SidecarWriter
    metrics: MetricsFacade
    clock: Clock
    settings: Settings
    remember_written_sidecar: Callable[[Path, str], None] | None = None

    async def _heartbeat_loop(self, job: EnrichmentJob) -> None:
        while True:
            await asyncio.sleep(self.settings.retry.heartbeat_seconds)
            await self.repository.heartbeat_job(
                job.job_key,
                self.clock.now() + timedelta(seconds=self.settings.retry.lease_ttl_seconds),
            )

    async def _process_job(self, job: EnrichmentJob, logger: object) -> ProcessingOutcome:
        del logger
        self._ensure_within_root(job.media_path, job.library_root)
        snapshot = await self.metadata_reader.read_snapshot(job.media_path, job.library_root)
        await self.repository.record_snapshot(snapshot)

        provenance = await self.repository.get_provenance(job.media_path)
        sidecar_path = job.media_path.with_suffix(".lrc")
        current_sidecar_hash: str | None = None
        if snapshot.lyrics_presence.sidecar_exists:
            current_sidecar_hash = await self.sidecar_writer.read_normalized_hash(sidecar_path)
        now = self.clock.now()
        cooldown = await self.repository.get_cooldown(snapshot.identity.normalized_lookup_key, "lrclib")

        decision = decide(
            JobFacts(
                sidecar_exists=snapshot.lyrics_presence.sidecar_exists,
                embedded_exists=snapshot.lyrics_presence.embedded_exists,
                has_provenance=provenance is not None,
                provenance_sidecar_deleted=provenance is not None and provenance.sidecar_deleted,
                provenance_hash_matches_sidecar=provenance is not None and current_sidecar_hash == provenance.normalized_lyrics_hash,
                cooldown_active=cooldown is not None and cooldown > now,
                attempt_count=job.attempt_count,
                force=job.force,
                overwrite_existing=job.overwrite_existing,
                allow_manual_overwrite=job.allow_manual_overwrite,
            )
        )
        if decision.mark_sidecar_deleted:
            await self.repository.mark_sidecar_deleted(job.media_path)
        if decision.mark_manual_diverged:
            await self.repository.mark_manual_diverged(job.media_path)
            self.metrics.manual_divergence_total.inc()
        if decision.count_sidecar_conflict:
            self.metrics.sidecar_conflicts_total.inc()
        if decision.count_embedded_preserved:
            self.metrics.embedded_preserved_total.inc()
        if decision.action == JobAction.PRESERVE:
            return _outcome(ProcessingCategory.PRESERVED, decision.reason_code)
        if decision.action == JobAction.NOOP:
            return _outcome(ProcessingCategory.NOOP, decision.reason_code)
        repair_missing_provenance = decision.repair_missing_provenance

        provider_result = await self.provider.fetch(snapshot.identity)
        if provider_result.status == ProviderStatus.THROTTLED:
            delay = timedelta(seconds=provider_result.retry_after_seconds or 1)
            return _outcome(
                ProcessingCategory.DEFERRED,
                "provider_throttled",
                retry_decision=RetryDecision(RetryClassification.PROVIDER_TRANSIENT, now + delay),
                provider_status=provider_result.status,
            )
        if provider_result.status == ProviderStatus.TRANSIENT_FAILURE:
            retry = self._build_retry(
                now,
                job.attempt_count,
                RetryClassification.PROVIDER_TRANSIENT,
            )
            if retry.next_attempt_at is None:
                return _outcome(
                    ProcessingCategory.TERMINAL,
                    "provider_retry_exhausted",
                    provider_status=provider_result.status,
                )
            return _outcome(
                ProcessingCategory.RETRY,
                "provider_transient_failure",
                retry_decision=retry,
                provider_status=provider_result.status,
            )

        if provider_result.status == ProviderStatus.REJECTED:
            return _outcome(
                ProcessingCategory.TERMINAL,
                "provider_request_rejected",
                provider_status=provider_result.status,
            )

        if provider_result.status == ProviderStatus.NOT_FOUND:
            await self.repository.record_cooldown(
                snapshot.identity.normalized_lookup_key,
                provider_result.provider_name,
                provider_result.status,
                now + timedelta(seconds=self.settings.cooldowns.not_found_seconds),
            )
            return _outcome(
                ProcessingCategory.TERMINAL,
                "lyrics_not_found",
                provider_status=provider_result.status,
            )

        if provider_result.status in {ProviderStatus.AMBIGUOUS, ProviderStatus.INVALID_CONTENT}:
            cooldown_seconds = (
                self.settings.cooldowns.ambiguous_seconds
                if provider_result.status == ProviderStatus.AMBIGUOUS
                else self.settings.cooldowns.invalid_content_seconds
            )
            await self.repository.record_cooldown(
                snapshot.identity.normalized_lookup_key,
                provider_result.provider_name,
                provider_result.status,
                now + timedelta(seconds=cooldown_seconds),
            )
            return _outcome(
                ProcessingCategory.TERMINAL,
                "provider_rejected",
                provider_status=provider_result.status,
            )

        if provider_result.lyrics_text is None:
            return _outcome(ProcessingCategory.TERMINAL, "provider_missing_lyrics")

        normalized_lyrics = normalize_lyrics_text(provider_result.lyrics_text)
        normalized_hash = hash_normalized_lyrics(normalized_lyrics)
        if repair_missing_provenance:
            if current_sidecar_hash != normalized_hash:
                return _outcome(ProcessingCategory.PRESERVED, "existing_sidecar_preserved")
            await self.repository.record_provenance(
                _build_provenance_record(
                    media_path=job.media_path,
                    sidecar_path=sidecar_path,
                    normalized_hash=normalized_hash,
                    provider_result=provider_result,
                    written_at=now,
                    embedded_exists=snapshot.lyrics_presence.embedded_exists,
                )
            )
            return _outcome(
                ProcessingCategory.PRESERVED,
                "provenance_repaired",
                provider_status=provider_result.status,
            )

        write_started = perf_counter()
        write_result = await self.sidecar_writer.write(sidecar_path, normalized_lyrics)
        self.metrics.sidecar_write_seconds.observe(perf_counter() - write_started)
        self.metrics.sidecar_writes_total.labels(mode="create" if write_result.created else "replace").inc()
        await self.repository.record_provenance(
            _build_provenance_record(
                media_path=job.media_path,
                sidecar_path=write_result.sidecar_path,
                normalized_hash=write_result.normalized_hash,
                provider_result=provider_result,
                written_at=now,
                embedded_exists=snapshot.lyrics_presence.embedded_exists,
            )
        )
        if self.remember_written_sidecar is not None:
            self.remember_written_sidecar(write_result.sidecar_path, write_result.normalized_hash)
        return _outcome(
            ProcessingCategory.WRITTEN,
            "sidecar_written",
            provider_status=provider_result.status,
            wrote_sidecar=True,
        )

    async def process_next(self, worker_id: str) -> bool:
        job = await self.repository.lease_next_ready_job(
            worker_id,
            self.clock.now(),
            lease_ttl_seconds=self.settings.retry.lease_ttl_seconds,
        )
        if job is None:
            return False
        logger = get_logger(
            "job_processor",
            job_key=job.job_key,
            path=str(job.media_path),
            trigger=job.trigger,
            priority=job.priority,
            attempt=job.attempt_count,
        )
        self.metrics.active_jobs.inc()
        started = perf_counter()
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            logger.info("job_started")
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(job))
            outcome = await self._process_job(job, logger)
            if outcome.category == ProcessingCategory.RETRY and outcome.retry_decision.next_attempt_at is not None:
                self.metrics.jobs_retried_total.labels(classification=outcome.retry_decision.classification).inc()
                await self.repository.retry_job(
                    job.job_key,
                    outcome.reason_code,
                    outcome.retry_decision.classification,
                    outcome.retry_decision.next_attempt_at,
                )
            elif outcome.category == ProcessingCategory.DEFERRED and outcome.retry_decision.next_attempt_at is not None:
                await self.repository.defer_job(job.job_key, outcome.reason_code, outcome.retry_decision.next_attempt_at)
            elif outcome.category == ProcessingCategory.TERMINAL:
                await self.repository.fail_job(job.job_key, outcome.reason_code, "terminal")
            else:
                await self.repository.complete_job(job.job_key, outcome.reason_code)
            self.metrics.jobs_completed_total.labels(
                outcome=outcome.category,
                reason=outcome.reason_code,
            ).inc()
            logger.info(
                "job_processed",
                outcome=outcome.category,
                reason_code=outcome.reason_code,
                provider_status=outcome.provider_status,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return True
        except FileNotFoundError:
            await self.repository.fail_job(job.job_key, "media_missing", "terminal")
            self.metrics.jobs_completed_total.labels(
                outcome=ProcessingCategory.TERMINAL,
                reason="media_missing",
            ).inc()
            return True
        except ValueError as error:
            logger.exception("job_processing_terminal", error_class=type(error).__name__)
            await self.repository.fail_job(
                job.job_key,
                "invalid_media_or_path",
                type(error).__name__,
            )
            self.metrics.jobs_completed_total.labels(
                outcome=ProcessingCategory.TERMINAL,
                reason="invalid_media_or_path",
            ).inc()
            return True
        except OSError as error:
            logger.exception("job_processing_failed", error_class=type(error).__name__)
            await self._retry_or_fail(job, "filesystem_transient", error)
            return True
        except Exception as error:
            logger.exception("job_processing_failed", error_class=type(error).__name__)
            await self._retry_or_fail(job, "unexpected_error", error)
            return True
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
            self.metrics.active_jobs.dec()
            self.metrics.job_duration_seconds.observe(perf_counter() - started)

    async def _retry_or_fail(self, job: EnrichmentJob, reason_code: str, error: Exception) -> None:
        retry = self._build_retry(self.clock.now(), job.attempt_count, RetryClassification.FILE_TRANSIENT)
        if retry.next_attempt_at is None:
            await self.repository.fail_job(job.job_key, f"{reason_code}_retry_exhausted", type(error).__name__)
            self.metrics.jobs_completed_total.labels(
                outcome=ProcessingCategory.TERMINAL,
                reason=f"{reason_code}_retry_exhausted",
            ).inc()
            return
        await self.repository.retry_job(job.job_key, reason_code, type(error).__name__, retry.next_attempt_at)
        self.metrics.jobs_retried_total.labels(classification=RetryClassification.FILE_TRANSIENT).inc()

    def _build_retry(self, now: datetime, attempt_count: int, classification: RetryClassification) -> RetryDecision:
        if classification == RetryClassification.PROVIDER_TRANSIENT:
            window = self.settings.retry.provider_transient
        else:
            window = self.settings.retry.file_unstable
        if attempt_count >= window.max_attempts:
            return RetryDecision(RetryClassification.NONE, None, max_attempts_reached=True)
        delay_seconds = min(
            window.initial_seconds * (2 ** max(attempt_count - 1, 0)),
            window.max_seconds,
        )
        if classification == RetryClassification.PROVIDER_TRANSIENT:
            # Spread retries so jobs that failed together do not hit the provider together.
            delay_seconds = min(delay_seconds * random.uniform(0.9, 1.1), window.max_seconds)
        return RetryDecision(classification, now + timedelta(seconds=delay_seconds))

    def _ensure_within_root(self, media_path: Path, library_root: Path) -> None:
        resolved_root = library_root.resolve(strict=True)
        resolved_media = media_path.resolve(strict=True)
        if resolved_media != resolved_root and resolved_root not in resolved_media.parents:
            msg = "media path resolves outside configured library root"
            raise ValueError(msg)


def _outcome(
    category: ProcessingCategory,
    reason_code: str,
    *,
    retry_decision: RetryDecision | None = None,
    wrote_sidecar: bool = False,
    preserved_existing: bool = False,
    provider_status: ProviderStatus | None = None,
) -> ProcessingOutcome:
    retry = retry_decision or RetryDecision(RetryClassification.NONE, None)
    return ProcessingOutcome(
        category=category,
        reason_code=reason_code,
        retry_decision=retry,
        wrote_sidecar=wrote_sidecar,
        preserved_existing=preserved_existing,
        provider_status=provider_status,
        metrics_labels={
            "outcome": str(category),
            "reason": reason_code,
        },
    )


def _build_provenance_record(
    *,
    media_path: Path,
    sidecar_path: Path,
    normalized_hash: str,
    provider_result: ProviderResult,
    written_at: datetime,
    embedded_exists: bool,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        media_path=media_path,
        sidecar_path=sidecar_path,
        artifact_type="lrc",
        normalized_lyrics_hash=normalized_hash,
        provider_name=provider_result.provider_name,
        provider_track_id=provider_result.provider_track_id,
        synced=provider_result.synced,
        last_written_at=written_at,
        manual_diverged=False,
        sidecar_deleted=False,
        conflict_marker="embedded_present" if embedded_exists else None,
    )
