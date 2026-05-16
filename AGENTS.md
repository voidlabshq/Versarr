# AGENTS.md

This repository expects disciplined engineering behavior from both human contributors and software agents.

These rules are authoritative unless explicitly overridden by the current task.

---

## Instruction precedence

If instructions conflict, resolve in this order:

1. explicit current user task
2. explicit issue acceptance criteria
3. repository architectural constraints
4. established repository conventions
5. this file

If conflict remains unresolved:

STOP and ask for clarification.

Do not improvise conflicting interpretations.

---

## Truthful execution

Never fabricate repository state.

Never claim success unless directly verified.

Examples:

- tests passed
- CI is green
- workflows validated
- build succeeded
- image published
- migration succeeded
- files modified
- branch exists
- PR exists
- issue exists

Distinguish clearly between:

- confirmed
- likely
- speculative

Never present guesses as facts.

---

## Repository-first discipline

Before making changes:

- inspect relevant files
- inspect neighboring tests
- inspect repository structure
- inspect existing conventions
- inspect issue context when applicable

Do not invent repository structure.

Do not assume scripts, tooling, or workflows exist without verification.

Adapt to established patterns.

---

## Scope discipline

Prefer the smallest coherent change that fully solves the task.

One problem → one scoped implementation.

Avoid:

- speculative refactors
- unrelated cleanup
- formatting churn
- gratuitous renames
- dependency churn
- "while we're here" changes
- speculative abstractions

Do not broaden scope without explicit justification.

---

## Behavioral discipline

Do not silently alter user-visible or operational behavior.

If behavior changes:

- state it explicitly
- justify it
- update tests where appropriate
- update docs when materially relevant

Prefer backward-compatible behavior unless explicit breakage is approved.

---

## Configuration compatibility

Avoid breaking:

- environment variables
- config files
- deployment assumptions
- operational defaults

If configuration changes:

document migration impact clearly.

---

## Operational safety

Preserve:

- safe repeated execution
- restart safety
- upgrade compatibility
- filesystem invariants
- idempotent operational behavior where appropriate

Avoid fragile assumptions.

Operational failures should be diagnosable.

Prefer actionable logs over silent failures.

---

## Dependency discipline

Prefer:

- Python standard library
- existing approved dependencies

Do not add dependencies casually.

If proposing a new dependency:

justify:

- necessity
- maintenance cost
- security implications
- operational impact

Do not silently upgrade dependencies.

---

## Validation discipline

Validation must be proportional to scope and risk.

Examples:

- docs-only changes → minimal validation
- focused bugfix → targeted regression validation
- runtime changes → broader validation
- persistence changes → migration validation
- workflow changes → workflow validation

Prefer focused regression coverage over speculative test expansion.

---

## Security discipline

Prefer least privilege.

Do not casually weaken:

- filesystem boundaries
- secrets handling
- CI permissions
- supply chain posture
- deployment assumptions

If security tradeoffs exist:

state them explicitly.

---

## Escalation boundary

STOP instead of improvising when work would require:

- architecture redesign
- broad refactor
- destructive migration
- unclear acceptance criteria
- uncertain security tradeoffs
- speculative persistence changes
- major release workflow changes
- unclear operational impact

---

## Success criteria

Successful work is:

- correct
- narrowly scoped
- reviewable
- architecture-consistent
- operationally safe
- honestly validated
- explicit about tradeoffs

"Working code" alone is not sufficient.