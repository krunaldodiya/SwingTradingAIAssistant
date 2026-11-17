#!/usr/bin/env bash
# Verify that the checkout-local Python environment belongs to THIS directory,
# and rebuild it when the repository has moved or the environment is damaged.
#
# A virtual environment is not relocatable: console-script shebangs, the
# editable-install .pth, and activate scripts all embed absolute paths. Moving
# or cloning the checkout therefore requires a rebuild, not a copy. This script
# detects that condition and recreates .venv in place from uv.lock.
#
# Usage:
#   scripts/ensure_local_environment.sh            # verify, repair if stale
#   scripts/ensure_local_environment.sh --check    # verify only, never write
#   scripts/ensure_local_environment.sh --quiet    # no success output
#
# Environment overrides:
#   SWING_REPO        checkout root (default: parent of this script)
#   SWING_UV_BIN      uv executable (default: uv on PATH)
#
# Exit codes: 0 healthy or repaired, 1 stale in --check mode, 2 invalid input,
# 3 repair failed or uv unavailable.
set -uo pipefail

REPO=${SWING_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
CHECK=0
QUIET=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "environment_invalid: unknown argument $1" >&2
      exit 2
      ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || echo "environment: $*"; }

VENV="$REPO/.venv"
PY="$VENV/bin/python"

# Project entry points declared in pyproject.toml. Each console script carries
# the absolute interpreter path, so a moved checkout leaves them unrunnable.
ENTRYPOINTS=(
  equity-data-download
  market-data
  signal-decisions
  swing-analysis
  stock-observations
  stock-safety-evidence
)

problems=()

check() {
  problems=()
  [ -x "$PY" ] || problems+=("missing interpreter $PY")
  if [ -x "$PY" ]; then
    "$PY" -c 'import sys, swing_trading_ai_assistant, equity_data_downloader; assert sys.version_info[:2] == (3, 11)' \
      >/dev/null 2>&1 || problems+=("$VENV is not a working Python 3.11 project environment")
  fi
  local name expected shebang
  expected="#!$PY"
  for name in "${ENTRYPOINTS[@]}"; do
    if [ ! -f "$VENV/bin/$name" ]; then
      problems+=("missing entry point $VENV/bin/$name")
      continue
    fi
    IFS= read -r shebang < "$VENV/bin/$name" || shebang=""
    [ "$shebang" = "$expected" ] || \
      problems+=("$name points at ${shebang#\#!} instead of $PY")
  done
  local activate="$VENV/bin/activate"
  if [ -f "$activate" ]; then
    grep -Fq "VIRTUAL_ENV='$VENV'" "$activate" || \
      problems+=("activate script names a different environment root")
  fi
}

check
if [ "${#problems[@]}" -eq 0 ]; then
  say "ok $VENV"
  exit 0
fi

say "stale $VENV"
printf '  - %s\n' "${problems[@]}" >&2
if [ "$CHECK" -eq 1 ]; then
  echo "environment_stale: run scripts/ensure_local_environment.sh" >&2
  exit 1
fi

UV=${SWING_UV_BIN:-$(command -v uv || true)}
if [ -z "$UV" ]; then
  echo "environment_failed: uv is not installed; cannot rebuild $VENV" >&2
  exit 3
fi

# Rebuild in place. A temporary sibling cannot be renamed into place because
# the fresh shebangs and .pth would still name the temporary path.
backup="$REPO/.venv.stale"
rm -rf "$backup"
if [ -e "$VENV" ] && ! mv "$VENV" "$backup"; then
  echo "environment_failed: cannot move $VENV aside" >&2
  exit 3
fi

if ! ( cd "$REPO" && "$UV" sync --frozen --extra dev --python 3.11 ); then
  echo "environment_failed: uv sync did not complete; restoring previous environment" >&2
  if [ -e "$backup" ]; then
    rm -rf "$VENV"
    mv "$backup" "$VENV"
  fi
  exit 3
fi
rm -rf "$backup"

check
if [ "${#problems[@]}" -ne 0 ]; then
  printf '  - %s\n' "${problems[@]}" >&2
  echo "environment_failed: rebuilt environment is still inconsistent" >&2
  exit 3
fi
if ! "$VENV/bin/signal-decisions" --help >/dev/null 2>&1; then
  echo "environment_failed: rebuilt signal-decisions entry point does not run" >&2
  exit 3
fi

say "rebuilt $VENV"
