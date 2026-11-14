#!/usr/bin/env bash
# Daily after-close Nifty 200 scan and retained G09 diary page.
#
# Owned by this repository. The script, its systemd units and its installer all
# live here; diary pages are written under the private evidence store, never to
# an ad-hoc home directory. Install the scheduling timer with
# scripts/install_research_schedule.sh.
#
# It guards weekends, intraday hours, NSE closures, and duplicate same-day pages.
# It runs the provider capture preflight before any scan or research, waits for
# an active 20:00 head start instead of duplicating it, and lets a complete
# receipt let the scan reuse the captured terminal session.
# Environment overrides:
#   SWING_REPO, SWING_STORAGE_ROOT, SWING_LOG_DIR, DOPPLER_BIN
#   SWING_DOPPLER_PROJECT, SWING_DOPPLER_CONFIG (explicit Doppler scope)
#   SWING_DATE_OVERRIDE (YYYY-MM-DD, for tests/dry runs)
#   SWING_DRY_RUN=1 (print the decision, do not scan)
#   SWING_ALLOW_OVERWRITE=1 (allow a second page for the same date)
#   SWING_CAPTURE_COMMAND, SWING_CAPTURE_SERVICE (capture preflight target)
#   SWING_CAPTURE_SERVICE_STATE_COMMAND (ActiveState command for tests)
#   SWING_CAPTURE_SERVICE_STATUS (explicit executable override, exit 0 = busy)
#   SWING_CAPTURE_LEASE_STATE_COMMAND (storage lease probe: FREE or BUSY)
#   SWING_CAPTURE_LEASE_PYTHON (interpreter for the default lease probe)
#   SWING_CAPTURE_PREFLIGHT_BUDGET, SWING_CAPTURE_POLL_SECONDS
#   SWING_CAPTURE_TIMEOUT, SWING_CAPTURE_KILL_AFTER
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
# Suppose the provider stops answering mid-scan. Without a deadline one stalled
# request consumes the whole pass and systemd eventually kills the unit, leaving
# an empty page and no record. Fail fast, name the stage, and leave no artifact.
SCAN_TIMEOUT=${SWING_SCAN_TIMEOUT:-1200}
SCAN_ARGS=(--storage-root "$STORE" --nifty200 --refresh --retain-decision-evidence --output json)

# Provider capture preflight, before any scan, research, or analysis. The capture
# has its own failure domain, so a later calendar or research failure cannot
# discard retained provider data. A complete receipt lets the scan reuse the
# captured terminal session. An active 20:00 head start is waited for, never
# killed or duplicated; a timed-out or failed one is resumed from its checkpoint.
CAPTURE_RECEIPT="$LOG/capture-$STAMP.json"
CAPTURE_COMMAND=${SWING_CAPTURE_COMMAND:-$REPO/scripts/capture_provider_data.sh}
CAPTURE_SERVICE=${SWING_CAPTURE_SERVICE:-swing-data-capture.service}
# The whole pass must fit swing-daily-scan.service TimeoutStartSec=3600:
#   preflight (unit/lease wait + capture resume) 1740
#   + capture kill-after grace 30
#   + scan 1200
#   + post-scan analysis/research/ledger reserve 600
#   = 3570, leaving 30 seconds of margin.
# The preflight budget is one deadline shared by the unit wait, the storage
# lease wait, and the capture resume, so no path can exceed it.
CAPTURE_PREFLIGHT_BUDGET=${SWING_CAPTURE_PREFLIGHT_BUDGET:-1740}
CAPTURE_POLL_SECONDS=${SWING_CAPTURE_POLL_SECONDS:-10}
CAPTURE_TIMEOUT=${SWING_CAPTURE_TIMEOUT:-1200}
CAPTURE_KILL_AFTER=${SWING_CAPTURE_KILL_AFTER:-30}
CAPTURE_LOG="$LOG/capture-preflight-$STAMP.log"

