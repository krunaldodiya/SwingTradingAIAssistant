#!/usr/bin/env bash
# Daily after-close Nifty 200 scan and retained G09 diary page.
#
# Owned by this repository. The script, its systemd units and its installer all
# live here; diary pages are written under the private evidence store, never to
# an ad-hoc home directory. Install the scheduling timer with
# scripts/install_research_schedule.sh.
#
# It guards weekends, intraday hours, NSE closures, and duplicate same-day pages.
# Environment overrides:
#   SWING_REPO, SWING_STORAGE_ROOT, SWING_LOG_DIR, DOPPLER_BIN
#   SWING_DOPPLER_PROJECT, SWING_DOPPLER_CONFIG (explicit Doppler scope)
#   SWING_DATE_OVERRIDE (YYYY-MM-DD, for tests/dry runs)
#   SWING_DRY_RUN=1 (print the decision, do not scan)
#   SWING_ALLOW_OVERWRITE=1 (allow a second page for the same date)
set -u

REPO=${SWING_REPO:-/home/krunaldodiya/WorkSpace/Code/SwingTradingAIAssistant}
STORE=${SWING_STORAGE_ROOT:-/home/krunaldodiya/SwingTradingAIAssistantData}
LOG=${SWING_LOG_DIR:-$STORE/daily-scan}
DOPPLER=${DOPPLER_BIN:-/home/krunaldodiya/.local/bin/doppler}
DOPPLER_PROJECT_NAME=${SWING_DOPPLER_PROJECT:-swing-trading}
DOPPLER_CONFIG_NAME=${SWING_DOPPLER_CONFIG:-dev}
STAMP=${SWING_DATE_OVERRIDE:-$(date +%F)}
DRY_RUN=${SWING_DRY_RUN:-0}
mkdir -p "$LOG"

# Provider credentials come from Doppler under an explicit project/config scope,
# so no global Doppler configuration is required or mutated by this repository.
run_with_secrets() {
  "$DOPPLER" run --project "$DOPPLER_PROJECT_NAME" --config "$DOPPLER_CONFIG_NAME" -- "$@"
}

dow=$(date -d "$STAMP" +%u)
hour=$(date +%-H)
if [ "$dow" -ge 6 ]; then
  echo "$(date -Is) skipped: weekend (NSE closed)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP weekend"
  exit 0
fi
if [ -z "${SWING_DATE_OVERRIDE:-}" ] && [ "$hour" -ge 8 ] && [ "$hour" -lt 20 ]; then
  echo "$(date -Is) skipped: 08:00-19:59 IST (intraday or provider not published)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP intraday"
  exit 0
fi

holiday=$(
  python3 - "$STORE" "$STAMP" <<'PY'
import glob
import json
import os
import sys
from datetime import date

root, target = sys.argv[1], date.fromisoformat(sys.argv[2])
best = None
for path in sorted(glob.glob(os.path.join(root, "**", "calendar-schedules", "**", "*.json"), recursive=True)):
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        with open(path) as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            continue
        if not (date.fromisoformat(value["covered_from"]) <= target <= date.fromisoformat(value["covered_to"])):
            continue
        as_of = str(value.get("as_of", ""))
        if best is None or as_of > best[0]:
            best = (as_of, value)
    except (OSError, ValueError, KeyError, TypeError):
        continue
if best is None:
    print("NO_COVERAGE")
    raise SystemExit(0)
value = best[1]
closures = {str(item.get("trade_date")) for item in value.get("closures", []) if isinstance(item, dict)}
sessions = {str(item.get("trade_date")) for item in value.get("sessions", []) if isinstance(item, dict)}
if str(target) in closures:
    print("CLOSED")
elif sessions and str(target) not in sessions:
    print("CLOSED")
else:
    print("TRADING")
PY
)
if [ "$holiday" = "CLOSED" ]; then
  echo "$(date -Is) skipped: NSE closure ($STAMP)" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP holiday"
  exit 0
fi
if [ "$holiday" = "NO_COVERAGE" ]; then
  echo "$(date -Is) warning: no schedule coverage for $STAMP; proceeding" >> "$LOG/skipped.log"
fi

