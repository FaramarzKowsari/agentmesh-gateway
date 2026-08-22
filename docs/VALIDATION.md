# Validation

The repository is designed so its default test suite requires no provider API key and no network access.

Required pre-merge checks:

```text
ruff check .
pytest
```

The initial bootstrap was locally exercised with the source tree on `PYTHONPATH`; 16 deterministic tests passed. Package installation/lint dependency download could not be reproduced in the isolated build environment because that environment has no outbound package-network access. GitHub Actions performs the full install + lint + test path on published branches and pull requests.
