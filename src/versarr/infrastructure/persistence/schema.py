from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

jobs = Table(
    "jobs",
    metadata,
    Column("job_key", String(512), primary_key=True),
    Column("library_root", Text, nullable=False),
    Column("media_path", Text, nullable=False),
    Column("trigger", String(64), nullable=False),
    Column("priority", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
    Column("dirty", Boolean, nullable=False, default=False),
    Column("force", Boolean, nullable=False, default=False),
    Column("overwrite_existing", Boolean, nullable=False, default=False),
    Column("allow_manual_overwrite", Boolean, nullable=False, default=False),
    Column("last_reason_code", String(128), nullable=True),
    Column("last_error_class", String(128), nullable=True),
    Column("last_event_kind", String(64), nullable=True),
    Column("last_event_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

track_snapshots = Table(
    "track_snapshots",
    metadata,
    Column("media_path", Text, primary_key=True),
    Column("library_root", Text, nullable=False),
    Column("extension", String(16), nullable=False),
    Column("file_size", Integer, nullable=False),
    Column("file_mtime_ns", Integer, nullable=False),
    Column("meaningful_state_hash", String(128), nullable=False),
    Column("normalized_lookup_key", String(512), nullable=False),
    Column("duration_seconds", Integer, nullable=True),
    Column("embedded_exists", Boolean, nullable=False),
    Column("sidecar_exists", Boolean, nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

provenance = Table(
    "provenance",
    metadata,
    Column("media_path", Text, primary_key=True),
    Column("sidecar_path", Text, nullable=False),
    Column("artifact_type", String(32), nullable=False),
    Column("normalized_lyrics_hash", String(128), nullable=False),
    Column("provider_name", String(128), nullable=False),
    Column("provider_track_id", String(256), nullable=True),
    Column("synced", Boolean, nullable=False),
    Column("last_written_at", DateTime(timezone=True), nullable=False),
    Column("manual_diverged", Boolean, nullable=False, default=False),
    Column("sidecar_deleted", Boolean, nullable=False, default=False),
    Column("conflict_marker", String(128), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

cooldowns = Table(
    "cooldowns",
    metadata,
    Column("lookup_key", String(512), primary_key=True),
    Column("provider_name", String(128), nullable=False),
    Column("outcome", String(64), nullable=False),
    Column("until_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

scan_state = Table(
    "scan_state",
    metadata,
    Column("library_root", Text, primary_key=True),
    Column("scan_kind", String(64), primary_key=True),
    Column("last_started_at", DateTime(timezone=True), nullable=True),
    Column("last_completed_at", DateTime(timezone=True), nullable=True),
    Column("last_status", String(64), nullable=True),
    Column("last_error_code", String(128), nullable=True),
)

control_requests = Table(
    "control_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_type", String(64), nullable=False),
    Column("target_root", Text, nullable=True),
    Column("target_path", Text, nullable=True),
    Column("force", Boolean, nullable=False, default=False),
    Column("overwrite_existing", Boolean, nullable=False, default=False),
    Column("allow_manual_overwrite", Boolean, nullable=False, default=False),
    Column("status", String(32), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(128), nullable=True),
)

Index("ix_jobs_state_next_priority", jobs.c.state, jobs.c.next_attempt_at, jobs.c.priority)
Index("ix_jobs_lease_until", jobs.c.lease_until)
Index(
    "ix_track_snapshots_root_seen",
    track_snapshots.c.library_root,
    track_snapshots.c.last_seen_at,
)
Index("ix_provenance_manual_diverged", provenance.c.manual_diverged)
Index("ix_cooldowns_until", cooldowns.c.until_at)
Index(
    "ix_control_requests_status_requested",
    control_requests.c.status,
    control_requests.c.requested_at,
)
