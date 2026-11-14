#!/usr/bin/env bash
# Independent, incremental provider capture, run before research.
#
# Sub-step 1 writes the raw session cache research reads. Sub-step 2 updates the
# adjusted-daily benchmark store per 100-member cohort. Both read only the
# governed retained Nifty 200 snapshot and the date; neither reads the exchange
# calendar, pair state, safety policy, or research result. Existing data is
# reused: a member whose newest retained session already reaches the requested
# end is skipped without a provider request, and an adjusted cohort is skipped
# only when every one of its instruments already has the requested session.
# One sub-step failing does not stop the other.
set -u

SCRIPT_PATH=${BASH_SOURCE[0]}
REPO=${SWING_REPO:-$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)}
STORE=${SWING_STORAGE_ROOT:-$HOME/SwingTradingAIAssistantData}
DOPPLER=${DOPPLER_BIN:-$HOME/.local/bin/doppler}
PROJECT=${SWING_DOPPLER_PROJECT:-swing-trading}
CONFIG=${SWING_DOPPLER_CONFIG:-dev}
PYTHON=${SWING_CAPTURE_PYTHON:-$REPO/.venv/bin/python}
RAW=${SWING_CAPTURE_RAW_SCRIPT:-$REPO/scripts/capture_bharatstock_current.py}
ADJUSTED_COHORTS=${SWING_CAPTURE_ADJUSTED_SCRIPT:-$REPO/scripts/capture_adjusted_cohorts.py}
DOWNLOADER=${SWING_CAPTURE_DOWNLOADER:-$REPO/.venv/bin/equity-data-download}
START_DAYS=${SWING_CAPTURE_START_DAYS:-45}
LOG=${SWING_LOG_DIR:-$STORE/daily-scan}
STAMP=${SWING_DATE_OVERRIDE:-$(TZ=Asia/Kolkata date +%F)}
UNIVERSE="$STORE/universe_snapshots/nifty-universe-v3.json"

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

[ -d "$STORE" ] || { echo "capture_invalid: storage root unavailable: $STORE" >&2; exit 2; }
[ -f "$UNIVERSE" ] || { echo "capture_invalid: universe snapshot unavailable: $UNIVERSE" >&2; exit 2; }
mkdir -p "$LOG" || exit 1

# The capture scripts and helpers must run this checkout's admitted readers and
# downloader module, not a stale site-packages copy.
if [ -d "$REPO/src" ]; then
  export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
fi

START=${SWING_CAPTURE_START:-$(date -d "$STAMP - $START_DAYS days" +%F)}
[ -n "$START" ] || { echo "capture_invalid: invalid start date" >&2; exit 2; }

INSTRUMENTS=$(mktemp) || exit 1
ADJ_RESULTS=$(mktemp) || exit 1
trap 'rm -f "$INSTRUMENTS" "$ADJ_RESULTS"' EXIT

# Governed universe admission: schema, official URLs, digests, counts, and
# membership consistency are validated before any provider effect.
if ! "$PYTHON" "$ADJUSTED_COHORTS" members --storage-root "$STORE" \
    > "$INSTRUMENTS" 2> "$LOG/capture-universe-$STAMP.err"; then
  echo "capture_invalid: governed Nifty 200 snapshot is unavailable or invalid" >&2
  exit 2
fi
[ -s "$INSTRUMENTS" ] || { echo "capture_invalid: no universe instruments" >&2; exit 2; }

# A terminated preflight must not leave provider processes behind. `timeout`
# signals this process group; the trap also stops the active child and exits
# with the conventional signal status.
CHILD_PID=""
terminate_child() {
  if [ -n "$CHILD_PID" ]; then
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
    CHILD_PID=""
  fi
}
on_signal() {
  trap - TERM INT
  terminate_child
  exit "$1"
}
trap 'on_signal 143' TERM
trap 'on_signal 130' INT
run_child() {
  # Never let a provider child consume the planner TSV on inherited stdin.
  "$@" < /dev/null &
  CHILD_PID=$!
  local code=0
  wait "$CHILD_PID" || code=$?
  CHILD_PID=""
  return "$code"
}

