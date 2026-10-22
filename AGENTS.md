# Agent Instructions

Authoritative repository agent instructions:

- .codex/instructions.md

Archived historical agent workflow materials:

- .meta/archive/codex-skills/

Only the active instruction surface should guide autonomous execution.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`voidlabshq/Versarr`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
