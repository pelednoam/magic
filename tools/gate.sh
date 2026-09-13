#!/usr/bin/env bash
# The full gate, in the order CI runs it. Fails on the first problem.
set -euo pipefail

echo "== ruff check"          && uv run ruff check .
echo "== ruff format --check" && uv run ruff format --check .
echo "== file length"         && uv run python tools/check_file_length.py
echo "== coverage opt-outs"   && uv run python tools/check_pragma_allowlist.py
echo "== mypy"                && uv run mypy
echo "== pyright"             && uv run pyright
echo "== pytest + coverage"   && uv run pytest --cov --cov-branch --cov-report=term-missing
echo "== all gates passed"
