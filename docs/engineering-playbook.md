# Engineering Playbook

This document defines the engineering operating model for Versarr.

It applies to both human contributors and software agents.

---

## Engineering principles

Priority order:

1. correctness
2. release safety
3. operational safety
4. maintainability
5. explicitness
6. contributor clarity
7. OSS maturity
8. implementation speed

Do not optimize for superficial speed.

---

## Issue discipline

Meaningful repository work should preferably be issue-driven.

If a task is explicitly scoped and no issue exists:

work may proceed while preserving scope discipline.

If an issue exists:

review before implementation.

Inspect:

- issue description
- acceptance criteria
- linked discussions
- related constraints
- referenced operational assumptions

Do not implement blindly against issue titles alone.

---

## GitHub Projects discipline

GitHub Projects are the roadmap / tracking layer.

Issues should be associated with the project when meaningful.

Project management exists to preserve backlog visibility.

Do not allow discovered work to become undocumented tribal knowledge.

---

## Label taxonomy

Preferred labels:

### Priority

- `p0` — critical release blocker
- `p1` — high priority
- `p2` — medium priority
- `p3` — backlog / low urgency

### Type

- `bug`
- `security`
- `docs`
- `oss`
- `validation`
- `tech-debt`
- `feature`

### Area

- `core`
- `docker`
- `ci`
- `packaging`

Apply labels intentionally.

---

## Branch discipline

Prefer established repository branch conventions.

Suggested defaults:

- `fix/*`
- `docs/*`
- `ci/*`
- `security/*`
- `feature/*`

Rules:

- one branch = one logical concern
- avoid mixed-purpose branches
- do not work directly on `main` unless explicitly instructed

---

## Pull request discipline

PRs must remain narrowly scoped.

Avoid:

- unrelated cleanup
- speculative refactors
- bundled concerns
- opportunistic churn

Prefer:

small, reviewable diffs.

---

## Merge strategy

Default:

squash merge for focused isolated work.

Use merge commits only when preserving explicit history adds value.

Keep history readable.

---

## Issue linkage discipline

Auto-close only when fully resolved.

Valid autoclose references:

- `Closes #X`
- `Fixes #X`
- `Resolves #X`

Non-closing references:

- `Refs #X`
- `Related to #X`
- `Partially addresses #X`

Do not auto-close unresolved work.

---

## Scope discipline

One problem → one scoped implementation.

Avoid:

- "while we're here" changes
- speculative architecture work
- unrelated formatting churn
- gratuitous renames
- dependency churn
- broad cleanup disguised as fixes

Scope discipline is mandatory.

---

## Repository-first workflow

Before implementation:

- inspect relevant files
- inspect neighboring tests
- inspect conventions
- inspect issue context
- inspect existing tooling assumptions

Do not invent repository structure.

Do not assume scripts/tooling exist.

---

## Debugging workflow

Debugging must be evidence-driven.

Required approach:

1. reproduce
2. inspect implementation
3. inspect logs / output
4. identify likely root cause
5. implement minimal fix
6. validate

Do not guess blindly.

If uncertainty exists:

state it explicitly.

---

## Validation discipline

Validation must be proportional to risk.

Examples:

### docs-only

Minimal validation.

### focused bugfix

Targeted regression validation.

### runtime logic

Broader validation.

### persistence changes

Migration / compatibility validation.

### workflow changes

Workflow-specific validation.

### release changes

Release-path validation.

---

## Standard validation commands

When applicable:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

These are defaults, not dogma.

Use judgment proportional to scope.

---

## Testing philosophy

Tests should be proportional.

Prefer:

focused regression coverage.

Avoid:

- speculative test expansion
- oversized suites for trivial changes
- under-testing risky changes

Behavioral regressions should be captured intentionally.

---

## Dependency discipline

Prefer:

- standard library
- existing dependencies

Do not add dependencies casually.

New dependency proposals must justify:

- necessity
- maintenance burden
- security impact
- operational impact

---

## Behavioral discipline

Do not silently alter behavior.

If behavior changes:

- state it explicitly
- justify it
- update tests appropriately
- update docs when relevant

Backward compatibility is preferred unless breakage is explicitly approved.

---

## CI / workflow discipline

Changes under:

`.github/workflows/*`

are high-risk.

Rules:

- inspect YAML carefully
- preserve least privilege
- preserve explicit permissions
- avoid merge artifact corruption
- validate assumptions

Python tests do not validate workflow correctness.

---

## Security expectations

Prefer least privilege.

Protect:

- secrets
- filesystem boundaries
- workflow permissions
- supply chain posture
- deployment assumptions

Security tradeoffs must be explicit.

---

## Release discipline

Release changes require caution.

Do not casually alter:

- versioning
- tags
- publishing semantics
- release workflows
- GHCR assumptions

---

## Communication expectations

Engineering communication should be:

- concise
- explicit
- technically honest
- uncertainty-aware

Do not present speculation as fact.

---

## Definition of done

Work is not complete unless:

- scope remained controlled
- architecture was respected
- validation was honest
- operational impact was considered
- security impact was considered
- issue linkage is correct
- relevant docs/tests updated where appropriate

"Code exists" is not completion.