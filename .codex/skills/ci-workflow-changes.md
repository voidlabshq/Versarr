# Skill: CI Workflow Changes

Govern safe modification of GitHub Actions workflows in Versarr.

Use this skill when editing `.github/workflows/*`.

## Risk classification

Workflow changes are high-risk.

They can affect:

- validation correctness
- release integrity
- supply-chain security
- deployment behavior
- repository governance

Treat workflow edits as infrastructure changes.

---

## 1. Inspect existing workflow

Before editing:

inspect current workflow behavior.

Understand:

- trigger conditions
- permissions
- job dependencies
- action usage
- release assumptions

Do not patch blindly.

---

## 2. Preserve least privilege

Permissions must be explicit and minimal.

Prefer:

```yaml
permissions:
  contents: read
```

Expand only when required.

Examples:

```yaml
contents: write
pull-requests: write
packages: write
```

Do not grant broad permissions casually.

---

## 3. Prefer immutable action pinning

Prefer commit SHA pinning over mutable tags.

Preferred:

```yaml
uses: actions/checkout@COMMIT_SHA
```

Avoid:

```yaml
uses: actions/checkout@v6
```

Validate referenced SHAs against upstream sources when updating.

---

## 4. Minimize supply-chain complexity

Prefer simpler execution paths.

Be cautious with:

- nested wrapper actions
- opaque third-party abstractions
- hidden transitive action dependencies

If a wrapper obscures behavior, prefer explicit commands when practical.

---

## 5. Validate locally

Workflow changes require workflow validation.

Preferred:

```powershell
act
```

Python validation alone is insufficient.

Also run relevant repository validation:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -m "not interop and not container"
```

---

## 6. Release workflow caution

Release workflows are especially sensitive.

Do not casually modify:

- publishing logic
- version tagging
- artifact naming
- GHCR publishing
- release triggers

Treat release automation conservatively.

---

## Constraints

Never:

- trust mutable action tags by default
- introduce excessive permissions
- modify workflows without inspection
- rely only on Python test success for workflow validation