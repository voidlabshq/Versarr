# Contributing

## Development standards

- Keep MVP sidecar-first.
- Do not add embedded tag writing in MVP.
- Keep SQLite limited to process state.
- Add or update tests for behavior changes.
- Prefer narrow, explicit modules over speculative abstractions.

## Quality gates

- `ruff check .`
- `ruff format --check .`
- `mypy src`
- `pytest`

