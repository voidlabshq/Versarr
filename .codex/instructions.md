# Codex Repository Instructions

Authoritative global execution contract for engineering agents working on Versarr.

## Project

Repository:

voidlabshq/Versarr

Summary:

Self-hosted Python lyrics enrichment daemon.

Primary stack:

- Python
- FastAPI
- SQLite
- Alembic
- watchdog
- Docker
- GitHub Actions
- GHCR

---

## Architectural invariants

Hard constraints unless explicitly overridden:

- `.lrc` sidecars are authoritative
- embedded lyrics writing is out of current scope
- SQLite stores process-derived state only
- prefer architectural stability over speculative redesign

Do not redesign architecture casually.

---

## Skill routing

Load relevant skills by task type.

Issue triage / ownership / project tracking:

`.codex/skills/github-issue-lifecycle.md`

Implementation work:

`.codex/skills/implementation-workflow.md`

Pull request publication / merge workflow:

`.codex/skills/pull-request-workflow.md`

CI failure remediation:

`.codex/skills/ci-remediation.md`

GitHub Actions workflow authoring:

`.codex/skills/ci-workflow-changes.md`

If multiple skills are relevant:

load all relevant skills while preserving strict scope discipline.

---

## Universal execution rules

Prefer issue-driven work.

If an issue exists:

inspect it before implementation.

Do not implement from issue title alone.

One logical concern per execution batch.

Never widen scope implicitly.

Prefer minimal deterministic changes.

Avoid speculative refactors.

Avoid opportunistic cleanup.

Avoid dependency churn unless explicitly required.

Do not silently change runtime behavior unless scope requires it.

---

## Validation rules

Validation must be proportional to risk.

Default validation when applicable:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

Do not over-validate trivial changes.

Do not under-validate risky changes.

---

## Command discipline

Do not invent repository tooling.

Repository operations may use supported integrations or shell tooling, provided repository conventions are preserved.

Do not assume undocumented helper scripts exist.

Commands should be directly executable.

---

## Git discipline

Do not work directly on `main` unless explicitly instructed.

Do not merge failing CI.

Prefer squash merge.

---

## Communication contract

Be:

- concise
- technical
- explicit
- evidence-driven

State uncertainty clearly.

Recommend one preferred approach when multiple valid options exist.