capture_receipt_complete() {
  [ -f "$CAPTURE_RECEIPT" ] || return 1
  [ "$(
    python3 - "$CAPTURE_RECEIPT" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle)
except (OSError, ValueError):
    value = {}
if not isinstance(value, dict):
    value = {}
sessions = value.get("sessions")
sessions = sessions if isinstance(sessions, dict) else {}
adjusted = value.get("adjusted")
adjusted = adjusted if isinstance(adjusted, dict) else {}
remaining = value.get("remaining_pending")
if not isinstance(remaining, int):
    remaining = sessions.get("remaining_pending")
try:
    failed = int(value.get("failed") or 0)
except (TypeError, ValueError):
    failed = 1
complete = (
    value.get("status") == "COMPLETE"
    and sessions.get("status") in {"COMPLETE", "SKIPPED"}
    and adjusted.get("status") in {"COMPLETE", "SKIPPED"}
    and failed == 0
    and remaining == 0
)
print("1" if complete else "0")
PY
  )" = "1" ]
}

capture_service_state() {
  if [ -n "${SWING_CAPTURE_SERVICE_STATE_COMMAND:-}" ]; then
    bash -c "$SWING_CAPTURE_SERVICE_STATE_COMMAND" 2> /dev/null || true
  else
    systemctl --user show -p ActiveState --value "$CAPTURE_SERVICE" 2> /dev/null \
      || true
  fi
}

capture_service_active() {
  if [ -n "${SWING_CAPTURE_SERVICE_STATUS:-}" ]; then
    # An explicit executable path override; never word-split the value.
    "$SWING_CAPTURE_SERVICE_STATUS" > /dev/null 2>&1
    return $?
  fi
  # A unit that is activating, deactivating, or reloading still owns the
  # capture; treating only "active" as busy could launch a duplicate.
  case "$(capture_service_state)" in
    active | activating | deactivating | reloading) return 0 ;;
    *) return 1 ;;
  esac
}

# A manually started capture holds the storage-root lease rather than a unit.
# Probe it without waiting or creating the lock; only an explicit BUSY blocks.
capture_lease_state() {
  if [ -n "${SWING_CAPTURE_LEASE_STATE_COMMAND:-}" ]; then
    bash -c "$SWING_CAPTURE_LEASE_STATE_COMMAND" 2> /dev/null || echo UNKNOWN
    return
  fi
  PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}" \
    "${SWING_CAPTURE_LEASE_PYTHON:-python3}" - "$STORE" <<'PY'
import os
import sys
from pathlib import Path

try:
    from swing_trading_ai_assistant.market_data.storage_root_lease import (
        LeaseOutcome,
        StorageRootLease,
    )
except Exception:  # noqa: BLE001 - an unavailable probe is not proof of a holder
    print("UNKNOWN")
    raise SystemExit(0)

root = Path(sys.argv[1])
try:
    if not os.path.lexists(root / ".ingestion.lock"):
        print("FREE")
    else:
        identity = StorageRootLease.admit_existing_private_identity(root)
        if identity is None:
            print("BUSY")
        else:
            result = StorageRootLease.try_acquire_existing_identity(root, identity)
            if result.outcome is LeaseOutcome.ACQUIRED and result.lease is not None:
                result.lease.close()
                print("FREE")
            else:
                print("BUSY")
except Exception:  # noqa: BLE001 - fail closed for a held or unsafe root
    print("BUSY")
PY
}

capture_lease_busy() {
  # Only an explicit FREE is proof that no manual capture holds the root. An
  # unknown probe result is treated as busy and must clear within the budget.
  case "$(capture_lease_state)" in
    FREE) return 1 ;;
    *) return 0 ;;
  esac
}

CAPTURE_STATE=INCOMPLETE
CAPTURE_BUSY=""
preflight_deadline=$(( $(date +%s) + CAPTURE_PREFLIGHT_BUDGET ))

