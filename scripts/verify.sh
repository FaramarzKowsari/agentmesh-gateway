#!/usr/bin/env sh
set -eu
ruff check .
pytest
