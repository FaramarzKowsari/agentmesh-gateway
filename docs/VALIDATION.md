# Validation

The repository is designed so its default test suite requires no provider API key and no network access.

Required pre-merge checks:

```text
ruff check .
pytest
```

## Verified baseline

The v0.1 foundation was exercised locally with 16 deterministic tests passing.

GitHub Actions then validated the published codebase on Python 3.11, 3.12, and 3.13. Every matrix job completed successfully with:

- `actions/checkout@v7`
- `actions/setup-python@v7`
- editable installation with development dependencies
- `ruff check .`
- the full `pytest` suite

No provider API key or paid service is required for these deterministic checks. Live-provider compatibility remains opt-in future validation and must not be conflated with the offline test baseline.