# Busy checks come first, even for a complete receipt: an older receipt must
# not let the scan start beside a capture that is still writing the root.
if capture_service_active; then
  echo "$(date -Is) capture preflight: waiting for $CAPTURE_SERVICE" \
    >> "$CAPTURE_LOG"
  while capture_service_active; do
    if [ "$(date +%s)" -ge "$preflight_deadline" ]; then
      break
    fi
    sleep "$CAPTURE_POLL_SECONDS"
  done
fi
if capture_service_active; then
  CAPTURE_BUSY="unit"
  echo "$(date -Is) capture preflight: $CAPTURE_SERVICE still busy after the ${CAPTURE_PREFLIGHT_BUDGET}s preflight budget" \
    >> "$CAPTURE_LOG"
fi

if [ -z "$CAPTURE_BUSY" ]; then
  if capture_lease_busy; then
    echo "$(date -Is) capture preflight: storage-root lease busy; waiting" \
      >> "$CAPTURE_LOG"
    while capture_lease_busy; do
      if [ "$(date +%s)" -ge "$preflight_deadline" ]; then
        break
      fi
      sleep "$CAPTURE_POLL_SECONDS"
    done
  fi
  if capture_lease_busy; then
    CAPTURE_BUSY="lease"
    echo "$(date -Is) capture preflight: storage-root lease still busy after the ${CAPTURE_PREFLIGHT_BUDGET}s preflight budget" \
      >> "$CAPTURE_LOG"
  fi
fi

if [ -z "$CAPTURE_BUSY" ]; then
  if capture_receipt_complete; then
    CAPTURE_STATE=COMPLETE
    echo "$(date -Is) capture preflight: receipt complete; scan reuses it" \
      >> "$CAPTURE_LOG"
  else
    remaining=$(( preflight_deadline - $(date +%s) ))
    [ "$remaining" -gt 0 ] || remaining=1
    [ "$remaining" -le "$CAPTURE_TIMEOUT" ] || remaining=$CAPTURE_TIMEOUT
    echo "$(date -Is) capture preflight: running $CAPTURE_COMMAND (bounded ${remaining}s)" \
      >> "$CAPTURE_LOG"
    timeout --kill-after="${CAPTURE_KILL_AFTER}s" "$remaining" \
      "$CAPTURE_COMMAND" >> "$CAPTURE_LOG" 2>&1
    preflight_code=$?
    echo "$(date -Is) capture preflight: exit_code=$preflight_code" \
      >> "$CAPTURE_LOG"
    if capture_receipt_complete; then
      CAPTURE_STATE=COMPLETE
    fi
  fi
fi

if [ -n "$CAPTURE_BUSY" ]; then
  # Capture and research must not run concurrently. A unit or a manual holder
  # that outlasts the preflight budget means this pass cannot both finish the
  # capture and scan inside the service deadline, so fail closed instead of
  # scanning beside it.
  echo "$(date -Is) CAPTURE_INCOMPLETE receipt=$CAPTURE_RECEIPT scan_not_started=$CAPTURE_BUSY" \
    >> "$CAPTURE_LOG"
  echo "$(date -Is) CAPTURE_INCOMPLETE receipt=$CAPTURE_RECEIPT scan_not_started=$CAPTURE_BUSY" \
    >> "$LOG/scan-$STAMP.err"
  exit 75
fi

if [ "$CAPTURE_STATE" = "COMPLETE" ]; then
  SCAN_ARGS+=(--reuse-captured-terminal)
fi
timeout "$SCAN_TIMEOUT" "$DOPPLER" run \
  --project "$DOPPLER_PROJECT_NAME" --config "$DOPPLER_CONFIG_NAME" -- \
  "$REPO/.venv/bin/signal-decisions" scan \
  "${SCAN_ARGS[@]}" \
  > "$PAGE" 2> "$LOG/scan-$STAMP.err"
