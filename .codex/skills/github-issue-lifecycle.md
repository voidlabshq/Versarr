# Skill: GitHub Issue Lifecycle

Govern GitHub issue selection, ownership, and project tracking for Versarr.

Use this skill for backlog triage and issue state management.

## Context

Repository: `voidlabshq/Versarr`

Project: `Versarr Roadmap`

Project ID: `PVT_kwDOEPkZX84BX04R`

Status field: `PVTSSF_lADOEPkZX84BX04RzhS_Fg8`

Status options:

- Todo: `f75ad846`
- In Progress: `47fc9ee4`
- Done: `98236657`

---

## 1. Discover work

Inspect open backlog:

```powershell
gh issue list `
  --repo voidlabshq/Versarr `
  --state open
```

Review:

- priority labels
- issue category
- scope
- ambiguity
- update recency

---

## 2. Select scope

Prefer:

- one issue
- or tightly related issue batch

Allowed:

- related bugs
- related validation work
- related CI/security work
- narrowly scoped docs work

Disallowed:

- unrelated mixed concerns
- broad multi-domain batches

Selection rules:

- coherent concern
- independently testable
- minimal blast radius
- explicit completion criteria

If scope is broad, split it.

---

## 3. Claim ownership

Assign explicitly:

```powershell
gh issue edit ISSUE `
  --repo voidlabshq/Versarr `
  --add-assignee "@me"
```

---

## 4. Move active work

When implementation begins, move project item to In Progress:

```powershell
gh project item-edit `
  --id ITEM_ID `
  --project-id PVT_kwDOEPkZX84BX04R `
  --field-id PVTSSF_lADOEPkZX84BX04RzhS_Fg8 `
  --single-select-option-id 47fc9ee4
```

---

## 5. Issue linkage semantics

Use only for full resolution:

```text
Closes #X
Fixes #X
Resolves #X
```

Use for partial work:

```text
Refs #X
Partially addresses #X
```

Never auto-close unresolved issues.

---

## 6. Completion

After merge, verify open backlog:

```powershell
gh issue list `
  --repo voidlabshq/Versarr `
  --state open
```

If project state did not update, move item to Done:

```powershell
gh project item-edit `
  --id ITEM_ID `
  --project-id PVT_kwDOEPkZX84BX04R `
  --field-id PVTSSF_lADOEPkZX84BX04RzhS_Fg8 `
  --single-select-option-id 98236657
```

---

## Constraints

Never:

- implement from issue title alone
- batch unrelated work
- leave active owned work in Todo
- auto-close unresolved issues
