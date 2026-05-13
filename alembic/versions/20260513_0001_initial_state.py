"""initial process state schema

Revision ID: 20260513_0001
Revises:
Create Date: 2026-05-13 15:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_key", sa.String(length=512), primary_key=True),
        sa.Column("library_root", sa.Text(), nullable=False),
        sa.Column("media_path", sa.Text(), nullable=False),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dirty", sa.Boolean(), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("overwrite_existing", sa.Boolean(), nullable=False),
        sa.Column("allow_manual_overwrite", sa.Boolean(), nullable=False),
        sa.Column("last_reason_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_class", sa.String(length=128), nullable=True),
        sa.Column("last_event_kind", sa.String(length=64), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_state_next_priority", "jobs", ["state", "next_attempt_at", "priority"])
    op.create_index("ix_jobs_lease_until", "jobs", ["lease_until"])

    op.create_table(
        "track_snapshots",
        sa.Column("media_path", sa.Text(), primary_key=True),
        sa.Column("library_root", sa.Text(), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_mtime_ns", sa.Integer(), nullable=False),
        sa.Column("meaningful_state_hash", sa.String(length=128), nullable=False),
        sa.Column("normalized_lookup_key", sa.String(length=512), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("embedded_exists", sa.Boolean(), nullable=False),
        sa.Column("sidecar_exists", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_track_snapshots_root_seen",
        "track_snapshots",
        ["library_root", "last_seen_at"],
    )

    op.create_table(
        "provenance",
        sa.Column("media_path", sa.Text(), primary_key=True),
        sa.Column("sidecar_path", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("normalized_lyrics_hash", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("provider_track_id", sa.String(length=256), nullable=True),
        sa.Column("synced", sa.Boolean(), nullable=False),
        sa.Column("last_written_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manual_diverged", sa.Boolean(), nullable=False),
        sa.Column("sidecar_deleted", sa.Boolean(), nullable=False),
        sa.Column("conflict_marker", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_provenance_manual_diverged", "provenance", ["manual_diverged"])

    op.create_table(
        "cooldowns",
        sa.Column("lookup_key", sa.String(length=512), primary_key=True),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("until_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cooldowns_until", "cooldowns", ["until_at"])

    op.create_table(
        "scan_state",
        sa.Column("library_root", sa.Text(), primary_key=True),
        sa.Column("scan_kind", sa.String(length=64), primary_key=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=64), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "control_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column("target_root", sa.Text(), nullable=True),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("overwrite_existing", sa.Boolean(), nullable=False),
        sa.Column("allow_manual_overwrite", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_control_requests_status_requested",
        "control_requests",
        ["status", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_control_requests_status_requested", table_name="control_requests")
    op.drop_table("control_requests")
    op.drop_table("scan_state")
    op.drop_index("ix_cooldowns_until", table_name="cooldowns")
    op.drop_table("cooldowns")
    op.drop_index("ix_provenance_manual_diverged", table_name="provenance")
    op.drop_table("provenance")
    op.drop_index("ix_track_snapshots_root_seen", table_name="track_snapshots")
    op.drop_table("track_snapshots")
    op.drop_index("ix_jobs_lease_until", table_name="jobs")
    op.drop_index("ix_jobs_state_next_priority", table_name="jobs")
    op.drop_table("jobs")

