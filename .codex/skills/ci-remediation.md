# Skill: CI Remediation

Govern remediation of failing GitHub Actions workflows in Versarr.

Use this skill when CI checks fail after push or pull request publication.

## 1. Inspect workflow state

List runs:

```powershell
gh run list `
  --repo voidlabshq/Versarr
```

Identify:

- failing workflow
- run ID
- failing job

Do not patch before identifying the actual failing check.

---

## 2. Inspect logs

Retrieve logs:

```powershell
gh run view RUN_ID `
  --repo voidlabshq/Versarr `
  --log
```

Inspect actual failure evidence.

Focus on:

- failing step
- command executed
- stderr output
- stack traces
- workflow assumptions

GitHub CI is source of truth.

---

## 3. Isolate root cause

Determine failure category:

- test failure
- lint failure
- type-check failure
- workflow syntax/config failure
- dependency/install failure
- environment assumption mismatch
- container/build failure

Fix root cause.

Do not patch symptoms.

---

## 4. Reproduce locally

Reproduce using matching local validation when possible.

Examples:

Default validation:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

Workflow validation:

```powershell
act
```

Container failures:

```powershell
docker compose build
```

If exact reproduction is impossible:

use CI evidence directly.

---

## 5. Patch minimally

Apply smallest fix that resolves the identified failure.

Rules:

- preserve scope
- avoid speculative refactors
- avoid unrelated cleanup
- avoid guessing

One failure at a time.

---

## 6. Revalidate

Run relevant validation again.

Do not push unvalidated remediation for risky failures.

---

## 7. Repeat until green

Push fix.

Reinspect CI.

Repeat:

inspect
→ isolate
→ reproduce
→ patch
→ validate

until all required checks pass.

---

## Constraints

Never:

- guess from red CI
- patch before reading logs
- fix unrelated issues during remediation
- merge failing CI