# Codex Instructions

Repository-specific execution guidance for Codex and similar engineering agents.

This file supplements AGENTS.md.

---

## Project context

Repository:
Versarr

Summary:
Self-hosted Python lyrics enrichment daemon for music libraries.

Current architecture includes:

- FastAPI
- watchdog filesystem monitoring
- SQLite persistent state
- Alembic migrations
- async workers
- sidecar-first `.lrc` lyrics writing
- Docker deployment
- GitHub Actions CI/CD
- GHCR container publishing

---

## Architectural invariants

These are hard constraints unless explicitly overridden.

- `.lrc` sidecars are authoritative
- embedded lyrics writing is out of MVP scope
- SQLite stores process/process-derived state only
- architecture stability is preferred over novelty

Do not redesign architecture casually.

---

## Working model

Meaningful repository work should preferably be issue-driven.

If no issue exists but the task is clearly scoped:

proceed while preserving scope discipline.

If an issue exists:

inspect it before implementation.

Review:

- description
- acceptance criteria
- linked context
- referenced constraints

---

## Branch discipline

Prefer established repository branch conventions.

Suggested defaults:

- fix/*
- docs/*
- ci/*
- security/*
- feature/*

Do not work directly on main unless explicitly instructed.

Each branch should represent one logical concern.

---

## Pull request discipline

PRs must remain narrowly scoped.

Prefer squash merge for focused isolated work.

Issue references:

Auto-close only when fully resolved:

- Closes #X
- Fixes #X
- Resolves #X

Non-closing references:

- Refs #X
- Related to #X
- Partially addresses #X

Never auto-close unresolved issues.

---

## Implementation workflow

Before implementation:

1. inspect relevant files
2. inspect neighboring tests
3. inspect repository conventions
4. identify minimal change surface
5. identify validation strategy
6. call out notable risks

Then implement.

---

## Debugging workflow

Use evidence-driven debugging.

Required approach:

1. reproduce
2. inspect implementation
3. inspect logs/output
4. identify likely root cause
5. propose minimal fix
6. validate

Do not guess blindly.

If confidence is low:

state uncertainty explicitly.

---

## Testing expectations

Validation should be proportional.

Default project validation when applicable:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

Examples:

docs-only:
minimal validation

focused bugfix:
targeted regression tests

runtime logic:
broader validation

workflow changes:
CI/workflow validation

persistence changes:
migration compatibility validation

release changes:
release workflow validation

Do not over-test trivial changes.

Do not under-test risky changes.

---

## Workflow / CI discipline

Changes under:

`.github/workflows/*`

are high-risk.

Python lint/tests do NOT validate workflow correctness.

When modifying workflows:

- inspect YAML carefully
- preserve explicit permissions
- preserve least privilege
- avoid merge artifact corruption
- validate assumptions

Prefer immutable action pinning where practical.

---

## Release discipline

Do not alter casually:

- versioning strategy
- tag semantics
- publishing workflow
- GHCR assumptions
- release workflow behavior

Release changes require high caution.

---

## Command discipline

Do not assume tooling exists without verification.

Do not invent:

- scripts
- make targets
- automation helpers

If proposing new tooling:

state clearly that it is a proposal.

Commands should be directly executable.

---

## Communication style

Be concise, technical, explicit, and evidence-oriented.

State assumptions.

Call out uncertainty.

If multiple options exist:

recommend one clearly with rationale.