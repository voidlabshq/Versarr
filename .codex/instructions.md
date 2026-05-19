# Codex Repository Instructions

## Scope

Operate autonomously on this repository using available GitHub integration and local workspace tooling.

Prefer direct action over requesting manual intervention unless blocked by permissions, missing credentials, or ambiguous requirements.

## Workflow

Follow this execution model:

1. Inspect open GitHub issues.
2. Select one tightly scoped issue.
3. Work only within the issue scope.
4. Create an isolated branch (never work on `main`).
5. Implement the minimal correct fix.
6. Validate locally.
7. Create or update a pull request.
8. Inspect CI results.
9. Remediate failures until green.
10. Merge only after validation succeeds.
11. Clean up merged branches.

Do not batch unrelated issues in a single implementation unless explicitly requested.

## Validation

Use repository-local tooling:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\pytest.exe -m "not interop and not container"
```

When changing CI workflows, security workflows, packaging, release automation, Docker behavior, dependency management, or validation logic, choose the minimal validation set appropriate to the scope.

## Pull Request Policy

Pull requests must be:

- narrowly scoped
- technically coherent
- minimal in diff size
- linked to the relevant issue when applicable

Prefer squash merge.

Do not merge failing CI.

## Engineering Constraints

Preserve existing architecture unless the issue explicitly requires structural change.

Do not perform speculative refactors.

Do not introduce unrelated cleanup.

Do not modify secrets, credentials, release artifacts, or repository governance unless explicitly in scope.

## GitHub Actions

When CI fails:

1. inspect logs
2. identify root cause
3. apply the minimal corrective change
4. revalidate
5. re-run until green

Do not disable failing checks to achieve a passing result.

## Communication

Be concise.

Act first, explain briefly.

Avoid unnecessary planning output unless the task is ambiguous or explicitly requests a plan.