code=$?
if [ "$CAPTURE_STATE" != "COMPLETE" ]; then
  echo "$(date -Is) CAPTURE_INCOMPLETE receipt=$CAPTURE_RECEIPT" \
    >> "$LOG/scan-$STAMP.err"
fi
echo "$(date -Is) exit_code=$code scan_timeout_s=$SCAN_TIMEOUT" >> "$LOG/scan-$STAMP.err"
if [ "$code" -ne 0 ]; then
  # A partial or empty page is not evidence; leaving it invites a later reader to
  # mistake a failed pass for a no-candidate market.
  rm -f "$PAGE"
  if [ "$code" -eq 124 ]; then
    echo "$(date -Is) scan exceeded ${SCAN_TIMEOUT}s; page discarded" >> "$LOG/scan-$STAMP.err"
  fi
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

# Forward paper observation (G11). Registers today's candidates and evaluates
# their recorded stop/target against retained bars. This is measurement, never
# advice, and it must never fail or delay the pass.
"$REPO/.venv/bin/signal-decisions" track --storage-root "$STORE" \
  --log-scan "$PAGE" --output json \
  > "$LOG/paper-tracking-$STAMP.json" 2> "$LOG/paper-tracking-$STAMP.err"
echo "$(date -Is) paper_tracking_exit=$?" >> "$LOG/scan-$STAMP.err"
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
  # Same-date artifacts from an earlier pass do not describe this page; leaving
  # them would let the report claim dossiers or a lifecycle that this pass never
  # produced.
  rm -f "$ANALYSIS" "$RESEARCH" "$LIFECYCLE"
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

# Deterministic pass report. Written after analysis, dossiers and lifecycle so it
# renders this pass, not the previous one. Facts only, never advice, and it must
# never fail the pass.
"$REPO/.venv/bin/python" "$REPO/scripts/pass_report.py" \
  --storage-root "$STORE" --artifacts-dir "$LOG" --date "$STAMP" \
  > "$LOG/report-$STAMP.md" 2> "$LOG/report-$STAMP.err"
echo "$(date -Is) pass_report_exit=$?" >> "$LOG/scan-$STAMP.err"

# Every real pass must reach the owner's private ledger. This stage is what keeps
# an unattended run from producing evidence with no research record. It skips a
# degenerate page (all members failing one upstream reason) and never overwrites
# an entry that already cites this page's handle.
if [ -n "${SWING_LEDGER_ROOT:-}" ]; then
  ledger_args=(--scan-json "$PAGE" --ledger-root "$SWING_LEDGER_ROOT" \
    --storage-root "$STORE" --status unconfirmed)
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

    # A pass with no entry for this session is not delivered. The page's own
    # evidence handle is checked, not the calendar date: a scan can bind an older
    # completed session, and a date filter would then pass vacuously.
    COVERAGE_HANDLE=$(
      python3 -c 'import json, sys
try:
    payload = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    payload = {}
value = payload.get("decision_evidence_handle") if isinstance(payload, dict) else None
print(value if isinstance(value, str) and len(value) == 64 else "")' "$PAGE"
    )
    coverage_args=(--storage-root "$STORE" --ledger-root "$SWING_LEDGER_ROOT" --output table)
    if [ -n "$COVERAGE_HANDLE" ]; then
      coverage_args+=(--handle "$COVERAGE_HANDLE")
    else
      coverage_args+=(--since "$STAMP")
    fi
    "$REPO/.venv/bin/python" "$REPO/scripts/check_ledger_coverage.py" \
      "${coverage_args[@]}" > "$LOG/coverage-$STAMP.log" 2>&1
    coverage_code=$?
    echo "$(date -Is) coverage_exit=$coverage_code" >> "$LOG/scan-$STAMP.err"
    if [ "$coverage_code" -ne 0 ]; then
      echo "$(date -Is) coverage gap for $STAMP; see $LOG/coverage-$STAMP.log" \
        >> "$LOG/scan-$STAMP.err"
      exit "$coverage_code"
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
