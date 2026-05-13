from __future__ import annotations

from enum import StrEnum


class TriggerKind(StrEnum):
    WATCHER = "watcher"
    RECONCILIATION = "reconciliation"
    STARTUP = "startup"
    MANUAL_RESCAN = "manual_rescan"
    FORCE_RESCAN = "force_rescan"


class JobPriority(StrEnum):
    FORCE_MANUAL = "force_manual"
    MANUAL = "manual"
    WATCHER = "watcher"
    RECONCILIATION = "reconciliation"


class JobState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderStatus(StrEnum):
    MATCHED = "matched"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    INVALID_CONTENT = "invalid_content"
    TRANSIENT_FAILURE = "transient_failure"


class ProcessingCategory(StrEnum):
    WRITTEN = "written"
    PRESERVED = "preserved"
    RETRY = "retry"
    TERMINAL = "terminal"
    NOOP = "noop"


class RetryClassification(StrEnum):
    FILE_TRANSIENT = "file_transient"
    PROVIDER_TRANSIENT = "provider_transient"
    NONE = "none"


class ControlRequestType(StrEnum):
    RESCAN_PATH = "rescan_path"
    FULL_SCAN = "full_scan"


class ControlRequestStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanKind(StrEnum):
    STARTUP = "startup"
    RECONCILIATION = "reconciliation"