PAGE="$LOG/scan-$STAMP.json"
if [ -f "$PAGE" ] && [ "${SWING_ALLOW_OVERWRITE:-0}" != "1" ]; then
  echo "$(date -Is) skipped: duplicate page for $STAMP" >> "$LOG/skipped.log"
  [ "$DRY_RUN" = "1" ] && echo "SKIP duplicate"
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "WOULD_SCAN $STAMP"
  exit 0
fi

cd "$REPO" || exit 1
run_with_secrets "$REPO/.venv/bin/signal-decisions" scan \
  --storage-root "$STORE" \
  --nifty200 --refresh --retain-decision-evidence --output json \
  > "$PAGE" 2> "$LOG/scan-$STAMP.err"
code=$?
echo "$(date -Is) exit_code=$code" >> "$LOG/scan-$STAMP.err"
if [ "$code" -ne 0 ]; then
  exit "$code"
fi

# Deterministic post-scan analysis. These stages never change the scan page and
# never make a decision; a failure is logged and does not fail the scan.
ANALYSIS="$LOG/analysis-$STAMP.json"
RESEARCH="$LOG/research-$STAMP.json"
LIFECYCLE="$LOG/lifecycle-$STAMP.json"
BREADTH="$LOG/breadth-$STAMP.json"

# Market breadth trend from retained evidence. This is provider-free and exists
# so a zero-candidate week can be explained: whether member breadth is
# improving, deteriorating, or flat. It is not an index measure and never
# changes a decision.
"$REPO/.venv/bin/python" "$REPO/scripts/breadth_trend_report.py" \
  --storage-root "$STORE" --sessions 20 --output json \
  > "$BREADTH" 2> "$LOG/breadth-$STAMP.err"
echo "$(date -Is) breadth_exit=$?" >> "$LOG/scan-$STAMP.err"

# Benchmark freshness advisory. The scan computes every relative-strength number
# from adjusted_daily, which a separate dataset refresh maintains; a stale store
# makes those numbers describe an earlier market. This stage never fails or
# blocks the pass: it only records the state so the ledger entry can say the
# claim is unavailable instead of restating a stale one.
FRESHNESS="$LOG/benchmark-freshness-$STAMP.json"
EVIDENCE_HANDLE=$(
  python3 - "$PAGE" <<'PY'
import json
import sys

try:
    with open(sys.argv[1]) as handle:
        envelope = json.load(handle)
except (OSError, ValueError):
    envelope = {}
value = envelope.get("decision_evidence_handle")
print(value if isinstance(value, str) and len(value) == 64 else "")
PY
)
freshness_args=(--storage-root "$STORE" --output json)
[ -n "$EVIDENCE_HANDLE" ] && freshness_args+=(--evidence-handle "$EVIDENCE_HANDLE")
# Bound the stage: a cold or stalled store must never delay the pass.
timeout 60 "$REPO/.venv/bin/python" "$REPO/scripts/check_benchmark_freshness.py" \
  "${freshness_args[@]}" > "$FRESHNESS" 2> "$LOG/benchmark-freshness-$STAMP.err"
freshness_code=$?
echo "$(date -Is) benchmark_freshness_exit=$freshness_code" >> "$LOG/scan-$STAMP.err"
# An unusable advisory must never reach the writer as a malformed artifact.
[ -s "$FRESHNESS" ] || rm -f "$FRESHNESS"
SYMBOLS=$(
  python3 - "$PAGE" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    envelope = json.load(handle)
scan = envelope.get("scan", envelope)
for candidate in scan.get("candidates") or []:
    symbol = candidate.get("symbol")
    if isinstance(symbol, str) and symbol:
        print(symbol)
PY
)

if [ -z "$SYMBOLS" ]; then
  echo "$(date -Is) analysis skipped: no candidates in $STAMP scan" >> "$LOG/scan-$STAMP.err"
