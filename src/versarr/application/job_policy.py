from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobAction(StrEnum):
    PRESERVE = "preserve"
    NOOP = "noop"
    FETCH = "fetch"


@dataclass(frozen=True, slots=True)
class JobFacts:
    """Everything the policy needs to know about a track and its job; no I/O happens here."""

    sidecar_exists: bool
    embedded_exists: bool
    has_provenance: bool
    provenance_sidecar_deleted: bool
    provenance_hash_matches_sidecar: bool
    cooldown_active: bool
    attempt_count: int
    force: bool
    overwrite_existing: bool
    allow_manual_overwrite: bool


@dataclass(frozen=True, slots=True)
class JobDecision:
    action: JobAction
    reason_code: str
    repair_missing_provenance: bool = False
    mark_sidecar_deleted: bool = False
    mark_manual_diverged: bool = False
    count_sidecar_conflict: bool = False
    count_embedded_preserved: bool = False


def decide(facts: JobFacts) -> JobDecision:
    """Decide what to do with a track: leave it alone, skip for now, or look lyrics up.

    The ladder protects what users already have (sidecars, manual edits, embedded lyrics) before
    spending a provider request.
    """
    if not facts.sidecar_exists and facts.has_provenance and not facts.force:
        return JobDecision(
            JobAction.PRESERVE,
            "sidecar_deleted_preserved",
            mark_sidecar_deleted=not facts.provenance_sidecar_deleted,
        )

    repair_missing_provenance = False
    mark_manual_diverged = False
    if facts.sidecar_exists:
        if not facts.has_provenance:
            if facts.attempt_count <= 1:
                return JobDecision(
                    JobAction.PRESERVE,
                    "existing_sidecar_preserved",
                    count_sidecar_conflict=facts.embedded_exists,
                )
            repair_missing_provenance = True
        elif not facts.provenance_hash_matches_sidecar:
            mark_manual_diverged = True
            if not (facts.force and facts.overwrite_existing and facts.allow_manual_overwrite):
                return JobDecision(JobAction.PRESERVE, "manual_edit_preserved", mark_manual_diverged=True)
        elif not (facts.force and facts.overwrite_existing):
            return JobDecision(JobAction.PRESERVE, "existing_sidecar_preserved")

    if not facts.sidecar_exists and facts.embedded_exists:
        return JobDecision(JobAction.PRESERVE, "existing_embedded_lyrics_preserved", count_embedded_preserved=True)

    if not repair_missing_provenance and facts.cooldown_active and not facts.force:
        return JobDecision(JobAction.NOOP, "cooldown_active")

    return JobDecision(
        JobAction.FETCH,
        "lookup",
        repair_missing_provenance=repair_missing_provenance,
        mark_manual_diverged=mark_manual_diverged,
    )
