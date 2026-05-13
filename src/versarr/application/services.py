from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Callable

from versarr.application.contracts import (
    Clock,
    LibraryScanner,
    LyricsProvider,
    MetadataReader,
    SidecarWriter,
    StateRepository,
)
from versarr.config import Settings
from versarr.domain import (
    ControlRequestType,
    EnrichmentJob,
    JobPriority,
    ProcessingCategory,
    ProcessingOutcome,
    ProviderStatus,
    ProvenanceRecord,
    RetryClassification,
    RetryDecision,
    ScanKind,
    TriggerKind,
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
        self.metrics.jobs_enqueued_total.labels(trigger=trigger).inc()


@dataclass(slots=True)
class RecoveryService:
    repository: StateRepository
    clock: Clock
    metrics: MetricsFacade
    stale_before_seconds: int

    async def recover_stale_jobs(self) -> int:
        recovered = await self.repository.recover_stale_jobs(self.clock.now(), self.stale_before_seconds)
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

    async def scan_root(self, root: Path, scan_kind: ScanKind, trigger: TriggerKind) -> int:
        started = perf_counter()
        await self.repository.record_scan_start(root, scan_kind, self.clock.now())
        try:
            candidates = await self.scanner.scan(root)
            for candidate in candidates:
                await self.ingestion.ingest_candidate(
                    library_root=root,
                    media_path=candidate,
                    trigger=trigger,
                    priority=JobPriority.RECONCILIATION,
                    event_kind=scan_kind,
                )
            await self.repository.record_scan_finish(root, scan_kind, self.clock.now(), "ok")
            return len(candidates)
        except Exception as error:
            await self.repository.record_scan_finish(root, scan_kind, self.clock.now(), "failed", type(error).__name__)
            raise
        finally:
            self.metrics.scan_duration_seconds.labels(kind=scan_kind).observe(perf_counter() - started)


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
                    )
                else:
                    if request.target_root is None or request.target_path is None:
                        raise ValueError("rescan request requires target_root and target_path")
                    await self.ingestion.ingest_candidate(
                        library_root=request.target_root,
                        media_path=request.target_path,
                        trigger=TriggerKind.FORCE_RESCAN if request.force else TriggerKind.MANUAL_RESCAN,
                        priority=JobPriority.FORCE_MANUAL if request.force else JobPriority.MANUAL,
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

    async def _process_job(self, job: EnrichmentJob, logger: object) -> ProcessingOutcome:
        del logger
        self._ensure_within_root(job.media_path, job.library_root)
        snapshot = await self.metadata_reader.read_snapshot(job.media_path, job.library_root)
        previous_snapshot = await self.repository.get_snapshot(job.media_path)
        await self.repository.record_snapshot(snapshot)

        provenance = await self.repository.get_provenance(job.media_path)
        sidecar_path = job.media_path.with_suffix(".lrc")
        if not snapshot.lyrics_presence.sidecar_exists and provenance is not None and provenance.sidecar_deleted and not job.force:
            return _outcome(ProcessingCategory.PRESERVED, "sidecar_deleted_preserved")
        if not snapshot.lyrics_presence.sidecar_exists and provenance is not None and not provenance.sidecar_deleted and not job.force:
            await self.repository.mark_sidecar_deleted(job.media_path)
            return _outcome(ProcessingCategory.PRESERVED, "sidecar_deleted_preserved")

        if snapshot.lyrics_presence.sidecar_exists:
            current_hash = await self.sidecar_writer.read_normalized_hash(sidecar_path)
            if provenance is None:
                if snapshot.lyrics_presence.embedded_exists:
                    self.metrics.sidecar_conflicts_total.inc()
                return _outcome(ProcessingCategory.PRESERVED, "existing_sidecar_preserved")
            if current_hash != provenance.normalized_lyrics_hash:
                await self.repository.mark_manual_diverged(job.media_path)
                self.metrics.manual_divergence_total.inc()
                if not (job.force and job.overwrite_existing and job.allow_manual_overwrite):
                    return _outcome(ProcessingCategory.PRESERVED, "manual_edit_preserved")
            elif not (job.force and job.overwrite_existing):
                return _outcome(ProcessingCategory.PRESERVED, "existing_sidecar_preserved")

        if not snapshot.lyrics_presence.sidecar_exists and snapshot.lyrics_presence.embedded_exists:
            self.metrics.embedded_preserved_total.inc()
            return _outcome(ProcessingCategory.PRESERVED, "existing_embedded_lyrics_preserved")

        if previous_snapshot is not None and previous_snapshot.meaningful_state_hash == snapshot.meaningful_state_hash and not job.force:
            return _outcome(ProcessingCategory.NOOP, "no_meaningful_change")

        cooldown = await self.repository.get_cooldown(snapshot.identity.normalized_lookup_key, "lrclib")
        now = self.clock.now()
        if cooldown is not None and cooldown > now and not job.force:
            return _outcome(ProcessingCategory.NOOP, "cooldown_active")

        provider_result = await self.provider.fetch(snapshot.identity)
        if provider_result.status == ProviderStatus.TRANSIENT_FAILURE:
            retry = self._build_retry(now, job.attempt_count, RetryClassification.PROVIDER_TRANSIENT)
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

        if provider_result.status == ProviderStatus.NOT_FOUND:
            await self.repository.record_cooldown(
                snapshot.identity.normalized_lookup_key,
                provider_result.provider_name,
                provider_result.status,
                now + timedelta(seconds=self.settings.cooldowns.not_found_seconds),
            )
            return _outcome(ProcessingCategory.TERMINAL, "lyrics_not_found", provider_status=provider_result.status)

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
        write_started = perf_counter()
        write_result = await self.sidecar_writer.write(sidecar_path, normalized_lyrics)
        self.metrics.sidecar_write_seconds.observe(perf_counter() - write_started)
        self.metrics.sidecar_writes_total.labels(
            mode="create" if write_result.created else "replace"
        ).inc()
        await self.repository.record_provenance(
            ProvenanceRecord(
                media_path=job.media_path,
                sidecar_path=write_result.sidecar_path,
                artifact_type="lrc",
                normalized_lyrics_hash=write_result.normalized_hash,
                provider_name=provider_result.provider_name,
                provider_track_id=provider_result.provider_track_id,
                synced=provider_result.synced,
                last_written_at=now,
                manual_diverged=False,
                sidecar_deleted=False,
                conflict_marker="embedded_present"
                if snapshot.lyrics_presence.embedded_exists
                else None,
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
        job = await self.repository.lease_next_ready_job(worker_id, self.clock.now())
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
        try:
            outcome = await self._process_job(job, logger)
            if outcome.category == ProcessingCategory.RETRY and outcome.retry_decision.next_attempt_at is not None:
                self.metrics.jobs_retried_total.labels(
                    classification=outcome.retry_decision.classification
                ).inc()
                await self.repository.retry_job(
                    job.job_key,
                    outcome.reason_code,
                    outcome.retry_decision.classification,
                    outcome.retry_decision.next_attempt_at,
                )
            elif outcome.category == ProcessingCategory.TERMINAL:
                await self.repository.fail_job(job.job_key, outcome.reason_code, "terminal")
            else:
                await self.repository.complete_job(job.job_key, outcome.reason_code)
            self.metrics.jobs_completed_total.labels(outcome=outcome.category, reason=outcome.reason_code).inc()
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
            self.metrics.jobs_completed_total.labels(outcome=ProcessingCategory.TERMINAL, reason="media_missing").inc()
            return True
        except ValueError as error:
            logger.exception("job_processing_terminal", error_class=type(error).__name__)
            await self.repository.fail_job(job.job_key, "invalid_media_or_path", type(error).__name__)
            self.metrics.jobs_completed_total.labels(
                outcome=ProcessingCategory.TERMINAL,
                reason="invalid_media_or_path",
            ).inc()
            return True
        except OSError as error:
            logger.exception("job_processing_failed", error_class=type(error).__name__)
            next_attempt = self.clock.now() + timedelta(seconds=self.settings.retry.file_unstable.initial_seconds)
            await self.repository.retry_job(job.job_key, "filesystem_transient", type(error).__name__, next_attempt)
            self.metrics.jobs_retried_total.labels(classification=RetryClassification.FILE_TRANSIENT).inc()
            return True
        except Exception as error:
            logger.exception("job_processing_failed", error_class=type(error).__name__)
            next_attempt = self.clock.now() + timedelta(seconds=self.settings.retry.file_unstable.initial_seconds)
            await self.repository.retry_job(job.job_key, "unexpected_error", type(error).__name__, next_attempt)
            self.metrics.jobs_retried_total.labels(classification=RetryClassification.FILE_TRANSIENT).inc()
            return True
        finally:
            self.metrics.active_jobs.dec()
            self.metrics.job_duration_seconds.observe(perf_counter() - started)

    def _build_retry(
        self, now: datetime, attempt_count: int, classification: RetryClassification
    ) -> RetryDecision:
        if classification == RetryClassification.PROVIDER_TRANSIENT:
            window = self.settings.retry.provider_transient
        else:
            window = self.settings.retry.file_unstable
        if attempt_count >= window.max_attempts:
            return RetryDecision(RetryClassification.NONE, None, max_attempts_reached=True)
        delay_seconds = min(window.initial_seconds * (2 ** max(attempt_count - 1, 0)), window.max_seconds)
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
