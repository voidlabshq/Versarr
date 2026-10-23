from __future__ import annotations

from dataclasses import replace

import pytest

from versarr.application.job_policy import JobAction, JobDecision, JobFacts, decide

# A track with no lyrics anywhere and no history: the baseline that should be looked up.
_FRESH = JobFacts(
    sidecar_exists=False,
    embedded_exists=False,
    has_provenance=False,
    provenance_sidecar_deleted=False,
    provenance_hash_matches_sidecar=False,
    cooldown_active=False,
    attempt_count=1,
    force=False,
    overwrite_existing=False,
    allow_manual_overwrite=False,
)

_OWNED_SIDECAR = replace(_FRESH, sidecar_exists=True, has_provenance=True, provenance_hash_matches_sidecar=True)
_EDITED_SIDECAR = replace(_OWNED_SIDECAR, provenance_hash_matches_sidecar=False)


def _case(name: str, facts: JobFacts, action: JobAction, reason: str, **flags: bool) -> pytest.param:
    return pytest.param(facts, JobDecision(action, reason, **flags), id=name)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        _case("fresh_track_is_looked_up", _FRESH, JobAction.FETCH, "lookup"),
        _case("cooldown_skips_lookup", replace(_FRESH, cooldown_active=True), JobAction.NOOP, "cooldown_active"),
        _case("force_ignores_cooldown", replace(_FRESH, cooldown_active=True, force=True), JobAction.FETCH, "lookup"),
        _case(
            "embedded_lyrics_are_preserved",
            replace(_FRESH, embedded_exists=True),
            JobAction.PRESERVE,
            "existing_embedded_lyrics_preserved",
            count_embedded_preserved=True,
        ),
        _case(
            "unknown_sidecar_is_preserved_on_first_attempt",
            replace(_FRESH, sidecar_exists=True),
            JobAction.PRESERVE,
            "existing_sidecar_preserved",
        ),
        _case(
            "unknown_sidecar_next_to_embedded_counts_a_conflict",
            replace(_FRESH, sidecar_exists=True, embedded_exists=True),
            JobAction.PRESERVE,
            "existing_sidecar_preserved",
            count_sidecar_conflict=True,
        ),
        _case(
            "unknown_sidecar_on_retry_repairs_provenance_even_in_cooldown",
            replace(_FRESH, sidecar_exists=True, attempt_count=2, cooldown_active=True),
            JobAction.FETCH,
            "lookup",
            repair_missing_provenance=True,
        ),
        _case("owned_sidecar_is_preserved", _OWNED_SIDECAR, JobAction.PRESERVE, "existing_sidecar_preserved"),
        _case(
            "force_alone_does_not_overwrite_owned_sidecar",
            replace(_OWNED_SIDECAR, force=True),
            JobAction.PRESERVE,
            "existing_sidecar_preserved",
        ),
        _case(
            "force_and_overwrite_replaces_owned_sidecar",
            replace(_OWNED_SIDECAR, force=True, overwrite_existing=True),
            JobAction.FETCH,
            "lookup",
        ),
        _case(
            "manual_edit_is_preserved_and_flagged",
            _EDITED_SIDECAR,
            JobAction.PRESERVE,
            "manual_edit_preserved",
            mark_manual_diverged=True,
        ),
        _case(
            "manual_edit_needs_all_three_flags_to_be_overwritten",
            replace(_EDITED_SIDECAR, force=True, overwrite_existing=True),
            JobAction.PRESERVE,
            "manual_edit_preserved",
            mark_manual_diverged=True,
        ),
        _case(
            "manual_edit_overwritten_with_all_flags_still_records_divergence",
            replace(_EDITED_SIDECAR, force=True, overwrite_existing=True, allow_manual_overwrite=True),
            JobAction.FETCH,
            "lookup",
            mark_manual_diverged=True,
        ),
        _case(
            "deleted_sidecar_is_marked_and_respected",
            replace(_FRESH, has_provenance=True),
            JobAction.PRESERVE,
            "sidecar_deleted_preserved",
            mark_sidecar_deleted=True,
        ),
        _case(
            "already_marked_deleted_sidecar_is_not_marked_again",
            replace(_FRESH, has_provenance=True, provenance_sidecar_deleted=True),
            JobAction.PRESERVE,
            "sidecar_deleted_preserved",
        ),
        _case("force_restores_a_deleted_sidecar", replace(_FRESH, has_provenance=True, force=True), JobAction.FETCH, "lookup"),
    ],
)
def test_decide(facts: JobFacts, expected: JobDecision) -> None:
    assert decide(facts) == expected
