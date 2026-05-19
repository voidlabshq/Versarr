# Skill: Pull Request Workflow

Govern pull request creation, publication, and merge workflow for Versarr.

Use this skill when publishing completed scoped work.

## Repository conventions

Repository:

`voidlabshq/Versarr`

Project:

`Versarr Roadmap`

Merge strategy:

- squash merge
- delete merged branches

---

## 1. Push branch

Publish current branch:

```powershell
git push --set-upstream origin BRANCH
```

---

## 2. Create pull request

Use explicit GitHub CLI conventions.

Pattern:

```powershell
gh pr create `
  --repo voidlabshq/Versarr `
  --base main `
  --head BRANCH `
  --project "Versarr Roadmap" `
  --title "TITLE" `
  --assignee "@me" `
  --label "LABEL" `
  --body @"
...
"@
```

Rules:

- explicit scope
- explicit labels
- explicit project association
- explicit ownership

Do not rely on implicit defaults.

---

## 3. PR body discipline

Include:

- concise summary
- implementation scope
- issue linkage
- validation performed
- operational notes if relevant

Example sections:

```text
## Summary
## Scope
## Validation
## Notes
```

Claims must match actual implementation.

Do not overstate validation.

---

## 4. Issue linkage

Use closure semantics only for fully resolved issues:

```text
Closes #X
Fixes #X
Resolves #X
```

Use references for partial work:

```text
Refs #X
Partially addresses #X
```

---

## 5. Wait for CI

Required checks must pass before merge.

Typical checks:

- ci
- container
- security

GitHub CI is source of truth.

---

## 6. Merge

Preferred:

```powershell
gh pr merge PR `
  --repo voidlabshq/Versarr `
  --squash `
  --delete-branch `
  --subject "FINAL SUBJECT"
```

If using automerge:

```powershell
gh pr merge PR `
  --repo voidlabshq/Versarr `
  --auto `
  --squash `
  --delete-branch `
  --subject "FINAL SUBJECT"
```

Use automerge only when repository policy permits.

---

## Constraints

Never:

- merge failing CI
- create misleading PR summaries
- auto-close unresolved issues
- rely on implicit gh defaults