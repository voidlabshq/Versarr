from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .enums import (
    ControlRequestStatus,
    ControlRequestType,
    JobPriority,
    JobState,
    ProcessingCategory,
    ProviderStatus,
    RetryClassification,
    TriggerKind,
)
from .normalization import normalize_lookup_text


@dataclass(frozen=True, slots=True)
class TrackIdentity:
    title: str
    artist: str
    album: str | None
    album_artist: str | None
    track_number: int | None
    disc_number: int | None
    duration_seconds: int | None
    release_year: int | None
    musicbrainz_ids: tuple[str, ...] = ()
    isrc: str | None = None
    normalized_lookup_key: str = field(init=False)

    def __post_init__(self) -> None:
        lookup_parts = [self.artist, self.title]
        if self.album:
            lookup_parts.append(self.album)
        object.__setattr__(
            self,
            "normalized_lookup_key",
            normalize_lookup_text(" ".join(part for part in lookup_parts if part)),
        )


@dataclass(frozen=True, slots=True)
class LyricsPresence:
    sidecar_exists: bool
    sidecar_path: Path | None
    embedded_exists: bool
    conflict_state: str | None = None

    def __post_init__(self) -> None:
        if self.sidecar_exists and self.sidecar_path is None:
            msg = "sidecar_path is required when sidecar_exists is true"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    library_root: Path
    media_path: Path
    extension: str
    file_size: int
    file_mtime_ns: int
    identity: TrackIdentity
    lyrics_presence: LyricsPresence
    meaningful_state_hash: str


@dataclass(frozen=True, slots=True)
class SnapshotStateRecord:
    media_path: Path
    library_root: Path
    extension: str
    file_size: int
    file_mtime_ns: int
    meaningful_state_hash: str
    normalized_lookup_key: str
    duration_seconds: int | None
    embedded_exists: bool
    sidecar_exists: bool
    last_seen_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class DirectoryGapSummary:
    library_root: Path
    directory_path: Path
    total_tracks: int
    tracks_with_lyrics: int
    tracks_missing_lyrics: int
    pending_jobs: int
    processing_jobs: int
    failed_jobs: int
    active_cooldowns: int
    manual_diverged: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    status: ProviderStatus
    provider_name: str
    lyrics_text: str | None
    synced: bool
    provider_track_id: str | None
    confidence: float
    matched_identity: TrackIdentity | None = None
    raw_metadata_digest: str | None = None

    def __post_init__(self) -> None:
        if self.status == ProviderStatus.MATCHED and not self.lyrics_text:
            msg = "matched provider result requires lyrics_text"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    classification: RetryClassification
    next_attempt_at: datetime | None
    max_attempts_reached: bool = False

    def __post_init__(self) -> None:
        if self.classification == RetryClassification.NONE and self.next_attempt_at is not None:
            msg = "terminal retry decisions cannot schedule next_attempt_at"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    category: ProcessingCategory
    reason_code: str
    retry_decision: RetryDecision
    wrote_sidecar: bool
    preserved_existing: bool
    provider_status: ProviderStatus | None
    metrics_labels: dict[str, str]


@dataclass(slots=True)
class EnrichmentJob:
    job_key: str
    library_root: Path
    media_path: Path
    trigger: TriggerKind
    priority: JobPriority
    state: JobState
    attempt_count: int
    next_attempt_at: datetime | None
    lease_until: datetime | None
    dirty: bool
    force: bool
    overwrite_existing: bool
    allow_manual_overwrite: bool
    last_reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    media_path: Path
    sidecar_path: Path
    artifact_type: str
    normalized_lyrics_hash: str
    provider_name: str
    provider_track_id: str | None
    synced: bool
    last_written_at: datetime
    manual_diverged: bool
    sidecar_deleted: bool
    conflict_marker: str | None


@dataclass(slots=True)
class FileStabilityState:
    candidate_path: Path
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_size: int | None = None
    last_mtime_ns: int | None = None
    successful_probes: int = 0


@dataclass(slots=True)
class ControlRequest:
    request_type: ControlRequestType
    target_root: Path | None
    target_path: Path | None
    force: bool
    overwrite_existing: bool
    allow_manual_overwrite: bool
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: ControlRequestStatus = ControlRequestStatus.PENDING
