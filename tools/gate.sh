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

# The app, if its dependencies are installed. Skipped rather than failed when
# they are not: the Python gate has to run on a machine that has never seen
# npm, and `apps/*` is strict TS with no coverage gate by design (§5).
if [ -d apps/mobile/node_modules ]; then
  echo "== app typecheck"      && (cd apps/mobile && npx --no-install tsc --noEmit)
  echo "== app tests"          && (cd apps/mobile && npx --no-install vitest run --reporter=dot)
else
  echo "== app                 skipped: run 'npm install' in apps/mobile"
fi

echo "== all gates passed"