else
  run_with_secrets "$REPO/.venv/bin/swing-analysis" \
    --scan-json "$PAGE" --output json \
    > "$ANALYSIS" 2> "$LOG/analysis-$STAMP.err"
  echo "$(date -Is) swing_analysis_exit=$?" >> "$LOG/analysis-$STAMP.err"

  symbol_args=""
  for symbol in $SYMBOLS; do
    symbol_args="$symbol_args --symbol $symbol"
  done
  # shellcheck disable=SC2086 # symbol_args is a built word list of validated symbols
  run_with_secrets "$REPO/.venv/bin/market-data" research-run-current \
    --contract-version v2 $symbol_args \
    --storage-root "$STORE" --output json \
    > "$RESEARCH" 2> "$LOG/research-$STAMP.err"
  echo "$(date -Is) research_exit=$?" >> "$LOG/research-$STAMP.err"

  # Read-only per-stock lifecycle projection over the retained artifacts.
  "$REPO/.venv/bin/swing-analysis" --lifecycle \
    --scan-json "$PAGE" --storage-root "$STORE" \
    --analysis-json "$ANALYSIS" --output json \
    > "$LIFECYCLE" 2> "$LOG/lifecycle-$STAMP.err"
  echo "$(date -Is) lifecycle_exit=$?" >> "$LOG/lifecycle-$STAMP.err"
fi

# Every real pass must reach the owner's private ledger. This stage is what keeps
# an unattended run from producing evidence with no research record. It skips a
# degenerate page (all members failing one upstream reason) and never overwrites
# an entry that already cites this page's handle.
if [ -n "${SWING_LEDGER_ROOT:-}" ]; then
  ledger_args=(--scan-json "$PAGE" --ledger-root "$SWING_LEDGER_ROOT" --status unconfirmed)
  [ -f "$ANALYSIS" ] && ledger_args+=(--analysis-json "$ANALYSIS")
  [ -f "$RESEARCH" ] && ledger_args+=(--research-json "$RESEARCH")
  [ -f "$LIFECYCLE" ] && ledger_args+=(--lifecycle-json "$LIFECYCLE")
  [ -s "$FRESHNESS" ] && ledger_args+=(--freshness-json "$FRESHNESS")
  ledger_args+=(--command "signal-decisions scan --nifty200 --refresh --retain-decision-evidence")
  [ -f "$ANALYSIS" ] && ledger_args+=(--command "swing-analysis --scan-json scan-$STAMP.json")
  [ -f "$RESEARCH" ] && ledger_args+=(--command "market-data research-run-current --contract-version v2")
  "$REPO/.venv/bin/python" "$REPO/scripts/write_scan_ledger_entry.py" \
    "${ledger_args[@]}" > "$LOG/ledger-$STAMP.log" 2>&1
  ledger_code=$?
  echo "$(date -Is) ledger_exit=$ledger_code $(cat "$LOG/ledger-$STAMP.log")" \
    >> "$LOG/scan-$STAMP.err"
  # A real pass that cannot record itself has not satisfied the delivery gate,
  # so the unit must report failure instead of a silent success.
  if [ "$ledger_code" -ne 0 ]; then
    exit "$ledger_code"
  fi

  # Push the new entry off-device immediately. The hourly timer is a fallback for
  # manual writes; it must not be the only path between a pass and its backup.
  RCLONE=${SWING_RCLONE_BIN:-/usr/bin/rclone}
  LEDGER_REMOTE=${SWING_LEDGER_REMOTE:-gdrive:SwingResearchLedger}
  if [ -x "$RCLONE" ]; then
    "$RCLONE" copy "$SWING_LEDGER_ROOT" "$LEDGER_REMOTE" --update \
      --exclude ".staged-*" \
      --log-file "${SWING_SYNC_LOG_DIR:-$HOME/.local/state/rclone}/research-ledger.log" \
      >> "$LOG/ledger-sync-$STAMP.log" 2>&1
    sync_code=$?
    echo "$(date -Is) ledger_sync_exit=$sync_code" >> "$LOG/scan-$STAMP.err"
    # A ledger that never left the device is still single-copy; report it.
    if [ "$sync_code" -ne 0 ]; then
      exit "$sync_code"
    fi
  else
    echo "$(date -Is) ledger sync failed: $RCLONE not executable" >> "$LOG/scan-$STAMP.err"
    exit 1
  fi
else
  echo "$(date -Is) ledger failed: SWING_LEDGER_ROOT is not set" >> "$LOG/scan-$STAMP.err"
  exit 1
fi

exit 0
