from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine

from versarr.application import (
    ControlRequestService,
    IngestionService,
    JobProcessor,
    ReconciliationService,
    RecoveryService,
)
from versarr.application.resilient_provider import ResilientProvider
from versarr.application.services import SystemClock
from versarr.application.supervision import LoopSupervisor
from versarr.config import Settings
from versarr.domain import (
    ControlRequest,
    ControlRequestType,
    JobPriority,
    ScanKind,
    TriggerKind,
)
from versarr.infrastructure.filesystem import (
    AtomicLrcWriter,
    DebounceStabilityDetector,
    FileLockManager,
    FilesystemScanner,
    MutagenMetadataReader,
    WatchdogFileWatcher,
    is_ignored_temp_file,
    resolve_candidate_media_path,
)
from versarr.infrastructure.persistence import SqliteStateRepository, create_engine, run_migrations
from versarr.infrastructure.provider import LrclibProvider
from versarr.observability import MetricsFacade, RuntimeReadiness, configure_logging, get_logger


@dataclass(slots=True)
class RuntimeStatus:
    readiness: RuntimeReadiness = field(default_factory=RuntimeReadiness)
    healthy: bool = True


class VersarrRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.status = RuntimeStatus()
        self.metrics = MetricsFacade()
        self.clock = SystemClock()
        self.logger = get_logger("runtime")
        self._engine: Engine | None = None
        self._repository: SqliteStateRepository | None = None
        self._lock_manager = FileLockManager(settings.state_dir / "versarr.lock")
        self._scanner = FilesystemScanner()
        self._stability = DebounceStabilityDetector(
            quiet_period_seconds=settings.scan.stability_quiet_period_seconds,
            probe_gap_seconds=settings.scan.stability_probe_gap_seconds,
        )
        self._sidecar_writer = AtomicLrcWriter()
        self._metadata_reader = MutagenMetadataReader()
        self._provider = ResilientProvider(
            LrclibProvider(
                base_url=settings.provider_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                user_agent=settings.provider_user_agent,
                metrics=self.metrics,
            ),
            min_interval_seconds=settings.provider_min_interval_seconds,
            failure_threshold=settings.provider_circuit_failure_threshold,
            open_seconds=settings.provider_circuit_open_seconds,
            max_open_seconds=settings.provider_circuit_max_open_seconds,
            metrics=self.metrics,
            logger=self.logger,
        )
        self._watcher = WatchdogFileWatcher(
            roots=settings.library_roots,
            callback=self._handle_filesystem_event,
        )
        self._stop_event = asyncio.Event()
        self._supervisor = LoopSupervisor(stop_event=self._stop_event, logger=self.logger)
        self._suppression_hashes: dict[Path, str] = {}

    @property
    def repository(self) -> SqliteStateRepository:
        if self._repository is None:
            raise RuntimeError("repository is not initialized")
        return self._repository

    async def start(self) -> None:
        configure_logging(self.settings.log_level)
        self.settings.ensure_directories()
        self.status.readiness.config_loaded = True
        self.metrics.set_readiness(False)

        await self._acquire_lock()
        self.status.readiness.lock_held = True

        run_migrations(self.settings.sqlite_path)
        self.status.readiness.migrations_complete = True

        self._engine = create_engine(self.settings.sqlite_path)
        self._repository = SqliteStateRepository(self._engine)
        self.status.readiness.database_ready = True

        ingestion = IngestionService(self.repository, self.metrics, self.logger)
        reconciliation = ReconciliationService(
            repository=self.repository,
            scanner=self._scanner,
            ingestion=ingestion,
            clock=self.clock,
            metrics=self.metrics,
            revisit_after_seconds=self.settings.scan.revisit_after_seconds,
        )
        self._control_service = ControlRequestService(
            repository=self.repository,
            ingestion=ingestion,
            reconciliation=reconciliation,
            clock=self.clock,
        )
        self._job_processor = JobProcessor(
            repository=self.repository,
            metadata_reader=self._metadata_reader,
            provider=self._provider,
            sidecar_writer=self._sidecar_writer,
            metrics=self.metrics,
            clock=self.clock,
            settings=self.settings,
            remember_written_sidecar=self.remember_sidecar_hash,
        )
        recovery = RecoveryService(
            repository=self.repository,
            clock=self.clock,
            metrics=self.metrics,
            # Lease TTL defines how long ownership lasts; startup recovery adds no extra grace.
            stale_before_seconds=0,
        )
        await recovery.recover_stale_jobs()

        await self._watcher.start()
        self.metrics.watcher_roots_active.set(len(self.settings.library_roots))
        self.status.readiness.discovery_active = True

        if self.settings.scan.startup_reconciliation:
            for root in self.settings.library_roots:
                await reconciliation.scan_root(
                    root,
                    scan_kind=ScanKind.STARTUP,
                    trigger=TriggerKind.STARTUP,
                )

        for index in range(self.settings.worker_concurrency):
            self._spawn_worker(f"worker-{index}")
        self._supervisor.spawn("stability", lambda: self._stability_step(ingestion))
        self._supervisor.spawn("control", self._control_step)
        self._supervisor.spawn("reconciliation", lambda: self._reconciliation_step(reconciliation))
        self._supervisor.spawn("metrics", self._metrics_step)
        self.status.readiness.worker_active = True
        self.metrics.set_readiness(self.status.readiness.ready)

    async def stop(self) -> None:
        self.status.readiness.worker_active = False
        self.status.readiness.discovery_active = False
        self.metrics.set_readiness(False)
        self._stop_event.set()
        await self._watcher.stop()
        await self._supervisor.stop()
        await self._provider.aclose()
        await self._lock_manager.release()
        self.status.readiness.lock_held = False
        self.logger.info("runtime_stopped")

    async def run_scan_once(self) -> None:
        configure_logging(self.settings.log_level)
        self.settings.ensure_directories()
        await self._acquire_lock()
        try:
            run_migrations(self.settings.sqlite_path)
            self._engine = create_engine(self.settings.sqlite_path)
            self._repository = SqliteStateRepository(self._engine)
            self.logger.info(
                "scan_once_started",
                roots=[str(root) for root in self.settings.library_roots],
            )
            ingestion = IngestionService(self.repository, self.metrics, self.logger)
            reconciliation = ReconciliationService(
                repository=self.repository,
                scanner=self._scanner,
                ingestion=ingestion,
                clock=self.clock,
                metrics=self.metrics,
            )
            processor = JobProcessor(
                repository=self.repository,
                metadata_reader=self._metadata_reader,
                provider=self._provider,
                sidecar_writer=self._sidecar_writer,
                metrics=self.metrics,
                clock=self.clock,
                settings=self.settings,
                remember_written_sidecar=self.remember_sidecar_hash,
            )
            for root in self.settings.library_roots:
                await reconciliation.scan_root(
                    root,
                    scan_kind=ScanKind.RECONCILIATION,
                    trigger=TriggerKind.MANUAL_RESCAN,
                    evaluate_all=True,
                )
            processed_jobs = 0
            while await processor.process_next("scan-once"):
                processed_jobs += 1
                await asyncio.sleep(0)
            self.logger.info("scan_once_completed", processed_jobs=processed_jobs)
        finally:
            await self._provider.aclose()
            await self._lock_manager.release()

    async def _acquire_lock(self) -> None:
        try:
            await self._lock_manager.acquire()
        except RuntimeError as error:
            self.logger.error("instance_lock_held", state_dir=str(self.settings.state_dir), detail=str(error))
            raise

    async def enqueue_control_request(
        self,
        request_type: str,
        *,
        target_root: Path | None = None,
        target_path: Path | None = None,
        force: bool = False,
        overwrite_existing: bool = False,
        allow_manual_overwrite: bool = False,
    ) -> None:
        configure_logging(self.settings.log_level)
        self.settings.ensure_directories()
        run_migrations(self.settings.sqlite_path)
        self._engine = create_engine(self.settings.sqlite_path)
        self._repository = SqliteStateRepository(self._engine)
        await self.repository.enqueue_control_request(
            ControlRequest(
                request_type=ControlRequestType(request_type),
                target_root=target_root,
                target_path=target_path,
                force=force,
                overwrite_existing=overwrite_existing,
                allow_manual_overwrite=allow_manual_overwrite,
            )
        )

    def _spawn_worker(self, worker_id: str) -> None:
        async def step() -> None:
            await self._worker_step(worker_id)

        self._supervisor.spawn(worker_id, step)

    @property
    def healthy(self) -> bool:
        return self.status.healthy and self._supervisor.healthy

    async def _worker_step(self, worker_id: str) -> None:
        processed = await self._job_processor.process_next(worker_id)
        if not processed:
            await asyncio.sleep(1)

    async def _stability_step(self, ingestion: IngestionService) -> None:
        ready_paths = await self._stability.poll_ready_paths()
        for media_path in ready_paths:
            library_root = self._match_root(media_path)
            if library_root is None:
                continue
            await ingestion.ingest_candidate(
                library_root=library_root,
                media_path=media_path,
                trigger=TriggerKind.WATCHER,
                priority=JobPriority.WATCHER,
                event_kind="stable",
            )
        await asyncio.sleep(1)

    async def _control_step(self) -> None:
        await self._control_service.drain_once()
        await asyncio.sleep(5)

    async def _reconciliation_step(self, reconciliation: ReconciliationService) -> None:
        await asyncio.sleep(self.settings.scan.reconciliation_interval_seconds)
        first_error: Exception | None = None
        for root in self.settings.library_roots:
            try:
                await reconciliation.scan_root(
                    root,
                    scan_kind=ScanKind.RECONCILIATION,
                    trigger=TriggerKind.RECONCILIATION,
                )
            except Exception as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    async def _metrics_step(self) -> None:
        for state, priority, count in await self.repository.get_queue_depths():
            self.metrics.queue_depth.labels(state=state, priority=priority).set(count)
        pending_requests = await self.repository.count_pending_control_requests()
        active_cooldowns = await self.repository.count_active_cooldowns(self.clock.now())
        self.metrics.control_requests_pending.set(pending_requests)
        self.metrics.cooldowns_active.set(active_cooldowns)
        self.metrics.set_readiness(self.status.readiness.ready and self.healthy)
        await asyncio.sleep(10)

    async def _handle_filesystem_event(self, candidate_path: Path, event_kind: str) -> None:
        self.metrics.watcher_events_total.labels(kind=event_kind).inc()
        if is_ignored_temp_file(candidate_path, self.settings.scan.ignored_temp_patterns):
            return
        media_path = resolve_candidate_media_path(candidate_path)
        if media_path is None:
            return
        if candidate_path.suffix.lower() == ".lrc":
            expected_hash = self._suppression_hashes.get(candidate_path)
            if expected_hash is not None and candidate_path.exists():
                try:
                    actual_hash = await self._sidecar_writer.read_normalized_hash(candidate_path)
                except OSError:
                    actual_hash = None
                if actual_hash == expected_hash:
                    self._suppression_hashes.pop(candidate_path, None)
                    return
        await self._stability.observe(media_path, event_kind)

    def remember_sidecar_hash(self, sidecar_path: Path, normalized_hash: str) -> None:
        self._suppression_hashes[sidecar_path] = normalized_hash

    def _match_root(self, media_path: Path) -> Path | None:
        try:
            resolved_media = media_path.resolve(strict=False)
        except OSError:
            return None
        for root in self.settings.library_roots:
            resolved_root = root.resolve(strict=False)
            if resolved_media == resolved_root or resolved_root in resolved_media.parents:
                return root
        return None


def create_runtime(settings: Settings) -> VersarrRuntime:
    return VersarrRuntime(settings)