# --- Sub-step 1: raw session cache -----------------------------------------
RAW_OUT="$LOG/capture-sessions-$STAMP.json"
RAW_ERR="$LOG/capture-sessions-$STAMP.err"
CHECKPOINT="$LOG/capture-sessions-$STAMP.checkpoint.json"
: > "$RAW_OUT"
run_child "$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
  "$PYTHON" "$RAW" \
  --storage-root "$STORE" \
  --universe-snapshot "$UNIVERSE" \
  --start "$START" --end "$STAMP" \
  --checkpoint "$CHECKPOINT" --delay 1 \
  > "$RAW_OUT" 2> "$RAW_ERR"
raw_code=$?

# --- Sub-step 2: adjusted daily store, per 100-member cohort ----------------
ADJ_PLAN_JSON="$LOG/capture-adjusted-plan-$STAMP.json"
ADJ_PLAN_TSV="$LOG/capture-adjusted-plan-$STAMP.tsv"
ADJ_ERR="$LOG/capture-adjusted-$STAMP.err"
ADJ_ERROR=""
: > "$ADJ_PLAN_TSV"
: > "$ADJ_RESULTS"
if ! "$PYTHON" "$ADJUSTED_COHORTS" plan --storage-root "$STORE" \
    --stamp "$STAMP" --stage-start "$START" \
    --json-out "$ADJ_PLAN_JSON" --format tsv > "$ADJ_PLAN_TSV" 2>> "$ADJ_ERR"; then
  ADJ_ERROR="ADJUSTED_PLAN_FAILED"
fi

ADJ_BUDGET=$("$PYTHON" - <<'PY'
from equity_data_downloader.core import _CALL_CONFIGURATION

print(int(_CALL_CONFIGURATION["max_requests"]))  # pyright: ignore[reportPrivateUsage]
PY
)
adj_budget_code=$?
if [ -z "$ADJ_ERROR" ] && [ "$adj_budget_code" -ne 0 ]; then
  ADJ_ERROR="ADJUSTED_BUDGET_UNREADABLE"
fi

if [ -z "$ADJ_ERROR" ]; then
  while IFS='|' read -r c_index c_status c_members c_start c_missing_count \
      c_unretained c_missing c_oldest; do
    [ -n "$c_index" ] || continue
    if [ "$c_status" = "SKIPPED" ]; then
      printf '%s|SKIPPED|%s|%s|0||||0|0|0|\n' \
        "$c_index" "$c_members" "$c_members" >> "$ADJ_RESULTS"
      continue
    fi
    IFS=',' read -r -a missing_keys <<< "$c_missing"
    args=()
    for key in "${missing_keys[@]}"; do
      args+=(--instrument "$key")
    done
    batch_out="$LOG/capture-adjusted-$STAMP-cohort-$c_index.json"
    batch_err="$LOG/capture-adjusted-$STAMP-cohort-$c_index.err"
    : > "$batch_out"
    : > "$batch_err"
    run_child "$DOPPLER" run --project "$PROJECT" --config "$CONFIG" -- \
      "$DOWNLOADER" "${args[@]}" --start "$c_start" --end "$STAMP" \
      --storage-root "$STORE" \
      > "$batch_out" 2> "$batch_err"
    code=$?
    cat "$batch_err" >> "$ADJ_ERR"
    requests=$("$PYTHON" - "$batch_out" <<'PY'
import json
import sys

count = None
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        for line in reversed(handle.read().splitlines()):
            if line.strip():
                value = json.loads(line)
                count = value.get("provider_requests_used")
                break
except (OSError, ValueError):
    count = None
print(count if type(count) is int and count >= 0 else "")
PY
)
    verify=$("$PYTHON" "$ADJUSTED_COHORTS" verify --storage-root "$STORE" \
      --stamp "$STAMP" --cohort-index "$c_index" --format tsv \
      2>> "$ADJ_ERR") || verify="|INCOMPLETE|0|"
    IFS='|' read -r _v_index v_status v_missing_count _v_missing <<< "$verify"
    cohort_status=COMPLETE
    cohort_error=""
    if [ "$code" -ne 0 ]; then
      if [ "$c_start" = "$STAMP" ] && [ "$c_unretained" = "0" ] \
          && grep -q "no valid requested member history" "$batch_err"; then
        # Every missing member already has a retained prior session and the
        # only requested session is the stamp itself. No session was published
        # there (weekend, holiday, or unpublished close): a typed no-op, not a
        # data failure.
        cohort_status=NO_NEWER_SESSION
      else
        cohort_status=INCOMPLETE
        cohort_error="COHORT_BATCH_FAILED"
      fi
    elif [ "$v_status" != "COMPLETE" ]; then
      cohort_status=INCOMPLETE
      cohort_error="COHORT_INCOMPLETE_AFTER_BATCH"
    fi
    [ -n "$ADJ_ERROR" ] || ADJ_ERROR="$cohort_error"
    printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
      "$c_index" "$cohort_status" "$c_members" \
      "$(( c_members - v_missing_count ))" "$c_missing_count" \
      "$c_start" "$c_oldest" "$code" "$requests" "${#missing_keys[@]}" \
      "$v_missing_count" "$cohort_error" >> "$ADJ_RESULTS"
  done < "$ADJ_PLAN_TSV"
