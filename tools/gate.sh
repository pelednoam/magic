#!/usr/bin/env bash
# The full gate, in the order CI runs it. Fails on the first problem.
set -euo pipefail

echo "== ruff check"          && uv run ruff check .
echo "== ruff format --check" && uv run ruff format --check .
echo "== file length"         && uv run python tools/check_file_length.py
echo "== coverage opt-outs"   && uv run python tools/check_pragma_allowlist.py
echo "== claude CLI flags"    && uv run python tools/check_cli_flags.py
echo "== mypy"                && uv run mypy
echo "== pyright"             && uv run pyright
echo "== pytest + coverage"   && uv run pytest --cov --cov-branch --cov-report=term-missing

# The app. Skipped only when explicitly allowed: a developer without npm can
# run the Python gate with SKIP_APP=1, but CI must not report "all gates
# passed" having silently checked no TypeScript at all.
if [ -d apps/mobile/node_modules ]; then
  echo "== app typecheck"      && (cd apps/mobile && npx --no-install tsc --noEmit)
  echo "== app tests"          && (cd apps/mobile && npx --no-install vitest run --reporter=dot)
elif [ "${SKIP_APP:-}" = "1" ]; then
  echo "== app                 SKIPPED by SKIP_APP=1 -- no TypeScript was checked"
else
  echo "== app                 FAILED: apps/mobile/node_modules is missing."
  echo "                       Run 'npm install' in apps/mobile, or set SKIP_APP=1"
  echo "                       to run the Python gate alone and accept that the"
  echo "                       TypeScript is unchecked."
  exit 1
fi

echo "== all gates passed"
