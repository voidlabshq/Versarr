# Skill: Implementation Workflow

Govern local engineering execution for Versarr implementation work.

Use this skill when editing code, configuration, documentation, or repository assets.

## 1. Create branch

Never work directly on `main`.

Start from current main:

```powershell
git checkout main
git pull
git checkout -b SCOPE/NAME
```

Branch patterns:

- fix/*
- docs/*
- ci/*
- security/*
- validation/*
- maintenance/*
- feature/*

Rules:

- one branch = one logical concern
- avoid mixed-purpose branches
- keep names explicit

---

## 2. Baseline validation

Before edits:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

If baseline fails:

stop and investigate repository state.

Do not implement on broken baseline.

---

## 3. Investigate before editing

Inspect:

- relevant implementation
- neighboring tests
- affected configuration
- architectural constraints
- issue acceptance criteria

Determine:

- root cause
- intended change surface
- validation strategy

Do not patch blindly.

Do not guess.

---

## 4. Implement minimally

Rules:

- edit only required files
- preserve architecture
- preserve conventions
- avoid speculative refactors
- avoid opportunistic cleanup
- avoid dependency churn unless required
- avoid unrelated formatting churn

Prefer small deterministic diffs.

---

## 5. Validate locally

Default validation:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

Additional validation when relevant:

Workflow changes:

```powershell
act
```

Container changes:

```powershell
docker compose build
```

Runtime behavior:

targeted reproduction validation

Validation must match risk.

---

## 6. Review diff

Before commit:

```powershell
git diff
```

Confirm:

- no unrelated edits
- no scope drift
- no generated artifacts
- no secrets
- no accidental churn

If diff exceeds intended scope:

reduce it.

---

## 7. Commit

Commit only after successful validation.

Format:

```text
type: concise scoped summary
```

Examples:

```text
bug: fix duplicated environment config parsing
ci: harden GitHub Actions supply chain security
docs: improve deployment guidance
```

---

## 8. Local cleanup

Confirm clean state:

```powershell
git status
```

Expected before PR publication:

- intended staged changes only
- no temporary artifacts
- no accidental untracked files

---

## Constraints

Never:

- work on main
- implement on broken baseline
- patch without investigation
- widen scope mid-batch
- commit unvalidated risky changes