fi

ADJ_STAGE="$LOG/capture-adjusted-stage-$STAMP.json"
"$PYTHON" - "$ADJ_STAGE" "$ADJ_PLAN_JSON" "$ADJ_RESULTS" "$STAMP" "$START" \
  "$ADJ_BUDGET" "$ADJ_ERROR" <<'PY'
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path


def _module_identity(module_name):
    try:
        module = importlib.import_module(module_name)
        path = Path(str(module.__file__))
        return {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    except Exception:  # noqa: BLE001 - an unavailable module is reported unknown
        return {"path": None, "sha256": None}


(
    path,
    plan_path,
    results_path,
    stamp,
    stage_start,
    budget,
    plan_error,
) = sys.argv[1:8]
try:
    with open(plan_path, encoding="utf-8") as handle:
        plan_value = json.load(handle)
    plan = plan_value if isinstance(plan_value, dict) else {}
except (OSError, ValueError):
    plan = {}
cohorts = []
try:
    with open(results_path, encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) != 12:
                continue
            (
                index,
                status,
                members,
                current,
                missing_count,
                start,
                oldest_missing,
                exit_code,
                requests,
                submitted,
                missing_after,
                error,
            ) = fields
            cohorts.append(
                {
                    "index": int(index),
                    "status": status,
                    "members": int(members),
                    "current": int(current),
                    "missing": int(missing_count),
                    "start": start or None,
                    "oldest_missing": oldest_missing or None,
                    "batch_exit_code": int(exit_code) if exit_code else None,
                    "provider_requests_used": int(requests) if requests else None,
                    "instruments_submitted": int(submitted),
                    "missing_after_batch": int(missing_after),
                    "error": error or None,
                }
            )
except (OSError, ValueError):
    cohorts = []
statuses = {cohort["status"] for cohort in cohorts}
if plan_error or not cohorts:
    status = "INCOMPLETE"
elif statuses == {"SKIPPED"}:
    status = "SKIPPED"
elif statuses <= {"COMPLETE", "SKIPPED", "NO_NEWER_SESSION"}:
    status = "COMPLETE"
else:
    status = "INCOMPLETE"
invoked = [
    cohort
    for cohort in cohorts
    if cohort["batch_exit_code"] is not None
]
known = [
    cohort["provider_requests_used"]
    for cohort in invoked
    if cohort["provider_requests_used"] is not None
]
starts = [cohort["start"] for cohort in cohorts if cohort["start"]]
payload = {
    "schema": "adjusted-capture-stage@v2",
    "status": status,
    "cohort_size": int(plan.get("cohort_size") or 100),
    "members": int(plan.get("members") or 0),
    "cohorts": cohorts,
    "cohorts_complete": sum(
        1 for cohort in cohorts if cohort["status"] == "COMPLETE"
    ),
    "cohorts_skipped": sum(
        1 for cohort in cohorts if cohort["status"] == "SKIPPED"
    ),
    "cohorts_incomplete": sum(
        1 for cohort in cohorts if cohort["status"] == "INCOMPLETE"
    ),
    "cohorts_no_newer_session": sum(
        1 for cohort in cohorts if cohort["status"] == "NO_NEWER_SESSION"
    ),
    "provider_requests_used": (
        sum(known) if known else (0 if not invoked else None)
    ),
    "provider_requests_complete": all(
        cohort["provider_requests_used"] is not None for cohort in invoked
    ),
    "provider_requests_basis": "DOWNLOADER_CLI_RECEIPT",
    "instruments_submitted": sum(
        cohort["instruments_submitted"] for cohort in cohorts
    ),
    "provider_request_budget": (
        int(budget) if budget.isdigit() else 0
    )
    * len(invoked),
    "provider_request_budget_basis": (
        "DOWNLOADER_MAX_REQUESTS_PER_INVOCATION * BATCHES_INVOKED"
    ),
    "range": {
        "start": min(starts) if starts else (stage_start or stamp),
        "end": stamp,
    },
    "universe": plan.get("universe"),
    "runtime": {
        "planner": plan.get("runtime"),
        "downloader": _module_identity("equity_data_downloader.core"),
    },
    "error": plan_error or None,
    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, indent=2)
    handle.write("\n")
PY
adj_stage_code=$?

# --- Composite receipt ------------------------------------------------------
RECEIPT="$LOG/capture-$STAMP.json"
RECEIPT_STATUS=$("$PYTHON" - "$RAW_OUT" "$ADJ_STAGE" "$RECEIPT" "$STAMP" "$raw_code" \
  "$SCRIPT_PATH" "$STARTED_AT" <<'PY'
import hashlib
import json
import sys
import time

raw_path, adj_path, receipt_path, stamp, raw_code, script_path, started_at = (
    sys.argv[1:8]
)
try:
    with open(raw_path, encoding="utf-8") as handle:
        raw_value = json.load(handle)
    raw = raw_value if isinstance(raw_value, dict) else {}
except (OSError, ValueError):
    raw = {}
try:
    with open(adj_path, encoding="utf-8") as handle:
        adj_value = json.load(handle)
    adjusted = adj_value if isinstance(adj_value, dict) else {}
except (OSError, ValueError):
    adjusted = {"status": "INCOMPLETE", "error": "ADJUSTED_STAGE_UNREADABLE"}

raw_status = raw.get("status")
try:
    failed = int(raw.get("failed") or 0)
    remaining = raw.get("remaining_pending")
    if not isinstance(remaining, int):
        remaining = int(raw.get("pending_symbols") or 0)
except (TypeError, ValueError):
    failed, remaining = 1, 1
adjusted_status = adjusted.get("status")
complete = (
    raw_status in {"COMPLETE", "SKIPPED"}
    and int(raw_code) == 0
    and adjusted_status in {"COMPLETE", "SKIPPED"}
    and failed == 0
    and remaining == 0
)
try:
    script_sha256 = hashlib.sha256(open(script_path, "rb").read()).hexdigest()
except OSError:
    script_sha256 = None
symbols = raw.get("symbols")
symbols = symbols if isinstance(symbols, dict) else {}
failed_isins = raw.get("failed_isins")
failed_isins = failed_isins if isinstance(failed_isins, list) else []
raw_requests = int(raw.get("requests_used") or 0)
raw_max = int(raw.get("requests_configured_max") or 0)
adj_requests = adjusted.get("provider_requests_used")
adj_budget = int(adjusted.get("provider_request_budget") or 0)
receipt = {
    "schema": "provider-capture@v3",
    "stamp": stamp,
    "status": "COMPLETE" if complete else "INCOMPLETE",
    "failed": failed,
    "remaining_pending": remaining,
    "latest_session": raw.get("latest_session"),
    "symbols": symbols,
    "symbols_total": len(symbols),
    "symbols_complete": sum(
        1
        for record in symbols.values()
        if isinstance(record, dict) and record.get("status") == "COMPLETE"
    ),
    "symbols_skipped": sum(
        1
        for record in symbols.values()
        if isinstance(record, dict) and record.get("status") == "SKIPPED"
    ),
    "symbols_no_newer_session": sum(
        1
        for record in symbols.values()
        if isinstance(record, dict) and record.get("status") == "NO_NEWER_SESSION"
    ),
    "failed_isins": failed_isins,
    "universe": raw.get("universe"),
    "universe_snapshot": raw.get("universe_snapshot"),
    "universe_snapshot_sha256": raw.get("universe_snapshot_sha256"),
    # Unlike units are never summed: the raw stage counts actual provider
    # requests, the adjusted stage reports the downloader's own request count
    # (or an explicit unknown), and instrument counts stay separate.
    "quota": {
        "raw": {
            "provider_requests_used": raw_requests,
            "requests_configured_max": raw_max,
            "max_requests_per_member": raw.get("max_requests_per_member"),
            "basis": "PROVIDER_REQUESTS_INCLUDING_FAILED_ATTEMPTS",
        },
        "adjusted": {
            "provider_requests_used": adj_requests,
            "provider_requests_complete": adjusted.get(
                "provider_requests_complete"
            ),
            "provider_request_budget": adj_budget,
            "instruments_submitted": adjusted.get("instruments_submitted"),
            "basis": adjusted.get("provider_requests_basis"),
        },
    },
    "stages": {
        "raw": {
            "status": raw_status,
            "exit_code": int(raw_code),
            "provider_requests_used": raw_requests,
            "requests_configured_max": raw_max,
            "sessions_written": raw.get("sessions_written"),
            "no_newer_session": raw.get("no_newer_session"),
            "latest_session": raw.get("latest_session"),
        },
        "adjusted": {
            "status": adjusted_status,
            "provider_requests_used": adj_requests,
            "provider_requests_complete": adjusted.get(
                "provider_requests_complete"
            ),
            "provider_request_budget": adj_budget,
            "instruments_submitted": adjusted.get("instruments_submitted"),
            "cohorts": adjusted.get("cohorts"),
            "cohorts_complete": adjusted.get("cohorts_complete"),
            "cohorts_skipped": adjusted.get("cohorts_skipped"),
            "cohorts_incomplete": adjusted.get("cohorts_incomplete"),
            "cohorts_no_newer_session": adjusted.get(
                "cohorts_no_newer_session"
            ),
            "range": adjusted.get("range"),
            "error": adjusted.get("error"),
        },
    },
    "runtime": {
        "raw": raw.get("runtime"),
        "adjusted": adjusted.get("runtime"),
        "composite": {
            "path": script_path,
            "sha256": script_sha256,
            "python": sys.version.split()[0],
        },
    },
    "timestamps": {
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
    "sessions": raw,
    "adjusted": adjusted,
}
with open(receipt_path, "w", encoding="utf-8") as handle:
    json.dump(receipt, handle, sort_keys=True, indent=2)
    handle.write("\n")
print("1" if complete else "0")
PY
)
receipt_code=$?

[ "$adj_stage_code" -eq 0 ] || exit 2
[ "$receipt_code" -eq 0 ] || exit 2
[ "$RECEIPT_STATUS" = "1" ] || exit 1
exit 0
